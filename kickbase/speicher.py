"""Dauerhafte Ablage in einer SQLite-Datei.

Warum ueberhaupt eine eigene Ablage, wo Kickbase die Daten doch liefert?

1. **Unabhaengigkeit.** Faellt Kickbase aus, zeigt der Berater trotzdem den
   letzten bekannten Stand statt einer Fehlerseite.
2. **Eigene Historie.** Kickbase liefert den Marktwertverlauf nur begrenzt und
   nur fuer einzelne Spieler. Wer taeglich abruft, hat nach ein paar Wochen
   eine lueckenlose eigene Reihe -- die Grundlage fuer die Trendanalyse.
3. **Schonung der Schnittstelle.** Die Oberflaeche liest aus der Datei, nicht
   aus dem Netz. Ein Klick loest also keinen Abruf aus.

SQLite ist bewusst gewaehlt: eine einzige Datei, kein Serverdienst, laesst
sich auf der NAS einfach sichern.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Iterator

from .logging_setup import logger
from .models import Marktwertpunkt, Spieler

SCHEMA = """
CREATE TABLE IF NOT EXISTS spieler (
    id           TEXT PRIMARY KEY,
    gespeichert  TEXT NOT NULL,
    daten        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS marktwert (
    spieler_id TEXT NOT NULL,
    tag        TEXT NOT NULL,
    wert       INTEGER NOT NULL,
    PRIMARY KEY (spieler_id, tag)
);

CREATE TABLE IF NOT EXISTS abruf (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    zeit         TEXT NOT NULL,
    erfolgreich  INTEGER NOT NULL,
    dauer_s      REAL NOT NULL DEFAULT 0,
    spieler      INTEGER NOT NULL DEFAULT 0,
    meldung      TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS notiz (
    schluessel TEXT PRIMARY KEY,
    wert       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS marktwert_tag ON marktwert (tag);
"""


class Speicher:
    """Alle Datenbankzugriffe des Beraters an einer Stelle."""

    def __init__(self, datei: str | Path) -> None:
        self.datei = Path(datei)
        self.datei.parent.mkdir(parents=True, exist_ok=True)
        with self._verbindung() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _verbindung(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.datei, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    # -- Spieler -----------------------------------------------------------

    def spieler_speichern(self, spieler: Iterable[Spieler]) -> int:
        """Legt den aktuellen Stand ab und ergaenzt die Marktwertreihe."""
        heute = date.today().isoformat()
        jetzt = datetime.now().isoformat(timespec="seconds")
        anzahl = 0
        with self._verbindung() as db:
            for s in spieler:
                db.execute(
                    "INSERT INTO spieler (id, gespeichert, daten) VALUES (?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET gespeichert=excluded.gespeichert, "
                    "daten=excluded.daten",
                    (s.id, jetzt, json.dumps(s.als_dict(), ensure_ascii=False)))
                if s.marktwert > 0:
                    db.execute(
                        "INSERT INTO marktwert (spieler_id, tag, wert) VALUES (?, ?, ?) "
                        "ON CONFLICT(spieler_id, tag) DO UPDATE SET wert=excluded.wert",
                        (s.id, heute, int(s.marktwert)))
                # Vom Anbieter geliefertere Verlaufspunkte mitschreiben --
                # sie fuellen die eigene Reihe rueckwirkend auf.
                for punkt in s.verlauf:
                    db.execute(
                        "INSERT INTO marktwert (spieler_id, tag, wert) VALUES (?, ?, ?) "
                        "ON CONFLICT(spieler_id, tag) DO NOTHING",
                        (s.id, punkt.tag.isoformat(), int(punkt.wert)))
                anzahl += 1
        return anzahl

    def spieler_laden(self) -> list[Spieler]:
        """Alle bekannten Spieler mit ihrer gespeicherten Marktwertreihe."""
        with self._verbindung() as db:
            zeilen = db.execute("SELECT daten FROM spieler").fetchall()
            reihen: dict[str, list[Marktwertpunkt]] = {}
            for z in db.execute(
                    "SELECT spieler_id, tag, wert FROM marktwert ORDER BY tag"):
                reihen.setdefault(z["spieler_id"], []).append(
                    Marktwertpunkt(tag=date.fromisoformat(z["tag"]), wert=int(z["wert"])))

        ergebnis: list[Spieler] = []
        for zeile in zeilen:
            try:
                spieler = Spieler.aus_dict(json.loads(zeile["daten"]))
            except (ValueError, TypeError, KeyError) as fehler:
                logger().warning("Gespeicherter Spieler unlesbar: %s", fehler)
                continue
            # Die Datenbankreihe ist die vollstaendigere -- sie enthaelt auch
            # die Werte frueherer Abrufe.
            if reihen.get(spieler.id):
                spieler.verlauf = reihen[spieler.id]
            ergebnis.append(spieler)
        return ergebnis

    def marktwert_reihe(self, spieler_id: str, tage: int = 120) -> list[Marktwertpunkt]:
        grenze = (date.today() - timedelta(days=tage)).isoformat()
        with self._verbindung() as db:
            zeilen = db.execute(
                "SELECT tag, wert FROM marktwert WHERE spieler_id = ? AND tag >= ? "
                "ORDER BY tag", (spieler_id, grenze)).fetchall()
        return [Marktwertpunkt(tag=date.fromisoformat(z["tag"]), wert=int(z["wert"]))
                for z in zeilen]

    def aufraeumen(self, tage: int = 400) -> int:
        """Entfernt sehr alte Marktwerte, damit die Datei nicht unbegrenzt waechst."""
        grenze = (date.today() - timedelta(days=tage)).isoformat()
        with self._verbindung() as db:
            cursor = db.execute("DELETE FROM marktwert WHERE tag < ?", (grenze,))
            return cursor.rowcount or 0

    # -- Abrufprotokoll ----------------------------------------------------

    def abruf_vermerken(self, erfolgreich: bool, spieler: int = 0,
                        dauer_s: float = 0.0, meldung: str = "") -> None:
        with self._verbindung() as db:
            db.execute(
                "INSERT INTO abruf (zeit, erfolgreich, dauer_s, spieler, meldung) "
                "VALUES (?, ?, ?, ?, ?)",
                (datetime.now().isoformat(timespec="seconds"),
                 1 if erfolgreich else 0, float(dauer_s), int(spieler), meldung[:500]))
            # Nur die juengsten 200 Eintraege aufheben.
            db.execute(
                "DELETE FROM abruf WHERE id NOT IN "
                "(SELECT id FROM abruf ORDER BY id DESC LIMIT 200)")

    def letzter_abruf(self) -> dict | None:
        with self._verbindung() as db:
            zeile = db.execute(
                "SELECT * FROM abruf ORDER BY id DESC LIMIT 1").fetchone()
        return dict(zeile) if zeile else None

    def abrufe(self, anzahl: int = 20) -> list[dict]:
        with self._verbindung() as db:
            zeilen = db.execute(
                "SELECT * FROM abruf ORDER BY id DESC LIMIT ?", (anzahl,)).fetchall()
        return [dict(z) for z in zeilen]

    # -- Freie Notizen (Ligadaten, Spielplan, ...) -------------------------

    def notiz_setzen(self, schluessel: str, wert: object) -> None:
        with self._verbindung() as db:
            db.execute(
                "INSERT INTO notiz (schluessel, wert) VALUES (?, ?) "
                "ON CONFLICT(schluessel) DO UPDATE SET wert=excluded.wert",
                (schluessel, json.dumps(wert, ensure_ascii=False, default=str)))

    def notiz_lesen(self, schluessel: str, standard: object = None) -> object:
        with self._verbindung() as db:
            zeile = db.execute(
                "SELECT wert FROM notiz WHERE schluessel = ?", (schluessel,)).fetchone()
        if not zeile:
            return standard
        try:
            return json.loads(zeile["wert"])
        except json.JSONDecodeError:
            return standard
