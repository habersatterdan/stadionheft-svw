"""Protokollierung des Kickbase-Beraters.

Eine Datei je Tag unter ``logs/`` plus Ausgabe auf der Konsole. Der Logger
heisst bewusst anders als der des Stadionheft-Generators, damit beide
Anwendungen im selben Container nebeneinander laufen koennten, ohne sich die
Protokolle zu vermischen.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

LOGGER_NAME = "kickbase"
_FORMAT = "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s"


class _KonsolenHandler(logging.StreamHandler):
    """Schreibt immer auf die *gerade gueltige* Standardfehlerausgabe.

    Der normale ``StreamHandler`` merkt sich den Datenstrom beim Erzeugen.
    Wird er spaeter ausgetauscht -- von Gunicorn, von einem Testlauf oder
    beim Umleiten in eine Datei --, schreibt der Handler in einen bereits
    geschlossenen Strom und meldet Fehler, die mit der Anwendung nichts zu
    tun haben.
    """

    def __init__(self) -> None:
        super().__init__(sys.stderr)

    @property
    def stream(self):
        return sys.stderr

    @stream.setter
    def stream(self, _wert) -> None:
        pass


def logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def einrichten(ordner: str | Path = "logs", level: str = "INFO") -> logging.Logger:
    """Richtet Konsolen- und Dateiprotokoll ein (mehrfacher Aufruf ist ok)."""
    log = logging.getLogger(LOGGER_NAME)
    log.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    log.propagate = False

    if any(getattr(h, "_kickbase", False) for h in log.handlers):
        return log

    formatter = logging.Formatter(_FORMAT)

    konsole = _KonsolenHandler()
    konsole.setFormatter(formatter)
    konsole._kickbase = True  # type: ignore[attr-defined]
    log.addHandler(konsole)

    try:
        pfad = Path(ordner)
        pfad.mkdir(parents=True, exist_ok=True)
        datei = logging.handlers.TimedRotatingFileHandler(
            pfad / "kickbase.log", when="midnight", backupCount=14,
            encoding="utf-8")
        datei.setFormatter(formatter)
        datei._kickbase = True  # type: ignore[attr-defined]
        log.addHandler(datei)
    except OSError as fehler:
        # Kein Schreibrecht ist kein Grund, die Anwendung nicht zu starten.
        log.warning("Protokolldatei nicht nutzbar (%s) - nur Konsole.", fehler)

    return log
