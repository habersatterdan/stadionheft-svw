"""Ablaufsteuerung: von der Mannschaftsauswahl zu den fertigen Dateien.

Der komplette Weg in einer Funktion, damit Weboberflaeche und Kommandozeile
garantiert dasselbe tun:

    1. Daten je ausgewaehlter Mannschaft holen (FuPa / CSV / Demo)
    2. Dazu jeweils die Zahlen des naechsten Gegners
    3. Die Seiten setzen und **je Mannschaft zu einer PDF-Datei** montieren
    4. Alle Dateien zusaetzlich in ein ZIP packen
    5. Snapshot der Rohdaten schreiben -> Reproduzierbarkeit

Warum eine Datei je Mannschaft und kein fertiges Heft?
------------------------------------------------------
Das Heft wird von Hand zusammengebaut -- mit Titelseite, Vorwort, Werbung,
Kontaktlisten und Impressum, die alle nicht aus FuPa kommen. Dieses Programm
liefert genau den Teil, der sich automatisieren laesst: die aktuellen Zahlen,
druckfertig gesetzt, je Mannschaft ein Stueck. Wer das Heft baut, legt die
Dateien an die richtige Stelle -- fertig.

Reproduzierbarkeit
------------------
Jeder Lauf legt eine Datei ``*_snapshot.json`` mit genau den Daten ab, aus
denen die PDFs entstanden sind. Mit ``dateien_aus_snapshot(...)`` entstehen
daraus jederzeit wieder dieselben Dateien -- ohne erneuten Zugriff auf FuPa.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .config import Konfiguration, Mannschaft
from .errors import StadionheftFehler, VorlageFehltFehler
from .logging_setup import logger
from .models import Ausgabe, MannschaftsDaten
from .render.assemble import Heftseite, zusammenfuegen
from .render.pages import SEITEN_VORLAGEN, STANDARD_SEITEN, SeitenRenderer
from .sources.base import quelle_erzeugen
from .storage.nas import NasAblage


@dataclass
class Mannschaftsdatei:
    """Eine fertige PDF-Datei fuer genau eine Mannschaft."""

    schluessel: str
    anzeigename: str
    pdf: Path
    seitenzahl: int = 0
    gegner: str = ""
    anstoss: str = ""
    seiten: list[str] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)

    def als_dict(self) -> dict:
        return {
            "schluessel": self.schluessel,
            "mannschaft": self.anzeigename,
            "dateiname": self.pdf.name,
            "pfad": str(self.pdf),
            "seitenzahl": self.seitenzahl,
            "gegner": self.gegner,
            "anstoss": self.anstoss,
            "seiten": list(self.seiten),
            "warnungen": list(self.warnungen),
        }


@dataclass
class LaufErgebnis:
    """Was bei einem Knopfdruck herausgekommen ist."""

    dateien: list[Mannschaftsdatei] = field(default_factory=list)
    ordner: Path | None = None
    archiv: Path | None = None
    snapshot: Path | None = None
    nas_ziel: str = ""
    warnungen: list[str] = field(default_factory=list)
    verwendete_quelle: str = ""
    stand: str = ""
    dauer_sekunden: float = 0.0

    @property
    def seitenzahl(self) -> int:
        return sum(d.seitenzahl for d in self.dateien)

    def als_dict(self) -> dict:
        return {
            "dateien": [d.als_dict() for d in self.dateien],
            "ordner": str(self.ordner) if self.ordner else "",
            "archiv": str(self.archiv) if self.archiv else "",
            "snapshot": str(self.snapshot) if self.snapshot else "",
            "nas_ziel": self.nas_ziel,
            "warnungen": list(self.warnungen),
            "quelle": self.verwendete_quelle,
            "stand": self.stand,
            "seitenzahl": self.seitenzahl,
            "dauer_sekunden": round(self.dauer_sekunden, 1),
        }


# ---------------------------------------------------------------------------
# Daten holen
# ---------------------------------------------------------------------------

def daten_holen(konfiguration: Konfiguration, schluessel: list[str],
                modus: str | None = None
                ) -> tuple[list[MannschaftsDaten], str, list[str]]:
    """Holt die Daten aller gewaehlten Mannschaften.

    Bei einem Ausfall der primaeren Quelle wird -- falls konfiguriert -- einmal
    komplett auf die Ersatzquelle umgeschaltet. Bewusst *komplett* und nicht je
    Mannschaft: Dateien, deren Zahlen aus verschiedenen Quellen mit
    verschiedenen Staenden stammen, waeren schwer nachvollziehbar.

    Als Ausfall gilt nicht nur ein Fehler, sondern auch eine Quelle, die zwar
    antwortet, aber **nichts liefert**. Lauter leere Seiten waeren formal ein
    Erfolg und praktisch wertlos.

    Eine einzelne Mannschaft, fuer die es keine Daten gibt, ist dagegen **kein**
    Ausfall. Sie wird uebersprungen und als Warnung gemeldet. Alles andere
    waere unbrauchbar: Solange nicht alle fuenf Mannschaften angebunden sind,
    duerfte sonst nie eine einzige Datei entstehen.
    """
    primaer = modus or str(konfiguration.get("datenquelle.modus", "api"))
    ersatz = str(konfiguration.get("datenquelle.fallback_modus", "") or "")
    warnungen: list[str] = []
    bestes: tuple[list[MannschaftsDaten], list, str] | None = None

    for versuch, aktueller_modus in enumerate([primaer, ersatz]):
        if not aktueller_modus:
            continue
        if versuch == 1:
            logger().warning("Wechsle auf Ersatz-Datenquelle '%s'.", aktueller_modus)
        quelle = quelle_erzeugen(aktueller_modus, konfiguration)

        ergebnis, ausgefallen = _je_mannschaft_holen(
            konfiguration, quelle, schluessel, aktueller_modus)

        # Keine einzige Mannschaft durchgekommen: Das liegt an der Quelle,
        # nicht an den Mannschaften.
        if not ergebnis:
            fehler = ausgefallen[0][1]
            logger().error("Datenquelle '%s' fehlgeschlagen: %s",
                           aktueller_modus, fehler.technisch)
            if versuch == 0 and ersatz:
                warnungen.append(
                    f"{fehler.benutzer_text} Es wurde automatisch auf "
                    f"'{ersatz}' umgeschaltet.")
                continue
            if bestes:
                break
            raise fehler

        if versuch == 0 and ersatz and not _brauchbar(ergebnis):
            logger().warning(
                "Datenquelle '%s' hat geantwortet, aber keine Spieldaten "
                "geliefert.", aktueller_modus)
            warnungen.append(
                f"Von '{aktueller_modus}' kamen keine verwertbaren Daten. "
                f"Es wurde automatisch auf '{ersatz}' umgeschaltet.")
            continue

        if bestes is None or len(ergebnis) > len(bestes[0]):
            bestes = (ergebnis, ausgefallen, aktueller_modus)

        # Hat die primaere Quelle einzelne Mannschaften nicht bedient, ist
        # erst die Ersatzquelle dran: Vielleicht kann die alle. Gemischte
        # Staende aus zwei Quellen wollen wir nicht -- aber eine Datei
        # weniger auch nicht. Liefert die Ersatzquelle nicht mehr, bleibt es
        # beim Ergebnis der primaeren.
        if versuch == 0 and ersatz and ausgefallen:
            logger().info(
                "'%s' hat %d Mannschaft(en) nicht geliefert - erst einmal "
                "'%s' versuchen.", aktueller_modus, len(ausgefallen), ersatz)
            continue

        break

    if bestes is None:
        raise StadionheftFehler(
            "Keine nutzbare Datenquelle.",
            benutzer_text="Es konnte keine Datenquelle verwendet werden.",
            hinweis="Bitte datenquelle.modus in config/config.yaml pruefen.")

    ergebnis, ausgefallen, gewaehlter_modus = bestes
    for name, fehler in ausgefallen:
        anzeigename = konfiguration.mannschaft(name).anzeigename
        warnungen.append(
            f"Für {anzeigename} gibt es keine Daten – es entsteht keine "
            f"Datei. {fehler.benutzer_text}")
    return ergebnis, gewaehlter_modus, warnungen


def _je_mannschaft_holen(konfiguration: Konfiguration, quelle, schluessel: list[str],
                         modus: str
                         ) -> tuple[list[MannschaftsDaten],
                                    list[tuple[str, StadionheftFehler]]]:
    """Holt jede Mannschaft fuer sich und sammelt die Ausfaelle ein."""
    ergebnis: list[MannschaftsDaten] = []
    ausgefallen: list[tuple[str, StadionheftFehler]] = []

    for name in schluessel:
        mannschaft: Mannschaft = konfiguration.mannschaft(name)
        logger().info("Lade Daten fuer %s (Quelle: %s) ...",
                      mannschaft.anzeigename, modus)
        try:
            ergebnis.append(quelle.hole(mannschaft))
        except StadionheftFehler as fehler:
            logger().warning("%s uebersprungen: %s",
                             mannschaft.anzeigename, fehler.technisch)
            ausgefallen.append((name, fehler))

    return ergebnis, ausgefallen


def _brauchbar(ergebnis: list[MannschaftsDaten]) -> bool:
    """Steckt in dem Ergebnis ueberhaupt Inhalt?

    Es genuegt, wenn *eine* Mannschaft etwas geliefert hat -- bei den unteren
    Mannschaften ist eine leere Torschuetzenliste voellig normal.
    """
    return any(d.tabelle or d.torjaeger or d.spieler or d.naechstes_spiel
               for d in ergebnis)


# ---------------------------------------------------------------------------
# Der Lauf
# ---------------------------------------------------------------------------

def dateien_erstellen(konfiguration: Konfiguration,
                      mannschaften: list[str],
                      *,
                      spieltag: str = "",
                      datenquelle: str | None = None,
                      erzeugt_von: str = "",
                      frisch: bool = False) -> LaufErgebnis:
    """Erzeugt je gewaehlter Mannschaft eine druckfertige PDF-Datei."""
    start = datetime.now()

    if not mannschaften:
        raise StadionheftFehler(
            "Keine Mannschaft ausgewaehlt.",
            benutzer_text="Bitte mindestens eine Mannschaft auswählen.")

    if frisch:
        # Ein ausdruecklicher Knopf "frische Daten" muss auch frische Daten
        # holen -- sonst ist er eine Luege.
        konfiguration.roh.setdefault("datenquelle", {}).setdefault("cache", {})
        konfiguration.roh["datenquelle"]["cache"]["aktiv"] = False
        logger().info("Zwischenspeicher fuer diesen Lauf abgeschaltet.")

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
    return _bauen(konfiguration, ausgabe, start=start)


def dateien_aus_snapshot(konfiguration: Konfiguration,
                         snapshot: Path) -> LaufErgebnis:
    """Baut die Dateien exakt aus einem frueheren Lauf neu auf."""
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
            benutzer_text=f"Die Snapshot-Datei '{pfad.name}' ist beschaedigt."
        ) from fehler

    logger().info("Baue Dateien aus Snapshot vom %s neu auf.", ausgabe.erstellt_am)
    return _bauen(konfiguration, ausgabe, start=start)


# ---------------------------------------------------------------------------
# Interner Bauvorgang
# ---------------------------------------------------------------------------

def _bauen(konfiguration: Konfiguration, ausgabe: Ausgabe,
           *, start: datetime) -> LaufErgebnis:
    arbeitsordner = konfiguration.arbeits_ordner / _laufordner(start)
    renderer = SeitenRenderer(konfiguration, arbeitsordner)

    ziel_ordner = konfiguration.ausgabe_ordner / _ausgabe_ordner(ausgabe, start)
    ziel_ordner.mkdir(parents=True, exist_ok=True)

    warnungen = list(ausgabe.warnungen)
    ergebnis = LaufErgebnis(ordner=ziel_ordner,
                            verwendete_quelle=(ausgabe.mannschaften[0].quelle
                                               if ausgabe.mannschaften else ""))

    for daten in ausgabe.mannschaften:
        seiten = seitenfolge(daten)
        if not ausgabe.seitenfolge:
            ausgabe.seitenfolge = list(seiten)

        montageliste: list[Heftseite] = []
        for nummer, art in enumerate(seiten, 1):
            montageliste.append(Heftseite(
                renderer.mannschaftsseite(art, daten, nummer),
                f"{daten.anzeigename} – {art}"))

        ziel = ziel_ordner / _dateiname(konfiguration, daten, ausgabe, start)
        montage = zusammenfuegen(montageliste, ziel)
        warnungen.extend(montage.warnungen)
        warnungen.extend(f"{daten.anzeigename}: {w}" for w in daten.warnungen)

        ergebnis.dateien.append(Mannschaftsdatei(
            schluessel=daten.schluessel,
            anzeigename=daten.anzeigename,
            pdf=ziel,
            seitenzahl=montage.seitenzahl,
            gegner=daten.gegner,
            anstoss=(daten.naechstes_spiel.datum if daten.naechstes_spiel else ""),
            seiten=list(seiten),
            warnungen=list(daten.warnungen),
        ))
        logger().info("%s: %s (%d Seiten)", daten.anzeigename, ziel.name,
                      montage.seitenzahl)

    ergebnis.archiv = _archiv_schreiben(ergebnis.dateien, ziel_ordner,
                                        konfiguration, ausgabe, start)
    if konfiguration.get("ausgabe.snapshot_speichern", True):
        ergebnis.snapshot = _snapshot_schreiben(ziel_ordner, ausgabe, start)

    if konfiguration.get("nas.aktiv", False):
        try:
            ablage = NasAblage(konfiguration).ablegen_mehrere(
                [d.pdf for d in ergebnis.dateien])
            ergebnis.nas_ziel = ablage.ziel
            logger().info("%s", ablage.meldung)
            if not ablage.erfolgreich:
                warnungen.append(ablage.meldung)
        except StadionheftFehler as fehler:
            # Die Dateien sind fertig - ein NAS-Problem ist nur eine Warnung.
            logger().error("NAS-Ablage fehlgeschlagen: %s", fehler.technisch)
            warnungen.append(f"{fehler.benutzer_text} {fehler.hinweis or ''}".strip())

    ergebnis.warnungen = warnungen
    ergebnis.stand = _stand(ausgabe)
    ergebnis.dauer_sekunden = (datetime.now() - start).total_seconds()
    logger().info("Fertig: %d Dateien in %s (%.1f s)",
                  len(ergebnis.dateien), ziel_ordner, ergebnis.dauer_sekunden)
    return ergebnis


def seitenfolge(daten: MannschaftsDaten) -> list[str]:
    """Welche Seiten die Datei dieser Mannschaft bekommt.

    Grundsaetzlich bei allen gleich. Nur wenn der Gegner in einer **anderen**
    Liga spielt (Pokal), kommen dessen Tabelle und Torschuetzenliste dazu --
    in derselben Liga waeren es dieselben Zahlen zweimal.
    """
    seiten = list(STANDARD_SEITEN)
    gegner = daten.gegner_daten
    if gegner and gegner.gefunden and not daten.gleiche_liga:
        if gegner.tabelle:
            seiten.insert(seiten.index("torjaeger") + 1, "tabelle_gegner")
        if gegner.torjaeger:
            stelle = seiten.index("tabelle_gegner") + 1 \
                if "tabelle_gegner" in seiten else seiten.index("torjaeger") + 1
            seiten.insert(stelle, "torjaeger_gegner")
    return [s for s in seiten if s in SEITEN_VORLAGEN]


# ---------------------------------------------------------------------------
# Kleine Helfer
# ---------------------------------------------------------------------------

def _dateiname(konfiguration: Konfiguration, daten: MannschaftsDaten,
               ausgabe: Ausgabe, start: datetime) -> str:
    """Der Dateiname einer Mannschaftsdatei.

    Er muss zwei Dinge leisten: Beim Sortieren im Ordner sollen die Dateien
    eines Spieltags beieinanderstehen, und wer sie sieht, soll ohne Oeffnen
    wissen, welche Mannschaft gegen wen.
    """
    vorlage = str(konfiguration.get("ausgabe.dateiname",
                                    "{datum}_{mannschaft}_gegen_{gegner}.pdf"))
    spiel = daten.naechstes_spiel
    zeitpunkt = spiel.anstoss_dt if spiel and spiel.anstoss_dt else start
    werte = {
        "datum": f"{zeitpunkt:%Y-%m-%d}",
        "datum_kompakt": f"{zeitpunkt:%Y%m%d}",
        "datum_deutsch": f"{zeitpunkt:%d.%m.%Y}",
        "saison": (ausgabe.saison or "").replace("/", "-"),
        "spieltag": ausgabe.spieltag or "",
        "mannschaft": daten.anzeigename or daten.schluessel,
        "schluessel": daten.schluessel,
        "gegner": daten.gegner or "offen",
    }
    try:
        name = vorlage.format(**werte)
    except KeyError as fehler:
        logger().warning("Unbekannter Platzhalter im Dateinamen: %s", fehler)
        name = f"{werte['datum']}_{werte['schluessel']}.pdf"

    # Sicherung gegen eine Vorlage aus der Zeit des Gesamthefts: Enthält sie
    # nichts, was die Mannschaften unterscheidet, bekaemen alle denselben
    # Namen -- und im selben Ordner bliebe nur die letzte Datei uebrig.
    # Das faellt sonst erst auf, wenn vier von fuenf Mannschaften fehlen.
    if not any(f"{{{p}}}" in vorlage for p in ("mannschaft", "schluessel", "gegner")):
        stamm, punkt, endung = name.rpartition(".")
        name = f"{stamm or name}_{werte['schluessel']}{punkt}{endung}"
        logger().warning(
            "ausgabe.dateiname unterscheidet die Mannschaften nicht ('%s'). "
            "Der Schluessel wird angehaengt. Besser in config.yaml auf "
            "'{datum}_{mannschaft}_gegen_{gegner}.pdf' umstellen.", vorlage)

    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return _sauberer_name(name)


def _sauberer_name(name: str) -> str:
    """Macht aus einem Namen etwas, das auf jedem System eine Datei sein darf.

    Die Dateien landen auf einer NAS und werden von Windows, macOS, Linux und
    Handys geoeffnet. Umlaute sind dabei kein Problem, Schraegstriche und
    Doppelpunkte schon.
    """
    ersetzt = name
    for zeichen in '/\\:*?"<>|':
        ersetzt = ersetzt.replace(zeichen, "-")
    return "_".join(ersetzt.split())


def _ausgabe_ordner(ausgabe: Ausgabe, start: datetime) -> str:
    """Je Lauf ein eigener Unterordner -- sonst vermischen sich die Spieltage."""
    spiele = [m.naechstes_spiel for m in ausgabe.mannschaften if m.naechstes_spiel]
    termine = [s.anstoss_dt for s in spiele if s.anstoss_dt]
    zeitpunkt = min(termine) if termine else start
    return f"{zeitpunkt:%Y-%m-%d}_Spieltag"


def _laufordner(start: datetime) -> str:
    return f"lauf_{start:%Y%m%d_%H%M%S}"


def _archiv_schreiben(dateien: list[Mannschaftsdatei], ordner: Path,
                      konfiguration: Konfiguration, ausgabe: Ausgabe,
                      start: datetime) -> Path | None:
    """Alle Mannschaftsdateien in einem ZIP -- ein Download statt fuenf."""
    if not dateien:
        return None
    zeitpunkt = min((d.pdf.stat().st_mtime for d in dateien if d.pdf.exists()),
                    default=start.timestamp())
    name = _sauberer_name(f"{ordner.name}_alle-Mannschaften.zip")
    ziel = ordner / name
    try:
        with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as archiv:
            for datei in dateien:
                if datei.pdf.exists():
                    archiv.write(datei.pdf, arcname=datei.pdf.name)
            archiv.writestr("UEBERSICHT.txt",
                            _uebersicht(dateien, ausgabe, zeitpunkt))
    except OSError as fehler:
        logger().warning("ZIP konnte nicht geschrieben werden: %s", fehler)
        return None
    return ziel


def _uebersicht(dateien: list[Mannschaftsdatei], ausgabe: Ausgabe,
                zeitpunkt: float) -> str:
    """Ein Beipackzettel im ZIP fuer die Person, die das Heft zusammenbaut."""
    zeilen = [
        "Stadionheft - Bausteine aus FuPa",
        "=" * 50,
        f"Erzeugt am : {_lesbar(ausgabe.erstellt_am)}",
        f"Saison     : {ausgabe.saison or '-'}",
        "",
        "Diese Dateien sind druckfertig: A5, 3 mm Anschnitt, Schnittmarken.",
        "Jede Datei enthält die Seiten einer Mannschaft in dieser Reihenfolge:",
        "",
    ]
    zeilen += [f"  {nr}. {_seitenname(art)}"
               for nr, art in enumerate(ausgabe.seitenfolge, 1)]
    zeilen += ["", "Dateien", "-" * 50]
    for datei in dateien:
        zeilen.append(f"  {datei.pdf.name}")
        zeilen.append(f"      {datei.anzeigename}, {datei.seitenzahl} Seiten"
                      + (f", gegen {datei.gegner}" if datei.gegner else "")
                      + (f" am {datei.anstoss}" if datei.anstoss else ""))
        for warnung in datei.warnungen:
            zeilen.append(f"      ACHTUNG: {warnung}")
    zeilen.append("")
    return "\n".join(zeilen)


SEITENNAMEN = {
    "trenner": "Trennseite mit Mannschaftsname",
    "vergleich": "Das nächste Spiel (Gegenüberstellung beider Mannschaften)",
    "tabelle": "Tabelle der Liga",
    "torjaeger": "Torschützenliste der Liga",
    "spielerstatistik": "Spielerstatistik der eigenen Mannschaft",
    "gegner": "Der Gegner mit seinem Kader",
    "bilanz": "Saisonbilanz in Zahlen",
    "tabelle_gegner": "Tabelle der Liga des Gegners",
    "torjaeger_gegner": "Torschützenliste der Liga des Gegners",
}


def _seitenname(art: str) -> str:
    return SEITENNAMEN.get(art, art)


def _lesbar(iso: str) -> str:
    try:
        return f"{datetime.fromisoformat(iso):%d.%m.%Y, %H:%M} Uhr"
    except (ValueError, TypeError):
        return iso or "-"


def _stand(ausgabe: Ausgabe) -> str:
    """Der aelteste Abrufzeitpunkt -- der bestimmt, wie aktuell das Ganze ist."""
    zeiten = [m.abgerufen_am for m in ausgabe.mannschaften if m.abgerufen_am]
    return _lesbar(min(zeiten)) if zeiten else _lesbar(ausgabe.erstellt_am)


def _snapshot_schreiben(ordner: Path, ausgabe: Ausgabe, start: datetime) -> Path:
    ziel = ordner / f"{ordner.name}_snapshot.json"
    ziel.write_text(json.dumps(ausgabe.to_dict(), ensure_ascii=False, indent=2),
                    encoding="utf-8")
    logger().debug("Snapshot geschrieben: %s", ziel)
    return ziel
