"""Die Vorab-Pruefung muss die Wahrheit sagen.

Der Anlass: Die alte Pruefung meldete "Konfiguration ist gueltig", und
unmittelbar danach brach der Lauf ab, weil fuer vier von fuenf Mannschaften
keine Daten vorlagen. Eine Pruefung, der man nicht trauen kann, ist schlimmer
als keine.
"""

from __future__ import annotations

import json

from stadionheft.config import Konfiguration
from stadionheft.tools.beispieldaten import vorlagen_schreiben
from stadionheft.vorabpruefung import PROBLEM, als_text, vorab_pruefen


def _nur_herren1(konfiguration: Konfiguration) -> None:
    vorlagen_schreiben(konfiguration, nur_vorlagen=False)
    for datei in konfiguration.eingabe_ordner.glob("damen1_*.csv"):
        datei.unlink()


def _fupa_test_ohne_treffer(konfiguration: Konfiguration) -> None:
    ordner = konfiguration.arbeits_ordner / "fupa_probe"
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / "_bericht.json").write_text(
        json.dumps({"zusammenfassung": {}}), encoding="utf-8")


def test_zaehlt_die_dateien_die_wirklich_entstehen(konfiguration: Konfiguration):
    konfiguration.roh["datenquelle"]["modus"] = "api"
    konfiguration.roh["datenquelle"]["fallback_modus"] = "manuell"
    _nur_herren1(konfiguration)
    _fupa_test_ohne_treffer(konfiguration)

    bericht = vorab_pruefen(konfiguration, probeseite=False)

    assert [m.schluessel for m in bericht.bereite] == ["herren1"]
    assert [m.schluessel for m in bericht.offene] == ["damen1"]
    assert "1 von 2" in bericht.urteil


def test_meldet_wenn_gar_nichts_entstehen_wuerde(konfiguration: Konfiguration):
    konfiguration.roh["datenquelle"]["modus"] = "manuell"
    konfiguration.roh["datenquelle"]["fallback_modus"] = ""
    konfiguration.eingabe_ordner.mkdir(parents=True, exist_ok=True)

    bericht = vorab_pruefen(konfiguration, probeseite=False)

    assert not bericht.lauffaehig
    assert "keine einzige Datei" in bericht.urteil


def test_ungepruefter_fupa_abruf_wird_als_solcher_benannt(
        konfiguration: Konfiguration):
    """Ohne Test darf nicht einfach 'FuPa' dastehen, als sei das gesichert."""
    konfiguration.roh["datenquelle"]["modus"] = "api"

    bericht = vorab_pruefen(konfiguration, probeseite=False)

    assert all("ungeprüft" in m.quelle for m in bericht.mannschaften)
    assert all(m.unsicher for m in bericht.mannschaften)
    assert any("noch nie getestet" in b.text for b in bericht.hinweise)
    assert "noch nie getestet" in bericht.urteil


def test_unanlegbarer_ausgabeordner_ist_ein_problem(konfiguration: Konfiguration,
                                                    tmp_path):
    """Ein falsch eingetragener Pfad faellt sonst erst nach dem Lauf auf."""
    sperre = tmp_path / "keine_datei_sondern_ordner"
    sperre.write_text("ich bin eine Datei", encoding="utf-8")
    konfiguration.roh["ausgabe"]["ordner"] = str(sperre / "05_Ausgaben")

    bericht = vorab_pruefen(konfiguration, probeseite=False)

    assert not bericht.lauffaehig
    assert any(b.thema == "Ausgaben" and b.stufe == PROBLEM
               for b in bericht.befunde), bericht.befunde


def test_nicht_beschreibbarer_ausgabeordner_ist_ein_problem(
        konfiguration: Konfiguration, monkeypatch):
    """Ordner vorhanden, aber nicht beschreibbar.

    Auf der NAS der haeufigste Fall: Der eingehaengte Ordner ist da, gehoert
    aber jemand anderem. Dass es ihn gibt, sagt darueber nichts aus -- und
    das faellt sonst erst nach dem ganzen Lauf beim Speichern auf.

    Der Schreibfehler wird nachgestellt, weil die Tests als 'root' laufen:
    Der darf auch in einen gesperrten Ordner schreiben.
    """
    konfiguration.ausgabe_ordner.mkdir(parents=True, exist_ok=True)

    import stadionheft.vorabpruefung as vp

    echt = vp._schreibprobe

    def streikt(ordner):
        if ordner == konfiguration.ausgabe_ordner:
            return "Read-only file system"
        return echt(ordner)

    monkeypatch.setattr(vp, "_schreibprobe", streikt)

    bericht = vorab_pruefen(konfiguration, probeseite=False)

    assert not bericht.lauffaehig
    befund = [b for b in bericht.befunde if b.thema == "Ausgaben"]
    assert befund and befund[0].stufe == PROBLEM
    assert "Read-only" in befund[0].text


def test_probeseite_prueft_vorlagen_und_schriften(konfiguration: Konfiguration):
    """Die Probeseite ist der einzige Weg, Satz und Schriften zu pruefen."""
    bericht = vorab_pruefen(konfiguration, probeseite=True)

    satz = [b for b in bericht.befunde if b.thema == "Seitensatz"]
    assert satz and satz[0].stufe != PROBLEM, satz
    assert "Probeseite gesetzt" in satz[0].text


def test_bericht_laesst_sich_lesen(konfiguration: Konfiguration):
    bericht = vorab_pruefen(konfiguration, probeseite=False)
    text = als_text(konfiguration, bericht)

    assert "Mannschaften" in text
    assert bericht.urteil in text


def test_leere_csv_vorlagen_zaehlen_nicht(konfiguration: Konfiguration):
    """Eine Vorlage mit nur der Kopfzeile ist keine Datengrundlage.

    'beispieldaten' ohne --mit-daten legt genau solche Dateien an. Wuerden
    sie zaehlen, sagte die Pruefung wieder etwas zu, das der Lauf nicht haelt.
    """
    konfiguration.roh["datenquelle"]["modus"] = "manuell"
    konfiguration.roh["datenquelle"]["fallback_modus"] = ""
    vorlagen_schreiben(konfiguration, nur_vorlagen=True)

    bericht = vorab_pruefen(konfiguration, probeseite=False)

    assert not bericht.bereite, [m.bemerkung for m in bericht.mannschaften]
    assert "keine einzige Datei" in bericht.urteil


def test_gefuellte_csv_dateien_zaehlen(konfiguration: Konfiguration):
    konfiguration.roh["datenquelle"]["modus"] = "manuell"
    konfiguration.roh["datenquelle"]["fallback_modus"] = ""
    vorlagen_schreiben(konfiguration, nur_vorlagen=False)

    bericht = vorab_pruefen(konfiguration, probeseite=False)

    assert len(bericht.bereite) == 2
    assert bericht.lauffaehig
