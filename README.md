# Stadionheft-Generator – SV Wörnitzstein-Berg

Erstellt das Stadionheft **„Wörnitzstein am Ball"** weitgehend automatisch:
Mannschaften anhaken, Knopf drücken, druckfertiges PDF im A5-Format erhalten.

Die Statistikseiten (Tabelle, Torschützen, Spielerstatistik, Gegnerkader)
werden aus Daten **gesetzt** statt als Bildschirmfoto eingefügt. Die
Werbeanzeigen bleiben unverändert und werden als fertige PDF-Seiten dazwischen
montiert. Endformat (148 × 210 mm), Anschnitt (3 mm) und Hausfarbe (#E52421)
entsprechen exakt der bisherigen InDesign-Vorlage.

---

## Inhalt

* [Schnellstart](#schnellstart)
* [Bedienung über den Browser](#bedienung-über-den-browser)
* [Bedienung über die Kommandozeile](#bedienung-über-die-kommandozeile)
* [Konfiguration](#konfiguration)
* [Daten bereitstellen](#daten-bereitstellen)
* [Betrieb auf der Synology NAS](#betrieb-auf-der-synology-nas)
* [Fehlermeldungen verstehen](#fehlermeldungen-verstehen)
* [Aufbau des Projekts](#aufbau-des-projekts)
* [Weiterführende Dokumente](#weiterführende-dokumente)

---

## Schnellstart

### Voraussetzungen

* Python 3.10 oder neuer
* Unter Linux zusätzlich die Systembibliotheken für WeasyPrint:
  ```bash
  sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
                   libffi8 libjpeg62-turbo fonts-dejavu-core fonts-open-sans
  ```
  Unter Windows und macOS bringt WeasyPrint alles Nötige mit
  (siehe [WeasyPrint-Installation](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html)).

### Der einfache Weg: Startskript

Nach dem Herunterladen des Projekts genügt ein Doppelklick:

| System | Datei |
|---|---|
| Windows | `start.bat` |
| macOS / Linux | `start.sh` |

Das Skript richtet beim ersten Start alles selbst ein (Arbeitsumgebung,
Pakete, Konfiguration), startet die Weboberfläche und öffnet den Browser.
Der erste Start dauert ein paar Minuten, jeder weitere wenige Sekunden.

### Der manuelle Weg

```bash
git clone <repository-url>
cd stadionheft-svw

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m stadionheft.cli init     # legt config/config.yaml + heftplan.yaml an
```

### Sofort ausprobieren

```bash
python -m stadionheft.cli erstellen --mannschaften herren1
```

Das erzeugt mit eingebauten Beispieldaten – **ohne Internet, ohne FuPa** – ein
vollständiges PDF unter `daten/05_ausgaben/`. Für die Herren 1 sind es die
echten Zahlen der Ausgabe vom 29.07.2026; das Ergebnis lässt sich also direkt
mit dem bisherigen Heft vergleichen.

### Weboberfläche starten

```bash
python -m stadionheft.cli web
```

Dann `http://localhost:8080` im Browser öffnen.

---

## Bedienung über den Browser

Für alle, die ein Heft erstellen – kein technisches Vorwissen nötig.

1. Seite öffnen (Lesezeichen setzen!).
2. **Mannschaften anhaken**, die ins Heft sollen.
3. Optional: Spieltag und eigenen Namen eintragen.
4. **„Stadionheft erstellen"** klicken.
5. Der Fortschritt läuft live mit. Am Ende: **„PDF herunterladen"**.

Fehlt etwas – eine Werbedatei, das Vorwort, Daten einer Mannschaft – bricht
nichts ab. Das Heft wird erzeugt, und unter dem Ergebnis steht in Klartext,
was fehlt und wo es hingehört.

Unter **Hilfe** steht eine Tabelle „Was tun, wenn …".

---

## Bedienung über die Kommandozeile

Für Administratoren und automatische Abläufe.

| Befehl | Zweck |
|---|---|
| `stadionheft init` | `config.yaml` und `heftplan.yaml` aus den Beispielen anlegen |
| `stadionheft pruefen` | Konfiguration, Ordner, Wappen und NAS prüfen – ohne etwas zu erzeugen |
| `stadionheft mannschaften` | konfigurierte Mannschaften auflisten |
| `stadionheft erstellen` | Heft erzeugen |
| `stadionheft probe-fupa` | FuPa-Endpunkte testen und Rohantworten speichern |
| `stadionheft seiten-uebernehmen` | feste Seiten (Werbung, Kontakte, Impressum) aus einem bestehenden Heft übernehmen |
| `stadionheft beispieldaten` | CSV-Vorlagen mit den richtigen Spalten anlegen |
| `stadionheft web` | Weboberfläche starten |

Aufruf wahlweise als `python -m stadionheft.cli <befehl>` oder – nach
`pip install -e .` – als `stadionheft <befehl>`.

**Beispiele:**

```bash
# Alle aktiven Mannschaften, Daten von FuPa, ohne NAS-Upload
stadionheft erstellen --quelle api --ohne-nas

# Nur Herren 1 und Damen 1, Titelbild-Spiel von Damen 1
stadionheft erstellen --mannschaften herren1,damen1 --titelspiel damen1

# Ein früheres Heft exakt neu bauen (kein FuPa-Zugriff nötig)
stadionheft erstellen --snapshot daten/05_ausgaben/20260729_WaB_Druck_snapshot.json
```

### Feste Seiten aus dem alten Heft übernehmen

Werbung, Kontaktlisten und Impressum sollen sich nicht ändern – sie werden
deshalb nicht neu gesetzt, sondern als Seiten aus dem bestehenden Heft
übernommen:

```bash
stadionheft seiten-uebernehmen --aus "20260728_WaB_Druck.pdf" --alles
```

Das legt `werbung_vorne.pdf`, `werbung_hinten.pdf`, `kontaktlisten.pdf`,
`impressum.pdf` und `ruecktitel.pdf` in `daten/02_werbung/` ab. Der
mitgelieferte Heftplan bindet sie bereits ein.

So sehen diese Seiten **exakt aus wie bisher**, und die Telefonnummern der
Kontaktliste müssen nirgends abgetippt werden – ein Vorteil auch beim
Datenschutz, weil keine personenbezogenen Daten in eine Konfigurationsdatei
wandern.

Einzelne Seiten gehen genauso:

```bash
stadionheft seiten-uebernehmen --aus alt.pdf --seiten 24-25 --als kontaktlisten
```

### Werbung: ein Ordner statt einer Sammel-PDF

Jede Anzeige liegt als eigene Datei in einem Ordner. Das Heft wird bei jedem
Lauf daraus neu zusammengebaut:

```
daten/02_werbung/vorne/
├── 010_bayern-fcn-freundschaftsspiel__bis_2026-08-01.pdf
├── 020_teamshop-jako.pdf
├── 030_jako-katalog-1.pdf
├── 031_jako-katalog-2.pdf
├── 040_ullmann-universa.pdf
└── _pausiert/            ← hier abgelegte Anzeigen bleiben draußen
```

| Was | Wie |
|---|---|
| Anzeige aufnehmen | PDF in den Ordner legen |
| Anzeige entfernen | Datei löschen oder nach `_pausiert/` schieben |
| Reihenfolge ändern | Zahl am Dateianfang ändern (Zehnerschritte lassen Platz) |
| Anzeige befristen | `__bis_JJJJ-MM-TT` in den Dateinamen |
| Anzeige später starten | `__ab_JJJJ-MM-TT` in den Dateinamen |

**Befristete Anzeigen verschwinden von selbst.** Die Ankündigung eines Spiels
am 01.08. heißt `…__bis_2026-08-01.pdf` und fällt ab dem 02.08. automatisch
aus dem Heft – mit einem Hinweis im Protokoll, damit es nicht unbemerkt
passiert. Niemand muss daran denken, sie herauszunehmen.

Im Heftplan:

```yaml
- typ: werbeblock
  ordner: "02_werbung/vorne"
  optional: true
```

Einen bestehenden Werbeblock in Einzeldateien zerlegen:

```bash
stadionheft seiten-uebernehmen --aus alt.pdf --seiten 4-11 --einzeln --als vorne
```

Danach die Dateien sinnvoll umbenennen – der Ordner ist dann gleichzeitig die
Übersicht, welche Anzeigen im Heft sind.

---

## Konfiguration

Drei Dateien im Ordner `config/`. Jede hat eine kommentierte `*.example.yaml`
als Vorlage.

| Datei | Inhalt | Wie oft ändern? |
|---|---|---|
| `config.yaml` | Verein, Mannschaften, FuPa-Links, Pfade, NAS, Layout | selten |
| `heftplan.yaml` | Reihenfolge der Heftseiten | pro Saison |
| `kontakte.yaml` | Kontaktlisten für die Kontaktseiten | selten |

### Mannschaften pflegen

```yaml
mannschaften:
  herren1:
    anzeigename: "Herren 1"
    gruppe: "Herren"                 # große Zeile auf der Trennseite
    untertitel: "1. Mannschaft"      # zweite Zeile
    liga: "Bezirksliga Schwaben Nord"
    fupa_team_url: "https://www.fupa.net/team/sv-woernitzstein-berg-m1-2026-27"
    aktiv: true
    seiten: ["trenner", "gegner", "tabelle", "torjaeger", "spielerstatistik"]
```

Eine neue Mannschaft ist ein weiterer solcher Block – die Oberfläche zeigt sie
danach automatisch an. Über `seiten` steuerst du, welche Seiten je Mannschaft
entstehen (mögliche Werte: `trenner`, `spielbericht`, `gegner`, `tabelle`,
`torjaeger`, `spielerstatistik`, `naechstes_spiel`).

> **Saisonwechsel:** Die FuPa-Adressen enthalten das Saisonkürzel
> (`…-m1-2026-27`). Einmal pro Saison bei allen Mannschaften anpassen, ebenso
> `saison:` und ggf. `liga:`.

### Heftplan

Bildet die Seitenfolge ab. `mannschaftsbloecke` ist der Platzhalter, der je
ausgewählter Mannschaft expandiert wird:

```yaml
seiten:
  - typ: titelseite
  - typ: freitext
    titel: "Vorwort"
    quelle: "03_eingaben/vorwort.md"
  - typ: pdf                              # Werbeblock
    quelle: "02_werbung/werbung_vorne.pdf"
    optional: true                        # fehlt sie: nur Warnung
  - typ: mannschaftsbloecke
  - typ: kontakte
  - typ: impressum
```

Bei `typ: pdf` lässt sich mit `seiten: "1-2"` ein Teil einer mehrseitigen Datei
einbinden. `optional: false` bedeutet: fehlt die Datei, bricht der Lauf mit
einer klaren Meldung ab.

### Ausgabename

```yaml
ausgabe:
  dateiname: "{datum_kompakt}_WaB_Druck.pdf"
```

Platzhalter: `{datum}`, `{datum_kompakt}`, `{saison}`, `{spieltag}`,
`{mannschaften}`.

---

## Daten bereitstellen

### Drei Betriebsarten

`datenquelle.modus` in `config.yaml`:

| Modus | Bedeutung |
|---|---|
| `demo` | Eingebaute Beispieldaten – zum Ausprobieren, ohne Internet |
| `manuell` | CSV-Dateien aus `daten/03_eingaben/` – **funktioniert immer** |
| `api` | Automatischer Abruf von FuPa – **Endpunkte müssen erst geprüft werden** |

Mit `fallback_modus` legst du fest, worauf umgeschaltet wird, wenn die
Hauptquelle ausfällt. Standard: `manuell`.

### Manuelle Eingabe einrichten

```bash
stadionheft beispieldaten            # nur Kopfzeilen
stadionheft beispieldaten --mit-daten  # mit Beispielwerten zum Überschreiben
```

Legt für jede aktive Mannschaft die passenden Dateien in `daten/03_eingaben/`
an, dazu eine `LIESMICH.txt`.

| Datei | Spalten |
|---|---|
| `<team>_spielplan.csv` | `heim;gast;wettbewerb;datum;uhrzeit;spielort;heimspiel;spieltag;ergebnis` |
| `<team>_tabelle.csv` | `platz;mannschaft;spiele;siege;unentschieden;niederlagen;tore;gegentore;punkte;zusatz` |
| `<team>_torjaeger.csv` | `platz;spieler;mannschaft;tore;vorlagen;spiele` |
| `<team>_spieler.csv` | `platz;spieler;spiele;tore;vorlagen;elfmeter;gelb;gelb_rot;rot;ein;aus;minuten` |
| `<team>_gegner_<gegner>.csv` | wie `_spieler.csv`, je Gegner (z. B. `herren1_gegner_sg-alerheim.csv`) |
| `<team>_spielbericht.md` | Freitext |
| `vorwort.md` | Freitext für die Vorwortseite |
| `titelbild.jpg` | Foto für die Titelseite |

#### Der Spielplan erspart die meiste Arbeit

In `<team>_spielplan.csv` gehören **alle Spiele der Saison** – eine Zeile je
Partie. Das trägt man einmal im Sommer ein. Danach schaut das Programm bei
jedem Heft auf das **heutige Datum** und ermittelt selbst:

* gegen wen als nächstes gespielt wird (Titelseite, Gegnerseite)
* wann und wo, Heim oder Auswärts
* welches Spiel zuletzt war (für den Spielbericht)

```csv
heim;gast;wettbewerb;datum;uhrzeit;spielort;heimspiel;spieltag;ergebnis
TG Lauingen;SV Wörnitzstein-Berg;Bezirksliga;26.07.2026;15:00;;nein;1;0:4
SV Wörnitzstein-Berg;TSV Meitingen;Bezirksliga;29.07.2026;18:30;Wörnitzstein;ja;2;
SV Wörnitzstein-Berg;SG Alerheim;Bezirksliga;09.08.2026;15:00;Wörnitzstein;ja;3;
```

Maßgeblich für die Auswahl ist **allein das Datum** – nicht die Reihenfolge in
der Datei und auch nicht, ob ein Ergebnis eingetragen ist. Ein vergessener
Ergebniseintrag bringt also keine alte Partie auf die Titelseite.

Für den Gegnerkader empfiehlt sich eine Datei **je Gegner**
(`herren1_gegner_sg-alerheim.csv`). Das Programm greift automatisch die
passende. Gibt es nur die allgemeine `herren1_gegner_spieler.csv`, wird das
Heft trotzdem erzeugt – mit dem Hinweis, dass die Liste zum aktuellen Gegner
passen muss.

Wer lieber vor jedem Heft eine einzelne Partie einträgt, kann statt des
Spielplans `<team>_naechstes_spiel.csv` mit genau einer Zeile verwenden.

Die Dateien lassen sich direkt in Excel bearbeiten. Beim Speichern
**„CSV UTF-8 (durch Trennzeichen getrennt)"** wählen. Semikolon und Komma
werden beide erkannt, ebenso deutsche und englische Spaltennamen
(`tore`/`goals`, `sp`/`spiele`).

Fehlt eine Datei, bleibt nur die betreffende Seite leer – das Heft wird
trotzdem erzeugt.

### FuPa-Abruf einrichten

> **Wichtig:** FuPa veröffentlicht keine dokumentierte, zugesagte
> Schnittstelle. Die Endpunkte in `config.example.yaml` sind **Platzhalter**
> und müssen einmal überprüft werden. Bitte vorher
> [KONZEPT.md, Abschnitt 10](docs/KONZEPT.md#10-rechtliche-und-technische-einschränkungen)
> zu den rechtlichen Aspekten lesen.

```bash
stadionheft probe-fupa
```

Ruft die konfigurierten Adressen auf und meldet je Endpunkt Status, Inhaltstyp,
erkannte Zeilen und Feldnamen. Die Rohantworten landen in
`daten/04_zwischenergebnisse/fupa_probe/`.

Stimmt eine Adresse nicht, findest du die richtige so: FuPa-Teamseite öffnen →
`F12` → Reiter **Netzwerk** → Filter **Fetch/XHR** → Seite neu laden. Die
angezeigten Adressen in `config.yaml` unter `datenquelle.fupa.endpunkte`
eintragen.

Das Programm verhält sich dabei fair: sprechender User-Agent mit
Kontaktadresse, `robots.txt` wird respektiert, Pause zwischen Anfragen,
Zwischenspeicher von zwei Stunden.

### Reproduzierbarkeit

Neben jedem PDF entsteht `*_snapshot.json` mit **allen verwendeten Daten und
dem Heftplan**. Damit lässt sich dasselbe Heft jederzeit erneut bauen – auch
Wochen später, ohne FuPa:

```bash
stadionheft erstellen --snapshot daten/05_ausgaben/20260729_WaB_Druck_snapshot.json
```

---

## Betrieb auf der Synology NAS

Das ist der eigentliche Zielzustand: **einmal einrichten, danach öffnet jeder
im Verein nur noch einen Link – am Rechner oder am Handy.**

Schritt-für-Schritt-Anleitung mit DSM-Klickwegen, Handy-Zugriff und
Fehlerbehebung: **[docs/INSTALLATION_NAS.md](docs/INSTALLATION_NAS.md)**

Kurzfassung:

1. Ordner `/volume1/Stadionheft/…` anlegen:
   ```bash
   cd /volume1/Stadionheft
   mkdir -p 00_Konfiguration 01_Vorlagen 02_Werbung 03_Eingaben \
            04_Zwischenergebnisse 05_Ausgaben/Archiv 99_Logs
   ```
2. `config.yaml`, `heftplan.yaml`, `kontakte.yaml` nach `00_Konfiguration`.
3. Container Manager → **Projekt** → `docker-compose.yml` aus diesem Repository.
4. Aufrufen unter `http://<nas-name>:8080`.

### Vom Handy

Die Oberfläche ist für kleine Bildschirme ausgelegt – getestet bei 320, 360
und 390 px Breite. Im heimischen WLAN genügt dieselbe Adresse im
Handy-Browser; über „Zum Home-Bildschirm hinzufügen" verhält sie sich wie
eine App.

> Von unterwegs bitte **nicht** einfach den Port ins Internet öffnen – die
> App hat keine Benutzeranmeldung. Empfohlen ist der VPN-Server von DSM.
> Details in [docs/INSTALLATION_NAS.md](docs/INSTALLATION_NAS.md).

### NAS-Ablage konfigurieren

```yaml
nas:
  aktiv: true
  modus: "mount"                            # empfohlen
  mount:
    zielordner: "/nas/Stadionheft/05_Ausgaben"
  ueberschreiben: false
```

`mount` bedeutet: Der NAS-Ordner ist als Volume bzw. Netzlaufwerk eingebunden
und das Programm kopiert nur eine Datei. Kein Passwort im Programm, einfach zu
verstehen und zu reparieren.

Alternativ `modus: "smb"` für direkten Upload (benötigt
`pip install smbprotocol`). Das Passwort kommt dann **ausschließlich** aus
einer Umgebungsvariablen, nie aus der Konfigurationsdatei.

> Schlägt die NAS-Ablage fehl, ist das nur eine Warnung – das Heft liegt
> fertig lokal vor und lässt sich herunterladen.

---

## Fehlermeldungen verstehen

Alle Meldungen sind in normalem Deutsch formuliert und nennen einen konkreten
nächsten Schritt. Technische Details stehen einklappbar darunter.

| Meldung | Bedeutung / Lösung |
|---|---|
| „Die Konfiguration fehlt noch." | `stadionheft init` ausführen |
| „Die Konfiguration enthält Fehler: …" | Die Liste nennt jeden Punkt einzeln |
| „FuPa ist im Moment nicht erreichbar." | Später erneut versuchen oder auf `manuell` umstellen |
| „FuPa hat den automatischen Abruf abgelehnt (403/429)." | Zu viele Anfragen oder gesperrt – auf `manuell` umstellen |
| „Die Daten konnten nicht gelesen werden." | FuPa hat sein Format geändert → `probe-fupa` |
| „Die Datei '…' wurde nicht gefunden." | Werbe- oder Vorlagendatei fehlt; der Pfad steht in der Meldung |
| „Für … wurden keine Eingabedateien gefunden." | CSV-Dateien fehlen → `stadionheft beispieldaten` |
| „Die Synology NAS ist nicht erreichbar." | Heft ist trotzdem fertig; lokaler Pfad steht in der Meldung |
| „Das Heft hat N Seiten." (Warnung) | Für Rückendrahtheftung sind Vielfache von 4 üblich |

Protokolle: `logs/stadionheft_JJJJ-MM.log` (auf der NAS `99_Logs/`).
Ausführlicher wird es mit `protokoll.level: DEBUG`.

---

## Aufbau des Projekts

```
stadionheft-svw/
├── config/                     Beispielkonfigurationen (*.example.yaml)
├── daten/                      lokale Entsprechung der NAS-Ordner
│   ├── 01_vorlagen/  02_werbung/  03_eingaben/
│   ├── 04_zwischenergebnisse/  05_ausgaben/
├── docs/
│   ├── ANALYSE_VORLAGE.md      Analyse des bestehenden Hefts
│   ├── KONZEPT.md              Architektur, Recht, Projektplan
│   └── NAS_ORDNERSTRUKTUR.md   Ordner und Berechtigungen auf der NAS
├── stadionheft/
│   ├── build.py                Ablaufsteuerung – das Herzstück
│   ├── config.py               Konfiguration laden und prüfen
│   ├── models.py               Datenmodelle (Tabelle, Torjäger, …)
│   ├── errors.py               Fehler mit verständlichen Texten
│   ├── cli.py                  Kommandozeile
│   ├── sources/                Datenquellen: fupa_api, manuell, demo, cache
│   ├── render/                 pages.py (HTML→PDF), assemble.py (Montage)
│   ├── storage/nas.py          Ablage auf der NAS
│   ├── templates/              Seitenvorlagen (Jinja2)
│   ├── static/css/heft.css     **alle Layoutmaße** – hier anpassen
│   └── web/                    Flask-Oberfläche
├── tests/                      58 Tests
├── Dockerfile · docker-compose.yml
└── requirements.txt
```

### Layout anpassen

Alle Maße stehen als CSS-Variablen am Anfang von
`stadionheft/static/css/heft.css` und sind aus der Vorlage gemessen:

```css
--rand: 12mm;            /* seitlicher Satzspiegel */
--kopf-oben: 12mm;       /* Oberkante roter Kopfbalken */
--kopf-hoehe: 15.5mm;
--inhalt-oben: 44mm;     /* Beginn des Inhalts */
--fuss-hoehe: 13mm;
```

Farbe, Schrift und Seitenformat kommen dagegen aus `config.yaml`
(Abschnitt `layout`) – dafür muss kein CSS angefasst werden.

### Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Die Tests prüfen unter anderem, dass das Endformat exakt dem InDesign-Original
entspricht und dass Werbeseiten mit abweichender Seitenbox korrekt
vereinheitlicht werden.

---

## Weiterführende Dokumente

* **[docs/INSTALLATION_NAS.md](docs/INSTALLATION_NAS.md)** – Schritt für
  Schritt auf der Synology NAS, inklusive Zugriff vom Handy
* **[docs/KONZEPT.md](docs/KONZEPT.md)** – Architektur, Bewertung der
  Technologie-Optionen, rechtliche Einordnung des FuPa-Abrufs, Projektplan,
  **offene Punkte und was noch gebraucht wird**
* **[docs/ANALYSE_VORLAGE.md](docs/ANALYSE_VORLAGE.md)** – was in der
  bestehenden Vorlage steckt und woher die Layoutmaße stammen
* **[docs/NAS_ORDNERSTRUKTUR.md](docs/NAS_ORDNERSTRUKTUR.md)** – Ordner,
  Berechtigungen, Datensicherung

---

## Bekannte Einschränkungen

1. **Der FuPa-Abruf ist ein geprüftes Gerüst, keine fertige Funktion.** Die
   Endpunkte konnten nicht getestet werden – siehe
   [KONZEPT.md, Abschnitt 9](docs/KONZEPT.md#9-wie-die-daten-aus-fupa-geholt-werden-können).
   Die Modi `manuell` und `demo` sind vollständig getestet.
2. **Segoe UI** ist eine Windows-Schrift und darf nicht mitgeliefert werden.
   Im Container wird **Open Sans** verwendet (sehr ähnlich). Liegt Segoe UI
   auf dem System, wird sie automatisch bevorzugt.
3. **Die Titelseite** ist eine gute Annäherung an das Designer-Layout, keine
   pixelgenaue Kopie. Wer das Original will, bindet sie im Heftplan als
   `typ: pdf` ein.
4. **Keine Benutzerverwaltung.** Für das Vereinsnetz angemessen; bei Zugriff
   von außen bitte hinter den DSM-Reverse-Proxy mit Passwortschutz stellen.
