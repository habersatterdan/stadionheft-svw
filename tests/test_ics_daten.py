"""Spielplaene aus Kalenderdateien.

Der Kalender ist der eine Weg, den FuPas robots.txt ausdruecklich freigibt
("Allow: /*.ics$"). Entsprechend genau muss er gelesen werden.
"""

from __future__ import annotations

from stadionheft.sources.erkennung import spiele_erkennen
from stadionheft.sources.ics_daten import ist_kalender, spiele_aus_ics

KALENDER = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//FuPa//Spielplan//DE
BEGIN:VEVENT
UID:1@fupa.net
DTSTART:20261004T130000Z
SUMMARY:SV Wörnitzstein-Berg - SG Alerheim
LOCATION:Sportgelände Wörnitzstein
DESCRIPTION:Bezirksliga Schwaben Nord
END:VEVENT
BEGIN:VEVENT
UID:2@fupa.net
DTSTART:20260927T130000Z
SUMMARY:TSV Meitingen - SV Wörnitzstein-Berg (1:2)
LOCATION:Sportpark Meitingen
END:VEVENT
END:VCALENDAR
"""


def test_kalender_wird_erkannt():
    assert ist_kalender(KALENDER) is True
    assert ist_kalender("<html>Kein Kalender</html>") is False
    assert ist_kalender("") is False


def test_paarung_und_ort():
    spiele = spiele_aus_ics(KALENDER)
    assert len(spiele) == 2
    assert spiele[0]["heim"] == "SV Wörnitzstein-Berg"
    assert spiele[0]["gast"] == "SG Alerheim"
    assert spiele[0]["spielort"] == "Sportgelände Wörnitzstein"
    assert spiele[0]["wettbewerb"] == "Bezirksliga Schwaben Nord"


def test_bindestrich_im_vereinsnamen_trennt_nicht():
    """'Wörnitzstein-Berg' darf nicht als Paarung missverstanden werden."""
    spiele = spiele_aus_ics(KALENDER)
    assert spiele[0]["heim"] == "SV Wörnitzstein-Berg"


def test_utc_wird_in_ortszeit_umgerechnet():
    """13:00 UTC sind im Sommer 15:00 Ortszeit -- sonst steht es falsch im Heft."""
    spiele = spiele_aus_ics(KALENDER)
    assert spiele[0]["anstoss"].startswith("2026-10-04T")
    assert not spiele[0]["anstoss"].endswith("Z")


def test_nachgetragenes_ergebnis_wird_mitgenommen():
    spiele = spiele_aus_ics(KALENDER)
    assert spiele[1]["ergebnis"] == "1:2"


def test_uhrzeit_wird_nicht_fuer_ein_ergebnis_gehalten():
    kalender = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:20261004T130000Z\n"
                "SUMMARY:A - B um 15:00 Uhr\nEND:VEVENT\nEND:VCALENDAR\n")
    assert spiele_aus_ics(kalender)[0].get("ergebnis", "") == ""


def test_termine_ohne_gegner_fallen_weg():
    """Training und Versammlungen gehoeren nicht in den Spielplan."""
    kalender = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:20261001T170000Z\n"
                "SUMMARY:Training\nEND:VEVENT\nEND:VCALENDAR\n")
    assert spiele_aus_ics(kalender) == []


def test_umgebrochene_zeilen_werden_zusammengefuegt():
    """Lange Werte bricht iCalendar um; die Fortsetzung beginnt mit Leerzeichen."""
    kalender = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:20261004T130000Z\n"
                "SUMMARY:SV Wörnitzstein-Berg - SG Aler\n heim\n"
                "END:VEVENT\nEND:VCALENDAR\n")
    assert spiele_aus_ics(kalender)[0]["gast"] == "SG Alerheim"


def test_maskierungen_werden_aufgeloest():
    kalender = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:20261004T130000Z\n"
                "SUMMARY:A - B\nLOCATION:Musterweg 1\\, Wörnitzstein\n"
                "END:VEVENT\nEND:VCALENDAR\n")
    assert spiele_aus_ics(kalender)[0]["spielort"] == "Musterweg 1, Wörnitzstein"


def test_kein_kalender_ergibt_nichts():
    assert spiele_aus_ics("<html><body>Nichts</body></html>") == []
    assert spiele_aus_ics("") == []


def test_geht_durch_dieselbe_erkennung():
    """Der Kalender braucht keine Sonderbehandlung weiter hinten."""
    spiele = spiele_erkennen({"spiele": spiele_aus_ics(KALENDER)},
                             "SV Wörnitzstein-Berg")
    assert len(spiele) == 2
    assert spiele[0].heimspiel is True
    assert spiele[0].gegner == "SG Alerheim"
    assert spiele[1].heimspiel is False
    assert spiele[1].ergebnis == "1:2"
