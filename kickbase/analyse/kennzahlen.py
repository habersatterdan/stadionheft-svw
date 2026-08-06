"""Die einzelnen Bewertungsgroessen.

Jede Funktion hier liefert genau eine :class:`~kickbase.models.Kennzahl`:
eine Punktzahl zwischen -100 (klar dagegen) und +100 (klar dafuer), dazu
einen kurzen Satz, der sie erklaert, und einen Anzeigewert fuer die Tabelle.

Die Skala ist bei allen Kennzahlen dieselbe, damit die Gewichtung in der
Konfiguration verstaendlich bleibt: ein Gewicht von 1,4 auf "Form" bedeutet,
dass Form 40 Prozent staerker zaehlt als eine Kennzahl mit Gewicht 1,0.
"""

from __future__ import annotations

from statistics import median
from typing import Sequence

from ..models import (STATUS_AUSFALL, STATUS_FRAGLICH, Kennzahl, Spieler,
                      Spieltagsleistung)
from ..quellen.openligadb import Ligalage


def begrenzen(wert: float, unten: float = -100, oben: float = 100) -> float:
    return max(unten, min(oben, wert))


def _euro(betrag: float) -> str:
    """1234567 -> '1,23 Mio. €' (Komma als Dezimaltrennzeichen)"""
    if abs(betrag) >= 1_000_000:
        zahl = f"{betrag / 1_000_000:.2f}".replace(".", ",")
        return f"{zahl} Mio. €"
    return f"{betrag / 1000:.0f} Tsd. €"


# --------------------------------------------------------------------------
# 1. Verfuegbarkeit
# --------------------------------------------------------------------------

#: Bewertung je Kickbase-Status. Der Wert ist die Punktzahl der Kennzahl.
_STATUS_PUNKTE = {
    0: 30,       # Fit -- die Normallage, kein besonderer Verdienst
    2: -35,      # Angeschlagen
    4: -55,      # Aufbautraining
    1: -85,      # Verletzt
    8: -70,      # Rotsperre
    16: -60,     # Gelbsperre
    32: -70,     # Nicht im Kader
    64: -70,     # Abwesend
    128: -90,    # Reha
    256: -95,    # Vereinslos
}


def verfuegbarkeit(spieler: Spieler) -> Kennzahl:
    """Kann der Spieler am naechsten Spieltag ueberhaupt punkten?

    Die mit Abstand wichtigste Frage: ein verletzter Spieler bringt null
    Punkte, egal wie gut er ist.
    """
    punkte = _STATUS_PUNKTE.get(int(spieler.status), -30)
    text = spieler.status_name

    if spieler.status == 0:
        begruendung = "Fit und einsatzbereit."
    elif spieler.status in STATUS_AUSFALL:
        begruendung = f"{text} – faellt am naechsten Spieltag aus."
    elif spieler.status in STATUS_FRAGLICH:
        begruendung = f"{text} – Einsatz ist unsicher."
    else:
        begruendung = f"Status '{text}' ist dem Berater nicht bekannt."

    if spieler.verletzungsmeldung:
        kurz = spieler.verletzungsmeldung.strip()
        if len(kurz) > 180:
            kurz = kurz[:177] + "..."
        begruendung += f" Meldung ({spieler.verletzungsquelle or 'Quelle'}): {kurz}"

    return Kennzahl("verfuegbarkeit", "Verfügbarkeit", text, punkte, 1.0, begruendung)


# --------------------------------------------------------------------------
# 2. Form
# --------------------------------------------------------------------------


def _gewichteter_schnitt(leistungen: Sequence[Spieltagsleistung]) -> float:
    """Durchschnittspunkte, juengste Spiele zaehlen am staerksten."""
    if not leistungen:
        return 0.0
    summe = gewichtssumme = 0.0
    for stelle, leistung in enumerate(leistungen, start=1):
        summe += leistung.punkte * stelle
        gewichtssumme += stelle
    return summe / gewichtssumme if gewichtssumme else 0.0


