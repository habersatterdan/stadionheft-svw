from __future__ import annotations

import json
from pathlib import Path

import pytest
from pypdf import PdfReader

from stadionheft.build import heft_aus_snapshot, heft_erstellen
from stadionheft.config import Konfiguration
from stadionheft.errors import StadionheftFehler, VorlageFehltFehler
from stadionheft.render.pages import LayoutWerte, text_zu_absaetzen

A5_BREITE_PT = 419.53
A5_HOEHE_PT = 595.28


def test_heft_wird_erzeugt(konfiguration: Konfiguration, heftplan_minimal):
    ergebnis = heft_erstellen(konfiguration, ["herren1"],
                              heftplan=heftplan_minimal, nas_hochladen=False)
    assert ergebnis.pdf.exists()
    # Titel + 5 Mannschaftsseiten + Impressum
    assert ergebnis.seitenzahl == 7
    assert ergebnis.verwendete_quelle == "demo"


def test_endformat_entspricht_der_vorlage(konfiguration: Konfiguration,
                                          heftplan_minimal):
    ergebnis = heft_erstellen(konfiguration, ["herren1"],
                              heftplan=heftplan_minimal, nas_hochladen=False)
    for seite in PdfReader(str(ergebnis.pdf)).pages:
        assert float(seite.trimbox.width) == pytest.approx(A5_BREITE_PT, abs=1)
        assert float(seite.trimbox.height) == pytest.approx(A5_HOEHE_PT, abs=1)


def test_mehrere_mannschaften_ergeben_mehr_seiten(konfiguration: Konfiguration,
                                                  heftplan_minimal):
    eine = heft_erstellen(konfiguration, ["herren1"], heftplan=heftplan_minimal,
                          nas_hochladen=False).seitenzahl
    zwei = heft_erstellen(konfiguration, ["herren1", "damen1"],
                          heftplan=heftplan_minimal, nas_hochladen=False).seitenzahl
    assert zwei > eine


def test_ohne_mannschaft_klare_meldung(konfiguration: Konfiguration,
                                       heftplan_minimal):
    with pytest.raises(StadionheftFehler) as fehler:
        heft_erstellen(konfiguration, [], heftplan=heftplan_minimal)
    assert "mindestens eine Mannschaft" in fehler.value.benutzer_text


def test_fremdformate_werden_vereinheitlicht(konfiguration: Konfiguration,
                                             werbe_pdf: Path):
    """Werbeseiten im InDesign-Format (461x637 pt) und erzeugte Seiten
    (437x612 pt) muessen im Ergebnis dieselbe MediaBox haben."""
    plan = [
        {"typ": "titelseite"},
        {"typ": "pdf", "quelle": str(werbe_pdf), "optional": False},
        {"typ": "impressum"},
    ]
    ergebnis = heft_erstellen(konfiguration, ["herren1"], heftplan=plan,
                              nas_hochladen=False)
    boxen = {(round(float(s.mediabox.width)), round(float(s.mediabox.height)))
             for s in PdfReader(str(ergebnis.pdf)).pages}
    assert len(boxen) == 1
    assert ergebnis.seitenzahl == 4


def test_nur_erste_seite_der_werbung(konfiguration: Konfiguration, werbe_pdf: Path):
    plan = [{"typ": "pdf", "quelle": str(werbe_pdf), "seiten": "1", "optional": False}]
    ergebnis = heft_erstellen(konfiguration, ["herren1"], heftplan=plan,
                              nas_hochladen=False)
    assert ergebnis.seitenzahl == 1


def test_fehlende_pflicht_pdf_bricht_mit_pfad_ab(konfiguration: Konfiguration):
    plan = [{"typ": "titelseite"},
            {"typ": "pdf", "quelle": "02_werbung/gibtsnicht.pdf", "optional": False}]
    with pytest.raises(VorlageFehltFehler) as fehler:
        heft_erstellen(konfiguration, ["herren1"], heftplan=plan, nas_hochladen=False)
    assert "gibtsnicht.pdf" in fehler.value.benutzer_text
    assert "gibtsnicht.pdf" in (fehler.value.hinweis or "")


