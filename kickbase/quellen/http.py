"""Gemeinsamer HTTP-Zugriff fuer alle Netzquellen.

Enthaelt die drei Dinge, die man sonst in jeder Quelle einzeln falsch macht:

* **Wiederholung mit wachsender Wartezeit** bei Netzhakeln und bei ``429``
  (zu viele Anfragen) -- so wird die Gegenstelle nicht ueberrannt.
* **Datei-Cache**, damit ein Neustart oder ein zweiter Blick auf dieselbe
  Seite keinen neuen Abruf ausloest.
* **Klare Fehler** statt roher ``requests``-Ausnahmen.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import requests

from ..errors import QuelleNichtErreichbarFehler
from ..logging_setup import logger

#: Ein ehrlicher Kennzeichner. Wer Anfragen stellt, sollte sagen, wer er ist.
KENNUNG = "kickbase-berater/0.1 (privates Heimserver-Projekt)"


class DateiCache:
    """Sehr einfacher Cache: eine JSON-Datei je Abfrage."""

    def __init__(self, ordner: str | Path, gueltigkeit_minuten: int = 60,
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
        return inhalt.get("daten")

    def schreiben(self, schluessel: str, daten: Any) -> None:
        if not self.aktiv:
            return
        try:
            self._datei(schluessel).write_text(
                json.dumps({"zeit": time.time(), "daten": daten},
                           ensure_ascii=False),
                encoding="utf-8")
        except (OSError, TypeError) as fehler:
            logger().debug("Cache nicht geschrieben: %s", fehler)


class HttpQuelle:
    """Basis fuer jede Quelle, die im Netz nachfragt."""

    #: Kurzname fuers Protokoll.
    name = "http"

    def __init__(self, cache: DateiCache | None = None,
                 zeitlimit: int = 20, versuche: int = 3,
                 pause_ms: int = 0) -> None:
        self.cache = cache
        self.zeitlimit = zeitlimit
        self.versuche = max(1, versuche)
        self.pause_ms = max(0, pause_ms)
        self.sitzung = requests.Session()
        self.sitzung.headers.update({
            "User-Agent": KENNUNG,
            "Accept": "application/json",
        })

    # -- Innereien ---------------------------------------------------------

    def _warten(self) -> None:
        """Hoeflichkeitspause zwischen zwei Anfragen an dieselbe Gegenstelle."""
        if self.pause_ms:
            time.sleep(self.pause_ms / 1000)

    def anfragen(self, methode: str, url: str, *, json_daten: dict | None = None,
                 params: dict | None = None,
                 kopfzeilen: dict | None = None) -> requests.Response:
        """Fuehrt eine Anfrage aus und wiederholt sie bei vorruebergehenden Fehlern."""
        letzter: Exception | None = None
        for versuch in range(1, self.versuche + 1):
            try:
                self._warten()
                antwort = self.sitzung.request(
                    methode, url, json=json_daten, params=params,
                    headers=kopfzeilen, timeout=self.zeitlimit)
            except requests.RequestException as fehler:
                letzter = fehler
                logger().warning("%s: Versuch %d/%d fehlgeschlagen (%s)",
                                 self.name, versuch, self.versuche, fehler)
            else:
                # 429 und 5xx sind vorruebergehend -- alles andere geben wir
                # unveraendert zurueck, damit der Aufrufer z. B. 401 selbst
                # als Anmeldeproblem behandeln kann.
                if antwort.status_code != 429 and antwort.status_code < 500:
                    return antwort
                letzter = QuelleNichtErreichbarFehler(
                    f"{url} antwortete mit {antwort.status_code}")
                logger().warning("%s: %s antwortete mit %d (Versuch %d/%d)",
                                 self.name, url, antwort.status_code,
                                 versuch, self.versuche)
            if versuch < self.versuche:
                time.sleep(2 ** versuch)

        raise QuelleNichtErreichbarFehler(
            f"{url} nach {self.versuche} Versuchen nicht erreichbar: {letzter}",
            benutzer_text=f"{self.name} ist im Moment nicht erreichbar.",
            hinweis="Der Berater arbeitet mit den zuletzt gespeicherten Daten weiter.")

    def holen(self, url: str, *, params: dict | None = None,
              kopfzeilen: dict | None = None,
              cache_schluessel: str | None = None) -> Any:
        """GET mit JSON-Antwort und optionalem Cache."""
        schluessel = cache_schluessel or f"{url}?{sorted((params or {}).items())}"
        if self.cache:
            zwischenstand = self.cache.lesen(schluessel)
            if zwischenstand is not None:
                return zwischenstand

        try:
            antwort = self.anfragen("GET", url, params=params, kopfzeilen=kopfzeilen)
        except QuelleNichtErreichbarFehler:
            # Lieber veraltete Daten als gar keine.
            if self.cache:
                notfall = self.cache.lesen(schluessel, auch_veraltet=True)
                if notfall is not None:
                    logger().warning(
                        "%s nicht erreichbar - verwende aeltere Daten aus dem Cache.",
                        self.name)
                    return notfall
            raise

        if antwort.status_code >= 400:
            raise QuelleNichtErreichbarFehler(
                f"{url} antwortete mit {antwort.status_code}: {antwort.text[:200]}",
                benutzer_text=f"{self.name} hat die Anfrage abgelehnt "
                              f"(Code {antwort.status_code}).")
        try:
            daten = antwort.json()
        except ValueError as fehler:
            raise QuelleNichtErreichbarFehler(
                f"{url} lieferte kein JSON: {fehler}",
                benutzer_text=f"{self.name} hat unerwartete Daten geliefert.") from fehler

        if self.cache:
            self.cache.schreiben(schluessel, daten)
        return daten

    def text_holen(self, url: str, kopfzeilen: dict | None = None) -> str:
        """GET fuer Seiten, die HTML statt JSON liefern."""
        kopf = {"Accept": "text/html,application/xhtml+xml"}
        kopf.update(kopfzeilen or {})
        antwort = self.anfragen("GET", url, kopfzeilen=kopf)
        if antwort.status_code >= 400:
            raise QuelleNichtErreichbarFehler(
                f"{url} antwortete mit {antwort.status_code}",
                benutzer_text=f"{url} war nicht abrufbar "
                              f"(Code {antwort.status_code}).")
        return antwort.text
