# Installation auf der Synology NAS

Ziel: Jede Person im Verein öffnet einen Link im Browser – am Rechner **oder
am Handy** – und kann ein Stadionheft erstellen. Niemand installiert etwas.

Zeitaufwand: etwa eine halbe Stunde beim ersten Mal.

---

## Warum das die richtige Lösung ist, wenn ihr verschiedene Systeme nutzt

Das Programm läuft **genau einmal** – im Container auf der NAS. Alle anderen
Geräte brauchen nur einen Browser. Kein Python, keine Installation, keine
Unterschiede zwischen den Systemen.

| Gerät | Was installiert werden muss | Was geht |
|---|---|---|
| **Synology NAS** | Container Manager (einmalig) | Hier läuft alles |
| **Fedora / Linux** | nichts | Heft erstellen, Dateien pflegen |
| **Windows** | nichts | Heft erstellen, Dateien pflegen |
| **macOS** | nichts | Heft erstellen, Dateien pflegen |
| **iPhone / iPad** | nichts (optional: DS file) | Heft erstellen, PDF ansehen |
| **Android** | nichts (optional: DS file) | Heft erstellen, PDF ansehen |

Weil die Werbedateien, die Eingaben und die fertigen Hefte **ohnehin schon auf
der NAS liegen**, entfällt jedes Kopieren: Der Container greift direkt auf
dieselben Ordner zu, die ihr in der Dateistation seht. Legt jemand von seinem
Fedora-Rechner eine neue Werbeanzeige nach `02_Werbung/vorne/`, ist sie beim
nächsten Heft automatisch dabei – egal, wer es erstellt und womit.

**Nur für die einmalige Einrichtung** braucht es einen Rechner mit Browser
(Fedora, Windows oder macOS – egal welcher). DSM lässt sich am Handy zwar
bedienen, der Container Manager ist dort aber unangenehm klein.

### Wer pflegt welche Dateien womit?

| Aufgabe | Fedora / Windows / macOS | iOS / Android |
|---|---|---|
| Heft erstellen | Browser | Browser |
| Werbung austauschen | Dateistation im Browser, Synology Drive oder Netzlaufwerk | DS file |
| Vorwort schreiben | Text-Editor der Dateistation oder lokal | DS file, Notiz-App |
| CSV-Zahlen pflegen | Excel, LibreOffice Calc, Numbers | eher unpraktisch |
| Titelbild hochladen | Dateistation | DS file (direkt aus der Fotos-App) |

CSV-Dateien sind ein reines Textformat – LibreOffice Calc unter Fedora, Excel
unter Windows und Numbers unter macOS können sie alle. Wichtig ist nur, beim
Speichern **UTF-8** zu wählen; das Programm erkennt Semikolon und Komma
selbst.

---

## Voraussetzungen

| | |
|---|---|
| DSM-Version | **7.2 oder neuer** empfohlen (siehe Kasten unten) |
| Paket | **Container Manager** – heißt bis DSM 7.1 noch „Docker" |
| NAS-Modell | Muss Docker unterstützen – Modelle mit Intel/AMD-CPU (z. B. DS220+, DS720+, DS920+, DS923+). Reine ARM-Einsteigermodelle wie DS120j können es **nicht**. |
| Arbeitsspeicher | 2 GB genügen |
| Speicherplatz | ca. 700 MB für das Abbild |

**Modell prüfen:** DSM → Systemsteuerung → Info-Center. Steht dort bei
Modell ein „+" oder „play", passt es meistens. Im Zweifel: Paket-Zentrum
öffnen und nach „Container Manager" bzw. „Docker" suchen – wird eines davon
angeboten, geht es.

> ### Wichtig bei DSM 7.1 und älter
>
> Die bequeme Einrichtung über **Projekt → docker-compose.yml einfügen** gibt
> es erst ab **DSM 7.2**. Dort wurde das alte Paket „Docker" durch den
> „Container Manager" ersetzt, der als neue Funktion Docker Compose mitbringt.
>
> Auf DSM 7.1 heißt das Paket noch „Docker" und hat **keine Projekt-Ansicht**.
> Zwei Möglichkeiten:
>
> 1. **DSM auf 7.2+ aktualisieren** (Systemsteuerung → Aktualisieren und
>    Wiederherstellen). Danach steht der Container Manager bereit – das ist
>    der einfachere Weg.
> 2. **Über SSH einrichten**: Terminal in DSM aktivieren, dann
>    `sudo docker compose up -d --build` im Projektordner ausführen.
>
> Vor einem DSM-Update: Datensicherung prüfen und das Update nicht kurz vor
> einem Spieltag einspielen.

---

## Schritt 1: Container Manager installieren

