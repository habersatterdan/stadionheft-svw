# Umsetzungskonzept

Stand: 03.08.2026 · Grundlage: Analyse von `20260728_WaB_Druck.pdf`
(siehe [ANALYSE_VORLAGE.md](ANALYSE_VORLAGE.md))

---

## 1. Zusammenfassung des Vorhabens

Das Stadionheft „Wörnitzstein am Ball" (A5, 28 Seiten) entsteht bisher in
InDesign. Die wiederkehrenden Teile – Werbung, Kontaktlisten, Impressum – sind
kein Aufwand. Der Aufwand steckt in **vier Seiten je Mannschaft**, deren Inhalte
heute als **Bildschirmfotos von fupa.net** von Hand ins Layout kopiert werden:
Tabelle, Torschützenliste, Spielerstatistik und Gegnerkader.

Ziel ist ein Programm, mit dem **jede Person im Verein** ein Heft erstellen kann:
Mannschaften anhaken, Knopf drücken, fertiges Druck-PDF erhalten – ohne InDesign,
ohne Screenshots, ohne dass es an einer einzelnen Person hängt.

Der gewählte Ansatz: **Die vier Datenseiten werden aus echten Daten gesetzt**
(scharfer Text statt 148-dpi-Bild), die unveränderten Werbeseiten werden als
fertige PDF-Dateien dazwischen montiert. Endformat, Anschnitt und Hausfarbe
bleiben exakt wie bisher.

---

## 2. Was ich noch von dir brauche

Sortiert nach Dringlichkeit. Ohne Punkt 1 und 2 läuft nur der Demo-Modus.

### Muss – sonst fehlen Inhalte

| # | Was | Wohin | Warum |
|---|---|---|---|
| 1 | **Ligen von Herren 2, Herren 3, Damen 1, Damen 2** | `config/config.yaml`, Feld `liga` | steht auf der Trennseite und über der Tabelle; aktuell „TODO" |
| 2 | **Werbeanzeigen als PDF** (A5, 3 mm Anschnitt) | `daten/02_werbung/` | 20 der 28 Seiten; ohne sie hat das Heft nur die erzeugten Seiten |
| 3 | **Vereinswappen** freigestellt als PNG in Druckauflösung | `daten/01_vorlagen/` | Ich habe es aus dem PDF extrahiert (107 × 155 px) – das reicht für 19 mm Breite gerade so, ein Original wäre besser |
| 4 | **Impressumsangaben** (Redaktion, Satz, Druck) | `config.yaml`, Abschnitt `impressum` | aktuell Platzhalter |
| 5 | **Kontaktlisten** | `config/kontakte.yaml` | ich habe sie bewusst *nicht* aus dem PDF übernommen – personenbezogene Daten gehören nicht ungefragt in ein Repository |

### Sollte – entscheidet über den Automatisierungsgrad

| # | Frage | Auswirkung |
|---|---|---|
| 6 | **Läuft der FuPa-Abruf bei euch?** Ein Klick: „FuPa-Verbindung prüfen" in der Oberfläche, oder `python -m stadionheft.cli probe-fupa`. Das Programm sucht sich Adressen und Feldnamen selbst; der Test zeigt, ob es fündig wird. | siehe Abschnitt 9 – aus meiner Umgebung ist fupa.net gesperrt, geprüft werden kann es nur bei euch |
| 7 | Habt ihr bei FuPa/Vereinsheim einen **Vereinszugang mit Exportfunktion**? | Ein offizieller Export wäre jedem Scraping vorzuziehen |
| 8 | Sollen die **Kader der Gegner** weiter ins Heft? Das ist die aufwendigste Abfrage (fremdes Team, fremde Liga). | ggf. Seite streichen und Aufwand halbieren |
| 9 | **Titelseite**: selbst erzeugen (funktioniert, kommt dem Original nahe) oder weiter vom Designstudio als PDF? | beides möglich, eine Zeile im Heftplan |

### Kann – für den Vollausbau

| # | Was |
|---|---|
| 10 | Zugangsdaten/Pfad der Synology NAS (Freigabename, Zielordner, DSM-Benutzer) |
| 11 | Titelfoto je Ausgabe – oder Regel, woher es kommt |
| 12 | Lizenz für Segoe UI auf dem Server, sonst bleibt es bei Open Sans (siehe Abschnitt 13) |

