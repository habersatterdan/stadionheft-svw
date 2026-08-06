"""Beispieldaten zum Ausprobieren ohne Kickbase-Konto.

Zweck: Wer den Berater zum ersten Mal startet, soll sofort sehen, wie eine
Empfehlung aussieht -- ohne vorher Zugangsdaten einzutragen. Ausserdem laufen
die Tests damit, ohne das Netz zu belasten.

Die Daten sind erfunden, aber plausibel aufgebaut: ein Kader mit einem
Verletzten, einem Formstarken, einem Bankdruecker und einem, dessen Marktwert
den Punkten davongelaufen ist. Der Zufallsstartwert ist fest, damit dieselbe
Ausgabe reproduzierbar bleibt.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from ..models import Marktwertpunkt, Spieler, Spieltagsleistung
from .openligadb import Begegnung, Ligalage, namen_schluessel

VEREINE = [
    ("2", "FC Bayern München"), ("3", "Borussia Dortmund"),
    ("4", "Eintracht Frankfurt"), ("5", "SC Freiburg"),
    ("7", "Bayer 04 Leverkusen"), ("9", "VfB Stuttgart"),
    ("10", "Werder Bremen"), ("11", "VfL Wolfsburg"),
    ("13", "FC Augsburg"), ("14", "1. FSV Mainz 05"),
    ("15", "Borussia Mönchengladbach"), ("18", "1. FC Union Berlin"),
]

NACHNAMEN = [
    "Brandtner", "Sonnleitner", "Wiesinger", "Kalkbrenner", "Hedegaard",
    "Okonkwo", "Steinmayr", "Vukovic", "Lindqvist", "Rehbein",
    "Alvarado", "Kittelmann", "Thanheiser", "Bergstroem", "Novak",
    "Feldkamp", "Osterhagen", "Duracak", "Marquardt", "Petrovic",
    "Ehrlichmann", "Sarpong", "Kranzler", "Mihajlovic", "Wolfsteiner",
    "Bramlage", "Tanriverdi", "Ostrowski", "Feuerbach", "Salzmann",
    "Kirchhoff", "Adeyemi-Bauer", "Hoevelmann", "Zdravkovic", "Lorbeer",
    "Wendelstein", "Kaltenbrunner", "Rasmussen", "Girardet", "Schuhbeck",
]

VORNAMEN = [
    "Jonas", "Luca", "Emre", "Nikola", "Mats", "Paul", "Anton", "Elias",
    "Rasmus", "Tobias", "Kwame", "Levin", "Fabio", "Miro", "Janne", "Ole",
]


#: Auch in der Sommerpause zeigen die Beispieldaten eine angespielte Saison --
#: sonst haette der Berater im Demomodus nichts zu rechnen.
MINDEST_SPIELTAGE = 12


def _spieltage_bis_heute() -> int:
    """Grobe Schaetzung, wie weit die Saison ist -- nur fuer die Optik."""
    heute = date.today()
    beginn = date(heute.year if heute.month >= 7 else heute.year - 1, 8, 15)
    wochen = max(0, (heute - beginn).days // 7)
    return max(MINDEST_SPIELTAGE, min(34, wochen))


def demo_spieler(anzahl: int = 120, startwert: int = 20260805) -> list[Spieler]:
    """Erzeugt einen kompletten Beispiel-Spielerpool."""
    zufall = random.Random(startwert)
    heute = date.today()
    spieltage = _spieltage_bis_heute()
    spieler: list[Spieler] = []

    for nummer in range(anzahl):
        team_id, team_name = VEREINE[nummer % len(VEREINE)]
        position = [1, 2, 2, 2, 3, 3, 3, 4, 4, 2][nummer % 10]

        # Grundniveau des Spielers: bestimmt Punkte *und* Marktwert.
        klasse = zufall.triangular(0.2, 1.0, 0.5)
        marktwert = int(400_000 + klasse ** 2 * 24_000_000)
        schnitt = int(20 + klasse * 90)

        # Ein paar Spieler bekommen absichtlich ein auffaelliges Profil,
        # damit die Empfehlungen im Demomodus etwas zu zeigen haben.
        rolle = "normal"
        if nummer % 17 == 0:
            rolle = "verletzt"
        elif nummer % 13 == 0:
            rolle = "formstark"
        elif nummer % 11 == 0:
            rolle = "bank"
        elif nummer % 19 == 0:
            rolle = "ueberbewertet"

        status = 0
        if rolle == "verletzt":
            status = zufall.choice([1, 1, 2, 4])

        # Vor- und Nachname so kombiniert, dass jeder Name genau einmal
        # vorkommt -- doppelte Namen wuerden beim Ausprobieren nur verwirren.
        s = Spieler(
            id=str(1000 + nummer),
            vorname=VORNAMEN[(nummer * 7 + nummer // len(NACHNAMEN)) % len(VORNAMEN)],
            nachname=NACHNAMEN[nummer % len(NACHNAMEN)],
            team_id=team_id, team_name=team_name,
            position=position, status=status,
            marktwert=marktwert, punkte_schnitt=schnitt,
            spiele=spieltage,
            tore=int(klasse * 7) if position == 4 else int(klasse * 2),
            vorlagen=int(klasse * 4),
        )
        if rolle == "verletzt":
            s.verletzungsmeldung = zufall.choice([
                "Muskelfaserriss im Oberschenkel, fällt voraussichtlich drei Wochen aus.",
                "Angeschlagen nach Prellung, Einsatz am Wochenende fraglich.",
                "Im Aufbautraining nach überstandener Kapselverletzung.",
            ])
            s.verletzungsquelle = "Demodaten"

        _leistungen_erzeugen(s, zufall, spieltage, rolle, schnitt)
        _verlauf_erzeugen(s, zufall, heute, rolle)
        s.punkte_gesamt = sum(l.punkte for l in s.leistungen)
        s.minuten_gesamt = sum(l.minuten for l in s.leistungen)
        spieler.append(s)

    return spieler


def _leistungen_erzeugen(s: Spieler, zufall: random.Random, spieltage: int,
                         rolle: str, schnitt: int) -> None:
    heute = date.today()
    for spieltag in range(1, spieltage + 1):
        rest = spieltage - spieltag
        if rolle == "bank":
            minuten = zufall.choice([0, 0, 0, 12, 25, 90])
        elif rolle == "verletzt" and rest < 3:
            minuten = 0
        else:
            minuten = zufall.choice([90, 90, 90, 88, 75, 62, 45, 0])

        if minuten == 0:
            punkte = 0
        else:
            grundwert = schnitt * minuten / 90
            # Formstarke Spieler drehen in den letzten Wochen auf,
            # Ueberbewertete lassen nach.
            faktor = 1.0
            if rolle == "formstark" and rest < 5:
                faktor = 1.8
            elif rolle == "ueberbewertet" and rest < 5:
                faktor = 0.45
            punkte = int(max(0, zufall.gauss(grundwert * faktor, 25)))

        gegner_id, gegner_name = zufall.choice(VEREINE)
        s.leistungen.append(Spieltagsleistung(
            spieltag=spieltag, punkte=punkte, minuten=minuten,
            datum=heute - timedelta(days=7 * rest + 1),
            eigenes_team_id=s.team_id, gegner_team_id=gegner_id,
            heimspiel=spieltag % 2 == 0, gespielt=True))


def _verlauf_erzeugen(s: Spieler, zufall: random.Random, heute: date,
                      rolle: str) -> None:
    """Baut den Verlauf rueckwaerts vom heutigen Marktwert aus auf.

    Rueckwaerts, damit der letzte Punkt exakt dem Marktwert entspricht --
    sonst gaebe es am rechten Rand der Kurve einen kuenstlichen Sprung.
    """
    if rolle == "formstark":
        tagesaenderung = 0.0035        # steigt seit Wochen
    elif rolle in ("verletzt", "ueberbewertet"):
        tagesaenderung = -0.0030       # faellt seit Wochen
    else:
        tagesaenderung = 0.0002

    wert = float(s.marktwert)
    punkte: list[Marktwertpunkt] = [Marktwertpunkt(tag=heute, wert=s.marktwert)]
    for zurueck in range(1, 91):
        wert = wert / (1 + tagesaenderung) + zufall.gauss(0, wert * 0.004)
        wert = max(100_000.0, wert)
        punkte.append(Marktwertpunkt(tag=heute - timedelta(days=zurueck),
                                     wert=int(wert)))
    punkte.reverse()
    s.verlauf = punkte


def demo_ligalage() -> Ligalage:
    """Tabelle und Restspielplan passend zu den Beispielvereinen."""
    lage = Ligalage(stand=datetime.now().isoformat(timespec="minutes"))
    for platz, (_, name) in enumerate(VEREINE, start=1):
        schluessel = namen_schluessel(name)
        lage.tabelle[schluessel] = platz
        lage.namen[schluessel] = name

    spieltag = _spieltage_bis_heute()
    lage.aktueller_spieltag = spieltag
    heute = datetime.now()
    for runde in range(2):
        gedreht = VEREINE[runde:] + VEREINE[:runde]
        for i in range(0, len(gedreht) - 1, 2):
            lage.begegnungen.append(Begegnung(
                spieltag=spieltag + runde + 1,
                anstoss=heute + timedelta(days=3 + 7 * runde),
                heim=gedreht[i][1], gast=gedreht[i + 1][1], beendet=False))
    return lage


def demo_kader(spieler: list[Spieler], groesse: int = 12) -> list[Spieler]:
    """Waehlt einen Beispielkader aus dem Pool und markiert ihn als eigenen."""
    kader = spieler[:groesse]
    for s in kader:
        s.im_eigenen_team = True
    return kader


def demo_transfermarkt(spieler: list[Spieler], groesse: int = 10) -> list[Spieler]:
    """Ein paar Spieler stehen zum Verkauf -- leicht ueber Marktwert."""
    zufall = random.Random(4711)
    markt = [s for s in spieler if not s.im_eigenen_team][:groesse]
    for s in markt:
        s.auf_transfermarkt = True
        s.angebotspreis = int(s.marktwert * zufall.uniform(0.95, 1.25))
        s.besitzer = zufall.choice(["Kevin", "Sandra", "Tobi", "Computer"])
    return markt
