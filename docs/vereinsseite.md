# Die eigene Vereinsseite als Datenquelle

Die naheliegendste Quelle war lange die übersehene: **www.sv-woernitzstein-berg.de**.
Dort stehen Tabelle, Spielplan und Ergebnisse ohnehin schon – gepflegt vom
Verein, für den Verein.

Das ist aus drei Gründen die beste Quelle, die es gibt:

| | FuPa / BFV | Eigene Seite |
|---|---|---|
| Erlaubnis | fremde `robots.txt` entscheidet | gehört uns |
| Verfügbarkeit | kann jederzeit umgestellt werden | wir stellen um |
| Inhalt | was das Portal zeigt | was wir eingetragen haben |

FuPa und BFV bleiben trotzdem eingebaut. Zwei Wege sind besser als einer –
und wenn beide liefern, gewinnt einfach die vollständigere Liste.

---

## Was das Programm von einer Webseite lesen kann

Drei Formen, in beliebiger Mischung auf derselben Seite:

**1. Ausgeschriebene HTML-Tabellen** – so liefert eine Vereinsseite ihre
Zahlen:

```html
<table>
  <tr><th>Pl.</th><th>Mannschaft</th><th>Sp.</th><th>Tore</th><th>Pkt.</th></tr>
  <tr><td>4.</td><td>SV Wörnitzstein-Berg</td><td>11</td><td>19:15</td><td>18</td></tr>
</table>
```

Die Kopfzeile stellt die Spaltennamen. Ob dort `Pkt.`, `Punkte` oder
`points` steht, ist egal – erkannt wird an der Struktur, nicht am Wort.

Zusammengefasste Spalten versteht das Programm ebenfalls, weil gedruckte
Tabellen sie fast immer verwenden:

* `19:15` in einer Spalte **Tore** → 19 Tore, 15 Gegentore
* `5-3-3` in einer Spalte **S-U-N** → 5 Siege, 3 Unentschieden, 3 Niederlagen
* `4.` in der Platzspalte → Platz 4
* `13.09.2026<br>15:00` in einer Datumsspalte → Datum und Anstoßzeit

**2. Eingebettetes JSON** – so liefern moderne Portale (FuPa, BFV).

**3. Eingebundene Widgets** (`<iframe>`) – steht auf der Seite selbst
nichts, weil Tabelle und Spielplan als Widget eines Portals eingebunden
sind, folgt das Programm der eingebundenen Adresse von selbst.

---

## Einrichten

In `config.yaml` bei der jeweiligen Mannschaft unter `zusatz_urls`:

```yaml
mannschaften:
  herren1:
    anzeigename: "Herren 1"
    liga: "Bezirksliga Schwaben Nord"
    fupa_team_url: "https://www.fupa.net/team/sv-woernitzstein-berg-m1-2026-27"
    zusatz_urls:
      - "https://www.sv-woernitzstein-berg.de/ergebnisse_1-mannschaft/"
```

`zusatz_urls` wird **vor allen anderen Adressen** probiert. In der
Beispielkonfiguration ist die Seite der 1. Mannschaft bereits eingetragen;
für die übrigen Mannschaften fehlt noch die passende Adresse.

!!! tip "Welche Adresse gehört dorthin?"
    Die Seite im Browser öffnen, auf der Tabelle und Spielplan stehen, und
    die Adresse aus der Adresszeile kopieren. Mehr ist es nicht.

---

## Prüfen, ob es trägt

```bash
docker exec stadionheft python -m stadionheft.cli probe-fupa --mannschaft herren1
```

Im Bericht steht dann je Adresse, was ankam. Die eigene Seite steht ganz oben.

Ohne Container – `skripte/quellen_pruefen.sh` prüft alle Mannschaftsseiten
auf einen Schlag. Entscheidend sind diese beiden Zeilen:

```
  *** 4 HTML-Tabellen mit 105 Zellen ***
  Die erste Kopfzeile:
      Pl.|Mannschaft|Sp.|S|U|N|Tore|Diff.|Pkt.|
```

Das heißt: Die Zahlen stehen in der Seite und sind lesbar.

```
  eingebundene Seiten (<iframe>):
      https://widget.fupa.net/standing/12345
```

Das heißt: Die Zahlen liegen eine Adresse weiter. Das Programm folgt dem
selbst – gut zu wissen ist es trotzdem.

---

## Eine Falle, die teuer war

Viele Webserver senden `Content-Type: text/html` **ohne** Angabe des
Zeichensatzes. Die HTTP-Norm schreibt dann ISO-8859-1 vor – aus
`SV Wörnitzstein-Berg` wird `SV WÃ¶rnitzstein-Berg`.

Das ist keine Schönheitsfrage: Am Vereinsnamen erkennt das Programm die
eigene Mannschaft im Spielplan. Stimmt er nicht, sind **Formkurve und
Saisonbilanz still falsch** – und das fällt erst im gedruckten Heft auf.

Das Programm liest den Zeichensatz deshalb aus der Seite selbst, wenn der
Server ihn verschweigt, und prüft nach, ob sich der Inhalt damit überhaupt
lesen lässt.
