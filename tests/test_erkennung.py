"""Strukturerkennung: findet die Daten unabhaengig von Feldnamen und Verpackung.

Die Testdaten bilden mehrere plausible Formen nach, in denen eine
Fussball-Schnittstelle ihre Daten liefern koennte -- englisch, deutsch,
flach, verschachtelt. Keiner davon ist FuPas echtes Format; genau das ist der
Punkt: Die Erkennung darf nicht davon abhaengen, eines davon zu kennen.
"""

from __future__ import annotations

from stadionheft.sources.erkennung import (spiele_erkennen, spieler_erkennen,
                                           tabelle_erkennen, torjaeger_erkennen)

# ---------------------------------------------------------------------------
# Tabelle
# ---------------------------------------------------------------------------

TABELLE_ENGLISCH_FLACH = {
    "data": {
        "standings": [
            {"place": 1, "teamName": "Joshofen-B.", "matches": 1, "wins": 1,
             "draws": 0, "losses": 0, "goalsFor": 5, "goalsAgainst": 0, "points": 3},
            {"place": 2, "teamName": "Wörnitzstein", "matches": 1, "wins": 1,
             "draws": 0, "losses": 0, "goalsFor": 4, "goalsAgainst": 0, "points": 3},
            {"place": 3, "teamName": "Dinkelscher.", "matches": 1, "wins": 1,
             "draws": 0, "losses": 0, "goalsFor": 3, "goalsAgainst": 1, "points": 3},
        ]
    }
}

TABELLE_VERSCHACHTELT = {
    "props": {"pageProps": {"table": {"rows": [
        {"rank": 1, "team": {"name": "Joshofen-B.", "id": 7}, "played": 1,
         "won": 1, "drawn": 0, "lost": 0, "scored": 5, "conceded": 0, "pts": 3},
        {"rank": 2, "team": {"name": "Wörnitzstein", "id": 3}, "played": 1,
         "won": 1, "drawn": 0, "lost": 0, "scored": 4, "conceded": 0, "pts": 3},
        {"rank": 3, "team": {"name": "Alerheim", "id": 9}, "played": 1,
         "won": 1, "drawn": 0, "lost": 0, "scored": 4, "conceded": 3, "pts": 3},
    ]}}}
}

TABELLE_DEUTSCH = {"tabelle": [
    {"platz": 1, "verein": "Joshofen-B.", "spiele": 1, "siege": 1,
     "unentschieden": 0, "niederlagen": 0, "tore": 5, "gegentore": 0, "punkte": 3},
    {"platz": 2, "verein": "Wörnitzstein", "spiele": 1, "siege": 1,
     "unentschieden": 0, "niederlagen": 0, "tore": 4, "gegentore": 0, "punkte": 3},
]}


def test_tabelle_englisch_flach():
    zeilen = tabelle_erkennen(TABELLE_ENGLISCH_FLACH, "SV Wörnitzstein-Berg")
    assert len(zeilen) == 3
    assert zeilen[0].mannschaft == "Joshofen-B."
    assert zeilen[0].punkte == 3
    assert zeilen[1].torverhaeltnis == "4:0"
    assert zeilen[1].eigene is True


def test_tabelle_verschachtelt_mit_teamobjekt():
    zeilen = tabelle_erkennen(TABELLE_VERSCHACHTELT, "SV Wörnitzstein-Berg")
    assert len(zeilen) == 3
    assert zeilen[1].mannschaft == "Wörnitzstein"
    assert zeilen[1].eigene is True
    assert zeilen[2].differenz == 1


def test_tabelle_deutsche_feldnamen():
    zeilen = tabelle_erkennen(TABELLE_DEUTSCH)
    assert len(zeilen) == 2
    assert zeilen[0].bilanz == "1-0-0"


def test_tabelle_ohne_platzfeld_wird_durchnummeriert():
    zeilen = tabelle_erkennen({"x": [
        {"name": "A", "points": 9, "wins": 3, "losses": 0},
        {"name": "B", "points": 6, "wins": 2, "losses": 1},
    ]})
    assert [z.platz for z in zeilen] == [1, 2]


