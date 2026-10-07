#!/bin/sh
# ---------------------------------------------------------------------------
# Holt die aktuellen Hilfsskripte von GitHub auf die NAS.
#
# Warum es das gibt: Die Skripte in diesem Ordner werden weiterentwickelt --
# Fehler werden behoben, neue Pruefungen kommen dazu. Auf der NAS liegt aber
# eine Kopie von dem Tag, an dem sie einmal hochgeladen wurde. Laeuft dann
# ein alter Stand, sieht man Fehler, die laengst behoben sind, und die
# Berichte passen nicht zu dem, was besprochen wurde.
#
# Dieses Skript ist die Ausnahme: Es ist kurz, es aendert sich praktisch nie,
# und es holt alle anderen. Einmal als Aufgabe anlegen, danach genuegt ein
# Klick auf "Ausfuehren", bevor eine der anderen Aufgaben laeuft.
#
# Verwendung: Systemsteuerung -> Aufgabenplaner -> Erstellen ->
#             Geplante Aufgabe -> Benutzerdefiniertes Skript.
#             Docker wird nicht gebraucht, jeder Benutzer genuegt.
#
# Ergebnis: _Programm/99_Logs/skripte_holen.txt
# ---------------------------------------------------------------------------
set -u

WURZEL=${WURZEL:-/volume1/SVW/Stadionheft/_Programm}
ZWEIG=${ZWEIG:-main}
QUELLE="https://raw.githubusercontent.com/habersatterdan/stadionheft-svw/$ZWEIG/skripte"

ZIEL="$WURZEL/skripte"
BERICHT="$WURZEL/99_Logs/skripte_holen.txt"

# skripte_holen.sh holt sich selbst mit. Das geht, weil unten ueber 'mv'
# ersetzt wird: Die laufende Datei behaelt ihren alten Inhalt bis zum Ende,
# der neue steht erst beim naechsten Aufruf bereit.
DATEIEN="nas_aktualisieren.sh quellen_pruefen.sh skripte_holen.sh"

mkdir -p "$ZIEL" "$WURZEL/99_Logs"

{
  echo "=== Skripte geholt am $(date) ==="
  echo "Zweig: $ZWEIG"
  echo

  FEHLER=0
  for NAME in $DATEIEN; do
      TEMP="$ZIEL/.$NAME.neu"
      if curl -fsSL --max-time 40 "$QUELLE/$NAME" -o "$TEMP" 2>/dev/null; then
          # Eine Fehlerseite von GitHub waere auch eine Datei. Ein Skript
          # erkennt man daran, dass es mit einer Raute-Zeile beginnt.
          if head -1 "$TEMP" | grep -q '^#'; then
              mv "$TEMP" "$ZIEL/$NAME"
              chmod +x "$ZIEL/$NAME" 2>/dev/null
              echo "  OK       $NAME  ($(wc -c < "$ZIEL/$NAME") Bytes)"
          else
              rm -f "$TEMP"
              echo "  UNKLAR   $NAME - die Antwort sieht nicht nach einem"
              echo "           Skript aus. Alte Fassung bleibt liegen."
              FEHLER=1
          fi
      else
          rm -f "$TEMP"
          echo "  FEHLER   $NAME - nicht erreichbar."
          FEHLER=1
      fi
  done

  echo
  if [ "$FEHLER" -eq 0 ]; then
      echo "Alle Skripte sind auf dem aktuellen Stand."
  else
      echo "Mindestens eine Datei kam nicht an."
      echo
      echo "Moegliche Gruende:"
      echo "  - Der Zweig heisst inzwischen anders. Oben im Skript unter"
      echo "    ZWEIG=... anpassen."
      echo "  - Die NAS kommt nicht ins Internet."
  fi

  echo
  echo "Die Skripte liegen in: $ZIEL"
  echo
  echo "Naechster Schritt - eine der anderen Aufgaben ausfuehren:"
  echo "  sh $ZIEL/nas_aktualisieren.sh   (Container auf neuen Stand bringen)"
  echo "  sh $ZIEL/quellen_pruefen.sh     (Datenquellen abklopfen)"
  echo "=== Ende ==="
} > "$BERICHT" 2>&1
