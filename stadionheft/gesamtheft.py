"""Das gesamte Stadionheft aus einem fertigen Ausgabe-Ordner der NAS.

Der zweite Knopf. Der erste erzeugt die FuPa-Seiten und legt den
Ausgabe-Ordner an; danach kommen von Hand Titelbild, Vorwort und Berichte
hinein. Aus diesem Ordner baut dieser Teil das druckfertige Heft:

* Deckblatt (neu gesetzt -- mit dem Titelbild aus dem Ausgabe-Ordner)
* Vorwort
* je Mannschaft: die FuPa-Seiten **mit** Kopf-/Fussbalken, danach alles, was
  im Mannschaftsordner liegt (PDF, Bild, Word, Text)
* weitere Ordner (z. B. Jugend) genauso
* Ansprechpartner (aus der Textdatei im Saisonordner)
* Werbung aus dem Werbe-Ordner, zwischen die Mannschaften verteilt; die
  letzte Anzeige kommt auf die Rueckseite. Leerseiten fuellen auf ein
  Vielfaches von 4 auf -- ein geheftetes Heft hat immer 4er-Seitenzahlen.

Die Reihenfolge steht danach als ``Heftplan.txt`` im Ausgabe-Ordner. Wer sie
dort aendert und erneut baut, bekommt genau diese Reihenfolge.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from .build import seitenfolge
from .config import Konfiguration
from .errors import NasFehler, RenderFehler, StadionheftFehler
from .logging_setup import logger
from .models import Ausgabe, MannschaftsDaten
from .render.assemble import Heftseite, zusammenfuegen
from .render.pages import SeitenRenderer
from .storage.filestation import (FileStation, ansprechpartner_lesen,
                                  ordnername_pruefen, text_dekodieren,
                                  zielordner_fuer)

PDF = {".pdf"}
BILD = {".jpg", ".jpeg", ".png"}
WORD = {".docx", ".doc", ".odt", ".rtf"}
TEXT = {".txt", ".md"}
#: Synology-Office-Dateien lassen sich ausserhalb von DSM nicht umwandeln.
NICHT_LESBAR = {".odoc", ".osheet", ".oslides"}

#: Ordner, die nie ins Heft gehoeren (Synology-Verwaltung, unsere Daten).
VERSTECKT = re.compile(r"^(@|#|\.|_daten$)")
#: Unsere eigene Ausgabe -- sonst baute sich das Heft beim zweiten Mal selbst ein.
EIGENE_AUSGABE = re.compile(r"_WaB(_Druck)?\.pdf$", re.I)
#: Die von Knopf 1 erzeugte Mannschaftsdatei (ohne Balken).
FUPA_DATEI = re.compile(r"^\d{4}-\d{2}-\d{2}_.+_gegen_.+\.pdf$")
DECKBLATT_DATEI = re.compile(r"^\d{4}-\d{2}-\d{2}_Deckblatt\.pdf$")

HEFTPLAN = "Heftplan.txt"
ARTEN = ("deckblatt", "vorwort", "fupa", "datei", "ansprechpartner",
         "werbung", "leerseite")


@dataclass
class Baustein:
    """Ein Eintrag im Heftplan."""

    art: str
    wert: str = ""            # Schluessel (fupa) bzw. relativer Pfad
    titel: str = ""
    pdf: Path | None = None   # nach dem Setzen
    seiten: int = 0

    def zeile(self) -> str:
        name = self.art.capitalize() if self.art != "fupa" else "FuPa"
        return f"[{name}] {self.wert}".rstrip()


@dataclass
class HeftErgebnis:
    ordner: str = ""
    pdf: Path | None = None
    nas_datei: str = ""
    seitenzahl: int = 0
    plan: str = ""
    warnungen: list[str] = field(default_factory=list)
    plan_von_hand: bool = False

    def als_dict(self) -> dict:
        return {"ordner": self.ordner, "pdf": str(self.pdf or ""),
                "nas_datei": self.nas_datei, "seitenzahl": self.seitenzahl,
                "plan": self.plan, "warnungen": list(self.warnungen),
                "plan_von_hand": self.plan_von_hand}


# ---------------------------------------------------------------------------
# Heftplan: verteilen, schreiben, lesen
# ---------------------------------------------------------------------------

def plan_erstellen(abschnitte: list[list[Baustein]], vorne: list[Baustein],
                   hinten: list[Baustein], werbung: list[Baustein]) -> list[Baustein]:
    """Verteilt die Werbung und fuellt auf ein Vielfaches von 4 auf.

    ``vorne`` (Deckblatt, Vorwort) und ``hinten`` (Ansprechpartner) rahmen
    die Abschnitte (je Mannschaft) ein. Die Luecken fuer Werbung liegen
    zwischen allen Bloecken ab dem Ende von ``vorne``. Die letzte Anzeige
    wird die Rueckseite.
    """
    werbung = list(werbung)
    rueckseite = werbung.pop() if werbung else None
    bloecke = [list(a) for a in abschnitte if a] + ([list(hinten)] if hinten else [])
    plan: list[Baustein] = list(vorne)
    if bloecke:
        # Luecke i liegt vor Block i: nach dem Vorwort, zwischen den
        # Mannschaften, vor den Ansprechpartnern. Gleichmaessig verteilt --
        # bei wenigen Anzeigen ueber das ganze Heft, nicht alle vorne.
        luecken: list[list[Baustein]] = [[] for _ in bloecke]
        for i, anzeige in enumerate(werbung):
            luecken[min(len(bloecke) - 1,
                        int((i + 0.5) * len(bloecke) / len(werbung)))].append(anzeige)
        for luecke, block in zip(luecken, bloecke):
            plan.extend(luecke)
            plan.extend(block)
    else:
        plan.extend(werbung)
    seiten = sum(b.seiten for b in plan) + (rueckseite.seiten if rueckseite else 0)
    plan.extend(Baustein("leerseite", seiten=1) for _ in range((-seiten) % 4))
    if rueckseite:
        plan.append(rueckseite)
    return plan


def plan_als_text(plan: list[Baustein], name: str) -> str:
    zeilen = [
        f"# Heftplan fuer '{name}' -- erzeugt {datetime.now():%d.%m.%Y %H:%M}",
        "#",
        "# So ist das Heft aufgebaut. Zum Aendern Zeilen verschieben, loeschen",
        "# oder ergaenzen und 'Gesamtes Heft bauen' erneut druecken -- dann gilt",
        "# genau diese Reihenfolge. Zum Neuplanen die Datei loeschen (oder beim",
        "# Bauen 'Heftplan neu erstellen' anhaken).",
        "#",
        "# [Deckblatt]  [Vorwort] <Datei>  [FuPa] <mannschaft>  [Datei] <Pfad>",
        "# [Ansprechpartner]  [Werbung] <Datei im Werbe-Ordner>  [Leerseite]",
        "",
    ]
    seite = 1
    for b in plan:
        bis = seite + max(b.seiten, 1) - 1
        nummer = f"S. {seite}" if bis == seite else f"S. {seite}-{bis}"
        zeilen.append(f"{b.zeile():<60} # {nummer}")
        seite = bis + 1
    zeilen.append(f"# Gesamt: {seite - 1} Seiten")
    return "\n".join(zeilen) + "\n"


def plan_lesen(text: str) -> tuple[list[Baustein], list[str]]:
    plan: list[Baustein] = []
    warnungen: list[str] = []
    for nummer, zeile in enumerate(text.splitlines(), 1):
        inhalt = zeile.split("#", 1)[0].strip() if not zeile.lstrip().startswith("#") \
            else ""
        if not inhalt:
            continue
        treffer = re.fullmatch(r"\[(\w+)\]\s*(.*)", inhalt)
        art = treffer.group(1).lower() if treffer else ""
        if art not in ARTEN:
            warnungen.append(f"Heftplan Zeile {nummer} nicht verstanden: '{inhalt}'")
            continue
        plan.append(Baustein(art, treffer.group(2).strip()))
    return plan, warnungen


# ---------------------------------------------------------------------------
# Der Bauvorgang
# ---------------------------------------------------------------------------

class _Laden:
    """Holt Dateien von der NAS -- mit Zwischenspeicher.

    Werbung und Vorlagen aendern sich selten; ueber das QuickConnect-Relay
    soll nicht jedes Mal alles neu kommen. Gleich ist eine Datei, wenn Pfad,
    Groesse und Aenderungszeit uebereinstimmen.
    """

    def __init__(self, fs: FileStation, ordner: Path) -> None:
        self.fs = fs
        self.ordner = ordner

    def holen(self, eintrag: dict) -> Path:
        pfad = eintrag["path"]
        zusatz = eintrag.get("additional") or {}
        kennung = json.dumps([pfad, zusatz.get("size"),
                              (zusatz.get("time") or {}).get("mtime")])
        ablage = self.ordner / hashlib.sha1(kennung.encode()).hexdigest()[:16]
        ziel = ablage / eintrag["name"]
        if ziel.exists() and (zusatz.get("size") in (None, ziel.stat().st_size)):
            return ziel
        self.fs.herunterladen(pfad, ziel)
        return ziel


def gesamtheft_bauen(k: Konfiguration, ausgabe_name: str, *,
                     neu_planen: bool = False,
                     melden: Callable[[str], None] | None = None,
                     fs: FileStation | None = None) -> HeftErgebnis:
    def jetzt(text: str) -> None:
        logger().info("%s", text)
        if melden:
            melden(text)

    name = ordnername_pruefen(ausgabe_name)
    saison = k.nas_saison_ordner
    ordner = f"{saison}/{name}"
    ergebnis = HeftErgebnis(ordner=ordner)
    start = datetime.now()
    arbeit = k.arbeits_ordner / f"heft_{start:%Y%m%d_%H%M%S}"
    renderer = SeitenRenderer(k, arbeit)
    # Im Gesamtheft gehoeren die Balken dazu -- auch wenn die Mannschafts-
    # dateien fuer das Layout ohne sie erzeugt werden.
    renderer.layout = replace(renderer.layout, balken=True)

    client = fs or FileStation.aus_konfiguration(k)
    if fs is None:
        client.anmelden()
    try:
        laden = _Laden(client, k.arbeits_ordner / "nas_cache")

        # -- 1. Was liegt im Ausgabe-Ordner? ---------------------------------
        jetzt(f"Lese den Ordner '{name}' …")
        if name not in {f["name"] for f in client.auflisten(saison) if f.get("isdir")}:
            raise NasFehler(f"{ordner} fehlt",
                            benutzer_text=f"Den Ordner '{name}' gibt es nicht.")
        oben = client.auflisten(ordner)
        unterordner = {f["name"]: client.auflisten(f["path"]) for f in oben
                       if f.get("isdir") and not VERSTECKT.match(f["name"])}
        daten_ordner = next((f for f in oben if f.get("isdir")
                             and f["name"] == "_daten"), None)

        # -- 2. Spieldaten (von Knopf 1 mit abgelegt) ------------------------
        ausgabe: Ausgabe | None = None
        if daten_ordner:
            snapshots = sorted((f for f in client.auflisten(daten_ordner["path"])
                                if f["name"].endswith("_snapshot.json")),
                               key=lambda f: f["name"])
            if snapshots:
                datei = laden.holen(snapshots[-1])
                ausgabe = Ausgabe.from_dict(json.loads(datei.read_text("utf-8")))
        if ausgabe is None:
            ergebnis.warnungen.append(
                "Im Ordner liegen keine Spieldaten (_daten). Deckblatt und "
                "FuPa-Seiten werden so übernommen, wie sie im Ordner liegen "
                "(ohne Balken). Ordner von neueren Läufen haben sie.")
        mannschaften: dict[str, MannschaftsDaten] = {
            m.schluessel: m for m in (ausgabe.mannschaften if ausgabe else [])}

        # -- 3. Bausteine sammeln ---------------------------------------------
        bausteine: dict[tuple[str, str], Baustein] = {}

        def merken(b: Baustein) -> Baustein:
            bausteine[(b.art, b.wert)] = b
            return b

        dateien_oben = {f["name"]: f for f in oben if not f.get("isdir")}
        vorne = [merken(Baustein("deckblatt"))]
        vorwort = next((f for n, f in sorted(dateien_oben.items())
                        if n.lower().startswith("vorwort")), None)
        if vorwort:
            vorne.append(merken(Baustein("vorwort", vorwort["name"], "Vorwort")))
        else:
            ergebnis.warnungen.append("Kein Vorwort im Ordner (Datei 'Vorwort…').")

        ordner_je_schluessel = {zielordner_fuer(k, m.schluessel): m.schluessel
                                for m in k.aktive_mannschaften()}
        reihenfolge = [o for o in ordner_je_schluessel if o in unterordner] + \
            sorted(o for o in unterordner if o not in ordner_je_schluessel)
        abschnitte: list[list[Baustein]] = []
        for unter in reihenfolge:
            schluessel = ordner_je_schluessel.get(unter, "")
            abschnitt: list[Baustein] = []
            if schluessel and schluessel in mannschaften:
                abschnitt.append(merken(Baustein(
                    "fupa", schluessel, mannschaften[schluessel].anzeigename)))
            titel = mannschaften[schluessel].anzeigename if schluessel in mannschaften \
                else unter
            for f in sorted(unterordner[unter], key=lambda f: f["name"].lower()):
                if (f.get("isdir") or EIGENE_AUSGABE.search(f["name"])
                        or VERSTECKT.match(f["name"])):
                    continue
                if schluessel in mannschaften and FUPA_DATEI.match(f["name"]):
                    continue        # ersetzt durch die FuPa-Seiten mit Balken
                abschnitt.append(merken(Baustein("datei", f"{unter}/{f['name']}", titel)))
            abschnitte.append(abschnitt)

        hinten = [merken(Baustein("ansprechpartner", titel="Ansprechpartner"))]

        werbe_ordner = str(k.get("heft.werbung_ordner", "") or "").strip("/")
        werbe_eintraege: dict[str, dict] = {}
        if werbe_ordner:
            try:
                werbe_eintraege = {f["name"]: f for f in
                                   client.auflisten(f"{saison}/{werbe_ordner}")
                                   if not f.get("isdir")
                                   and not VERSTECKT.match(f["name"])}
            except StadionheftFehler:
                ergebnis.warnungen.append(f"Werbe-Ordner '{werbe_ordner}' fehlt.")
        werbung = [merken(Baustein("werbung", n))
                   for n in sorted(werbe_eintraege, key=str.lower)]

        # -- 4. Plan: der eigene aus dem Ordner oder ein neuer ----------------
        plan_datei = dateien_oben.get(HEFTPLAN)
        plan: list[Baustein] | None = None
        if plan_datei and not neu_planen:
            text = text_dekodieren(laden.holen(plan_datei).read_bytes())
            plan, warnungen = plan_lesen(text)
            ergebnis.warnungen.extend(warnungen)
            ergebnis.plan_von_hand = True
            jetzt("Heftplan aus dem Ordner wird befolgt.")

        # -- 5. Setzen ---------------------------------------------------------
        def setzen(b: Baustein, nummer: int) -> None:
            stamm = f"{nummer:03d}_{b.art}"
            if b.art == "deckblatt":
                if ausgabe is not None:
                    bild = _titelbild(dateien_oben, laden, k, client, saison)
                    b.pdf = renderer.deckblatt(ausgabe, bild)
                else:
                    alt = next((f for n, f in dateien_oben.items()
                                if DECKBLATT_DATEI.match(n)), None)
                    b.pdf = laden.holen(alt) if alt else None
            elif b.art == "vorwort":
                eintrag = dateien_oben.get(b.wert)
                b.pdf = _datei_setzen(k, renderer, laden, eintrag, "Vorwort",
                                      stamm, ergebnis) if eintrag else None
            elif b.art == "fupa":
                daten = mannschaften.get(b.wert)
                if daten is not None:
                    seiten = [Heftseite(renderer.mannschaftsseite(art, daten, i),
                                        f"{daten.anzeigename} – {art}")
                              for i, art in enumerate(seitenfolge(daten), 1)]
                    b.pdf = zusammenfuegen(seiten, arbeit / f"{stamm}_{b.wert}.pdf").ziel
            elif b.art == "datei":
                unter, _, dateiname = b.wert.partition("/")
                eintrag = next((f for f in unterordner.get(unter, [])
                                if f["name"] == dateiname), None) \
                    if dateiname else dateien_oben.get(unter)
                titel = b.titel or (mannschaften[ordner_je_schluessel[unter]].anzeigename
                                    if ordner_je_schluessel.get(unter) in mannschaften
                                    else unter)
                b.pdf = _datei_setzen(k, renderer, laden, eintrag, titel, stamm,
                                      ergebnis) if eintrag else None
            elif b.art == "ansprechpartner":
                eintraege = _ansprechpartner(k, client, saison, laden, ergebnis)
                b.pdf = renderer.ansprechpartner(eintraege) if eintraege else None
            elif b.art == "werbung":
                eintrag = werbe_eintraege.get(b.wert)
                b.pdf = _datei_setzen(k, renderer, laden, eintrag, "", stamm,
                                      ergebnis, vollbild=True) if eintrag else None
            elif b.art == "leerseite":
                b.pdf = renderer.vollbildseite(None, stamm)
            if b.pdf is None and b.art != "leerseite":
                ergebnis.warnungen.append(f"{b.zeile()} -- nicht gefunden, übersprungen.")
            b.seiten = _seitenzahl(b.pdf)

        if plan is None:
            alle = vorne + [b for a in abschnitte for b in a] + hinten + werbung
        else:
            alle = plan
        gesetzt: dict[tuple[str, str], tuple[Path | None, int]] = {}
        for nummer, b in enumerate(alle, 1):
            schluessel_b = (b.art, b.wert)
            if b.art != "leerseite" and schluessel_b in gesetzt:
                # Steht im eigenen Plan zweimal: nur einmal setzen.
                b.pdf, b.seiten = gesetzt[schluessel_b]
                continue
            jetzt(f"Setze {b.zeile()} …")
            setzen(b, nummer)
            gesetzt[schluessel_b] = (b.pdf, b.seiten)

        if plan is None:
            plan = plan_erstellen(
                [[b for b in a if b.pdf] for a in abschnitte],
                [b for b in vorne if b.pdf], [b for b in hinten if b.pdf],
                [b for b in werbung if b.pdf])
            for nummer, b in enumerate(plan, 1):
                if b.art == "leerseite" and b.pdf is None:
                    setzen(b, 900 + nummer)
        else:
            plan = [b for b in plan if b.pdf is not None]
            fehlend = (-sum(b.seiten for b in plan)) % 4
            if fehlend:
                ergebnis.warnungen.append(
                    f"Der Heftplan ergibt {sum(b.seiten for b in plan)} Seiten -- "
                    f"nicht durch 4 teilbar. {fehlend} Leerseite(n) vor der "
                    f"Rückseite ergänzt.")
                leer = [Baustein("leerseite") for _ in range(fehlend)]
                for nummer, b in enumerate(leer, 1):
                    setzen(b, 950 + nummer)
                plan = plan[:-1] + leer + plan[-1:] if plan else leer

        # -- 6. Zusammenfuegen --------------------------------------------------
        jetzt("Füge das Heft zusammen …")
        datum = _erstes_spiel(ausgabe) or start
        dateiname = _dateiname(k, datum)
        lokal = k.ausgabe_ordner / "Gesamtheft" / name / dateiname
        lokal.parent.mkdir(parents=True, exist_ok=True)
        montage = zusammenfuegen([Heftseite(b.pdf, b.zeile()) for b in plan], lokal)
        ergebnis.warnungen.extend(montage.warnungen)
        ergebnis.pdf = lokal
        ergebnis.seitenzahl = montage.seitenzahl
        ergebnis.plan = plan_als_text(plan, name)

        # -- 7. Zurueck auf die NAS ---------------------------------------------
        plan_lokal = arbeit / HEFTPLAN
        plan_lokal.write_text(ergebnis.plan, encoding="utf-8")
        if not ergebnis.plan_von_hand:
            jetzt("Lege den Heftplan in den Ordner …")
            client.hochladen(plan_lokal, ordner)
        jetzt(f"Lade {dateiname} auf die NAS ({lokal.stat().st_size // 1_000_000} MB) …")
        try:
            client.hochladen(lokal, ordner)
            ergebnis.nas_datei = f"{ordner}/{dateiname}"
        except NasFehler as fehler:
            ergebnis.warnungen.append(
                f"Das Heft ist fertig, konnte aber nicht auf die NAS geladen werden "
                f"({fehler.benutzer_text}). Bitte hier herunterladen.")
        jetzt(f"Fertig: {ergebnis.seitenzahl} Seiten.")
        return ergebnis
    finally:
        if fs is None:
            client.abmelden()


# ---------------------------------------------------------------------------
# Helfer
# ---------------------------------------------------------------------------

def _seitenzahl(pdf: Path | None) -> int:
    if pdf is None or not Path(pdf).exists():
        return 0
    from pypdf import PdfReader
    return len(PdfReader(str(pdf)).pages)


def _erstes_spiel(ausgabe: Ausgabe | None) -> datetime | None:
    termine = [m.naechstes_spiel.anstoss_dt for m in (ausgabe.mannschaften if ausgabe else [])
               if m.naechstes_spiel and m.naechstes_spiel.anstoss_dt]
    return min(termine) if termine else None


def _dateiname(k: Konfiguration, datum: datetime) -> str:
    muster = str(k.get("heft.dateiname", "{datum:%Y%m%d}_WaB_Druck.pdf"))
    try:
        name = muster.format(datum=datum)
    except (KeyError, ValueError, IndexError):
        name = f"{datum:%Y%m%d}_WaB_Druck.pdf"
    name = re.sub(r'[/\\:*?"<>|]', "-", name)
    return name if name.lower().endswith(".pdf") else name + ".pdf"


def _titelbild(dateien_oben: dict, laden: _Laden, k: Konfiguration,
               client: FileStation, saison: str) -> Path | None:
    """Titelbild aus dem Ausgabe-Ordner, sonst aus der Vorlage."""
    def suchen(eintraege) -> dict | None:
        return next((f for f in eintraege if not f.get("isdir") and
                     re.match(r"titelbild\.(jpe?g|png)$", f["name"], re.I)), None)

    eintrag = suchen(dateien_oben.values())
    if eintrag is None:
        vorlage = str(k.get("nas.filestation.vorlage_ordner", "") or "").strip("/")
        if vorlage:
            try:
                eintrag = suchen(client.auflisten(f"{saison}/{vorlage}"))
            except StadionheftFehler:
                eintrag = None
    return laden.holen(eintrag) if eintrag else None


def _ansprechpartner(k: Konfiguration, client: FileStation, saison: str,
                     laden: _Laden, ergebnis: HeftErgebnis) -> list[dict]:
    datei = str(k.get("heft.ansprechpartner_datei", "") or "").strip("/")
    if datei:
        eltern, _, name = f"{saison}/{datei}".rpartition("/")
        try:
            eintrag = next((f for f in client.auflisten(eltern)
                            if f["name"] == name), None)
        except StadionheftFehler:
            eintrag = None
        if eintrag:
            return ansprechpartner_lesen(text_dekodieren(laden.holen(eintrag).read_bytes()))
        ergebnis.warnungen.append(f"Ansprechpartner-Datei '{datei}' fehlt -- "
                                  f"es gilt die Liste aus der Konfiguration.")
    return [e for e in (k.get("deckblatt.ansprechpartner") or [])
            if isinstance(e, dict) and e.get("funktion")]


def _datei_setzen(k: Konfiguration, renderer: SeitenRenderer, laden: _Laden,
                  eintrag: dict, titel: str, stamm: str, ergebnis: HeftErgebnis,
                  vollbild: bool = False) -> Path | None:
    """Eine Datei von der NAS als PDF-Seite(n) -- je nach Art."""
    endung = Path(eintrag["name"]).suffix.lower()
    if endung in NICHT_LESBAR:
        ergebnis.warnungen.append(
            f"'{eintrag['name']}' ist eine Synology-Office-Datei und lässt sich nur "
            f"in DSM umwandeln -- bitte dort als PDF oder .docx exportieren.")
        return None
    if endung not in PDF | BILD | WORD | TEXT:
        ergebnis.warnungen.append(f"'{eintrag['name']}': Dateiart wird nicht "
                                  f"unterstützt, übersprungen.")
        return None
    lokal = laden.holen(eintrag)
    if endung in PDF:
        return auf_heftformat(lokal, renderer.layout,
                              renderer.arbeitsordner / f"{stamm}.pdf", ergebnis)
    if endung in BILD:
        return (renderer.vollbildseite(lokal, stamm) if vollbild
                else renderer.bildseite(lokal, titel, stamm))
    if endung in TEXT:
        return renderer.freitextseite(titel, text_dekodieren(lokal.read_bytes()),
                                      stamm, quelle=eintrag["name"])
    umgewandelt = _umwandeln(k, lokal, renderer.arbeitsordner / f"{stamm}_word.pdf",
                             ergebnis)
    return auf_heftformat(umgewandelt, renderer.layout,
                          renderer.arbeitsordner / f"{stamm}.pdf", ergebnis) \
        if umgewandelt else None


MM = 72 / 25.4
#: So viel Abweichung vom Endformat gilt noch als "passt" (Rundung, 150 statt
#: 148 mm bei mancher Anzeige) -- solche Seiten bleiben unangetastet.
FORMAT_TOLERANZ_MM = 3


def auf_heftformat(quelle: Path, layout, ziel: Path,
                   ergebnis: HeftErgebnis | None = None) -> Path:
    """Bringt jede Seite einer fremden PDF auf das Heftformat.

    Anzeigen und Zeitungsartikel kommen als A4, A5-quer oder A5 mit/ohne
    Anschnitt. Die Montage legt Seiten nur mittig auf ein gemeinsames Format
    -- eine einzige A4-Anzeige machte so das ganze Heft zu A4. Hier wird jede
    Seite, deren Endformat nicht passt, proportional in das Endformat
    (A5) eingepasst und mittig auf A5 + Anschnitt gesetzt. Passende Seiten
    bleiben, wie sie sind (ihr Anschnitt ist dann echt).
    """
    from pypdf import PageObject, PdfReader, PdfWriter, Transformation
    from pypdf.generic import RectangleObject

    breite, hoehe = layout.breite_mm * MM, layout.hoehe_mm * MM
    rand = layout.anschnitt_mm * MM
    leser = PdfReader(str(quelle))
    schreiber = PdfWriter()
    angepasst = 0
    for seite in leser.pages:
        trim = seite.trimbox
        tb, th = float(trim.width), float(trim.height)
        if (abs(tb - breite) <= FORMAT_TOLERANZ_MM * MM
                and abs(th - hoehe) <= FORMAT_TOLERANZ_MM * MM):
            schreiber.add_page(seite)
            continue
        angepasst += 1
        faktor = min(breite / tb, hoehe / th)
        dx = rand + (breite - tb * faktor) / 2
        dy = rand + (hoehe - th * faktor) / 2
        neu = PageObject.create_blank_page(width=breite + 2 * rand,
                                           height=hoehe + 2 * rand)
        neu.merge_transformed_page(
            seite, Transformation().translate(-float(trim.left), -float(trim.bottom))
            .scale(faktor, faktor).translate(dx, dy))
        neu.trimbox = RectangleObject((rand, rand, rand + breite, rand + hoehe))
        neu.bleedbox = RectangleObject((0, 0, breite + 2 * rand, hoehe + 2 * rand))
        schreiber.add_page(neu)
    if not angepasst:
        return quelle
    with ziel.open("wb") as strom:
        schreiber.write(strom)
    if ergebnis is not None:
        ergebnis.warnungen.append(
            f"'{quelle.name}': {angepasst} Seite(n) nicht im Heftformat -- auf A5 "
            f"verkleinert/eingepasst. Bitte im Druck-PDF ansehen.")
    return ziel


def _umwandeln(k: Konfiguration, datei: Path, ziel: Path,
               ergebnis: HeftErgebnis) -> Path | None:
    """Word & Co. ueber Gotenberg (LibreOffice) in PDF."""
    import requests

    adresse = str(k.get("heft.umwandler_url", "") or "").rstrip("/")
    if not adresse:
        ergebnis.warnungen.append(
            f"'{datei.name}' ist eine Word-Datei; dafür ist kein Umwandler "
            f"eingerichtet (heft.umwandler_url). Bitte als PDF ablegen.")
        return None
    try:
        with datei.open("rb") as strom:
            antwort = requests.post(f"{adresse}/forms/libreoffice/convert",
                                    files={"files": (datei.name, strom)}, timeout=180)
        antwort.raise_for_status()
    except requests.RequestException as fehler:
        ergebnis.warnungen.append(f"'{datei.name}' konnte nicht umgewandelt werden "
                                  f"({fehler}).")
        return None
    ziel.write_bytes(antwort.content)
    return ziel


def ausgaben_auflisten(k: Konfiguration) -> list[str]:
    """Die Ausgabe-Ordner der Saison, neueste zuerst (fuer die Auswahl)."""
    with FileStation.aus_konfiguration(k) as fs:
        namen = [f["name"] for f in fs.auflisten(k.nas_saison_ordner) if f.get("isdir")]
    ausgaben = [(int(t.group(1)), n) for n in namen
                if (t := re.match(r"\s*(\d+)\s+Ausgabe\b", n))]
    return [n for _, n in sorted(ausgaben, reverse=True)]


__all__ = ["gesamtheft_bauen", "ausgaben_auflisten", "plan_erstellen",
           "plan_lesen", "plan_als_text", "Baustein", "HeftErgebnis",
           "RenderFehler"]