def form(spieler: Spieler, spieltage: int = 5) -> Kennzahl:
    """Laeuft es gerade besser oder schlechter als ueblich?

    Verglichen wird der gewichtete Schnitt der letzten Spieltage mit dem
    Saisonschnitt desselben Spielers. Das ist der eigentliche Trendindikator:
    er sagt nicht, wer gut ist, sondern wer *gerade* gut ist.
    """
    letzte = spieler.letzte_leistungen(spieltage)
    if len(letzte) < 2:
        return Kennzahl("form", "Form", "zu wenig Daten", 0, 1.0,
                        "Noch keine zwei gewerteten Spieltage – Form nicht beurteilbar.")

    aktuell = _gewichteter_schnitt(letzte)
    referenz = float(spieler.punkte_schnitt or 0)
    if referenz <= 0:
        referenz = aktuell or 1

    unterschied = aktuell - referenz
    # Der Nenner sorgt dafuer, dass 10 Punkte Abweichung bei einem
    # 30-Punkte-Spieler mehr bedeuten als bei einem 90-Punkte-Spieler.
    bezug = max(12.0, referenz * 0.45)
    punkte = begrenzen(unterschied / bezug * 55)

    richtung = "über" if unterschied >= 0 else "unter"
    begruendung = (
        f"Letzte {len(letzte)} Spieltage: {aktuell:.0f} Punkte im Schnitt, "
        f"das sind {abs(unterschied):.0f} {richtung} dem Saisonschnitt "
        f"({referenz:.0f}).")

    nullen = sum(1 for l in letzte if l.punkte <= 0 and l.minuten > 0)
    if nullen >= 2:
        punkte = begrenzen(punkte - 15)
        begruendung += f" In {nullen} Spielen trotz Einsatz ohne Punkte."

    return Kennzahl("form", "Form", f"{aktuell:.0f} Pkt.", punkte, 1.0, begruendung)


# --------------------------------------------------------------------------
# 3. Einsatzzeit
# --------------------------------------------------------------------------


def einsatzzeit(spieler: Spieler, spieltage: int = 5) -> Kennzahl:
    """Ist der Spieler gesetzt oder Ergaenzungsspieler?

    Punkte gibt es in Kickbase nur auf dem Platz. Ein guter Spieler mit
    20 Minuten Einsatzzeit ist als Kauf schlechter als ein mittelmaessiger
    Stammspieler.
    """
    letzte = spieler.letzte_leistungen(spieltage)
    if not letzte:
        return Kennzahl("einsatzzeit", "Einsatzzeit", "keine Daten", 0, 1.0,
                        "Keine gewerteten Spieltage vorhanden.")

    schnitt = sum(l.minuten for l in letzte) / len(letzte)
    startelf = sum(1 for l in letzte if l.startelf)
    ohne = sum(1 for l in letzte if l.minuten == 0)

    if schnitt >= 80:
        punkte = 45.0
        lage = "gesetzter Stammspieler"
    elif schnitt >= 60:
        punkte = 20.0
        lage = "meist in der Startelf"
    elif schnitt >= 35:
        punkte = -15.0
        lage = "Rotationsspieler"
    elif schnitt >= 15:
        punkte = -45.0
        lage = "meist Einwechselspieler"
    else:
        punkte = -70.0
        lage = "kaum Einsatzzeit"

    begruendung = (
        f"{schnitt:.0f} Minuten im Schnitt der letzten {len(letzte)} Spieltage "
        f"({startelf}× von Beginn, {ohne}× ohne Einsatz) – {lage}.")

    # Ein frischer Bruch in der Einsatzzeit ist wichtiger als der Schnitt:
    # drei Spiele ohne Minute bedeuten meist Aussortierung oder Verletzung.
    if len(letzte) >= 3 and all(l.minuten == 0 for l in letzte[-3:]):
        punkte = -85.0
        begruendung += " Zuletzt drei Spiele am Stück ohne Einsatz."

    return Kennzahl("einsatzzeit", "Einsatzzeit", f"{schnitt:.0f} Min.",
                    punkte, 1.0, begruendung)


# --------------------------------------------------------------------------
# 4. Marktwerttrend
# --------------------------------------------------------------------------


