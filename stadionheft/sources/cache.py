"""Einfacher Datei-Cache fuer Netzabfragen.

Zweck:

* Beim Ausprobieren nicht bei jedem Klick erneut FuPa belasten.
* Wenn FuPa waehrend der Hefterstellung kurz ausfaellt, kann auf die zuletzt
  erfolgreich geholten Daten zurueckgegriffen werden ("veralteter Cache" ist
  besser als "kein Heft").
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from ..logging_setup import logger


class DateiCache:
    def __init__(self, ordner: str | Path, gueltigkeit_minuten: int = 120,
                 aktiv: bool = True) -> None:
        self.ordner = Path(ordner)
        self.gueltigkeit = max(0, int(gueltigkeit_minuten)) * 60
        self.aktiv = aktiv
        if self.aktiv:
            try:
                self.ordner.mkdir(parents=True, exist_ok=True)
            except OSError as fehler:
                logger().warning("Cache-Ordner nicht nutzbar (%s) - Cache aus.", fehler)
                self.aktiv = False

    def _datei(self, schluessel: str) -> Path:
        name = hashlib.sha256(schluessel.encode("utf-8")).hexdigest()[:24]
        return self.ordner / f"{name}.json"

    def lesen(self, schluessel: str, auch_veraltet: bool = False) -> Any | None:
        if not self.aktiv:
            return None
        datei = self._datei(schluessel)
        if not datei.exists():
            return None
        try:
            inhalt = json.loads(datei.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        alter = time.time() - float(inhalt.get("zeit", 0))
        if alter > self.gueltigkeit and not auch_veraltet:
            return None
        if alter > self.gueltigkeit:
            logger().warning(
                "Verwende zwischengespeicherte Daten von vor %.0f Minuten fuer %s.",
                alter / 60, schluessel)
        return inhalt.get("daten")

    def schreiben(self, schluessel: str, daten: Any) -> None:
        if not self.aktiv:
            return
        try:
            self._datei(schluessel).write_text(
                json.dumps({"zeit": time.time(), "schluessel": schluessel,
                            "daten": daten}, ensure_ascii=False),
                encoding="utf-8")
        except (OSError, TypeError) as fehler:
            logger().debug("Cache konnte nicht geschrieben werden: %s", fehler)

    def leeren(self) -> int:
        if not self.ordner.exists():
            return 0
        anzahl = 0
        for datei in self.ordner.glob("*.json"):
            try:
                datei.unlink()
                anzahl += 1
            except OSError:
                pass
        return anzahl
