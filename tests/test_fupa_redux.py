"""Die oeffentlichen FuPa-Seiten, so wie sie heute wirklich aussehen.

Grundlage ist ein echter Abruf vom 05.10.2026 (Herren 1, Saison 2026/27),
auf das Noetige gekuerzt: FuPa liefert jede Seite als HTML mit einem
eingebetteten ``window.REDUX_DATA``. Die Feldnamen unten sind FuPas eigene --
genau an ihnen ist die Erkennung bisher gescheitert:

* Kader: ``firstName``/``lastName`` statt eines gemeinsamen Namensfelds.
* Vereinsnamen als Objekt ``{"full": ..., "middle": ..., "short": ...}``.
* Torjaeger: Tore unter ``statistics.goals`` statt ``goals``.
* Spielplan: ``homeGoal``/``awayGoal`` (Einzahl).
* Tabelle: ``ownGoals``/``againstGoals``.

Und davor: Die per robots.txt gesperrten api.fupa.net-Adressen galten als
Netzfehler -- drei davon am Anfang der Liste beendeten den Abruf, bevor die
erlaubte Teamseite ueberhaupt an der Reihe war.
"""

from __future__ import annotations

import json
import urllib.robotparser

import pytest

from stadionheft.config import Konfiguration
from stadionheft.errors import AdresseGesperrtFehler
from stadionheft.sources.erkennung import (spiele_erkennen, spieler_erkennen,
                                           tabelle_erkennen, torjaeger_erkennen)
from stadionheft.models import Spiel
from stadionheft.sources.fupa_api import (FupaApiQuelle, FupaClient,
                                          _besserer_spielplan, liga_adressen)
from stadionheft.sources.ics_daten import spiele_aus_ics
from stadionheft.sources.html_daten import json_aus_html

SVW = "SV Wörnitzstein-Berg"
LIGA = "bezirksliga-schwaben-nord"


def _verein(name: str, slug: str) -> dict:
    return {"slug": f"{slug}-m1-2026-27",
            "name": {"full": name, "middle": name.split()[-1], "short": "X"},
            "linkUrl": f"/team/{slug}-m1-2026-27",
            "club": {"name": name, "slug": slug}}


WETTBEWERB = {"slug": LIGA, "name": "Bezirksliga Schwaben Nord",
              "season": {"slug": "2026-27", "name": "26/27"},
              "category": {"id": 1, "name": "Liga"}}

TEAMSEITE = {"dataHistory": [{
    "key": "undefined",
    "TeamPage": {"slug": "sv-woernitzstein-berg-m1-2026-27",
                 "name": {"full": SVW, "middle": "Wörnitzstein"},
                 "competition": WETTBEWERB},
    "TeamPlayersPage": {"data": {"players": [
        # Trikotfolge, nicht nach Toren -- wie bei FuPa
        {"id": 1, "firstName": "Robin", "lastName": "Klinger",
         "position": "Torwart", "jerseyNumber": 95,
         "matches": 0, "goals": 0, "assists": 0},
        {"id": 2, "firstName": "Florian", "lastName": "Moll",
         "position": "Mittelfeld", "jerseyNumber": 8,
         "matches": 12, "goals": 4, "assists": 6},
        {"id": 3, "firstName": "Sandro", "lastName": "Scherl",
         "position": "Abwehr", "jerseyNumber": 4,
         "matches": 11, "goals": 0, "assists": 0},
        {"id": 4, "firstName": "Julian", "lastName": "Schmidbaur",
         "position": "Sturm", "jerseyNumber": 9,
         "matches": 12, "goals": 5, "assists": 1},
    ], "coaches": [], "info": {}}},
}]}

SPIELPLANSEITE = {"dataHistory": [{
    "key": "undefined",
    "TeamPage": TEAMSEITE["dataHistory"][0]["TeamPage"],
    "TeamMatchesPage": {"items": [
        {"homeTeam": _verein(SVW, "sv-woernitzstein-berg"),
         "awayTeam": _verein("FC Horgau", "fc-horgau"),
         "kickoff": "2026-10-02T19:00:00+02:00", "homeGoal": 4, "awayGoal": 2,
         "competition": WETTBEWERB},
        {"homeTeam": _verein("SG Alerheim", "sg-alerheim"),
         "awayTeam": _verein(SVW, "sv-woernitzstein-berg"),
         "kickoff": "2026-10-11T15:00:00+02:00", "homeGoal": None,
         "awayGoal": None,
         # Ein Pokalspiel darf die Liga nicht verdraengen
         "competition": {"slug": "toto-pokal-schwaben", "name": "Toto-Pokal",
                         "category": {"name": "Pokal"}}},
    ], "nextUrl": None, "isFetching": False},
}]}

