"""Werbeblöcke aus einem Ordner: Reihenfolge, Befristung, Pausieren."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pypdf import PageObject, PdfWriter

from stadionheft.render.werbung import Anzeige, anzeigen_lesen, werbeblock


def _anzeige(ordner: Path, name: str) -> Path:
    """Legt eine gueltige einseitige PDF im A5-Format an."""
    ordner.mkdir(parents=True, exist_ok=True)
    schreiber = PdfWriter()
    schreiber.add_page(PageObject.create_blank_page(width=419.53, height=595.28))
    ziel = ordner / name
    with ziel.open("wb") as datei:
        schreiber.write(datei)
    return ziel


# ---------------------------------------------------------------------------
# Reihenfolge
# ---------------------------------------------------------------------------

def test_reihenfolge_folgt_dem_dateinamen(tmp_path: Path):
    for name in ("030_c.pdf", "010_a.pdf", "020_b.pdf"):
        _anzeige(tmp_path, name)
    anzeigen, _ = werbeblock(tmp_path, date(2026, 8, 4))
    assert [a.pfad.name for a in anzeigen] == ["010_a.pdf", "020_b.pdf", "030_c.pdf"]


def test_nur_pdf_dateien(tmp_path: Path):
    _anzeige(tmp_path, "010_a.pdf")
    (tmp_path / "notiz.txt").write_text("kein PDF", encoding="utf-8")
    (tmp_path / "bild.jpg").write_bytes(b"x")
    anzeigen, _ = werbeblock(tmp_path, date(2026, 8, 4))
    assert len(anzeigen) == 1


# ---------------------------------------------------------------------------
# Befristung
# ---------------------------------------------------------------------------

def test_abgelaufene_anzeige_faellt_heraus(tmp_path: Path):
    """Der konkrete Fall: Ankuendigung eines Spiels vom 01.08."""
    _anzeige(tmp_path, "010_bayern-spiel__bis_2026-08-01.pdf")
    _anzeige(tmp_path, "020_dauerkunde.pdf")

    anzeigen, hinweise = werbeblock(tmp_path, date(2026, 8, 4))
    assert [a.pfad.name for a in anzeigen] == ["020_dauerkunde.pdf"]
    assert any("abgelaufen" in h and "bayern" in h.lower() for h in hinweise)


def test_anzeige_am_letzten_gueltigkeitstag_ist_dabei(tmp_path: Path):
    _anzeige(tmp_path, "010_spiel__bis_2026-08-01.pdf")
    anzeigen, _ = werbeblock(tmp_path, date(2026, 8, 1))
    assert len(anzeigen) == 1


def test_anzeige_startet_erst_spaeter(tmp_path: Path):
    _anzeige(tmp_path, "010_sommerfest__ab_2026-09-01.pdf")
    anzeigen, hinweise = werbeblock(tmp_path, date(2026, 8, 4))
    assert anzeigen == []
    assert any("startet erst" in h for h in hinweise)


def test_zeitfenster_mit_ab_und_bis(tmp_path: Path):
    _anzeige(tmp_path, "010_aktion__ab_2026-08-01__bis_2026-08-31.pdf")
    assert len(werbeblock(tmp_path, date(2026, 7, 31))[0]) == 0
    assert len(werbeblock(tmp_path, date(2026, 8, 15))[0]) == 1
    assert len(werbeblock(tmp_path, date(2026, 9, 1))[0]) == 0


def test_unlesbares_datum_wird_ignoriert(tmp_path: Path):
    """Ein Tippfehler im Datum darf die Anzeige nicht verschwinden lassen."""
    _anzeige(tmp_path, "010_kunde__bis_31-12-2026.pdf")
    anzeigen, _ = werbeblock(tmp_path, date(2026, 8, 4))
    assert len(anzeigen) == 1


def test_anzeige_ohne_datum_laeuft_immer(tmp_path: Path):
    _anzeige(tmp_path, "010_dauerkunde.pdf")
    assert len(werbeblock(tmp_path, date(2030, 1, 1))[0]) == 1


# ---------------------------------------------------------------------------
# Pausieren und leere Ordner
# ---------------------------------------------------------------------------

def test_pausierte_anzeigen_werden_nicht_eingebunden(tmp_path: Path):
    _anzeige(tmp_path, "010_aktiv.pdf")
    _anzeige(tmp_path / "_pausiert", "020_ruht.pdf")
    anzeigen, hinweise = werbeblock(tmp_path, date(2026, 8, 4))
    assert [a.pfad.name for a in anzeigen] == ["010_aktiv.pdf"]
    assert any("_pausiert" in h for h in hinweise)


def test_leerer_ordner_meldet_verstaendlich(tmp_path: Path):
    ordner = tmp_path / "vorne"
    ordner.mkdir()
    anzeigen, hinweise = werbeblock(ordner, date(2026, 8, 4))
    assert anzeigen == []
    assert any("keine einzige PDF-Anzeige" in h for h in hinweise)


def test_fehlender_ordner_meldet_verstaendlich(tmp_path: Path):
    anzeigen, hinweise = werbeblock(tmp_path / "gibtsnicht", date(2026, 8, 4))
    assert anzeigen == []
    assert any("existiert nicht" in h for h in hinweise)


# ---------------------------------------------------------------------------
# Anzeigetitel fuer Meldungen
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dateiname,erwartet", [
    ("010_teamshop.pdf", "teamshop"),
    ("020_jako-katalog-1.pdf", "jako-katalog-1"),
    ("010_bayern-spiel__bis_2026-08-01.pdf", "bayern-spiel"),
    ("030_optik_augenblick.pdf", "optik augenblick"),
])
def test_titel_ist_lesbar(tmp_path: Path, dateiname: str, erwartet: str):
    assert Anzeige(pfad=tmp_path / dateiname).titel == erwartet


def test_anzeigen_lesen_bei_fehlendem_ordner(tmp_path: Path):
    assert anzeigen_lesen(tmp_path / "weg") == []
