from __future__ import annotations

import pytest
import yaml

from stadionheft.config import BEISPIEL_CONFIG, Konfiguration
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


def test_mannschaft_ohne_fupa_link_ist_nur_eine_warnung():
    """Eine Mannschaft ohne FuPa-Seite darf den Start nicht verhindern.

    Sonst bekaeme wegen einer neu gegruendeten AH auch keine der anderen
    Mannschaften mehr eine Datei.
    """
    daten = yaml.safe_load(BEISPIEL_CONFIG.read_text(encoding="utf-8"))
    daten["datenquelle"]["modus"] = "api"
    daten["mannschaften"] = {"x": {"anzeigename": "X", "fupa_team_url": "kaputt"}}

    k = Konfiguration(daten)

    assert any("keine FuPa-Teamseite" in w for w in k.warnungen), k.warnungen


def test_vertippter_schluessel_wird_erkannt():
    """Ein Tippfehler darf nicht stillschweigend ignoriert werden.

    'fallbackmodus' statt 'fallback_modus' wuerde sonst dazu fuehren, dass
    sich das Programm anders verhaelt, als die Datei aussagt -- ohne dass
    irgendwo etwas davon steht.
    """
    daten = yaml.safe_load(BEISPIEL_CONFIG.read_text(encoding="utf-8"))
    daten["datenquelle"]["fallbackmodus"] = daten["datenquelle"].pop("fallback_modus")

    with pytest.raises(KonfigurationsFehler) as fehler:
        Konfiguration(daten)

    assert "fallback_modus" in fehler.value.benutzer_text


def test_vertippter_schluessel_bei_einer_mannschaft():
    daten = yaml.safe_load(BEISPIEL_CONFIG.read_text(encoding="utf-8"))
    eintrag = daten["mannschaften"]["herren1"]
    eintrag["anzeige_name"] = eintrag.pop("anzeigename")

    with pytest.raises(KonfigurationsFehler) as fehler:
        Konfiguration(daten)

    assert "anzeigename" in fehler.value.benutzer_text


def test_freie_abschnitte_bleiben_frei():
    """Endpunktnamen, Gegnernamen und Mannschaftsschluessel sind frei waehlbar."""
    daten = yaml.safe_load(BEISPIEL_CONFIG.read_text(encoding="utf-8"))
    daten["datenquelle"]["fupa"]["endpunkte"]["statistik_neu"] = "/x"
    daten["datenquelle"]["fupa"]["gegner"]["SG Alerheim"] = "https://example.invalid/t"
    daten["mannschaften"]["ah"] = {
        "anzeigename": "AH", "liga": "Freundschaftsspiele",
        "fupa_team_url": "https://www.fupa.net/team/svw-ah-2026-27"}

    k = Konfiguration(daten)

    assert not any("nicht bekannt" in w for w in k.warnungen), k.warnungen


def test_unbekannter_eintrag_ist_nur_ein_hinweis():
    """Eine bewusste Ergaenzung darf den Start nicht verhindern."""
    daten = yaml.safe_load(BEISPIEL_CONFIG.read_text(encoding="utf-8"))
    daten["eigene_notiz"] = "Zettel fuer mich selbst"

    k = Konfiguration(daten)

    assert any("eigene_notiz" in w for w in k.warnungen)


def test_todo_liga_wird_nicht_gedruckt():
    """'TODO: Liga eintragen' darf nie in einem PDF landen."""
    daten = yaml.safe_load(BEISPIEL_CONFIG.read_text(encoding="utf-8"))
    k = Konfiguration(daten)

    m = k.mannschaft("herren2")
    assert m.liga_fehlt
    assert m.liga_anzeige == ""
    assert k.mannschaft("herren1").liga_anzeige == "Bezirksliga Schwaben Nord"


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
