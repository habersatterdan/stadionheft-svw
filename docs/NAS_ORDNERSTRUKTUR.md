# Ordnerstruktur auf der Synology NAS

## Vorschlag

Eine gemeinsame Freigabe `Stadionheft`, darin nummerierte Ordner in der
Reihenfolge des Arbeitsablaufs. Die Nummern sorgen dafür, dass die Ordner in
der Dateistation immer in der logischen Reihenfolge stehen – und dass jeder
sofort sieht, wo etwas hingehört.

```
/volume1/Stadionheft/
│
├── 00_Konfiguration/            ← nur Administratoren
│   ├── config.yaml                 Mannschaften, FuPa-Links, Pfade
│   ├── heftplan.yaml               Seitenreihenfolge des Hefts
│   └── kontakte.yaml               Kontaktlisten (personenbezogen!)
│
├── 01_Vorlagen/                 ← ändert sich fast nie
│   ├── svw_logo.png                Vereinswappen (freigestellt, PNG)
│   ├── titelseite_designer.pdf     optional: fertige Titelseite aus InDesign
│   └── Original_InDesign/          das InDesign-Dokument als Archiv
│
├── 02_Werbung/                  ← einmal pro Saison
│   ├── werbung_vorne.pdf           Seiten 4–11 (eine mehrseitige PDF)
│   ├── werbung_zwischen.pdf        Trennanzeige zwischen Mannschaftsblöcken
│   ├── werbung_hinten.pdf          Seiten 19–26
│   ├── ruecktitel.pdf              Seite 28
│   └── einzeln/                    Ablage der Einzelanzeigen je Kunde
│       ├── ullmann_universa.pdf
│       ├── axa_wiedemann.pdf
│       └── ...
│
├── 03_Eingaben/                 ← hier arbeitet die Redaktion, pro Ausgabe
│   ├── LIESMICH.txt                erklärt die Dateien (legt das Programm an)
│   ├── vorwort.md                  Vorworttext
│   ├── titelbild.jpg               Foto für die Titelseite
│   ├── herren1_tabelle.csv         nur nötig bei manueller Eingabe
│   ├── herren1_torjaeger.csv
│   ├── herren1_spieler.csv
│   ├── herren1_gegner_spieler.csv
│   ├── herren1_naechstes_spiel.csv
│   ├── herren1_spielbericht.md
│   └── damen1_...
│
├── 04_Zwischenergebnisse/       ← erzeugt das Programm, darf gelöscht werden
│   ├── cache/                      zwischengespeicherte FuPa-Antworten
│   ├── fupa_probe/                 Diagnoseausgaben von `probe-fupa`
│   └── lauf_20260803_101500/       Einzelseiten des jeweiligen Laufs
│
├── 05_Ausgaben/                 ← das Ergebnis
│   ├── 20260729_WaB_Druck.pdf
│   ├── 20260729_WaB_Druck_snapshot.json
│   └── Archiv/
│       └── Saison_2025_26/         alte Ausgaben
│
└── 99_Logs/
    └── stadionheft_2026-08.log
```

## Warum diese Aufteilung?

| Ordner | Begründung |
|---|---|
| `00_Konfiguration` getrennt | Nur hier braucht es Fachwissen. Der Ordner kann in DSM auf eine Admin-Gruppe beschränkt werden, ohne den Rest zu sperren. |
| `01_Vorlagen` schreibgeschützt | Diese Dateien sollen nicht versehentlich überschrieben werden. Im Docker-Compose ist der Mount deshalb `:ro`. |
| `02_Werbung` getrennt von `03_Eingaben` | Werbung wechselt einmal pro Saison, Eingaben alle zwei Wochen. Unterschiedliche Rhythmen, unterschiedliche Zuständige. |
| `04_Zwischenergebnisse` als eigener Ordner | Klar erkennbar wegwerfbar. Wenn die NAS voll wird, kann man diesen Ordner bedenkenlos leeren. |
| `05_Ausgaben` mit `Archiv/` | Die aktuelle Ausgabe liegt oben, alte wandern nach Saison sortiert ins Archiv. |
| Snapshot neben dem PDF | Wer die Datei findet, findet auch die Daten dazu – ohne sie suchen zu müssen. |

## Berechtigungen in DSM

| Gruppe | Ordner | Recht |
|---|---|---|
| `stadionheft-admin` | alles | Lesen/Schreiben |
| `stadionheft-redaktion` | `03_Eingaben`, `05_Ausgaben` | Lesen/Schreiben |
| `stadionheft-redaktion` | `01_Vorlagen`, `02_Werbung` | nur Lesen |
| `stadionheft-redaktion` | `00_Konfiguration` | kein Zugriff |

Für den Container empfiehlt sich ein eigener DSM-Benutzer `stadionheft` mit
Schreibrecht auf `03_`, `04_`, `05_` und `99_` sowie Leserecht auf `00_`, `01_`, `02_`.

## Einrichtung in drei Schritten

1. **Freigabe anlegen:** DSM → Systemsteuerung → Gemeinsamer Ordner → `Stadionheft`.
   Papierkorb aktivieren (rettet versehentlich gelöschte Werbedateien).
2. **Unterordner anlegen** wie oben. Am schnellsten per SSH:
   ```bash
   cd /volume1/Stadionheft
   mkdir -p 00_Konfiguration 01_Vorlagen/Original_InDesign 02_Werbung/einzeln \
            03_Eingaben 04_Zwischenergebnisse 05_Ausgaben/Archiv 99_Logs
   ```
3. **Container starten:** Container Manager → Projekt → `docker-compose.yml`
   aus diesem Repository verwenden. Die Volumes zeigen bereits auf die obige
   Struktur.

## Datensicherung

* **Unbedingt sichern:** `00_Konfiguration`, `01_Vorlagen`, `02_Werbung`,
  `05_Ausgaben`
* **Nicht nötig:** `04_Zwischenergebnisse` (wird jederzeit neu erzeugt)
* Empfehlung: Hyper Backup auf ein externes Ziel, wöchentlich.
  `00_Konfiguration` enthält mit `kontakte.yaml` personenbezogene Daten – das
  Backup-Ziel sollte verschlüsselt sein.
