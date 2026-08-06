"""Der Ablauf: Daten holen, ablegen, auswerten.

Hier laeuft alles zusammen. Wichtig ist die strikte Trennung der beiden
Vorgaenge:

* :meth:`Berater.abrufen` spricht mit dem Netz und schreibt in die Datenbank.
  Das dauert und passiert selten (nach Zeitplan oder auf Knopfdruck).
* :meth:`Berater.bericht` liest nur aus der Datenbank und rechnet. Das geht
  schnell und passiert bei jedem Seitenaufruf.

Deshalb loest kein Klick in der Oberflaeche eine Anfrage an Kickbase aus --
und die Oberflaeche funktioniert auch dann, wenn gerade nichts erreichbar ist.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Sequence

from .analyse.bewertung import Referenzwerte, kader_bewerten
from .config import Konfiguration
from .errors import KickbaseFehler
from .logging_setup import logger
from .models import Lagebericht, Spieler
from .quellen import demo as demoquelle
from .quellen.http import DateiCache
from .quellen.kickbase_api import KickbaseQuelle, namen_ergaenzen
from .quellen.openligadb import Ligalage, OpenLigaDbQuelle
from .speicher import Speicher

#: Ab so vielen gespeicherten Marktwerten ist die eigene Reihe aussagekraeftig
#: genug -- dann muss der Verlauf nicht mehr bei Kickbase geholt werden.
EIGENE_HISTORIE_REICHT = 20


class Berater:
    """Die Anwendung hinter Oberflaeche und Kommandozeile."""

    def __init__(self, konfiguration: Konfiguration | None = None) -> None:
        self.k = konfiguration or Konfiguration.laden()
        self.speicher = Speicher(self.k.datenbank)
        self._sperre = threading.Lock()
        self.laeuft = False
        self.letzte_meldung = ""

    # -- Abruf -------------------------------------------------------------

    def abrufen(self) -> dict:
        """Holt alle Daten und legt sie ab. Gibt eine kurze Zusammenfassung zurueck."""
        if not self._sperre.acquire(blocking=False):
            return {"erfolgreich": False,
                    "meldung": "Es läuft bereits ein Abruf."}
        beginn = time.monotonic()
        self.laeuft = True
        try:
            if self.k.demomodus:
                ergebnis = self._abruf_demo()
            else:
                ergebnis = self._abruf_echt()
            dauer = time.monotonic() - beginn
            self.speicher.abruf_vermerken(
                True, ergebnis.get("spieler", 0), dauer, ergebnis.get("meldung", ""))
            ergebnis["dauer_s"] = round(dauer, 1)
            self.letzte_meldung = ergebnis.get("meldung", "")
            logger().info("Abruf fertig in %.1f s: %s", dauer, self.letzte_meldung)
            return ergebnis
        except KickbaseFehler as fehler:
            dauer = time.monotonic() - beginn
            self.speicher.abruf_vermerken(False, 0, dauer, fehler.benutzer_text)
            self.letzte_meldung = fehler.benutzer_text
            logger().error("Abruf fehlgeschlagen: %s", fehler.technisch)
            return {"erfolgreich": False, "meldung": fehler.benutzer_text,
                    "hinweis": fehler.hinweis, "dauer_s": round(dauer, 1)}
        finally:
            self.laeuft = False
            self._sperre.release()

    def _abruf_demo(self) -> dict:
        """Beispieldaten -- damit die Anwendung ohne Konto benutzbar ist."""
        logger().info("Demomodus: erzeuge Beispieldaten.")
        spieler = demoquelle.demo_spieler()
        demoquelle.demo_kader(spieler)
        demoquelle.demo_transfermarkt(spieler)
        self.speicher.spieler_speichern(spieler)
        self.speicher.notiz_setzen("ligalage", demoquelle.demo_ligalage().als_dict())
        self.speicher.notiz_setzen("liga", {
            "name": "Beispielliga (Demodaten)", "budget": 12_500_000,
            "teamwert": 148_000_000, "id": "demo", "demo": True})
        return {"erfolgreich": True, "spieler": len(spieler),
                "meldung": f"Demodaten erzeugt ({len(spieler)} Spieler)."}

    def _abruf_echt(self) -> dict:
        cache = DateiCache(
            self.k.pfad(None, "daten/kickbase/cache"),
            int(self.k.get("abruf.cache_minuten", 60)))

        quelle = KickbaseQuelle(
            self.k.email, self.k.passwort, cache=cache,
            wettbewerb_id=self.k.wettbewerb_id,
            pause_ms=int(self.k.get("abruf.hoeflichkeitspause_ms", 250)))
        quelle.anmelden()

        liga = quelle.liga_waehlen(self.k.liga_id)
        logger().info("Liga: %s (%s)", liga["name"], liga["id"])
        liga_id = liga["id"]

        kader = quelle.eigener_kader(liga_id)
        markt = quelle.transfermarkt(liga_id)
        alle = quelle.wettbewerbsspieler()
        namen = quelle.mannschaftsnamen()

        # Zusammenfuehren: derselbe Spieler kann in mehreren Listen stehen.
        gesamt: dict[str, Spieler] = {}
        for liste in (alle, markt, kader):
            for s in liste:
                vorhanden = gesamt.get(s.id)
                if vorhanden is None:
                    gesamt[s.id] = s
                else:
                    _zusammenfuehren(vorhanden, s)
        namen_ergaenzen(gesamt.values(), namen)

        auswahl = self._anreicherungsliste(list(gesamt.values()))
        logger().info("%d Spieler bekannt, %d werden im Detail geholt.",
                      len(gesamt), len(auswahl))
        for nummer, s in enumerate(auswahl, start=1):
            mit_verlauf = len(self.speicher.marktwert_reihe(s.id)) < EIGENE_HISTORIE_REICHT
            quelle.anreichern(liga_id, s,
                              marktwert_tage=int(self.k.get("abruf.marktwert_tage", 92)),
                              mit_verlauf=mit_verlauf)
            if nummer % 25 == 0:
                logger().info("  ... %d von %d Spielern geholt.", nummer, len(auswahl))

        budget = quelle.budget(liga_id) or liga.get("budget", 0)
        self.speicher.notiz_setzen("liga", {
            "id": liga_id, "name": liga["name"], "budget": budget,
            "teamwert": liga.get("teamwert", 0), "platz": liga.get("platz", 0),
            "mitspieler": liga.get("mitspieler", 0), "demo": False})

        meldungen = self._zusatzquellen(list(gesamt.values()))
        anzahl = self.speicher.spieler_speichern(gesamt.values())
        self.speicher.aufraeumen()

        meldung = (f"{anzahl} Spieler aktualisiert, davon {len(auswahl)} im Detail. "
                   f"Kader: {len(kader)}, Transfermarkt: {len(markt)}.")
        if meldungen:
            meldung += " " + " ".join(meldungen)
        return {"erfolgreich": True, "spieler": anzahl, "meldung": meldung,
                "liga": liga["name"]}

    def _anreicherungsliste(self, spieler: Sequence[Spieler]) -> list[Spieler]:
        """Waehlt aus, fuer wen die teuren Detailabfragen gemacht werden.

        Alle Bundesligaspieler im Detail zu holen waere unnoetig und wuerde
        die Schnittstelle unhoeflich belasten. Gebraucht werden: der eigene
        Kader, alles auf dem Transfermarkt und je Position die
        interessantesten Kandidaten.
        """
        je_position = int(self.k.get("abruf.kandidaten_je_position", 25))
        mindest = int(self.k.get("analyse.mindest_marktwert", 300000))

        pflicht = [s for s in spieler if s.im_eigenen_team or s.auf_transfermarkt]
        gewaehlt = {s.id for s in pflicht}

        nach_position: dict[int, list[Spieler]] = {}
        for s in spieler:
            if s.id in gewaehlt or s.marktwert < mindest:
                continue
            nach_position.setdefault(s.position, []).append(s)

        auswahl = list(pflicht)
        for kandidaten in nach_position.values():
            # Sortiert nach Durchschnittspunkten: wer nie punktet, ist auch
            # als Schnaeppchen uninteressant.
            kandidaten.sort(key=lambda s: (s.punkte_schnitt, s.marktwert), reverse=True)
            auswahl.extend(kandidaten[:je_position])
        return auswahl

    def _zusatzquellen(self, spieler: Sequence[Spieler]) -> list[str]:
        """Spielplan und optionale Verletzungsmeldungen."""
        meldungen: list[str] = []

        if self.k.get("quellen.openligadb.aktiv", True):
            try:
                quelle = OpenLigaDbQuelle(
                    liga=str(self.k.get("quellen.openligadb.liga", "bl1")),
                    saison=self.k.get("quellen.openligadb.saison", ""),
                    cache=DateiCache(self.k.pfad(None, "daten/kickbase/cache"), 180))
                lage = quelle.lage_holen()
                self.speicher.notiz_setzen("ligalage", lage.als_dict())
                meldungen.append(f"Spielplan: {len(lage.begegnungen)} Begegnungen.")
            except KickbaseFehler as fehler:
                logger().warning("OpenLigaDB: %s", fehler.technisch)
                meldungen.append("Spielplan nicht erreichbar.")

        if self.k.get("quellen.verletzungen.aktiv", False):
            seiten = self.k.get("quellen.verletzungen.seiten", []) or []
            try:
                from .quellen.verletzungen import VerletzungsQuelle
                lage = VerletzungsQuelle(seiten).lage_holen(spieler)
                getroffen = lage.anwenden(spieler)
                meldungen.append(f"Verletzungsmeldungen: {getroffen} zugeordnet.")
                for fehler in lage.fehler:
                    logger().warning("Verletzungsquelle: %s", fehler)
            except KickbaseFehler as fehler:
                logger().warning("Verletzungsquellen: %s", fehler.technisch)
                meldungen.append("Verletzungsseiten nicht erreichbar.")

        return meldungen

    # -- Auswertung --------------------------------------------------------

    def ligalage(self) -> Ligalage | None:
        roh = self.speicher.notiz_lesen("ligalage")
        if not isinstance(roh, dict):
            return None
        try:
            return Ligalage.aus_dict(roh)
        except (ValueError, TypeError) as fehler:
            logger().warning("Gespeicherter Spielplan unlesbar: %s", fehler)
            return None

    def bericht(self) -> Lagebericht:
        """Baut den kompletten Lagebericht aus den gespeicherten Daten."""
        spieler = self.speicher.spieler_laden()
        liga = self.speicher.notiz_lesen("liga", {}) or {}
        lage = self.ligalage()

        bericht = Lagebericht(
            erstellt=datetime.now(),
            liga_name=str(liga.get("name", "")),
            budget=int(liga.get("budget", 0) or 0),
            teamwert=int(liga.get("teamwert", 0) or 0))

        if not spieler:
            bericht.warnungen.append(
                "Es sind noch keine Daten gespeichert. Bitte einen Abruf starten.")
            return bericht

        referenz = Referenzwerte.aus_spielern(
            spieler, int(self.k.get("analyse.mindest_spiele", 3)))

        eigene = [s for s in spieler if s.im_eigenen_team]
        markt = [s for s in spieler if s.auf_transfermarkt and not s.im_eigenen_team]
        mindest = int(self.k.get("analyse.mindest_marktwert", 300000))
        frei = [s for s in spieler
                if not s.im_eigenen_team and s.marktwert >= mindest]

        bericht.eigene = kader_bewerten(eigene, referenz, self.k, lage)
        bericht.transfermarkt = kader_bewerten(markt, referenz, self.k, lage,
                                               mit_preis=True)
        bericht.kandidaten = kader_bewerten(frei, referenz, self.k, lage)

        letzter = self.speicher.letzter_abruf()
        bericht.quellen = {
            "letzter_abruf": (letzter or {}).get("zeit", "noch nie"),
            "abruf_erfolgreich": "ja" if (letzter or {}).get("erfolgreich") else "nein",
            "spielplan": ("vorhanden" if lage and lage.begegnungen
                          else "nicht vorhanden"),
            "modus": "Demodaten" if liga.get("demo") or self.k.demomodus else "Kickbase",
        }
        # Auf den Demomodus weist die Oberflaeche selbst hin -- hier waere es
        # nur eine zweite, gleichlautende Meldung.
        if lage is None:
            bericht.warnungen.append(
                "Kein Spielplan gespeichert – die Kennzahl 'Nächste Gegner' "
                "bleibt ohne Wirkung.")
        return bericht

    def spieler_finden(self, spieler_id: str) -> Spieler | None:
        for s in self.speicher.spieler_laden():
            if s.id == str(spieler_id):
                return s
        return None


def _zusammenfuehren(ziel: Spieler, zusatz: Spieler) -> None:
    """Uebernimmt die aussagekraeftigeren Angaben aus einer zweiten Liste."""
    for feld in ("vorname", "nachname", "team_name", "besitzer"):
        if not getattr(ziel, feld) and getattr(zusatz, feld):
            setattr(ziel, feld, getattr(zusatz, feld))
    for feld in ("marktwert", "punkte_gesamt", "punkte_schnitt", "spiele",
                 "position", "team_id", "marktwert_trend"):
        if not getattr(ziel, feld) and getattr(zusatz, feld):
            setattr(ziel, feld, getattr(zusatz, feld))
    # Status 0 kann "fit" heissen oder "nicht mitgeliefert" -- der von Null
    # verschiedene Wert ist der informativere.
    if not ziel.status and zusatz.status:
        ziel.status = zusatz.status
    ziel.im_eigenen_team = ziel.im_eigenen_team or zusatz.im_eigenen_team
    ziel.auf_transfermarkt = ziel.auf_transfermarkt or zusatz.auf_transfermarkt
    if zusatz.angebotspreis:
        ziel.angebotspreis = zusatz.angebotspreis


class Planer:
    """Startet den Abruf in festem Abstand im Hintergrund.

    Ein eigener Faden statt eines Cron-Eintrags: so genuegt es, den Container
    zu starten -- auf der NAS muss nichts zusaetzlich eingerichtet werden.
    """

    def __init__(self, berater: Berater) -> None:
        self.berater = berater
        self.faden: threading.Thread | None = None
        self.beenden = threading.Event()

    @property
    def intervall_s(self) -> float:
        stunden = float(self.berater.k.get("abruf.intervall_stunden", 6))
        return max(600.0, stunden * 3600)

    def starten(self) -> None:
        if not self.berater.k.get("abruf.automatisch", True):
            logger().info("Automatischer Abruf ist ausgeschaltet.")
            return
        if self.faden and self.faden.is_alive():
            return
        self.faden = threading.Thread(target=self._schleife, name="kickbase-abruf",
                                      daemon=True)
        self.faden.start()
        logger().info("Automatischer Abruf alle %.1f Stunden.",
                      self.intervall_s / 3600)

    def stoppen(self) -> None:
        self.beenden.set()

    def _schleife(self) -> None:
        # Beim Start kurz warten, damit die Weboberflaeche zuerst erreichbar ist.
        if self.beenden.wait(15):
            return
        while not self.beenden.is_set():
            try:
                self.berater.abrufen()
            except Exception as fehler:  # ein Fehler darf den Faden nie beenden
                logger().exception("Unerwarteter Fehler im Abruf: %s", fehler)
            if self.beenden.wait(self.intervall_s):
                return
