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

import fnmatch
import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from pypdf.errors import PdfReadError

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
#: "Vorwort.docx", "Grußwort Stadionheft.docx", "Grusswort.txt" ...
VORWORT = re.compile(r"^(vorwort|gru(ß|ss)wort)", re.I)
ARTEN = ("deckblatt", "vorwort", "trenner", "datei", "fupa", "kontaktliste",
         "impressum", "werbung", "leerseite", "ansprechpartner")


@dataclass
class Baustein:
    """Ein Eintrag im Heftplan."""

    art: str
    wert: str = ""            # Schluessel (fupa) bzw. relativer Pfad
    titel: str = ""
    pdf: Path | None = None   # nach dem Setzen
    seiten: int = 0
    halb: bool = False        # Anzeige, die nur eine halbe Seite braucht

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

        def liste(pfad: str) -> list[dict]:
            try:
                return [f for f in client.auflisten(pfad)
                        if not VERSTECKT.match(f["name"])]
            except StadionheftFehler:
                return []

        # -- 1. Was liegt im Ausgabe-Ordner? ---------------------------------
        jetzt(f"Lese den Ordner '{name}' …")
        if name not in {f["name"] for f in liste(saison) if f.get("isdir")}:
            raise NasFehler(f"{ordner} fehlt",
                            benutzer_text=f"Den Ordner '{name}' gibt es nicht.")
        oben = client.auflisten(ordner)
        unterordner = {f["name"]: liste(f["path"]) for f in oben
                       if f.get("isdir") and not VERSTECKT.match(f["name"])}
        dateien_oben = {f["name"]: f for f in oben if not f.get("isdir")}
        vorlage_name = str(k.get("nas.filestation.vorlage_ordner", "") or "").strip("/")
        vorlage = {u: liste(f"{saison}/{vorlage_name}/{u}")
                   for u in unterordner} if vorlage_name else {}

        # -- 2. Spieldaten (von Knopf 1 mit abgelegt) ------------------------
        ausgabe: Ausgabe | None = None
        daten_ordner = next((f for f in oben if f.get("isdir")
                             and f["name"] == "_daten"), None)
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
        ordner_je_schluessel = {zielordner_fuer(k, m.schluessel): m.schluessel
                                for m in k.aktive_mannschaften()}

        def team(schluessel: str) -> MannschaftsDaten | None:
            if schluessel in mannschaften:
                return mannschaften[schluessel]
            if schluessel in k.mannschaften:
                m = k.mannschaften[schluessel]
                return MannschaftsDaten(schluessel=m.schluessel,
                                        anzeigename=m.anzeigename,
                                        gruppe=m.gruppe, untertitel=m.untertitel,
                                        liga=m.liga)
            return None

        # -- 3. Bausteine sammeln ---------------------------------------------
        vorne = [Baustein("deckblatt")]
        vorwort = next((f for n, f in sorted(dateien_oben.items())
                        if VORWORT.match(n) and Path(n).suffix.lower()
                        in PDF | WORD | TEXT | NICHT_LESBAR), None)
        if vorwort:
            vorne.append(Baustein("vorwort", vorwort["name"]))
        else:
            ergebnis.warnungen.append("Kein Vorwort im Ordner (Datei 'Vorwort…' "
                                      "oder 'Grußwort…').")

        reihenfolge = [o for o in ordner_je_schluessel if o in unterordner] + \
            sorted(o for o in unterordner if o not in ordner_je_schluessel)
        abschnitte: list[list[Baustein]] = []
        for unter in reihenfolge:
            schluessel = ordner_je_schluessel.get(unter, "")
            aus_vorlage = {f["name"] for f in vorlage.get(unter, [])}
            abschnitt: list[Baustein] = []
            if schluessel:
                abschnitt.append(Baustein("trenner", schluessel))
            for f in sorted(unterordner[unter], key=lambda f: f["name"].lower()):
                if f.get("isdir") or EIGENE_AUSGABE.search(f["name"]):
                    continue
                if f["name"] in aus_vorlage:
                    continue        # das Zwischenbild -- kommt aus der Vorlage
                if schluessel in mannschaften and FUPA_DATEI.match(f["name"]):
                    continue        # ersetzt durch die FuPa-Seiten mit Balken
                abschnitt.append(Baustein("datei", f"{unter}/{f['name']}"))
            if schluessel in mannschaften:
                abschnitt.append(Baustein("fupa", schluessel))
            abschnitte.append(abschnitt)

        schluss: list[Baustein] = []
        for muster in k.get("heft.kontaktlisten") or [
                k.get("heft.ansprechpartner_datei", "")]:
            for pfad in _finden(liste, saison, str(muster or ""), ergebnis):
                schluss.append(Baustein("kontaktliste", pfad))
        if not any(b.art == "kontaktliste" for b in schluss):
            schluss.append(Baustein("kontaktliste", ""))     # aus der Konfiguration
        for pfad in _finden(liste, saison, str(k.get("heft.impressum", "") or ""),
                            ergebnis):
            schluss.append(Baustein("impressum", pfad))

        werbe_ordner = str(k.get("heft.werbung_ordner", "") or "").strip("/")
        werbung_alle = {f["name"]: f for f in liste(f"{saison}/{werbe_ordner}")} \
            if werbe_ordner else {}
        if werbe_ordner and not werbung_alle:
            ergebnis.warnungen.append(f"Werbe-Ordner '{werbe_ordner}' fehlt oder ist leer.")
        werbe_teile = {teil: str(k.get(f"heft.werbung_{teil}", "") or "")
                       for teil in ("vorne", "hinten", "rueckseite")}
        fest = any(n in werbung_alle and werbung_alle[n].get("isdir")
                   for n in werbe_teile.values() if n)
        werbe_dateien: dict[str, dict] = {}

        def werbung_aus(unter: str) -> list[Baustein]:
            pfad = f"{saison}/{werbe_ordner}/{unter}" if unter else \
                f"{saison}/{werbe_ordner}"
            bausteine = []
            dateien = [f for f in liste(pfad) if not f.get("isdir")]
            behalten = set(nur_neueste([f["name"] for f in dateien], ergebnis))
            for f in sorted(dateien, key=lambda f: f["name"].lower()):
                if f["name"] not in behalten:
                    continue
                schluessel = f"{unter}/{f['name']}" if unter else f["name"]
                werbe_dateien[schluessel] = f
                bausteine.append(Baustein("werbung", schluessel))
            return bausteine

        werbung = {teil: (werbung_aus(werbe_teile[teil]) if fest and werbe_teile[teil]
                          else []) for teil in werbe_teile}
        if not fest:
            werbung["verteilt"] = werbung_aus("")

        # -- 4. Plan: der eigene aus dem Ordner oder ein neuer ----------------
        plan_datei = dateien_oben.get(HEFTPLAN)
        eigener_plan: list[Baustein] | None = None
        if plan_datei and not neu_planen:
            text = text_dekodieren(laden.holen(plan_datei).read_bytes())
            eigener_plan, warnungen = plan_lesen(text)
            ergebnis.warnungen.extend(warnungen)
            ergebnis.plan_von_hand = True
            jetzt("Heftplan aus dem Ordner wird befolgt.")
            for b in eigener_plan:
                if b.art == "werbung":
                    for teil in b.wert.split(" + "):
                        if teil not in werbe_dateien:
                            unter, _, dateiname = teil.rpartition("/")
                            eintrag = next((f for f in liste(
                                f"{saison}/{werbe_ordner}/{unter}" if unter
                                else f"{saison}/{werbe_ordner}")
                                if f["name"] == dateiname), None)
                            if eintrag:
                                werbe_dateien[teil] = eintrag

        # -- 5. Setzen ---------------------------------------------------------
        zaehler = [0]

        def stamm(b: Baustein) -> str:
            zaehler[0] += 1
            return f"{zaehler[0]:03d}_{b.art}"

        def anzeige(schluessel: str) -> tuple[Path | None, bool]:
            """Eine Anzeige als PDF -- und ob sie nur eine halbe Seite ist."""
            eintrag = werbe_dateien.get(schluessel)
            if eintrag is None:
                return None, False
            endung = Path(eintrag["name"]).suffix.lower()
            if endung not in PDF | BILD:
                ergebnis.warnungen.append(
                    f"Werbung '{eintrag['name']}': nur PDF oder Bild möglich.")
                return None, False
            lokal = laden.holen(eintrag)
            if endung in BILD:
                # Nach der Anzeige benannt -- der Name erscheint in Hinweisen.
                lokal = bild_als_pdf(lokal, arbeit / f"{len(werbe_pdf):02d}"
                                     / f"{Path(eintrag['name']).stem}.pdf")
            return lokal, _ist_halbe_seite(lokal)

        werbe_pdf: dict[str, tuple[Path | None, bool]] = {}

        def setzen(b: Baustein) -> None:
            name_s = stamm(b)
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
                b.pdf = _text_oder_pdf(renderer, laden, eintrag, "Vorwort", name_s,
                                       ergebnis) if eintrag else None
            elif b.art == "trenner":
                daten = team(b.wert)
                if daten is not None:
                    unter = zielordner_fuer(k, b.wert)
                    bild = next((f for f in vorlage.get(unter, [])
                                 if Path(f["name"]).suffix.lower() in BILD), None)
                    b.pdf = (renderer.zwischenbildseite(daten, laden.holen(bild), name_s)
                             if bild else renderer.mannschaftsseite("trenner", daten, 0))
            elif b.art == "fupa":
                daten = mannschaften.get(b.wert)
                if daten is not None:
                    seiten = [Heftseite(renderer.mannschaftsseite(art, daten, i),
                                        f"{daten.anzeigename} – {art}")
                              for i, art in enumerate(seitenfolge(daten), 1)
                              if art != "trenner"]
                    b.pdf = zusammenfuegen(seiten, arbeit / f"{name_s}_{b.wert}.pdf").ziel
            elif b.art == "datei":
                unter, _, dateiname = b.wert.partition("/")
                eintrag = next((f for f in unterordner.get(unter, [])
                                if f["name"] == dateiname), None) \
                    if dateiname else dateien_oben.get(unter)
                if eintrag is not None:
                    ist_team = unter in ordner_je_schluessel
                    titel = "Spielbericht" if ist_team else unter
                    if ist_team and Path(dateiname).suffix.lower() in PDF \
                            and not FUPA_DATEI.match(dateiname):
                        rahmen = renderer.rahmenseite(titel, name_s + "_rahmen")
                        b.pdf = inhalt_einsetzen(rahmen, laden.holen(eintrag),
                                                 arbeit / f"{name_s}.pdf")
                    else:
                        daten = team(ordner_je_schluessel.get(unter, ""))
                        b.pdf = _text_oder_pdf(
                            renderer, laden, eintrag, titel, name_s, ergebnis,
                            bildtitel=daten.anzeigename if daten else unter)
            elif b.art == "kontaktliste":
                b.pdf = _kontaktliste(k, renderer, laden, liste, saison, b.wert,
                                      str(k.get("heft.kontaktlisten_titel",
                                                "Kontaktlisten")), name_s, ergebnis)
            elif b.art == "impressum":
                b.pdf = _kontaktliste(k, renderer, laden, liste, saison, b.wert,
                                      "Impressum", name_s, ergebnis)
            elif b.art == "werbung":
                teile = [t.strip() for t in b.wert.split(" + ") if t.strip()]
                quellen = []
                for teil in teile:
                    if teil not in werbe_pdf:
                        werbe_pdf[teil] = anzeige(teil)
                    if werbe_pdf[teil][0] is not None:
                        quellen.append(werbe_pdf[teil])
                if len(teile) > 1 or (quellen and quellen[0][1]):
                    b.pdf = halbe_seiten([q for q, _ in quellen], renderer.layout,
                                         arbeit / f"{name_s}.pdf") if quellen else None
                    b.halb = len(teile) == 1
                elif quellen:
                    b.pdf = auf_heftformat(quellen[0][0], renderer.layout,
                                           arbeit / f"{name_s}.pdf", ergebnis)
            elif b.art == "leerseite":
                b.pdf = renderer.vollbildseite(None, name_s)
            if b.pdf is None and b.art != "leerseite":
                ergebnis.warnungen.append(f"{b.zeile()} -- nicht gefunden, übersprungen.")
            b.seiten = _seitenzahl(b.pdf)

        if eigener_plan is None:
            alle = vorne + [b for a in abschnitte for b in a] + schluss + \
                [b for teil in werbung.values() for b in teil]
        else:
            alle = eigener_plan
        gesetzt: dict[tuple[str, str], tuple[Path | None, int, bool]] = {}
        for b in alle:
            schluessel_b = (b.art, b.wert)
            if b.art != "leerseite" and schluessel_b in gesetzt:
                b.pdf, b.seiten, b.halb = gesetzt[schluessel_b]
                continue
            jetzt(f"Setze {b.zeile()} …")
            try:
                setzen(b)
            except (DateiKaputt, PdfReadError, OSError, ValueError) as fehler:
                # Eine kaputte Datei darf nie das ganze Heft kosten.
                logger().warning("%s nicht lesbar: %s", b.zeile(), fehler)
                ergebnis.warnungen.append(
                    f"{b.zeile()} -- Datei nicht lesbar, übersprungen ({fehler}).")
                b.pdf, b.seiten = None, 0
            gesetzt[schluessel_b] = (b.pdf, b.seiten, b.halb)

        def mit_pdf(liste_b: list[Baustein]) -> list[Baustein]:
            return [b for b in liste_b if b.pdf is not None]

        if eigener_plan is None:
            if fest:
                vorne_werbung = paaren(mit_pdf(werbung["vorne"]), setzen)
                hinten_werbung = paaren(mit_pdf(werbung["hinten"]), setzen)
                rueckseite = paaren(mit_pdf(werbung["rueckseite"]), setzen)
                plan = mit_pdf(vorne) + vorne_werbung + \
                    [b for a in abschnitte for b in mit_pdf(a)] + hinten_werbung
                ende = mit_pdf(schluss) + rueckseite
                fehlend = (-(sum(b.seiten for b in plan + ende))) % 4
                leer = [Baustein("leerseite") for _ in range(fehlend)]
                for b in leer:
                    setzen(b)
                # Leerseiten vor die Kontaktlisten -- nicht mitten ins Heft
                plan = plan + leer + ende
            else:
                plan = plan_erstellen(
                    [mit_pdf(a) for a in abschnitte], mit_pdf(vorne),
                    mit_pdf(schluss), paaren(mit_pdf(werbung["verteilt"]), setzen))
                for b in plan:
                    if b.art == "leerseite" and b.pdf is None:
                        setzen(b)
        else:
            plan = mit_pdf(eigener_plan)
            fehlend = (-sum(b.seiten for b in plan)) % 4
            if fehlend:
                ergebnis.warnungen.append(
                    f"Der Heftplan ergibt {sum(b.seiten for b in plan)} Seiten -- "
                    f"nicht durch 4 teilbar. {fehlend} Leerseite(n) vor der "
                    f"Rückseite ergänzt.")
                leer = [Baustein("leerseite") for _ in range(fehlend)]
                for b in leer:
                    setzen(b)
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
        groesse = lokal.stat().st_size
        jetzt(f"Lade {dateiname} auf die NAS ({groesse // 1_000_000} MB, über "
              f"QuickConnect etwa {max(1, groesse // 60_000 // 60)} Minuten) …")
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