TABELLENSEITE = {"dataHistory": [{
    "key": "undefined",
    "LeagueStandingPage": {"total": [
        {"rank": 1, "matches": 12, "wins": 8, "draws": 2, "defeats": 2,
         "ownGoals": 33, "againstGoals": 12, "points": 26,
         "team": _verein("SpVgg Joshofen-Bergheim", "spvgg-joshofen-bergheim")},
        {"rank": 2, "matches": 12, "wins": 6, "draws": 2, "defeats": 4,
         "ownGoals": 25, "againstGoals": 20, "points": 20,
         "team": _verein(SVW, "sv-woernitzstein-berg")},
        {"rank": 3, "matches": 12, "wins": 5, "draws": 2, "defeats": 5,
         "ownGoals": 18, "againstGoals": 22, "points": 17,
         "team": _verein("SG Alerheim", "sg-alerheim")},
    ]},
}]}

TORJAEGERSEITE = {"dataHistory": [{
    "key": "undefined",
    "LeagueScorersPage": {"scorers": [
        {"player": {"firstName": "Sebastian", "lastName": "Hertle"},
         "team": _verein("SG Alerheim", "sg-alerheim"),
         "statistics": {"matches": 11, "goals": 12, "assists": 6,
                        "yellowCard": 2, "minutes": 990}},
        {"player": {"firstName": "Manuel", "lastName": "Utz"},
         "team": _verein("BC Rinnenthal", "bc-rinnenthal"),
         "statistics": {"matches": 12, "goals": 11, "assists": 5,
                        "yellowCard": 0, "minutes": 1080}},
        {"player": {"firstName": "Julian", "lastName": "Schmidbaur"},
         "team": _verein(SVW, "sv-woernitzstein-berg"),
         "statistics": {"matches": 12, "goals": 5, "assists": 1,
                        "yellowCard": 1, "minutes": 1020}},
    ]},
}]}


def _html(redux: dict) -> str:
    return ("<!DOCTYPE html><html><body><div id=\"root\"></div><script>"
            "window.REDUX_DATA = " + json.dumps(redux, ensure_ascii=False)
            + ";</script></body></html>")


def _bloecke(redux: dict) -> list:
    return list(json_aus_html(_html(redux)))


def _erste(funktion, redux: dict, *args) -> list:
    for block in _bloecke(redux):
        gefunden = funktion(block, *args)
        if gefunden:
            return gefunden
    return []


# ---------------------------------------------------------------------------
# Erkennung
# ---------------------------------------------------------------------------

def test_kader_mit_vor_und_nachname_wird_spielerstatistik():
    spieler = _erste(spieler_erkennen, TEAMSEITE)
    assert [s.spieler for s in spieler] == [
        "Robin Klinger", "Florian Moll", "Sandro Scherl", "Julian Schmidbaur"]
    assert spieler[1].spiele == 12 and spieler[1].tore == 4


def test_kader_als_torjaegerliste_nach_toren_ohne_nullen():
    """Fehlt die Ligaliste, taugt der Kader -- aber erst sortiert."""
    schuetzen = _erste(torjaeger_erkennen, TEAMSEITE, SVW)
    assert [(t.platz, t.spieler, t.tore) for t in schuetzen] == [
        (1, "Julian Schmidbaur", 5), (2, "Florian Moll", 4)]


def test_kader_ohne_jedes_tor_ist_keine_torjaegerliste():
    """Damen 1: FuPa fuehrt im Kader keine Tore. 31 Nullen haetten sonst die
    25 Eintraege der Ligaliste verdraengt -- die laengere Liste gewinnt."""
    kader = json.loads(json.dumps(TEAMSEITE))
    for spieler in kader["dataHistory"][0]["TeamPlayersPage"]["data"]["players"]:
        spieler["goals"] = 0
    assert _erste(torjaeger_erkennen, kader, SVW) == []
    assert len(_erste(spieler_erkennen, kader)) == 4


