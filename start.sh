#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Stadionheft-Generator starten (macOS / Linux)
#
# Einfach doppelklicken oder im Terminal aufrufen:  ./start.sh
#
# Beim ersten Start wird alles Noetige eingerichtet. Das dauert ein paar
# Minuten. Danach geht es in wenigen Sekunden.
# ---------------------------------------------------------------------------
set -euo pipefail

cd "$(dirname "$0")"

echo
echo "======================================================"
echo "  Stadionheft-Generator - SV Woernitzstein-Berg"
echo "======================================================"
echo

# --- 1. Python vorhanden? --------------------------------------------------
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "FEHLER: Python wurde nicht gefunden."
    echo
    echo "Bitte Python 3.10 oder neuer installieren:"
    echo "  https://www.python.org/downloads/"
    echo
    read -r -p "Zum Beenden Eingabetaste druecken."
    exit 1
fi

# --- 2. Virtuelle Umgebung -------------------------------------------------
if [ ! -d ".venv" ]; then
    echo "[1/4] Richte die Arbeitsumgebung ein (nur beim ersten Mal) ..."
    "$PY" -m venv .venv
else
    echo "[1/4] Arbeitsumgebung vorhanden."
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# --- 3. Abhaengigkeiten ----------------------------------------------------
if ! python -c "import flask, weasyprint, pypdf, yaml" >/dev/null 2>&1; then
    echo "[2/4] Installiere benoetigte Pakete (das dauert einen Moment) ..."
    python -m pip install --quiet --upgrade pip
    if ! python -m pip install --quiet -r requirements.txt; then
        echo
        echo "FEHLER: Die Pakete konnten nicht installiert werden."
        echo
        echo "Unter Linux fehlen meist noch Systembibliotheken. Bitte einmalig:"
        echo "  sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \\"
        echo "                   libffi8 libjpeg62-turbo fonts-dejavu-core fonts-open-sans"
        echo
        read -r -p "Zum Beenden Eingabetaste druecken."
        exit 1
    fi
else
    echo "[2/4] Pakete sind installiert."
fi

# --- 4. Konfiguration ------------------------------------------------------
if [ ! -f "config/config.yaml" ]; then
    echo "[3/4] Lege die Konfiguration an ..."
    python -m stadionheft.cli init
    echo
    echo "HINWEIS: In config/config.yaml stehen noch Platzhalter (TODO)."
    echo "         Das Programm laeuft trotzdem - zunaechst mit Beispieldaten."
    echo
else
    echo "[3/4] Konfiguration vorhanden."
fi

# --- 5. Starten ------------------------------------------------------------
echo "[4/4] Starte die Weboberflaeche ..."
echo
echo "  ------------------------------------------------"
echo "   Im Browser oeffnen:   http://localhost:8080"
echo "  ------------------------------------------------"
echo
echo "  Zum Beenden dieses Fenster schliessen"
echo "  oder Strg+C druecken."
echo

# Browser nach kurzer Wartezeit automatisch oeffnen
(
    sleep 3
    if command -v open >/dev/null 2>&1; then open http://localhost:8080
    elif command -v xdg-open >/dev/null 2>&1; then xdg-open http://localhost:8080
    fi
) >/dev/null 2>&1 &

python -m stadionheft.cli web --port 8080
