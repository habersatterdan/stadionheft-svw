@echo off
REM ---------------------------------------------------------------------------
REM  Stadionheft-Generator starten (Windows)
REM
REM  Einfach doppelklicken.
REM
REM  Beim ersten Start wird alles Noetige eingerichtet. Das dauert ein paar
REM  Minuten. Danach geht es in wenigen Sekunden.
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

echo.
echo ======================================================
echo   Stadionheft-Generator - SV Woernitzstein-Berg
echo ======================================================
echo.

REM --- 1. Python vorhanden? --------------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo FEHLER: Python wurde nicht gefunden.
    echo.
    echo Bitte Python 3.10 oder neuer installieren:
    echo   https://www.python.org/downloads/
    echo.
    echo WICHTIG: Bei der Installation den Haken bei
    echo          "Add Python to PATH" setzen!
    echo.
    pause
    exit /b 1
)

REM --- 2. Virtuelle Umgebung -------------------------------------------------
if not exist ".venv" (
    echo [1/4] Richte die Arbeitsumgebung ein ^(nur beim ersten Mal^) ...
    python -m venv .venv
) else (
    echo [1/4] Arbeitsumgebung vorhanden.
)

call .venv\Scripts\activate.bat

REM --- 3. Abhaengigkeiten ----------------------------------------------------
python -c "import flask, weasyprint, pypdf, yaml" >nul 2>&1
if errorlevel 1 (
    echo [2/4] Installiere benoetigte Pakete ^(das dauert einen Moment^) ...
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet -r requirements.txt
    if errorlevel 1 (
        echo.
        echo FEHLER: Die Pakete konnten nicht installiert werden.
        echo Bitte die Internetverbindung pruefen.
        echo.
        pause
        exit /b 1
    )
) else (
    echo [2/4] Pakete sind installiert.
)

REM --- 4. Konfiguration ------------------------------------------------------
if not exist "config\config.yaml" (
    echo [3/4] Lege die Konfiguration an ...
    python -m stadionheft.cli init
    echo.
    echo HINWEIS: In config\config.yaml stehen noch Platzhalter ^(TODO^).
    echo          Das Programm laeuft trotzdem - zunaechst mit Beispieldaten.
    echo.
) else (
    echo [3/4] Konfiguration vorhanden.
)

REM --- 5. Starten ------------------------------------------------------------
echo [4/4] Starte die Weboberflaeche ...
echo.
echo   ------------------------------------------------
echo    Im Browser oeffnen:   http://localhost:8080
echo   ------------------------------------------------
echo.
echo   Zum Beenden dieses Fenster schliessen
echo   oder Strg+C druecken.
echo.

start "" http://localhost:8080
python -m stadionheft.cli web --port 8080

pause
