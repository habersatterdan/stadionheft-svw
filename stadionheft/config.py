"""Laden und Pruefen der Konfiguration.

Grundsatz: Fehler in der Konfiguration werden *beim Start* erkannt und mit
einem klaren Text gemeldet -- nicht erst mitten im Heft-Lauf.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import KonfigurationsFehler

PROJEKT_WURZEL = Path(__file__).resolve().parent.parent
STANDARD_CONFIG = PROJEKT_WURZEL / "config" / "config.yaml"
BEISPIEL_CONFIG = PROJEKT_WURZEL / "config" / "config.example.yaml"
STANDARD_HEFTPLAN = PROJEKT_WURZEL / "config" / "heftplan.yaml"
BEISPIEL_HEFTPLAN = PROJEKT_WURZEL / "config" / "heftplan.example.yaml"

ERLAUBTE_SEITENTYPEN = {
    "trenner", "spielbericht", "gegner", "tabelle",
    "torjaeger", "spielerstatistik", "naechstes_spiel",
}
ERLAUBTE_HEFTPLAN_TYPEN = {
    "titelseite", "trennseite", "freitext", "kontakte",
    "impressum", "mannschaftsbloecke", "pdf", "werbeblock",
}
GUELTIGE_MODI = {"api", "manuell", "demo"}

_SLUG_MUSTER = re.compile(r"/team/([^/?#]+)")


@dataclass
class Mannschaft:
    """Eine konfigurierte Mannschaft."""

    schluessel: str
    anzeigename: str
    gruppe: str = ""
    untertitel: str = ""
    liga: str = ""
    fupa_team_url: str = ""
    aktiv: bool = True
    seiten: list[str] = field(default_factory=lambda: [
        "trenner", "tabelle", "torjaeger", "spielerstatistik"])

    @property
    def fupa_slug(self) -> str:
        """Der Team-Bezeichner aus der FuPa-URL.

        Aus ``https://www.fupa.net/team/sv-woernitzstein-berg-m1-2026-27``
        wird ``sv-woernitzstein-berg-m1-2026-27``. Genau dieser Wert wird in
        den Endpunkt-Vorlagen als ``{team_slug}`` eingesetzt.
        """
        treffer = _SLUG_MUSTER.search(self.fupa_team_url or "")
        return treffer.group(1) if treffer else ""

    @property
    def liga_fehlt(self) -> bool:
        return not self.liga or self.liga.upper().startswith("TODO")


class Konfiguration:
    """Zugriff auf config.yaml mit Pfad-Aufloesung und Validierung."""

    def __init__(self, daten: dict, quelle: Path | None = None) -> None:
        self.roh = daten or {}
        self.quelle = quelle
        self.wurzel = PROJEKT_WURZEL
        self.mannschaften: dict[str, Mannschaft] = {}
        self._mannschaften_lesen()
        self.warnungen: list[str] = []
        self._pruefen()

    # -- Laden --------------------------------------------------------------

    @classmethod
    def laden(cls, pfad: str | Path | None = None) -> "Konfiguration":
        ziel = Path(pfad) if pfad else STANDARD_CONFIG
        if not ziel.exists():
            if ziel == STANDARD_CONFIG and BEISPIEL_CONFIG.exists():
                raise KonfigurationsFehler(
                    f"Konfigurationsdatei {ziel} nicht gefunden.",
                    benutzer_text="Die Konfiguration fehlt noch.",
                    hinweis=("Bitte einmalig die Datei config/config.example.yaml "
                             "nach config/config.yaml kopieren und die mit TODO "
                             "markierten Werte ausfuellen."),
                )
            raise KonfigurationsFehler(
                f"Konfigurationsdatei {ziel} nicht gefunden.",
                benutzer_text=f"Die Konfigurationsdatei {ziel} wurde nicht gefunden.",
            )
        try:
            daten = yaml.safe_load(ziel.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as fehler:
            raise KonfigurationsFehler(
                str(fehler),
                benutzer_text=f"Die Datei {ziel.name} ist fehlerhaft aufgebaut.",
                hinweis=("YAML reagiert empfindlich auf Einrueckungen. Die "
                         "Fehlerstelle steht in der technischen Meldung."),
            ) from fehler
        if not isinstance(daten, dict):
            raise KonfigurationsFehler(
                "Oberste Ebene ist kein Objekt.",
                benutzer_text=f"Die Datei {ziel.name} hat nicht den erwarteten Aufbau.",
            )
        return cls(daten, ziel)

    # -- Bequemer Zugriff ---------------------------------------------------

    def get(self, pfad: str, standard: Any = None) -> Any:
        """Liest einen verschachtelten Wert, z. B. ``get("nas.mount.zielordner")``."""
        knoten: Any = self.roh
        for teil in pfad.split("."):
            if not isinstance(knoten, dict) or teil not in knoten:
                return standard
            knoten = knoten[teil]
        return knoten if knoten is not None else standard

    def pfad(self, wert: str | Path | None, standard: str = "") -> Path:
        """Macht aus einem konfigurierten Pfad einen absoluten Pfad."""
        p = Path(str(wert or standard))
        return p if p.is_absolute() else (self.wurzel / p)

    # -- Mannschaften -------------------------------------------------------

    def _mannschaften_lesen(self) -> None:
        roh = self.get("mannschaften", {}) or {}
        if not isinstance(roh, dict):
            raise KonfigurationsFehler(
                "Abschnitt 'mannschaften' ist keine Zuordnung.",
                benutzer_text="Der Abschnitt 'mannschaften' in der Konfiguration ist fehlerhaft.",
            )
        for schluessel, eintrag in roh.items():
            eintrag = eintrag or {}
            seiten = eintrag.get("seiten") or ["trenner", "tabelle", "torjaeger",
                                               "spielerstatistik"]
            self.mannschaften[schluessel] = Mannschaft(
                schluessel=schluessel,
                anzeigename=eintrag.get("anzeigename", schluessel),
                gruppe=eintrag.get("gruppe", ""),
                untertitel=eintrag.get("untertitel", ""),
                liga=eintrag.get("liga", ""),
                fupa_team_url=eintrag.get("fupa_team_url", ""),
                aktiv=bool(eintrag.get("aktiv", True)),
                seiten=list(seiten),
            )

    def aktive_mannschaften(self) -> list[Mannschaft]:
        return [m for m in self.mannschaften.values() if m.aktiv]

    def mannschaft(self, schluessel: str) -> Mannschaft:
        try:
            return self.mannschaften[schluessel]
        except KeyError:
            bekannt = ", ".join(self.mannschaften) or "(keine)"
            raise KonfigurationsFehler(
                f"Unbekannte Mannschaft '{schluessel}'.",
                benutzer_text=f"Die Mannschaft '{schluessel}' ist nicht konfiguriert.",
                hinweis=f"Bekannte Mannschaften: {bekannt}",
            ) from None

    # -- Validierung --------------------------------------------------------

    def _pruefen(self) -> None:
        fehler: list[str] = []
        warnungen: list[str] = []

        if not self.mannschaften:
            fehler.append("Es ist keine einzige Mannschaft konfiguriert.")

        modus = str(self.get("datenquelle.modus", "demo"))
        if modus not in GUELTIGE_MODI:
            fehler.append(
                f"datenquelle.modus ist '{modus}', erlaubt sind: "
                f"{', '.join(sorted(GUELTIGE_MODI))}.")

        fallback = str(self.get("datenquelle.fallback_modus", "") or "")
        if fallback and fallback not in GUELTIGE_MODI:
            fehler.append(
                f"datenquelle.fallback_modus ist '{fallback}', erlaubt sind: "
                f"{', '.join(sorted(GUELTIGE_MODI))} oder leer.")

        for m in self.mannschaften.values():
            unbekannt = set(m.seiten) - ERLAUBTE_SEITENTYPEN
            if unbekannt:
                fehler.append(
                    f"Mannschaft '{m.schluessel}': unbekannte Seitentypen "
                    f"{sorted(unbekannt)}. Erlaubt: "
                    f"{', '.join(sorted(ERLAUBTE_SEITENTYPEN))}.")
            if modus == "api" and not m.fupa_slug and m.aktiv:
                fehler.append(
                    f"Mannschaft '{m.schluessel}': aus der FuPa-URL laesst sich "
                    f"kein Team-Bezeichner lesen (erwartet wird eine Adresse der "
                    f"Form https://www.fupa.net/team/...).")
            if m.liga_fehlt and m.aktiv:
                warnungen.append(
                    f"Fuer '{m.anzeigename}' ist noch keine Liga eingetragen "
                    f"(config.yaml -> mannschaften.{m.schluessel}.liga).")

        if self.get("nas.aktiv"):
            nas_modus = str(self.get("nas.modus", "mount"))
            if nas_modus not in ("mount", "smb"):
                fehler.append(f"nas.modus ist '{nas_modus}', erlaubt: mount, smb.")
            if nas_modus == "mount" and not self.get("nas.mount.zielordner"):
                fehler.append("nas.aktiv ist true, aber nas.mount.zielordner ist leer.")
            if nas_modus == "smb":
                for schluessel in ("host", "freigabe", "benutzer"):
                    if not self.get(f"nas.smb.{schluessel}"):
                        fehler.append(f"nas.smb.{schluessel} fehlt.")
                var = self.get("nas.smb.passwort_umgebungsvariable", "NAS_PASSWORT")
                if var and not os.environ.get(str(var)):
                    warnungen.append(
                        f"Die Umgebungsvariable {var} mit dem NAS-Passwort ist nicht "
                        f"gesetzt. Der Upload wird fehlschlagen.")

        if fehler:
            raise KonfigurationsFehler(
                " | ".join(fehler),
                benutzer_text="Die Konfiguration enthaelt Fehler:\n- " + "\n- ".join(fehler),
                hinweis="Bitte config/config.yaml korrigieren und erneut versuchen.",
            )
        self.warnungen = warnungen

    # -- Abgeleitete Werte --------------------------------------------------

    @property
    def saison(self) -> str:
        return str(self.get("saison", ""))

    @property
    def hefttitel(self) -> str:
        return str(self.get("verein.hefttitel", "Stadionheft"))

    @property
    def vereinsname(self) -> str:
        return str(self.get("verein.name", ""))

    @property
    def logo_pfad(self) -> Path:
        return self.pfad(self.get("verein.logo"),
                         "stadionheft/static/img/svw_logo.png")

    @property
    def ausgabe_ordner(self) -> Path:
        return self.pfad(self.get("ausgabe.ordner"), "daten/05_ausgaben")

    @property
    def arbeits_ordner(self) -> Path:
        return self.pfad(self.get("ausgabe.arbeitsordner"),
                         "daten/04_zwischenergebnisse")

    @property
    def eingabe_ordner(self) -> Path:
        return self.pfad(self.get("datenquelle.manuell.ordner"), "daten/03_eingaben")

    @property
    def werbung_ordner(self) -> Path:
        return self.pfad(self.get("daten.werbung"), "daten/02_werbung")

    @property
    def daten_wurzel(self) -> Path:
        return self.pfad(self.get("daten.wurzel"), "daten")


# ---------------------------------------------------------------------------
# Heftplan
# ---------------------------------------------------------------------------

def heftplan_laden(pfad: str | Path | None = None) -> list[dict]:
    """Laedt config/heftplan.yaml, faellt sonst auf die Beispieldatei zurueck."""
    ziel = Path(pfad) if pfad else STANDARD_HEFTPLAN
    if not ziel.exists():
        ziel = BEISPIEL_HEFTPLAN
    if not ziel.exists():
        raise KonfigurationsFehler(
            "Kein Heftplan gefunden.",
            benutzer_text="Die Datei config/heftplan.yaml fehlt.",
            hinweis="Bitte config/heftplan.example.yaml nach config/heftplan.yaml kopieren.",
        )
    try:
        daten = yaml.safe_load(ziel.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as fehler:
        raise KonfigurationsFehler(
            str(fehler),
            benutzer_text=f"Die Datei {ziel.name} ist fehlerhaft aufgebaut.",
        ) from fehler

    seiten = daten.get("seiten") if isinstance(daten, dict) else None
    if not isinstance(seiten, list) or not seiten:
        raise KonfigurationsFehler(
            "Heftplan enthaelt keine Liste 'seiten'.",
            benutzer_text=f"Im Heftplan ({ziel.name}) fehlt die Liste 'seiten'.",
        )

    unbekannt = {str(e.get("typ")) for e in seiten if isinstance(e, dict)} \
        - ERLAUBTE_HEFTPLAN_TYPEN
    if unbekannt:
        raise KonfigurationsFehler(
            f"Unbekannte Seitentypen im Heftplan: {sorted(unbekannt)}",
            benutzer_text=("Der Heftplan enthaelt unbekannte Seitentypen: "
                           + ", ".join(sorted(unbekannt))),
            hinweis="Erlaubt: " + ", ".join(sorted(ERLAUBTE_HEFTPLAN_TYPEN)),
        )
    return seiten
