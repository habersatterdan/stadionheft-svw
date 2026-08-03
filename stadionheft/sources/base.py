"""Gemeinsame Schnittstelle aller Datenquellen.

Der Rest des Programms weiss nicht, ob die Daten von FuPa, aus einer CSV-Datei
oder aus den eingebauten Beispieldaten stammen. Damit laesst sich eine neue
Quelle ergaenzen, ohne Rendering oder Oberflaeche anzufassen -- und ein
Ausfall von FuPa legt die Hefterstellung nicht lahm.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..config import Konfiguration, Mannschaft
from ..models import MannschaftsDaten


@runtime_checkable
class Datenquelle(Protocol):
    """Liefert die Daten genau einer Mannschaft."""

    #: Kurzname, taucht im Protokoll und im Snapshot auf.
    name: str

    def hole(self, mannschaft: Mannschaft) -> MannschaftsDaten:
        """Laedt alle Daten fuer eine Mannschaft.

        Erwartete Fehler duerfen als ``StadionheftFehler`` geworfen werden.
        Teilweise fehlende Daten (z. B. kein naechstes Spiel) sind *kein*
        Fehler, sondern landen in ``MannschaftsDaten.warnungen``.
        """
        ...


def basis_daten(mannschaft: Mannschaft, quelle: str) -> MannschaftsDaten:
    """Erzeugt ein vorbefuelltes Ergebnisobjekt aus der Konfiguration."""
    return MannschaftsDaten(
        schluessel=mannschaft.schluessel,
        anzeigename=mannschaft.anzeigename,
        gruppe=mannschaft.gruppe,
        untertitel=mannschaft.untertitel,
        liga=mannschaft.liga,
        fupa_team_url=mannschaft.fupa_team_url,
        quelle=quelle,
    )


def quelle_erzeugen(modus: str, konfiguration: Konfiguration) -> Datenquelle:
    """Fabrikfunktion: erzeugt die Datenquelle zum konfigurierten Modus."""
    # Verzoegerter Import, damit z. B. 'requests' nur geladen wird,
    # wenn der API-Modus wirklich benutzt wird.
    if modus == "api":
        from .fupa_api import FupaApiQuelle
        return FupaApiQuelle(konfiguration)
    if modus == "manuell":
        from .manuell import ManuelleQuelle
        return ManuelleQuelle(konfiguration)
    if modus == "demo":
        from .demo import DemoQuelle
        return DemoQuelle(konfiguration)
    from ..errors import KonfigurationsFehler
    raise KonfigurationsFehler(
        f"Unbekannter Datenquellen-Modus '{modus}'.",
        benutzer_text=f"Der Datenquellen-Modus '{modus}' ist nicht bekannt.",
        hinweis="Erlaubt sind: api, manuell, demo.",
    )
