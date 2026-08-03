"""Einstiegspunkt fuer den Produktivbetrieb (gunicorn).

    gunicorn --bind 0.0.0.0:8080 stadionheft.web.wsgi:app

Besonderheit: Ein Konfigurationsfehler darf hier **nicht** dazu fuehren, dass
der Prozess beim Start abstuerzt. Sonst laeuft der Container auf der NAS in
eine Neustartschleife und der Benutzer sieht nur „Seite nicht erreichbar" --
also genau nicht den Hinweis, den er braucht.

Stattdessen wird eine Ersatzanwendung ausgeliefert, die den Fehler und den
naechsten Schritt anzeigt.
"""

from __future__ import annotations

from flask import Flask, render_template

from ..errors import StadionheftFehler
from ..logging_setup import einrichten, logger
from . import app_erzeugen


def _ersatz_app(fehler: StadionheftFehler) -> Flask:
    """Minimale Anwendung, die nur den Konfigurationsfehler erklaert."""
    app = Flask(__name__)

    class _Platzhalter:
        hefttitel = "Stadionheft"
        vereinsname = "Einrichtung nicht abgeschlossen"
        saison = ""

    @app.context_processor
    def kontext():
        return {"konfiguration": _Platzhalter()}

    # Die Endpunktnamen 'start' und 'hilfe' muessen existieren, weil das
    # gemeinsame Seitengeruest per url_for darauf verweist.
    @app.route("/", endpoint="start", defaults={"pfad": ""})
    @app.route("/hilfe", endpoint="hilfe", defaults={"pfad": "hilfe"})
    @app.route("/<path:pfad>")
    def einrichtung(pfad: str):
        return render_template(
            "fehler.html",
            titel="Einrichtung nicht abgeschlossen",
            meldung=fehler.benutzer_text,
            hinweis=(fehler.hinweis or "") + "\n\n"
                    "Im Docker-Betrieb liegt die Konfiguration im gemounteten "
                    "Ordner (Standard: /volume1/Stadionheft/00_Konfiguration). "
                    "Dorthin gehören config.yaml, heftplan.yaml und "
                    "kontakte.yaml. Vorlagen dafür stehen im Repository unter "
                    "config/*.example.yaml.\n\n"
                    "Nach dem Ablegen der Dateien den Container neu starten.",
            technisch=fehler.technisch), 503

    return app


try:
    app = app_erzeugen()
except StadionheftFehler as _fehler:
    einrichten()
    logger().error("Start ohne gueltige Konfiguration: %s", _fehler.technisch)
    app = _ersatz_app(_fehler)
