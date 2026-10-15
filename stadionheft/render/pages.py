"""Erzeugt die variablen Heftseiten als PDF.

Weg: Jinja2 -> HTML -> WeasyPrint -> PDF.

Warum HTML/CSS und nicht InDesign fernsteuern?

* Der Ablauf laeuft ohne Adobe-Lizenz und ohne Windows-Rechner -- also auch
  in einem Container auf der Synology NAS.
* Layoutaenderungen sind CSS-Aenderungen und damit nachvollziehbar
  versionierbar.
* WeasyPrint erzeugt dieselbe TrimBox (148 x 210 mm) mit 3 mm Anschnitt und
  Schnittmarken wie die bisherige InDesign-Ausgabe. Die erzeugten Seiten
  passen also massgenau zwischen die bestehenden Werbeseiten.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape
from markupsafe import Markup

from ..config import Konfiguration
from ..errors import RenderFehler
from ..logging_setup import logger
from ..models import WOCHENTAGE, Ausgabe, MannschaftsDaten, Spiel, SpielerZeile

TEMPLATE_ORDNER = Path(__file__).resolve().parent.parent / "templates"
STATIC_ORDNER = Path(__file__).resolve().parent.parent / "static"

#: Mannschaftsseite -> (Vorlage, Ueberschrift im roten Balken)
SEITEN_VORLAGEN: dict[str, tuple[str, str]] = {
    "trenner":          ("trenner.html.j2", ""),
    "vergleich":        ("vergleich.html.j2", "Das nächste Spiel"),
    "tabelle":          ("tabelle.html.j2", "Tabelle"),
    "torjaeger":        ("torjaeger.html.j2", "Torschützenliste"),
    "spielerstatistik": ("spielerstatistik.html.j2", "Spielerstatistik"),
    "gegner":           ("gegner.html.j2", "Der Gegner"),
    # Nur noetig, wenn der Gegner in einer anderen Liga spielt (Pokal).
    "tabelle_gegner":   ("tabelle.html.j2", "Tabelle des Gegners"),
    "torjaeger_gegner": ("torjaeger.html.j2", "Torschützen des Gegners"),
}

#: Reihenfolge der Seiten in der Datei einer Mannschaft. Bewusst im Code und
#: nicht in der Konfiguration: Die Datei soll bei allen Mannschaften gleich
#: aufgebaut sein, damit die Person, die das Heft zusammenbaut, sich darauf
#: verlassen kann.
STANDARD_SEITEN: tuple[str, ...] = (
    "trenner", "vergleich", "tabelle", "torjaeger",
    "spielerstatistik", "gegner",
)

#: So viele Zeilen passen auf eine A5-Seite. Was darueber hinausgeht, wuerde
#: auf eine zweite Seite umbrechen oder abgeschnitten.
HOECHSTENS_ZEILEN = 22


def spieler_rangfolge(spieler: list[SpielerZeile],
                      hoechstens: int = HOECHSTENS_ZEILEN) -> list[SpielerZeile]:
    """Die Spieler mit den meisten Einsaetzen zuerst, bei Gleichstand die mit
    mehr Minuten -- und nur so viele, wie auf die Seite passen.

    Die Plaetze werden neu durchgezaehlt. Die Daten selbst bleiben unberuehrt
    (Snapshot), es wird nur eine sortierte Kopie gedruckt.
    """
    sortiert = sorted(spieler, key=lambda z: (-z.spiele, -z.minuten))
    return [replace(z, platz=nr)
            for nr, z in enumerate(sortiert[:hoechstens], 1)]


def _css_sauber(wert: str) -> str:
    """Entfernt alles, was aus einem CSS-Wert bzw. dem <style>-Block ausbrechen
    koennte. Die Werte kommen aus config.yaml -- also nicht von beliebigen
    Benutzern -- aber ein Tippfehler soll die Seite nicht zerlegen."""
    return re.sub(r"[<>{};:\\@()]", "", str(wert or "")).strip()


@dataclass
class LayoutWerte:
    breite_mm: float = 148
    hoehe_mm: float = 210
    anschnitt_mm: float = 3
    druckmarken: bool = True
    primaerfarbe: str = "#E52421"
    textfarbe: str = "#1A1A1A"
    schriftfamilie: str = "Segoe UI, Open Sans, DejaVu Sans, sans-serif"
    #: Kopf- und Fussbalken auf den Inhaltsseiten (siehe _inhaltsseite.html.j2)
    balken: bool = True

    @property
    def schrift_css(self) -> Markup:
        """Die Schriftliste als gueltiger CSS-Wert.

        Zwei Stolpersteine, die hier abgeraeumt werden:

        1. Namen wie ``Source Sans 3`` sind ohne Anfuehrungszeichen ungueltig
           (ein CSS-Bezeichner darf nicht mit einer Ziffer beginnen) -- und
           eine einzige ungueltige Angabe macht die komplette ``font-family``
           unwirksam, das Ergebnis waere eine Serifenschrift.
        2. Der Wert landet in einem ``<style>``-Block. Wuerde Jinja ihn
           HTML-maskieren, wuerden aus den Anfuehrungszeichen ``&#34;`` -- und
           die Regel waere wieder kaputt. Deshalb ``Markup``; die Bestandteile
           werden vorher von allem befreit, was aus dem Wert ausbrechen kann.
        """
        generisch = {"serif", "sans-serif", "monospace", "cursive", "fantasy",
                     "system-ui", "ui-sans-serif", "ui-serif", "ui-monospace"}
        teile = []
        for name in self.schriftfamilie.split(","):
            name = _css_sauber(name).strip("'\"")
            if not name:
                continue
            teile.append(name if name.lower() in generisch else f'"{name}"')
        return Markup(", ".join(teile) or "sans-serif")

    @property
    def primaerfarbe_css(self) -> Markup:
        return Markup(_css_sauber(self.primaerfarbe) or "#E52421")

    @property
    def textfarbe_css(self) -> Markup:
        return Markup(_css_sauber(self.textfarbe) or "#1A1A1A")

    @classmethod
    def aus_konfiguration(cls, k: Konfiguration) -> "LayoutWerte":
        return cls(
            breite_mm=float(k.get("layout.seitenbreite_mm", 148)),
            hoehe_mm=float(k.get("layout.seitenhoehe_mm", 210)),
            anschnitt_mm=float(k.get("layout.anschnitt_mm", 3)),
            druckmarken=bool(k.get("layout.druckmarken", True)),
            primaerfarbe=str(k.get("layout.primaerfarbe", "#E52421")),
            textfarbe=str(k.get("layout.textfarbe", "#1A1A1A")),
            schriftfamilie=str(k.get("layout.schriftfamilie",
                                     "Segoe UI, Open Sans, DejaVu Sans, sans-serif")),
            balken=bool(k.get("layout.balken", True)),
        )


def text_zu_absaetzen(text: str) -> list[dict]:
    """Zerlegt einfachen Text/Markdown in Absaetze und Ueberschriften.

    Bewusst minimal: Zeilen mit ``#`` am Anfang oder eine erste kurze Zeile
    ohne Satzzeichen gelten als Ueberschrift. Damit kann die Redaktion das
    Vorwort in jedem beliebigen Editor schreiben.
    """
    absaetze: list[dict] = []
    for block in re.split(r"\n\s*\n", (text or "").strip()):
        block = block.strip()
        if not block:
            continue
        if block.startswith("#"):
            absaetze.append({"ueberschrift": True,
                             "text": block.lstrip("#").strip()})
        elif len(absaetze) == 0 and len(block) < 90 and "\n" not in block:
            absaetze.append({"ueberschrift": True, "text": block})
        else:
            absaetze.append({"ueberschrift": False,
                             "text": " ".join(block.split())})
    return absaetze


class SeitenRenderer:
    """Erzeugt einzelne PDF-Seiten in den Arbeitsordner."""

    def __init__(self, konfiguration: Konfiguration, arbeitsordner: Path) -> None:
        self.konfiguration = konfiguration
        self.arbeitsordner = Path(arbeitsordner)
        self.arbeitsordner.mkdir(parents=True, exist_ok=True)
        self.layout = LayoutWerte.aus_konfiguration(konfiguration)

        self.umgebung = Environment(
            loader=FileSystemLoader(str(TEMPLATE_ORDNER)),
            autoescape=select_autoescape(["html", "j2"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

        logo = konfiguration.logo_pfad
        self.heft = {
            "hefttitel": konfiguration.hefttitel,
            "saison": konfiguration.saison,
            "verein": konfiguration.vereinsname,
            "logo_url": logo.as_uri() if logo.exists() else "",
            "titel_zeile1": konfiguration.hefttitel.split(" am ")[0],
            "titel_zeile2": ("am " + konfiguration.hefttitel.split(" am ", 1)[1])
                            if " am " in konfiguration.hefttitel else "",
        }
        if not logo.exists():
            logger().warning("Vereinswappen nicht gefunden: %s", logo)

        self.css_pfad = (STATIC_ORDNER / "css" / "heft.css").as_uri()

    # -- Kern ---------------------------------------------------------------

    def _html(self, vorlage: str, **kontext) -> str:
        try:
            template = self.umgebung.get_template(vorlage)
        except TemplateNotFound as fehler:
            raise RenderFehler(
                f"Vorlage {vorlage} nicht gefunden.",
                benutzer_text=f"Die Seitenvorlage '{vorlage}' fehlt im Programm.",
                hinweis="Bitte einen Administrator informieren.",
            ) from fehler
        return template.render(
            heft=self.heft,
            layout=self.layout,
            css_pfad=self.css_pfad,
            **kontext,
        )

    def _pdf(self, html: str, name: str) -> Path:
        from weasyprint import HTML

        ziel = self.arbeitsordner / f"{name}.pdf"
        try:
            HTML(string=html, base_url=str(TEMPLATE_ORDNER)).write_pdf(str(ziel))
        except Exception as fehler:  # noqa: BLE001 - WeasyPrint wirft vieles
            raise RenderFehler(
                f"{name}: {fehler}",
                benutzer_text=f"Die Seite '{name}' konnte nicht erzeugt werden.",
                hinweis="Details stehen im Protokoll.",
            ) from fehler
        logger().debug("Seite erzeugt: %s", ziel.name)
        return ziel

    # -- Seiten einer Mannschaft -------------------------------------------

    def mannschaftsseite(self, art: str, daten: MannschaftsDaten,
                         nummer: int) -> Path:
        """Erzeugt eine einzelne Seite der Mannschaftsdatei."""
        vorlage, ueberschrift = SEITEN_VORLAGEN[art]
        html = self._html(vorlage, seitentitel=ueberschrift, fliessend=False,
                          daten=daten, **_seiten_kontext(art, daten))
        return self._pdf(html, f"{nummer:02d}_{daten.schluessel}_{art}")


    # -- Deckblatt ----------------------------------------------------------

    def deckblatt(self, ausgabe: Ausgabe, titelbild: Path | None) -> Path:
        """Titelseite: Titelbild und die Heimspiele dieser Ausgabe."""
        spieltage = deckblatt_spieltage(ausgabe, self.konfiguration.get(
            "verein.kurzname", ""))
        html = self._html(
            "deckblatt.html.j2",
            seitentitel=self.heft["hefttitel"],
            spieltage=spieltage,
            anzahl_spiele=sum(len(t["spiele"]) for t in spieltage),
            kopfdatum=kopfdatum(ausgabe),
            titelbild_url=(titelbild.as_uri()
                           if titelbild and titelbild.exists() else ""),
        )
        return self._pdf(html, "00_deckblatt")

    def ansprechpartner(self, eintraege: list[dict]) -> Path:
        html = self._html("ansprechpartner.html.j2",
                          seitentitel="Ansprechpartner", fliessend=False,
                          eintraege=eintraege)
        return self._pdf(html, "00_ansprechpartner")


    # -- Gesamtheft --------------------------------------------------------

    def freitextseite(self, titel: str, text: str, name: str,
                      quelle: str = "", absaetze: list[dict] | None = None) -> Path:
        """Text (Vorwort, Bericht) -- darf auf Folgeseiten weiterlaufen.

        ``absaetze`` statt ``text``, wenn die Absaetze schon feststehen (aus
        einer Word-Datei) -- dann gilt keine Ueberschriften-Erkennung.
        """
        html = self._html("freitext.html.j2", seitentitel=titel, fliessend=True,
                          absaetze=absaetze if absaetze is not None
                          else text_zu_absaetzen(text), quelle=quelle)
        return self._pdf(html, name)

    def zwischenbildseite(self, daten: MannschaftsDaten, bild: Path | None,
                          name: str) -> Path:
        html = self._html("zwischenbild.html.j2", seitentitel="", fliessend=False,
                          daten=daten, bild_url=bild.as_uri() if bild else "")
        return self._pdf(html, name)

    def rahmenseite(self, titel: str, name: str) -> Path:
        html = self._html("rahmen.html.j2", seitentitel=titel, fliessend=False)
        return self._pdf(html, name)

    def kontaktlistenseite(self, titel: str, zeilen: list[dict], name: str) -> Path:
        html = self._html("kontaktliste.html.j2", seitentitel=titel,
                          fliessend=True, zeilen=zeilen)
        return self._pdf(html, name)

    def bildseite(self, bild: Path, titel: str, name: str) -> Path:
        html = self._html("bildseite.html.j2", seitentitel=titel, fliessend=False,
                          bild_url=bild.as_uri())
        return self._pdf(html, name)

    def vollbildseite(self, bild: Path | None, name: str) -> Path:
        """Ganze Seite ohne Balken -- fuer Anzeigen als Bild und Leerseiten."""
        html = self._html("vollbild.html.j2", seitentitel="", fliessend=False,
                          bild_url=bild.as_uri() if bild else "")
        return self._pdf(html, name)


def deckblatt_spieltage(ausgabe: Ausgabe, kurzname: str = "") -> list[dict]:
    """Die Heimspiele aller Mannschaften, nach Tagen gruppiert.

    "Wir begruessen unsere Gaeste" -- also nur, wo der Gegner zu uns kommt.
    Jede Mannschaft steuert ihr naechstes Spiel bei; das ist genau das Spiel,
    fuer das ihre Seiten in dieser Ausgabe gemacht sind.
    """
    spiele: list[tuple[Spiel, MannschaftsDaten]] = [
        (m.naechstes_spiel, m) for m in ausgabe.mannschaften
        if m.naechstes_spiel and m.naechstes_spiel.heimspiel]
    # ISO-Text sortiert wie die Zeit; ohne Termin ans Ende.
    spiele.sort(key=lambda p: (p[0].anstoss or "9999", p[1].anzeigename))

    tage: list[dict] = []
    for spiel, daten in spiele:
        eintrag = {
            "paarung": " ".join(t for t in (kurzname, daten.anzeigename) if t)
                       + (f" – {spiel.gegner}" if spiel.gegner else ""),
            "wettbewerb": spiel.wettbewerb or daten.liga,
            "datum": spiel.datum,
            "uhrzeit": spiel.uhrzeit,
        }
        if tage and tage[-1]["datum"] == spiel.datum:
            tage[-1]["spiele"].append(eintrag)
        else:
            tage.append({"wochentag": spiel.wochentag or "Termin offen",
                         "datum": spiel.datum, "spiele": [eintrag]})
    return tage


def kopfdatum(ausgabe: Ausgabe) -> str:
    """'Freitag 16.10.2026' bei einem Tag, sonst '16.–18.10.2026'."""
    termine = sorted({m.naechstes_spiel.anstoss_dt.date()
                      for m in ausgabe.mannschaften
                      if m.naechstes_spiel and m.naechstes_spiel.anstoss_dt})
    if not termine:
        return ""
    erster, letzter = termine[0], termine[-1]
    if erster == letzter:
        return f"{WOCHENTAGE[erster.weekday()]} {erster:%d.%m.%Y}"
    if (erster.year, erster.month) == (letzter.year, letzter.month):
        return f"{erster:%d.}–{letzter:%d.%m.%Y}"
    return f"{erster:%d.%m.}–{letzter:%d.%m.%Y}"


def _seiten_kontext(art: str, daten: MannschaftsDaten) -> dict:
    """Was die jeweilige Vorlage ausser ``daten`` noch braucht.

    Tabelle und Torschuetzenliste kommen zweimal vor: einmal fuer die eigene
    Liga, einmal -- nur bei einem Gegner aus einer anderen Liga -- fuer
    dessen Liga. Beide Faelle benutzen dieselbe Vorlage, nur mit anderen
    Zeilen.
    """
    gegner = daten.gegner_daten
    markieren = [daten.gegner] if daten.gegner else []

    if art == "tabelle":
        return {"zeilen": daten.tabelle, "liga": daten.liga,
                "hervorheben": markieren}
    if art == "torjaeger":
        return {"zeilen": daten.torjaeger[:HOECHSTENS_ZEILEN], "liga": daten.liga,
                "hervorheben": markieren}
    if art == "tabelle_gegner":
        return {"zeilen": gegner.tabelle if gegner else [],
                "liga": (gegner.liga if gegner else "") or daten.gegner,
                "hervorheben": markieren}
    if art == "torjaeger_gegner":
        return {"zeilen": (gegner.torjaeger if gegner else [])[:HOECHSTENS_ZEILEN],
                "liga": (gegner.liga if gegner else "") or daten.gegner,
                "hervorheben": markieren}
    if art == "spielerstatistik":
        return {"spieler": spieler_rangfolge(daten.spieler)}
    if art == "gegner":
        return {"spieler": spieler_rangfolge(gegner.spieler if gegner else [])}
    if art == "vergleich":
        return {"letzte_duelle": letzte_duelle(daten)}
    return {}


def letzte_duelle(daten: MannschaftsDaten, anzahl: int = 3) -> list[Spiel]:
    """Die letzten gespielten Partien gegen denselben Gegner.

    Gesucht wird im eigenen Spielplan; der reicht nur ueber die laufende
    Saison. Das Hinspiel ist damit erfasst, aeltere Duelle nicht -- und
    lieber nichts anzeigen als etwas Halbes behaupten.
    """
    name = (daten.gegner or "").strip().lower()
    if not name:
        return []
    treffer = [s for s in daten.spiele
               if s.gespielt and name in (s.heim + " " + s.gast).lower()]
    treffer.sort(key=lambda s: s.anstoss_dt or datetime.min)
    return treffer[-anzahl:]


def _dateiname(text: str) -> str:
    sauber = re.sub(r"[^a-z0-9]+", "_", (text or "seite").lower())
    return sauber.strip("_") or "seite"