---

## 3. Software-Architektur

Vier Schichten, klar getrennt. Jede Schicht kennt nur die darunter.

```
┌─────────────────────────────────────────────────────────┐
│  Bedienung                                              │
│  stadionheft/web/   Weboberfläche (Flask)               │
│  stadionheft/cli.py Kommandozeile (Admins, Automatik)   │
└───────────────────────────┬─────────────────────────────┘
                            │  beide rufen dieselbe Funktion
┌───────────────────────────▼─────────────────────────────┐
│  Ablaufsteuerung                                        │
│  stadionheft/build.py                                   │
│  Daten holen → Snapshot → Seiten setzen → montieren     │
└───────┬───────────────────┬──────────────────┬──────────┘
        │                   │                  │
┌───────▼────────┐ ┌────────▼────────┐ ┌───────▼─────────┐
│ Datenquellen   │ │ Rendering       │ │ Ablage          │
│ sources/       │ │ render/         │ │ storage/        │
│ ├ fupa_api.py  │ │ ├ pages.py      │ │ └ nas.py        │
│ ├ manuell.py   │ │ │  Jinja2+CSS   │ │   Mount / SMB   │
│ ├ demo.py      │ │ │  →WeasyPrint  │ │                 │
│ └ cache.py     │ │ └ assemble.py   │ │                 │
│                │ │    pypdf-Montage│ │                 │
└────────────────┘ └─────────────────┘ └─────────────────┘
        ▲                   ▲
        │                   │
   models.py           templates/  + static/css/heft.css
   config.py           errors.py     logging_setup.py
```

### Die drei Entscheidungen, auf denen alles aufbaut

**a) Datenquellen sind austauschbar.**
`sources/base.py` definiert eine Schnittstelle mit genau einer Methode:
`hole(mannschaft) -> MannschaftsDaten`. Es gibt drei Implementierungen (FuPa,
CSV, Demo). Der Rest des Programms weiß nicht, welche gerade läuft. Folge:
Wenn FuPa ausfällt oder sein Format ändert, **schaltet das Programm automatisch
auf CSV um** statt abzustürzen – und die Hefterstellung ist nie blockiert.

**b) Feste Seiten werden montiert, nicht nachgebaut.**
Die Werbeseiten sind gestaltete Kundenanzeigen. Sie bleiben PDF-Dateien und
werden mit `pypdf` zwischen die erzeugten Seiten gelegt. `assemble.py` bringt
dabei **alle Seiten auf eine gemeinsame Seitenbox** – nötig, weil das
InDesign-Original 461 × 637 pt hat und WeasyPrint 437 × 612 pt liefert. Ohne
diesen Schritt bekäme die Druckerei ein gemischtes Dokument.

**c) Jeder Lauf ist reproduzierbar.**
Neben jedem PDF entsteht `*_snapshot.json` mit **allen verwendeten Daten und
dem Heftplan**. Damit lässt sich dasselbe Heft jederzeit erneut bauen – ohne
FuPa, ohne dass zwischenzeitliche Tabellenänderungen etwas verschieben. Das ist
die Antwort auf „das Heft von letzter Woche nochmal, aber mit korrigiertem
Vorwort".

---

## 4. Empfehlung: Web-App, Desktop-App oder Skript?

### Bewertung der genannten Optionen

| Option | Vorteile | Nachteile | Urteil |
|---|---|---|---|
| **Python + Flask (Web)** | Läuft zentral im Container auf der NAS. Benutzer brauchen **nur einen Browser** – keine Installation, kein Update. Alle arbeiten mit derselben Version und denselben Pfaden. NAS-Ordner sind lokale Ordner. | Muss einmal auf der NAS eingerichtet werden. | **Empfehlung** |
| Python + Streamlit | Sehr schnell gebaut. | Zusatzabhängigkeit (~100 MB), eigenes Bedienkonzept, bei Mehrschritt-Abläufen und Fehleranzeige unhandlich. Kaum weniger Code als Flask hier. | nein |
| Python + Tkinter/PySide (Desktop) | Kein Server nötig. | **Muss auf jedem Rechner installiert und aktualisiert werden.** Jeder braucht Zugriff auf die NAS-Laufwerke; Pfade unterscheiden sich je Rechner. Genau das Problem „hängt an einer Person" verlagert sich nur. | nein |
| Node.js Web-App | Gute PDF-Werkzeuge (Puppeteer). | Puppeteer bringt einen kompletten Chromium mit (~400 MB) – schwer für eine NAS. Datenaufbereitung ist in Python angenehmer. Kein Vorteil gegenüber a). | nein |
| PowerShell | – | Kein brauchbarer PDF-Satz, Windows-gebunden, schlecht testbar. | nein |

