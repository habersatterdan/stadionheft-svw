"""Die FuPa-Quelle klappert Adressen ab und erkennt die Daten selbst.

Getestet wird das Zusammenspiel, nicht die Erkennung an sich (die hat
``test_erkennung.py``) und nicht das Auspacken von HTML (``test_html_daten.py``).
Der HTTP-Teil wird ersetzt: Die Tests duerfen nie ins Netz gehen.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from stadionheft.config import Konfiguration
from stadionheft.errors import (DatenNichtLesbarFehler,
                                DatenquelleNichtErreichbarFehler)
from stadionheft.sources.fupa_api import (KANDIDATEN, FupaApiQuelle,
                                          _nutzlasten_aus, adressen_fuer,
                                          probe_fupa)

# ---------------------------------------------------------------------------
# Beispielantworten -- bewusst in Formen, die FuPa so nicht liefern muss
# ---------------------------------------------------------------------------

TABELLE = [
    {"place": nr, "teamName": name, "matches": 3, "wins": w, "draws": 0,
     "losses": 3 - w, "goalsFor": 3 * w, "goalsAgainst": 3, "points": 3 * w}
    for nr, (name, w) in enumerate(
        [("Joshofen-B.", 3), ("Wörnitzstein", 2), ("SG Alerheim", 2),
         ("TSV Meitingen", 1), ("Türk Gücü Lauingen", 0)], 1)
]

TORJAEGER = [
    {"rank": 1, "name": "C. Hollinger", "club": "Joshofen-B.", "goals": 5},
    {"rank": 2, "name": "F. Moll", "club": "Wörnitzstein", "goals": 4},
    {"rank": 3, "name": "F. Veit", "club": "SG Alerheim", "goals": 3},
]

KADER = [
    {"name": "Dominik Marks", "appearances": 3, "goals": 0, "minutes": 240,
     "yellowCards": 1, "subIn": 0, "subOut": 1},
    {"name": "Julian Schmidbaur", "appearances": 3, "goals": 2, "minutes": 270,
     "yellowCards": 0, "subIn": 0, "subOut": 0},
]

SPIELPLAN = [
    {"homeTeam": {"name": "Türk Gücü Lauingen"},
     "awayTeam": {"name": "SV Wörnitzstein-Berg"},
     "kickoff": "2026-07-26T15:00:00", "homeGoals": 0, "awayGoals": 4,
     "competition": {"name": "Bezirksliga Schwaben Nord"}},
    {"homeTeam": {"name": "SV Wörnitzstein-Berg"},
     "awayTeam": {"name": "TSV Meitingen"},
     "kickoff": "2026-07-29T18:30:00", "homeGoals": 2, "awayGoals": 1,
     "competition": {"name": "Bezirksliga Schwaben Nord"}},
    {"homeTeam": {"name": "SV Wörnitzstein-Berg"},
     "awayTeam": {"name": "SG Alerheim"},
     "kickoff": "2026-08-09T15:00:00",
     "competition": {"name": "Bezirksliga Schwaben Nord"},
     "venue": {"name": "Sportgelände Wörnitzstein"}},
]


def _teamseite() -> str:
    """Eine Seite, wie sie ein Next.js-Auftritt ausliefert: alles im HTML."""
    daten = {"props": {"pageProps": {
        "standings": TABELLE, "topScorers": TORJAEGER,
        "squad": KADER, "fixtures": SPIELPLAN}}}
    return ('<!DOCTYPE html><html><body><div id="__next"></div>'
            '<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(daten) + "</script></body></html>")


class Antwort:
    """Das Wenige, was der Code von einer requests-Antwort braucht."""

    def __init__(self, text: str = "", status: int = 200,
                 typ: str = "text/html; charset=utf-8") -> None:
        self.text = text
        self.status_code = status
        self.headers = {"Content-Type": typ}
        self.content = text.encode("utf-8")

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    def json(self):
        return json.loads(self.text)


def _quelle(konfiguration: Konfiguration, antworten: dict[str, Antwort],
            protokoll: list[str] | None = None) -> FupaApiQuelle:
    """FuPa-Quelle, deren HTTP-Teil aus einer Tabelle bedient wird."""
    quelle = FupaApiQuelle(konfiguration)
    quelle.client.cache.aktiv = False

    def abrufen(url: str) -> Antwort:
        if protokoll is not None:
            protokoll.append(url)
        if url not in antworten:
            return Antwort("Nicht gefunden", status=404)
        return antworten[url]

    quelle.client.abrufen = abrufen        # type: ignore[method-assign]
    return quelle


@pytest.fixture
def herren1(konfiguration: Konfiguration):
    return konfiguration.mannschaft("herren1")


# ---------------------------------------------------------------------------
# Adressliste
# ---------------------------------------------------------------------------

def test_adressliste_beginnt_mit_konfigurierten_endpunkten(
        konfiguration: Konfiguration, herren1):
    from stadionheft.sources.fupa_api import FupaClient

    adressen = adressen_fuer(FupaClient(konfiguration), herren1)
    assert adressen[0].startswith("https://api.fupa.net/v1/teams/")
    assert herren1.fupa_team_url in adressen
    # Jede Standardadresse ist enthalten, keine doppelt
    for muster in KANDIDATEN:
        assert muster.format(slug=herren1.fupa_slug) in adressen
    assert len(adressen) == len(set(adressen))


def test_zusatzadressen_aus_der_konfiguration(konfiguration: Konfiguration,
                                              herren1):
    from stadionheft.sources.fupa_api import FupaClient

    konfiguration.roh["datenquelle"]["fupa"]["zusatz_adressen"] = [
        "https://beispiel.test/{slug}/alles"]
    adressen = adressen_fuer(FupaClient(konfiguration), herren1)
    assert f"https://beispiel.test/{herren1.fupa_slug}/alles" in adressen


# ---------------------------------------------------------------------------
# Erkennen aus einer HTML-Seite
# ---------------------------------------------------------------------------

def test_teamseite_liefert_alles_auf_einmal(konfiguration: Konfiguration, herren1):
    protokoll: list[str] = []
    quelle = _quelle(konfiguration, {herren1.fupa_team_url: Antwort(_teamseite())},
                     protokoll)
    daten = quelle.hole(herren1)

    assert [z.mannschaft for z in daten.tabelle][:2] == ["Joshofen-B.", "Wörnitzstein"]
    assert daten.tabelle[1].eigene is True
    assert daten.torjaeger[0].spieler == "C. Hollinger"
    assert [s.spieler for s in daten.spieler] == ["Dominik Marks", "Julian Schmidbaur"]
    assert daten.warnungen == []
    # Nach der Teamseite ist alles beisammen -- danach darf nichts mehr geholt
    # werden. Sonst belastet jedes Heft FuPa ohne Grund.
    assert protokoll[-1] == herren1.fupa_team_url


def test_naechstes_spiel_richtet_sich_nach_dem_datum(konfiguration: Konfiguration,
                                                     herren1, monkeypatch):
    """Am 05.08. ist Alerheim das naechste Spiel -- nicht Meitingen."""
    import stadionheft.models as models

    class Festes(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 8, 5, 12, 0)

    monkeypatch.setattr(models, "datetime", Festes)
    quelle = _quelle(konfiguration, {herren1.fupa_team_url: Antwort(_teamseite())})
    daten = quelle.hole(herren1)

    assert daten.naechstes_spiel.gast == "SG Alerheim"
    assert daten.naechstes_spiel.datum == "09.08.2026"
    assert daten.letztes_spiel.gast == "TSV Meitingen"
    assert daten.letztes_spiel.ergebnis == "2:1"


def test_json_schnittstelle_wird_ebenso_verwertet(konfiguration: Konfiguration,
                                                  herren1):
    """Liefert eine Adresse sauberes JSON, braucht es keinen HTML-Umweg."""
    adresse = "https://api.fupa.net/v1/teams/{slug}/standing".format(
        slug=herren1.fupa_slug)
    quelle = _quelle(konfiguration, {
        adresse: Antwort(json.dumps({"standing": TABELLE}),
                         typ="application/json")})
    daten = quelle.hole(herren1)
    assert len(daten.tabelle) == 5


def test_teile_von_mehreren_adressen_werden_zusammengesetzt(
        konfiguration: Konfiguration, herren1):
    slug = herren1.fupa_slug
    quelle = _quelle(konfiguration, {
        f"https://api.fupa.net/v1/teams/{slug}/standing":
            Antwort(json.dumps({"standing": TABELLE}), typ="application/json"),
        f"https://api.fupa.net/v1/teams/{slug}/topscorers":
            Antwort(json.dumps({"scorers": TORJAEGER}), typ="application/json"),
        f"https://www.fupa.net/team/{slug}/kader":
            Antwort(json.dumps({"squad": KADER}), typ="application/json"),
        f"https://www.fupa.net/team/{slug}/spielplan":
            Antwort(json.dumps({"matches": SPIELPLAN}), typ="application/json"),
    })
    daten = quelle.hole(herren1)
    assert len(daten.tabelle) == 5
    assert len(daten.torjaeger) == 3
    assert len(daten.spieler) == 2
    assert daten.naechstes_spiel is not None
    assert daten.warnungen == []


def test_laengere_liste_setzt_sich_durch(konfiguration: Konfiguration, herren1):
    """Eine Kurzfassung auf der ersten Seite darf die Volltabelle nicht blockieren."""
    slug = herren1.fupa_slug
    quelle = _quelle(konfiguration, {
        f"https://api.fupa.net/v1/teams/{slug}":
            Antwort(json.dumps({"standing": TABELLE[:3]}), typ="application/json"),
        f"https://www.fupa.net/team/{slug}/tabelle":
            Antwort(json.dumps({"standing": TABELLE}), typ="application/json"),
    })
    daten = quelle.hole(herren1)
    assert len(daten.tabelle) == 5


# ---------------------------------------------------------------------------
# Wenn etwas fehlt oder schiefgeht
# ---------------------------------------------------------------------------

def test_fehlende_teile_werden_gemeldet(konfiguration: Konfiguration, herren1):
    slug = herren1.fupa_slug
    quelle = _quelle(konfiguration, {
        f"https://www.fupa.net/team/{slug}/tabelle":
            Antwort(json.dumps({"standing": TABELLE}), typ="application/json")})
    daten = quelle.hole(herren1)

    assert len(daten.tabelle) == 5
    assert daten.torjaeger == []
    assert len(daten.warnungen) == 1
    warnung = daten.warnungen[0]
    for fehlend in ("Torschützenliste", "Spielerstatistik", "nächste Spiel"):
        assert fehlend in warnung
    assert "Tabelle" not in warnung


def test_alle_adressen_leer_ist_kein_absturz(konfiguration: Konfiguration, herren1):
    """404 ueberall: Das Heft entsteht trotzdem, nur mit leeren Seiten."""
    quelle = _quelle(konfiguration, {})
    daten = quelle.hole(herren1)
    assert daten.tabelle == [] and daten.naechstes_spiel is None
    assert daten.warnungen and "FuPa" in daten.warnungen[0]


def test_netzausfall_wird_durchgereicht(konfiguration: Konfiguration, herren1):
    quelle = FupaApiQuelle(konfiguration)
    quelle.client.cache.aktiv = False

    def kaputt(url: str):
        raise DatenquelleNichtErreichbarFehler(
            f"{url}: kein Netz", benutzer_text="FuPa ist nicht erreichbar.")

    quelle.client.abrufen = kaputt        # type: ignore[method-assign]
    with pytest.raises(DatenquelleNichtErreichbarFehler):
        quelle.hole(herren1)


def test_netzausfall_bricht_nach_wenigen_versuchen_ab(konfiguration: Konfiguration,
                                                      herren1):
    """Ist das Netz weg, hat es keinen Sinn, alle zehn Adressen abzuwarten."""
    versuche: list[str] = []

    quelle = FupaApiQuelle(konfiguration)
    quelle.client.cache.aktiv = False

    def kaputt(url: str):
        versuche.append(url)
        raise DatenquelleNichtErreichbarFehler("kein Netz",
                                               benutzer_text="nicht erreichbar")

    quelle.client.abrufen = kaputt        # type: ignore[method-assign]
    with pytest.raises(DatenquelleNichtErreichbarFehler):
        quelle.hole(herren1)
    assert len(versuche) == 3


def test_abweisung_durch_fupa_stoppt_nicht_die_uebrigen_adressen(
        konfiguration: Konfiguration, herren1):
    """Eine 403-Antwort auf die API darf die oeffentliche Seite nicht verhindern."""
    slug = herren1.fupa_slug
    antworten = {
        f"https://api.fupa.net/v1/teams/{slug}": Antwort("", status=403),
        herren1.fupa_team_url: Antwort(_teamseite()),
    }
    quelle = _quelle(konfiguration, antworten)
    daten = quelle.hole(herren1)
    assert len(daten.tabelle) == 5


def test_ohne_fupa_link_klare_ansage(konfiguration: Konfiguration):
    mannschaft = konfiguration.mannschaft("herren1")
    mannschaft.fupa_team_url = ""
    quelle = _quelle(konfiguration, {})
    with pytest.raises(DatenNichtLesbarFehler) as fehler:
        quelle.hole(mannschaft)
    assert "FuPa-Link" in fehler.value.benutzer_text


def test_hoechstens_so_viele_abrufe_wie_erlaubt(konfiguration: Konfiguration,
                                                herren1):
    protokoll: list[str] = []
    quelle = _quelle(konfiguration, {}, protokoll)
    quelle.max_abrufe = 2
    quelle.hole(herren1)
    assert len(protokoll) == 2


def test_robots_gilt_je_host(konfiguration: Konfiguration):
    """api.fupa.net und www.fupa.net sind verschiedene Server.

    Frueher wurde die zuerst gelesene robots.txt auf alle Adressen angewandt --
    ein Verbot der API haette damit auch die oeffentliche Seite gesperrt.
    """
    import urllib.robotparser

    from stadionheft.sources.fupa_api import FupaClient

    client = FupaClient(konfiguration)

    def regeln(text: str):
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(text.splitlines())
        return parser

    client._robots = {
        "api.fupa.net": regeln("User-agent: *\nDisallow: /"),
        "www.fupa.net": regeln("User-agent: *\nDisallow: /admin"),
    }
    assert client._robots_erlaubt("https://api.fupa.net/v1/teams/x") is False
    assert client._robots_erlaubt("https://www.fupa.net/team/x") is True


# ---------------------------------------------------------------------------
# Antwort zerlegen
# ---------------------------------------------------------------------------

def test_nutzlasten_aus_json_antwort():
    bloecke = _nutzlasten_aus(Antwort(json.dumps({"a": 1}), typ="application/json"))
    assert bloecke == [{"a": 1}]


def test_nutzlasten_aus_falsch_deklariertem_json():
    """Manche Server melden text/plain und liefern trotzdem JSON."""
    bloecke = _nutzlasten_aus(Antwort(json.dumps({"a": 1}), typ="text/plain"))
    assert bloecke == [{"a": 1}]


def test_nutzlasten_aus_html_antwort():
    bloecke = _nutzlasten_aus(Antwort(_teamseite()))
    assert bloecke and any(isinstance(b, dict) for b in bloecke)


def test_nutzlasten_aus_leerer_antwort():
    assert _nutzlasten_aus(Antwort("")) == []


def test_nutzlasten_aus_kaputtem_json():
    assert _nutzlasten_aus(Antwort("{kaputt", typ="application/json")) == []


# ---------------------------------------------------------------------------
# Diagnose
# ---------------------------------------------------------------------------

def test_probe_berichtet_was_erkannt_wurde(konfiguration: Konfiguration,
                                           monkeypatch, tmp_path):
    from stadionheft.sources import fupa_api

    team_url = konfiguration.mannschaft("herren1").fupa_team_url

    def abrufen(self, url: str):
        return Antwort(_teamseite()) if url == team_url else Antwort("", status=404)

    monkeypatch.setattr(fupa_api.FupaClient, "abrufen", abrufen)
    bericht = probe_fupa(konfiguration, "herren1", tmp_path)

    assert bericht["geprueft"] >= len(KANDIDATEN)
    treffer = [e for e in bericht["ergebnisse"].values() if e["bewertung"] == "ok"]
    assert len(treffer) == 1
    assert treffer[0]["erkannt"]["tabelle"] == 5
    assert bericht["zusammenfassung"] == {
        "tabelle": 5, "torjaeger": 3, "spieler": 2, "spiele": 3}

    # Die Rohantwort muss auf der Platte liegen -- sie ist der Zweck der Uebung
    abgelegt = list((tmp_path / "fupa_probe").glob("*.json"))
    assert any(d.name == "_bericht.json" for d in abgelegt)
    assert len(abgelegt) == 2

    # ... und daneben eine Fassung, die man ohne Werkzeug lesen kann
    text = (tmp_path / "fupa_probe" / "_bericht.txt").read_text(encoding="utf-8")
    assert "Tabelle            gefunden (5 Zeilen)" in text
    assert "Alles Nötige wird gefunden" in text


def test_berichtstext_benennt_das_fehlende(konfiguration: Konfiguration,
                                           monkeypatch, tmp_path):
    """Wer den Test ueber den Aufgabenplaner startet, liest nur diese Datei."""
    from stadionheft.sources import fupa_api

    monkeypatch.setattr(fupa_api.FupaClient, "abrufen",
                        lambda self, url: Antwort("", status=404))
    bericht = probe_fupa(konfiguration, "herren1", tmp_path)
    text = fupa_api.bericht_als_text(bericht)
    assert "Tabelle            NICHT gefunden" in text
    assert "keine Spieldaten an" in text


def test_probe_haelt_fehler_aus(konfiguration: Konfiguration, monkeypatch, tmp_path):
    from stadionheft.sources import fupa_api

    def kaputt(self, url: str):
        raise DatenquelleNichtErreichbarFehler("kein Netz",
                                               benutzer_text="nicht erreichbar")

    monkeypatch.setattr(fupa_api.FupaClient, "abrufen", kaputt)
    bericht = probe_fupa(konfiguration, "herren1", tmp_path)
    assert bericht["zusammenfassung"] == {}
    assert all("nicht erreichbar" in e["bewertung"]
               for e in bericht["ergebnisse"].values())
