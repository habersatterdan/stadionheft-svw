# FuPa-Anbindung

Tabelle, Torschützenliste und Spielerstatistik können automatisch von
fupa.net geholt werden – dann entfällt die Pflege der CSV-Dateien.

Diese Seite richtet sich an Administratoren.

---

## Ausgangslage: ehrlich betrachtet

**FuPa bietet keine offizielle, dokumentierte Schnittstelle an.** Die Website
lädt ihre Inhalte zwar über interne JSON-Aufrufe nach, aber diese sind:

* nicht dokumentiert
* nicht zugesichert
* jederzeit ohne Ankündigung änderbar

Deshalb ist das Programm so gebaut, dass ein Ausfall nichts blockiert:

* Alle Adressen stehen in der Konfiguration, nicht im Programmcode
* Die Feldzuordnung sucht nach mehreren möglichen Namen statt nach genau einem
* Bei einem Fehlschlag wird automatisch auf die CSV-Dateien umgeschaltet
* Es gibt ein Diagnosewerkzeug, das ohne Raten zeigt, was tatsächlich ankommt

---

## Verbindung prüfen

In der Fußzeile der Oberfläche steht **„FuPa-Verbindung prüfen"**. Die Seite
ruft die hinterlegten Adressen auf und zeigt je Adresse an, was zurückkommt.

Der Test **liest nur** – es wird nichts verändert. Er dauert etwa 20 Sekunden.

### Die drei möglichen Ergebnisse

| Ergebnis | Bedeutung |
|---|---|
| **Alle Abfragen haben funktioniert** | Der automatische Abruf lässt sich einschalten |
| **Ein Teil hat funktioniert** | Einzelne Adressen stimmen nicht – Rohantworten herunterladen und auswerten |
| **Keine hat funktioniert** | Adressen stimmen nicht oder FuPa ist nicht erreichbar |

Sobald mindestens eine Adresse geantwortet hat, gibt es einen Knopf
**„Ergebnis herunterladen (ZIP)"**. Darin stehen die Rohantworten – aus ihnen
lässt sich die genaue Feldzuordnung ablesen.

---

## Richtige Adressen selbst finden

Falls der Test nichts liefert, sind die hinterlegten Adressen veraltet. So
findest du die aktuellen:

1. FuPa-Teamseite im Browser öffnen, z. B.
   `https://www.fupa.net/team/sv-woernitzstein-berg-m1-2026-27`
2. Taste `F12` drücken (Entwicklerwerkzeuge)
3. Reiter **Netzwerk** wählen, Filter **Fetch/XHR**
4. Seite mit `F5` neu laden
5. In der Liste erscheinen die tatsächlich benutzten Adressen

Diese in `config.yaml` eintragen:

```yaml
datenquelle:
  fupa:
    basis_url: "https://api.fupa.net"
    endpunkte:
      team: "/v1/teams/{team_slug}"
      tabelle: "/v1/teams/{team_slug}/standing"
      spielplan: "/v1/teams/{team_slug}/matches"
      spieler: "/v1/teams/{team_slug}/players"
      torjaeger: "/v1/teams/{team_slug}/topscorers"
```

`{team_slug}` wird automatisch aus der `fupa_team_url` der Mannschaft
gebildet.

---

## Einschalten

Wenn der Test erfolgreich war, in `config.yaml`:

```yaml
datenquelle:
  modus: "api"
  fallback_modus: "manuell"
```

`fallback_modus` sorgt dafür, dass bei einem Ausfall automatisch auf die
CSV-Dateien umgeschaltet wird – das Heft entsteht dann trotzdem.

---

## Faires Verhalten

Das Programm verhält sich bewusst zurückhaltend:

* Sprechender User-Agent **mit Kontaktadresse** – kein anonymer Zugriff
* `robots.txt` wird gelesen und respektiert
* Konfigurierbare Pause zwischen Anfragen (Standard 1,5 Sekunden)
* Wiederholung mit wachsender Wartezeit bei Netzfehlern
* Zwischenspeicher: dieselbe Adresse wird innerhalb von zwei Stunden nicht
  erneut abgerufen
* Insgesamt rund ein Dutzend Abrufe alle zwei Wochen

Weist FuPa den Zugriff ab (403 oder 429), meldet das Programm das im Klartext
und schaltet um. Es versucht **nicht**, eine Sperre zu umgehen.

---

## Rechtliches in Kürze

Ausführlich im [Umsetzungskonzept](KONZEPT.md#10-rechtliche-und-technische-einschrankungen).
Die Kurzfassung:

* **Zahlen sind nicht urheberrechtlich geschützt.** Dass das Programm die
  Werte neu setzt statt Bildschirmfotos zu übernehmen, ist rechtlich sauberer
  als die bisherige Praxis.
* **Spielerfotos werden bewusst nicht übernommen.**
* **Quellenangabe** steht auf jeder Datenseite: „Quelle: fupa.net" mit
  Stand-Datum.
* **Nutzungsbedingungen** von FuPa untersagen automatisierte Abfragen
  möglicherweise. Das ist eine vertragliche Frage, keine strafrechtliche.

!!! tip "Der einfachste Weg aus der Grauzone"
    FuPa kurz anschreiben: „Wir sind der SV Wörnitzstein-Berg und möchten für
    unser Stadionheft alle zwei Wochen Tabelle und Statistik unserer eigenen
    Mannschaften automatisch abrufen – ist das in Ordnung?"

    Eine schriftliche Zusage klärt alles. Regionalportale stehen
    Vereinsprojekten erfahrungsgemäß offen gegenüber.

---

## Alternativen

| Weg | Bewertung |
|---|---|
| **Offizieller Export von FuPa** | Beste Lösung, falls es einen Vereinszugang gibt – bitte prüfen |
| **BFV-Daten** | Die Originalquelle. Prüfenswert, ob der Verband Vereinen Zugang bietet |
| **Manuelle CSV-Eingabe** | Funktioniert immer, rechtlich unbedenklich, etwa 10 Minuten je Mannschaft |
| **Copy-Paste nach Excel** | Praktischer Mittelweg, deutlich schneller als Abtippen |