### Begründung der Empfehlung

Die Anforderung „**nicht nur von mir abhängig**" ist keine Layout-Anforderung,
sondern eine Betriebsanforderung. Eine Desktop-App erfüllt sie nur scheinbar:
Sobald zwei Leute unterschiedliche Versionen oder unterschiedliche
Laufwerksbuchstaben haben, entstehen Fehler, die wieder nur eine Person lösen
kann.

Eine zentrale Web-App auf der NAS löst das strukturell:

* **Eine** Installation, **eine** Konfiguration, **ein** Satz Pfade.
* Neue Helfer bekommen einen Link, keine Installationsanleitung.
* Die NAS läuft ohnehin – kein zusätzliches Gerät.
* Funktioniert vom Handy aus (z. B. Vorwort korrigieren und neu erzeugen).

Flask statt Streamlit, weil die Oberfläche hier *sehr* einfach ist (ein Formular)
und der Wert stattdessen in verständlichen Fehlermeldungen und einer
Fortschrittsanzeige liegt – dafür braucht es Kontrolle über das HTML.

**Die Kommandozeile bleibt trotzdem erhalten** (`stadionheft erstellen …`).
Sie ist für Administratoren, für Tests und dafür, das Heft später per
Aufgabenplaner automatisch erzeugen zu lassen.

---

## 5. Ordnerstruktur auf der Synology NAS

Ausführlich in [NAS_ORDNERSTRUKTUR.md](NAS_ORDNERSTRUKTUR.md). Kurzfassung:

```
/volume1/Stadionheft/
├── 00_Konfiguration/      config.yaml, heftplan.yaml, kontakte.yaml
├── 01_Vorlagen/           Wappen, ggf. Designer-Titelseite, InDesign-Archiv
├── 02_Werbung/            Werbeseiten als PDF
├── 03_Eingaben/           Vorwort, Titelbild, CSV-Dateien  ← Redaktion
├── 04_Zwischenergebnisse/ Cache und Einzelseiten (löschbar)
├── 05_Ausgaben/           fertige Hefte + Snapshots
└── 99_Logs/
```

Die Nummerierung folgt dem Arbeitsablauf, damit in der Dateistation sofort
erkennbar ist, wo etwas hingehört. `00_Konfiguration` lässt sich in DSM auf
Administratoren beschränken, ohne den Rest zu sperren.

---

## 6. Konfigurationsdatei

**YAML statt JSON** – weil YAML Kommentare erlaubt. Bei einer Datei, die
Vereinsmitglieder ohne Programmierkenntnisse pflegen sollen, ist die
Erklärung direkt neben dem Wert der halbe Nutzen.

Drei Dateien, bewusst getrennt:

| Datei | Inhalt | Ändert sich |
|---|---|---|
| `config.yaml` | Verein, Mannschaften, FuPa-Links, Pfade, NAS, Layout | selten |
| `heftplan.yaml` | Seitenreihenfolge des Hefts | pro Saison |
| `kontakte.yaml` | Kontaktlisten | selten, personenbezogen |

Vollständige Beispiele mit Kommentaren: `config/config.example.yaml`,
`config/heftplan.example.yaml`, `config/kontakte.example.yaml`.

Kernstück – eine Mannschaft:

```yaml
mannschaften:
  herren1:
    anzeigename: "Herren 1"
    gruppe: "Herren"                          # große Zeile der Trennseite
    untertitel: "1. Mannschaft"               # zweite Zeile
    liga: "Bezirksliga Schwaben Nord"
    fupa_team_url: "https://www.fupa.net/team/sv-woernitzstein-berg-m1-2026-27"
    aktiv: true
    seiten: ["trenner", "gegner", "tabelle", "torjaeger", "spielerstatistik"]
```

