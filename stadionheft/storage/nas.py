"""Ablage des fertigen Hefts auf der Synology NAS.

Zwei Wege, bewusst in dieser Reihenfolge empfohlen:

1. ``mount`` -- Der NAS-Ordner ist als Netzlaufwerk bzw. als Docker-Volume
   eingebunden; das Programm kopiert einfach eine Datei. Kein Passwort im
   Programm, keine zusaetzliche Bibliothek, leicht zu verstehen und zu
   reparieren. **Das ist der empfohlene Weg.**

2. ``smb`` -- Direkter Upload ueber das SMB-Protokoll. Nur sinnvoll, wenn ein
   Mount nicht moeglich ist. Benoetigt das Zusatzpaket ``smbprotocol`` und ein
   Passwort, das ausschliesslich ueber eine Umgebungsvariable kommt -- niemals
   aus der Konfigurationsdatei.

Grundsatz in beiden Faellen: **Ein NAS-Problem darf das Heft nicht kosten.**
Die Datei liegt zu diesem Zeitpunkt bereits lokal fertig vor; schlaegt der
Upload fehl, wird das als Warnung gemeldet, nicht als Abbruch.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from ..config import Konfiguration
from ..errors import NasFehler
from ..logging_setup import logger


@dataclass
class AblageErgebnis:
    erfolgreich: bool
    ziel: str = ""
    meldung: str = ""


class NasAblage:
    def __init__(self, konfiguration: Konfiguration) -> None:
        self.k = konfiguration
        self.aktiv = bool(konfiguration.get("nas.aktiv", False))
        self.modus = str(konfiguration.get("nas.modus", "mount"))
        self.ueberschreiben = bool(konfiguration.get("nas.ueberschreiben", False))

    def ablegen(self, datei: Path) -> AblageErgebnis:
        if not self.aktiv:
            return AblageErgebnis(True, meldung="NAS-Upload ist ausgeschaltet.")
        if not datei.exists():
            return AblageErgebnis(False, meldung=f"Datei {datei} existiert nicht.")

        try:
            if self.modus == "smb":
                return self._per_smb(datei)
            return self._per_mount(datei)
        except NasFehler:
            raise
        except Exception as fehler:  # noqa: BLE001
            raise NasFehler(
                str(fehler),
                benutzer_text="Das Heft konnte nicht auf der NAS abgelegt werden.",
                hinweis=(f"Das fertige Heft liegt lokal unter:\n{datei}\n"
                         f"Es kann von dort von Hand hochgeladen werden."),
            ) from fehler

    # -- Weg 1: eingebundener Ordner ----------------------------------------

    def _per_mount(self, datei: Path) -> AblageErgebnis:
        zielordner = Path(str(self.k.get("nas.mount.zielordner", "")))
        if not str(zielordner):
            raise NasFehler(
                "nas.mount.zielordner ist leer.",
                benutzer_text="Es ist kein NAS-Zielordner konfiguriert.",
                hinweis="Bitte nas.mount.zielordner in config/config.yaml eintragen.")

        if not zielordner.exists():
            try:
                zielordner.mkdir(parents=True, exist_ok=True)
            except OSError as fehler:
                raise NasFehler(
                    f"{zielordner}: {fehler}",
                    benutzer_text=f"Der NAS-Ordner '{zielordner}' ist nicht erreichbar.",
                    hinweis=("Bitte pruefen, ob das Netzlaufwerk verbunden ist. "
                             f"Das Heft liegt lokal unter:\n{datei}"),
                ) from fehler

        ziel = zielordner / datei.name
        if ziel.exists() and not self.ueberschreiben:
            ziel = _freier_name(ziel)

        try:
            shutil.copy2(datei, ziel)
        except OSError as fehler:
            raise NasFehler(
                f"{ziel}: {fehler}",
                benutzer_text=f"Das Heft konnte nicht nach '{zielordner}' kopiert werden.",
                hinweis=("Moeglicherweise fehlen Schreibrechte oder die "
                         "Verbindung ist abgebrochen. "
                         f"Das Heft liegt lokal unter:\n{datei}"),
            ) from fehler

        logger().info("Auf NAS abgelegt: %s", ziel)
        return AblageErgebnis(True, str(ziel), f"Auf der NAS abgelegt: {ziel}")

    # -- Weg 2: SMB ----------------------------------------------------------

    def _per_smb(self, datei: Path) -> AblageErgebnis:
        try:
            import smbclient
        except ImportError as fehler:
            raise NasFehler(
                "Paket 'smbprotocol' fehlt.",
                benutzer_text="Der direkte NAS-Upload ist auf diesem Server nicht "
                              "eingerichtet.",
                hinweis=("Entweder 'pip install smbprotocol' ausfuehren oder in "
                         "config/config.yaml nas.modus auf 'mount' stellen."),
            ) from fehler

        host = str(self.k.get("nas.smb.host", ""))
        freigabe = str(self.k.get("nas.smb.freigabe", ""))
        unterordner = str(self.k.get("nas.smb.zielordner", "")).strip("/\\")
        benutzer = str(self.k.get("nas.smb.benutzer", ""))
        variable = str(self.k.get("nas.smb.passwort_umgebungsvariable", "NAS_PASSWORT"))
        passwort = os.environ.get(variable, "")

        if not passwort:
            raise NasFehler(
                f"Umgebungsvariable {variable} ist leer.",
                benutzer_text="Das NAS-Passwort ist auf dem Server nicht hinterlegt.",
                hinweis=f"Bitte die Umgebungsvariable {variable} setzen.")

        try:
            smbclient.ClientConfig(username=benutzer, password=passwort)
            basis = rf"\\{host}\{freigabe}"
            if unterordner:
                basis = basis + "\\" + unterordner.replace("/", "\\")
            ziel = f"{basis}\\{datei.name}"

            if not self.ueberschreiben:
                try:
                    smbclient.stat(ziel)
                    stamm, endung = datei.stem, datei.suffix
                    nummer = 2
                    while True:
                        kandidat = f"{basis}\\{stamm}_{nummer}{endung}"
                        try:
                            smbclient.stat(kandidat)
                            nummer += 1
                        except Exception:
                            ziel = kandidat
                            break
                except Exception:
                    pass   # existiert nicht -> Originalname behalten

            with open(datei, "rb") as quelle, smbclient.open_file(ziel, mode="wb") as senke:
                shutil.copyfileobj(quelle, senke)
        except NasFehler:
            raise
        except Exception as fehler:  # noqa: BLE001
            raise NasFehler(
                f"SMB-Upload nach {host}: {fehler}",
                benutzer_text=f"Die NAS '{host}' ist nicht erreichbar oder die "
                              f"Anmeldung wurde abgelehnt.",
                hinweis=("Bitte Netzwerk, Benutzername und Passwort pruefen. "
                         f"Das Heft liegt lokal unter:\n{datei}"),
            ) from fehler

        logger().info("Per SMB hochgeladen: %s", ziel)
        return AblageErgebnis(True, ziel, f"Auf der NAS abgelegt: {ziel}")

    # -- Vorabpruefung -------------------------------------------------------

    def erreichbar(self) -> tuple[bool, str]:
        """Schnelltest fuer die Oberflaeche ('NAS-Verbindung pruefen')."""
        if not self.aktiv:
            return True, "NAS-Upload ist ausgeschaltet."
        if self.modus == "mount":
            ordner = Path(str(self.k.get("nas.mount.zielordner", "")))
            if not str(ordner):
                return False, "Kein Zielordner konfiguriert."
            if not ordner.exists():
                return False, f"Ordner '{ordner}' ist nicht erreichbar."
            if not os.access(ordner, os.W_OK):
                return False, f"Ordner '{ordner}' ist nicht beschreibbar."
            return True, f"Ordner '{ordner}' ist erreichbar."
        try:
            import smbclient  # noqa: F401
        except ImportError:
            return False, "Paket 'smbprotocol' ist nicht installiert."
        host = self.k.get("nas.smb.host", "")
        variable = str(self.k.get("nas.smb.passwort_umgebungsvariable", "NAS_PASSWORT"))
        if not os.environ.get(variable):
            return False, f"Umgebungsvariable {variable} ist nicht gesetzt."
        return True, f"SMB-Zugang zu '{host}' ist konfiguriert (nicht getestet)."


def _freier_name(ziel: Path) -> Path:
    stamm, endung = ziel.stem, ziel.suffix
    nummer = 2
    kandidat = ziel
    while kandidat.exists():
        kandidat = ziel.with_name(f"{stamm}_{nummer}{endung}")
        nummer += 1
    return kandidat
