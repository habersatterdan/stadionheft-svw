"""Weboberflaeche des Kickbase-Beraters (Flask).

Bewusst klein gehalten: fuenf Seiten, kein JavaScript-Framework, keine
Anmeldung ausser dem optionalen Passwortschutz. Die Seiten lesen nur aus der
Datenbank -- der Abruf laeuft getrennt davon im Hintergrund.

Aufteilung:

* ``/``             Lagebericht: eigener Kader, Warnungen, Verkaufskandidaten
* ``/markt``        Transfermarkt der Liga, jeder Spieler bewertet
* ``/kandidaten``   Kaufkandidaten aus der ganzen Liga, filterbar
* ``/spieler/<id>`` Alles zu einem Spieler samt Marktwertverlauf
* ``/hilfe``        Wie die Bewertung zustande kommt
"""

from __future__ import annotations

import threading
from datetime import datetime

from flask import (Flask, jsonify, redirect, render_template, request,
                   url_for)

from ..config import Konfiguration
from ..dienst import Berater, Planer
from ..errors import KickbaseFehler
from ..logging_setup import einrichten, logger
from ..models import POSITIONEN
from .diagramm import euro_kurz, marktwertdiagramm, sparklinie


def app_erzeugen(konfiguration: Konfiguration | None = None,
                 planer_starten: bool = True) -> Flask:
    k = konfiguration or Konfiguration.laden()
    einrichten(k.pfad(k.get("protokoll.ordner"), "logs"),
               str(k.get("protokoll.level", "INFO")))
    for warnung in k.warnungen:
        logger().warning(warnung)

    app = Flask(__name__)
    app.config["KONFIGURATION"] = k

    berater = Berater(k)
    app.config["BERATER"] = berater

    from .zugang import einrichten as zugang_einrichten
    zugang_einrichten(app, k)

    planer = Planer(berater)
    app.config["PLANER"] = planer
    if planer_starten:
        planer.starten()

    # -- Hilfen fuer die Vorlagen ------------------------------------------

    @app.context_processor
    def standard_kontext():
        return {
            "konfiguration": k,
            "titel": str(k.get("web.titel", "Kickbase-Berater")),
            "demomodus": k.demomodus,
            "positionen": POSITIONEN,
            "laeuft": berater.laeuft,
            "jetzt": datetime.now(),
        }

    def zeitpunkt(roh: str) -> str:
        """ISO-Zeitstempel -> '06.08.2026, 05:04' (deutsche Schreibweise)."""
        if not roh:
            return "noch nie"
        try:
            return datetime.fromisoformat(str(roh)).strftime("%d.%m.%Y, %H:%M")
        except ValueError:
            return str(roh)

    app.jinja_env.filters["euro"] = lambda w: f"{euro_kurz(w or 0)} €"
    app.jinja_env.filters["sparklinie"] = sparklinie
    app.jinja_env.filters["zeitpunkt"] = zeitpunkt

    # -- Seiten ------------------------------------------------------------

    @app.get("/gesundheit")
    def gesundheit():
        """Fuer den Healthcheck des Containers -- bewusst ohne Anmeldung."""
        return {"status": "ok"}

    @app.get("/")
    def start():
        bericht = berater.bericht()
        return render_template("start.html", bericht=bericht,
                               letzter_abruf=berater.speicher.letzter_abruf())

    @app.get("/markt")
    def markt():
        bericht = berater.bericht()
        return render_template("markt.html", bericht=bericht)

    @app.get("/kandidaten")
    def kandidaten():
        bericht = berater.bericht()
        liste = bericht.kandidaten

        position = request.args.get("position", "").strip()
        if position.isdigit():
            liste = [b for b in liste if b.spieler.position == int(position)]

        hoechstpreis = request.args.get("hoechstpreis", "").strip()
        if hoechstpreis.replace(".", "").isdigit():
            grenze = float(hoechstpreis) * 1_000_000
            liste = [b for b in liste if b.spieler.marktwert <= grenze]

        if request.args.get("nur_fit"):
            liste = [b for b in liste if b.spieler.einsatzbereit]

        return render_template(
            "kandidaten.html", bericht=bericht, liste=liste[:60],
            gesamt=len(liste), position=position, hoechstpreis=hoechstpreis,
            nur_fit=bool(request.args.get("nur_fit")))

    @app.get("/spieler/<spieler_id>")
    def spieler(spieler_id: str):
        from ..analyse.bewertung import Referenzwerte, bewerten

        alle = berater.speicher.spieler_laden()
        treffer = next((s for s in alle if s.id == str(spieler_id)), None)
        if treffer is None:
            return render_template(
                "fehler.html",
                fehler={"meldung": "Diesen Spieler kennt der Berater nicht.",
                        "hinweis": "Vielleicht wurde er noch nie abgerufen. "
                                   "Ein neuer Abruf kann helfen."}), 404

        referenz = Referenzwerte.aus_spielern(
            alle, int(k.get("analyse.mindest_spiele", 3)))
        bewertung = bewerten(treffer, referenz, k, berater.ligalage(),
                             treffer.angebotspreis or None)
        verlauf = berater.speicher.marktwert_reihe(treffer.id, 180) or treffer.verlauf
        return render_template("spieler.html", bewertung=bewertung,
                               spieler=treffer,
                               diagramm=marktwertdiagramm(verlauf),
                               leistungen=list(reversed(treffer.letzte_leistungen(10))))

    @app.get("/hilfe")
    def hilfe():
        gewichte = {name: k.gewicht(name) for name in (
            "verfuegbarkeit", "form", "einsatzzeit", "marktwerttrend",
            "preis_leistung", "gegnerstaerke", "bewertungsniveau")}
        return render_template("hilfe.html", gewichte=gewichte,
                               abrufe=berater.speicher.abrufe(10))

    # -- Aktionen ----------------------------------------------------------

    @app.post("/abruf")
    def abruf():
        """Startet den Abruf im Hintergrund und kehrt sofort zurueck."""
        if berater.laeuft:
            return redirect(url_for("start"))

        def arbeiten():
            try:
                berater.abrufen()
            except Exception as fehler:  # pragma: no cover - Schutznetz
                logger().exception("Abruf abgebrochen: %s", fehler)

        threading.Thread(target=arbeiten, name="kickbase-abruf-web",
                         daemon=True).start()
        return redirect(url_for("start"))

    @app.get("/status.json")
    def status():
        letzter = berater.speicher.letzter_abruf() or {}
        return jsonify({
            "laeuft": berater.laeuft,
            "letzter_abruf": letzter.get("zeit", ""),
            "erfolgreich": bool(letzter.get("erfolgreich")),
            "meldung": letzter.get("meldung", ""),
        })

    @app.get("/bericht.json")
    def bericht_json():
        """Maschinenlesbare Fassung -- fuer eigene Skripte oder Benachrichtigungen."""
        bericht = berater.bericht()
        return jsonify({
            "erstellt": bericht.erstellt.isoformat(timespec="seconds"),
            "liga": bericht.liga_name,
            "budget": bericht.budget,
            "eigene": [b.als_dict() for b in bericht.eigene],
            "transfermarkt": [b.als_dict() for b in bericht.transfermarkt],
            "kandidaten": [b.als_dict() for b in bericht.kandidaten[:40]],
            "warnungen": bericht.warnungen,
            "quellen": bericht.quellen,
        })

    # -- Fehlerbehandlung --------------------------------------------------

    @app.errorhandler(KickbaseFehler)
    def kickbase_fehler(fehler: KickbaseFehler):  # pragma: no cover
        logger().error("Fehler in der Oberflaeche: %s", fehler.technisch)
        return render_template("fehler.html", fehler=fehler.as_dict()), 500

    @app.errorhandler(404)
    def nicht_gefunden(_):
        return render_template("fehler.html", fehler={
            "meldung": "Diese Seite gibt es nicht.",
            "hinweis": "Über das Menü oben geht es zurück."}), 404

    return app
