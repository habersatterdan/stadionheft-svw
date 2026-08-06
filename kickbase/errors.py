"""Fehlerklassen mit verstaendlichen deutschen Meldungen.

Aufbau bewusst wie im Stadionheft-Generator: jeder Fehler traegt einen
technischen Text fuers Protokoll und einen Text, den die Oberflaeche
unveraendert anzeigen kann.
"""

from __future__ import annotations


class KickbaseFehler(Exception):
    """Basisklasse fuer alle erwarteten Fehler des Beraters."""

    standard_text = "Es ist ein Fehler aufgetreten."

    def __init__(self, technisch: str = "", benutzer_text: str | None = None,
                 hinweis: str | None = None) -> None:
        super().__init__(technisch or self.standard_text)
        self.technisch = technisch or self.standard_text
        self._benutzer_text = benutzer_text
        self.hinweis = hinweis

    @property
    def benutzer_text(self) -> str:
        return self._benutzer_text or self.standard_text

    def as_dict(self) -> dict:
        return {
            "typ": type(self).__name__,
            "meldung": self.benutzer_text,
            "hinweis": self.hinweis,
            "technisch": self.technisch,
        }


class KonfigurationsFehler(KickbaseFehler):
    standard_text = (
        "Die Konfigurationsdatei konnte nicht gelesen werden. "
        "Bitte config/kickbase.yaml pruefen."
    )


class AnmeldeFehler(KickbaseFehler):
    standard_text = (
        "Die Anmeldung bei Kickbase ist fehlgeschlagen. Bitte E-Mail und "
        "Passwort pruefen."
    )


class QuelleNichtErreichbarFehler(KickbaseFehler):
    standard_text = (
        "Eine Datenquelle ist im Moment nicht erreichbar. Der Berater "
        "arbeitet solange mit den zuletzt gespeicherten Daten weiter."
    )
