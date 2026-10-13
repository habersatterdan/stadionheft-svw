"""Ablage per File Station: Ordner anlegen, Vorlage kopieren, hochladen.

Die NAS wird im Speicher nachgebaut -- kein Test geht ins Netz.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from stadionheft.config import Konfiguration
from stadionheft.errors import NasFehler
from stadionheft.storage import filestation as fsmod
from stadionheft.storage.filestation import (FileStation, FileStationFehler,
                                             ablage_ausfuehren,
                                             ordnername_pruefen,
                                             ordnername_vorschlagen)

SAISON = "/SVW/Stadionheft/Saison 26-27"


class NachgebauteNas:
    """Ordnerbaum im Speicher: Pfad -> {Name: Groesse oder None fuer Ordner}."""

    def __init__(self) -> None:
        self.baum: dict[str, dict[str, int | None]] = {
            SAISON: {"08 Ausgabe 161026": None, "00 Vorlage": None},
            f"{SAISON}/08 Ausgabe 161026": {},
            f"{SAISON}/00 Vorlage": {"Titelbild.jpeg": 1000, "Herren 1": None},
            f"{SAISON}/00 Vorlage/Herren 1": {"Liga.jpeg": 500},
        }
        self.aufrufe: list[str] = []
        self.groesse_falsch = False

    def auflisten(self, ordner: str) -> list[dict]:
        if ordner not in self.baum:
            raise FileStationFehler("408", code=408)
        return [{"name": n, "path": f"{ordner}/{n}", "isdir": g is None,
                 "additional": {"size": g or 0}}
                for n, g in self.baum[ordner].items()]

    def ordner_anlegen(self, eltern: str, name: str) -> str:
        self.aufrufe.append(f"mkdir {name}")
        self.baum[eltern][name] = None
        self.baum[f"{eltern}/{name}"] = {}
        return f"{eltern}/{name}"

    def _kopie(self, quelle: str, ziel: str) -> None:
        name = quelle.rsplit("/", 1)[1]
        eltern = quelle.rsplit("/", 1)[0]
        self.baum[ziel][name] = self.baum[eltern][name]
        if self.baum[eltern][name] is None:
            self.baum[f"{ziel}/{name}"] = {}
            for kind in list(self.baum[quelle]):
                self._kopie(f"{quelle}/{kind}", f"{ziel}/{name}")

    def kopieren(self, pfade: list[str], ziel: str) -> None:
        self.aufrufe.append(f"copy {len(pfade)}")
        for p in pfade:
            self._kopie(p, ziel)

    def hochladen(self, datei: Path, zielordner: str) -> None:
        self.aufrufe.append(f"upload {datei.name} -> {zielordner}")
        fehlend = []                                # create_parents
        pfad = zielordner
        while pfad not in self.baum:
            fehlend.append(pfad)
            pfad = pfad.rsplit("/", 1)[0]
        for pfad in reversed(fehlend):
            eltern, name = pfad.rsplit("/", 1)
            self.baum[eltern][name] = None
            self.baum[pfad] = {}
        groesse = datei.stat().st_size + (1 if self.groesse_falsch else 0)
        self.baum[zielordner][datei.name] = groesse


@pytest.fixture
def nas_konfiguration(konfiguration: Konfiguration) -> Konfiguration:
    konfiguration.roh["nas"]["aktiv"] = True
    konfiguration.roh["nas"]["modus"] = "filestation"
    konfiguration.roh["nas"]["filestation"].update({
        "quickconnect_id": "test", "saison_ordner": SAISON,
        "vorlage_ordner": "00 Vorlage",
        "mannschaftsordner": {"herren1": "Herren 1", "damen2": "Damen2"}})
    return konfiguration


@pytest.fixture
def dateien(tmp_path: Path) -> list[tuple[str, Path]]:
    paare = []
    for schluessel, name in (("", "2026-10-16_Deckblatt.pdf"),
                             ("herren1", "Herren_1.pdf"),
                             ("damen2", "Damen_2.pdf"),
                             ("herren3", "Herren_3.pdf")):   # ohne Zuordnung
        pfad = tmp_path / name
        pfad.write_bytes(b"%PDF" + name.encode())
        paare.append((schluessel, pfad))
    return paare


def test_ablage_legt_an_kopiert_und_laedt_in_die_mannschaftsordner(
        nas_konfiguration, dateien):
    nas = NachgebauteNas()
    bericht = ablage_ausfuehren(nas_konfiguration, "09 Ausgabe 301026",
                                dateien, fs=nas)
    assert bericht.erfolgreich, bericht.fehler
    neu = f"{SAISON}/09 Ausgabe 301026"
    assert bericht.ordner == neu
    # Vorlage samt Unterordner ist drin
    assert nas.baum[neu]["Titelbild.jpeg"] == 1000
    assert nas.baum[f"{neu}/Herren 1"]["Liga.jpeg"] == 500
    # Dateien dort, wo sie hingehoeren
    assert "Herren_1.pdf" in nas.baum[f"{neu}/Herren 1"]
    assert "Damen_2.pdf" in nas.baum[f"{neu}/Damen2"]
    assert "2026-10-16_Deckblatt.pdf" in nas.baum[neu]
    assert "Herren_3.pdf" in nas.baum[neu]
    # Erst anlegen, dann kopieren, dann hochladen
    assert nas.aufrufe[:2] == ["mkdir 09 Ausgabe 301026", "copy 2"]
    assert bericht.schritte[-1].text.startswith("Geprüft: alle 4 Dateien")


def test_vorhandener_ordner_wird_nicht_angefasst(nas_konfiguration, dateien):
    nas = NachgebauteNas()
    bericht = ablage_ausfuehren(nas_konfiguration, "08 Ausgabe 161026",
                                dateien, fs=nas)
    assert not bericht.erfolgreich
    assert "gibt es schon" in bericht.fehler
    assert nas.aufrufe == []


def test_fehlende_vorlage_bricht_vor_dem_anlegen_ab(nas_konfiguration, dateien):
    nas = NachgebauteNas()
    nas_konfiguration.roh["nas"]["filestation"]["vorlage_ordner"] = "99 Gibtsnicht"
    bericht = ablage_ausfuehren(nas_konfiguration, "09 Ausgabe", dateien, fs=nas)
    assert not bericht.erfolgreich and "Vorlage" in bericht.fehler
    assert nas.aufrufe == []


def test_unvollstaendige_datei_wird_gemeldet(nas_konfiguration, dateien):
    nas = NachgebauteNas()
    nas.groesse_falsch = True
    bericht = ablage_ausfuehren(nas_konfiguration, "09 Ausgabe", dateien, fs=nas)
    assert not bericht.erfolgreich
    assert "nicht alle dateien sind vollständig" in bericht.fehler.lower()
    assert bericht.angelegt


def test_abgebrochener_versuch_wird_fortgesetzt(nas_konfiguration, dateien):
    nas = NachgebauteNas()
    nas.groesse_falsch = True
    erster = ablage_ausfuehren(nas_konfiguration, "09 Ausgabe", dateien, fs=nas)
    assert not erster.erfolgreich and erster.angelegt

    # Ohne "fortsetzen" gilt der Ordner als fremd und bleibt unangetastet
    nas.groesse_falsch = False
    nas.aufrufe.clear()
    fremd = ablage_ausfuehren(nas_konfiguration, "09 Ausgabe", dateien, fs=nas)
    assert not fremd.erfolgreich and nas.aufrufe == []

    zweiter = ablage_ausfuehren(nas_konfiguration, "09 Ausgabe", dateien,
                                fs=nas, fortsetzen=True)
    assert zweiter.erfolgreich, zweiter.fehler
    assert not any(a.startswith("mkdir") for a in nas.aufrufe)
    assert "fortgesetzt" in zweiter.schritte[0].text


def test_fehlende_lokale_datei_bricht_vor_dem_anlegen_ab(nas_konfiguration,
                                                        dateien):
    dateien[1][1].unlink()
    nas = NachgebauteNas()
    bericht = ablage_ausfuehren(nas_konfiguration, "09 Ausgabe", dateien, fs=nas)
    assert not bericht.erfolgreich and nas.aufrufe == []


@pytest.mark.parametrize("name", ["", "   ", "a/b", "..", ".versteckt",
                                  'x"y', "x" * 81, "a:b"])
def test_unzulaessige_ordnernamen(name):
    with pytest.raises(NasFehler):
        ordnername_pruefen(name)


def test_ordnername_wird_bereinigt():
    assert ordnername_pruefen("  09   Ausgabe 301026 ") == "09 Ausgabe 301026"


def test_ordnername_vorschlag_zaehlt_weiter():
    vorhandene = ["01 Ausgabe 290726", "05 Ausgabe 050926", "05_Ausgaben",
                  "08 Ausgabe 161026", "Allgemein", "00 Vorlage"]
    assert ordnername_vorschlagen(vorhandene, datetime(2026, 10, 30)) \
        == "09 Ausgabe 301026"
    assert ordnername_vorschlagen([], datetime(2026, 7, 29)) == "01 Ausgabe 290726"


# -- Wiederholung und Neuanmeldung ------------------------------------------

class _Antwort:
    def __init__(self, status: int, daten: dict | None = None) -> None:
        self.status_code = status
        self._daten = daten

    def json(self):
        if self._daten is None:
            raise ValueError("kein JSON")
        return self._daten


class _Sitzung:
    def __init__(self, antworten: list[_Antwort]) -> None:
        self.antworten = antworten
        self.aufrufe: list[dict] = []

    def post(self, url, data=None, files=None, timeout=None):
        self.aufrufe.append({"url": url, **(data or {})})
        return self.antworten.pop(0)


def _client(antworten: list[_Antwort], monkeypatch) -> tuple[FileStation, _Sitzung]:
    monkeypatch.setattr(fsmod.time, "sleep", lambda _s: None)
    client = FileStation("https://nas.example", "stadionheft", "geheim")
    sitzung = _Sitzung(antworten)
    client._sitzung_obj = sitzung
    return client, sitzung


def test_relay_502_wird_wiederholt(monkeypatch):
    client, sitzung = _client([
        _Antwort(200, {"success": True, "data": {"sid": "S1"}}),
        _Antwort(502),
        _Antwort(200, {"success": True, "data": {"files": [{"name": "a"}]}}),
    ], monkeypatch)
    assert client.auflisten("/x") == [{"name": "a"}]
    assert sitzung.aufrufe[-1]["url"].endswith("?_sid=S1")


def test_verlorene_sitzung_meldet_neu_an(monkeypatch):
    client, sitzung = _client([
        _Antwort(200, {"success": True, "data": {"sid": "S1"}}),
        _Antwort(200, {"success": False, "error": {"code": 119}}),
        _Antwort(200, {"success": True, "data": {"sid": "S2"}}),
        _Antwort(200, {"success": True, "data": {"files": []}}),
    ], monkeypatch)
    assert client.auflisten("/x") == []
    assert sitzung.aufrufe[-1]["url"].endswith("?_sid=S2")
    # Das Passwort steht nie in einer Adresse
    assert all("geheim" not in a["url"] for a in sitzung.aufrufe)


def test_falsches_passwort_ist_verstaendlich(monkeypatch):
    client, _ = _client([_Antwort(200, {"success": False,
                                         "error": {"code": 400}})], monkeypatch)
    with pytest.raises(FileStationFehler) as fehler:
        client.anmelden()
    assert "Passwort" in fehler.value.benutzer_text


def test_dauerhaft_unerreichbar_gibt_auf(monkeypatch):
    client, sitzung = _client([_Antwort(502)] * 3, monkeypatch)
    with pytest.raises(NasFehler):
        client.anmelden()
    assert len(sitzung.aufrufe) == FileStation.VERSUCHE


class _QcAntwort:
    def __init__(self, daten):
        self.daten = daten

    def raise_for_status(self):
        pass

    def json(self):
        return self.daten


def test_quickconnect_adresse(monkeypatch):
    import requests

    monkeypatch.setattr(requests, "post", lambda *a, **k: _QcAntwort(
        [{"errno": 0, "env": {"relay_region": "de7"}}]))
    assert fsmod.quickconnect_adresse("meinverein") == "https://meinverein.de7.quickconnect.to"


def test_quickconnect_folgt_den_regionalen_servern(monkeypatch):
    """Antwort wie am 13.10.2026: global kennt die NAS nicht, nennt 'dec'."""
    import requests

    gefragt: list[str] = []

    def post(url, **_k):
        gefragt.append(url)
        if url.startswith("https://global."):
            return _QcAntwort([{"errno": 4, "errinfo": "Ds info not found",
                                "sites": ["dec.quickconnect.to",
                                          "boese.example.org"]}])
        return _QcAntwort([{"errno": 0, "env": {"control_host": "dec.quickconnect.to",
                                                "relay_region": "de7"}}])

    monkeypatch.setattr(requests, "post", post)
    assert fsmod.quickconnect_adresse("meinverein") == "https://meinverein.de7.quickconnect.to"
    # Nur Synology-Server werden gefragt
    assert gefragt == ["https://global.quickconnect.to/Serv.php",
                       "https://dec.quickconnect.to/Serv.php"]


def test_quickconnect_unbekannte_id(monkeypatch):
    import requests

    monkeypatch.setattr(requests, "post", lambda *a, **k: _QcAntwort(
        [{"errno": 4, "errinfo": "Ds info not found"}]))
    with pytest.raises(NasFehler) as fehler:
        fsmod.quickconnect_adresse("gibtsnicht")
    assert "nicht bekannt" in fehler.value.benutzer_text


def test_ohne_passwort_klare_meldung(nas_konfiguration, monkeypatch):
    monkeypatch.delenv("NAS_PASSWORT", raising=False)
    with pytest.raises(NasFehler) as fehler:
        FileStation.aus_konfiguration(nas_konfiguration)
    assert "Passwort" in fehler.value.benutzer_text


def test_fortschritt_wird_gemeldet(nas_konfiguration, dateien):
    meldungen: list[str] = []
    bericht = ablage_ausfuehren(nas_konfiguration, "09 Ausgabe", dateien,
                                fs=NachgebauteNas(), melden=meldungen.append)
    assert bericht.erfolgreich
    assert meldungen[0].startswith("Kopiere die Vorlage")
    assert "(4 von 4)" in meldungen[-2]
    assert meldungen[-1].startswith("Prüfe")
