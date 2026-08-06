"""Optionaler Passwortschutz fuer die Weboberflaeche.

Im eigenen Heimnetz ist ein Zugangsschutz meist unnoetig. Sobald die
Anwendung aber von aussen erreichbar sein soll, gilt das nicht mehr: hinter
dieser Oberflaeche stehen die eigenen Kickbase-Daten.

Der Schutz ist **standardmaessig aus** und wird ueber die Konfiguration
eingeschaltet::

    web:
      passwortschutz: true
      benutzer: "kickbase"

Das Passwort steht nie in der Konfigurationsdatei, sondern kommt aus der
Umgebungsvariablen ``KICKBASE_WEB_PASSWORT``.

Einschraenkung: Verwendet wird HTTP Basic Authentication. Die Zugangsdaten
werden dabei nur kodiert, **nicht verschluesselt** uebertragen. Das genuegt
hinter einem HTTPS-Reverse-Proxy oder im VPN -- ueber eine offene
HTTP-Verbindung ins Internet waere es wertlos.
"""

from __future__ import annotations

import hmac

from flask import Response, request

from ..config import Konfiguration
from ..logging_setup import logger

#: Adressen, die auch ohne Anmeldung erreichbar bleiben.
OFFEN = {"/gesundheit"}


class Zugangsschutz:
    def __init__(self, konfiguration: Konfiguration) -> None:
        self.aktiv = bool(konfiguration.get("web.passwortschutz", False))
        self.benutzername = str(konfiguration.get("web.benutzer", "kickbase"))
        self.passwort = konfiguration.web_passwort

        if self.aktiv and not self.passwort:
            logger().error(
                "web.passwortschutz ist eingeschaltet, aber KICKBASE_WEB_PASSWORT "
                "ist leer. Es kommt niemand hinein, bis sie gesetzt ist.")

    def stimmt(self, benutzer: str, passwort: str) -> bool:
        """Vergleich in konstanter Zeit gegen zeichenweises Erraten."""
        if not self.passwort:
            return False
        return (hmac.compare_digest(benutzer or "", self.benutzername)
                and hmac.compare_digest(passwort or "", self.passwort))

    def anmeldung_verlangen(self) -> Response:
        return Response(
            "Zugang nur mit Anmeldung.\n", 401,
            {"WWW-Authenticate": 'Basic realm="Kickbase-Berater", charset="UTF-8"'})


def einrichten(app, konfiguration: Konfiguration) -> Zugangsschutz:
    """Haengt den Schutz vor jede Anfrage der Anwendung."""
    schutz = Zugangsschutz(konfiguration)

    if not schutz.aktiv:
        logger().info("Kein Passwortschutz aktiv (nur fuer das eigene Netz gedacht).")
        return schutz

    @app.before_request
    def pruefen():  # pragma: no cover - ueber Testclient mitgetestet
        if request.path in OFFEN:
            return None
        angaben = request.authorization
        if angaben and schutz.stimmt(angaben.username or "",
                                     angaben.password or ""):
            return None
        return schutz.anmeldung_verlangen()

    logger().info("Passwortschutz aktiv (Benutzer '%s').", schutz.benutzername)
    return schutz
