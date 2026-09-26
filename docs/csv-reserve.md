# CSV-Reserve

Diese Seite braucht ihr nur, wenn **FuPa ausfällt** – oder wenn eine
Mannschaft dort gar nicht geführt wird.

Im Normalfall holt das Programm alles selbst. Es ist nichts zu pflegen.

---

## Wann das greift

Das Programm schaltet **von selbst** auf die CSV-Dateien um, wenn

- fupa.net nicht erreichbar ist, oder
- der Abruf zwar durchläuft, aber nichts Verwertbares liefert.

Ihr merkt es an der Meldung *„Es wurde automatisch auf 'manuell'
umgeschaltet"*. Liegen dann keine CSV-Dateien bereit, bleiben die Seiten leer –
und das Programm sagt es.

Wer die Reserve vorbereiten will, legt die Dateien einmal an. Sie liegen dann
da und stören nicht.

---

## Vorlagen erzeugen lassen

```bash
docker exec stadionheft python -m stadionheft.cli beispieldaten
```

Das schreibt leere CSV-Dateien mit den richtigen Kopfzeilen nach
`_Programm/03_Eingaben/`. Mit `--mit-daten` kommen Beispielwerte mit, damit
man sieht, wie es aussehen soll.

---

## Die Dateien

Alle beginnen mit dem Mannschaftsschlüssel aus der `config.yaml`
(`herren1`, `damen1` …).

| Datei | Inhalt |
|---|---|
| `herren1_tabelle.csv` | Die Liga-Tabelle |
| `herren1_torjaeger.csv` | Die Torschützenliste |
| `herren1_spieler.csv` | Der eigene Kader |
| `herren1_spielplan.csv` | **Alle** Spiele der Saison |
| `herren1_gegner_<gegner>.csv` | Kader eines Gegners, z. B. `herren1_gegner_sg-alerheim.csv` |

### Bearbeiten

Die Dateien lassen sich direkt in Excel öffnen. Beim Speichern
**„CSV UTF-8 (durch Trennzeichen getrennt)"** wählen.

Semikolon und Komma werden beide erkannt, ebenso deutsche und englische
Spaltennamen (`tore`/`goals`, `sp`/`spiele`).

Fehlt eine Datei, bleibt nur die betreffende Seite leer – der Rest entsteht
trotzdem.

---

## Der Spielplan ist der wichtigste

```csv
heim;gast;wettbewerb;datum;uhrzeit;spielort;heimspiel;ergebnis
SV Wörnitzstein-Berg;TSV Meitingen;Bezirksliga;27.09.2026;15:00;Wörnitzstein;ja;2:1
SG Alerheim;SV Wörnitzstein-Berg;Bezirksliga;04.10.2026;15:00;Alerheim;nein;
```

Einmal im Sommer die ganze Saison eintragen – danach findet das Programm zu
jedem Termin von selbst die richtige Partie. **Maßgeblich ist das Datum**,
nicht die Reihenfolge in der Datei.

Aus diesem Spielplan rechnet das Programm auch die Formkurve und die
Saisonbilanz. Die Spalte `ergebnis` ist also mehr als Zierde: Sie füllt zwei
weitere Seiten.

!!! tip "Ergebnisse nachtragen"
    Nach jedem Spiel das Ergebnis in die Zeile schreiben. Das ist die einzige
    wiederkehrende Arbeit – und auch nur, solange FuPa ausfällt.

---

## Gegnerkader

Am besten **je Gegner eine Datei**:

```
herren1_gegner_sg-alerheim.csv
herren1_gegner_tsv-meitingen.csv
```

Der Dateiname entsteht aus dem Vereinsnamen: klein geschrieben, Leerzeichen
werden zu Bindestrichen, Umlaute ausgeschrieben (`Türk Gücü Lauingen` →
`tuerk-guecue-lauingen`).

Es geht auch mit einer einzigen Datei `herren1_gegner_spieler.csv`, die vor
jedem Heft ausgetauscht wird. Dann weist das Programm aber jedes Mal darauf
hin, dass sie zum falschen Gegner gehören könnte – denn genau das passiert
erfahrungsgemäß irgendwann.

---

## Dauerhaft auf CSV umstellen

Falls eine Mannschaft bei FuPa gar nicht geführt wird, lässt sich die Quelle
in der `config.yaml` festlegen:

```yaml
datenquelle:
  modus: "manuell"
```

Das gilt dann allerdings für **alle** Mannschaften. Für eine einzelne
Mannschaft gibt es diese Umschaltung nicht – in dem Fall lieber die
FuPa-Daten nehmen, was geht, und die fehlenden Seiten hinnehmen.
