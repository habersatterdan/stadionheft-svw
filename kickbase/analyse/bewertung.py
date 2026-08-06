"""Aus Kennzahlen wird eine Empfehlung.

Der Ablauf ist absichtlich einfach und nachrechenbar:

1. Alle Kennzahlen berechnen (jede -100 bis +100).
2. Mit den Gewichten aus der Konfiguration mitteln -> Gesamtnote.
3. Harte Regeln pruefen, die den Rest uebersteuern duerfen -- etwa: ein
   Langzeitverletzter ist kein Kauf, egal wie gut seine Preis-Leistung ist.
4. Die Note in eine Stufe uebersetzen: Kaufen, Beobachten, Halten,
   Verkauf prüfen, Verkaufen.

Es gibt hier bewusst kein selbstlernendes Modell. Ein Punktesystem, das man
in fünf Minuten versteht und selbst nachjustieren kann, ist im Alltag mehr
wert als eine Vorhersage, der man nicht ansieht, woher sie kommt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from ..config import Konfiguration
from ..models import Bewertung, Kennzahl, Spieler
from ..quellen.openligadb import Ligalage
from . import kennzahlen as kz


@dataclass
class Referenzwerte:
    """Vergleichsmassstaebe, die aus dem gesamten Spielerfeld entstehen."""

    punkte_je_million: dict[int, float] = field(default_factory=dict)
    #: Wie viele Spieler in die Vergleichswerte eingeflossen sind.
    grundlage: int = 0

    @classmethod
    def aus_spielern(cls, spieler: Sequence[Spieler],
                     mindest_spiele: int = 3) -> "Referenzwerte":
        werte = kz.positionsvergleich(spieler, mindest_spiele)
        return cls(punkte_je_million=werte, grundlage=len(spieler))

    def vergleich(self, position: int) -> float:
        if position in self.punkte_je_million:
            return self.punkte_je_million[position]
        # Ohne Positionswert lieber den Gesamtschnitt als gar nichts.
        alle = list(self.punkte_je_million.values())
        return sum(alle) / len(alle) if alle else 0.0


def bewerten(spieler: Spieler, referenz: Referenzwerte,
             konfiguration: Konfiguration,
             ligalage: Ligalage | None = None,
             preis: int | None = None) -> Bewertung:
    """Bewertet genau einen Spieler."""
    spieltage = int(konfiguration.get("analyse.form_spieltage", 5))

    rohwerte = [
        kz.verfuegbarkeit(spieler),
        kz.form(spieler, spieltage),
        kz.einsatzzeit(spieler, spieltage),
        kz.marktwerttrend(spieler),
        kz.preis_leistung(spieler, referenz.vergleich(spieler.position), preis),
        kz.gegnerstaerke(spieler, ligalage),
        kz.bewertungsniveau(spieler),
    ]

    # Die Gewichte kommen aus der Konfiguration -- so kann jeder den Berater
    # auf seinen Spielstil einstellen, ohne den Code anzufassen.
    gewichtet: list[Kennzahl] = []
    for kennzahl in rohwerte:
        gewicht = konfiguration.gewicht(kennzahl.schluessel)
        gewichtet.append(Kennzahl(
            schluessel=kennzahl.schluessel, name=kennzahl.name,
            anzeige=kennzahl.anzeige, punkte=kennzahl.punkte,
            gewicht=gewicht, begruendung=kennzahl.begruendung))

    gewichtssumme = sum(k.gewicht for k in gewichtet) or 1.0
    gesamt = sum(k.beitrag for k in gewichtet) / gewichtssumme

    bewertung = Bewertung(spieler=spieler, gesamtpunkte=gesamt,
                          kennzahlen=gewichtet)
    _harte_regeln(bewertung, konfiguration, preis)
    return bewertung


def _harte_regeln(bewertung: Bewertung, konfiguration: Konfiguration,
                  preis: int | None) -> None:
    """Regeln, die das Punktesystem uebersteuern duerfen.

    Sie greifen selten, aber dann deutlich -- immer nur nach unten. Ein
    Punktesystem kann sonst einen Langzeitverletzten schoenrechnen, weil
    Preis-Leistung und Marktwerttrend noch aus der gesunden Zeit stammen.
    """
    spieler = bewertung.spieler
    grenzen: list[tuple[float, str]] = []

    if spieler.status in (1, 128):
        grenzen.append((-45, "Verletzt gemeldet – bis zur Rückkehr kein Kauf."))
    elif spieler.status in (8, 16):
        grenzen.append((-20, "Gesperrt – am nächsten Spieltag ohne Punkte."))
    elif spieler.status in (32, 64, 256):
        grenzen.append((-35, "Nicht im Kader – Einsatz auf absehbare Zeit unklar."))
    elif spieler.status == 4:
        grenzen.append((5, "Erst im Aufbautraining – Rückkehr abwarten."))
    elif spieler.status == 2:
        grenzen.append((20, "Angeschlagen – Aufstellung am Spieltag abwarten."))

    letzte = spieler.letzte_leistungen(3)
    if len(letzte) == 3 and all(l.minuten == 0 for l in letzte):
        grenzen.append((-30, "Drei Spiele ohne Einsatz – aktuell kein Faktor."))

    mindest = int(konfiguration.get("analyse.mindest_spiele", 3))
    if spieler.spiele < mindest and spieler.spiele >= 0:
        bewertung.warnungen.append(
            f"Erst {spieler.spiele} Spiele gewertet – die Bewertung steht auf "
            "dünner Datengrundlage.")
        # Bei wenig Daten wird die Note zur Mitte hin gedaempft.
        bewertung.gesamtpunkte *= 0.5

    if preis and spieler.marktwert > 0:
        aufschlag = (preis - spieler.marktwert) / spieler.marktwert
        if aufschlag > 0.25:
            grenzen.append((10, f"Angebotspreis liegt {aufschlag * 100:.0f} % "
                                "über dem Marktwert – zu teuer."))
        elif aufschlag > 0.1:
            bewertung.warnungen.append(
                f"Angebotspreis liegt {aufschlag * 100:.0f} % über dem Marktwert.")

    for obergrenze, text in grenzen:
        if bewertung.gesamtpunkte > obergrenze:
            bewertung.gesamtpunkte = obergrenze
            bewertung.uebersteuerung = text
        elif not bewertung.uebersteuerung:
            bewertung.uebersteuerung = text

    if spieler.verletzungsmeldung and spieler.verletzungsquelle != "Kickbase":
        bewertung.warnungen.append(
            f"Meldung aus {spieler.verletzungsquelle}: {spieler.verletzungsmeldung}")


def kader_bewerten(spieler: Sequence[Spieler], referenz: Referenzwerte,
                   konfiguration: Konfiguration,
                   ligalage: Ligalage | None = None,
                   mit_preis: bool = False) -> list[Bewertung]:
    """Bewertet eine Liste von Spielern und sortiert nach Note.

    ``mit_preis`` beruecksichtigt den Angebotspreis vom Transfermarkt statt
    des reinen Marktwerts.
    """
    ergebnis = []
    for s in spieler:
        preis = s.angebotspreis if (mit_preis and s.angebotspreis) else None
        ergebnis.append(bewerten(s, referenz, konfiguration, ligalage, preis))
    ergebnis.sort(key=lambda b: b.gesamtpunkte, reverse=True)
    return ergebnis
