# Analyse der bestehenden Vorlage

Grundlage: `20260728_WaB_Druck.pdf` – Ausgabe zum Heimspiel gegen TSV Meitingen
am 29.07.2026.

Diese Analyse ist die Basis aller Layout-Entscheidungen im Programm. Wer das
Layout ändert, sollte hier zuerst nachsehen.

---

## 1. Technische Eckdaten

| Merkmal | Wert |
|---|---|
| Erzeugt mit | Adobe InDesign 21.3 (Windows), PDF über Ghostscript |
| Seitenzahl | 28 |
| Endformat (TrimBox) | 419,53 × 595,28 pt = **148 × 210 mm (A5 hoch)** |
| Anschnitt (BleedBox) | 3 mm umlaufend |
| MediaBox | 461,53 × 637,28 pt (Endformat + 7,4 mm für Schnittmarken) |
| Hausfarbe | **#E52421** (aus Kopfbalken, Fußbalken und Trennseite gemessen) |
| Schriften | Segoe UI (Light / Semibold / Bold / SemiboldItalic), Minion Pro (Fußzeile) |

**Konsequenz für das Programm:** Die erzeugten Seiten verwenden exakt dasselbe
Endformat und denselben Anschnitt. Der Test
`tests/test_build.py::test_endformat_entspricht_der_vorlage` prüft das bei
jedem Lauf nach.

---

## 2. Seitenaufbau der Ausgabe

| Seite | Inhalt | Ändert sich je Ausgabe? | Herkunft |
|---|---|---|---|
| 1 | Titelseite: Saison, Datum, Paarung, Liga, Anstoß, Foto | **ja** | Redaktion + Spieldaten |
| 2–3 | Vorwort (zweispaltiger Fließtext) | **ja** | Redaktion (Text) |
| 4–9 | Werbeanzeigen (ganzseitige Grafiken) | nein | fertige Dateien |
| 10–11 | Werbeanzeigen | nein | fertige Dateien |
| 12 | Trennseite „Herren / 1. Mannschaft / Bezirksliga Schwaben Nord" | teilweise | Konfiguration |
| 13–14 | Spielbericht (zweispaltiger Fließtext) | **ja** | Redaktion / Presse |
| 15 | „Vorstellung Gegner" – Kader + Statistik des Gegners | **ja** | **FuPa** |
| 16 | „Tabellen" | **ja** | **FuPa** |
| 17 | „Torschützenlisten" | **ja** | **FuPa** |
| 18 | „Spielerstatistik" | **ja** | **FuPa** |
| 19–23 | Werbeanzeigen | nein | fertige Dateien |
| 24–25 | Kontaktlisten (Vorstand, Trainer, Jugend) | selten | Konfiguration |
| 26 | Werbeanzeige | nein | fertige Datei |
| 27 | Impressum | nein | Konfiguration |
| 28 | Rücktitel (Werbung) | nein | fertige Datei |

**Kernbefund:** Von 28 Seiten sind **rund 7 Seiten wirklich variabel**, davon
**4 rein datengetrieben** (Seiten 15–18). Genau dort liegt der Automatisierungs­gewinn.

---

## 3. Der entscheidende Befund: Seiten 15–18 sind Screenshots

Die Seiten „Vorstellung Gegner", „Tabellen", „Torschützenlisten" und
„Spielerstatistik" enthalten **keinen Text**, sondern jeweils ein eingebettetes
Bitmap-Bild:

| Seite | Bildgröße (Pixel) | Platzierung (pt) |
|---|---|---|
| 15 Vorstellung Gegner | 689 × 771 | x 73, y 149, 345 × 386 |
| 16 Tabellen | 698 × 536 | x 58, y 146, 349 × 268 |
| 17 Torschützenlisten | 721 × 219 und 721 × 547 | zwei Bilder untereinander |
| 18 Spielerstatistik | 698 × 776 | x 60, y 154, 349 × 388 |