def test_ligaweite_torjaegerliste_mit_statistik_unterobjekt():
    schuetzen = _erste(torjaeger_erkennen, TORJAEGERSEITE, SVW)
    assert [(t.spieler, t.mannschaft, t.tore) for t in schuetzen] == [
        ("Sebastian Hertle", "SG Alerheim", 12),
        ("Manuel Utz", "BC Rinnenthal", 11),
        ("Julian Schmidbaur", SVW, 5)]
    assert [t.eigene for t in schuetzen] == [False, False, True]


def test_ligaweite_torjaegerliste_ist_kein_kader():
    """Spieler mehrerer Vereine waeren als eigene Spielerstatistik falsch."""
    assert _erste(spieler_erkennen, TORJAEGERSEITE) == []


def test_ligatabelle_mit_vereinsobjekten_und_eigenen_toren():
    tabelle = _erste(tabelle_erkennen, TABELLENSEITE, SVW)
    eigene = [z for z in tabelle if z.eigene]
    assert len(tabelle) == 3 and len(eigene) == 1
    assert (eigene[0].platz, eigene[0].mannschaft, eigene[0].punkte,
            eigene[0].tore, eigene[0].gegentore) == (2, SVW, 20, 25, 20)


def test_ligatabelle_ist_kein_kader():
    assert _erste(spieler_erkennen, TABELLENSEITE) == []


def test_spielplan_mit_vereinsobjekten_und_tor_in_einzahl():
    spiele = _erste(spiele_erkennen, SPIELPLANSEITE, SVW)
    assert [(s.heim, s.gast, s.ergebnis, s.heimspiel) for s in spiele] == [
        (SVW, "FC Horgau", "4:2", True),
        ("SG Alerheim", SVW, "", False)]
    assert spiele[1].heim_kennung == "sg-alerheim-m1-2026-27"


# ---------------------------------------------------------------------------
# Ligaseiten finden
# ---------------------------------------------------------------------------

def test_folgeseiten_der_teamseite():
    """Tabelle und Torjaeger der Liga, dann der Spielplan der Mannschaft."""
    assert liga_adressen(_bloecke(TEAMSEITE),
                         "https://www.fupa.net/team/x") == [
        f"https://www.fupa.net/league/{LIGA}/standing",
        f"https://www.fupa.net/league/{LIGA}/scorers",
        "https://www.fupa.net/team/x/matches"]


def test_pokal_verdraengt_die_liga_nicht():
    """Auf der Spielplanseite steht auch der Pokal -- die Liga gewinnt."""
    bloecke = _bloecke({"dataHistory": [{
        "TeamMatchesPage": SPIELPLANSEITE["dataHistory"][0]["TeamMatchesPage"]
    }]})
    # Erste genannte Partie umdrehen: Pokal zuerst
    bloecke[0]["dataHistory"][0]["TeamMatchesPage"]["items"].reverse()
    assert liga_adressen(bloecke, "https://www.fupa.net/team/x/matches") == [
        f"https://www.fupa.net/league/{LIGA}/standing",
        f"https://www.fupa.net/league/{LIGA}/scorers"]


def test_keine_folgeseiten_ohne_daten():
    """Eine 404-Teamseite kostet sonst gleich noch einen Abruf mehr."""
    assert liga_adressen([], "https://www.fupa.net/team/x") == []


def test_ligaseiten_nur_bei_fupa():
    """Eine Vereinsseite mit 'competition' im JSON ist keine FuPa-Seite."""
    assert liga_adressen(_bloecke(TEAMSEITE), "https://www.example.org/") == []


def test_spielplan_mit_kennungen_schlaegt_laengeren_kalender():
    kalender = [Spiel(heim="A", gast=SVW), Spiel(heim=SVW, gast="B"),
                Spiel(heim="C", gast=SVW)]
    teamseite = [Spiel(heim="A", gast=SVW, heim_kennung="a-m1-2026-27",
                       gast_kennung="svw-m1-2026-27")]
    assert _besserer_spielplan(teamseite, kalender) is True
    assert _besserer_spielplan(kalender, teamseite) is False
    # Ohne Unterschied bei den Kennungen gilt weiter: laenger gewinnt
    assert _besserer_spielplan(kalender, kalender[:1]) is True


def test_liga_ist_der_haeufigste_wettbewerb():
    from stadionheft.sources.fupa_api import Fund
    fund = Fund(spiele=[Spiel(wettbewerb="Frauen-Bezirkspokal Schwaben"),
                        Spiel(wettbewerb="Frauen-Bezirksliga Nord"),
                        Spiel(wettbewerb="Frauen-Bezirksliga Nord")])
    assert fund.liga == "Frauen-Bezirksliga Nord"


