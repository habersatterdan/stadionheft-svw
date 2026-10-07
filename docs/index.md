# Stadionheft „Wörnitzstein am Ball"

Diese Anleitung erklärt, wie die aktuellen Statistikseiten für das Stadionheft
des SV Wörnitzstein-Berg entstehen. Sie richtet sich an alle im Verein –
Vorkenntnisse sind nicht nötig.

## Was das Programm macht — und was nicht

Das Programm nimmt genau die Arbeit ab, die bisher am meisten Zeit gekostet
hat: **Tabelle, Torschützenliste, Spielerstatistik und die Zahlen des nächsten
Gegners** werden nicht mehr als Bildschirmfotos zusammengesucht, sondern
automatisch von fupa.net geholt und sauber gesetzt.

Es entsteht **pro Mannschaft eine druckfertige PDF-Datei**. Diese Dateien gehen
an die Person, die das Heft zusammenbaut – zusammen mit Titelseite, Vorwort,
Werbung, Kontaktlisten und Impressum, die weiterhin von Hand kommen.

!!! tip "In einem Satz"
    Mannschaften anhaken → Knopf drücken → fertige PDFs herunterladen →
    weitergeben.

---

## Ich möchte …

<div class="grid cards" markdown>

-   **die aktuellen Seiten erzeugen**

    Mannschaften anhaken, Knopf drücken, Dateien herunterladen.

    [→ Seiten erzeugen](erzeugen.md)

-   **das Heft zusammenbauen**

    Was in den Dateien steckt und wie sie ins Heft kommen.

    [→ Übergabe ans Layout](uebergabe.md)

-   **nachsehen, wenn etwas fehlt**

    Leere Seiten, falscher Gegner, FuPa nicht erreichbar.

    [→ Wenn etwas nicht klappt](fehler.md)

-   **das Programm einrichten**

    Einmalig auf der NAS oder im Homelab aufsetzen.

    [→ Erste Einrichtung](ERSTE_EINRICHTUNG.md)

</div>

---

## Was in einer Mannschaftsdatei steht

Jede Datei hat sechs Seiten, immer in derselben Reihenfolge:

| # | Seite | Inhalt |
|---|---|---|
| 1 | Trennseite | Mannschaftsname und Liga |
| 2 | Das nächste Spiel | Gegenüberstellung beider Mannschaften: Platz, Punkte, Tore, Form |
| 3 | Tabelle | Liga-Tabelle, eigene Mannschaft und Gegner hervorgehoben |
| 4 | Torschützenliste | Die besten 22 Liga-Torschützen, beide Vereine hervorgehoben |
| 5 | Spielerstatistik | Der eigene Kader, nach Einsätzen und Minuten sortiert (höchstens 22) |
| 6 | Der Gegner | Kader des nächsten Gegners, ebenso sortiert |

Spielt der Gegner ausnahmsweise in einer anderen Liga (Pokal), kommen dessen
Tabelle und Torschützenliste als zusätzliche Seiten dazu.

Format: **A5, 3 mm Anschnitt, Schnittmarken** – exakt wie die bisherigen
Heftseiten.

---

## Woher die Zahlen kommen

Von **fupa.net**, live beim Klick auf den Knopf. Auf jeder Seite steht unten,
wann die Daten geholt wurden – so lässt sich später nachvollziehen, welchem
Spieltag ein Blatt entspricht.

Der **nächste Gegner wird automatisch ermittelt**: Das Programm schaut in den
Spielplan und nimmt die Partie, die als nächste ansteht. Nichts muss von Hand
umgestellt werden.

Die Zahlen kommen aus drei Quellen, in dieser Reihenfolge:

1. **Die eigene Vereinsseite** – braucht keine Erlaubnis von Dritten und
   kann niemand sperren. Dort stehen Tabelle, Spielplan und Ergebnisse
   ohnehin schon.
2. **FuPa** – Spielplan über die Kalenderdatei, die FuPa ausdrücklich
   freigibt.
3. **CSV-Dateien** – wenn beides nicht trägt, und das Programm sagt es
   deutlich.

[→ Eigene Vereinsseite als Quelle](vereinsseite.md) ·
[→ Details zur FuPa-Anbindung](fupa.md)