DSM öffnen → **Paket-Zentrum** → nach `Container Manager` suchen →
**Installieren**.

---

## Schritt 2: Ordner anlegen

**Systemsteuerung → Gemeinsamer Ordner → Erstellen**

* Name: `Stadionheft`
* Papierkorb aktivieren (rettet versehentlich gelöschte Werbedateien)

Dann in der **Dateistation** innerhalb von `Stadionheft` diese Unterordner
anlegen:

```
00_Konfiguration
01_Vorlagen
02_Werbung
03_Eingaben
04_Zwischenergebnisse
05_Ausgaben
99_Logs
```

Wer SSH mag, geht schneller:

```bash
cd /volume1/Stadionheft
mkdir -p 00_Konfiguration 01_Vorlagen 02_Werbung 03_Eingaben \
         04_Zwischenergebnisse 05_Ausgaben/Archiv 99_Logs
```

Hintergrund zu den Ordnern: [NAS_ORDNERSTRUKTUR.md](NAS_ORDNERSTRUKTUR.md)

---

## Schritt 3: Konfiguration hinterlegen

**Wichtig – sonst startet die App im Einrichtungsmodus.**

Aus diesem Projekt die drei Beispieldateien nehmen, umbenennen und per
Dateistation nach `Stadionheft/00_Konfiguration/` hochladen:

| aus dem Projekt | auf der NAS |
|---|---|
| `config/config.example.yaml` | `00_Konfiguration/config.yaml` |
| `config/heftplan.example.yaml` | `00_Konfiguration/heftplan.yaml` |
| `config/kontakte.example.yaml` | `00_Konfiguration/kontakte.yaml` |

Danach `config.yaml` bearbeiten (Text-Editor in der Dateistation genügt) und
mindestens diese Werte setzen:

```yaml
nas:
  aktiv: true
  modus: "mount"
  mount:
    zielordner: "/nas/Stadionheft/05_Ausgaben"
```

Die mit `TODO` markierten Ligen kannst du später ergänzen – die App läuft
auch so.

---

## Schritt 4: Projekt anlegen

**Container Manager → Projekt → Erstellen**

* Projektname: `stadionheft`
* Pfad: `/volume1/Stadionheft` (oder ein eigener Ordner `/volume1/docker/stadionheft`)
* Quelle: **Docker-compose.yml erstellen** und den Inhalt der Datei
  `docker-compose.yml` aus diesem Projekt einfügen

Alternativ – sauberer, weil das Abbild direkt aus dem Quellcode gebaut wird:
per SSH auf die NAS und

```bash
cd /volume1/docker
git clone -b main https://github.com/habersatterdan/stadionheft-svw.git stadionheft
cd stadionheft
docker compose up -d --build
```

Der erste Build dauert 5–15 Minuten (es werden Pango, Cairo und die
Schriften installiert). Danach startet der Container in Sekunden.

---

## Schritt 5: Aufrufen

Im Browser:

```
http://<name-oder-ip-der-nas>:8080
```

Also z. B. `http://diskstation:8080` oder `http://192.168.178.42:8080`.

Die IP findest du in DSM unter Systemsteuerung → Netzwerk → Netzwerkschnittstelle.

**Tipp:** Der NAS eine feste IP geben (im Router als DHCP-Reservierung),
damit sich die Adresse nie ändert.

---

## FuPa-Abruf einrichten – ohne Kommandozeile

In der Fußzeile der Oberfläche steht **„FuPa-Verbindung prüfen"**. Diese Seite
testet die hinterlegten Adressen und zeigt an, ob der automatische Abruf von
Tabelle und Statistiken funktioniert.

Das läuft im Container auf der NAS – also von jedem Gerät aus, auch vom Handy.
Ein Terminal wird dafür nicht gebraucht.

---

## Vom Handy aus benutzen

Die Oberfläche ist für kleine Bildschirme ausgelegt – getestet bei 320, 360
und 390 Pixel Breite, kein seitliches Scrollen, Knöpfe in Daumengröße.

### Im WLAN zu Hause / im Vereinsheim

Nichts weiter nötig. Im Handy-Browser dieselbe Adresse öffnen:
`http://192.168.178.42:8080`

**Als App auf den Startbildschirm legen:**

* *iPhone (Safari)*: Teilen-Symbol → „Zum Home-Bildschirm"
* *Android (Chrome)*: Drei-Punkte-Menü → „Zum Startbildschirm hinzufügen"

Danach sieht es aus wie eine echte App – ein Symbol antippen, fertig.

### Von unterwegs

Drei Wege, vom sichersten zum bequemsten:

