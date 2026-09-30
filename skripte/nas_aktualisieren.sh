#!/bin/sh
# ---------------------------------------------------------------------------
# Aktualisiert den Stadionheft-Container auf der Synology NAS und schreibt
# einen Bericht, aus dem hervorgeht, was wirklich passiert ist.
#
# Verwendung: Systemsteuerung -> Aufgabenplaner -> Erstellen ->
#             Geplante Aufgabe -> Benutzerdefiniertes Skript,
#             Benutzer: root, Zeitplan deaktiviert.
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
BEHAELTER=stadionheft

{
  echo "=== Aktualisierung vom $(date) ==="
  echo

  # -- 0. Laeuft das ueberhaupt mit den noetigen Rechten? -------------------
  if ! $DOCKER info >/dev/null 2>&1; then
      echo "PROBLEM: Kein Zugriff auf Docker."
      echo
      echo "ZU TUN: Im Aufgabenplaner diese Aufgabe bearbeiten und unter"
      echo "        'Allgemein' als Benutzer 'root' eintragen."
      echo
      $DOCKER info 2>&1 | head -3
      echo "=== Abbruch ==="
      exit 1
  fi

  # -- 1. Welche Compose-Datei ist im Spiel? --------------------------------
  echo "########## 1. Compose-Datei ##########"
  COMPOSE=$(find "$WURZEL/docker" -maxdepth 3 -name 'docker-compose.y*ml' 2>/dev/null | head -1)
  if [ -z "$COMPOSE" ]; then
      echo "KEINE docker-compose.yml unter $WURZEL/docker gefunden."
      echo "=== Abbruch ==="
      exit 1
  fi
  echo "$COMPOSE"
  echo
  grep -v '^[[:space:]]*#' "$COMPOSE" | grep -v '^[[:space:]]*$'
  echo

  HAT_BUILD=$(grep -c '^[[:space:]]*build:' "$COMPOSE")
  HAT_IMAGE=$(grep -c '^[[:space:]]*image:' "$COMPOSE")
  if [ "$HAT_BUILD" -gt 0 ] && [ "$HAT_IMAGE" -gt 0 ]; then
      echo "PROBLEM: 'build:' UND 'image:' sind beide aktiv."
      echo "Docker baut dann aus dem oertlichen Quellcode und haengt dem"
      echo "Ergebnis den Namen des GitHub-Abbilds an. Es wird nie etwas"
      echo "geholt."
      echo "ZU TUN: Die Zeile mit 'build:' loeschen."
      echo "=== Abbruch ==="
      exit 1
  fi
  if [ "$HAT_BUILD" -gt 0 ]; then
      echo "Diese Datei baut selbst. Ein Pull hilft nicht - es braucht"
      echo "neuen Quellcode als ZIP."
      echo "=== Abbruch ==="
      exit 1
  fi

  ABBILD=$(grep '^[[:space:]]*image:' "$COMPOSE" | head -1 | sed 's/.*image:[[:space:]]*//')
  echo "Abbild: $ABBILD"
  echo

  # -- 2. Womit laeuft der Container gerade? --------------------------------
  # Der Befehl 'stand' kam erst spaeter dazu. Fehlt er, ist das schon die
  # Antwort: Dann laeuft eine aeltere Fassung.
  stand() {
      if ! $DOCKER exec "$BEHAELTER" python -m stadionheft.cli stand 2>/dev/null; then
          echo "(aeltere Fassung - kennt den Befehl 'stand' noch nicht)"
      fi
  }

  echo "########## 2. Stand VORHER ##########"
  stand
  echo

  # -- 3. Abbild holen. Schlaegt das fehl, bleibt alles wie es ist. ---------
  echo "########## 3. Abbild holen ##########"
  if ! $DOCKER pull "$ABBILD" 2>&1; then
      echo
      echo "PROBLEM: Das Abbild konnte nicht geholt werden."
      echo
      echo "Steht oben 'unauthorized' oder 'denied', ist das Paket auf"
      echo "GitHub noch privat. ZU TUN, einmalig im Browser:"
      echo "  github.com -> Profilbild -> Your packages -> stadionheft-svw"
      echo "  -> Package settings -> Change visibility -> Public"
      echo
      echo "Der laufende Container wurde NICHT angeruehrt."
      echo "=== Abbruch ==="
      exit 1
  fi
  echo

  # -- 4. Container neu starten ---------------------------------------------
  # Der Projektname muss der sein, unter dem der Container Manager das
  # Projekt angelegt hat. Sonst haelt Compose den laufenden Container fuer
  # einen fremden und scheitert mit "name is already in use".
  echo "########## 4. Container neu starten ##########"
  PROJEKT=$($DOCKER inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' \
            "$BEHAELTER" 2>/dev/null)
  [ -z "$PROJEKT" ] && PROJEKT="$BEHAELTER"
  echo "Compose-Projekt: $PROJEKT"

  cd "$(dirname "$COMPOSE")" || exit 1

  hochfahren() {
      if $DOCKER compose version >/dev/null 2>&1; then
          $DOCKER compose -p "$PROJEKT" up -d --force-recreate 2>&1
      else
          docker-compose -p "$PROJEKT" up -d --force-recreate 2>&1
      fi
  }

  AUSGABE=$(hochfahren)
  echo "$AUSGABE"

  # "name is already in use": Compose haelt den laufenden Container fuer
  # einen fremden. Dann wird er weggeraeumt und neu angelegt. Das ist
  # gefahrlos -- der Container haelt keine Daten. Konfiguration, Eingaben
  # und fertige PDFs liegen alle in eingehaengten Ordnern ausserhalb.
  case "$AUSGABE" in
      *"already in use"*)
          echo
          echo "Der alte Container steht im Weg. Er wird entfernt und neu"
          echo "angelegt (die Daten liegen ausserhalb und bleiben)."
          $DOCKER rm -f "$BEHAELTER" 2>&1
          hochfahren
          ;;
  esac
  echo

  # -- 5. Kontrolle ----------------------------------------------------------
  echo "########## 5. Stand NACHHER ##########"
  sleep 8
  stand
  echo
  echo "Stehen VORHER und NACHHER gleich da, hat sich nichts geaendert."
  echo

  echo "########## 6. FuPa-Verbindung ##########"
  $DOCKER exec "$BEHAELTER" python -m stadionheft.cli probe-fupa 2>&1
  echo
  echo "=== Ende ==="
} > "$BERICHT" 2>&1
