"""Ganz normale HTML-Tabellen lesen.

Die eigene Vereinsseite war die einzige Quelle, die das Programm nicht lesen
konnte -- obwohl sie die zugaenglichste von allen ist. Sie liefert kein
eingebettetes JSON, sondern eine ausgeschriebene Tabelle.
"""

from __future__ import annotations

from stadionheft.sources.erkennung import (spiele_erkennen, tabelle_erkennen,
                                           torjaeger_erkennen)
from stadionheft.sources.html_tabellen import (rahmenseiten_aus_html,
                                               tabellen_aus_html)

TABELLE = """
<table>
 <tr><th>Pl.</th><th>Mannschaft</th><th>Sp.</th><th>S</th><th>U</th><th>N</th>
     <th>Tore</th><th>Diff.</th><th>Pkt.</th></tr>
 <tr><td>1.</td><td>TSV Meitingen</td><td>11</td><td>8</td><td>2</td><td>1</td>
     <td>28:9</td><td>+19</td><td>26</td></tr>
 <tr><td>4.</td><td><a href="/x">SV W&ouml;rnitzstein-Berg</a></td><td>11</td>
     <td>5</td><td>3</td><td>3</td><td>19:15</td><td>+4</td><td>18</td></tr>
 <tr><td>6.</td><td>VfL Ecknach</td><td>11</td><td>1</td><td>1</td><td>9</td>
     <td>8:31</td><td>-23</td><td>4</td></tr>
</table>
"""


def test_kopfzeile_stellt_die_schluessel():
    tabellen = tabellen_aus_html(TABELLE)
    assert len(tabellen) == 1
    erste = tabellen[0][0]
    assert erste["Mannschaft"] == "TSV Meitingen"
    assert erste["Pkt."] == "26"


def test_tabelle_wird_als_tabelle_erkannt():
    """Der eigentliche Zweck: Die Erkennung muss damit weiterarbeiten."""
    zeilen = tabelle_erkennen(tabellen_aus_html(TABELLE)[0],
                              "SV Wörnitzstein-Berg")

    assert [z.platz for z in zeilen] == [1, 4, 6]
    wir = [z for z in zeilen if z.eigene]
    assert len(wir) == 1
    assert wir[0].punkte == 18
    # "19:15" in einer einzigen Spalte "Tore"
    assert (wir[0].tore, wir[0].gegentore) == (19, 15)
    assert (wir[0].siege, wir[0].unentschieden, wir[0].niederlagen) == (5, 3, 3)


def test_sieg_unentschieden_niederlage_in_einer_spalte():
    html = """
    <table>
     <tr><th>Pl</th><th>Team</th><th>Sp</th><th>SUN</th><th>Tore</th><th>Pkt</th></tr>
     <tr><td>1</td><td>TSV Meitingen</td><td>11</td><td>8-2-1</td><td>28:9</td><td>26</td></tr>
     <tr><td>4</td><td>SV Wörnitzstein-Berg</td><td>11</td><td>5-3-3</td><td>19:15</td><td>18</td></tr>
     <tr><td>6</td><td>VfL Ecknach</td><td>11</td><td>1-1-9</td><td>8:31</td><td>4</td></tr>
    </table>
    """
    zeilen = tabelle_erkennen(tabellen_aus_html(html)[0], "SV Wörnitzstein-Berg")
    wir = [z for z in zeilen if z.eigene][0]
    assert (wir.siege, wir.unentschieden, wir.niederlagen) == (5, 3, 3)


def test_spielplan_mit_umbruch_in_der_datumszelle():
    """'13.09.2026<br>15:00' -- so steht es auf Vereinsseiten."""
    html = """
    <table>
     <tr><th>Datum</th><th>Heim</th><th>Gast</th><th>Ergebnis</th></tr>
     <tr><td>13.09.2026<br>15:00</td><td>SV Wörnitzstein-Berg</td>
         <td>TG Lauingen</td><td>3:1</td></tr>
     <tr><td>11.10.2026<br>14:00</td><td>SG Alerheim</td>
         <td>SV Wörnitzstein-Berg</td><td>&nbsp;</td></tr>
    </table>
    """
    spiele = spiele_erkennen(tabellen_aus_html(html)[0], "SV Wörnitzstein-Berg")

    assert len(spiele) == 2
    assert spiele[0].datum == "13.09.2026"
    assert spiele[0].uhrzeit == "15:00 Uhr"
    assert spiele[0].ergebnis == "3:1"
    # Ein leeres Ergebnis bleibt leer und wird nicht zu "0:0"
    assert spiele[1].ergebnis == ""


def test_torschuetzenliste():
    html = """
    <table>
     <tr><th>Spieler</th><th>Tore</th><th>Vorlagen</th><th>Spiele</th></tr>
     <tr><td>F. Moll</td><td>7</td><td>3</td><td>11</td></tr>
     <tr><td>D. Habersatter</td><td>5</td><td>4</td><td>10</td></tr>
     <tr><td>M. Bschor</td><td>3</td><td>1</td><td>11</td></tr>
    </table>
    """
    zeilen = torjaeger_erkennen(tabellen_aus_html(html)[0])
    assert [(z.spieler, z.tore) for z in zeilen] == [
        ("F. Moll", 7), ("D. Habersatter", 5), ("M. Bschor", 3)]


def test_layouttabellen_werden_uebersprungen():
    """Eine Navigationsleiste ist keine Datentabelle."""
    html = """
    <table><tr><td>Startseite</td><td>Verein</td></tr></table>
    <table><tr><td>Nur eine Spalte</td></tr><tr><td>und noch eine</td></tr></table>
    """
    # Die erste hat nur eine Zeile, die zweite nur eine Spalte.
    assert tabellen_aus_html(html) == []


def test_skript_inhalt_wird_nicht_gelesen():
    """In <script> steht oft HTML als Zeichenkette. Das ist kein Inhalt."""
    html = """
    <script>var vorlage = "<table><tr><td>Platzhalter</td></tr></table>";</script>
    <table>
     <tr><th>Spieler</th><th>Tore</th></tr>
     <tr><td>F. Moll</td><td>7</td></tr>
     <tr><td>M. Bschor</td><td>3</td></tr>
    </table>
    """
    tabellen = tabellen_aus_html(html)
    assert len(tabellen) == 1
    assert "Platzhalter" not in str(tabellen)


def test_eingebundene_widgets_werden_gemeldet():
    """Steht die Tabelle in einem Widget, liegt sie eine Adresse weiter."""
    html = """
    <iframe src="//widget.fupa.net/team/abc"></iframe>
    <iframe src="/ohne-host/tabelle"></iframe>
    <iframe></iframe>
    """
    adressen = rahmenseiten_aus_html(
        html, "https://www.sv-woernitzstein-berg.de/ergebnisse_1-mannschaft/")

    assert adressen == ["https://widget.fupa.net/team/abc",
                        "https://www.sv-woernitzstein-berg.de/ohne-host/tabelle"]


def test_kaputtes_html_wirft_nicht():
    """Eine halbe Seite ist besser als ein Absturz."""
    assert tabellen_aus_html("<table><tr><td>offen") == []
    assert tabellen_aus_html("") == []
    assert rahmenseiten_aus_html("<iframe src=") == []
