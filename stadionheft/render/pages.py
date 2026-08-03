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
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape
from markupsafe import Markup

from ..config import Konfiguration
from ..errors import RenderFehler
from ..logging_setup import logger
from ..models import Ausgabe, MannschaftsDaten, Spiel

TEMPLATE_ORDNER = Path(__file__).resolve().parent.parent / "templates"
STATIC_ORDNER = Path(__file__).resolve().parent.parent / "static"

#: Mannschaftsseite -> (Vorlage, Ueberschrift im roten Balken)
SEITEN_VORLAGEN: dict[str, tuple[str, str]] = {
    "trenner":          ("trenner.html.j2", ""),
    "tabelle":          ("tabelle.html.j2", "Tabellen"),
    "torjaeger":        ("torjaeger.html.j2", "Torschützenlisten"),
    "spielerstatistik": ("spielerstatistik.html.j2", "Spielerstatistik"),
    "gegner":           ("gegner.html.j2", "Vorstellung Gegner"),
    "naechstes_spiel":  ("naechstes_spiel.html.j2", "Nächstes Spiel"),
    "spielbericht":     ("spielbericht.html.j2", "Spielbericht"),
}


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

    # -- Einzelne Seitentypen ----------------------------------------------

    def titelseite(self, ausgabe: Ausgabe, titelbild: Path | None) -> Path:
        spiel = ausgabe.titelspiel or Spiel()
        html = self._html(
            "titelseite.html.j2",
            seitentitel=self.heft["hefttitel"],
            spiel=spiel,
            ausgabe=_ausgabe_kontext(ausgabe),
            titelbild_url=titelbild.as_uri() if titelbild and titelbild.exists() else "",
            titelbild_erwartet="daten/03_eingaben/titelbild.jpg",
        )
        return self._pdf(html, "01_titelseite")

    def mannschaftsseite(self, art: str, daten: MannschaftsDaten,
                         ausgabe: Ausgabe, nummer: int) -> Path:
        vorlage, ueberschrift = SEITEN_VORLAGEN[art]
        kontext: dict = {
            "seitentitel": ueberschrift,
            "daten": daten,
            "ausgabe": _ausgabe_kontext(ausgabe),
            "fliessend": art == "spielbericht",
        }
        if art == "spielbericht":
            kontext["absaetze"] = text_zu_absaetzen(daten.spielbericht)
        html = self._html(vorlage, **kontext)
        return self._pdf(html, f"{nummer:02d}_{daten.schluessel}_{art}")

    def freitextseite(self, titel: str, text: str, ausgabe: Ausgabe,
                      nummer: int, quelle: str = "") -> Path:
        html = self._html(
            "freitext.html.j2",
            seitentitel=titel,
            absaetze=text_zu_absaetzen(text),
            quelle=quelle,
            ausgabe=_ausgabe_kontext(ausgabe),
            fliessend=True,
        )
        return self._pdf(html, f"{nummer:02d}_{_dateiname(titel)}")

    def kontaktseite(self, abschnitte: list[dict], ausgabe: Ausgabe,
                     nummer: int) -> Path:
        html = self._html(
            "kontakte.html.j2",
            seitentitel="Kontaktlisten",
            abschnitte=abschnitte,
            ausgabe=_ausgabe_kontext(ausgabe),
            fliessend=True,
        )
        return self._pdf(html, f"{nummer:02d}_kontakte")

    def impressumsseite(self, felder: list[dict], ausgabe: Ausgabe,
                        nummer: int) -> Path:
        html = self._html(
            "impressum.html.j2",
            seitentitel="Impressum",
            felder=felder,
            ausgabe=_ausgabe_kontext(ausgabe),
        )
        return self._pdf(html, f"{nummer:02d}_impressum")

    def trennseite(self, daten: MannschaftsDaten, nummer: int) -> Path:
        html = self._html("trenner.html.j2", seitentitel="", daten=daten)
        return self._pdf(html, f"{nummer:02d}_trenner")


def _ausgabe_kontext(ausgabe: Ausgabe) -> dict:
    """Vorbereitete Anzeigewerte fuer die Vorlagen."""
    lesbar = ausgabe.erstellt_am
    try:
        from datetime import datetime
        lesbar = f"{datetime.fromisoformat(ausgabe.erstellt_am):%d.%m.%Y, %H:%M} Uhr"
    except (ValueError, TypeError):
        pass
    return {
        "saison": ausgabe.saison,
        "spieltag": ausgabe.spieltag,
        "erstellt_am": ausgabe.erstellt_am,
        "erstellt_am_lesbar": lesbar,
        "erzeugt_von": ausgabe.erzeugt_von,
    }


def _dateiname(text: str) -> str:
    sauber = re.sub(r"[^a-z0-9]+", "_", (text or "seite").lower())
    return sauber.strip("_") or "seite"
