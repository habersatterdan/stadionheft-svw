"""Laden und Pruefen der Konfiguration des Kickbase-Beraters.

Grundsatz wie beim Stadionheft: Fehler in der Konfiguration werden beim Start
erkannt und im Klartext gemeldet -- nicht erst mitten im Abruf.

Zugangsdaten gehoeren *nicht* in die YAML-Datei. Sie werden bevorzugt aus den
Umgebungsvariablen ``KICKBASE_EMAIL`` und ``KICKBASE_PASSWORT`` gelesen; nur
wenn die fehlen, wird auf die Datei zurueckgegriffen.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .errors import KonfigurationsFehler

PROJEKT_WURZEL = Path(__file__).resolve().parent.parent
STANDARD_CONFIG = PROJEKT_WURZEL / "config" / "kickbase.yaml"
BEISPIEL_CONFIG = PROJEKT_WURZEL / "config" / "kickbase.example.yaml"

#: Wettbewerbs-ID der Bundesliga in der Kickbase-Schnittstelle.
BUNDESLIGA = "1"

STANDARDWERTE: dict[str, Any] = {
    "kickbase": {
        "email": "",
        "passwort": "",
        "liga_id": "",
        "wettbewerb_id": BUNDESLIGA,
    },
    "abruf": {
        "automatisch": True,
        "intervall_stunden": 6,
        "marktwert_tage": 92,
        "cache_minuten": 60,
        "kandidaten_je_position": 25,
        "hoeflichkeitspause_ms": 250,
    },
    "quellen": {
        "openligadb": {"aktiv": True, "liga": "bl1", "saison": ""},
        "verletzungen": {"aktiv": False, "seiten": [], "hoechstalter_stunden": 12},
    },
    "analyse": {
        "form_spieltage": 5,
        "mindest_marktwert": 300000,
        "mindest_spiele": 3,
        "gewichte": {
            "verfuegbarkeit": 1.6,
            "form": 1.4,
            "einsatzzeit": 1.2,
            "marktwerttrend": 1.0,
            "preis_leistung": 0.9,
            "gegnerstaerke": 0.6,
            "bewertungsniveau": 0.5,
        },
    },
    "web": {
        "titel": "Kickbase-Berater",
        "passwortschutz": False,
        "benutzer": "kickbase",
    },
    "speicher": {"datenbank": "daten/kickbase/kickbase.sqlite3"},
    "protokoll": {"ordner": "logs", "level": "INFO"},
}


def _verschmelzen(standard: dict, eigen: dict) -> dict:
    """Fuegt die Benutzerwerte in die Standardwerte ein (rekursiv)."""
    ergebnis = dict(standard)
    for schluessel, wert in (eigen or {}).items():
        if isinstance(wert, dict) and isinstance(ergebnis.get(schluessel), dict):
            ergebnis[schluessel] = _verschmelzen(ergebnis[schluessel], wert)
        else:
            ergebnis[schluessel] = wert
    return ergebnis


class Konfiguration:
    """Zugriff auf kickbase.yaml mit Pfadaufloesung und Pruefung."""

    def __init__(self, daten: dict | None = None, quelle: Path | None = None) -> None:
        self.roh = _verschmelzen(STANDARDWERTE, daten or {})
        self.quelle = quelle
        self.wurzel = PROJEKT_WURZEL
        self.warnungen: list[str] = []
        self._pruefen()

    # -- Laden -------------------------------------------------------------

    @classmethod
    def laden(cls, pfad: str | Path | None = None) -> "Konfiguration":
        datei = Path(pfad) if pfad else STANDARD_CONFIG
        if not datei.exists():
            if pfad:
                raise KonfigurationsFehler(
                    f"Konfigurationsdatei nicht gefunden: {datei}",
                    benutzer_text=f"Die Datei {datei} gibt es nicht.",
                    hinweis="Bitte den Pfad pruefen oder ohne Angabe starten.")
            # Ohne eigene Datei laeuft der Berater mit den Standardwerten.
            # Das genuegt, solange die Zugangsdaten als Umgebungsvariablen
            # gesetzt sind -- typisch fuer den Betrieb im Container.
            return cls({}, quelle=None)
        try:
            inhalt = yaml.safe_load(datei.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as fehler:
            raise KonfigurationsFehler(
                f"YAML-Fehler in {datei}: {fehler}",
                benutzer_text=f"Die Datei {datei.name} ist fehlerhaft aufgebaut.",
                hinweis="Meist eine falsche Einrueckung. Zeile aus der "
                        "technischen Meldung pruefen.") from fehler
        except OSError as fehler:
            raise KonfigurationsFehler(
                f"{datei} nicht lesbar: {fehler}") from fehler
        if not isinstance(inhalt, dict):
            raise KonfigurationsFehler(
                f"{datei} enthaelt kein Zuordnungs-Dokument.",
                benutzer_text=f"Die Datei {datei.name} hat nicht den erwarteten Aufbau.")
        return cls(inhalt, quelle=datei)

    # -- Zugriff -----------------------------------------------------------

    def get(self, pfad: str, standard: Any = None) -> Any:
        """Liest einen Wert ueber einen Punkt-Pfad, z. B. ``analyse.form_spieltage``."""
        stelle: Any = self.roh
        for teil in pfad.split("."):
            if not isinstance(stelle, dict) or teil not in stelle:
                return standard
            stelle = stelle[teil]
        return stelle

    def pfad(self, wert: str | None, standard: str) -> Path:
        """Macht aus einer Pfadangabe einen absoluten Pfad."""
        roh = Path(str(wert or standard))
        return roh if roh.is_absolute() else (self.wurzel / roh)

    # -- Zugangsdaten ------------------------------------------------------

    @property
    def email(self) -> str:
        return os.environ.get("KICKBASE_EMAIL") or str(self.get("kickbase.email", ""))

    @property
    def passwort(self) -> str:
        return os.environ.get("KICKBASE_PASSWORT") or str(self.get("kickbase.passwort", ""))

    @property
    def zugangsdaten_vorhanden(self) -> bool:
        return bool(self.email and self.passwort)

    @property
    def liga_id(self) -> str:
        return str(os.environ.get("KICKBASE_LIGA") or self.get("kickbase.liga_id", "") or "")

    @property
    def wettbewerb_id(self) -> str:
        return str(self.get("kickbase.wettbewerb_id", BUNDESLIGA) or BUNDESLIGA)

    @property
    def web_passwort(self) -> str:
        return os.environ.get("KICKBASE_WEB_PASSWORT", "")

    # -- Analyse -----------------------------------------------------------

    def gewicht(self, schluessel: str) -> float:
        gewichte = self.get("analyse.gewichte", {}) or {}
        standard = STANDARDWERTE["analyse"]["gewichte"].get(schluessel, 1.0)
        try:
            return float(gewichte.get(schluessel, standard))
        except (TypeError, ValueError):
            return float(standard)

    @property
    def datenbank(self) -> Path:
        return self.pfad(self.get("speicher.datenbank"),
                         STANDARDWERTE["speicher"]["datenbank"])

    # -- Pruefung ----------------------------------------------------------

    def _pruefen(self) -> None:
        if not self.zugangsdaten_vorhanden:
            self.warnungen.append(
                "Keine Kickbase-Zugangsdaten gesetzt. Der Berater startet im "
                "Demomodus mit Beispieldaten. Zugangsdaten als Umgebungsvariablen "
                "KICKBASE_EMAIL und KICKBASE_PASSWORT setzen.")

        spieltage = self.get("analyse.form_spieltage", 5)
        if not isinstance(spieltage, int) or not 1 <= spieltage <= 34:
            raise KonfigurationsFehler(
                f"analyse.form_spieltage muss zwischen 1 und 34 liegen, ist '{spieltage}'.",
                benutzer_text="Der Wert 'form_spieltage' muss eine Zahl von 1 bis 34 sein.")

        stunden = self.get("abruf.intervall_stunden", 6)
        if not isinstance(stunden, (int, float)) or stunden <= 0:
            raise KonfigurationsFehler(
                f"abruf.intervall_stunden muss groesser als 0 sein, ist '{stunden}'.",
                benutzer_text="Der Wert 'intervall_stunden' muss eine positive Zahl sein.")

        if self.get("web.passwortschutz") and not self.web_passwort:
            self.warnungen.append(
                "Passwortschutz ist eingeschaltet, aber die Umgebungsvariable "
                "KICKBASE_WEB_PASSWORT ist leer. Die Oberfläche bleibt offen.")

        seiten = self.get("quellen.verletzungen.seiten", []) or []
        if self.get("quellen.verletzungen.aktiv") and not seiten:
            self.warnungen.append(
                "Verletzungsquellen sind eingeschaltet, aber es ist keine Seite "
                "hinterlegt. Es wird nur der Kickbase-Status ausgewertet.")

    @property
    def demomodus(self) -> bool:
        """Ohne Zugangsdaten laeuft der Berater mit Beispieldaten."""
        return not self.zugangsdaten_vorhanden
