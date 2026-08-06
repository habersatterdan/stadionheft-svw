"""Ablaufsteuerung: von der Mannschaftsauswahl zum fertigen PDF.

Der komplette Weg in einer Funktion, damit Weboberflaeche und Kommandozeile
garantiert dasselbe tun:

    1. Daten je ausgewaehlter Mannschaft holen (FuPa / CSV / Demo)
    2. Snapshot der Rohdaten schreiben  -> Reproduzierbarkeit
    3. Variable Seiten als PDF erzeugen
    4. Mit den festen Seiten (Werbung usw.) laut Heftplan montieren
    5. Ergebnis speichern und optional auf die NAS legen

Reproduzierbarkeit
------------------
Jeder Lauf legt neben dem PDF eine Datei ``*_snapshot.json`` mit genau den
Daten ab, aus denen das Heft entstanden ist. Mit
``heft_aus_snapshot(...)`` entsteht daraus jederzeit wieder dasselbe PDF --
ohne erneuten Zugriff auf FuPa. Das ist die Antwort auf "das Heft von letzter
Woche nochmal, aber mit korrigiertem Vorwort".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from .config import Konfiguration, Mannschaft, heftplan_laden
from .errors import StadionheftFehler, VorlageFehltFehler
from .logging_setup import logger
from .models import Ausgabe, MannschaftsDaten, Spiel
from .render.assemble import Heftseite, MontageErgebnis, zusammenfuegen
from .render.pages import SEITEN_VORLAGEN, SeitenRenderer
from .render.werbung import werbeblock
from .sources.base import quelle_erzeugen
from .storage.nas import NasAblage


@dataclass
class BauErgebnis:
    pdf: Path
    seitenzahl: int = 0
    snapshot: Path | None = None
    nas_ziel: str = ""
    warnungen: list[str] = field(default_factory=list)
    verwendete_quelle: str = ""
    dauer_sekunden: float = 0.0

    def als_dict(self) -> dict:
        return {
            "pdf": str(self.pdf),
            "dateiname": self.pdf.name,
            "seitenzahl": self.seitenzahl,
            "snapshot": str(self.snapshot) if self.snapshot else "",
            "nas_ziel": self.nas_ziel,
            "warnungen": self.warnungen,
            "quelle": self.verwendete_quelle,
            "dauer_sekunden": round(self.dauer_sekunden, 1),
        }


# ---------------------------------------------------------------------------
# Daten holen
# ---------------------------------------------------------------------------

def daten_holen(konfiguration: Konfiguration, schluessel: list[str],
                modus: str | None = None) -> tuple[list[MannschaftsDaten], str, list[str]]:
    """Holt die Daten aller gewaehlten Mannschaften.

    Bei einem Ausfall der primaeren Quelle wird -- falls konfiguriert -- einmal
    komplett auf die Ersatzquelle umgeschaltet. Bewusst *komplett* und nicht je
    Mannschaft: ein Heft, dessen Mannschaften aus verschiedenen Quellen mit
    verschiedenen Staenden stammen, waere schwer nachvollziehbar.

    Als Ausfall gilt nicht nur ein Fehler, sondern auch eine Quelle, die zwar
    antwortet, aber **nichts liefert**. Ein Heft mit lauter leeren Seiten waere
    formal ein Erfolg und praktisch wertlos.
    """
    primaer = modus or str(konfiguration.get("datenquelle.modus", "demo"))
    ersatz = str(konfiguration.get("datenquelle.fallback_modus", "") or "")
    warnungen: list[str] = []

    for versuch, aktueller_modus in enumerate([primaer, ersatz]):
        if not aktueller_modus:
            continue
        if versuch == 1:
            logger().warning("Wechsle auf Ersatz-Datenquelle '%s'.", aktueller_modus)
        quelle = quelle_erzeugen(aktueller_modus, konfiguration)
        ergebnis: list[MannschaftsDaten] = []
        try:
            for name in schluessel:
                mannschaft: Mannschaft = konfiguration.mannschaft(name)
                logger().info("Lade Daten fuer %s (Quelle: %s) ...",
                              mannschaft.anzeigename, aktueller_modus)
                daten = quelle.hole(mannschaft)
                ergebnis.append(daten)
            if versuch == 0 and ersatz and not _brauchbar(ergebnis):
                logger().warning(
                    "Datenquelle '%s' hat geantwortet, aber keine Spieldaten "
                    "geliefert.", aktueller_modus)
                warnungen.append(
                    f"Von '{aktueller_modus}' kamen keine verwertbaren Daten. "
                    f"Es wurde automatisch auf '{ersatz}' umgeschaltet.")
                continue
            return ergebnis, aktueller_modus, warnungen
        except StadionheftFehler as fehler:
            logger().error("Datenquelle '%s' fehlgeschlagen: %s",
                           aktueller_modus, fehler.technisch)
            if versuch == 0 and ersatz:
                warnungen.append(
                    f"{fehler.benutzer_text} Es wurde automatisch auf "
                    f"'{ersatz}' umgeschaltet.")
                continue
            raise

    raise StadionheftFehler(
        "Keine nutzbare Datenquelle.",
        benutzer_text="Es konnte keine Datenquelle verwendet werden.",
        hinweis="Bitte datenquelle.modus in config/config.yaml pruefen.")


def _brauchbar(ergebnis: list[MannschaftsDaten]) -> bool:
    """Steckt in dem Ergebnis ueberhaupt Inhalt fuer ein Heft?

    Es genuegt, wenn *eine* Mannschaft etwas geliefert hat -- bei den unteren
    Mannschaften ist eine leere Torschuetzenliste voellig normal.
    """
    return any(d.tabelle or d.torjaeger or d.spieler or d.naechstes_spiel
               for d in ergebnis)


# ---------------------------------------------------------------------------
# Hefterstellung
# ---------------------------------------------------------------------------

def heft_erstellen(konfiguration: Konfiguration,
                   mannschaften: list[str],
                   *,
                   spieltag: str = "",
                   datenquelle: str | None = None,
                   dateiname: str = "",
                   erzeugt_von: str = "",
                   titelspiel_von: str = "",
                   nas_hochladen: bool | None = None,
                   heftplan: list[dict] | None = None) -> BauErgebnis:
    """Erstellt ein komplettes Stadionheft."""
    start = datetime.now()

    if not mannschaften:
        raise StadionheftFehler(
            "Keine Mannschaft ausgewaehlt.",
            benutzer_text="Bitte mindestens eine Mannschaft auswählen.")

    daten, verwendete_quelle, warnungen = daten_holen(
        konfiguration, mannschaften, datenquelle)

    ausgabe = Ausgabe(
        saison=konfiguration.saison,
        spieltag=spieltag,
        mannschaften=daten,
        erstellt_am=start.isoformat(timespec="seconds"),
        erzeugt_von=erzeugt_von,
        warnungen=list(warnungen) + list(konfiguration.warnungen),
    )
    ausgabe.titelspiel = _titelspiel_bestimmen(daten, titelspiel_von)

    return _bauen(konfiguration, ausgabe, dateiname=dateiname,
                  nas_hochladen=nas_hochladen, heftplan=heftplan, start=start)


def heft_aus_snapshot(konfiguration: Konfiguration, snapshot: Path,
                      *, dateiname: str = "",
                      nas_hochladen: bool | None = None) -> BauErgebnis:
    """Baut ein Heft exakt aus einem frueheren Snapshot neu auf."""
    start = datetime.now()
    pfad = Path(snapshot)
    if not pfad.exists():
        raise VorlageFehltFehler(
            f"Snapshot {pfad} nicht gefunden.",
            benutzer_text=f"Die Snapshot-Datei '{pfad.name}' wurde nicht gefunden.")
    try:
        ausgabe = Ausgabe.from_dict(json.loads(pfad.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as fehler:
        raise VorlageFehltFehler(
            f"{pfad}: {fehler}",
            benutzer_text=f"Die Snapshot-Datei '{pfad.name}' ist beschaedigt.") from fehler

    logger().info("Baue Heft aus Snapshot vom %s neu auf.", ausgabe.erstellt_am)
    # Der im Snapshot festgehaltene Heftplan hat Vorrang: nur so entsteht
    # wirklich dasselbe Heft, auch wenn config/heftplan.yaml sich geaendert hat.
    if not ausgabe.heftplan:
        logger().warning(
            "Der Snapshot enthaelt keinen Heftplan (aeltere Version) - "
            "es wird der aktuelle Heftplan verwendet.")
    return _bauen(konfiguration, ausgabe, dateiname=dateiname,
                  nas_hochladen=nas_hochladen,
                  heftplan=ausgabe.heftplan or None, start=start)


# ---------------------------------------------------------------------------
# Interner Bauvorgang
# ---------------------------------------------------------------------------

def _bauen(konfiguration: Konfiguration, ausgabe: Ausgabe, *,
           dateiname: str, nas_hochladen: bool | None,
           heftplan: list[dict] | None, start: datetime) -> BauErgebnis:

    plan = heftplan if heftplan is not None else heftplan_laden()
    ausgabe.heftplan = plan
    arbeitsordner = konfiguration.arbeits_ordner / _laufordner(start)
    renderer = SeitenRenderer(konfiguration, arbeitsordner)

    warnungen = list(ausgabe.warnungen)
    for mannschaft in ausgabe.mannschaften:
        warnungen.extend(f"{mannschaft.anzeigename}: {w}" for w in mannschaft.warnungen)

    montageliste = _plan_abarbeiten(konfiguration, renderer, ausgabe, plan, warnungen)

    ziel = konfiguration.ausgabe_ordner / (dateiname or _dateiname(konfiguration, ausgabe))
    ergebnis_montage: MontageErgebnis = zusammenfuegen(montageliste, ziel)
    warnungen.extend(ergebnis_montage.warnungen)

    ergebnis = BauErgebnis(
        pdf=ziel,
        seitenzahl=ergebnis_montage.seitenzahl,
        warnungen=warnungen,
        verwendete_quelle=(ausgabe.mannschaften[0].quelle
                           if ausgabe.mannschaften else ""),
    )

    if konfiguration.get("ausgabe.snapshot_speichern", True):
        ergebnis.snapshot = _snapshot_schreiben(ziel, ausgabe)

    hochladen = (bool(konfiguration.get("nas.aktiv", False))
                 if nas_hochladen is None else nas_hochladen)
    if hochladen:
        try:
            ablage = NasAblage(konfiguration).ablegen(ziel)
            ergebnis.nas_ziel = ablage.ziel
            logger().info("%s", ablage.meldung)
        except StadionheftFehler as fehler:
            # Das Heft ist fertig - ein NAS-Problem ist nur eine Warnung.
            logger().error("NAS-Ablage fehlgeschlagen: %s", fehler.technisch)
            warnungen.append(
                f"{fehler.benutzer_text} {fehler.hinweis or ''}".strip())

    ergebnis.dauer_sekunden = (datetime.now() - start).total_seconds()
    logger().info("Fertig: %s (%d Seiten, %.1f s)",
                  ziel.name, ergebnis.seitenzahl, ergebnis.dauer_sekunden)
    return ergebnis


def _plan_abarbeiten(konfiguration: Konfiguration, renderer: SeitenRenderer,
                     ausgabe: Ausgabe, plan: list[dict],
                     warnungen: list[str]) -> list[Heftseite]:
    """Uebersetzt den Heftplan in eine flache Liste zu montierender PDFs."""
    liste: list[Heftseite] = []
    nummer = 0

    def naechste() -> int:
        nonlocal nummer
        nummer += 1
        return nummer

    for eintrag in plan:
        typ = str(eintrag.get("typ", ""))

        if typ == "titelseite":
            titelbild = _titelbild(konfiguration)
            liste.append(Heftseite(renderer.titelseite(ausgabe, titelbild),
                                   "Titelseite"))
            naechste()

        elif typ == "freitext":
            titel = str(eintrag.get("titel", "Vorwort"))
            quelle = str(eintrag.get("quelle", ""))
            text = _textdatei_lesen(konfiguration, quelle)
            if not text and not eintrag.get("optional", True):
                raise VorlageFehltFehler(
                    f"Textdatei {quelle} fehlt.",
                    benutzer_text=f"Die Textdatei für '{titel}' wurde nicht gefunden.",
                    hinweis=f"Erwartet: daten/{quelle}")
            if not text:
                warnungen.append(
                    f"'{titel}': keine Textdatei gefunden (daten/{quelle}) – "
                    f"die Seite bleibt leer.")
            liste.append(Heftseite(
                renderer.freitextseite(titel, text, ausgabe, naechste(), quelle),
                titel))

        elif typ == "kontakte":
            abschnitte = _kontakte_lesen(konfiguration)
            if not abschnitte:
                warnungen.append(
                    "Keine Kontaktdaten gefunden (config/kontakte.yaml) – "
                    "die Seite bleibt leer.")
            liste.append(Heftseite(
                renderer.kontaktseite(abschnitte, ausgabe, naechste()),
                "Kontaktlisten"))

        elif typ == "impressum":
            liste.append(Heftseite(
                renderer.impressumsseite(_impressum_felder(konfiguration),
                                         ausgabe, naechste()),
                "Impressum"))

        elif typ == "trennseite":
            platzhalter = MannschaftsDaten(
                gruppe=str(eintrag.get("gruppe", "")),
                untertitel=str(eintrag.get("untertitel", "")),
                liga=str(eintrag.get("liga", "")))
            liste.append(Heftseite(renderer.trennseite(platzhalter, naechste()),
                                   "Trennseite"))

        elif typ == "pdf":
            liste.append(_pdf_eintrag(konfiguration, eintrag))

        elif typ == "werbeblock":
            liste.extend(_werbeblock_eintraege(konfiguration, eintrag, warnungen))

        elif typ == "mannschaftsbloecke":
            zwischen = eintrag.get("trenner_zwischen") or []
            for index, daten in enumerate(ausgabe.mannschaften):
                if index > 0:
                    for z in zwischen:
                        if str(z.get("typ")) == "werbeblock":
                            liste.extend(_werbeblock_eintraege(
                                konfiguration, z, warnungen))
                        else:
                            liste.append(_pdf_eintrag(konfiguration, z))
                mannschaft = konfiguration.mannschaft(daten.schluessel)
                for art in mannschaft.seiten:
                    if art not in SEITEN_VORLAGEN:
                        continue
                    liste.append(Heftseite(
                        renderer.mannschaftsseite(art, daten, ausgabe, naechste()),
                        f"{daten.anzeigename} – {art}"))

    return liste


def _werbeblock_eintraege(konfiguration: Konfiguration, eintrag: dict,
                          warnungen: list[str]) -> list[Heftseite]:
    """Baut einen Werbeblock aus allen gueltigen Anzeigen eines Ordners."""
    quelle = str(eintrag.get("ordner") or eintrag.get("quelle") or "")
    pfad = Path(quelle)
    if not pfad.is_absolute():
        pfad = konfiguration.daten_wurzel / quelle

    anzeigen, hinweise = werbeblock(pfad)
    warnungen.extend(hinweise)

    if not anzeigen and not bool(eintrag.get("optional", True)):
        raise VorlageFehltFehler(
            f"Werbeordner {pfad} liefert keine Anzeige.",
            benutzer_text=f"Im Werbeordner '{pfad.name}' liegt keine gültige Anzeige.",
            hinweis=f"Erwartet werden PDF-Dateien in: {pfad}")

    return [Heftseite(pfad=a.pfad, beschreibung=f"Werbung: {a.titel}", pflicht=False)
            for a in anzeigen]


def _pdf_eintrag(konfiguration: Konfiguration, eintrag: dict) -> Heftseite:
    quelle = str(eintrag.get("quelle", ""))
    pfad = Path(quelle)
    if not pfad.is_absolute():
        pfad = konfiguration.daten_wurzel / quelle
    return Heftseite(
        pfad=pfad,
        beschreibung=str(eintrag.get("bemerkung") or pfad.name),
        seiten=str(eintrag.get("seiten", "")),
        pflicht=not bool(eintrag.get("optional", True)),
    )


# ---------------------------------------------------------------------------
# Kleine Helfer
# ---------------------------------------------------------------------------

def _titelspiel_bestimmen(daten: list[MannschaftsDaten], bevorzugt: str = "") -> Spiel:
    """Die Partie fuer die Titelseite: bevorzugte Mannschaft, sonst die erste
    mit bekanntem naechsten Heimspiel, sonst die erste ueberhaupt."""
    kandidaten = list(daten)
    if bevorzugt:
        kandidaten.sort(key=lambda d: d.schluessel != bevorzugt)
    for eintrag in kandidaten:
        if eintrag.naechstes_spiel and eintrag.naechstes_spiel.heimspiel:
            return eintrag.naechstes_spiel
    for eintrag in kandidaten:
        if eintrag.naechstes_spiel:
            return eintrag.naechstes_spiel
    return Spiel()


def _dateiname(konfiguration: Konfiguration, ausgabe: Ausgabe) -> str:
    vorlage = str(konfiguration.get("ausgabe.dateiname", "{datum_kompakt}_Heft.pdf"))
    spiel = ausgabe.titelspiel
    zeitpunkt = spiel.anstoss_dt if spiel and spiel.anstoss_dt else datetime.now()
    werte = {
        "datum": f"{zeitpunkt:%d.%m.%Y}",
        "datum_kompakt": f"{zeitpunkt:%Y%m%d}",
        "saison": (ausgabe.saison or "").replace("/", "-"),
        "spieltag": ausgabe.spieltag or "",
        "mannschaften": "-".join(m.schluessel for m in ausgabe.mannschaften),
    }
    try:
        name = vorlage.format(**werte)
    except KeyError as fehler:
        logger().warning("Unbekannter Platzhalter im Dateinamen: %s", fehler)
        name = f"{werte['datum_kompakt']}_Stadionheft.pdf"
    name = "_".join(name.split())
    return name if name.lower().endswith(".pdf") else name + ".pdf"


def _laufordner(start: datetime) -> str:
    return f"lauf_{start:%Y%m%d_%H%M%S}"


def _snapshot_schreiben(pdf: Path, ausgabe: Ausgabe) -> Path:
    ziel = pdf.with_name(pdf.stem + "_snapshot.json")
    try:
        ziel.write_text(json.dumps(ausgabe.to_dict(), ensure_ascii=False, indent=2),
                        encoding="utf-8")
        logger().info("Snapshot gespeichert: %s", ziel.name)
    except OSError as fehler:
        logger().warning("Snapshot konnte nicht geschrieben werden: %s", fehler)
    return ziel


def _titelbild(konfiguration: Konfiguration) -> Path | None:
    for name in ("titelbild.jpg", "titelbild.jpeg", "titelbild.png"):
        pfad = konfiguration.eingabe_ordner / name
        if pfad.exists():
            return pfad
    return None


def _textdatei_lesen(konfiguration: Konfiguration, quelle: str) -> str:
    if not quelle:
        return ""
    pfad = Path(quelle)
    if not pfad.is_absolute():
        pfad = konfiguration.daten_wurzel / quelle
    if not pfad.exists():
        return ""
    for kodierung in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return pfad.read_text(encoding=kodierung).strip()
        except UnicodeDecodeError:
            continue
    return ""


def _kontakte_lesen(konfiguration: Konfiguration) -> list[dict]:
    from .config import PROJEKT_WURZEL
    for name in ("kontakte.yaml", "kontakte.example.yaml"):
        pfad = PROJEKT_WURZEL / "config" / name
        if pfad.exists():
            try:
                daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
                return list(daten.get("abschnitte", []))
            except yaml.YAMLError as fehler:
                logger().warning("kontakte.yaml fehlerhaft: %s", fehler)
                return []
    return []


def _impressum_felder(konfiguration: Konfiguration) -> list[dict]:
    roh = konfiguration.get("impressum") or {}
    if isinstance(roh, dict) and roh:
        return [{"titel": titel, "text": str(text)} for titel, text in roh.items()]
    return [
        {"titel": "Herausgeber",
         "text": f"{konfiguration.vereinsname}\nWörnitzstraße 4\n"
                 f"86609 Donauwörth/Wörnitzstein"},
        {"titel": "Redaktion", "text": "TODO: Namen in config.yaml unter "
                                       "'impressum' eintragen"},
        {"titel": "Satz und Gestaltung", "text": "TODO"},
        {"titel": "Druck", "text": "TODO"},
    ]
