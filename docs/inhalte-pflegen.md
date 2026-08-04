# Inhalte pflegen

Alles, was die Redaktion vor einem Spieltag vorbereitet. Die Dateien liegen
auf der NAS unter **`Stadionheft/03_Eingaben`**.

Du kommst dort hin über die **Dateistation** im Browser, über **Synology
Drive**, über ein Netzlaufwerk – oder am Handy mit der App **DS file**.

---

## Titelbild

Ein Foto namens `titelbild.jpg` (auch `.jpeg` oder `.png`) in `03_Eingaben`
ablegen. Es landet automatisch im Bildband der Titelseite.

!!! tip "Welches Format?"
    Querformat passt am besten – das Bild wird auf etwa 148 × 96 mm
    zugeschnitten. Für guten Druck sollte es mindestens **1800 Pixel breit**
    sein. Handyfotos erfüllen das locker.

---

## Vorwort

Datei `vorwort.md` in `03_Eingaben`. Ein ganz normaler Text:

```text
Liebe Gäste, liebe Fans des SV Wörnitzstein-Berg,

ich darf Euch recht herzlich zum Heimspiel gegen die SG Alerheim
begrüßen. Ein besonderer Gruß gilt allen Zuschauern sowie dem
eingeteilten Schiedsrichtergespann.

Nach dem gelungenen Saisonstart wollen wir heute nachlegen.

Man sieht sich – bis bald,
David
```

* Die **erste kurze Zeile** wird als rote Überschrift gesetzt
* **Leerzeile** zwischen den Absätzen
* Der Text läuft automatisch zweispaltig und bei Bedarf auf die nächste Seite

---

## Spielplan – die wichtigste Datei

In `<mannschaft>_spielplan.csv` stehen **alle Spiele der Saison**. Einmal im
Sommer ausfüllen, danach findet das Programm bei jedem Heft selbst heraus,
gegen wen als nächstes gespielt wird.

```csv
heim;gast;wettbewerb;datum;uhrzeit;spielort;heimspiel;spieltag;ergebnis
TG Lauingen;SV Wörnitzstein-Berg;Bezirksliga;26.07.2026;15:00;;nein;1;0:4
SV Wörnitzstein-Berg;TSV Meitingen;Bezirksliga;29.07.2026;18:30;Wörnitzstein;ja;2;
SV Wörnitzstein-Berg;SG Alerheim;Bezirksliga;09.08.2026;15:00;Wörnitzstein;ja;3;
```

| Spalte | Inhalt |
|---|---|
| `heim` / `gast` | Vereinsnamen |
| `wettbewerb` | Liga oder Pokal – leer lassen übernimmt die Liga aus der Konfiguration |
| `datum` | `TT.MM.JJJJ` |
| `uhrzeit` | `HH:MM` |
| `spielort` | frei, z. B. „Sportgelände Wörnitzstein" |
| `heimspiel` | `ja` oder `nein` |
| `spieltag` | frei, z. B. „3" oder „3. Spieltag" |
| `ergebnis` | leer lassen, bis gespielt wurde – z. B. `4:0` |

!!! info "Maßgeblich ist das Datum"
    Welche Partie aufs Titelblatt kommt, entscheidet **allein das Datum** –
    nicht die Reihenfolge in der Datei und auch nicht, ob ein Ergebnis
    eingetragen ist. Ein vergessener Ergebniseintrag bringt also keine alte
    Partie nach vorn.

    Ein Spiel bleibt bis drei Stunden nach Anstoß das „nächste" – wer das Heft
    am Spieltag nachdruckt, bekommt weiter die richtige Partie.

---

## Zahlen: Tabelle, Torschützen, Spielerstatistik

Nur nötig, solange die [FuPa-Anbindung](fupa.md) nicht eingerichtet ist.
Danach kommen diese Zahlen automatisch.

| Datei | Spalten |
|---|---|
| `<mannschaft>_tabelle.csv` | `platz;mannschaft;spiele;siege;unentschieden;niederlagen;tore;gegentore;punkte;zusatz` |
| `<mannschaft>_torjaeger.csv` | `platz;spieler;mannschaft;tore;vorlagen;spiele` |
| `<mannschaft>_spieler.csv` | `platz;spieler;spiele;tore;vorlagen;elfmeter;gelb;gelb_rot;rot;ein;aus;minuten` |

`zusatz` ist für „(Auf)" oder „(Ab)" hinter dem Vereinsnamen. Bei `elfmeter`
schreibt man `1/1` für „einen von einem verwandelt".

### Schneller als abtippen

1. Tabelle auf fupa.net im Browser markieren und kopieren
2. In Excel, LibreOffice Calc oder Numbers einfügen
3. Spalten in die richtige Reihenfolge bringen
4. Speichern unter → **CSV UTF-8**

!!! warning "Beim Speichern UTF-8 wählen"
    Sonst werden aus Umlauten kryptische Zeichen. Das Programm erkennt
    Semikolon und Komma als Trennzeichen selbst – darum musst du dich nicht
    kümmern.

---

## Gegnerkader

Für die Seite „Vorstellung Gegner". Zwei Wege:

**Empfohlen – eine Datei je Gegner:**

```
herren1_gegner_sg-alerheim.csv
herren1_gegner_tsv-meitingen.csv
```

Das Programm greift automatisch die passende zum ermittelten Gegner. Einmal
für alle Ligagegner angelegt, stimmt es die ganze Saison.

Der Dateiname entsteht aus dem Vereinsnamen: klein geschrieben, Leerzeichen
werden zu Bindestrichen, Umlaute ausgeschrieben (`Türk Gücü` → `tuerk-guecue`).

**Einfacher, aber fehleranfällig:** eine einzige `herren1_gegner_spieler.csv`,
die vor jedem Heft ausgetauscht wird. Das Programm weist dann jedes Mal darauf
hin, dass die Liste zum Gegner passen muss.

---

## Spielbericht

Datei `<mannschaft>_spielbericht.md`, aufgebaut wie das Vorwort. Erscheint nur,
wenn die Seite `spielbericht` für diese Mannschaft konfiguriert ist.

---

## Was passiert, wenn eine Datei fehlt?

**Das Heft wird trotzdem erzeugt.** Nur die betreffende Seite bleibt leer, und
unter dem Ergebnis steht ein Hinweis mit dem erwarteten Dateinamen.

Es geht also nie etwas kaputt, wenn mal etwas vergessen wird.
