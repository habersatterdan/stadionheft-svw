"""Ablage auf der Synology ueber die File-Station-API (auch per QuickConnect).

Wofuer: Die NAS steht im Sportheim, das Programm laeuft woanders. Ein
eingebundener Ordner oder SMB gehen dann nicht -- QuickConnect leitet nur die
DSM-Oberflaeche weiter. Genau ueber diese Oberflaeche spricht auch die
File-Station-API: Ordner auflisten, anlegen, kopieren, hochladen.

Anders als ``mount``/``smb`` laeuft diese Ablage **nicht** automatisch nach
jedem Lauf. Erst wird das Heft angesehen, dann auf Knopfdruck abgelegt:

1. neuer Ausgabe-Ordner im Saisonordner (Name kommt aus der Oberflaeche),
2. Inhalt des Vorlage-Ordners hineinkopieren (Titelbild, Liga-Bilder, ...),
3. die Dateien hochladen -- jede Mannschaft in ihren Unterordner, das
   Deckblatt in den Hauptordner,
4. nachsehen, ob jede Datei mit der richtigen Groesse angekommen ist.

DSM kennt keine API-Schluessel. Angemeldet wird mit einem eigenen Benutzer,
dessen Passwort nur aus einer Umgebungsvariablen kommt -- nie aus der
config.yaml.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from collections.abc import Callable
from typing import Any

from ..config import Konfiguration
from ..errors import NasFehler
from ..logging_setup import logger

#: Fehlercodes, nach denen eine neue Anmeldung hilft (Sitzung abgelaufen,
#: vom Relay verworfen o. ae.). Gesehen: 119 mitten in einer Serie.
SITZUNG_WEG = {106, 107, 119}

#: Die wichtigsten File-Station-Fehler, damit die Meldung etwas sagt.
FEHLERTEXTE = {
    105: "Der Benutzer hat für diese Aktion keine Rechte.",
    400: "Die Anmeldung wurde abgelehnt (Benutzer oder Passwort falsch).",
    401: "Das Konto ist deaktiviert.",
    402: "Für diesen Benutzer ist die Anmeldung gesperrt.",
    403: "Für diesen Benutzer ist eine Zwei-Faktor-Anmeldung eingeschaltet.",
    407: "Die IP-Adresse ist auf der NAS gesperrt (zu viele Fehlversuche).",
    408: "Ordner oder Datei gibt es nicht.",
    414: "Ordner oder Datei gibt es schon.",
    416: "Auf der NAS ist kein Platz mehr.",
    418: "Der Name enthält unzulässige Zeichen.",
    1100: "Der Ordner konnte nicht angelegt werden.",
    1101: "Zu viele Ordner auf einmal.",
}

UNERLAUBT = re.compile(r'[/\\:*?"<>|]')


class FileStationFehler(NasFehler):
    """Ein Fehler, den die NAS selbst gemeldet hat (mit Code)."""

    def __init__(self, technisch: str, code: int | None = None, **kwargs) -> None:
        super().__init__(technisch, **kwargs)
        self.code = code


@dataclass
class Schritt:
    text: str
    ok: bool = True


@dataclass
class AblageBericht:
    """Was beim Ablegen passiert ist -- fuer die Oberflaeche."""

    ordner: str = ""
    erfolgreich: bool = False
    #: Der Ausgabe-Ordner existiert (neu angelegt oder fortgesetzt) -- ein
    #: weiterer Versuch mit demselben Namen darf ihn weiterbenutzen.
    angelegt: bool = False
    schritte: list[Schritt] = field(default_factory=list)
    fehler: str = ""

    def als_dict(self) -> dict:
        return {
            "ordner": self.ordner,
            "erfolgreich": self.erfolgreich,
            "angelegt": self.angelegt,
            "schritte": [{"text": s.text, "ok": s.ok} for s in self.schritte],
            "fehler": self.fehler,
        }


# ---------------------------------------------------------------------------
# Verbindung
# ---------------------------------------------------------------------------

def quickconnect_adresse(kennung: str, timeout: float = 20) -> str:
    """Die Relay-Adresse zu einer QuickConnect-ID (z. B. ``meinverein``).

    Dieselbe Frage stellt auch der Browser, wenn man ``<id>.quickconnect.to``
    oeffnet. Der globale Server kennt die NAS nicht immer selbst
    ("Ds info not found") und nennt dann unter ``sites`` die regionalen
    Server -- die werden der Reihe nach gefragt (gesehen 13.10.2026: global
    mal ja, mal nein; ``dec.quickconnect.to`` zuverlaessig).
    """
    import requests

    anfrage = [{"version": 1, "command": "get_server_info",
                "stop_when_error": False, "stop_when_success": False,
                "id": "dsm_portal_https", "serverID": kennung,
                "is_gofile": False}]
    warteschlange = ["global.quickconnect.to"]
    gefragt: list[str] = []
    letzte_antwort: Any = None
    while warteschlange and len(gefragt) < 6:
        server = warteschlange.pop(0)
        if server in gefragt:
            continue
        gefragt.append(server)
        try:
            antwort = requests.post(f"https://{server}/Serv.php", json=anfrage,
                                    timeout=timeout)
            antwort.raise_for_status()
            letzte_antwort = antwort.json()
        except (requests.RequestException, ValueError) as fehler:
            logger().warning("QuickConnect-Server %s: %s", server, fehler)
            continue
        for eintrag in (letzte_antwort if isinstance(letzte_antwort, list)
                        else [letzte_antwort]):
            if not isinstance(eintrag, dict):
                continue
            region = (eintrag.get("env") or {}).get("relay_region")
            if eintrag.get("errno") == 0 and region:
                return f"https://{kennung}.{region}.quickconnect.to"
            for weiter in eintrag.get("sites") or []:
                if isinstance(weiter, str) and re.fullmatch(
                        r"[a-z0-9.-]+\.quickconnect\.to", weiter):
                    warteschlange.append(weiter)

    if letzte_antwort is None:
        raise NasFehler(
            f"QuickConnect nicht erreichbar ({', '.join(gefragt)})",
            benutzer_text="QuickConnect ist gerade nicht erreichbar.",
            hinweis="Bitte später erneut versuchen.")
    raise NasFehler(
        f"QuickConnect kennt {kennung} nicht ({', '.join(gefragt)}): {letzte_antwort}",
        benutzer_text=f"Die QuickConnect-ID '{kennung}' ist nicht bekannt "
                      f"oder die NAS ist gerade nicht online.",
        hinweis="QuickConnect-ID in der Konfiguration prüfen (nas.filestation).")


class FileStation:
    """Schmaler Client fuer die paar Aufrufe, die gebraucht werden."""

    VERSUCHE = 3

    def __init__(self, adresse: str, benutzer: str, passwort: str,
                 timeout: float = 120) -> None:
        self.adresse = adresse.rstrip("/")
        self.benutzer = benutzer
        self.passwort = passwort
        self.timeout = timeout
        self._sid = ""
        self._sitzung_obj = None

    @classmethod
    def aus_konfiguration(cls, k: Konfiguration) -> "FileStation":
        adresse = str(k.get("nas.filestation.adresse", "") or "").strip()
        kennung = str(k.get("nas.filestation.quickconnect_id", "") or "").strip()
        benutzer = str(k.get("nas.filestation.benutzer", "") or "").strip()
        variable = str(k.get("nas.filestation.passwort_umgebungsvariable",
                             "NAS_PASSWORT"))
        passwort = os.environ.get(variable, "")
        if not benutzer or not passwort:
            raise NasFehler(
                f"Benutzer oder {variable} fehlt.",
                benutzer_text="Für die NAS fehlen Benutzer oder Passwort.",
                hinweis=(f"nas.filestation.benutzer in der Konfiguration und "
                         f"die Umgebungsvariable {variable} setzen."))
        if not adresse:
            if not kennung:
                raise NasFehler(
                    "Weder adresse noch quickconnect_id gesetzt.",
                    benutzer_text="Es ist nicht eingetragen, wie die NAS "
                                  "erreicht wird.",
                    hinweis="nas.filestation.quickconnect_id eintragen.")
            adresse = quickconnect_adresse(kennung)
        return cls(adresse, benutzer, passwort)

    # -- Grundlagen ---------------------------------------------------------

    def _sitzung(self):
        if self._sitzung_obj is None:
            import requests
            self._sitzung_obj = requests.Session()
        return self._sitzung_obj

    def anmelden(self) -> None:
        daten = self._roh({"api": "SYNO.API.Auth", "version": "6",
                           "method": "login", "account": self.benutzer,
                           "passwd": self.passwort, "session": "FileStation",
                           "format": "sid"}, mit_sid=False)
        self._sid = daten["sid"]
        logger().debug("Bei der NAS angemeldet (%s).", self.adresse)

    def abmelden(self) -> None:
        if not self._sid:
            return
        try:
            self._roh({"api": "SYNO.API.Auth", "version": "6",
                       "method": "logout", "session": "FileStation"})
        except NasFehler:
            pass
        self._sid = ""

    def __enter__(self) -> "FileStation":
        self.anmelden()
        return self

    def __exit__(self, *_args) -> None:
        self.abmelden()

    def _roh(self, parameter: dict, *, mit_sid: bool = True,
             dateien: dict | None = None, timeout: float | None = None) -> Any:
        """Ein Aufruf mit Wiederholung.

        Das QuickConnect-Relay antwortet gelegentlich mit 502, und eine
        Sitzung kann verloren gehen (Code 119). Beides heilt ein zweiter
        Versuch -- bei verlorener Sitzung nach neuer Anmeldung.
        """
        import requests

        letzter: Exception | None = None
        for versuch in range(1, self.VERSUCHE + 1):
            daten = dict(parameter)
            url = f"{self.adresse}/webapi/entry.cgi"
            if mit_sid:
                if not self._sid:
                    self.anmelden()
                # Beim Hochladen muss die Sitzung in der Adresse stehen.
                url += f"?_sid={self._sid}"
            try:
                if dateien:
                    for wert in dateien.values():
                        wert[1].seek(0)
                antwort = self._sitzung().post(url, data=daten, files=dateien,
                                               timeout=timeout or self.timeout)
            except requests.RequestException as fehler:
                letzter = fehler
                logger().warning("NAS-Aufruf %s fehlgeschlagen (%s), Versuch %d.",
                                 parameter.get("api"), fehler, versuch)
                time.sleep(2 * versuch)
                continue
            if antwort.status_code >= 500:
                letzter = NasFehler(f"HTTP {antwort.status_code}")
                logger().warning("NAS antwortet mit %d auf %s, Versuch %d.",
                                 antwort.status_code, parameter.get("api"), versuch)
                time.sleep(2 * versuch)
                continue
            try:
                inhalt = antwort.json()
            except ValueError as fehler:
                letzter = fehler
                time.sleep(2 * versuch)
                continue
            if inhalt.get("success"):
                return inhalt.get("data") or {}
            code = (inhalt.get("error") or {}).get("code")
            if code in SITZUNG_WEG and mit_sid and versuch < self.VERSUCHE:
                logger().info("NAS-Sitzung verloren (%s), melde neu an.", code)
                self._sid = ""
                continue
            raise FileStationFehler(
                f"{parameter.get('api')}.{parameter.get('method')}: Fehler {code} "
                f"{json.dumps(inhalt.get('error'), ensure_ascii=False)}",
                code=code,
                benutzer_text=FEHLERTEXTE.get(code, f"Die NAS meldet Fehler {code}."),
                hinweis="")
        raise NasFehler(
            f"{parameter.get('api')}: {letzter}",
            benutzer_text="Die NAS ist über QuickConnect gerade nicht erreichbar.",
            hinweis="Bitte in ein paar Minuten erneut versuchen.") from letzter

    # -- Aufrufe ------------------------------------------------------------

    def auflisten(self, ordner: str) -> list[dict]:
        daten = self._roh({"api": "SYNO.FileStation.List", "version": "2",
                           "method": "list", "folder_path": ordner,
                           "additional": '["size","time"]'})
        return list(daten.get("files") or [])

    def gibt_es(self, pfad: str) -> bool:
        eltern, _, name = pfad.rstrip("/").rpartition("/")
        try:
            return any(f.get("name") == name for f in self.auflisten(eltern or "/"))
        except FileStationFehler as fehler:
            if fehler.code == 408:
                return False
            raise

    def ordner_anlegen(self, eltern: str, name: str) -> str:
        daten = self._roh({"api": "SYNO.FileStation.CreateFolder", "version": "2",
                           "method": "create",
                           "folder_path": json.dumps([eltern], ensure_ascii=False),
                           "name": json.dumps([name], ensure_ascii=False),
                           "force_parent": "false"})
        ordner = (daten.get("folders") or [{}])[0]
        return str(ordner.get("path") or f"{eltern}/{name}")

    def kopieren(self, pfade: list[str], ziel: str, warten: float = 300) -> None:
        """Kopiert (nicht verschiebt) und wartet, bis die NAS fertig ist."""
        if not pfade:
            return
        daten = self._roh({"api": "SYNO.FileStation.CopyMove", "version": "3",
                           "method": "start",
                           "path": json.dumps(pfade, ensure_ascii=False),
                           "dest_folder_path": ziel,
                           # false = Vorhandenes ueberspringen (nicht: Fehler)
                           "overwrite": "false", "remove_src": "false"})
        aufgabe = daten.get("taskid")
        ende = time.monotonic() + warten
        while time.monotonic() < ende:
            time.sleep(1)
            stand = self._roh({"api": "SYNO.FileStation.CopyMove", "version": "3",
                               "method": "status", "taskid": aufgabe})
            if stand.get("finished"):
                if stand.get("error"):
                    raise FileStationFehler(
                        f"CopyMove: {stand.get('error')}",
                        benutzer_text="Die Vorlage konnte nicht vollständig "
                                      "kopiert werden.")
                return
        raise NasFehler(f"CopyMove {aufgabe} nach {warten}s nicht fertig.",
                        benutzer_text="Das Kopieren der Vorlage dauert zu lange.")

    #: Ueber das QuickConnect-Relay gemessen ~60 KB/s; mit Reserve gerechnet.
    MINDEST_RATE = 30_000

    def hochladen(self, datei: Path, zielordner: str, name: str = "") -> None:
        # Zeitgrenze nach Groesse: Ein ganzes Heft (~50 MB) braucht ueber das
        # Relay eine Viertelstunde -- mit 2 Minuten brach es ab (15.10.2026).
        zeit = max(self.timeout, datei.stat().st_size / self.MINDEST_RATE)
        with datei.open("rb") as strom:
            self._roh({"api": "SYNO.FileStation.Upload", "version": "2",
                       "method": "upload", "path": zielordner,
                       "create_parents": "true", "overwrite": "true"},
                      dateien={"file": (name or datei.name, strom,
                                        "application/octet-stream")},
                      timeout=zeit)

    def herunterladen(self, pfad: str, ziel: Path) -> Path:
        """Laedt eine Datei herunter -- mit Wiederholung wie bei ``_roh``.

        Ein Fehler kommt hier als kleines JSON mit Status 200 zurueck, nicht
        als HTTP-Fehler; das wird erkannt und gemeldet.
        """
        import requests

        letzter: Exception | None = None
        for versuch in range(1, self.VERSUCHE + 1):
            if not self._sid:
                self.anmelden()
            try:
                antwort = self._sitzung().get(
                    f"{self.adresse}/webapi/entry.cgi",
                    params={"api": "SYNO.FileStation.Download", "version": "2",
                            "method": "download", "mode": "download",
                            "path": json.dumps([pfad], ensure_ascii=False),
                            "_sid": self._sid},
                    timeout=(self.timeout, max(self.timeout, 1800)))
            except requests.RequestException as fehler:
                letzter = fehler
                time.sleep(2 * versuch)
                continue
            if antwort.status_code >= 500:
                letzter = NasFehler(f"HTTP {antwort.status_code}")
                logger().warning("NAS antwortet mit %d beim Laden von %s, Versuch %d.",
                                 antwort.status_code, pfad, versuch)
                time.sleep(2 * versuch)
                continue
            inhalt = antwort.content or b""
            if inhalt[:1] == b"{" and b'"success":false' in inhalt[:200].replace(b" ", b""):
                try:
                    code = json.loads(inhalt).get("error", {}).get("code")
                except ValueError:
                    code = None
                if code in SITZUNG_WEG and versuch < self.VERSUCHE:
                    self._sid = ""
                    continue
                raise FileStationFehler(
                    f"Download {pfad}: Fehler {code}", code=code,
                    benutzer_text=f"'{pfad.rsplit('/', 1)[-1]}' konnte nicht von "
                                  f"der NAS geladen werden "
                                  f"({FEHLERTEXTE.get(code, f'Fehler {code}')})")
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.write_bytes(inhalt)
            return ziel
        raise NasFehler(
            f"Download {pfad}: {letzter}",
            benutzer_text=f"'{pfad.rsplit('/', 1)[-1]}' konnte nicht von der NAS "
                          f"geladen werden.",
            hinweis="QuickConnect ist gerade unzuverlässig -- bitte erneut versuchen.") \
            from letzter


# ---------------------------------------------------------------------------
# Der Ablauf hinter dem Knopf
# ---------------------------------------------------------------------------

def ordnername_pruefen(name: str) -> str:
    """Ein Ordnername aus der Oberflaeche -- oder eine verstaendliche Absage."""
    sauber = " ".join((name or "").split())
    if not sauber:
        raise NasFehler("leerer Ordnername",
                        benutzer_text="Bitte einen Ordnernamen eingeben.")
    if len(sauber) > 80 or sauber.startswith(".") or UNERLAUBT.search(sauber):
        raise NasFehler(f"unzulaessiger Ordnername {sauber!r}",
                        benutzer_text="Der Ordnername darf keine Zeichen wie "
                                      "/ \\ : * ? \" < > | enthalten und "
                                      "höchstens 80 Zeichen lang sein.")
    return sauber


def ordnername_vorschlagen(vorhandene: list[str], erster_spieltag: datetime | None,
                           muster: str = "{nummer:02d} Ausgabe {datum:%d%m%y}") -> str:
    """Naechste laufende Nummer + Datum des ersten Spiels.

    Aus ``07 Ausgabe 021026`` und ``08 Ausgabe 161026`` wird
    ``09 Ausgabe <Datum>``.
    """
    nummern = [int(t.group(1)) for n in vorhandene
               if (t := re.match(r"\s*(\d+)\s+Ausgabe\b", n))]
    nummer = max(nummern, default=0) + 1
    try:
        return muster.format(nummer=nummer, datum=erster_spieltag or datetime.now())
    except (KeyError, ValueError, IndexError):
        return f"{nummer:02d} Ausgabe {(erster_spieltag or datetime.now()):%d%m%y}"


def zielordner_fuer(k: Konfiguration, schluessel: str) -> str:
    """Unterordner einer Mannschaft im Ausgabe-Ordner ('' = Hauptordner).

    ``ordner:<name>`` steht fuer einen festen Unterordner, z. B.
    ``ordner:_daten`` fuer die Spieldaten des Laufs.
    """
    if schluessel.startswith("ordner:"):
        return schluessel[len("ordner:"):].strip("/")
    zuordnung = k.get("nas.filestation.mannschaftsordner", {}) or {}
    return str(zuordnung.get(schluessel, "") or "").strip("/")


def ablage_ausfuehren(k: Konfiguration, ordnername: str,
                      dateien: list[tuple[str, Path]],
                      fs: FileStation | None = None,
                      fortsetzen: bool = False,
                      melden: Callable[[str], None] | None = None) -> AblageBericht:
    """Legt den Ausgabe-Ordner an, kopiert die Vorlage, laedt die Dateien hoch.

    ``dateien`` sind Paare (Schluessel der Mannschaft bzw. '' fuer den
    Hauptordner, lokale Datei).

    ``fortsetzen``: Ein frueherer Versuch *desselben* Laufs hat den Ordner
    schon angelegt und ist dann abgebrochen (z. B. Relay weg). Dann wird der
    Ordner weiterbenutzt: Die Vorlage wird erneut kopiert, wobei Vorhandenes
    uebersprungen wird, und alle Dateien werden noch einmal hochgeladen.

    ``melden(text)`` bekommt laufend mit, was gerade passiert -- ueber
    QuickConnect dauert die Ablage einige Minuten.
    """
    def jetzt(text: str) -> None:
        if melden:
            melden(text)

    name = ordnername_pruefen(ordnername)
    saison = k.nas_saison_ordner
    vorlage_name = str(k.get("nas.filestation.vorlage_ordner", "") or "").strip("/")
    if not saison:
        raise NasFehler("nas.filestation.saison_ordner fehlt",
                        benutzer_text="Der Saisonordner auf der NAS ist nicht "
                                      "eingetragen.")
    ziel = f"{saison}/{name}"
    bericht = AblageBericht(ordner=ziel)
    client = fs or FileStation.aus_konfiguration(k)

    try:
        if fs is None:
            client.anmelden()

        # Erst alles pruefen, dann anlegen: Ein halb angelegter Ordner waere
        # schlimmer als keiner.
        vorhanden = {f["name"]: f for f in client.auflisten(saison)}
        weiter = fortsetzen and name in vorhanden
        if name in vorhanden and not weiter:
            raise NasFehler(f"{ziel} existiert schon",
                            benutzer_text=f"Den Ordner '{name}' gibt es schon.",
                            hinweis="Bitte einen anderen Namen wählen oder den "
                                    "Ordner auf der NAS erst löschen.")
        vorlage_inhalt: list[dict] = []
        if vorlage_name:
            if vorlage_name not in vorhanden:
                raise NasFehler(f"Vorlage {saison}/{vorlage_name} fehlt",
                                benutzer_text=f"Der Vorlage-Ordner '{vorlage_name}' "
                                              f"fehlt im Saisonordner.")
            vorlage_inhalt = client.auflisten(f"{saison}/{vorlage_name}")
        for _schluessel, datei in dateien:
            if not datei.exists():
                raise NasFehler(f"{datei} fehlt lokal",
                                benutzer_text=f"Die Datei '{datei.name}' gibt es "
                                              f"nicht mehr.",
                                hinweis="Bitte das Heft neu erzeugen.")

        if weiter:
            bericht.schritte.append(Schritt(
                f"Angefangenen Ordner '{name}' fortgesetzt"))
        else:
            client.ordner_anlegen(saison, name)
            bericht.schritte.append(Schritt(f"Ordner '{name}' angelegt"))
        bericht.angelegt = True

        # Kommt ein eigenes Titelbild mit, bleibt das der Vorlage draussen --
        # sonst laegen zwei im Ordner und "Gesamtes Heft bauen" nimmt das
        # falsche.
        if any(not s and ist_titelbild(d.name) for s, d in dateien):
            vorlage_inhalt = [f for f in vorlage_inhalt
                              if f.get("isdir") or not ist_titelbild(f["name"])]
        if vorlage_inhalt:
            jetzt(f"Kopiere die Vorlage '{vorlage_name}' …")
            client.kopieren([f["path"] for f in vorlage_inhalt], ziel)
            bericht.schritte.append(Schritt(
                f"Vorlage kopiert ({len(vorlage_inhalt)} Einträge aus "
                f"'{vorlage_name}')"))

        for nummer, (schluessel, datei) in enumerate(dateien, 1):
            unter = zielordner_fuer(k, schluessel) if schluessel else ""
            ordner = f"{ziel}/{unter}" if unter else ziel
            jetzt(f"Lade {datei.name} hoch ({nummer} von {len(dateien)}) …")
            client.hochladen(datei, ordner)
            bericht.schritte.append(Schritt(
                f"{datei.name} → {unter or 'Hauptordner'}"))

        # Gegenprobe: Ist jede Datei mit der richtigen Groesse da?
        jetzt("Prüfe, ob alles vollständig angekommen ist …")
        fehlend: list[str] = []
        je_ordner: dict[str, dict[str, int]] = {}
        for schluessel, datei in dateien:
            unter = zielordner_fuer(k, schluessel) if schluessel else ""
            ordner = f"{ziel}/{unter}" if unter else ziel
            if ordner not in je_ordner:
                je_ordner[ordner] = {
                    f["name"]: int((f.get("additional") or {}).get("size") or -1)
                    for f in client.auflisten(ordner)}
            if je_ordner[ordner].get(datei.name) != datei.stat().st_size:
                fehlend.append(datei.name)
        if fehlend:
            raise NasFehler(f"nicht vollstaendig angekommen: {fehlend}",
                            benutzer_text="Nicht alle Dateien sind vollständig "
                                          "auf der NAS angekommen: "
                                          + ", ".join(fehlend),
                            hinweis="Bitte erneut auf „Auf NAS ablegen“ "
                                    "klicken -- der Ordner wird fortgesetzt.")
        bericht.schritte.append(Schritt(
            f"Geprüft: alle {len(dateien)} Dateien vollständig angekommen"))
        bericht.erfolgreich = True
        logger().info("NAS-Ablage fertig: %s", ziel)
    except NasFehler as fehler:
        bericht.fehler = " ".join(t for t in (fehler.benutzer_text, fehler.hinweis) if t)
        bericht.schritte.append(Schritt(fehler.benutzer_text, ok=False))
        logger().error("NAS-Ablage abgebrochen: %s", fehler.technisch)
    finally:
        if fs is None:
            client.abmelden()
    return bericht


def ist_titelbild(name: str) -> bool:
    """Titelbild.jpg / .jpeg / .png -- so heisst es in Vorlage und Ausgabe."""
    return bool(re.match(r"titelbild\.(jpe?g|png)$", name, re.I))


def titelbild_holen(k: Konfiguration, ziel_ordner: Path) -> Path | None:
    """Das Titelbild aus dem Vorlage-Ordner der NAS, falls es eins gibt.

    So wird das Bild an einer Stelle getauscht -- dort, wo es fuer die Ausgabe
    ohnehin liegt. Klappt das nicht, nimmt das Deckblatt das Bild aus dem
    Eingabeordner.
    """
    saison = k.nas_saison_ordner
    vorlage = str(k.get("nas.filestation.vorlage_ordner", "") or "").strip("/")
    if not saison or not vorlage:
        return None
    try:
        with FileStation.aus_konfiguration(k) as fs:
            kandidaten = [f for f in fs.auflisten(f"{saison}/{vorlage}")
                          if not f.get("isdir")
                          and re.match(r"titelbild\.(jpe?g|png)$", f["name"], re.I)]
            if not kandidaten:
                return None
            pfad = kandidaten[0]["path"]
            antwort = fs._sitzung().get(
                f"{fs.adresse}/webapi/entry.cgi",
                params={"api": "SYNO.FileStation.Download", "version": "2",
                        "method": "download", "mode": "download",
                        "path": json.dumps([pfad], ensure_ascii=False),
                        "_sid": fs._sid},
                timeout=fs.timeout)
            # Ein Fehler kommt als kleines JSON mit Status 200 zurueck.
            if (antwort.status_code != 200 or not antwort.content
                    or antwort.content[:1] == b"{"):
                logger().warning("Titelbild von der NAS nicht geladen (%s).",
                                 antwort.status_code)
                return None
            ziel_ordner.mkdir(parents=True, exist_ok=True)
            ziel = ziel_ordner / ("titelbild_nas" + Path(pfad).suffix.lower())
            ziel.write_bytes(antwort.content)
            logger().info("Titelbild aus der NAS-Vorlage: %s", pfad)
            return ziel
    except NasFehler as fehler:
        logger().warning("Titelbild von der NAS nicht geladen: %s", fehler.technisch)
        return None


# ---------------------------------------------------------------------------
# Ansprechpartner aus einer Textdatei auf der NAS
# ---------------------------------------------------------------------------

ANSPRECHPARTNER_KOPF = """\
# Ansprechpartner fuer das Stadionheft (Deckblatt und Gesamtheft).
#
# Je Person ein Block aus zwei Zeilen, dazwischen eine Leerzeile:
#   Funktion: Name
#   Telefon • E-Mail
# Zeilen mit # am Anfang werden nicht gedruckt.
"""


def ansprechpartner_lesen(text: str) -> list[dict]:
    """``Funktion: Name`` + Kontaktzeile(n) je Block -> Eintraege."""
    eintraege: list[dict] = []
    zeilen = [z.rstrip() for z in text.replace("\r\n", "\n").split("\n")
              if not z.lstrip().startswith("#")]
    for block in re.split(r"\n\s*\n", "\n".join(zeilen)):
        teile = [z.strip() for z in block.strip().split("\n") if z.strip()]
        if not teile:
            continue
        funktion, _, name = teile[0].partition(":")
        eintraege.append({"funktion": funktion.strip(), "name": name.strip(),
                          "kontakt": " ".join(" ".join(teile[1:]).split())})
    return [e for e in eintraege if e["funktion"]]


def ansprechpartner_schreiben(eintraege: list[dict]) -> str:
    bloecke = [f"{e.get('funktion', '')}: {e.get('name', '')}\n{e.get('kontakt', '')}"
               for e in eintraege]
    return ANSPRECHPARTNER_KOPF + "\n" + "\n\n".join(bloecke) + "\n"


def text_dekodieren(daten: bytes) -> str:
    """UTF-8 (auch mit BOM, so speichert der DSM-Texteditor), sonst Windows."""
    try:
        return daten.decode("utf-8-sig")
    except UnicodeDecodeError:
        return daten.decode("cp1252", errors="replace")


def ansprechpartner_von_nas(k: Konfiguration, arbeitsordner: Path) -> list[dict] | None:
    """Liest ``heft.ansprechpartner_datei`` aus dem Saisonordner.

    ``None`` heisst: keine Datei (oder NAS nicht erreichbar) -- dann gilt
    die Liste aus der Konfiguration.
    """
    datei = str(k.get("heft.ansprechpartner_datei", "") or "").strip("/")
    saison = k.nas_saison_ordner
    if not datei or not saison:
        return None
    try:
        with FileStation.aus_konfiguration(k) as fs:
            ziel = fs.herunterladen(f"{saison}/{datei}",
                                    Path(arbeitsordner) / "ansprechpartner.txt")
        eintraege = ansprechpartner_lesen(text_dekodieren(ziel.read_bytes()))
        logger().info("Ansprechpartner von der NAS: %d Einträge (%s)",
                      len(eintraege), datei)
        return eintraege
    except NasFehler as fehler:
        logger().warning("Ansprechpartner nicht von der NAS: %s", fehler.technisch)
        return None


# ---------------------------------------------------------------------------
# Neue Saison
# ---------------------------------------------------------------------------

def vorherige_saison(namen: list[str], aktuell: str) -> str:
    """Der juengste andere 'Saison XX-YY'-Ordner (nach Startjahr)."""
    kandidaten = []
    for name in namen:
        treffer = re.fullmatch(r"Saison\s*(\d{2})-(\d{2})", name.strip())
        if treffer and name != aktuell:
            kandidaten.append((int(treffer.group(1)), name))
    return max(kandidaten)[1] if kandidaten else ""


def saison_anlegen(k: Konfiguration, fs: FileStation | None = None) -> AblageBericht:
    """Legt den Saisonordner an und kopiert Vorlage und 'Allgemein' (Werbung,
    Ansprechpartner) aus der Vorsaison. Ein vorhandener Ordner bleibt
    unangetastet."""
    saison = k.nas_saison_ordner
    eltern, _, name = saison.rpartition("/")
    bericht = AblageBericht(ordner=saison)
    client = fs or FileStation.aus_konfiguration(k)
    try:
        if fs is None:
            client.anmelden()
        namen = [f["name"] for f in client.auflisten(eltern or "/") if f.get("isdir")]
        if name in namen:
            raise NasFehler(f"{saison} existiert",
                            benutzer_text=f"Den Saisonordner '{name}' gibt es schon.")
        vorher = vorherige_saison(namen, name)
        client.ordner_anlegen(eltern, name)
        bericht.angelegt = True
        bericht.schritte.append(Schritt(f"Saisonordner '{name}' angelegt"))
        if vorher:
            alt = {f["name"]: f["path"] for f in client.auflisten(f"{eltern}/{vorher}")}
            mitnehmen = [n for n in (str(k.get("nas.filestation.vorlage_ordner", "") or ""),
                                     "Allgemein") if n and n in alt]
            if mitnehmen:
                client.kopieren([alt[n] for n in mitnehmen], saison)
                bericht.schritte.append(Schritt(
                    f"Aus '{vorher}' übernommen: {', '.join(mitnehmen)}"))
        else:
            bericht.schritte.append(Schritt("Keine Vorsaison gefunden -- leer angelegt"))
        bericht.erfolgreich = True
    except NasFehler as fehler:
        bericht.fehler = " ".join(t for t in (fehler.benutzer_text, fehler.hinweis) if t)
        bericht.schritte.append(Schritt(fehler.benutzer_text, ok=False))
    finally:
        if fs is None:
            client.abmelden()
    return bericht