Eine neue Mannschaft ist ein weiterer solcher Block – die Oberfläche zeigt sie
danach automatisch an. **Kein Programmcode muss angefasst werden.**

Das Feld `seiten` bestimmt, welche Seiten je Mannschaft entstehen. Damit lässt
sich steuern, dass die Herren 1 den vollen Block bekommen und die dritte
Mannschaft nur Tabelle und Torjäger.

Der Heftplan bildet die 28 Seiten der Vorlage ab; `mannschaftsbloecke` ist der
Platzhalter, der je ausgewählter Mannschaft expandiert wird:

```yaml
seiten:
  - typ: titelseite
  - typ: freitext
    titel: "Vorwort"
    quelle: "03_eingaben/vorwort.md"
  - typ: pdf
    quelle: "02_werbung/werbung_vorne.pdf"
    optional: true
  - typ: mannschaftsbloecke
    trenner_zwischen:
      - typ: pdf
        quelle: "02_werbung/werbung_zwischen.pdf"
        optional: true
  - typ: kontakte
  - typ: impressum
```

**Passwörter stehen nie in einer Konfigurationsdatei.** Das NAS-Passwort wird
ausschließlich aus einer Umgebungsvariablen gelesen (`nas.smb.passwort_umgebungsvariable`).

---

## 7. Ablauf für normale Benutzer

Fünf Schritte, kein technisches Vorwissen:

1. Browser öffnen, Lesezeichen „Stadionheft" anklicken (`http://diskstation:8080`).
2. Mannschaften anhaken, die ins Heft sollen.
3. Optional: Spieltag und eigenen Namen eintragen.
4. **„Stadionheft erstellen"** klicken.
5. Warten (Fortschritt läuft mit), dann **„PDF herunterladen"** – oder das Heft
   direkt im NAS-Ordner `05_Ausgaben` abholen.

**Wenn eine Mannschaft leere Seiten hat oder eine Werbedatei fehlt**, bricht
nichts ab. Das Heft wird erzeugt, und unter dem Ergebnis steht in Klartext, was
fehlt und wo es hingehört, z. B.:

> Die Datei `herren2_torjaeger.csv` fehlt – die zugehörige Seite bleibt leer.

**Wenn wirklich etwas schiefgeht**, erscheint eine Meldung in normalem Deutsch
mit Lösungsvorschlag – die technischen Details sind einklappbar darunter:

> **FuPa ist im Moment nicht erreichbar.**
> Bitte Internetverbindung prüfen und später erneut versuchen. Alternativ im
> Programm auf „Manuelle Eingabe" umstellen.

Zusätzlich gibt es unter `/hilfe` eine Tabelle „Was tun, wenn …".

### Vor dem Spieltag (Redaktion)

