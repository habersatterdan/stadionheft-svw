"""Fehlerklassen mit verstaendlichen deutschen Meldungen.

Jeder Fehler traegt zwei Texte:

* ``benutzer_text`` -- was ein nicht-technischer Benutzer in der Oberflaeche
  lesen soll, inklusive eines konkreten Loesungsvorschlags.
* ``str(fehler)`` -- die technische Meldung fuer das Protokoll.

So kann die Weboberflaeche jeden Fehler anzeigen, ohne selbst zu wissen,
was schiefgegangen ist.
"""

from __future__ import annotations


class StadionheftFehler(Exception):
    """Basisklasse fuer alle erwarteten Fehler des Programms."""

    #: Wird angezeigt, wenn die Unterklasse nichts Eigenes setzt.
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


class KonfigurationsFehler(StadionheftFehler):
    standard_text = (
        "Die Konfigurationsdatei konnte nicht gelesen werden. "
        "Bitte config/config.yaml pruefen oder einen Administrator fragen."
    )


class VorlageFehltFehler(StadionheftFehler):
    standard_text = (
        "Eine benoetigte Vorlagen- oder Werbedatei wurde nicht gefunden. "
        "Bitte pruefen, ob die Datei im Vorlagenordner auf der NAS liegt."
    )


class DatenquelleNichtErreichbarFehler(StadionheftFehler):
    standard_text = (
        "FuPa ist im Moment nicht erreichbar. Bitte spaeter erneut versuchen "
        "oder im Programm auf 'Manuelle Eingabe' umstellen."
    )


class AdresseGesperrtFehler(StadionheftFehler):
    """Die Quelle erlaubt den Abruf dieser Adresse nicht (robots.txt).

    Bewusst **kein** Unterfall von DatenquelleNichtErreichbarFehler: Ein
    Verbot ist eine klare Auskunft, kein Ausfall. Die Adresse faellt weg,
    alle anderen werden weiter probiert.
    """

    standard_text = (
        "Diese Adresse darf laut robots.txt nicht automatisch abgerufen werden."
    )


class DatenNichtLesbarFehler(StadionheftFehler):
    standard_text = (
        "Die Daten konnten nicht gelesen werden. Moeglicherweise hat sich der "
        "Aufbau der FuPa-Seite geaendert. Bitte einen Administrator informieren."
    )


class ManuelleDatenFehlenFehler(StadionheftFehler):
    standard_text = (
        "Fuer mindestens eine Mannschaft fehlen die manuellen Eingabedateien. "
        "Bitte die CSV-Dateien im Eingabeordner ergaenzen."
    )


class RenderFehler(StadionheftFehler):
    standard_text = (
        "Beim Erzeugen der Seiten ist ein Fehler aufgetreten. "
        "Bitte das Protokoll pruefen."
    )


class NasFehler(StadionheftFehler):
    standard_text = (
        "Die Synology NAS ist nicht erreichbar oder der Zielordner existiert "
        "nicht. Das Stadionheft wurde lokal gespeichert und kann von Hand "
        "hochgeladen werden."
    )