def paaren(werbung: list[Baustein], setzen: Callable[[Baustein], None]) -> list[Baustein]:
    """Halbe Anzeigen (quer, Logos) kommen zu zweit auf eine Seite --
    wie in der Layoutdatei. Die Reihenfolge bleibt erhalten."""
    ergebnis: list[Baustein] = []
    offen: Baustein | None = None
    for b in werbung:
        if not b.halb:
            ergebnis.append(b)
            continue
        if offen is None:
            offen = b
            ergebnis.append(b)
            continue
        paar = Baustein("werbung", f"{offen.wert} + {b.wert}")
        setzen(paar)
        ergebnis[ergebnis.index(offen)] = paar
        offen = None
    return ergebnis


# ---------------------------------------------------------------------------
# Helfer
# ---------------------------------------------------------------------------

JAHR = re.compile(r"(?<!\d)(19|20)\d{2}(?!\d)")


def nur_neueste(namen: list[str], ergebnis: HeftErgebnis | None = None) -> list[str]:
    """Von Dateien, die sich nur in der Jahreszahl unterscheiden, die neueste.

    So genuegt es, den neuen Teamshop-Flyer (..._2026.pdf) dazuzulegen --
    der alte (..._2025.pdf) faellt von selbst heraus, nichts steht doppelt
    im Heft.
    """
    gruppen: dict[str, list[tuple[int, str]]] = {}
    for name in namen:
        jahre = [int(t.group(0)) for t in JAHR.finditer(name)]
        kern = JAHR.sub("####", name).lower()
        gruppen.setdefault(kern, []).append((max(jahre) if jahre else 0, name))
    behalten = []
    for gruppe in gruppen.values():
        gruppe.sort()
        behalten.append(gruppe[-1][1])
        if ergebnis is not None and len(gruppe) > 1:
            ergebnis.warnungen.append(
                f"'{gruppe[-1][1]}' ist die neueste Fassung -- übergangen: "
                + ", ".join(n for _, n in gruppe[:-1]))
    return [n for n in namen if n in behalten]