| Weg | Sicherheit | Aufwand |
|---|---|---|
| **VPN** | am besten | mittel |
| **Reverse Proxy + Passwortschutz** | gut | mittel |
| **QuickConnect** | funktioniert hier nicht | – |

#### VPN – die Empfehlung

Das Gerät verbindet sich ins Vereinsnetz, danach funktioniert die lokale
Adresse wie zu Hause – und zwar für alles auf der NAS, nicht nur für das
Stadionheft. Die Anwendung steht dabei zu keinem Zeitpunkt offen im Internet.

Welcher Weg passt, hängt am Router-Zugriff:

* **ohne Router-Zugriff** → Tailscale (keine Portfreigabe nötig)
* **mit Router-Zugriff** → OpenVPN aus dem Paket „VPN Server"

Ausführlich: [Zugriff von unterwegs](VPN_EINRICHTEN.md)

!!! note "WireGuard gibt es im VPN Server von Synology nicht"
    Das Paket bietet PPTP, OpenVPN und L2TP/IPSec. PPTP bitte nicht
    verwenden – die Verschlüsselung gilt als gebrochen.

#### Reverse Proxy – wenn es ohne VPN gehen soll

DSM → Anmeldeportal → **Reverse Proxy**: Regel von
`stadionheft.eure-domain.de` (HTTPS, 443) auf `localhost:8080`. Dazu ein
Zertifikat über Let's Encrypt.

!!! danger "Dann unbedingt den Passwortschutz einschalten"
    Sonst kann jeder, der die Adresse kennt, Hefte erzeugen und eure Daten
    einsehen. In `config.yaml`:

    ```yaml
    zugang:
      passwortschutz: true
      benutzername: "svw"
      passwort_umgebungsvariable: "STADIONHEFT_PASSWORT"
    ```

    Das Passwort selbst wird im Container Manager unter **Umgebung** gesetzt –
    nicht in die Konfigurationsdatei schreiben.

    Der Schutz wirkt nur zusammen mit HTTPS. Über eine unverschlüsselte
    Verbindung wären die Zugangsdaten mitlesbar.

#### QuickConnect

Leitet nur DSM-eigene Dienste weiter, **nicht** die Ports eigener Container.
Für das Stadionheft also kein gangbarer Weg – auch wenn die QuickConnect-ID
eingerichtet ist.

---

## Web Station? Nein.

Naheliegende Frage, aber **Web Station kann das nicht**. Sie liefert statische
Seiten und PHP aus. Das Stadionheft braucht Python mit WeasyPrint für den
PDF-Satz – das läuft nur im Container.

Web Station und Container Manager schließen sich nicht aus; sie sind für
verschiedene Dinge da.

---

## Wenn etwas nicht klappt

| Symptom | Ursache / Lösung |
|---|---|
| Seite lädt nicht | Container Manager → Container → läuft `stadionheft`? Sonst starten und ins Protokoll sehen. |
| „Einrichtung nicht abgeschlossen" im Browser | `config.yaml` fehlt in `00_Konfiguration`. Schritt 3 nachholen, dann Container neu starten. |
| Container startet und stoppt sofort | Protokoll im Container Manager ansehen. Meist ein YAML-Fehler in `config.yaml` (Einrückung!). |
| Build schlägt fehl | Kein Internet auf der NAS oder zu wenig Speicherplatz. |
| Heft wird erzeugt, liegt aber nicht in `05_Ausgaben` | In `config.yaml` prüfen: `nas.aktiv: true` und `zielordner: "/nas/Stadionheft/05_Ausgaben"`. Der Pfad ist der **Pfad im Container**, nicht der DSM-Pfad. |
| „NAS nicht erreichbar" | Volume-Zuordnung in `docker-compose.yml` prüfen. |

Protokolle liegen auf der NAS unter `Stadionheft/99_Logs/`.

---

## Aktualisieren

Bei einer neuen Version:

```bash
cd /volume1/docker/stadionheft
git pull
docker compose up -d --build
```

Konfiguration und Daten bleiben erhalten – sie liegen außerhalb des
Containers in den gemounteten Ordnern.

---

## Sicherung

Hyper Backup einrichten für:

* `Stadionheft/00_Konfiguration` – **wichtig**, enthält eure ganze Einrichtung
* `Stadionheft/01_Vorlagen` und `02_Werbung` – schwer wiederzubeschaffen
* `Stadionheft/05_Ausgaben` – die fertigen Hefte

`04_Zwischenergebnisse` braucht keine Sicherung.

> `00_Konfiguration/kontakte.yaml` enthält personenbezogene Daten
> (Telefonnummern, private E-Mail-Adressen). Das Backup-Ziel sollte
> verschlüsselt sein.
