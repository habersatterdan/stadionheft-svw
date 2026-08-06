"""Einstiegspunkt fuer Gunicorn im Container.

    gunicorn --bind 0.0.0.0:8090 kickbase.web.wsgi:app

Wichtig: Der Hintergrundabruf laeuft als Faden *im* Arbeitsprozess. Deshalb
wird der Dienst mit genau **einem** Arbeitsprozess betrieben -- sonst wuerden
mehrere Prozesse gleichzeitig bei Kickbase anfragen.
"""

from __future__ import annotations

from html import escape

from ..errors import KickbaseFehler
from ..logging_setup import einrichten, logger
from . import app_erzeugen

_NOTFALL_SEITE = """<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kickbase-Berater – Start nicht möglich</title></head>
<body style="font-family:system-ui,Arial,sans-serif;max-width:40rem;margin:3rem auto;
             padding:0 1rem;line-height:1.55;color:#16191D">
<h1 style="font-size:1.4rem">Der Berater konnte nicht starten</h1>
<p style="border-left:4px solid #B4241F;background:#FCEDEC;padding:.8rem 1rem">
<strong>{meldung}</strong>{hinweis}</p>
<p style="color:#79828D;font-size:.9rem">Technisch: {technisch}</p>
<p style="color:#79828D;font-size:.9rem">Nach der Korrektur den Container neu starten.</p>
</body></html>
"""


def _notfall_app(fehler: KickbaseFehler):
    """Zeigt den Konfigurationsfehler an, statt beim Start zu sterben.

    Ein Container, der sofort abstuerzt, hinterlaesst auf der NAS nur einen
    roten Punkt. Eine Seite mit der Fehlermeldung ist deutlich hilfreicher.
    Diese Seite kommt bewusst ohne Vorlagen und ohne Konfiguration aus --
    beides koennte ja gerade das Problem sein.
    """
    from flask import Flask

    einrichten("logs", "INFO")
    logger().error("Start nicht moeglich: %s", fehler.technisch)

    app = Flask(__name__)
    seite = _NOTFALL_SEITE.format(
        meldung=escape(fehler.benutzer_text),
        hinweis=f"<br>{escape(fehler.hinweis)}" if fehler.hinweis else "",
        technisch=escape(fehler.technisch))

    @app.get("/gesundheit")
    def gesundheit():
        return {"status": "fehler", "meldung": fehler.benutzer_text}, 503

    @app.route("/", defaults={"pfad": ""})
    @app.route("/<path:pfad>")
    def alles(pfad):
        return seite, 503, {"Content-Type": "text/html; charset=utf-8"}

    return app


try:
    app = app_erzeugen()
except KickbaseFehler as _fehler:
    app = _notfall_app(_fehler)