def marktwerttrend(spieler: Spieler) -> Kennzahl:
    """Wohin laeuft der Marktwert?

    Kickbase-Marktwerte bewegen sich traege und mit Nachlauf. Ein steigender
    Wert ist deshalb weniger eine Vorhersage als eine Bestaetigung: die
    Mitspieler haben den Spieler entdeckt. Fuer den Kauf zaehlt vor allem der
    Sieben-Tage-Wert, weil er der frischeste ist.
    """
    heute = spieler.marktwert
    vor_7 = spieler.marktwert_vor(7)
    vor_30 = spieler.marktwert_vor(30)

    if not heute or (not vor_7 and not vor_30):
        anzeige = "keine Historie"
        # Der von Kickbase gelieferte Pfeil ist besser als nichts.
        if spieler.marktwert_trend == 1:
            return Kennzahl("marktwerttrend", "Marktwerttrend", "steigend", 20, 1.0,
                            "Kein Verlauf gespeichert; Kickbase meldet steigenden Marktwert.")
        if spieler.marktwert_trend == 2:
            return Kennzahl("marktwerttrend", "Marktwerttrend", "fallend", -20, 1.0,
                            "Kein Verlauf gespeichert; Kickbase meldet fallenden Marktwert.")
        return Kennzahl("marktwerttrend", "Marktwerttrend", anzeige, 0, 1.0,
                        "Noch kein Marktwertverlauf gespeichert. Nach einigen "
                        "Tagen mit taeglichem Abruf steht diese Kennzahl zur Verfügung.")

    prozent_7 = ((heute - vor_7) / vor_7 * 100) if vor_7 else 0.0
    prozent_30 = ((heute - vor_30) / vor_30 * 100) if vor_30 else 0.0

    punkte = begrenzen(prozent_7 * 9 + prozent_30 * 2.5)

    teile = []
    if vor_7:
        teile.append(f"7 Tage: {prozent_7:+.1f} %")
    if vor_30:
        teile.append(f"30 Tage: {prozent_30:+.1f} %")
    begruendung = ("Marktwert " + ", ".join(teile) +
                   f" (aktuell {_euro(heute)}).")

    anzeige = f"{prozent_7:+.1f} %" if vor_7 else f"{prozent_30:+.1f} %"
    return Kennzahl("marktwerttrend", "Marktwerttrend", anzeige, punkte, 1.0,
                    begruendung)


# --------------------------------------------------------------------------
# 5. Preis-Leistung
# --------------------------------------------------------------------------


def preis_leistung(spieler: Spieler, vergleich: float,
                   preis: int | None = None) -> Kennzahl:
    """Wie viele Punkte bekommt man je Million?

    ``vergleich`` ist der Mittelwert derselben Position -- ein Torwart wird
    also nicht an einem Stuermer gemessen. ``preis`` weicht vom Marktwert ab,
    wenn der Spieler auf dem Transfermarkt teurer angeboten wird.
    """
    kosten = int(preis or spieler.marktwert or 0)
    if kosten <= 0 or spieler.punkte_schnitt <= 0:
        return Kennzahl("preis_leistung", "Preis-Leistung", "unbekannt", 0, 1.0,
                        "Ohne Marktwert oder Punkte nicht berechenbar.")

    eigen = spieler.punkte_schnitt / (kosten / 1_000_000)
    if vergleich <= 0:
        return Kennzahl("preis_leistung", "Preis-Leistung", f"{eigen:.1f} Pkt./Mio.",
                        0, 1.0, "Kein Vergleichswert für diese Position vorhanden.")

    verhaeltnis = eigen / vergleich
    punkte = begrenzen((verhaeltnis - 1) * 85)

    if verhaeltnis >= 1.15:
        urteil = "deutlich günstiger als üblich"
    elif verhaeltnis >= 1.02:
        urteil = "etwas günstiger als üblich"
    elif verhaeltnis >= 0.9:
        urteil = "marktüblich"
    else:
        urteil = "teuer für die Leistung"

    zusatz = ""
    if preis and preis != spieler.marktwert:
        aufschlag = (preis - spieler.marktwert) / spieler.marktwert * 100
        zusatz = (f" Angebotspreis liegt {aufschlag:+.0f} % über dem Marktwert."
                  if aufschlag > 0 else
                  f" Angebotspreis liegt {abs(aufschlag):.0f} % unter dem Marktwert.")

    begruendung = (
        f"{eigen:.1f} Punkte je Million bei {_euro(kosten)} – "
        f"{urteil} (Schnitt {spieler.positions_name}: {vergleich:.1f})." + zusatz)

    return Kennzahl("preis_leistung", "Preis-Leistung", f"{eigen:.1f} Pkt./Mio.",
                    punkte, 1.0, begruendung)


# --------------------------------------------------------------------------
# 6. Gegnerstaerke
# --------------------------------------------------------------------------