def _finden(liste: Callable[[str], list[dict]], saison: str, muster: str,
            ergebnis: HeftErgebnis | None = None) -> list[str]:
    """'Allgemein/Kontakte_Jugend*.docx' -> passende Pfade (relativ zur Saison)."""
    muster = muster.strip("/")
    if not muster:
        return []
    eltern, _, name = muster.rpartition("/")
    treffer = [f["name"] for f in liste(f"{saison}/{eltern}" if eltern else saison)
               if not f.get("isdir") and fnmatch.fnmatch(f["name"].lower(), name.lower())]
    treffer = nur_neueste(treffer, ergebnis)
    return [f"{eltern}/{n}" if eltern else n for n in sorted(treffer, key=str.lower)]


def _eintrag(liste: Callable[[str], list[dict]], saison: str, pfad: str) -> dict | None:
    eltern, _, name = f"{saison}/{pfad}".rpartition("/")
    return next((f for f in liste(eltern) if f["name"] == name), None)


class DateiKaputt(Exception):
    """Eine Datei laesst sich nicht lesen -- sie wird mit Hinweis uebersprungen."""


def word_absaetze(datei: Path) -> list[tuple[str, bool]]:
    """Absaetze einer .docx als (Text, fett). Bilder und Formatierung bleiben
    draussen -- gesetzt wird im Heftlayout."""
    import html
    import zipfile

    try:
        with zipfile.ZipFile(datei) as archiv:
            xml = archiv.read("word/document.xml").decode("utf-8")
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError, OSError) as fehler:
        raise DateiKaputt(f"{datei.name}: {fehler}") from fehler
    absaetze: list[tuple[str, bool]] = []
    for absatz in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
        absatz = re.sub(r"<w:tab/>", "\t", absatz)
        absatz = re.sub(r"<w:br/>", "\n", absatz)
        laeufe = re.findall(r"<w:r[ >].*?</w:r>", absatz, re.S)
        teile = []
        fett = bool(laeufe)
        for lauf in laeufe:
            text = "".join(re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>", lauf, re.S))
            text += "\t" * lauf.count("\t") if "<w:t" not in lauf else ""
            if text.strip():
                teile.append(text)
                if not re.search(r"<w:b(?: w:val=\"(?:1|true)\")?/>", lauf):
                    fett = False
        text = html.unescape("".join(teile)).strip()
        if text:
            absaetze.append((text, fett))
    return absaetze


def _ist_halbe_seite(pdf: Path) -> bool:
    """Querformat oder Logo-Streifen: passt zweimal auf eine Seite."""
    from pypdf import PdfReader

    seiten = PdfReader(str(pdf)).pages
    if len(seiten) != 1:
        return False
    trim = seiten[0].trimbox
    return float(trim.width) >= float(trim.height)


def bild_als_pdf(bild: Path, ziel: Path) -> Path:
    """Ein Bild als einseitige PDF in seinem Seitenverhaeltnis (300 dpi)."""
    from PIL import Image

    ziel.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(bild) as quelle:
        quelle.convert("RGB").save(ziel, "PDF", resolution=300)
    return ziel


def _text_oder_pdf(renderer: SeitenRenderer, laden: _Laden, eintrag: dict,
                   titel: str, stamm: str, ergebnis: HeftErgebnis,
                   bildtitel: str = "") -> Path | None:
    """Vorwort, Berichte und sonstige Dateien als Seite(n) im Heftlayout."""
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
        return renderer.bildseite(lokal, bildtitel or titel, stamm)
    if endung in TEXT:
        return renderer.freitextseite(titel, text_dekodieren(lokal.read_bytes()),
                                      stamm, quelle=eintrag["name"])
    if endung == ".docx":
        absaetze = [{"ueberschrift": False, "text": text}
                    for text, _fett in word_absaetze(lokal)]
        return renderer.freitextseite(titel, "", stamm, quelle=eintrag["name"],
                                      absaetze=absaetze)
    # .doc/.odt/.rtf: ueber Gotenberg (LibreOffice) als fertige Seiten
    umgewandelt = _umwandeln(renderer.konfiguration, lokal,
                             renderer.arbeitsordner / f"{stamm}_word.pdf", ergebnis)
    return auf_heftformat(umgewandelt, renderer.layout,
                          renderer.arbeitsordner / f"{stamm}.pdf", ergebnis) \
        if umgewandelt else None


def _kontaktliste(k: Konfiguration, renderer: SeitenRenderer, laden: _Laden,
                  liste: Callable[[str], list[dict]], saison: str, pfad: str,
                  titel: str, stamm: str, ergebnis: HeftErgebnis) -> Path | None:
    """Kontaktlisten/Impressum aus .txt, .docx oder fertigem PDF."""
    if not pfad:
        eintraege = [e for e in (k.get("deckblatt.ansprechpartner") or [])
                     if isinstance(e, dict) and e.get("funktion")]
        zeilen = _zeilen_aus_ansprechpartnern(eintraege)
        return renderer.kontaktlistenseite(titel, zeilen, stamm) if zeilen else None
    eintrag = _eintrag(liste, saison, pfad)
    if eintrag is None:
        return None
    endung = Path(eintrag["name"]).suffix.lower()
    lokal = laden.holen(eintrag)
    if endung in PDF:
        return auf_heftformat(lokal, renderer.layout,
                              renderer.arbeitsordner / f"{stamm}.pdf", ergebnis)
    if endung in TEXT:
        text = text_dekodieren(lokal.read_bytes())
        eintraege = ansprechpartner_lesen(text)
        zeilen = _zeilen_aus_ansprechpartnern(eintraege) if eintraege else \
            [{"text": z.strip(), "fett": False} for z in text.splitlines()
             if z.strip() and not z.lstrip().startswith("#")]
    elif endung == ".docx":
        zeilen = [{"text": text, "fett": fett or _sieht_aus_wie_ueberschrift(text)}
                  for text, fett in word_absaetze(lokal)]
    else:
        ergebnis.warnungen.append(f"'{eintrag['name']}': für {titel} bitte .txt, "
                                  f".docx oder PDF.")
        return None
    return renderer.kontaktlistenseite(titel, zeilen, stamm)


def _zeilen_aus_ansprechpartnern(eintraege: list[dict]) -> list[dict]:
    zeilen = []
    for e in eintraege:
        zeilen.append({"text": f"{e['funktion']}: {e.get('name', '')}".rstrip(": "),
                       "fett": True})
        if e.get("kontakt"):
            zeilen.append({"text": e["kontakt"], "fett": False})
    return zeilen


def _sieht_aus_wie_ueberschrift(text: str) -> bool:
    """'A-Jugend' ja, 'Watzl Nico • 0151-… • a-jgd@…' nein."""
    return len(text) <= 40 and "@" not in text and not re.search(r"\d{3}", text)


def inhalt_einsetzen(rahmen: Path, quelle: Path, ziel: Path) -> Path:
    """Setzt jede Seite von ``quelle`` (z. B. Zeitungsartikel) verkleinert in
    den Inhaltsbereich einer Rahmenseite (Balken + Ueberschrift)."""
    from pypdf import PdfReader, PdfWriter, Transformation

    schreiber = PdfWriter()
    for seite in PdfReader(str(quelle)).pages:
        # Erst ins Dokument, dann einsetzen -- so verlangt es pypdf ab 7.
        grund = schreiber.add_page(PdfReader(str(rahmen)).pages[0])
        trim = grund.trimbox
        x0 = float(trim.left) + INHALT_RAND_MM * MM
        x1 = float(trim.right) - INHALT_RAND_MM * MM
        y0 = float(trim.bottom) + INHALT_UNTEN_MM * MM
        y1 = float(trim.top) - INHALT_OBEN_MM * MM
        q = seite.trimbox
        faktor = min((x1 - x0) / float(q.width), (y1 - y0) / float(q.height))
        dx = x0 + ((x1 - x0) - float(q.width) * faktor) / 2
        dy = y1 - float(q.height) * faktor              # oben anliegend
        grund.merge_transformed_page(
            seite, Transformation().translate(-float(q.left), -float(q.bottom))
            .scale(faktor, faktor).translate(dx, dy))
    with ziel.open("wb") as strom:
        schreiber.write(strom)
    return ziel


def halbe_seiten(quellen: list[Path], layout, ziel: Path) -> Path:
    """Eine Seite mit bis zu zwei halben Anzeigen uebereinander."""
    from pypdf import PdfReader, PdfWriter, Transformation
    from pypdf.generic import RectangleObject

    breite, hoehe = layout.breite_mm * MM, layout.hoehe_mm * MM
    rand = layout.anschnitt_mm * MM
    luft = 8 * MM
    schreiber = PdfWriter()
    neu = schreiber.add_blank_page(width=breite + 2 * rand, height=hoehe + 2 * rand)
    faecher = [(rand + hoehe / 2 + luft / 2, rand + hoehe - luft),     # oben
               (rand + luft, rand + hoehe / 2 - luft / 2)]             # unten
    for quelle, (unten, oben) in zip(quellen[:2], faecher):
        seite = PdfReader(str(quelle)).pages[0]
        q = seite.trimbox
        b_fach, h_fach = breite - 2 * luft, oben - unten
        faktor = min(b_fach / float(q.width), h_fach / float(q.height))
        dx = rand + luft + (b_fach - float(q.width) * faktor) / 2
        dy = unten + (h_fach - float(q.height) * faktor) / 2
        neu.merge_transformed_page(
            seite, Transformation().translate(-float(q.left), -float(q.bottom))
            .scale(faktor, faktor).translate(dx, dy))
    neu.trimbox = RectangleObject((rand, rand, rand + breite, rand + hoehe))
    neu.bleedbox = RectangleObject((0, 0, breite + 2 * rand, hoehe + 2 * rand))
    with ziel.open("wb") as strom:
        schreiber.write(strom)
    return ziel


#: Inhaltsbereich der Inhaltsseiten (wie --rand/--inhalt-oben/--inhalt-unten
#: in heft.css), fuer Artikel, die in eine Rahmenseite gesetzt werden.
INHALT_RAND_MM = 12
INHALT_OBEN_MM = 44
INHALT_UNTEN_MM = 20



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
    from pypdf import PdfReader, PdfWriter, Transformation
    from pypdf.generic import RectangleObject

    breite, hoehe = layout.breite_mm * MM, layout.hoehe_mm * MM
    rand = layout.anschnitt_mm * MM
    toleranz = FORMAT_TOLERANZ_MM * MM
    schreiber = PdfWriter()
    angepasst = 0
    for nummer in range(len(PdfReader(str(quelle)).pages)):
        seite = PdfReader(str(quelle)).pages[nummer]
        trim = seite.trimbox
        tb, th = float(trim.width), float(trim.height)
        if abs(tb - breite) <= toleranz and abs(th - hoehe) <= toleranz:
            schreiber.add_page(seite)
            continue
        angepasst += 1
        # Doppelseite: quer und so gross wie zwei Heftseiten nebeneinander
        # (A4 quer bei A5) -- wie der Teamshop-Flyer. Wird in zwei Seiten
        # zerlegt, so wie es das Layout von Hand macht. Erkannt an der Groesse,
        # nicht am Seitenverhaeltnis: A5 quer (halbe Anzeige) hat dasselbe.
        if abs(tb - 2 * breite) <= 2 * toleranz and abs(th - hoehe) <= 2 * toleranz:
            mitte = float(trim.left) + tb / 2
            teile = [(float(trim.left), mitte), (mitte, float(trim.right))]
        else:
            teile = [(float(trim.left), float(trim.right))]
        for links, rechts in teile:
            # Frisch lesen: die CropBox begrenzt, was eingesetzt wird --
            # so blitzt die Nachbarhaelfte nicht im Anschnitt durch.
            teil = PdfReader(str(quelle)).pages[nummer]
            teil.cropbox = RectangleObject((links, float(trim.bottom),
                                            rechts, float(trim.top)))
            tb_teil = rechts - links
            faktor = min(breite / tb_teil, hoehe / th)
            dx = rand + (breite - tb_teil * faktor) / 2
            dy = rand + (hoehe - th * faktor) / 2
            neu = schreiber.add_blank_page(width=breite + 2 * rand,
                                           height=hoehe + 2 * rand)
            neu.merge_transformed_page(
                teil, Transformation().translate(-links, -float(trim.bottom))
                .scale(faktor, faktor).translate(dx, dy))
            neu.trimbox = RectangleObject((rand, rand, rand + breite, rand + hoehe))
            neu.bleedbox = RectangleObject((0, 0, breite + 2 * rand, hoehe + 2 * rand))
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
