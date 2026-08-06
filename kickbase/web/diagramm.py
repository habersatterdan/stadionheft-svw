"""Kleine Diagramme ohne JavaScript-Bibliothek.

Der Marktwertverlauf ist eine einzelne Reihe ueber die Zeit -- dafuer genuegt
ein Liniendiagramm, das hier direkt als SVG berechnet wird. Vorteile
gegenueber einer eingebundenen Diagrammbibliothek:

* Die Seite laedt nichts aus dem Netz nach. Der Berater funktioniert auch in
  einem Heimnetz ohne Internetzugang.
* Es gibt nichts, was in zwei Jahren veraltet ist.

Bewusste Gestaltungsentscheidungen: eine Reihe braucht keine Legende (die
Ueberschrift benennt sie), das Gitter bleibt zurueckhaltend, beschriftet wird
nur der letzte Wert sowie Hoechst- und Tiefstwert.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Marktwertpunkt


def euro_kurz(betrag: float) -> str:
    """1234567 -> '1,23 Mio.'"""
    if abs(betrag) >= 1_000_000:
        return f"{betrag / 1_000_000:.2f}".replace(".", ",") + " Mio."
    return f"{betrag / 1000:.0f} Tsd."


@dataclass
class Punkt:
    x: float
    y: float
    wert: int
    beschriftung: str


@dataclass
class Liniendiagramm:
    """Fertig gerechnete Geometrie -- die Vorlage zeichnet nur noch."""

    breite: int = 720
    hoehe: int = 240
    linie: str = ""
    flaeche: str = ""
    punkte: list[Punkt] = field(default_factory=list)
    gitter: list[tuple[float, str]] = field(default_factory=list)
    x_beschriftungen: list[tuple[float, str]] = field(default_factory=list)
    hoechst: Punkt | None = None
    tiefst: Punkt | None = None
    letzter: Punkt | None = None
    leer: bool = True

    @property
    def punkte_json(self) -> list[dict]:
        """Fuer das Fadenkreuz in der Vorlage -- als einfache Liste von Werten."""
        return [{"x": p.x, "y": p.y, "beschriftung": p.beschriftung}
                for p in self.punkte]


#: Innenabstaende: links Platz fuer die Werteachse, unten fuer die Datumsachse.
_LINKS, _RECHTS, _OBEN, _UNTEN = 8, 74, 14, 26


def marktwertdiagramm(verlauf: list[Marktwertpunkt], breite: int = 720,
                      hoehe: int = 240) -> Liniendiagramm:
    """Rechnet einen Marktwertverlauf in SVG-Koordinaten um."""
    diagramm = Liniendiagramm(breite=breite, hoehe=hoehe)
    reihe = sorted(verlauf, key=lambda p: p.tag)
    if len(reihe) < 2:
        return diagramm

    diagramm.leer = False
    werte = [p.wert for p in reihe]
    tiefst_wert, hoechst_wert = min(werte), max(werte)
    # Etwas Luft nach oben und unten, damit die Linie nicht am Rand klebt.
    spanne = max(1, hoechst_wert - tiefst_wert)
    unten_wert = tiefst_wert - spanne * 0.12
    oben_wert = hoechst_wert + spanne * 0.12

    zeichen_breite = breite - _LINKS - _RECHTS
    zeichen_hoehe = hoehe - _OBEN - _UNTEN

    def x_von(stelle: int) -> float:
        return _LINKS + zeichen_breite * stelle / (len(reihe) - 1)

    def y_von(wert: float) -> float:
        anteil = (wert - unten_wert) / (oben_wert - unten_wert)
        return _OBEN + zeichen_hoehe * (1 - anteil)

    for stelle, punkt in enumerate(reihe):
        diagramm.punkte.append(Punkt(
            x=round(x_von(stelle), 2), y=round(y_von(punkt.wert), 2),
            wert=punkt.wert,
            beschriftung=f"{punkt.tag.strftime('%d.%m.%Y')}: "
                         f"{euro_kurz(punkt.wert)} €"))

    diagramm.linie = " ".join(f"{p.x},{p.y}" for p in diagramm.punkte)
    diagramm.flaeche = (f"{diagramm.punkte[0].x},{hoehe - _UNTEN} "
                        + diagramm.linie
                        + f" {diagramm.punkte[-1].x},{hoehe - _UNTEN}")

    # Vier waagerechte Hilfslinien mit Wertbeschriftung.
    for schritt in range(4):
        wert = unten_wert + (oben_wert - unten_wert) * schritt / 3
        diagramm.gitter.append((round(y_von(wert), 2), euro_kurz(wert)))

    # Hoechstens fuenf Datumsangaben, sonst ueberlappen die Beschriftungen.
    schritte = max(1, (len(reihe) - 1) // 4)
    for stelle in range(0, len(reihe), schritte):
        diagramm.x_beschriftungen.append(
            (round(x_von(stelle), 2), reihe[stelle].tag.strftime("%d.%m.")))

    diagramm.hoechst = max(diagramm.punkte, key=lambda p: p.wert)
    diagramm.tiefst = min(diagramm.punkte, key=lambda p: p.wert)
    diagramm.letzter = diagramm.punkte[-1]
    return diagramm


def sparklinie(verlauf: list[Marktwertpunkt], breite: int = 90,
               hoehe: int = 26) -> str:
    """Winziger Verlauf fuer die Tabellenzeile -- nur Form, keine Achsen."""
    reihe = sorted(verlauf, key=lambda p: p.tag)[-45:]
    if len(reihe) < 2:
        return ""
    werte = [p.wert for p in reihe]
    tiefst, hoechst = min(werte), max(werte)
    spanne = max(1, hoechst - tiefst)
    punkte = []
    for stelle, punkt in enumerate(reihe):
        x = breite * stelle / (len(reihe) - 1)
        y = hoehe - 2 - (hoehe - 4) * (punkt.wert - tiefst) / spanne
        punkte.append(f"{x:.1f},{y:.1f}")
    return " ".join(punkte)