1. `vorwort.md` und `titelbild.jpg` in `03_Eingaben` ablegen.
2. Bei manueller Eingabe: CSV-Dateien aktualisieren (in Excel öffnen, Zahlen
   eintragen, als „CSV UTF-8" speichern).
3. Heft erstellen, PDF durchsehen, an die Druckerei geben.

---

## 8. Ablauf für Administratoren

### Einmalig

1. Container Manager auf der NAS → Projekt aus `docker-compose.yml`.
2. `config.yaml` in `00_Konfiguration` ausfüllen (TODO-Werte).
3. `python -m stadionheft.cli pruefen` – zeigt Konfiguration, Ordner und
   NAS-Erreichbarkeit auf einen Blick.
4. `python -m stadionheft.cli beispieldaten` – legt CSV-Vorlagen mit den
   richtigen Spaltenüberschriften an.

### Wiederkehrend

| Anlass | Was tun |
|---|---|
| Neue Saison | `fupa_team_url` aller Mannschaften auf das neue Saisonkürzel ändern (`…-2027-28`), `saison` anpassen, `liga` prüfen |
| Neue Werbeanzeigen | PDFs nach `02_Werbung`, ggf. `heftplan.yaml` anpassen |
| Neue Mannschaft | Block in `config.yaml` ergänzen |
| FuPa liefert nichts mehr | „FuPa-Verbindung prüfen“ bzw. `probe-fupa` – meldet je Adresse Status und was erkannt wurde; notfalls Adresse in `datenquelle.fupa.zusatz_adressen` nachtragen. Bis dahin greift der Rückfall auf CSV. |
| Layout anpassen | `stadionheft/static/css/heft.css` – alle Maße stehen als Variablen am Anfang |
| Fehlersuche | `99_Logs/stadionheft_JJJJ-MM.log` |

### Notfall: „Das Heft muss heute raus und nichts funktioniert"

`datenquelle.modus: manuell` setzen, Zahlen in die CSV-Dateien eintragen,
Heft erstellen. Diese Betriebsart braucht kein Internet und keine
Schnittstelle – sie funktioniert immer.

---

## 9. Wie die Daten aus FuPa geholt werden können

### Ehrliche Lage vorweg

**Ich konnte die FuPa-Schnittstellen aus meiner Arbeitsumgebung heraus nicht
testen** – der Netzzugang zu `fupa.net` und `api.fupa.net` ist hier gesperrt
(HTTP 403 vom Proxy). Ich weiß also weder, welche Adressen antworten, noch wie
FuPa seine Felder nennt.

Die erste Fassung hat daraus die falsche Konsequenz gezogen: feste Adressen,
feste Feldnamen, beides als „Platzhalter" markiert und zur Prüfung an den
Verein weitergereicht. Das funktioniert nur, wenn jemand die Prüfung macht –
und bricht wieder, sobald FuPa etwas umstellt.

Die jetzige Fassung dreht das um: **Das Programm findet beides selbst heraus.**

### Die drei technisch möglichen Wege

| Weg | Wie es funktioniert | Bewertung |
|---|---|---|
| **A – Interne JSON-Schnittstelle** | Die FuPa-Website lädt Tabellen und Statistiken über eigene JSON-Aufrufe nach. Diese lassen sich direkt ansprechen. | Sauber, wenn zugänglich: kein HTML-Parsen, geringe Last. Aber undokumentiert und jederzeit änderbar. |
| **B – Eingebettetes JSON aus der Teamseite** | Die öffentliche Teamseite abrufen und die JSON-Blöcke lesen, die im HTML stecken (`__NEXT_DATA__` und Ähnliches). | **Der verlässliche Weg.** Die Adresse steht in der Konfiguration, sie muss nicht erraten werden. Kein Parsen von HTML-Struktur, nur von Daten. |
| **C – Manuelle Eingabe (CSV)** | Zahlen aus FuPa in Excel übertragen bzw. per Copy-Paste einfügen, als CSV speichern. | **Immer verfügbar, keine rechtliche Grauzone.** Aufwand ~10 Minuten je Mannschaft. Bleibt als Rückfall bestehen. |

Das Programm nutzt A und B **nacheinander in einem Durchgang** und fällt bei
Bedarf auf C zurück.

### Wie das Suchen funktioniert

1. **Adressen durchprobieren.** Konfigurierte Endpunkte, dann die Teamseite der
   Mannschaft, dann selbst ergänzte Adressen, dann eingebaute Kandidaten
   (`/tabelle`, `/spielplan`, `/kader`, `/statistiken`). Abbruch, sobald alles
   beisammen ist – meist nach einer Seite.
2. **Nutzdaten gewinnen.** JSON direkt; bei HTML werden die eingebetteten
   JSON-Blöcke herausgelöst (`stadionheft/sources/html_daten.py`).
3. **Erkennen statt zuordnen.** In allen gefundenen Daten wird gesucht, was wie
   eine Tabelle, eine Torschützenliste, eine Spielerstatistik oder ein
   Spielplan *aussieht* – an der Struktur, nicht an den Feldnamen
   (`stadionheft/sources/erkennung.py`).

Eine Tabellenzeile ist eine Zeile mit Mannschaftsname, Punkten, Siegen,
Niederlagen und Toren – ob das Feld `points`, `punkte` oder `pts` heißt und ob
der Name direkt drinsteht oder in einem verschachtelten `team`-Objekt, spielt
keine Rolle. Torschützen unterscheiden sich von der Spielerstatistik dadurch,
dass Letztere Einsatzminuten und Karten führt. Kommen mehrere Kandidaten in
Frage, gewinnt die vollständigste Liste.

### Prüfen, was tatsächlich ankommt

```bash
python -m stadionheft.cli probe-fupa
```

Der Befehl klappert dieselben Adressen ab und meldet je Adresse Status und was
sich daraus erkennen ließ, am Ende eine Bilanz über alle vier Datenteile. Die
Rohantworten landen als JSON in `04_Zwischenergebnisse/fupa_probe/`. Dasselbe
gibt es als Knopf in der Weboberfläche.

Fehlt etwas, lässt sich eine Adresse in `datenquelle.fupa.zusatz_adressen`
nachtragen – am Programm muss dafür nichts geändert werden.

### Was das Programm heute schon richtig macht

* Sprechender User-Agent **mit Kontaktadresse** – kein anonymer Zugriff.
* `robots.txt` wird gelesen und respektiert (abschaltbar, aber standardmäßig an).
* Konfigurierbare Pause zwischen Anfragen (Standard 1,5 s).
* Wiederholung mit wachsender Wartezeit bei Netzfehlern (2 s, 4 s, 8 s).
* Zwischenspeicher: dieselbe Adresse wird innerhalb von zwei Stunden nicht
  erneut abgerufen. Bei Ausfall wird notfalls auf ältere Daten zurückgegriffen –
  mit deutlichem Hinweis im Heft-Protokoll.
* **Sehr geringe Last insgesamt**: rund ein Dutzend Abrufe alle zwei Wochen.

---

## 10. Rechtliche und technische Einschränkungen

**Kein Rechtsrat, sondern eine Einordnung mit dem, was technisch relevant ist.**
Im Zweifel bitte den Vereinsjuristen oder FuPa selbst fragen – Letzteres ist
ohnehin der pragmatischste Weg.

### Rechtlich

| Thema | Einordnung | Konsequenz im Programm |
|---|---|---|
| **Nutzungsbedingungen (AGB)** | Verbieten häufig automatisierte Abfragen. Verstoß ist primär vertraglich, nicht strafbar – kann aber zur Sperre führen. | AGB einmal prüfen. Alternative: FuPa direkt fragen. |
| **Datenbankherstellerrecht** (§§ 87a ff. UrhG) | Geschützt ist die *wesentliche* Übernahme einer Datenbank. Eine Liga-Tabelle für ein Vereinsheft ist ein sehr kleiner Ausschnitt. Wiederholte systematische Entnahme unwesentlicher Teile kann in Summe dennoch relevant werden. | Nur die tatsächlich benötigten Seiten, keine Massenabfrage, kein Aufbau einer eigenen Datenbank. |
| **Urheberrecht an Zahlen** | Reine Fakten (Tore, Punkte) sind **nicht** urheberrechtlich geschützt. Die *Darstellung* schon. | Das Programm setzt Zahlen **neu**, statt Screenshots zu übernehmen. Das ist rechtlich sauberer als die bisherige Praxis. |
| **Spielerfotos** | Die runden Bilder auf FuPa sind geschützt und unterliegen dem Recht am eigenen Bild. | **Werden bewusst nicht übernommen.** |
| **Quellenangabe** | Guter Stil und im Zweifel hilfreich. | Auf jeder Datenseite steht „Quelle: fupa.net" mit Stand-Datum. |
| **DSGVO** | Spielernamen mit Statistik sind personenbezogene Daten. Für den eigenen Kader unproblematisch (Vereinsmitglieder, öffentlicher Spielbetrieb); beim **Gegnerkader** ist es eine Weiterverbreitung fremder Personendaten. | Bewusste Entscheidung nötig – siehe offene Frage 8. `kontakte.yaml` steht nicht im Repository. |

**Meine Empfehlung, in dieser Reihenfolge:**

1. **FuPa kurz anschreiben.** Ein Satz genügt: „Wir sind der SV Wörnitzstein-Berg,
   möchten für unser Stadionheft alle zwei Wochen Tabelle und Statistik unserer
   eigenen Teams automatisch abrufen – ist das in Ordnung?" Eine schriftliche
   Zusage löst jede Grauzone. Erfahrungsgemäß stehen Regionalportale
   Vereinsprojekten offen gegenüber.
2. Bis zur Antwort: **manuelle Eingabe** benutzen. Funktioniert vollständig.
3. Danach: automatischen Abruf einschalten.

### Technisch

* **Keine Zusage auf Stabilität.** Ändert FuPa etwas, bricht der Abruf. Deshalb
  der automatische Rückfall auf CSV und die verständliche Fehlermeldung statt
  eines Absturzes.
* **Kein Login-Zugriff.** Das Programm meldet sich nicht bei FuPa an und umgeht
  keine Schutzmaßnahmen. Sollte FuPa den Zugriff sperren (403/429), meldet das
  Programm das im Klartext und schaltet um – es versucht **nicht**, die Sperre
  zu umgehen.
* **Saisonwechsel:** Die Team-Adressen enthalten das Saisonkürzel
  (`…-m1-2026-27`). Sie müssen jede Saison einmal aktualisiert werden – das ist
  in `config.yaml` eine Minute Arbeit und in Abschnitt 8 vermerkt.

### Bessere Alternativen zum Scraping – bewertet

| Alternative | Bewertung |
|---|---|
| **Offizieller Export von FuPa** (falls es einen Vereinszugang gibt) | **Beste Lösung.** Bitte prüfen (offene Frage 7). |
| **BFV-Daten** (Bayerischer Fußball-Verband) | Die Originalquelle – FuPa bezieht seine Daten von dort. Prüfenswert, ob der BFV Vereinen einen Datenzugang bietet. |
| **Manuelle CSV-Eingabe** | Umgesetzt, rechtlich unbedenklich, ~10 min/Mannschaft. Der solide Standardweg. |
| **Copy-Paste aus der Browsertabelle nach Excel** | Praktischer Mittelweg: FuPa-Tabelle markieren, in Excel einfügen, Spalten sortieren, als CSV speichern. Deutlich schneller als Abtippen. |
| **Eigene Erfassung im Verein** | Für die eigene Spielerstatistik ohnehin oft genauer als FuPa (Einwechslungen, Minuten). Auf Dauer die unabhängigste Lösung. |

---

## 11. Wie die Vorlage automatisch befüllt wird

### Der gewählte Weg: HTML/CSS → PDF, dann montieren

```
Daten (Tabelle, Torjäger, …)
        │
        ▼  Jinja2-Vorlage  (templates/tabelle.html.j2)
      HTML
        │
        ▼  CSS  (static/css/heft.css – enthält alle Maße der Vorlage)
        │      @page { size: 148mm 210mm; bleed: 3mm; marks: crop cross; }
        ▼  WeasyPrint
   Einzelne PDF-Seite  (Endformat exakt wie InDesign)
        │
        ▼  pypdf – zusammen mit den Werbe-PDFs, Boxen vereinheitlicht
   Fertiges Stadionheft
```

**Nachgewiesen, nicht behauptet:** Die erzeugten Seiten haben eine TrimBox von
419,53 × 595,28 pt – identisch mit dem InDesign-Original. Der Test
`test_endformat_entspricht_der_vorlage` prüft das bei jedem Testlauf.

### Warum nicht InDesign fernsteuern?

InDesign lässt sich per Skript automatisieren (IDML/Datenzusammenführung). Das
wäre aber:

* an eine Adobe-Lizenz und einen Windows-Rechner gebunden – **läuft nicht auf
  der NAS**, damit fällt die zentrale Web-App weg,
* schwer testbar und schlecht versionierbar,
* fehleranfällig bei jedem InDesign-Update.

HTML/CSS ist dagegen Text: versionierbar, testbar, von jedem mit
Webkenntnissen anpassbar – und im Verein findet sich dafür eher jemand als für
InDesign-Skripting.

### Was das konkret heißt

| Seite | Herkunft |
|---|---|
| Titelseite | erzeugt (oder Designer-PDF, eine Zeile im Heftplan) |
| Vorwort | erzeugt aus `vorwort.md`, zweispaltig, läuft automatisch auf Folgeseiten |
| Werbung | **unverändert montiert** |
| Trennseite | erzeugt aus der Konfiguration |
| Spielbericht | erzeugt aus `<mannschaft>_spielbericht.md` |
| Gegner / Tabelle / Torjäger / Spielerstatistik | **erzeugt aus Daten** – das ist der eigentliche Gewinn |
| Kontakte / Impressum | erzeugt aus der Konfiguration |
| Rücktitel | montiert |

---

## 12. Projektplan

### Fertig (dieses Repository)

- [x] Vorlage analysiert, Maße und Farbe übernommen
- [x] Projektstruktur, Konfiguration mit Validierung
- [x] Drei Datenquellen: FuPa (selbstsuchend), CSV, Demo – mit automatischem Rückfall
- [x] Seitensatz aller Seitentypen im Layout der Vorlage
- [x] PDF-Montage inkl. Vereinheitlichung unterschiedlicher Seitenboxen
- [x] Weboberfläche mit Fortschrittsanzeige und verständlichen Fehlermeldungen
- [x] Kommandozeile inkl. `pruefen`, `probe-fupa`, `beispieldaten`
- [x] NAS-Ablage (Mount und SMB)
- [x] Snapshot-Mechanismus für reproduzierbare Läufe
- [x] Docker-Setup für die Synology NAS
- [x] 159 automatische Tests

### Schritt 1 – Betriebsbereit (etwa ein Abend, ohne FuPa)

1. Ligen, Impressum, Kontakte eintragen.
2. Werbeanzeigen als PDF nach `02_Werbung`.
3. Heftplan an die tatsächliche Seitenfolge anpassen.
4. Probelauf, Ergebnis mit der Ausgabe vom 29.07. vergleichen.
5. Container auf der NAS einrichten.

**Ergebnis:** Das Heft ist mit manueller Dateneingabe vollständig erstellbar.

### Schritt 2 – FuPa automatisch (Voreinstellung, nur noch prüfen)

`datenquelle.modus: api` ist bereits gesetzt. Zu tun bleibt:

1. „FuPa-Verbindung prüfen" anklicken und die Bilanz ansehen.
2. Was nicht gefunden wird: Adresse in `zusatz_adressen` nachtragen oder per
   CSV pflegen.
3. Probelauf mit allen fünf Mannschaften.

**Ergebnis:** Mannschaften anhaken → Knopf → fertiges Heft.

### Schritt 3 – Feinschliff (nach Bedarf)

* Titelseite nach Designer-Vorlage verfeinern oder als PDF einbinden.
* Vorwort direkt in der Weboberfläche bearbeitbar machen.
* Automatischer Lauf per Aufgabenplaner (z. B. jeden Donnerstag ein
  Entwurf ins Postfach der Redaktion).
* Segoe UI durch eine lizenzierte Datei ersetzen.

---

## 13. Bekannte Einschränkungen

Damit hier nichts überversprochen wird:

1. **Die FuPa-Endpunkte sind ungeprüft.** Siehe Abschnitt 9. Der Modus `api`
   ist als Gerüst vorhanden, nicht als fertige Funktion. `manuell` und `demo`
   sind vollständig getestet.
2. **Segoe UI fehlt auf dem Server.** Die Schrift ist eine Windows-Systemschrift
   und darf nicht mitgeliefert werden. Im Container wird **Open Sans**
   verwendet – gleiche Anmutung, ganz leicht andere Buchstabenbreiten. Wer
   Segoe UI lizenziert hat, legt die Dateien in den Container und ändert nichts
   weiter: die Schriftliste probiert Segoe UI zuerst.
3. **Die Titelseite ist eine sehr gute Annäherung, keine pixelgenaue Kopie.**
   Die diagonalen Formen des Designstudios sind nachgebildet, nicht
   nachgemessen. Wer das Original will, bindet die Titelseite als PDF ein.
4. **Das Vereinswappen** stammt aus dem PDF (107 × 155 px). Für 19 mm Breite
   reicht das knapp; ein Original in Druckauflösung wäre besser.
5. **Keine Benutzerverwaltung.** Wer die Adresse kennt, kann ein Heft erzeugen.
   Für das Vereinsnetz angemessen; bei Zugriff von außen bitte hinter den
   DSM-Reverse-Proxy mit Passwortschutz stellen.
6. **Ein Heft gleichzeitig.** Bei zwei parallelen Läufen funktioniert alles,
   aber die Ausgabedateien können sich denselben Namen teilen. In der Praxis
   irrelevant.
