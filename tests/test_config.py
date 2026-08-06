from __future__ import annotations

import pytest
import yaml

from stadionheft.config import BEISPIEL_CONFIG, Konfiguration, heftplan_laden
from stadionheft.errors import KonfigurationsFehler


def test_beispielkonfiguration_ist_gueltig(konfiguration: Konfiguration):
    assert konfiguration.vereinsname == "SV Wörnitzstein-Berg"
    assert "herren1" in konfiguration.mannschaften


def test_fupa_slug_aus_url(konfiguration: Konfiguration):
    m = konfiguration.mannschaft("herren1")
    assert m.fupa_slug == "sv-woernitzstein-berg-m1-2026-27"


def test_fupa_slug_leer_bei_unsinniger_url():
    daten = yaml.safe_load(BEISPIEL_CONFIG.read_text(encoding="utf-8"))
    # Ohne API-Modus ist eine unbrauchbare URL nur folgenlos, kein Fehler
    daten["datenquelle"]["modus"] = "demo"
    daten["mannschaften"] = {"x": {"anzeigename": "X",
                                   "fupa_team_url": "https://example.org/foo"}}
    k = Konfiguration(daten)
    assert k.mannschaft("x").fupa_slug == ""


def test_api_modus_verlangt_gueltigen_link():
    daten = yaml.safe_load(BEISPIEL_CONFIG.read_text(encoding="utf-8"))
    daten["datenquelle"]["modus"] = "api"
    daten["mannschaften"] = {"x": {"anzeigename": "X", "fupa_team_url": "kaputt"}}
    with pytest.raises(KonfigurationsFehler) as fehler:
        Konfiguration(daten)
    assert "Team-Bezeichner" in fehler.value.benutzer_text


def test_unbekannter_seitentyp_wird_erkannt():
    daten = yaml.safe_load(BEISPIEL_CONFIG.read_text(encoding="utf-8"))
    daten["mannschaften"]["herren1"]["seiten"] = ["tabelle", "gibtsnicht"]
    with pytest.raises(KonfigurationsFehler) as fehler:
        Konfiguration(daten)
    assert "gibtsnicht" in fehler.value.technisch


def test_unbekannter_datenquellen_modus():
    daten = yaml.safe_load(BEISPIEL_CONFIG.read_text(encoding="utf-8"))
    daten["datenquelle"]["modus"] = "zauberei"
    with pytest.raises(KonfigurationsFehler):
        Konfiguration(daten)


def test_fehlende_liga_ist_nur_warnung(konfiguration: Konfiguration):
    daten = yaml.safe_load(BEISPIEL_CONFIG.read_text(encoding="utf-8"))
    k = Konfiguration(daten)
    assert any("Liga" in w for w in k.warnungen)


def test_unbekannte_mannschaft_meldet_bekannte(konfiguration: Konfiguration):
    with pytest.raises(KonfigurationsFehler) as fehler:
        konfiguration.mannschaft("herren9")
    assert "herren1" in (fehler.value.hinweis or "")


def test_verschachtelter_zugriff(konfiguration: Konfiguration):
    assert konfiguration.get("layout.primaerfarbe") == "#E52421"
    assert konfiguration.get("gibt.es.nicht", "standard") == "standard"


def test_heftplan_beispiel_laedt():
    seiten = heftplan_laden()
    assert any(e.get("typ") == "mannschaftsbloecke" for e in seiten)