def test_kalender_ohne_symbol_vor_dem_heimverein():
    """FuPas Kalender stellt jedem Termin ein Fussball-Emoji voran."""
    ics = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\n"
           "DTSTART:20261011T130000Z\r\n"
           "SUMMARY:\u26bd\ufe0f BC Rinnenthal - SV W\u00f6rnitzstein-Berg\r\n"
           "END:VEVENT\r\nEND:VCALENDAR\r\n")
    spiele = spiele_aus_ics(ics)
    assert spiele and spiele[0]["heim"] == "BC Rinnenthal"


# ---------------------------------------------------------------------------
# Der ganze Abruf -- mit echter robots.txt-Pruefung
# ---------------------------------------------------------------------------

class _Antwort:
    def __init__(self, text: str, status: int = 200) -> None:
        self.text = text
        self.status_code = status
        self.headers = {"Content-Type": "text/html; charset=utf-8"}
        self.content = text.encode("utf-8")

    @property
    def ok(self) -> bool:
        return self.status_code < 400


class _Sitzung:
    """Bedient nur www.fupa.net. Ein Abruf bei api.fupa.net ist ein Fehler:
    Dort darf wegen der robots.txt gar nicht erst angefragt werden."""

    def __init__(self, seiten: dict[str, str]) -> None:
        self.seiten = seiten
        self.abgerufen: list[str] = []

    def get(self, url: str, **_kwargs) -> _Antwort:
        assert "api.fupa.net" not in url, f"gesperrte Adresse abgerufen: {url}"
        self.abgerufen.append(url)
        if url in self.seiten:
            return _Antwort(self.seiten[url])
        return _Antwort("Nicht gefunden", status=404)


def _robots(text: str) -> dict:
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(text.splitlines())
    return {"status": 200, "text": text, "regeln": parser,
            "bewertung": "Regeln gelesen"}


def _client_mit_fupa_robots(client: FupaClient, seiten: dict[str, str]) -> _Sitzung:
    """robots.txt wie bei FuPa heute: API gesperrt, Webseite frei."""
    client._robots = {
        "api.fupa.net": _robots("User-agent: *\nAllow: /*.ics$\nDisallow: /"),
        "www.fupa.net": _robots("User-agent: Googlebot\nAllow: /"),
    }
    client.pause = 0
    client.cache.aktiv = False
    sitzung = _Sitzung(seiten)
    client._session = sitzung
    return sitzung


def test_gesperrte_adresse_ist_kein_netzfehler(konfiguration: Konfiguration):
    client = FupaClient(konfiguration)
    _client_mit_fupa_robots(client, {})
    with pytest.raises(AdresseGesperrtFehler):
        client.abrufen("https://api.fupa.net/v1/teams/x/matches")


def test_gesperrte_api_haelt_die_teamseite_nicht_auf(konfiguration: Konfiguration):
    """Der Fehler aus dem Live-Lauf: 'Herren 1 uebersprungen: robots.txt ...'.

    Fuenf gesperrte Endpunkte stehen vor der Teamseite. Sie werden
    uebersprungen, und Teamseite, Spielplan und Ligaseiten liefern alles.
    """
    herren1 = konfiguration.mannschaft("herren1")
    herren1.zusatz_urls = []
    team = herren1.fupa_team_url.rstrip("/")
    quelle = FupaApiQuelle(konfiguration)
    quelle.gegner_abrufen = False
    sitzung = _client_mit_fupa_robots(quelle.client, {
        team: _html(TEAMSEITE),
        f"{team}/matches": _html(SPIELPLANSEITE),
        f"https://www.fupa.net/league/{LIGA}/standing": _html(TABELLENSEITE),
        f"https://www.fupa.net/league/{LIGA}/scorers": _html(TORJAEGERSEITE),
    })

    daten = quelle.hole(herren1)

    assert len(daten.spieler) == 4
    assert len(daten.tabelle) == 3
    assert [t.tore for t in daten.torjaeger] == [12, 11, 5]
    assert len(daten.spiele) == 2
    # Alle Folgeseiten kamen von der Teamseite, keine wurde geraten
    assert sitzung.abgerufen[:4] == [
        team,
        f"https://www.fupa.net/league/{LIGA}/standing",
        f"https://www.fupa.net/league/{LIGA}/scorers",
        f"{team}/matches"]
