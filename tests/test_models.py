from __future__ import annotations

from datetime import datetime

from stadionheft.models import (Ausgabe, MannschaftsDaten, Spiel, SpielerZeile,
                                TabellenZeile, TorjaegerZeile, spiele_einordnen)


def test_tabellenzeile_abgeleitete_werte():
    z = TabellenZeile(platz=2, mannschaft="Wörnitzstein", spiele=1, siege=1,
                      tore=4, gegentore=0, punkte=3)
    assert z.differenz == 4
    assert z.bilanz == "1-0-0"
    assert z.torverhaeltnis == "4:0"


def test_tabellenzeile_aus_csv_erkennt_eigene_mannschaft():
    z = TabellenZeile.aus_csv(
        {"platz": "2", "mannschaft": "Wörnitzstein", "punkte": "3"}, "Wörnitzstein")
    assert z.eigene is True
    assert z.punkte == 3


def test_tabellenzeile_aus_csv_toleriert_englische_spalten():
    z = TabellenZeile.aus_csv({"pl": "1", "team": "FC X", "sp": "5", "pkt": "12"})
    assert (z.platz, z.mannschaft, z.spiele, z.punkte) == (1, "FC X", 5, 12)


def test_tabellenzeile_aus_csv_ignoriert_muell():
    z = TabellenZeile.aus_csv({"platz": "-", "mannschaft": "FC X", "punkte": ""})
    assert z.platz == 0 and z.punkte == 0


def test_spielerzeile_zerlegt_elfmeter():
    z = SpielerZeile.aus_csv({"spieler": "A", "elfmeter": "1/2"})
    assert (z.elfmeter_getroffen, z.elfmeter_gesamt) == (1, 2)
    assert z.elfmeter == "1/2"


def test_spiel_datum_und_uhrzeit():
    s = Spiel(heim="A", gast="B", anstoss="2026-07-29T18:30:00")
    assert s.wochentag == "Mittwoch"
    assert s.datum == "29.07.2026"
    assert s.uhrzeit == "18:30 Uhr"
    assert s.paarung == "A - B"


def test_spiel_aus_csv_mit_getrennten_spalten():
    s = Spiel.aus_csv({"heim": "SVW", "gast": "TSV", "datum": "29.07.2026",
                       "uhrzeit": "18:30 Uhr", "heimspiel": "ja"})
    assert s.anstoss.startswith("2026-07-29T18:30")
    assert s.heimspiel is True
    assert s.gegner == "TSV"


def test_spiel_ohne_anstoss_bleibt_leer():
    s = Spiel(heim="A", gast="B")
    assert s.datum == "" and s.uhrzeit == "" and s.wochentag == ""


def test_auswaertsspiel_gegner_ist_heimmannschaft():
    s = Spiel(heim="TSV", gast="SVW", heimspiel=False)
    assert s.gegner == "TSV"


def test_ausgabe_json_hin_und_zurueck():
    original = Ausgabe(
        saison="2026/2027", spieltag="2. Spieltag",
        titelspiel=Spiel(heim="SVW", gast="TSV", anstoss="2026-07-29T18:30:00"),
        mannschaften=[MannschaftsDaten(
            schluessel="herren1", anzeigename="Herren 1",
            tabelle=[TabellenZeile(platz=1, mannschaft="SVW", punkte=3)],
            torjaeger=[TorjaegerZeile(platz=1, spieler="F. Moll", tore=2)],
            spieler=[SpielerZeile(platz=1, spieler="F. Moll", tore=2)],
            naechstes_spiel=Spiel(heim="SVW", gast="TSV"),
        )],
        erstellt_am="2026-08-03T10:00:00",
    )
    kopie = Ausgabe.from_dict(original.to_dict())
    assert kopie.to_dict() == original.to_dict()
    assert kopie.mannschaften[0].tabelle[0].mannschaft == "SVW"
    assert kopie.titelspiel.datum == "29.07.2026"


# ---------------------------------------------------------------------------
# Auswahl des naechsten Spiels -- massgeblich ist das Datum
# ---------------------------------------------------------------------------

def _spiel(tag: str, gast: str = "Gegner", ergebnis: str = "") -> Spiel:
    return Spiel(heim="SVW", gast=gast, anstoss=f"2026-08-{tag}T15:00:00",
                 ergebnis=ergebnis)


def test_naechstes_spiel_richtet_sich_nach_dem_datum():
    plan = [_spiel("02", "Alerheim"), _spiel("09", "Ecknach"),
            _spiel("26", "Lauingen")]
    naechstes, letztes = spiele_einordnen(plan, stichtag=datetime(2026, 8, 5, 12, 0))
    assert naechstes.gast == "Ecknach"
    assert letztes.gast == "Alerheim"


def test_reihenfolge_in_der_datei_ist_egal():
    plan = [_spiel("26", "Lauingen"), _spiel("02", "Alerheim"),
            _spiel("09", "Ecknach")]
    naechstes, _ = spiele_einordnen(plan, stichtag=datetime(2026, 8, 5))
    assert naechstes.gast == "Ecknach"


def test_fehlendes_ergebnis_verschiebt_nichts_nach_vorn():
    """Ein nicht nachgetragenes Ergebnis darf keine alte Partie
    auf die Titelseite bringen."""
    plan = [_spiel("02", "Alerheim", ergebnis=""),      # gespielt, nicht gepflegt
            _spiel("09", "Ecknach")]
    naechstes, letztes = spiele_einordnen(plan, stichtag=datetime(2026, 8, 5))
    assert naechstes.gast == "Ecknach"
    assert letztes.gast == "Alerheim"


def test_spiel_am_selben_tag_bleibt_das_naechste():
    """Heft am Spieltag nachdrucken: die laufende Partie bleibt vorn."""
    plan = [_spiel("09", "Ecknach")]
    naechstes, _ = spiele_einordnen(plan, stichtag=datetime(2026, 8, 9, 16, 30))
    assert naechstes is not None and naechstes.gast == "Ecknach"


def test_spiel_von_gestern_ist_das_letzte():
    plan = [_spiel("09", "Ecknach")]
    naechstes, letztes = spiele_einordnen(plan, stichtag=datetime(2026, 8, 10, 9, 0))
    assert naechstes is None
    assert letztes.gast == "Ecknach"


def test_saisonende_liefert_kein_naechstes_spiel():
    plan = [_spiel("02"), _spiel("09")]
    naechstes, letztes = spiele_einordnen(plan, stichtag=datetime(2026, 12, 1))
    assert naechstes is None
    assert letztes.anstoss.startswith("2026-08-09")


def test_vor_saisonstart_gibt_es_kein_letztes_spiel():
    plan = [_spiel("02"), _spiel("09")]
    naechstes, letztes = spiele_einordnen(plan, stichtag=datetime(2026, 7, 1))
    assert naechstes.anstoss.startswith("2026-08-02")
    assert letztes is None


def test_ohne_datum_faellt_auf_die_reihenfolge_zurueck():
    plan = [Spiel(heim="A", gast="B", ergebnis="1:0"),
            Spiel(heim="C", gast="D")]
    naechstes, letztes = spiele_einordnen(plan, stichtag=datetime(2026, 8, 5))
    assert naechstes.gast == "D"
    assert letztes.gast == "B"


def test_leerer_spielplan():
    assert spiele_einordnen([], stichtag=datetime(2026, 8, 5)) == (None, None)