Das sind **Bildschirmfotos von fupa.net**, von Hand in InDesign platziert – gut
erkennbar an den FuPa-Bedienelementen („Gesamt / Heim / Auswärts / Hin / Rück /
Form") und den runden Spielerfotos.

Daraus folgen drei Dinge:

1. **Der bisherige Aufwand liegt genau hier**: FuPa öffnen, richtigen Reiter
   wählen, Fenster passend ziehen, Screenshot, zuschneiden, in InDesign
   platzieren, ausrichten – mal vier Seiten, mal Anzahl Mannschaften.
2. **Die Qualität ist unnötig schlecht**: Bei ~700 px Breite auf ~120 mm
   Druckbreite entspricht das etwa 148 dpi statt der für Text üblichen 300+ dpi.
   Echte Tabellen sind im Druck sichtbar schärfer.
3. **Die Ersetzung ist gefahrlos**: Diese Seiten haben keine Verbindung zum
   restlichen Layout. Sie lassen sich als eigenständige PDF-Seiten erzeugen und
   zwischen die unveränderten Werbeseiten montieren – genau das macht dieses
   Programm.

---

## 4. Übernommene Layout-Maße

Alle Werte relativ zur oberen linken Ecke des Endformats, gemessen an den
Seiten 15–18. Sie stehen als CSS-Variablen in
`stadionheft/static/css/heft.css`:

| Element | Wert |
|---|---|
| Roter Kopfbalken | oben 12 mm, Höhe 15,5 mm, volle Breite |
| Überschrift im Balken | Segoe UI Light 24 pt, weiß, Einzug 34 mm |
| Vereinswappen | oben 5,5 mm, links 9 mm, Breite 19 mm (überlappt den Balken) |
| Inhaltsbereich | oben 44 mm, unten 20 mm, Rand 12 mm |
| Roter Fußbalken | unten 1,5 mm, Höhe 13 mm, Text „Wörnitzstein am Ball" zentriert |
| Tabellenschrift | ca. 7 pt, Kopfzeile ca. 6 pt grau |

**Trennseite (Seite 12):** vollflächig #E52421, „Herren" 70 pt bold zentriert,
„1. Mannschaft" 48 pt semibold kursiv, Liga unten 24 pt.

**Titelseite (Seite 1):** roter Grund, Wappen oben links (30 mm), Titel
rechtsbündig zweizeilig („Wörnitzstein" bold / „am Ball" kursiv), Foto im
Mittelband, zwei weiße Schrägen als Gestaltungselement, weißer Textkasten unten
rechts mit „Wir begrüßen unsere Gäste:", Wochentag, Paarung, Liga · Datum · Uhrzeit.

---

## 5. Datenfelder, die aus FuPa kommen müssen

Direkt aus den Screenshots abgelesen – das sind exakt die Felder der
Datenmodelle in `stadionheft/models.py`:

**Tabelle** (Seite 16)
`Pl. | Team | Sp. | S-U-N | Tore | Diff. | Pkt.`
zzgl. Zusatz „(Auf)" / „(Ab)" hinter dem Vereinsnamen.

**Torschützenliste** (Seite 17)
`Pl. | Spieler (+ Verein als Unterzeile) | Tore | Assists | Sp.`

**Spielerstatistik** (Seite 18) und **Gegnerkader** (Seite 15)
`Pl. | Spieler | Spiele | Tore | Assists | 11m | Gelb | Gelb-Rot | Rot | Ein. | Aus. | Min.`
Das Feld „11m" kommt als `getroffen/geschossen`, z. B. `1/1`.

**Titelseite** braucht zusätzlich: Wochentag, Datum, Uhrzeit, Wettbewerb,
Heim- und Gastmannschaft.

---

## 6. Was das Programm bewusst *nicht* ersetzt

* **Werbeanzeigen** – bleiben fertige PDF-Dateien und werden nur montiert.
  Sie sind gestaltete Kundenanzeigen; sie nachzubauen wäre falsch.
* **Vorwort und Spielbericht** – bleiben redaktioneller Text. Das Programm
  setzt ihn nur ins Layout (aus einer `.md`-Datei).
* **Titelfoto** – wird als Bilddatei bereitgestellt.
* **Die Titelseite selbst** kann wahlweise erzeugt *oder* als fertige
  Designer-PDF eingebunden werden (Heftplan-Eintrag `typ: pdf` statt
  `typ: titelseite`). Sie ist die gestalterisch anspruchsvollste Seite; wer sie
  weiter in InDesign pflegen will, kann das tun.
