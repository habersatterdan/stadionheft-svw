"""Die FuPa-Quelle klappert Adressen ab und erkennt die Daten selbst.

Getestet wird das Zusammenspiel, nicht die Erkennung an sich (die hat
``test_erkennung.py``) und nicht das Auspacken von HTML (``test_html_daten.py``).
Der HTTP-Teil wird ersetzt: Die Tests duerfen nie ins Netz gehen.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

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

def _wann(tage: int) -> str:
    """Ein Anstoss relativ zu heute -- sonst rostet der Test mit dem Kalender."""
    return (datetime.now() + timedelta(days=tage)).replace(
        hour=15, minute=0, second=0, microsecond=0).isoformat()


#: Zwei gespielte Partien, eine kommende. Das naechste Spiel ist damit immer
#: SG Alerheim, egal wann der Test laeuft.
SPIELPLAN = [
    {"homeTeam": {"name": "Türk Gücü Lauingen", "slug": "tuerk-guecue-lauingen"},
     "awayTeam": {"name": "SV Wörnitzstein-Berg", "slug": "svw"},
     "kickoff": _wann(-21), "homeGoals": 0, "awayGoals": 4,
     "competition": {"name": "Bezirksliga Schwaben Nord"}},
    {"homeTeam": {"name": "SV Wörnitzstein-Berg", "slug": "svw"},
     "awayTeam": {"name": "TSV Meitingen", "slug": "tsv-meitingen"},
     "kickoff": _wann(-7), "homeGoals": 2, "awayGoals": 1,
     "competition": {"name": "Bezirksliga Schwaben Nord"}},
    {"homeTeam": {"name": "SV Wörnitzstein-Berg", "slug": "svw"},
     "awayTeam": {"name": "SG Alerheim", "slug": "sg-alerheim"},
     "kickoff": _wann(8),
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
    # Nach der Teamseite ist fuer die eigene Mannschaft alles beisammen --
    # danach wird nur noch der Gegner geholt. Sonst belastet jedes Heft FuPa
    # ohne Grund.
    bis_eigene = protokoll[:protokoll.index(herren1.fupa_team_url) + 1]
    assert len(bis_eigene) <= len(KANDIDATEN) + 1


def test_naechstes_spiel_richtet_sich_nach_dem_datum(konfiguration: Konfiguration,
                                                     herren1):
    """Massgeblich ist das Datum, nicht die Reihenfolge in der Liste.

    Meitingen steht im Spielplan vor Alerheim und hat ein Ergebnis; Alerheim
    liegt in der Zukunft. Also ist Alerheim das naechste Spiel.
    """
    quelle = _quelle(konfiguration, {herren1.fupa_team_url: Antwort(_teamseite())})
    daten = quelle.hole(herren1)

    assert daten.naechstes_spiel.gast == "SG Alerheim"
    assert daten.naechstes_spiel.anstoss_dt > datetime.now()
    assert daten.letztes_spiel.gast == "TSV Meitingen"
    assert daten.letztes_spiel.ergebnis == "2:1"


def test_formkurve_und_bilanz_aus_dem_spielplan(konfiguration: Konfiguration,
                                                herren1):
    """Beides wird gerechnet, nicht geholt -- und passt damit zum Spielplan."""
    quelle = _quelle(konfiguration, {herren1.fupa_team_url: Antwort(_teamseite())})
    daten = quelle.hole(herren1)

    assert "".join(f.ausgang for f in daten.form) == "SS"
    assert daten.bilanz.gesamt.bilanz == "2-0-0"
    assert daten.bilanz.gesamt.torverhaeltnis == "6:1"
    assert daten.bilanz.gesamt.punkte == 6


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
    # Zum Gegner gibt es in dieser Probe keine Seite -- das muss gesagt werden,
    # darf aber den Rest nicht beschaedigen.
    assert daten.warnungen == [
        "Zu SG Alerheim kamen keine Zahlen an - die Gegnerseiten bleiben leer. "
        "Der Rest des Hefts ist davon nicht betroffen."]


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


def test_robots_verbot_wuergt_den_lauf_nicht_ab(konfiguration: Konfiguration,
                                                 herren1):
    """Gesperrte Adressen am Listenanfang duerfen die Teamseite nicht blockieren.

    So ist es in der Praxis: FuPas robots.txt verbietet api.fupa.net, und
    genau diese fuenf Adressen stehen ganz oben. Wurden sie als Netzausfall
    gezaehlt, brach der Abruf nach dreien ab -- bevor die Teamseite, die
    einwandfrei antwortet, ueberhaupt an die Reihe kam.
    """
    from stadionheft.errors import AdresseGesperrtFehler

    quelle = _quelle(konfiguration, {herren1.fupa_team_url: Antwort(_teamseite())})
    attrappe = quelle.client.abrufen        # type: ignore[assignment]

    def abrufen(url: str):
        if "api.fupa.net" in url:
            raise AdresseGesperrtFehler(
                f"robots.txt verbietet den Abruf von {url}.",
                benutzer_text="Gesperrt.")
        return attrappe(url)

    quelle.client.abrufen = abrufen         # type: ignore[method-assign]

    daten = quelle.hole(herren1)
    assert len(daten.tabelle) == 5
    assert daten.naechstes_spiel is not None


def test_nur_gesperrte_adressen_ergibt_klare_meldung(konfiguration: Konfiguration,
                                                     herren1):
    """Ist wirklich alles gesperrt, muss das als solches gemeldet werden."""
    from stadionheft.errors import AdresseGesperrtFehler

    def gesperrt(url: str):
        raise AdresseGesperrtFehler(f"robots.txt verbietet {url}.",
                                    benutzer_text="Gesperrt.")

    quelle = _quelle(konfiguration, {})
    quelle.client.abrufen = gesperrt        # type: ignore[method-assign]

    with pytest.raises(DatenquelleNichtErreichbarFehler) as fehler:
        quelle.hole(herren1)
    assert "verwertbare Antwort" in fehler.value.benutzer_text


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


def test_tote_adressen_werden_im_lauf_uebersprungen(konfiguration: Konfiguration,
                                                    herren1):
    """Was einmal nichts lieferte, wird beim naechsten Mal nicht neu probiert."""
    protokoll: list[str] = []
    quelle = _quelle(konfiguration, {herren1.fupa_team_url: Antwort(_teamseite())},
                     protokoll)

    quelle.hole(herren1)
    erster_lauf = len(protokoll)
    protokoll.clear()

    quelle.hole(herren1)
    assert len(protokoll) < erster_lauf


def test_bewaehrtes_muster_bleibt_fuer_die_naechste_mannschaft(
        konfiguration: Konfiguration):
    """Fehlt die Seite einer Mannschaft, darf das die naechste nicht lahmlegen.

    Sonst reicht eine Mannschaft ohne FuPa-Auftritt, um allen folgenden die
    Daten zu nehmen -- der Fehler faellt erst im fertigen Heft auf.
    """
    herren1 = konfiguration.mannschaft("herren1")
    damen1 = konfiguration.mannschaft("damen1")
    damen1.fupa_team_url = "https://www.fupa.net/team/svw-damen1-2026-27"

    # Nur Herren 1 hat eine Seite. Damen 1 laeuft ins Leere ...
    quelle = _quelle(konfiguration, {herren1.fupa_team_url: Antwort(_teamseite())})
    quelle.hole(herren1)
    leer = quelle.hole(damen1)
    assert leer.tabelle == []

    # ... und danach muss Herren 1 immer noch funktionieren.
    wieder = quelle.hole(herren1)
    assert len(wieder.tabelle) == 5


def test_ohne_uebrige_adresse_wird_doch_alles_probiert(
        konfiguration: Konfiguration, herren1):
    """Lieber ein paar Abrufe zu viel als eine Mannschaft ohne jeden Versuch."""
    protokoll: list[str] = []
    quelle = _quelle(konfiguration, {}, protokoll)
    quelle._tote_muster = {"{slug}"}          # alles als tot markieren
    quelle._tote_muster.update(
        quelle._muster(a, herren1.fupa_slug)
        for a in adressen_fuer(quelle.client, herren1))

    quelle.hole(herren1)
    assert protokoll, "Es wurde gar keine Adresse versucht"


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

    def lage(text: str) -> dict:
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(text.splitlines())
        return {"status": 200, "text": text, "regeln": parser,
                "bewertung": "Regeln gelesen"}

    client._robots = {
        "api.fupa.net": lage("User-agent: *\nDisallow: /"),
        "www.fupa.net": lage("User-agent: *\nDisallow: /admin"),
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


# ---------------------------------------------------------------------------
# robots.txt -- nach RFC 9309, nicht nach Pythons strengerem Standardverhalten
# ---------------------------------------------------------------------------

def _client_mit_robots(konfiguration: Konfiguration, status: int, text: str = ""):
    from stadionheft.sources.fupa_api import FupaClient

    client = FupaClient(konfiguration)
    client.cache.aktiv = False
    typ = "text/plain"
    client._sitzung = lambda: type("S", (), {           # type: ignore[assignment]
        "get": staticmethod(lambda url, **k: Antwort(text, status, typ))})()
    return client


def test_robots_regel_wird_befolgt(konfiguration: Konfiguration):
    client = _client_mit_robots(konfiguration, 200,
                                "User-agent: *\nDisallow: /v1/\n")
    assert client._robots_erlaubt("https://api.fupa.net/v1/teams/x") is False
    assert client._robots_erlaubt("https://api.fupa.net/anderes") is True


def test_robots_403_ist_kein_verbot(konfiguration: Konfiguration):
    """RFC 9309, 2.3.1.4: Bei 4xx gibt es keine Regeln -- also kein Verbot.

    Pythons RobotFileParser sperrt bei 403 alles. Ein API-Host hinter einer
    Schutzschicht antwortet aber gern mit 403 auf /robots.txt, ohne dass
    irgendwo etwas verboten waere. Wir haetten uns selbst ausgesperrt.
    """
    client = _client_mit_robots(konfiguration, 403)
    assert client._robots_erlaubt("https://api.fupa.net/v1/teams/x") is True
    assert "keine Regeln" in client.robots_lage("api.fupa.net")["bewertung"]


def test_robots_404_ist_kein_verbot(konfiguration: Konfiguration):
    client = _client_mit_robots(konfiguration, 404)
    assert client._robots_erlaubt("https://api.fupa.net/v1/teams/x") is True


def test_robots_serverfehler_sperrt(konfiguration: Konfiguration):
    """RFC 9309, 2.3.1.3: unerreichbar wegen 5xx -> vollstaendig sperren."""
    client = _client_mit_robots(konfiguration, 503)
    assert client._robots_erlaubt("https://api.fupa.net/v1/teams/x") is False


def test_robots_wird_je_host_nur_einmal_geholt(konfiguration: Konfiguration):
    abrufe = []
    from stadionheft.sources.fupa_api import FupaClient

    client = FupaClient(konfiguration)
    client.cache.aktiv = False

    def sitzung():
        def get(url, **k):
            abrufe.append(url)
            return Antwort("User-agent: *\nDisallow: /geheim\n", 200, "text/plain")
        return type("S", (), {"get": staticmethod(get)})()

    client._sitzung = sitzung        # type: ignore[assignment]
    for pfad in ("/a", "/b", "/c"):
        client._robots_erlaubt(f"https://www.fupa.net{pfad}")
    assert abrufe == ["https://www.fupa.net/robots.txt"]


def test_bericht_nennt_den_programmstand(konfiguration: Konfiguration,
                                         monkeypatch, tmp_path):
    """Ohne diese Zeile kostet jede Aktualisierung einen Ratedurchgang.

    Genau das ist am 29.09. passiert: Der Container lief noch mit dem alten
    Code, der Bericht sah aus wie zuvor, und niemand konnte es dem Bericht
    ansehen.
    """
    from stadionheft.sources import fupa_api

    monkeypatch.setattr(fupa_api.FupaClient, "abrufen",
                        lambda self, url: Antwort("", status=404))
    bericht = probe_fupa(konfiguration, "herren1", tmp_path)
    assert bericht["programmstand"]
    assert "Programmstand" in fupa_api.bericht_als_text(bericht)


def test_rohantwort_wird_gesichert_wenn_nichts_erkannt_wird(
        konfiguration: Konfiguration, monkeypatch, tmp_path):
    """Erkennt das Programm nichts, ist die Rohantwort das Einzige, was hilft.

    Ohne sie bleibt nur Raten, wie die Seite ihre Daten fuehrt -- und genau
    daran haben wir uns mehrere Runden lang aufgehalten.
    """
    from stadionheft.sources import fupa_api

    seite = ("<html><body><script>self.__x=" + json.dumps({"a": [1, 2, 3]})
             + ";</script>Kein Fussball hier.</body></html>")
    monkeypatch.setattr(fupa_api.FupaClient, "abrufen",
                        lambda self, url: Antwort(seite))
    bericht = probe_fupa(konfiguration, "herren1", tmp_path)

    treffer = [e for e in bericht["ergebnisse"].values() if e.get("rohantwort")]
    assert treffer, "Keine Rohantwort gesichert"
    datei = tmp_path / "fupa_probe" / treffer[0]["rohantwort"]
    assert "Kein Fussball hier." in datei.read_text(encoding="utf-8")
    assert "Rohantwort:" in fupa_api.bericht_als_text(bericht)


def test_rohantwort_entfaellt_wenn_alles_erkannt_wurde(
        konfiguration: Konfiguration, herren1, monkeypatch, tmp_path):
    from stadionheft.sources import fupa_api

    monkeypatch.setattr(fupa_api.FupaClient, "abrufen",
                        lambda self, url: (Antwort(_teamseite())
                                           if url == herren1.fupa_team_url
                                           else Antwort("", status=404)))
    bericht = probe_fupa(konfiguration, "herren1", tmp_path)
    gut = [e for e in bericht["ergebnisse"].values() if e.get("erkannt")]
    assert gut and not gut[0].get("rohantwort")


def test_eigene_adressen_stehen_ganz_vorn(konfiguration: Konfiguration):
    """Eine von Hand eingetragene Adresse hat Vorrang vor jeder Vermutung.

    Darueber laesst sich auch eine ganz andere Quelle anbinden -- etwa eine
    BFV-Seite. Die Erkennung arbeitet ueber die Struktur der Daten, nicht
    ueber den Anbieter.
    """
    from stadionheft.sources.fupa_api import FupaClient

    mannschaft = konfiguration.mannschaft("herren1")
    mannschaft.zusatz_urls = ["https://www.bfv.de/mannschaften/irgendwas-123"]

    adressen = adressen_fuer(FupaClient(konfiguration), mannschaft)
    assert adressen[0] == "https://www.bfv.de/mannschaften/irgendwas-123"
    assert mannschaft.fupa_team_url in adressen


def test_fremde_quelle_wird_genauso_ausgewertet(konfiguration: Konfiguration):
    """Kommen die Daten von woanders, aendert das nichts an der Erkennung."""
    mannschaft = konfiguration.mannschaft("herren1")
    fremd = "https://www.bfv.de/wettbewerb/1234"
    mannschaft.zusatz_urls = [fremd]

    quelle = _quelle(konfiguration, {fremd: Antwort(_teamseite())})
    daten = quelle.hole(mannschaft)
    assert len(daten.tabelle) == 5
    assert daten.naechstes_spiel is not None


# ---------------------------------------------------------------------------
# Der Kalenderweg -- das Einzige, was FuPas robots.txt ausdruecklich freigibt
# ---------------------------------------------------------------------------

def _kalender(eigen: str = "SV Wörnitzstein-Berg") -> str:
    from datetime import datetime, timedelta

    def wann(tage: int) -> str:
        return (datetime.now() + timedelta(days=tage)).strftime("%Y%m%dT130000Z")

    return (
        "BEGIN:VCALENDAR\nVERSION:2.0\n"
        "BEGIN:VEVENT\nDTSTART:" + wann(-14) + "\n"
        f"SUMMARY:Türk Gücü Lauingen - {eigen} (0:4)\nEND:VEVENT\n"
        "BEGIN:VEVENT\nDTSTART:" + wann(-7) + "\n"
        f"SUMMARY:{eigen} - TSV Meitingen (2:1)\nEND:VEVENT\n"
        "BEGIN:VEVENT\nDTSTART:" + wann(8) + "\n"
        f"SUMMARY:{eigen} - SG Alerheim\n"
        "LOCATION:Sportgelände Wörnitzstein\n"
        "DESCRIPTION:Bezirksliga Schwaben Nord\nEND:VEVENT\n"
        "END:VCALENDAR\n")


def test_spielplan_kommt_aus_dem_kalender(konfiguration: Konfiguration, herren1):
    """Liefert nur der Kalender etwas, muss der Spielplan trotzdem stehen."""
    adresse = f"https://api.fupa.net/v1/teams/{herren1.fupa_slug}/calendar.ics"
    quelle = _quelle(konfiguration, {
        adresse: Antwort(_kalender(), typ="text/calendar; charset=utf-8")})
    daten = quelle.hole(herren1)

    assert daten.naechstes_spiel is not None
    assert daten.naechstes_spiel.gegner == "SG Alerheim"
    assert daten.naechstes_spiel.heimspiel is True
    assert daten.naechstes_spiel.spielort == "Sportgelände Wörnitzstein"
    assert daten.letztes_spiel.ergebnis == "2:1"
    # Aus den nachgetragenen Ergebnissen entsteht auch die Formkurve
    assert "".join(f.ausgang for f in daten.form) == "SS"
    # Tabelle und Torschuetzen liefert der Kalender nicht -- das muss gesagt werden
    assert any("Tabelle" in w for w in daten.warnungen)


def test_kalender_wird_auch_ohne_richtigen_inhaltstyp_erkannt(
        konfiguration: Konfiguration, herren1):
    """Manche Server liefern .ics als text/plain aus."""
    adresse = f"https://api.fupa.net/v1/teams/{herren1.fupa_slug}/calendar.ics"
    quelle = _quelle(konfiguration, {
        adresse: Antwort(_kalender(), typ="text/plain")})
    daten = quelle.hole(herren1)
    assert daten.naechstes_spiel.gegner == "SG Alerheim"


# ---------------------------------------------------------------------------
# Zeitbudget
# ---------------------------------------------------------------------------

def test_zeitbudget_bricht_den_abruf_ab(konfiguration: Konfiguration, herren1,
                                        monkeypatch):
    """Ein haengendes FuPa darf den Lauf nicht ueber das Webserver-Limit ziehen.

    Fuenf Mannschaften mal ein Dutzend Adressen mal Zeitlimit mal
    Wiederholungen ergibt im schlechtesten Fall eine Viertelstunde. Der
    Webserver bricht vorher ab -- und dann entsteht gar nichts, obwohl die
    Ersatzquelle bereitgelegen haette.
    """
    import stadionheft.sources.fupa_api as modul

    konfiguration.roh["datenquelle"]["fupa"]["zeitbudget_sekunden"] = 5
    versuche: list[str] = []
    quelle = _quelle(konfiguration, {}, protokoll=versuche)

    # Jeder Abruf "dauert" zwei Sekunden - ohne wirklich zu warten.
    uhr = {"jetzt": 0.0}
    monkeypatch.setattr(modul.time, "monotonic", lambda: uhr["jetzt"])
    quelle._frist = quelle.zeitbudget

    echt = quelle.client.abrufen

    def langsam(url: str):
        uhr["jetzt"] += 2.0
        return echt(url)

    quelle.client.abrufen = langsam        # type: ignore[method-assign]

    fund = quelle._sammeln(adressen_fuer(quelle.client, herren1),
                           konfiguration.vereinsname, 50, herren1.fupa_slug)

    # Fuenf Sekunden Budget bei zwei Sekunden je Abruf: nach dem dritten ist
    # Schluss, auch wenn noch ein Dutzend Adressen in der Liste steht.
    assert len(versuche) == 3, versuche
    assert len(adressen_fuer(quelle.client, herren1)) > 5


def test_ohne_zeitbudget_laeuft_alles_durch(konfiguration: Konfiguration, herren1):
    """0 bedeutet 'keine Grenze' - das muss auch so bleiben."""
    konfiguration.roh["datenquelle"]["fupa"]["zeitbudget_sekunden"] = 0
    quelle = _quelle(konfiguration, {})

    assert quelle._frist == 0.0
    assert quelle._zeit_abgelaufen() is False
