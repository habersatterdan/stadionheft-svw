"""Vorab-Pruefung: Wird ein Lauf gelingen -- und womit?

Warum es das gibt
-----------------
``pruefen`` hat frueher die Konfiguration gelesen, die Ordner aufgezaehlt und
"Konfiguration ist gueltig" gemeldet. Danach brach der Lauf ab, weil fuer vier
von fuenf Mannschaften keine Daten vorlagen. Eine Pruefung, die gruenes Licht
gibt und danach scheitert, ist schlimmer als gar keine: Man verlaesst sich
darauf.

Diese Pruefung beantwortet deshalb genau eine Frage, und zwar ehrlich:

    Wenn ich jetzt auf den Knopf druecke -- was kommt heraus?

Sie sagt je Mannschaft, woher die Zahlen kommen werden und ob ueberhaupt
welche kommen. Sie schreibt eine Probeseite, um Schriften und Vorlagen
wirklich auszuprobieren statt sie nur anzunehmen. Und sie prueft, ob in die
Ordner geschrieben werden kann -- nicht nur, ob es sie gibt.

Bewusst **ohne Netzzugriff**: Die Pruefung soll in Sekunden durch sein und
auch dann etwas sagen, wenn FuPa gerade nicht erreichbar ist. Ob der Abruf
tatsaechlich Zahlen liefert, zeigt ``probe-fupa``.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import programmstand
from .config import Konfiguration, Mannschaft
from .logging_setup import logger

#: Die Dateiarten, aus denen sich eine Mannschaftsdatei speisen kann.
CSV_ARTEN = ("tabelle", "torjaeger", "spieler", "spielplan", "naechstes_spiel")

OK = "ok"
HINWEIS = "hinweis"
PROBLEM = "problem"

_ZEICHEN = {OK: " OK  ", HINWEIS: "  !  ", PROBLEM: "FEHLT"}


@dataclass
class Befund:
    """Ein einzelnes Pruefergebnis."""

    stufe: str
    thema: str
    text: str
    zu_tun: str = ""

    @property
    def zeichen(self) -> str:
        return _ZEICHEN.get(self.stufe, "?")


@dataclass
class Mannschaftslage:
    """Was bei dieser Mannschaft herauskommen wird."""

    schluessel: str
    anzeigename: str
    quelle: str                 # "FuPa", "CSV-Dateien", "Beispieldaten", ""
    bereit: bool
    bemerkung: str = ""
    #: Die Quelle ist zwar eingerichtet, hat aber noch nie Zahlen geliefert.
    #: Das ist etwas anderes als "bereit" und darf nicht so aussehen.
    unsicher: bool = False

    @property
    def zeichen(self) -> str:
        if not self.bereit:
            return "FEHLT"
        return "  ?  " if self.unsicher else " OK  "


@dataclass
class Vorabbericht:
    befunde: list[Befund] = field(default_factory=list)
    mannschaften: list[Mannschaftslage] = field(default_factory=list)

    def ergaenzen(self, stufe: str, thema: str, text: str, zu_tun: str = "") -> None:
        self.befunde.append(Befund(stufe, thema, text, zu_tun))

    @property
    def probleme(self) -> list[Befund]:
        return [b for b in self.befunde if b.stufe == PROBLEM]

    @property
    def hinweise(self) -> list[Befund]:
        return [b for b in self.befunde if b.stufe == HINWEIS]

    @property
    def bereite(self) -> list[Mannschaftslage]:
        return [m for m in self.mannschaften if m.bereit]

    @property
    def offene(self) -> list[Mannschaftslage]:
        return [m for m in self.mannschaften if not m.bereit]

    @property
    def unsichere(self) -> list[Mannschaftslage]:
        return [m for m in self.mannschaften if m.bereit and m.unsicher]

    @property
    def lauffaehig(self) -> bool:
        """Wuerde ein Lauf mindestens eine Datei erzeugen?"""
        return not self.probleme and bool(self.bereite)

    @property
    def urteil(self) -> str:
        if self.probleme:
            return ("Ein Lauf würde fehlschlagen. Bitte zuerst die mit FEHLT "
                    "markierten Punkte beheben.")
        if not self.bereite:
            return ("Ein Lauf würde keine einzige Datei erzeugen – für keine "
                    "Mannschaft sind Daten erreichbar.")

        gesamt = len(self.mannschaften)
        # Eine Quelle, die noch nie Zahlen geliefert hat, ist keine Zusage.
        # Genau an dieser Stelle hat die alte Pruefung Vertrauen verspielt.
        if self.unsichere:
            sicher = len(self.bereite) - len(self.unsichere)
            return (f"Noch nicht abschließend prüfbar: {len(self.unsichere)} von "
                    f"{gesamt} Mannschaften hängen an einem FuPa-Abruf, der hier "
                    f"noch nie getestet wurde. Sicher sind {sicher} Dateien. "
                    f"Bitte einmal 'FuPa-Verbindung prüfen' anstoßen.")
        if self.offene:
            return (f"Ein Lauf erzeugt {len(self.bereite)} von {gesamt} "
                    f"Dateien. Für die übrigen fehlen die Daten.")
        return f"Alles bereit. Ein Lauf erzeugt {len(self.bereite)} Dateien."


# ---------------------------------------------------------------------------
# Die Pruefung
# ---------------------------------------------------------------------------

def vorab_pruefen(k: Konfiguration, *, probeseite: bool = True) -> Vorabbericht:
    """Prueft alles, was sich ohne Netzzugriff pruefen laesst."""
    bericht = Vorabbericht()

    _konfiguration_pruefen(k, bericht)
    _ordner_pruefen(k, bericht)
    _wappen_pruefen(k, bericht)
    if probeseite:
        _probeseite_erzeugen(k, bericht)
    _mannschaften_pruefen(k, bericht)
    _nas_pruefen(k, bericht)

    return bericht


def _konfiguration_pruefen(k: Konfiguration, bericht: Vorabbericht) -> None:
    modus = str(k.get("datenquelle.modus", "demo"))
    ersatz = str(k.get("datenquelle.fallback_modus", "") or "")

    if modus == "demo":
        bericht.ergaenzen(
            HINWEIS, "Datenquelle",
            "Der Modus ist 'demo'. Es entstehen Dateien mit erfundenen Zahlen.",
            "datenquelle.modus auf 'api' oder 'manuell' stellen.")
    elif modus == "api" and not ersatz:
        bericht.ergaenzen(
            HINWEIS, "Datenquelle",
            "Modus 'api' ohne Ersatzquelle. Ist FuPa nicht erreichbar, "
            "entsteht gar nichts.",
            "datenquelle.fallback_modus auf 'manuell' stellen.")

    for warnung in k.warnungen:
        # Die Liga-Hinweise erscheinen schon je Mannschaft weiter unten.
        if "keine Liga eingetragen" in warnung:
            continue
        bericht.ergaenzen(HINWEIS, "Konfiguration", warnung)


def _ordner_pruefen(k: Konfiguration, bericht: Vorabbericht) -> None:
    """Nicht nur: gibt es den Ordner. Sondern: kann man hineinschreiben.

    Auf der NAS ist genau das der Unterschied. Ein eingehaengter Ordner ist
    da -- nur gehoert er einem anderen Benutzer, und der Container darf
    nichts hineinlegen. Das faellt sonst erst beim Speichern auf, nach dem
    ganzen Lauf.
    """
    ordner = (
        ("Eingaben", k.eingabe_ordner, False),
        ("Zwischenergebnisse", k.arbeits_ordner, True),
        ("Ausgaben", k.ausgabe_ordner, True),
    )
    for name, pfad, schreiben_noetig in ordner:
        if not pfad.exists():
            try:
                pfad.mkdir(parents=True, exist_ok=True)
            except OSError as fehler:
                bericht.ergaenzen(
                    PROBLEM, name,
                    f"{pfad} gibt es nicht und lässt sich nicht anlegen "
                    f"({fehler.strerror}).",
                    "Pfad in der config.yaml prüfen oder den Ordner anlegen.")
                continue

        if not schreiben_noetig:
            bericht.ergaenzen(OK, name, str(pfad))
            continue

        fehlergrund = _schreibprobe(pfad)
        if fehlergrund:
            bericht.ergaenzen(
                PROBLEM, name,
                f"In {pfad} kann nicht geschrieben werden ({fehlergrund}).",
                "Im Docker-Betrieb: Besitzer und Rechte des eingehängten "
                "Ordners prüfen.")
        else:
            bericht.ergaenzen(OK, name, str(pfad))


def _schreibprobe(ordner: Path) -> str:
    try:
        with tempfile.NamedTemporaryFile(dir=ordner, prefix=".schreibprobe_"):
            pass
    except OSError as fehler:
        return fehler.strerror or str(fehler)
    return ""


def _wappen_pruefen(k: Konfiguration, bericht: Vorabbericht) -> None:
    logo = k.logo_pfad
    if logo.exists():
        bericht.ergaenzen(OK, "Vereinswappen", str(logo))
    else:
        bericht.ergaenzen(
            HINWEIS, "Vereinswappen",
            f"{logo} wurde nicht gefunden. Die Seiten entstehen ohne Wappen.",
            "verein.logo in der config.yaml prüfen.")


def _probeseite_erzeugen(k: Konfiguration, bericht: Vorabbericht) -> None:
    """Eine echte Seite setzen -- statt zu hoffen, dass es ginge.

    Das prueft in einem Rutsch: Vorlagen vorhanden, WeasyPrint mit allen
    Systembibliotheken lauffaehig, Schriften gefunden, Arbeitsordner
    beschreibbar. Keiner dieser Punkte laesst sich sinnvoll einzeln pruefen.
    """
    from .models import MannschaftsDaten
    from .render.pages import SeitenRenderer

    try:
        with tempfile.TemporaryDirectory(dir=str(k.arbeits_ordner)) as tmp:
            renderer = SeitenRenderer(k, Path(tmp))
            beispiel = MannschaftsDaten(
                schluessel="probe", anzeigename="Probeseite",
                gruppe="Probe", untertitel="Vorab-Prüfung", quelle="probe")
            pfad = renderer.mannschaftsseite("trenner", beispiel, 1)
            groesse = pfad.stat().st_size
            schriften = _schriften_aus(pfad)
    except Exception as fehler:  # noqa: BLE001 - hier zaehlt jeder Ausfall
        logger().exception("Probeseite fehlgeschlagen")
        bericht.ergaenzen(
            PROBLEM, "Seitensatz",
            f"Es lässt sich keine Seite erzeugen: {fehler}",
            "Das ist ein Fehler im Programm oder im Container, nicht in der "
            "Konfiguration. Bitte das Protokoll mitschicken.")
        return

    if groesse < 500:
        bericht.ergaenzen(
            PROBLEM, "Seitensatz",
            "Die Probeseite ist leer geblieben.")
        return

    if schriften:
        bericht.ergaenzen(
            OK, "Seitensatz",
            f"Probeseite gesetzt, Schrift: {', '.join(sorted(schriften))}")
    else:
        bericht.ergaenzen(
            HINWEIS, "Seitensatz",
            "Probeseite gesetzt, aber es ist keine Schrift eingebettet. "
            "Die Seiten könnten beim Druck anders aussehen.")


def _schriften_aus(pdf: Path) -> set[str]:
    """Welche Schriften stecken wirklich in der Seite?

    Die Konfiguration nennt eine Wunschliste ('Segoe UI, Open Sans, ...').
    Was davon ankommt, entscheidet erst das System. Nur die fertige Seite
    weiss es.
    """
    try:
        from pypdf import PdfReader

        namen: set[str] = set()
        for seite in PdfReader(str(pdf)).pages:
            quellen = (seite.get("/Resources") or {}).get("/Font") or {}
            for eintrag in quellen.values():
                roh = str((eintrag.get_object() or {}).get("/BaseFont", ""))
                if roh:
                    # "/ABCDEF+OpenSans-Regular" -> "OpenSans-Regular"
                    name = roh.lstrip("/").split("+")[-1]
                    namen.add(name)
        return namen
    except Exception:  # noqa: BLE001 - eine Nebeninformation darf nie stoeren
        return set()


# ---------------------------------------------------------------------------
# Je Mannschaft: kommen Daten an?
# ---------------------------------------------------------------------------

def _mannschaften_pruefen(k: Konfiguration, bericht: Vorabbericht) -> None:
    modus = str(k.get("datenquelle.modus", "demo"))
    ersatz = str(k.get("datenquelle.fallback_modus", "") or "")
    ordner = k.eingabe_ordner
    fupa_liefert = _fupa_lage(k, bericht)

    aktive = k.aktive_mannschaften()
    if not aktive:
        bericht.ergaenzen(
            PROBLEM, "Mannschaften",
            "Es ist keine einzige Mannschaft auf 'aktiv: true' gestellt.")
        return

    for m in aktive:
        bericht.mannschaften.append(_lage(m, modus, ersatz, ordner, fupa_liefert))
        if m.liga_fehlt:
            bericht.ergaenzen(
                HINWEIS, m.anzeigename,
                "Es ist keine Liga eingetragen. Die Seiten entstehen ohne "
                "Liganamen.",
                f"mannschaften.{m.schluessel}.liga in der config.yaml setzen.")


def _fupa_lage(k: Konfiguration, bericht: Vorabbericht) -> bool | None:
    """Hat FuPa beim letzten Test ueberhaupt Zahlen geliefert?

    Die Vorab-Pruefung geht selbst nicht ins Netz -- sie soll in Sekunden
    durch sein. Der letzte Bericht von ``probe-fupa`` liegt aber auf der
    Platte und kostet nichts. Ohne ihn stuende hier bei jeder Mannschaft
    zuversichtlich "FuPa", obwohl seit Wochen nichts ankommt.

    Rueckgabe: True (liefert), False (liefert nichts), None (nie getestet).
    """
    import json
    from datetime import datetime

    datei = k.arbeits_ordner / "fupa_probe" / "_bericht.json"
    if not datei.exists():
        bericht.ergaenzen(
            HINWEIS, "FuPa-Test",
            "FuPa wurde auf diesem Rechner noch nie getestet.",
            "Einmal 'FuPa-Verbindung prüfen' anstoßen – erst danach lässt "
            "sich sagen, ob der Abruf trägt.")
        return None

    try:
        daten = json.loads(datei.read_text(encoding="utf-8"))
        gefunden = sum(int(n) for n in (daten.get("zusammenfassung") or {}).values())
    except (OSError, ValueError, TypeError):
        return None

    alter = datetime.now() - datetime.fromtimestamp(datei.stat().st_mtime)
    wann = f"vor {alter.days} Tagen" if alter.days else "heute"

    if gefunden:
        arten = ", ".join(sorted(daten.get("zusammenfassung", {})))
        bericht.ergaenzen(OK, "FuPa-Test",
                          f"letzter Test {wann}: {arten}")
        return True

    bericht.ergaenzen(
        HINWEIS, "FuPa-Test",
        f"Beim letzten Test {wann} kam von FuPa nichts an.",
        "Solange das so bleibt, zählen nur die CSV-Dateien.")
    return False


def _lage(m: Mannschaft, modus: str, ersatz: str, ordner: Path,
          fupa_liefert: bool | None) -> Mannschaftslage:
    dateien = csv_dateien(ordner, m.schluessel)
    abrufbar = bool(m.fupa_slug or m.zusatz_urls)

    if modus == "demo" or ersatz == "demo":
        return Mannschaftslage(m.schluessel, m.anzeigename, "Beispieldaten",
                               True, "erfundene Zahlen")

    # FuPa nur dann als Quelle zaehlen, wenn der letzte Test das hergibt.
    # Ein "wahrscheinlich schon" waere genau die Zusage, an der die Pruefung
    # bisher gescheitert ist.
    if modus == "api" and abrufbar and fupa_liefert is not False:
        # Liegen CSV-Dateien bereit, ist die Mannschaft auch ohne FuPa
        # versorgt -- dann ist nichts unsicher.
        offen = not fupa_liefert and not dateien
        zusatz = (f"Ersatz: {len(dateien)} CSV-Dateien" if dateien
                  else "kein Ersatz hinterlegt")
        return Mannschaftslage(
            m.schluessel, m.anzeigename,
            "FuPa" + ("" if fupa_liefert else " (ungeprüft)"),
            True, zusatz, unsicher=offen)

    if dateien:
        herkunft = "CSV-Dateien"
        if modus == "api":
            herkunft = "CSV-Dateien (Ersatz)"
        return Mannschaftslage(m.schluessel, m.anzeigename, herkunft, True,
                               ", ".join(sorted(dateien)))

    if modus == "api" and abrufbar:
        return Mannschaftslage(
            m.schluessel, m.anzeigename, "", False,
            "FuPa liefert nichts und es liegen keine CSV-Dateien bereit")
    if modus == "api":
        return Mannschaftslage(
            m.schluessel, m.anzeigename, "", False,
            "keine FuPa-Teamseite und keine CSV-Dateien")
    return Mannschaftslage(
        m.schluessel, m.anzeigename, "", False,
        f"keine Datei {m.schluessel}_tabelle.csv o. Ä. in {ordner}")


def csv_dateien(ordner: Path, schluessel: str) -> set[str]:
    """Welche Eingabedateien liegen fuer diese Mannschaft **gefuellt** bereit?

    Dass es die Datei gibt, genuegt nicht. ``beispieldaten`` legt Vorlagen mit
    nichts als der Kopfzeile an; der Abruf wertet sie als leer. Wuerde die
    Pruefung sie mitzaehlen, sagte sie wieder etwas zu, das der Lauf nicht
    haelt -- und genau darum geht es hier.
    """
    if not ordner.is_dir():
        return set()
    gefunden = set()
    for art in CSV_ARTEN:
        datei = ordner / f"{schluessel}_{art}.csv"
        if datei.exists() and _hat_datenzeilen(datei):
            gefunden.add(art)
    return gefunden


def _hat_datenzeilen(datei: Path) -> bool:
    """Steht unter der Kopfzeile ueberhaupt etwas?"""
    try:
        with datei.open(encoding="utf-8-sig") as strom:
            for nummer, zeile in enumerate(strom):
                if nummer and zeile.strip(" ;\r\n\t"):
                    return True
    except OSError as fehler:
        logger().debug("%s nicht lesbar: %s", datei, fehler)
    return False


def _nas_pruefen(k: Konfiguration, bericht: Vorabbericht) -> None:
    from .storage.nas import NasAblage

    try:
        erreichbar, meldung = NasAblage(k).erreichbar()
    except Exception as fehler:  # noqa: BLE001
        bericht.ergaenzen(HINWEIS, "NAS-Ablage", f"Nicht prüfbar: {fehler}")
        return
    if not k.get("nas.aktiv"):
        bericht.ergaenzen(OK, "NAS-Ablage", meldung)
    elif erreichbar:
        bericht.ergaenzen(OK, "NAS-Ablage", meldung)
    else:
        bericht.ergaenzen(
            PROBLEM, "NAS-Ablage", meldung,
            "nas.aktiv auf false stellen oder die Ablage einrichten.")


# ---------------------------------------------------------------------------
# Ausgabe als Text (Kommandozeile, Protokoll, Aufgabenplaner)
# ---------------------------------------------------------------------------

def als_text(k: Konfiguration, bericht: Vorabbericht) -> str:
    zeilen: list[str] = [
        f"Programmstand : {programmstand()}",
        f"Konfiguration : {k.quelle}",
        f"Verein        : {k.vereinsname}",
        f"Saison        : {k.saison}",
        f"Datenquelle   : {k.get('datenquelle.modus')} "
        f"(Ersatz: {k.get('datenquelle.fallback_modus') or 'keine'})",
        "",
        "Mannschaften -- woher kommen die Zahlen?",
    ]
    for lage in bericht.mannschaften:
        quelle = lage.quelle or "keine Quelle"
        zeilen.append(f"  {lage.zeichen}  {lage.anzeigename:<12} {quelle:<14} "
                      f"{lage.bemerkung}")

    zeilen += ["", "Technische Voraussetzungen:"]
    for b in bericht.befunde:
        zeilen.append(f"  {b.zeichen}  {b.thema:<20} {b.text}")
        if b.zu_tun and b.stufe != OK:
            zeilen.append(f"         ZU TUN: {b.zu_tun}")

    zeilen += ["", "=" * 68, bericht.urteil, "=" * 68]
    return "\n".join(zeilen)
