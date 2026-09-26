# Übergabe ans Layout

Diese Seite ist für die Person gedacht, die das Stadionheft zusammenbaut.

---

## Was du bekommst

Ein ZIP mit einer PDF-Datei je Mannschaft, zum Beispiel:

```
2026-10-04_Spieltag_alle-Mannschaften.zip
├── 2026-10-04_Herren_1_gegen_SG_Alerheim.pdf
├── 2026-10-04_Herren_2_gegen_TSV_Binswangen.pdf
├── 2026-10-04_Damen_1_gegen_SV_Holzheim.pdf
└── UEBERSICHT.txt
```

Die `UEBERSICHT.txt` nennt Erstellungszeitpunkt, Seitenreihenfolge und je Datei
die Mannschaft, den Gegner, das Spieldatum und die Seitenzahl. Wenn bei einer
Mannschaft etwas fehlt, steht dort ein `ACHTUNG:`-Hinweis – **die Stelle bitte
im Heft anschauen**, sie ist dann leer.

---

## Das Format

| | |
|---|---|
| Endformat | 148 × 210 mm (A5) |
| Anschnitt | 3 mm umlaufend |
| Beschnittene Größe | 154 × 216 mm |
| Schnittmarken | vorhanden |
| Farbe | RGB, Vereinsrot `#E52421` |
| Schriften | eingebettet |

Die TrimBox ist gesetzt. Die Seiten passen damit **maßgenau zwischen die
bestehenden Werbeseiten** – so, wie die bisherigen InDesign-Seiten es taten.

!!! note "RGB, nicht CMYK"
    Die Dateien sind in RGB. Die meisten Druckereien wandeln das selbst um.
    Wenn deine Druckerei CMYK verlangt, sag Bescheid – das lässt sich
    einbauen.

---

## Was in jeder Datei steckt

Immer dieselben sieben Seiten, in dieser Reihenfolge:

1. **Trennseite** – Mannschaftsname und Liga, ganzseitig
2. **Das nächste Spiel** – Paarung, Anstoß, Ort und die Gegenüberstellung
   beider Mannschaften (Platz, Punkte, Tore, Form)
3. **Tabelle** – die Liga-Tabelle, eigene Mannschaft rot, Gegner grau
4. **Torschützenliste** – die Liga-Torschützen
5. **Spielerstatistik** – der eigene Kader
6. **Der Gegner** – Kader des Gegners mit kurzer Einordnung
7. **Saisonbilanz** – Kennzahlen beider Mannschaften nebeneinander

Bei einem Pokalgegner aus einer anderen Liga kommen zwei Seiten dazu (Tabelle
und Torschützen der fremden Liga). Die `UEBERSICHT.txt` sagt es dir.

---

## Wie du sie einbaust

Du kannst die Seiten **einzeln platzieren oder komplett übernehmen** – sie sind
bewusst als geschlossener Block je Mannschaft geschnitten.

**InDesign:** Datei → Platzieren, die PDF wählen, „Alle Seiten" ankreuzen,
Beschneiden auf **Medien** (nicht Beschnittrahmen – der Anschnitt ist schon
drin). Beim Platzieren die Seiten auf die Musterseiten legen.

**Acrobat oder ein PDF-Werkzeug:** Die Dateien einfach an der richtigen Stelle
zwischen Werbung und Kontaktlisten einfügen. Die Seitengrößen stimmen überein,
es gibt nichts zu skalieren.

---

## Was nicht aus dem Programm kommt

Diese Teile bleiben bei dir, sie ändern sich ja kaum:

- Titelseite mit Titelbild
- Vorwort
- Werbeanzeigen
- Kontaktlisten
- Impressum
- Rücktitel

---

## Wie aktuell sind die Zahlen?

Auf **jeder Seite unten** steht der Abrufzeitpunkt:

```
Stand: 04.10.2026, 09:12 Uhr · Quelle: fupa.net
```

Steht dort stattdessen ein roter Kasten **„Achtung – möglicherweise
veraltet"**, war FuPa beim Erzeugen nicht erreichbar und es wurden ältere
Daten verwendet. Dann bitte nachfragen, bevor das Heft in den Druck geht.

---

## Wenn etwas nicht stimmt

Sag einfach Bescheid, welche Seite und was daran falsch ist. Die Dateien lassen
sich in einer Minute neu erzeugen – es lohnt sich nicht, etwas von Hand zu
korrigieren, das beim nächsten Mal wieder falsch wäre.
