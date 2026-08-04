#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Legt die Ordner fuer den Stadionheft-Generator auf der Synology NAS an.
#
# Zugeschnitten auf die vorhandene Struktur der SVWNAS:
#
#     /volume1/SVW/Stadionheft/
#
# Die bestehenden Ordner (Saison 22 23, Fupa-Export, ...) bleiben unangetastet.
# Alles Neue landet in einem eigenen Unterordner "_Programm", damit die
# gewachsene Ablage nicht durcheinandergeraet.
#
# Aufruf ueber SSH:
#
#     sudo bash nas-ordner-anlegen.sh
#
# Der Aufruf ist gefahrlos wiederholbar - vorhandene Ordner werden nicht
# angefasst, es wird nichts geloescht und nichts ueberschrieben.
# ---------------------------------------------------------------------------
set -euo pipefail

# Bei abweichender Ablage nur diese beiden Zeilen anpassen:
BASIS="${BASIS:-/volume1/SVW/Stadionheft}"
SAISON="${SAISON:-Saison 26-27}"

PROGRAMM="$BASIS/_Programm"

echo
echo "Stadionheft-Ordner anlegen"
echo "=========================="
echo "  Basis  : $BASIS"
echo "  Saison : $SAISON"
echo

if [ ! -d "$BASIS" ]; then
    echo "FEHLER: $BASIS existiert nicht."
    echo
    echo "Bitte den Pfad pruefen. Die vorhandenen Freigaben zeigt:"
    echo "    ls /volume1"
    exit 1
fi

anlegen() {
    if [ -d "$1" ]; then
        echo "  vorhanden  $1"
    else
        mkdir -p "$1"
        echo "  ANGELEGT   $1"
    fi
}

anlegen "$PROGRAMM/00_Konfiguration"
anlegen "$PROGRAMM/01_Vorlagen"
anlegen "$PROGRAMM/02_Werbung/vorne"
anlegen "$PROGRAMM/02_Werbung/vorne/_pausiert"
anlegen "$PROGRAMM/02_Werbung/hinten"
anlegen "$PROGRAMM/02_Werbung/hinten/_pausiert"
anlegen "$PROGRAMM/02_Werbung/zwischen"
anlegen "$PROGRAMM/03_Eingaben"
anlegen "$PROGRAMM/04_Zwischenergebnisse"
anlegen "$PROGRAMM/99_Logs"

# Die fertigen Hefte kommen dorthin, wo sie bisher auch lagen:
# in den Saisonordner.
anlegen "$BASIS/$SAISON/05_Ausgaben"

echo
echo "Rechte setzen ..."
# Die Ordner muessen fuer die Benutzergruppe der Dateistation schreibbar sein.
# 'users' ist die Standardgruppe auf einer Synology.
chown -R :users "$PROGRAMM" "$BASIS/$SAISON/05_Ausgaben" 2>/dev/null \
    || echo "  (Gruppenzuordnung uebersprungen - ohne sudo ausgefuehrt?)"
chmod -R 775 "$PROGRAMM" "$BASIS/$SAISON/05_Ausgaben" 2>/dev/null || true

echo
echo "Fertig."
echo
echo "Naechste Schritte:"
echo "  1. Die drei Dateien config/*.example.yaml aus dem Projekt nach"
echo "     $PROGRAMM/00_Konfiguration/"
echo "     kopieren und dabei '.example' aus dem Namen entfernen."
echo "  2. Werbeanzeigen als PDF nach"
echo "     $PROGRAMM/02_Werbung/vorne/  bzw.  .../hinten/"
echo "  3. Im Container Manager ein Projekt mit docker-compose.svwnas.yml"
echo "     anlegen."
echo
