"""Stadionheft-Generator des SV Wörnitzstein-Berg."""

from __future__ import annotations

import os
from pathlib import Path

__version__ = "0.2.0"

#: Wird beim Bau des Images geschrieben (siehe Dockerfile). Ohne die Datei
#: laeuft das Programm direkt aus dem Quellcode.
_BAUDATUM = Path(__file__).resolve().parent.parent / ".build_datum"


def programmstand() -> str:
    """Welcher Stand laeuft hier gerade?

    Klingt nach Kleinkram, ist aber der Unterschied zwischen "der Fehler ist
    noch da" und "der Container laeuft noch mit dem alten Code". Ohne diese
    Zeile kostet jede Aktualisierung einen Ratedurchgang.
    """
    teile = [f"v{__version__}"]

    datum = ""
    try:
        datum = _BAUDATUM.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    teile.append(f"gebaut {datum}" if datum else "aus dem Quellcode")

    ref = (os.environ.get("STADIONHEFT_BUILD") or "").strip()
    if ref and ref != "unbekannt":
        teile.append(ref[:12])

    return " · ".join(teile)
