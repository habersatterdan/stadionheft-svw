"""Optionaler Passwortschutz fuer die Weboberflaeche.

Im Vereinsnetz ist ein Zugangsschutz nicht noetig -- wer im WLAN ist, darf
auch ein Heft bauen. Sobald die Anwendung aber von aussen erreichbar sein
soll, gilt das nicht mehr: Ohne Schutz koennte jeder, der die Adresse kennt,
Hefte erzeugen und die abgelegten Daten sehen.

Deshalb dieser Schalter. Er ist **standardmaessig aus** und wird ueber die
Konfiguration eingeschaltet::

    zugang:
      passwortschutz: true
      benutzername: "svw"
      passwort_umgebungsvariable: "STADIONHEFT_PASSWORT"

Das Passwort steht wie beim NAS-Zugang **nie in der Konfigurationsdatei**,
sondern kommt aus einer Umgebungsvariablen.

Wichtige Einschraenkung
-----------------------
Verwendet wird HTTP Basic Authentication. Die Zugangsdaten werden dabei nur
base64-kodiert uebertragen -- **nicht verschluesselt**. Das ist ausreichend,
wenn die Verbindung selbst per HTTPS geschuetzt ist (DSM-Reverse-Proxy mit
Zertifikat). Ueber eine unverschluesselte http-Verbindung ins Internet waere
es wertlos.

Der sicherste Weg bleibt ein VPN. Dieser Schutz ist die zweite
Verteidigungslinie, nicht die erste.
"""

from __future__ import annotations

import hmac
import os
from functools import wraps

from flask import Response, request

from ..config import Konfiguration
from ..logging_setup import logger

#: Adressen, die auch ohne Anmeldung erreichbar bleiben. Der Gesundheitscheck
#: des Containers soll nicht an der Anmeldung scheitern.
OFFEN = {"/gesundheit"}


class Zugangsschutz:
    def __init__(self, konfiguration: Konfiguration) -> None:
        self.aktiv = bool(konfiguration.get("zugang.passwortschutz", False))
        self.benutzername = str(konfiguration.get("zugang.benutzername", "svw"))
        variable = str(konfiguration.get("zugang.passwort_umgebungsvariable",
                                         "STADIONHEFT_PASSWORT"))
        self.variable = variable
        self.passwort = os.environ.get(variable, "")

        if self.aktiv and not self.passwort:
            # Bewusst *nicht* stillschweigend den Schutz abschalten -- lieber
            # laut warnen, damit es auffaellt.
            logger().error(
                "zugang.passwortschutz ist eingeschaltet, aber die "
                "Umgebungsvariable %s ist leer. Es kommt niemand hinein, "
                "bis sie gesetzt ist.", variable)

    def stimmt(self, benutzer: str, passwort: str) -> bool:
        """Vergleich in konstanter Zeit, damit sich das Passwort nicht
        zeichenweise erraten laesst."""
        if not self.passwort:
            return False
        return (hmac.compare_digest(benutzer or "", self.benutzername)
                and hmac.compare_digest(passwort or "", self.passwort))

    def anmeldung_verlangen(self) -> Response:
        return Response(
            "Zugang nur für Berechtigte des SV Wörnitzstein-Berg.\n",
            401,
            {"WWW-Authenticate": 'Basic realm="Stadionheft", charset="UTF-8"'},
        )


def einrichten(app, konfiguration: Konfiguration) -> Zugangsschutz:
    """Haengt den Schutz vor jede Anfrage der Anwendung."""
    schutz = Zugangsschutz(konfiguration)

    if not schutz.aktiv:
        logger().info("Kein Passwortschutz aktiv (nur fuer den Betrieb im "
                      "Vereinsnetz gedacht).")
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
