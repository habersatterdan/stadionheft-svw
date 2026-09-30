"""Spielplaene aus Kalenderdateien (iCalendar, .ics).

Warum ausgerechnet dieses Format?

FuPas ``api.fupa.net/robots.txt`` sagt::

    User-agent: *
    Allow: /*.ics$
    Disallow: /

Alles gesperrt -- **ausser Kalenderdateien**. Das ist keine Luecke, sondern
eine ausdrueckliche Freigabe: Kalender sind zum Abonnieren gedacht. Damit ist
der Spielplan der eine Teil, den wir sauber und mit Erlaubnis holen koennen.

Das Format ist alt und einfach (RFC 5545). Es braucht keine Bibliothek:

    BEGIN:VEVENT
    DTSTART:20261004T130000Z
    SUMMARY:SV Wörnitzstein-Berg - SG Alerheim
    LOCATION:Sportgelände Wörnitzstein
    END:VEVENT

Die Paarung steht in SUMMARY. Wer Heim und wer Gast ist, ergibt sich aus der
Reihenfolge -- so schreiben es alle Fussballkalender.

Das Ergebnis wird als Liste von Zuordnungen mit deutschen Feldnamen
zurueckgegeben. Damit laeuft es durch dieselbe Erkennung wie alles andere
(:mod:`stadionheft.sources.erkennung`) und muss nirgends gesondert behandelt
werden.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from ..logging_setup import logger

#: Trennzeichen zwischen den Mannschaften in SUMMARY. Reihenfolge = Vorrang;
#: " - " zuerst, damit ein Bindestrich im Vereinsnamen nicht falsch trennt
#: ("Wörnitzstein-Berg" bleibt heil).
TRENNER = (" - ", " – ", " — ", " vs. ", " vs ", " : ", " gegen ")

_ZEITZONE = re.compile(r";TZID=([^:;]+)")


def ist_kalender(text: str) -> bool:
    return "BEGIN:VCALENDAR" in (text or "")[:2000]


def _entfalten(text: str) -> list[str]:
    """Fortgesetzte Zeilen zusammenfuegen (RFC 5545, 3.1).

    Lange Werte werden umgebrochen; die Fortsetzung beginnt mit einem
    Leerzeichen oder Tabulator.
    """
    zeilen: list[str] = []
    for roh in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if roh[:1] in (" ", "\t") and zeilen:
            zeilen[-1] += roh[1:]
        else:
            zeilen.append(roh)
    return zeilen


def _text(wert: str) -> str:
    """Maskierungen aufloesen (RFC 5545, 3.3.11)."""
    return (wert.replace("\\n", " ").replace("\\N", " ")
                .replace("\\,", ",").replace("\\;", ";")
                .replace("\\\\", "\\").strip())


def _zeitpunkt(wert: str, parameter: str) -> str:
    """DTSTART in einen ISO-Zeitstempel ohne Zeitzone umrechnen.

    ``Z`` bedeutet UTC -- daraus wird Ortszeit gemacht, sonst stuende im Heft
    eine Uhrzeit, die zwei Stunden danebenliegt.
    """
    wert = wert.strip()
    try:
        if wert.endswith("Z"):
            roh = datetime.strptime(wert, "%Y%m%dT%H%M%SZ").replace(
                tzinfo=timezone.utc)
            return roh.astimezone().replace(tzinfo=None).isoformat(
                timespec="seconds")
        if "T" in wert:
            return datetime.strptime(wert[:15], "%Y%m%dT%H%M%S").isoformat(
                timespec="seconds")
        # Ganztaegiger Eintrag: Datum ohne Uhrzeit
        return datetime.strptime(wert[:8], "%Y%m%d").isoformat(timespec="seconds")
    except ValueError:
        logger().debug("Unlesbarer Zeitpunkt im Kalender: %r (%s)", wert, parameter)
        return ""


def _paarung(summary: str) -> tuple[str, str]:
    for trenner in TRENNER:
        if trenner in summary:
            heim, _, gast = summary.partition(trenner)
            return heim.strip(), gast.strip()
    return summary.strip(), ""


def spiele_aus_ics(text: str, wettbewerb: str = "") -> list[dict]:
    """Alle Termine einer Kalenderdatei als Spiel-Zuordnungen.

    Rueckgabe mit deutschen Feldnamen (``heim``, ``gast``, ``anstoss`` ...),
    damit :mod:`stadionheft.sources.erkennung` sie ohne Sonderbehandlung
    erkennt.
    """
    if not ist_kalender(text):
        return []

    spiele: list[dict] = []
    laufend: dict[str, str] | None = None

    for zeile in _entfalten(text):
        if zeile.startswith("BEGIN:VEVENT"):
            laufend = {}
            continue
        if zeile.startswith("END:VEVENT"):
            if laufend:
                spiel = _zu_spiel(laufend, wettbewerb)
                if spiel:
                    spiele.append(spiel)
            laufend = None
            continue
        if laufend is None or ":" not in zeile:
            continue

        kopf, _, wert = zeile.partition(":")
        name, _, parameter = kopf.partition(";")
        laufend[name.upper()] = wert
        if parameter:
            laufend[name.upper() + "#param"] = parameter

    logger().info("Kalender gelesen: %d Termine", len(spiele))
    return spiele


def _zu_spiel(eintrag: dict, wettbewerb: str) -> dict | None:
    summary = _text(eintrag.get("SUMMARY", ""))
    if not summary:
        return None
    heim, gast = _paarung(summary)
    if not gast:
        # Ohne zwei Mannschaften ist es kein Spiel, sondern ein Termin
        # (Training, Versammlung). Solche Eintraege gehoeren nicht ins Heft.
        return None

    spiel = {
        "heim": heim,
        "gast": gast,
        "anstoss": _zeitpunkt(eintrag.get("DTSTART", ""),
                              eintrag.get("DTSTART#param", "")),
        "spielort": _text(eintrag.get("LOCATION", "")),
    }
    beschreibung = _text(eintrag.get("DESCRIPTION", ""))
    liga = wettbewerb or _liga_aus(beschreibung)
    if liga:
        spiel["wettbewerb"] = liga
    ergebnis = _ergebnis_aus(summary, beschreibung)
    if ergebnis:
        spiel["ergebnis"] = ergebnis
    return spiel


_ERGEBNIS = re.compile(r"\b(\d{1,2})\s*:\s*(\d{1,2})\b")


def _ergebnis_aus(summary: str, beschreibung: str) -> str:
    """Manche Kalender tragen das Ergebnis nach, etwa '(2:1)'.

    Zeitangaben wie '15:00' werden ausgeschlossen: Ein Fussballergebnis mit
    einer zweistelligen Null hinten gibt es praktisch nicht.
    """
    for quelle in (summary, beschreibung):
        for treffer in _ERGEBNIS.finditer(quelle or ""):
            heim, gast = treffer.group(1), treffer.group(2)
            if len(gast) == 2 and gast.endswith("0") and int(heim) < 24:
                continue          # sieht nach einer Uhrzeit aus
            return f"{int(heim)}:{int(gast)}"
    return ""


def _liga_aus(beschreibung: str) -> str:
    for zeile in (beschreibung or "").split(","):
        if any(wort in zeile for wort in ("liga", "Liga", "Klasse", "Pokal")):
            return zeile.strip()
    return ""