def gegnerstaerke(spieler: Spieler, lage: Ligalage | None,
                  anzahl: int = 2) -> Kennzahl:
    """Wie schwer sind die naechsten Gegner?

    Kurzfristige Kaeufe lohnen sich vor leichten Spielen. Der Tabellenplatz
    ist dafuer ein grober, aber brauchbarer Massstab; Heimrecht wird mit
    einem kleinen Bonus beruecksichtigt.
    """
    if lage is None or not spieler.team_name:
        return Kennzahl("gegnerstaerke", "Nächste Gegner", "unbekannt", 0, 1.0,
                        "Kein Spielplan verfügbar (OpenLigaDB ausgeschaltet "
                        "oder nicht erreichbar).")

    gegner = lage.naechste_gegner(spieler.team_name, anzahl)
    if not gegner:
        return Kennzahl("gegnerstaerke", "Nächste Gegner", "unbekannt", 0, 1.0,
                        f"Für {spieler.team_name} wurden keine kommenden Spiele "
                        "im Spielplan gefunden.")

    mannschaften = lage.mannschaften
    mitte = (mannschaften + 1) / 2
    einzeln: list[float] = []
    beschreibung: list[str] = []

    for name, heimspiel in gegner:
        platz = lage.platz(name)
        if not platz:
            beschreibung.append(f"{name} ({'H' if heimspiel else 'A'})")
            continue
        # Platz 1 = staerkster Gegner = negativ; letzter Platz = positiv.
        wert = (platz - mitte) / (mitte - 1) * 60
        wert += 12 if heimspiel else -12
        einzeln.append(wert)
        beschreibung.append(
            f"{name} (Platz {platz}, {'Heimspiel' if heimspiel else 'Auswärts'})")

    if not einzeln:
        return Kennzahl("gegnerstaerke", "Nächste Gegner",
                        " / ".join(beschreibung), 0, 1.0,
                        "Gegner bekannt, aber ohne Tabellenplatz – nicht bewertbar.")

    punkte = begrenzen(sum(einzeln) / len(einzeln))
    if punkte >= 20:
        urteil = "günstiges Programm"
    elif punkte <= -20:
        urteil = "schweres Programm"
    else:
        urteil = "ausgeglichenes Programm"

    return Kennzahl("gegnerstaerke", "Nächste Gegner",
                    " / ".join(beschreibung), punkte, 1.0,
                    f"Nächste Spiele gegen {' und '.join(beschreibung)} – {urteil}.")


# --------------------------------------------------------------------------
# 7. Bewertungsniveau
# --------------------------------------------------------------------------


def bewertungsniveau(spieler: Spieler) -> Kennzahl:
    """Wo steht der Marktwert innerhalb seiner eigenen Spanne?

    Nahe am Hoechststand ist ein Kauf teuer und ein Verkauf attraktiv --
    nahe am Tiefststand umgekehrt. Diese Kennzahl ist bewusst gegenlaeufig
    zum Marktwerttrend: zusammen ergeben sie "steigt, ist aber noch nicht
    ausgereizt" statt blindem Hinterherlaufen.
    """
    if len(spieler.verlauf) < 10:
        return Kennzahl("bewertungsniveau", "Bewertungsniveau", "keine Historie",
                        0, 1.0, "Zu wenige gespeicherte Marktwerte für einen Vergleich.")

    werte = [p.wert for p in spieler.verlauf]
    tiefst, hoechst = min(werte), max(werte)
    if hoechst <= tiefst:
        return Kennzahl("bewertungsniveau", "Bewertungsniveau", "unverändert",
                        0, 1.0, "Der Marktwert hat sich im gespeicherten Zeitraum "
                                "nicht bewegt.")

    stelle = (spieler.marktwert - tiefst) / (hoechst - tiefst)
    punkte = begrenzen((0.5 - stelle) * 90)

    if stelle >= 0.9:
        urteil = "nahe am Höchststand – teuer im Einkauf, gut zum Verkaufen"
    elif stelle <= 0.15:
        urteil = "nahe am Tiefststand – günstig, aber prüfen, warum"
    else:
        urteil = "im mittleren Bereich seiner Spanne"

    return Kennzahl("bewertungsniveau", "Bewertungsniveau", f"{stelle * 100:.0f} %",
                    punkte, 1.0,
                    f"Marktwert liegt bei {stelle * 100:.0f} % der Spanne zwischen "
                    f"{_euro(tiefst)} und {_euro(hoechst)} – {urteil}.")


# --------------------------------------------------------------------------
# Vergleichswerte
# --------------------------------------------------------------------------


def punkte_je_million(spieler: Spieler) -> float:
    if spieler.marktwert <= 0:
        return 0.0
    return spieler.punkte_schnitt / (spieler.marktwert / 1_000_000)


def positionsvergleich(spieler: Sequence[Spieler],
                       mindest_spiele: int = 3) -> dict[int, float]:
    """Mittleres Punkte-je-Million-Verhaeltnis je Position.

    Der Median statt des Mittelwerts, damit einzelne Ausreisser -- ein
    Torwart mit drei Elfmetersaven -- den Massstab nicht verzerren.
    """
    nach_position: dict[int, list[float]] = {}
    for s in spieler:
        if s.marktwert <= 0 or s.spiele < mindest_spiele or s.punkte_schnitt <= 0:
            continue
        nach_position.setdefault(s.position, []).append(punkte_je_million(s))
    return {pos: median(werte) for pos, werte in nach_position.items() if werte}
