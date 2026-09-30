#!/bin/sh
# ---------------------------------------------------------------------------
# Holt Webseiten roh auf die NAS und sagt, was drinsteckt.
#
# Zweck: herausfinden, wie eine Quelle ihre Daten wirklich ausliefert --
# ohne Container, ohne Aktualisierung, ohne Programm. Nur curl.
#
# Verwendung: Systemsteuerung -> Aufgabenplaner -> Erstellen ->
#             Geplante Aufgabe -> Benutzerdefiniertes Skript,
#             Benutzer: root (oder jeder andere, Docker wird nicht gebraucht).
#
# Ergebnis: _Programm/99_Logs/quellen_pruefen.txt  (Bericht)
#           _Programm/99_Logs/quellen/*.html       (die Seiten selbst)
# ---------------------------------------------------------------------------
set -u

WURZEL=/volume1/SVW/Stadionheft/_Programm
BERICHT="$WURZEL/99_Logs/quellen_pruefen.txt"
ABLAGE="$WURZEL/99_Logs/quellen"
mkdir -p "$ABLAGE"

# Ein Browser-User-Agent. Viele Seiten antworten technischen Abrufern anders
# als Browsern -- und wir wollen sehen, was ein Browser sieht.
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"

# Hier stehen die Adressen, die geprueft werden sollen. Weitere Zeilen
# einfach anhaengen -- Name und Adresse durch ein Leerzeichen getrennt.
ADRESSEN="
fupa-team|https://www.fupa.net/team/sv-woernitzstein-berg-m1-2026-27
fupa-robots|https://api.fupa.net/robots.txt
fupa-www-robots|https://www.fupa.net/robots.txt
bfv-wettbewerb|https://www.bfv.de/ergebnisse/wettbewerb/-/03151UJ1KC000005VS5489BUVSBBVPEU-G
"

pruefe() {
    NAME=$1
    URL=$2
    DATEI="$ABLAGE/$NAME.html"

    echo "----------------------------------------------------------------"
    echo "$NAME"
    echo "$URL"

    : > "$DATEI"                      # anlegen, damit wc/grep nicht stolpern
    CODE=$(curl -sL -A "$UA" -w '%{http_code}' -o "$DATEI" \
                --max-time 40 --compressed "$URL" 2>/dev/null)
    [ -z "$CODE" ] && CODE=000
    GROESSE=$(wc -c < "$DATEI")
    echo "  HTTP $CODE, $GROESSE Bytes -> 99_Logs/quellen/$NAME.html"

    if [ "$CODE" = "000" ]; then
        echo "  Keine Verbindung - Adresse oder Netz pruefen."
        echo
        return
    fi
    if [ "$GROESSE" -lt 200 ]; then
        echo "  Antwort zu kurz, um etwas daraus zu lesen:"
        sed -n '1,5p' "$DATEI" | sed 's/^/      /'
        echo
        return
    fi

    # Welche bekannten Verpackungen fuer eingebettete Daten kommen vor?
    for MARKE in __NEXT_DATA__ __next_f __NUXT__ application/ld+json \
                 application/json window.__ __INITIAL_STATE__ apollo; do
        N=$(grep -c -- "$MARKE" "$DATEI" 2>/dev/null) || N=0
        [ "$N" -gt 0 ] && echo "  enthaelt $MARKE ($N x)"
    done

    # Stehen Begriffe aus dem Spielbetrieb ueberhaupt im Text? Wenn ja,
    # sind die Daten in der Seite. Wenn nein, holt sie der Browser nach.
    for WORT in Wörnitzstein Tabelle Punkte Torschützen Spielplan Bezirksliga; do
        N=$(grep -c -- "$WORT" "$DATEI" 2>/dev/null) || N=0
        [ "$N" -gt 0 ] && echo "  nennt '$WORT' ($N x)"
    done
    echo
}

{
  echo "=== Quellen geprüft am $(date) ==="
  echo
  echo "$ADRESSEN" | while IFS='|' read -r NAME URL; do
      [ -z "${NAME:-}" ] && continue
      pruefe "$NAME" "$URL"
  done
  echo "=== Ende ==="
  echo
  echo "Die Seiten liegen in: $ABLAGE"
} > "$BERICHT" 2>&1