def test_kein_tabellenfund_bei_unpassenden_daten():
    assert tabelle_erkennen({"news": [
        {"title": "Bericht", "text": "lang"},
        {"title": "Vorschau", "text": "kurz"},
    ]}) == []


def test_leere_eingaben():
    assert tabelle_erkennen({}) == []
    assert tabelle_erkennen(None) == []
    assert torjaeger_erkennen([]) == []


# ---------------------------------------------------------------------------
# Torschuetzen
# ---------------------------------------------------------------------------

TORJAEGER = {"scorers": [
    {"position": 1, "player": {"firstName": "C.", "lastName": "Hollinger"},
     "team": {"name": "Joshofen-B."}, "goals": 3, "assists": 1, "matches": 1},
    {"position": 2, "player": {"firstName": "F.", "lastName": "Moll"},
     "team": {"name": "Wörnitzstein"}, "goals": 2, "assists": 2, "matches": 1},
    {"position": 3, "player": {"firstName": "F.", "lastName": "Veit"},
     "team": {"name": "Alerheim"}, "goals": 2, "assists": 1, "matches": 1},
]}


def test_torjaeger_mit_getrennten_namensfeldern():
    zeilen = torjaeger_erkennen(TORJAEGER, "SV Wörnitzstein-Berg")
    assert len(zeilen) == 3
    assert zeilen[0].spieler == "C. Hollinger"
    assert zeilen[0].tore == 3
    assert zeilen[1].eigene is True
    assert zeilen[1].vorlagen == 2


def test_torjaeger_nicht_mit_spielerstatistik_verwechseln():
    """Beide haben Spieler und Tore -- die Statistik hat aber Einsatzdaten."""
    gemischt = {
        "topscorers": [
            {"rank": 1, "name": "A. Spieler", "club": "FC X", "goals": 7},
            {"rank": 2, "name": "B. Spieler", "club": "FC Y", "goals": 5},
        ],
        "squad": [
            {"name": "C. Spieler", "appearances": 12, "goals": 1,
             "minutes": 900, "yellowCards": 2, "subIn": 3, "subOut": 4},
            {"name": "D. Spieler", "appearances": 10, "goals": 0,
             "minutes": 700, "yellowCards": 0, "subIn": 1, "subOut": 2},
        ],
    }
    torjaeger = torjaeger_erkennen(gemischt)
    spieler = spieler_erkennen(gemischt)
    assert [z.spieler for z in torjaeger] == ["A. Spieler", "B. Spieler"]
    assert [z.spieler for z in spieler] == ["C. Spieler", "D. Spieler"]


# ---------------------------------------------------------------------------
# Spielerstatistik
# ---------------------------------------------------------------------------

SPIELER = {"players": [
    {"name": "Dominik Marks", "matches": 1, "goals": 0, "assists": 0,
     "penalties": "0/0", "yellowCards": 0, "yellowRedCards": 0, "redCards": 0,
     "substitutedIn": 0, "substitutedOut": 1, "minutes": 68},
    {"name": "Julian Schmidbaur", "matches": 1, "goals": 1, "assists": 0,
     "penalties": "1/1", "yellowCards": 0, "yellowRedCards": 0, "redCards": 0,
     "substitutedIn": 0, "substitutedOut": 0, "minutes": 90},
]}


def test_spielerstatistik_mit_elfmeterangabe():
    zeilen = spieler_erkennen(SPIELER)
    assert len(zeilen) == 2
    assert zeilen[0].minuten == 68
    assert zeilen[1].elfmeter == "1/1"
    assert zeilen[1].tore == 1


def test_spielerstatistik_deutsche_felder():
    zeilen = spieler_erkennen({"kader": [
        {"spieler": "A", "spiele": 5, "tore": 2, "minuten": 300, "gelb": 1},
        {"spieler": "B", "spiele": 3, "tore": 0, "minuten": 180, "gelb": 0},
    ]})
    assert [z.spieler for z in zeilen] == ["A", "B"]
    assert zeilen[0].minuten == 300


