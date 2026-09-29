"""JSON aus HTML gewinnen -- in den Varianten, die Websites tatsaechlich nutzen."""

from __future__ import annotations

import json

from stadionheft.sources.erkennung import tabelle_erkennen
from stadionheft.sources.html_daten import json_aus_html

TABELLE = [
    {"place": 1, "teamName": "Joshofen-B.", "matches": 1, "wins": 1, "draws": 0,
     "losses": 0, "goalsFor": 5, "goalsAgainst": 0, "points": 3},
    {"place": 2, "teamName": "Wörnitzstein", "matches": 1, "wins": 1, "draws": 0,
     "losses": 0, "goalsFor": 4, "goalsAgainst": 0, "points": 3},
    {"place": 3, "teamName": "Alerheim", "matches": 1, "wins": 1, "draws": 0,
     "losses": 0, "goalsFor": 4, "goalsAgainst": 3, "points": 3},
]


def _seite(script: str) -> str:
    return f"""<!DOCTYPE html><html lang="de"><head>
<title>SV Wörnitzstein-Berg</title></head><body>
<div id="__next"><h1>Tabelle</h1></div>
{script}
</body></html>"""


def test_next_data_block():
    daten = {"props": {"pageProps": {"standings": TABELLE}}}
    html = _seite(f'<script id="__NEXT_DATA__" type="application/json">'
                  f'{json.dumps(daten)}</script>')
    bloecke = json_aus_html(html)
    assert bloecke
    assert len(tabelle_erkennen(bloecke[0])) == 3


def test_allgemeiner_json_block():
    html = _seite('<script type="application/json">'
                  + json.dumps({"table": TABELLE}) + "</script>")
    assert len(tabelle_erkennen(json_aus_html(html)[0])) == 3


def test_nuxt_zuweisung():
    html = _seite("<script>window.__NUXT__ = "
                  + json.dumps({"state": {"standings": TABELLE}}) + ";</script>")
    bloecke = json_aus_html(html)
    assert bloecke
    assert len(tabelle_erkennen(bloecke)) == 3


def test_json_als_zeichenkette_im_json():
    """Next.js-Streams verpacken die Nutzdaten als Text in einem JSON-Feld."""
    innen = json.dumps({"standings": TABELLE})
    aussen = {"chunk": innen, "id": 1}
    html = _seite(f'<script type="application/json">{json.dumps(aussen)}</script>')
    bloecke = json_aus_html(html)
    # Die aufgeloeste Zeichenkette muss als eigener Block dabei sein
    assert any(len(tabelle_erkennen(b)) == 3 for b in bloecke)


def test_objekt_in_freiem_javascript():
    html = _seite("<script>var vorlauf = 1; "
                  "var daten = " + json.dumps({"standings": TABELLE})
                  + "; render(daten);</script>")
    bloecke = json_aus_html(html)
    assert any(len(tabelle_erkennen(b)) == 3 for b in bloecke)


def test_klammer_im_text_verwirrt_nicht():
    daten = {"standings": TABELLE, "hinweis": "Achtung } und { im Text"}
    html = _seite("<script>var x = " + json.dumps(daten) + ";</script>")
    assert any(len(tabelle_erkennen(b)) == 3 for b in json_aus_html(html))


def test_seite_ohne_json():
    html = "<html><body><p>Nur Text</p><script>alert(1)</script></body></html>"
    assert json_aus_html(html) == []


def test_leere_eingabe():
    assert json_aus_html("") == []


def test_kaputtes_json_wird_uebergangen():
    html = _seite('<script type="application/json">{ das ist kaputt }</script>')
    assert json_aus_html(html) == []


def test_mehrere_bloecke_werden_alle_geliefert():
    html = _seite(
        '<script type="application/json">' + json.dumps({"a": TABELLE}) + "</script>"
        '<script type="application/json">' + json.dumps({"b": TABELLE}) + "</script>")
    assert len(json_aus_html(html)) >= 2


def test_kleiner_json_block_verdeckt_die_echten_daten_nicht():
    """Ein JSON-LD-Schnipsel darf die Suche nach den Nutzdaten nicht beenden.

    Genau dieser Fall trat auf der echten FuPa-Teamseite auf: Die Seite
    lieferte JSON, aber nur eine Adressangabe -- die Spieldaten steckten
    daneben in freiem JavaScript und wurden nie angesehen.
    """
    html = _seite(
        '<script type="application/ld+json">'
        + json.dumps({"@type": "SportsTeam", "name": "SV Wörnitzstein-Berg"})
        + "</script>"
        "<script>self.__DATA__ = " + json.dumps({"standings": TABELLE})
        + ";</script>")
    bloecke = json_aus_html(html)
    assert any(len(tabelle_erkennen(b)) == 3 for b in bloecke)


def test_next_js_strom_wird_ausgepackt():
    """Neuere Next.js-Versionen liefern self.__next_f.push([1,"..."])."""
    nutzlast = "4:" + json.dumps({"standings": TABELLE})
    html = _seite("<script>self.__next_f=self.__next_f||[];"
                  "self.__next_f.push([1," + json.dumps(nutzlast) + "]);</script>")
    bloecke = json_aus_html(html)
    assert any(len(tabelle_erkennen(b)) == 3 for b in bloecke)


def test_liste_auf_oberster_ebene_wird_gefunden():
    html = _seite("<script>var daten = " + json.dumps(TABELLE) + ";</script>")
    assert any(len(tabelle_erkennen(b)) == 3 for b in json_aus_html(html))
