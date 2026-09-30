"""Weboberflaeche (Flask).

Bewusst klein gehalten: eine Seite mit dem Formular, eine Fortschrittsseite,
ein Download. Kein Login, keine Datenbank, kein JavaScript-Framework -- die
Anwendung laeuft im Vereinsnetz bzw. auf der NAS und soll auch in fuenf Jahren
noch von jemandem repariert werden koennen, der Python nur grundlegend kennt.

Die eigentliche Arbeit macht ``stadionheft.build``. Diese Schicht kuemmert sich
nur um Formular, Fortschrittsanzeige und verstaendliche Fehlermeldungen.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   send_file, url_for)

from .. import programmstand
from ..build import dateien_erstellen
from ..config import Konfiguration
from ..errors import StadionheftFehler
from ..logging_setup import LaufProtokoll, einrichten, logger


@dataclass
class Lauf:
    """Zustand eines Laufs (fuer die Fortschrittsanzeige)."""

    id: str
    gestartet: datetime = field(default_factory=datetime.now)
    fertig: bool = False
    erfolgreich: bool = False
    ergebnis: dict | None = None
    fehler: dict | None = None
    protokoll: list[dict] = field(default_factory=list)
    benutzer: str = ""

    def als_dict(self) -> dict:
        return {
            "id": self.id,
            "fertig": self.fertig,
            "erfolgreich": self.erfolgreich,
            "ergebnis": self.ergebnis,
            "fehler": self.fehler,
            "protokoll": self.protokoll[-200:],
        }


def app_erzeugen(konfiguration: Konfiguration | None = None) -> Flask:
    k = konfiguration or Konfiguration.laden()
    einrichten(k.pfad(k.get("protokoll.ordner"), "logs"),
               str(k.get("protokoll.level", "INFO")))

    app = Flask(__name__)
    app.config["KONFIGURATION"] = k

    from .zugang import einrichten as zugang_einrichten
    zugang_einrichten(app, k)

    @app.get("/gesundheit")
    def gesundheit():
        """Fuer den Healthcheck des Containers -- bewusst ohne Anmeldung."""
        return {"status": "ok"}

    # Jede Vorlage -- auch die Fehlerseiten -- braucht die Konfiguration
    # fuer Kopf- und Fusszeile.
    @app.context_processor
    def standard_kontext():
        # Der Programmstand steht in der Fusszeile jeder Seite. Grund: Auf der
        # NAS ist die haeufigste Stoerung, dass der Container noch mit altem
        # Code laeuft -- das sieht man sonst nirgends, weil nichts fehlschlaegt.
        return {"konfiguration": k, "programmstand": programmstand()}

    laeufe: dict[str, Lauf] = {}
    sperre = threading.Lock()

    # -- Seiten -------------------------------------------------------------

    @app.get("/")
    def start():
        from ..storage.nas import NasAblage
        nas_ok, nas_meldung = NasAblage(k).erreichbar()
        return render_template(
            "start.html",
            konfiguration=k,
            mannschaften=k.aktive_mannschaften(),
            modus=k.get("datenquelle.modus", "api"),
            cache_minuten=k.get("datenquelle.cache.gueltigkeit_minuten", 15),
            nas_aktiv=bool(k.get("nas.aktiv", False)),
            nas_ok=nas_ok,
            nas_meldung=nas_meldung,
            warnungen=k.warnungen,
        )

    @app.post("/erstellen")
    def erstellen():
        auswahl = request.form.getlist("mannschaften")
        if not auswahl:
            return render_template(
                "fehler.html",
                titel="Keine Mannschaft ausgewählt",
                meldung="Bitte mindestens eine Mannschaft anhaken.",
                hinweis="", technisch=""), 400

        lauf = Lauf(id=uuid.uuid4().hex[:12],
                    benutzer=request.form.get("benutzer", "").strip())
        with sperre:
            laeufe[lauf.id] = lauf

        argumente = {
            "mannschaften": auswahl,
            "spieltag": request.form.get("spieltag", "").strip(),
            "datenquelle": request.form.get("quelle") or None,
            "erzeugt_von": lauf.benutzer or "Weboberfläche",
            "frisch": request.form.get("frisch") == "ja",
        }

        threading.Thread(target=_lauf_ausfuehren, args=(k, lauf, argumente),
                         daemon=True).start()
        return redirect(url_for("fortschritt", lauf_id=lauf.id))

    @app.get("/lauf/<lauf_id>")
    def fortschritt(lauf_id: str):
        lauf = laeufe.get(lauf_id)
        if not lauf:
            abort(404)
        return render_template("lauf.html", lauf=lauf, konfiguration=k)

    @app.get("/lauf/<lauf_id>/status")
    def status(lauf_id: str):
        lauf = laeufe.get(lauf_id)
        if not lauf:
            return jsonify({"fehlt": True}), 404
        return jsonify(lauf.als_dict())

    @app.get("/lauf/<lauf_id>/download")
    def download(lauf_id: str):
        """Alle Dateien als ZIP -- ein Klick statt fuenf."""
        lauf = laeufe.get(lauf_id)
        if not lauf or not lauf.ergebnis:
            abort(404)
        pfad = Path(lauf.ergebnis.get("archiv") or "")
        if not str(pfad) or not pfad.exists():
            abort(404)
        return send_file(pfad, as_attachment=True, download_name=pfad.name)

    @app.get("/lauf/<lauf_id>/datei/<int:nummer>")
    def datei(lauf_id: str, nummer: int):
        """Eine einzelne Mannschaftsdatei."""
        lauf = laeufe.get(lauf_id)
        if not lauf or not lauf.ergebnis:
            abort(404)
        dateien = lauf.ergebnis.get("dateien") or []
        if not 0 <= nummer < len(dateien):
            abort(404)
        pfad = Path(dateien[nummer]["pfad"])
        if not pfad.exists():
            abort(404)
        return send_file(pfad, as_attachment=True, download_name=pfad.name)

    @app.get("/hilfe")
    def hilfe():
        return render_template("hilfe.html", konfiguration=k)

    # -- FuPa-Verbindung pruefen -------------------------------------------
    # Bewusst als Knopf in der Oberflaeche und nicht nur als Befehl auf der
    # Kommandozeile: Der Test ist der eine Schritt, der den automatischen
    # Datenabruf freischaltet -- dafuer soll niemand ein Terminal oeffnen
    # muessen.

    @app.get("/fupa-test")
    def fupa_test():
        return render_template("fupa_test.html", konfiguration=k,
                               mannschaften=k.aktive_mannschaften(),
                               bericht=None)

    @app.post("/fupa-test")
    def fupa_test_starten():
        from ..sources.fupa_api import probe_fupa

        auswahl = request.form.get("mannschaft") or None
        try:
            bericht = probe_fupa(k, auswahl)
            fehler = None
        except StadionheftFehler as ausnahme:
            logger().error("FuPa-Test fehlgeschlagen: %s", ausnahme.technisch)
            bericht, fehler = None, ausnahme.as_dict()

        return render_template("fupa_test.html", konfiguration=k,
                               mannschaften=k.aktive_mannschaften(),
                               bericht=bericht, fehler=fehler)

    @app.get("/fupa-test/download")
    def fupa_test_download():
        """Packt die Rohantworten als ZIP -- die Datei, die zur Auswertung
        weitergegeben wird."""
        import io
        import zipfile

        ordner = Path(k.arbeits_ordner) / "fupa_probe"
        if not ordner.is_dir():
            abort(404)

        puffer = io.BytesIO()
        with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as archiv:
            # Auch die Rohantworten: Wenn nichts erkannt wurde, sind sie
            # das Einzige, woran sich der Aufbau der Seite ablesen laesst.
            for muster in ("*.json", "*.html", "*.txt"):
                for datei in sorted(ordner.glob(muster)):
                    archiv.write(datei, arcname=datei.name)
        puffer.seek(0)
        return send_file(puffer, mimetype="application/zip", as_attachment=True,
                         download_name="fupa_probe.zip")

    # -- Fehlerbehandlung ---------------------------------------------------

    @app.errorhandler(404)
    def nicht_gefunden(_fehler):
        return render_template(
            "fehler.html", titel="Seite nicht gefunden",
            meldung="Diese Adresse gibt es nicht (mehr).",
            hinweis="Vermutlich wurde die Anwendung zwischenzeitlich neu gestartet.",
            technisch=""), 404

    @app.errorhandler(StadionheftFehler)
    def bekannter_fehler(fehler: StadionheftFehler):
        logger().error("%s", fehler.technisch)
        return render_template(
            "fehler.html", titel="Es ist ein Fehler aufgetreten",
            meldung=fehler.benutzer_text, hinweis=fehler.hinweis or "",
            technisch=fehler.technisch), 500

    return app


def _lauf_ausfuehren(k: Konfiguration, lauf: Lauf, argumente: dict) -> None:
    """Laeuft im Hintergrund-Thread und fuellt ``lauf`` mit dem Ergebnis."""
    with LaufProtokoll() as protokoll:
        lauf.protokoll = protokoll.zeilen
        try:
            ergebnis = dateien_erstellen(k, **argumente)
            lauf.ergebnis = ergebnis.als_dict()
            lauf.erfolgreich = True
        except StadionheftFehler as fehler:
            logger().error("Lauf abgebrochen: %s", fehler.technisch)
            lauf.fehler = fehler.as_dict()
        except Exception as fehler:  # noqa: BLE001
            logger().exception("Unerwarteter Fehler beim Erzeugen der Dateien")
            lauf.fehler = {
                "typ": type(fehler).__name__,
                "meldung": "Im Programm ist ein unerwarteter Fehler aufgetreten.",
                "hinweis": "Bitte einen Administrator informieren. Details "
                           "stehen im Protokoll unter logs/.",
                "technisch": str(fehler),
            }
        finally:
            lauf.fertig = True