def test_fehlende_optionale_pdf_ist_nur_warnung(konfiguration: Konfiguration):
    plan = [{"typ": "titelseite"},
            {"typ": "pdf", "quelle": "02_werbung/gibtsnicht.pdf", "optional": True}]
    ergebnis = heft_erstellen(konfiguration, ["herren1"], heftplan=plan,
                              nas_hochladen=False)
    assert ergebnis.seitenzahl == 1
    assert any("gibtsnicht.pdf" in w for w in ergebnis.warnungen)


def test_snapshot_erzeugt_identisches_heft(konfiguration: Konfiguration,
                                           heftplan_minimal):
    erst = heft_erstellen(konfiguration, ["herren1"], spieltag="2. Spieltag",
                          heftplan=heftplan_minimal, nas_hochladen=False)
    assert erst.snapshot and erst.snapshot.exists()

    inhalt = json.loads(erst.snapshot.read_text(encoding="utf-8"))
    assert inhalt["spieltag"] == "2. Spieltag"
    assert inhalt["mannschaften"][0]["tabelle"][1]["mannschaft"] == "Wörnitzstein"

    erneut = heft_aus_snapshot(konfiguration, erst.snapshot,
                               dateiname="wiederholung.pdf", nas_hochladen=False)
    assert erneut.seitenzahl == erst.seitenzahl


def test_dateiname_aus_vorlage(konfiguration: Konfiguration, heftplan_minimal):
    ergebnis = heft_erstellen(konfiguration, ["herren1"],
                              heftplan=heftplan_minimal, nas_hochladen=False)
    # Anstoss der Demo-Daten ist der 29.07.2026
    assert ergebnis.pdf.name == "20260729_WaB_Druck.pdf"


def test_titelspiel_bevorzugt_gewuenschte_mannschaft(konfiguration: Konfiguration,
                                                     heftplan_minimal):
    ergebnis = heft_erstellen(konfiguration, ["herren1", "damen1"],
                              titelspiel_von="damen1", heftplan=heftplan_minimal,
                              nas_hochladen=False)
    inhalt = json.loads(ergebnis.snapshot.read_text(encoding="utf-8"))
    assert "Damen 1" in inhalt["titelspiel"]["heim"]


def test_fallback_auf_manuelle_daten(konfiguration: Konfiguration, heftplan_minimal):
    """Faellt die primaere Quelle aus, wird auf die Ersatzquelle umgeschaltet."""
    konfiguration.roh["datenquelle"]["fallback_modus"] = "demo"
    (konfiguration.eingabe_ordner).mkdir(parents=True, exist_ok=True)
    # 'manuell' scheitert (keine Dateien) -> Ersatz 'demo' greift
    ergebnis = heft_erstellen(konfiguration, ["herren1"], datenquelle="manuell",
                              heftplan=heftplan_minimal, nas_hochladen=False)
    assert ergebnis.verwendete_quelle == "demo"
    assert any("umgeschaltet" in w for w in ergebnis.warnungen)


# ---------------------------------------------------------------------------
# Rendering-Details
# ---------------------------------------------------------------------------

def test_schriftliste_wird_korrekt_gequotet():
    layout = LayoutWerte(schriftfamilie="Segoe UI, Source Sans 3, sans-serif")
    assert str(layout.schrift_css) == '"Segoe UI", "Source Sans 3", sans-serif'


def test_schriftliste_wehrt_ausbruch_ab():
    layout = LayoutWerte(schriftfamilie="A} body{display:none")
    assert "}" not in str(layout.schrift_css)
    assert "{" not in str(layout.schrift_css)


def test_text_zu_absaetzen_erkennt_ueberschrift():
    absaetze = text_zu_absaetzen("Kurze Zeile\n\nEin normaler Absatz mit Text.")
    assert absaetze[0]["ueberschrift"] is True
    assert absaetze[1]["ueberschrift"] is False


def test_text_zu_absaetzen_mit_raute():
    absaetze = text_zu_absaetzen("# Titel\n\nText")
    assert absaetze[0] == {"ueberschrift": True, "text": "Titel"}


def test_text_zu_absaetzen_leer():
    assert text_zu_absaetzen("") == []