# ---------------------------------------------------------------------------
# Spielplan
# ---------------------------------------------------------------------------

SPIELPLAN = {"matches": [
    {"homeTeam": {"name": "Türk Gücü Lauingen"},
     "awayTeam": {"name": "SV Wörnitzstein-Berg"},
     "kickoff": "2026-07-26T15:00:00Z", "homeGoals": 0, "awayGoals": 4,
     "competition": {"name": "Bezirksliga Schwaben Nord"}},
    {"homeTeam": {"name": "SV Wörnitzstein-Berg"},
     "awayTeam": {"name": "TSV Meitingen"},
     "kickoff": "2026-07-29T18:30:00Z",
     "competition": {"name": "Bezirksliga Schwaben Nord"},
     "venue": {"name": "Sportgelände Wörnitzstein"}},
    {"homeTeam": {"name": "SV Wörnitzstein-Berg"},
     "awayTeam": {"name": "SG Alerheim"},
     "kickoff": "2026-08-09T15:00:00Z",
     "competition": {"name": "Bezirksliga Schwaben Nord"}},
]}


def test_spielplan_erkennen():
    spiele = spiele_erkennen(SPIELPLAN, "SV Wörnitzstein-Berg")
    assert len(spiele) == 3
    assert spiele[0].heimspiel is False
    assert spiele[0].ergebnis == "0:4"
    assert spiele[1].heimspiel is True
    assert spiele[1].datum == "29.07.2026"
    assert spiele[1].spielort == "Sportgelände Wörnitzstein"
    assert spiele[2].gegner == "SG Alerheim"


def test_spielplan_mit_deutschem_datumsformat():
    spiele = spiele_erkennen({"spiele": [
        {"heim": "A", "gast": "B", "datum": "09.08.2026 15:00"},
        {"heim": "C", "gast": "D", "datum": "16.08.2026 15:00"},
    ]})
    assert spiele[0].datum == "09.08.2026"
    assert spiele[0].uhrzeit == "15:00 Uhr"


def test_unlesbares_datum_bricht_nichts():
    spiele = spiele_erkennen({"spiele": [
        {"heim": "A", "gast": "B", "datum": "demnächst"},
        {"heim": "C", "gast": "D", "datum": "demnächst"},
    ]})
    assert len(spiele) == 2
    assert spiele[0].anstoss == ""


# ---------------------------------------------------------------------------
# Alles in einer Antwort
# ---------------------------------------------------------------------------

def test_eine_antwort_mit_allem():
    """Realistischer Fall: eine Seite liefert alles auf einmal."""
    alles = {
        "props": {"pageProps": {
            "team": {"name": "SV Wörnitzstein-Berg"},
            "standings": TABELLE_ENGLISCH_FLACH["data"]["standings"],
            "topScorers": TORJAEGER["scorers"],
            "squad": SPIELER["players"],
            "fixtures": SPIELPLAN["matches"],
        }}
    }
    assert len(tabelle_erkennen(alles, "SV Wörnitzstein-Berg")) == 3
    assert len(torjaeger_erkennen(alles)) == 3
    assert len(spieler_erkennen(alles)) == 2
    assert len(spiele_erkennen(alles, "SV Wörnitzstein-Berg")) == 3


def test_laengere_tabelle_gewinnt():
    """Steckt eine Kurzfassung und eine Volltabelle drin, gewinnt die lange."""
    daten = {
        "vorschau": [
            {"name": "A", "points": 9, "wins": 3, "losses": 0},
            {"name": "B", "points": 6, "wins": 2, "losses": 1},
        ],
        "voll": [
            {"name": f"Team {i}", "points": 20 - i, "wins": 6, "losses": i}
            for i in range(10)
        ],
    }
    assert len(tabelle_erkennen(daten)) == 10
