# Stadionheft-Generator – SV Wörnitzstein-Berg

Erzeugt pro Mannschaft eine **druckfertige PDF-Datei** mit den aktuellen
Zahlen aus [fupa.net](https://www.fupa.net) – Tabelle, Torschützenliste,
Spielerstatistik und die Daten des nächsten Gegners. Diese Dateien gehen an
die Person, die das Stadionheft „Wörnitzstein am Ball" zusammenbaut.

Ein Klick. Die Zahlen sind die von jetzt.

```
Mannschaften anhaken  →  Knopf  →  ZIP mit einer PDF je Mannschaft
```

---

## Was es macht — und was nicht

**Es liefert:** die Statistikseiten, druckfertig gesetzt (A5, 3 mm Anschnitt,
Schnittmarken), mit korrekt ermitteltem nächsten Gegner.

**Es liefert nicht:** Titelseite, Vorwort, Werbung, Kontaktlisten, Impressum.
Die kommen weiterhin von Hand – sie ändern sich kaum und stecken nicht in
FuPa.

Je Mannschaft entstehen sieben Seiten:

| # | Seite |
|---|---|
| 1 | Trennseite mit Mannschaftsname und Liga |
| 2 | Das nächste Spiel – Gegenüberstellung beider Mannschaften mit Form |
| 3 | Liga-Tabelle, eigene Mannschaft und Gegner hervorgehoben |
| 4 | Liga-Torschützenliste |
| 5 | Spielerstatistik der eigenen Mannschaft |
| 6 | Der Gegner mit seinem Kader |
| 7 | Saisonbilanz beider Mannschaften in Zahlen |

Bei einem Pokalgegner aus einer anderen Liga kommen dessen Tabelle und
Torschützenliste dazu.

---

## Schnellstart

### Auf der Synology NAS

Das Image ist fertig gebaut – es muss nichts kompiliert werden.

1. Ordner anlegen, `config.yaml` und `docker-compose.yml` hinterlegen
2. Container Manager → Projekt → Erstellen
3. `http://svwnas:8080` aufrufen

→ **[Schritt-für-Schritt-Anleitung](docs/ERSTE_EINRICHTUNG.md)**

### Im Homelab

```bash
docker run -d --name stadionheft -p 8080:8080 \
  -v ./config:/app/config \
  -v ./ausgaben:/app/daten/05_ausgaben \
  ghcr.io/habersatterdan/stadionheft-svw:latest
```

Gebaut für `linux/amd64` und `linux/arm64`.
→ **[Im Homelab betreiben](docs/homelab.md)**

### Lokal zum Entwickeln

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config/config.example.yaml config/config.yaml
python -m stadionheft.cli web
```

WeasyPrint braucht Pango und Cairo als Systembibliotheken. Unter Debian/Ubuntu:

```bash
sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
                 libjpeg-turbo8 shared-mime-info
```

---

## Kommandozeile

```bash
# Konfiguration, Ordner und NAS prüfen – erzeugt nichts
stadionheft pruefen

# Je Mannschaft eine PDF (alle aktiven Mannschaften)
stadionheft erstellen

# Nur bestimmte Mannschaften, Zwischenspeicher übergehen
stadionheft erstellen --mannschaften herren1,damen1 --frisch

# Testen, was FuPa tatsächlich liefert
stadionheft probe-fupa

# Einen früheren Lauf exakt wiederholen (ohne FuPa-Zugriff)
stadionheft erstellen --snapshot daten/05_ausgaben/.../snapshot.json

# CSV-Vorlagen für den Notfall anlegen
stadionheft beispieldaten
```

Im Container: `docker exec stadionheft python -m stadionheft.cli <befehl>`

---

## Der FuPa-Abruf

FuPa hat keine dokumentierte Schnittstelle. Das Programm setzt deshalb nicht
auf feste Adressen mit festen Feldnamen, sondern **sucht**:

1. **Mehrere Adressen durchprobieren** – konfigurierte Endpunkte, die
   Teamseite aus `fupa_team_url`, weitere Kandidaten. Es hört auf, sobald
   alles beisammen ist; meist genügt eine Seite.
2. **JSON aus der Seite holen** – kommt HTML statt JSON zurück, werden die
   eingebetteten JSON-Blöcke herausgelöst (`__NEXT_DATA__`, `window.__NUXT__`
   und Ähnliches).
3. **An der Struktur erkennen**, was Tabelle, Torschützenliste,
   Spielerstatistik und Spielplan ist – unabhängig davon, ob ein Feld
   `points` oder `punkte` heißt.
4. **Dasselbe für den Gegner.** Sein Bezeichner steht im Spielplan, der
   ohnehin gelesen wird. Es muss also nichts gepflegt werden.

Formkurve und Saisonbilanz werden aus dem Spielplan **gerechnet**, nicht
geholt – so passen sie immer zu den Spielen, die auch sonst im Heft stehen.

Was tatsächlich ankommt, zeigt der Knopf **„FuPa-Verbindung prüfen"** bzw.
`stadionheft probe-fupa`.
→ **[Details zur FuPa-Anbindung](docs/fupa.md)**

### Immer aktuell

- Zwischenspeicher: **15 Minuten** – er fängt nur ab, dass mehrere
  Mannschaften dieselbe Seite doppelt holen
- Auf **jeder Seite** steht der Abrufzeitpunkt
- Wurde auf ältere Daten zurückgegriffen, steht das rot im PDF und als Warnung
  in der Oberfläche
- Der nächste Gegner ergibt sich **aus dem Datum**, nicht aus der Reihenfolge
  im Spielplan

### Fair gegenüber FuPa

Sprechender User-Agent mit Kontaktadresse, `robots.txt` wird je Host
ausgewertet und respektiert, Pause zwischen Anfragen, Abbruch sobald alles da
ist, Adressmuster die einmal nichts lieferten werden im Lauf übersprungen.
Größenordnung: eine Handvoll Abrufe alle zwei Wochen.

Zu den rechtlichen Aspekten:
[KONZEPT.md, Abschnitt 10](docs/KONZEPT.md#10-rechtliche-und-technische-einschränkungen).

---

## Konfiguration

Alles in einer Datei: `config/config.yaml`
(Vorlage: [`config.example.yaml`](config/config.example.yaml)).

```yaml
verein:
  name: "SV Wörnitzstein-Berg"
  hefttitel: "Wörnitzstein am Ball"

saison: "2026/2027"

datenquelle:
  modus: "api"              # api | manuell | demo
  fallback_modus: "manuell" # wenn nichts kommt: CSV-Dateien

mannschaften:
  herren1:
    anzeigename: "Herren 1"
    gruppe: "Herren"
    untertitel: "1. Mannschaft"
    liga: "Bezirksliga Schwaben Nord"
    fupa_team_url: "https://www.fupa.net/team/sv-woernitzstein-berg-m1-2026-27"
    aktiv: true

ausgabe:
  dateiname: "{datum}_{mannschaft}_gegen_{gegner}.pdf"
  ordner: "daten/05_ausgaben"
```

Eine neue Mannschaft ist ein weiterer Block – die Oberfläche zeigt sie danach
von selbst an. Am Programmcode muss dafür nichts geändert werden.

---

## Wenn FuPa ausfällt

Dann greift automatisch der `fallback_modus`. Liegen CSV-Dateien in
`daten/03_eingaben/`, werden sie verwendet; sonst bleiben die betreffenden
Seiten leer und das Programm sagt es.

Vorlagen dafür: `stadionheft beispieldaten`
→ **[CSV-Reserve](docs/csv-reserve.md)**

---

## Reproduzierbarkeit

Jeder Lauf legt neben den PDFs eine `*_snapshot.json` mit genau den Daten ab,
aus denen sie entstanden sind. Damit lassen sich dieselben Dateien später
wieder erzeugen – ohne FuPa zu fragen.

Praktisch für die Frage „Wie sah die Tabelle beim Heft vom 4. Oktober aus?"

---

## Aufbau des Projekts

```
stadionheft/
├── build.py              Ablauf: Daten holen → setzen → je Mannschaft eine PDF
├── config.py             Konfiguration mit Validierung
├── models.py             Datenmodelle, Formkurve und Saisonbilanz
├── cli.py                Kommandozeile
├── errors.py             Fehler mit verständlichem Text und Hinweis
├── sources/
│   ├── fupa_api.py       Adressen durchprobieren, Gegner mitnehmen
│   ├── erkennung.py      Daten an ihrer Struktur erkennen
│   ├── html_daten.py     JSON aus einer HTML-Seite holen
│   ├── manuell.py        CSV-Dateien
│   ├── demo.py           eingebaute Beispieldaten
│   └── cache.py          Zwischenspeicher
├── render/
│   ├── pages.py          Jinja2 → HTML → WeasyPrint → PDF
│   └── assemble.py       Seiten zu einer Datei montieren
├── storage/nas.py        Ablage auf der NAS (Mount oder SMB)
├── web/                  Flask-Oberfläche
├── templates/            Seitenvorlagen
└── static/css/heft.css   Das gesamte Layout
```

Tests: `python -m pytest -q` (141 Tests, kein Netzzugriff)

---

## Weiterführende Dokumente

| Dokument | Inhalt |
|---|---|
| [Anleitung als Website](https://habersatterdan.github.io/stadionheft-svw/) | Alles unten, aber schöner |
| [Seiten erzeugen](docs/erzeugen.md) | Der Vorgang vor jedem Heimspiel |
| [Übergabe ans Layout](docs/uebergabe.md) | Für die Person, die das Heft baut |
| [Erste Einrichtung](docs/ERSTE_EINRICHTUNG.md) | NAS, Schritt für Schritt |
| [Im Homelab betreiben](docs/homelab.md) | Docker außerhalb der NAS |
| [FuPa-Anbindung](docs/fupa.md) | Wie der Abruf funktioniert |
| [Wenn etwas nicht klappt](docs/fehler.md) | Meldungen und was zu tun ist |
| [Umsetzungskonzept](docs/KONZEPT.md) | Architektur, Entscheidungen, Recht |
| [Analyse der Vorlage](docs/ANALYSE_VORLAGE.md) | Maße und Farben des alten Hefts |

---

## Bekannte Einschränkungen

- **Der FuPa-Abruf ist aus der Entwicklungsumgebung nie gegen das echte
  fupa.net getestet worden** – der Netzzugang dorthin war gesperrt. Geprüft
  wurde gegen nachgebaute Seiten. Der Knopf „FuPa-Verbindung prüfen" zeigt,
  ob es in eurer Umgebung greift.
- Die Dateien sind in **RGB**, nicht CMYK. Die meisten Druckereien wandeln
  selbst um.
- Die Formkurve zeigt nur Spiele der **laufenden Saison** – weiter reicht der
  Spielplan nicht.
- Der Gegnerabruf hängt daran, dass FuPa im Spielplan einen Bezeichner für den
  Gegner mitliefert. Tut er das nicht, lässt sich die Adresse von Hand
  hinterlegen.
