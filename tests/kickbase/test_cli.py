"""Kommandozeile -- fuer Cron-Aufrufe und schnelle Blicke ins Terminal."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from kickbase.cli import main


@pytest.fixture
def config_datei(tmp_path: Path) -> str:
    pfad = tmp_path / "kickbase.yaml"
    pfad.write_text(yaml.safe_dump({
        "speicher": {"datenbank": str(tmp_path / "k.sqlite3")},
        "protokoll": {"ordner": str(tmp_path / "logs")},
        "abruf": {"automatisch": False},
    }), encoding="utf-8")
    return str(pfad)


@pytest.fixture
def mit_daten(config_datei: str) -> str:
    assert main(["--config", config_datei, "abruf"]) == 0
    return config_datei


def test_abruf_meldet_erfolg(config_datei, capsys):
    assert main(["--config", config_datei, "abruf"]) == 0
    assert "Demodaten erzeugt" in capsys.readouterr().out


def test_team_zeigt_kader_und_verkaufsvorschlaege(mit_daten, capsys):
    assert main(["--config", mit_daten, "team"]) == 0
    ausgabe = capsys.readouterr().out
    assert "Verkaufsvorschläge" in ausgabe
    assert "Kompletter Kader" in ausgabe


def test_ausfuehrlich_zeigt_begruendungen(mit_daten, capsys):
    main(["--config", mit_daten, "-v", "team"])
    schlicht = capsys.readouterr().out
    main(["--config", mit_daten, "team"])
    assert len(schlicht) > len(capsys.readouterr().out)


def test_markt_laeuft_durch(mit_daten, capsys):
    assert main(["--config", mit_daten, "markt"]) == 0
    assert "Transfermarkt" in capsys.readouterr().out


def test_kandidaten_lassen_sich_filtern(mit_daten, capsys):
    assert main(["--config", mit_daten, "kandidaten", "--position", "4",
                 "--anzahl", "5"]) == 0
    ausgabe = capsys.readouterr().out
    assert "Sturm" in ausgabe
    assert "Torwart" not in ausgabe


def test_spieler_wird_ueber_den_namen_gefunden(mit_daten, capsys):
    from kickbase.config import Konfiguration
    from kickbase.dienst import Berater

    spieler = Berater(Konfiguration.laden(mit_daten)).speicher.spieler_laden()[0]
    assert main(["--config", mit_daten, "spieler", spieler.id]) == 0
    ausgabe = capsys.readouterr().out
    assert spieler.name in ausgabe
    assert "Empfehlung:" in ausgabe
    assert "Kennzahlen:" in ausgabe


def test_unbekannter_spieler_ergibt_einen_fehlercode(mit_daten, capsys):
    assert main(["--config", mit_daten, "spieler", "gibtsnichtxyz"]) == 1
    assert "Kein Spieler" in capsys.readouterr().out


def test_fehlende_konfigurationsdatei_wird_klar_gemeldet(tmp_path, capsys):
    code = main(["--config", str(tmp_path / "fehlt.yaml"), "team"])
    assert code == 1
    assert "gibt es nicht" in capsys.readouterr().err


def test_ohne_befehl_beendet_sich_das_programm():
    with pytest.raises(SystemExit):
        main([])
