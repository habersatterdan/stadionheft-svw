#!/bin/sh
# ---------------------------------------------------------------------------
# Aktualisiert den Stadionheft-Container auf der Synology NAS und schreibt
# einen Bericht, aus dem hervorgeht, was wirklich passiert ist.
#
# Verwendung: Systemsteuerung -> Aufgabenplaner -> Erstellen ->
#             Geplante Aufgabe -> Benutzerdefiniertes Skript, Benutzer root.
#             Inhalt dieser Datei hineinkopieren, Zeitplan deaktivieren.
#
# Warum ein eigenes Skript und nicht nur "Projekt neu erstellen"?
# Docker holt ein Abbild mit dem Namen "latest" NICHT von selbst neu. Liegt
# lokal schon eines unter dem Namen, wird das weiterverwendet -- der Container
# laeuft dann mit altem Code, ohne dass irgendwo ein Fehler erscheint.
# ---------------------------------------------------------------------------
set -u

WURZEL=/volume1/SVW/Stadionheft/_Programm
BERICHT="$WURZEL/99_Logs/aktualisierung.txt"
DOCKER=$(command -v docker || echo /usr/local/bin/docker)

{
  echo "=== Aktualisierung vom $(date) ==="
  echo

  echo "########## 1. Welche Compose-Datei wird verwendet? ##########"
  COMPOSE=$(find "$WURZEL/docker" -maxdepth 3 -name 'docker-compose.y*ml' 2>/dev/null | head -1)
  if [ -z "$COMPOSE" ]; then
      echo "KEINE docker-compose.yml unter $WURZEL/docker gefunden."
      exit 1
  fi
  echo "$COMPOSE"
  echo
  sed -n '1,80p' "$COMPOSE" | grep -v '^\s*#' | grep -v '^\s*$'
  echo

  if grep -q '^\s*build:' "$COMPOSE"; then
      echo "ACHTUNG: Diese Datei baut selbst (build:)."
      echo "Ein Pull hilft dann nicht - dafuer braucht es neuen Quellcode."
      echo "Zum Umsteigen die build-Zeile ersetzen durch:"
      echo "  image: ghcr.io/habersatterdan/stadionheft-svw:latest"
  fi
  echo

  echo "########## 2. Stand VOR der Aktualisierung ##########"
  $DOCKER exec stadionheft python -m stadionheft.cli stand 2>&1
  echo

  echo "########## 3. Neues Abbild holen ##########"
  ORDNER=$(dirname "$COMPOSE")
  cd "$ORDNER" || exit 1
  if $DOCKER compose version >/dev/null 2>&1; then
      $DOCKER compose pull 2>&1
      $DOCKER compose up -d 2>&1
  else
      docker-compose pull 2>&1
      docker-compose up -d 2>&1
  fi
  echo

  echo "########## 4. Stand NACH der Aktualisierung ##########"
  sleep 5
  $DOCKER exec stadionheft python -m stadionheft.cli stand 2>&1
  echo

  echo "########## 5. FuPa-Verbindung pruefen ##########"
  $DOCKER exec stadionheft python -m stadionheft.cli probe-fupa 2>&1
  echo
  echo "=== Ende ==="
} > "$BERICHT" 2>&1
