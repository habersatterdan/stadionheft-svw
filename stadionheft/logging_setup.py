"""Protokollierung.

Zwei Ziele gleichzeitig:

1. Eine Logdatei je Tag unter ``logs/`` -- fuer die Fehlersuche.
2. Ein Speicher-Handler je Lauf -- dessen Zeilen zeigt die Weboberfläche
   direkt als Fortschrittsprotokoll an.
"""

from __future__ import annotations

import logging
import logging.handlers
from datetime import date
from pathlib import Path

LOGGER_NAME = "stadionheft"
_FORMAT = "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s"


def logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def einrichten(ordner: str | Path = "logs", level: str = "INFO") -> logging.Logger:
    """Richtet Konsolen- und Dateiprotokoll ein (mehrfacher Aufruf ist ok)."""
    log = logging.getLogger(LOGGER_NAME)
    log.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    log.propagate = False

    if any(getattr(h, "_stadionheft", False) for h in log.handlers):
        return log

    formatter = logging.Formatter(_FORMAT)

    konsole = logging.StreamHandler()
    konsole.setFormatter(formatter)
    konsole._stadionheft = True  # type: ignore[attr-defined]
    log.addHandler(konsole)

    try:
        pfad = Path(ordner)
        pfad.mkdir(parents=True, exist_ok=True)
        datei = logging.FileHandler(pfad / f"stadionheft_{date.today():%Y-%m}.log",
                                    encoding="utf-8")
        datei.setFormatter(formatter)
        datei._stadionheft = True  # type: ignore[attr-defined]
        log.addHandler(datei)
    except OSError as fehler:  # z. B. schreibgeschuetztes Verzeichnis
        log.warning("Logdatei konnte nicht angelegt werden: %s", fehler)

    return log


class LaufProtokoll(logging.Handler):
    """Sammelt die Meldungen eines einzelnen Laufs im Arbeitsspeicher.

    Wird als Kontextmanager im Arbeits-Thread benutzt. Es werden nur Meldungen
    aus genau diesem Thread aufgezeichnet -- laufen zwei Benutzer gleichzeitig,
    sieht trotzdem jeder nur sein eigenes Protokoll.
    """

    def __init__(self, level: int = logging.INFO) -> None:
        super().__init__(level)
        self.zeilen: list[dict] = []
        self.thread_id: int | None = None

    def emit(self, record: logging.LogRecord) -> None:
        if self.thread_id is not None and record.thread != self.thread_id:
            return
        self.zeilen.append({
            "zeit": self.format_time(record),
            "level": record.levelname,
            "text": record.getMessage(),
        })

    @staticmethod
    def format_time(record: logging.LogRecord) -> str:
        import time
        return time.strftime("%H:%M:%S", time.localtime(record.created))

    def __enter__(self) -> "LaufProtokoll":
        import threading
        self.thread_id = threading.get_ident()
        logger().addHandler(self)
        return self

    def __exit__(self, *_exc) -> None:
        logger().removeHandler(self)
