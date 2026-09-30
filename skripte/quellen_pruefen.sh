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

WURZEL=${WURZEL:-/volume1/SVW/Stadionheft/_Programm}
BERICHT="$WURZEL/99_Logs/quellen_pruefen.txt"
ABLAGE="$WURZEL/99_Logs/quellen"
mkdir -p "$ABLAGE"

# Ein Browser-User-Agent. Viele Seiten antworten technischen Abrufern anders
# als Browsern -- und wir wollen sehen, was ein Browser sieht.
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"

# Hier stehen die Adressen, die geprueft werden sollen. Weitere Zeilen
# einfach anhaengen -- Name und Adresse durch einen senkrechten Strich
# getrennt.
#
# Die .ics-Adressen sind der eigentliche Grund fuer diesen Durchlauf:
# api.fupa.net/robots.txt erlaubt ausdruecklich "/*.ics$" und sperrt sonst
# alles. Kalenderdateien sind also der eine Weg, den FuPa freigibt -- wir
# wissen nur noch nicht, unter welcher Adresse sie liegen. Welche der
# Zeilen HTTP 200 und "BEGIN:VCALENDAR" liefert, ist die richtige.
# Zum Ausprobieren laesst sich die Liste von aussen setzen:
#   ADRESSEN="name|https://..." sh quellen_pruefen.sh
ADRESSEN=${ADRESSEN:-"
fupa-team|https://www.fupa.net/team/sv-woernitzstein-berg-m1-2026-27
fupa-robots|https://api.fupa.net/robots.txt
fupa-www-robots|https://www.fupa.net/robots.txt
ics-api-calendar|https://api.fupa.net/v1/teams/sv-woernitzstein-berg-m1-2026-27/calendar.ics
ics-api-matches|https://api.fupa.net/v1/teams/sv-woernitzstein-berg-m1-2026-27/matches.ics
ics-api-slug|https://api.fupa.net/v1/teams/sv-woernitzstein-berg-m1-2026-27.ics
ics-api-kalender|https://api.fupa.net/v1/teams/sv-woernitzstein-berg-m1-2026-27/kalender.ics
ics-www-kalender|https://www.fupa.net/team/sv-woernitzstein-berg-m1-2026-27/kalender.ics
ics-www-slug|https://www.fupa.net/team/sv-woernitzstein-berg-m1-2026-27.ics
bfv-wettbewerb|https://www.bfv.de/ergebnisse/wettbewerb/-/03151UJ1KC000005VS5489BUVSBBVPEU-G
bfv-robots|https://www.bfv.de/robots.txt
bfv-app-robots|https://app.bfv.de/robots.txt
"}

pruefe() {
    NAME=$1
    URL=$2
    DATEI="$ABLAGE/$NAME.html"

    echo "----------------------------------------------------------------"
    echo "$NAME"
    echo "$URL"

    : > "$DATEI"                      # anlegen, damit wc/grep nicht stolpern
    AUSKUNFT=$(curl -sL -A "$UA" -w '%{http_code}|%{content_type}' -o "$DATEI" \
                    --max-time 40 --compressed "$URL" 2>/dev/null)
    CODE=${AUSKUNFT%%|*}
    TYP=${AUSKUNFT#*|}
    [ -z "$CODE" ] && CODE=000
    GROESSE=$(wc -c < "$DATEI")
    echo "  HTTP $CODE, $GROESSE Bytes, Typ: ${TYP:-unbekannt}"
    echo "  gesichert in 99_Logs/quellen/$NAME.html"

    if [ "$CODE" = "000" ]; then
        echo "  Keine Verbindung - Adresse oder Netz pruefen."
        echo
        return
    fi

    # Ein Kalender ist der Treffer, auf den wir warten: FuPa erlaubt genau
    # diese Dateien. Also zuerst danach schauen.
    if grep -q "BEGIN:VCALENDAR" "$DATEI" 2>/dev/null; then
        TERMINE=$(grep -c "BEGIN:VEVENT" "$DATEI" 2>/dev/null) || TERMINE=0
        echo "  *** KALENDER gefunden, $TERMINE Termine ***"
        echo "  Die ersten Zeilen eines Termins:"
        sed -n '/BEGIN:VEVENT/,/END:VEVENT/p' "$DATEI" | sed -n '1,12p' \
            | sed 's/^/      /'
        echo
        return
    fi

    # Reiner Text (robots.txt, Fehlerseiten) wird gezeigt statt ausgewertet:
    # Der Inhalt selbst steht schneller da als jede Zusammenfassung. Die
    # Groesse entscheidet hier nicht -- www.fupa.net/robots.txt hat ueber
    # 4 KB und ist trotzdem genau das, was wir lesen wollen.
    case "$URL$TYP" in
        *robots.txt*|*text/plain*)
            echo "  Inhalt (bis 80 Zeilen):"
            sed -n '1,80p' "$DATEI" | sed 's/^/      /'
            echo
            return
            ;;
    esac

    if [ "$GROESSE" -lt 4000 ]; then
        echo "  Inhalt (bis 40 Zeilen):"
        sed -n '1,40p' "$DATEI" | sed 's/^/      /'
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
  echo "Worauf es ankommt:"
  echo "  - Steht bei einer ics-Zeile 'KALENDER gefunden', ist der Weg frei."
  echo "    Diese Adresse gehoert dann in die Konfiguration unter"
  echo "    datenquelle.fupa.zusatz_adressen."
  echo "  - Liefern alle ics-Zeilen 404, gibt es den Kalender unter diesen"
  echo "    Namen nicht. Dann hilft nur: auf fupa.net die Mannschaftsseite"
  echo "    im Browser oeffnen und nach 'Kalender abonnieren' suchen."
  echo "  - 'nennt Wörnitzstein (2 x)' auf einer grossen Seite heisst: die"
  echo "    Daten stehen nicht in der Seite, der Browser holt sie nach."
  echo
  echo "Die Seiten liegen in: $ABLAGE"
} > "$BERICHT" 2>&1
