# Ordner auf der NAS

Was wo liegt – und warum.

```
SVW/Stadionheft/
│
├── _Programm/                      Alles, was zum Programm gehört
│   │
│   ├── 00_Konfiguration/
│   │   └── config.yaml             Mannschaften, FuPa-Links, Ligen, Pfade
│   │
│   ├── 01_Vorlagen/                Vereinswappen, falls ihr ein besseres habt
│   │                               als das im Programm mitgelieferte
│   │
│   ├── 03_Eingaben/                CSV-Dateien als Reserve, falls FuPa
│   │                               einmal ausfällt (siehe csv-reserve.md)
│   │
│   ├── 04_Zwischenergebnisse/      Arbeitsordner. Legt das Programm selbst an.
│   │   ├── lauf_20261004_091205/   Einzelseiten eines Laufs
│   │   ├── cache/                  FuPa-Antworten der letzten 15 Minuten
│   │   └── fupa_probe/             Ergebnis von „FuPa-Verbindung prüfen"
│   │       ├── _bericht.txt        lesbar, hier zuerst reinschauen
│   │       └── _bericht.json       dasselbe für die Weiterverarbeitung
│   │
│   ├── 99_Logs/                    Protokolle, täglich eine Datei
│   │
│   └── docker/
│       └── docker-compose.yml      Die Datei für den Container Manager
│
└── Saison 26-27/
    └── 05_Ausgaben/                Die fertigen Dateien
        └── 2026-10-04_Spieltag/    Je Spieltag ein Ordner
            ├── 2026-10-04_Herren_1_gegen_SG_Alerheim.pdf
            ├── 2026-10-04_Herren_2_gegen_TSV_Binswangen.pdf
            ├── 2026-10-04_Spieltag_alle-Mannschaften.zip
            └── 2026-10-04_Spieltag_snapshot.json
```

---

## Was ihr anfassen müsst

| Ordner | Wann |
|---|---|
| `00_Konfiguration/` | Einmal am Anfang, danach bei Saisonwechsel |
| `05_Ausgaben/` | Nach jedem Lauf – hier holt ihr die Dateien ab |
| `03_Eingaben/` | Nur, wenn FuPa ausfällt |

Alles andere verwaltet das Programm selbst.

---

## Die einzelnen Dateien im Ausgabeordner

**Die PDFs** – das eigentliche Ergebnis, je Mannschaft eine Datei.

**Das ZIP** – dieselben PDFs plus eine `UEBERSICHT.txt`. Das ist die Datei,
die ihr weitergebt.

**Die Snapshot-Datei** – alle verwendeten Zahlen als JSON. Damit lassen sich
dieselben PDFs später exakt wieder erzeugen, ohne FuPa zu fragen:

```bash
docker exec stadionheft python -m stadionheft.cli erstellen \
  --snapshot "/app/daten/05_ausgaben/2026-10-04_Spieltag/2026-10-04_Spieltag_snapshot.json"
```

Praktisch, wenn jemand fragt: „Wie sah die Tabelle beim Heft vom 4. Oktober
noch mal aus?"

---

## Aufräumen

Der Ordner `04_Zwischenergebnisse/` wächst mit jedem Lauf. Er enthält nichts,
was gebraucht wird, sobald die PDFs fertig sind. Ein- oder zweimal pro Saison
kann der Inhalt gelöscht werden – das Programm legt ihn neu an.

Die Ausgabeordner dürfen bleiben: Eine komplette Saison sind etwa 50 MB.

---

## Saisonwechsel

Zwei Dinge:

1. In der `config.yaml` die `fupa_team_url` jeder Mannschaft auf die neue
   Saison umstellen (`...-2026-27` → `...-2027-28`) und `saison:` ändern.
2. In der `docker-compose.yml` den Ausgabeordner auf den neuen Saisonordner
   umstellen, dann Projekt neu erstellen.
