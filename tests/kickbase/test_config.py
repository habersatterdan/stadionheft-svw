"""Konfiguration: Standardwerte, Umgebungsvariablen, Pruefungen."""

from __future__ import annotations

import pytest
import yaml

from kickbase.config import BEISPIEL_CONFIG, Konfiguration
from kickbase.errors import KonfigurationsFehler


def test_standardwerte_ohne_datei():
    k = Konfiguration({})
    assert k.get("analyse.form_spieltage") == 5
    assert k.gewicht("verfuegbarkeit") == pytest.approx(1.6)
    assert k.demomodus is True


def test_beispieldatei_ist_gueltig():
    """Die mitgelieferte Beispielkonfiguration muss laden, sonst ist sie wertlos."""
    daten = yaml.safe_load(BEISPIEL_CONFIG.read_text(encoding="utf-8"))
    k = Konfiguration(daten, BEISPIEL_CONFIG)
    assert k.get("quellen.openligadb.aktiv") is True
    assert k.get("quellen.verletzungen.aktiv") is False, \
        "Verletzungsquellen muessen ab Werk ausgeschaltet sein."


def test_eigene_werte_ueberschreiben_nur_das_genannte():
    k = Konfiguration({"analyse": {"form_spieltage": 3}})
    assert k.get("analyse.form_spieltage") == 3
    # Nicht genannte Werte bleiben beim Standard.
    assert k.get("analyse.mindest_marktwert") == 300000
    assert k.gewicht("form") == pytest.approx(1.4)


def test_zugangsdaten_kommen_bevorzugt_aus_der_umgebung(monkeypatch):
    k = Konfiguration({"kickbase": {"email": "aus-datei@example.org",
                                    "passwort": "aus-datei"}})
    assert k.email == "aus-datei@example.org"
    assert k.demomodus is False

    monkeypatch.setenv("KICKBASE_EMAIL", "aus-umgebung@example.org")
    monkeypatch.setenv("KICKBASE_PASSWORT", "geheim")
    assert k.email == "aus-umgebung@example.org"
    assert k.passwort == "geheim"


def test_unsinnige_werte_werden_beim_start_abgelehnt():
    with pytest.raises(KonfigurationsFehler):
        Konfiguration({"analyse": {"form_spieltage": 99}})
    with pytest.raises(KonfigurationsFehler):
        Konfiguration({"abruf": {"intervall_stunden": 0}})


def test_warnung_bei_passwortschutz_ohne_passwort():
    k = Konfiguration({"web": {"passwortschutz": True}})
    assert any("KICKBASE_WEB_PASSWORT" in w for w in k.warnungen)


def test_unbekanntes_gewicht_faellt_auf_den_standard_zurueck():
    k = Konfiguration({"analyse": {"gewichte": {"form": "keine Zahl"}}})
    assert k.gewicht("form") == pytest.approx(1.4)
