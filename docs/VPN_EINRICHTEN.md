# Zugriff von unterwegs

Ziel: `http://svwnas:8080` funktioniert auch, wenn du nicht im Vereinsnetz
bist.

---

## Zuerst die entscheidende Frage: Kommst du an den Router?

Davon hängt alles ab.

| Situation | Weg |
|---|---|
| **Kein Zugriff auf den Router** | → [Tailscale](#tailscale-ohne-router-zugriff) |
| Router-Zugriff vorhanden | → [OpenVPN](#openvpn-mit-router-zugriff) |

!!! warning "Der VPN Server von Synology reicht allein nicht"
    Das Paket **VPN Server** bietet PPTP, OpenVPN und L2TP/IPSec.
    **WireGuard ist nicht dabei** – anders als oft behauptet.

    Wichtiger noch: **Alle drei brauchen eine Portfreigabe im Router.**
    Ohne Zugriff auf den Router nützt das Einrichten in DSM nichts – der
    Dienst läuft dann zwar, ist aber von außen nicht erreichbar.

---

## Tailscale – ohne Router-Zugriff

Tailscale baut die Verbindung von innen nach außen auf. **Keine
Portfreigabe, keine DynDNS, kein Router-Zugriff nötig** – es funktioniert
sogar hinter DS-Lite.

Alle Geräte, die mit demselben Konto angemeldet sind, sehen sich
gegenseitig, als wären sie im selben Netz.

### Einrichten

1. **Konto anlegen** auf [tailscale.com](https://tailscale.com) – kostenlos
   für private Nutzung, Anmeldung mit Google- oder GitHub-Konto
2. **Paket für die NAS holen**: Auf tailscale.com unter *Download →
   Synology* das Paket für die passende Architektur herunterladen.
   Die DS720+ hat einen Intel Celeron J4125, also **x86_64 / Apollolake**.
3. **In DSM installieren**: Paket-Zentrum → **Manuelle Installation** →
   die heruntergeladene `.spk` auswählen
4. **Tailscale öffnen** (erscheint im Hauptmenü) → **Log in** → der
   angezeigte Link führt zur Anmeldung im Browser
5. Nach der Anmeldung erscheint die NAS in der Tailscale-Übersicht mit
   einer eigenen Adresse, z. B. `100.101.102.103`

### Auf dem Handy und am Rechner

1. Tailscale-App installieren (App Store, Play Store, oder
   [tailscale.com/download](https://tailscale.com/download))
2. Mit **demselben Konto** anmelden
3. Fertig – die NAS ist erreichbar

### Aufrufen

```
http://100.101.102.103:8080
```

Die Adresse steht in der Tailscale-Übersicht. Mit aktiviertem *MagicDNS*
geht auch `http://svwnas:8080`.

!!! tip "Warum das ohne Router-Zugriff geht"
    Beide Geräte melden sich bei einem Vermittlungsdienst und bauen die
    Verbindung dann direkt zueinander auf – so wie ein Videoanruf
    funktioniert, ohne dass jemand Ports freigibt.

!!! note "Nicht selbst verifiziert"
    Diese Anleitung beruht auf der Dokumentation von Tailscale, nicht auf
    einem Test auf eurer NAS. Falls etwas abweicht, sag Bescheid.

---

## OpenVPN – mit Router-Zugriff

Nur sinnvoll, wenn jemand an den Router kommt.

### Voraussetzung: DynDNS

Privatanschlüsse bekommen regelmäßig eine neue IP-Adresse. Deshalb braucht
es einen festen Namen:

**Systemsteuerung → Externer Zugriff → DDNS → Hinzufügen**

| Feld | Eingabe |
|---|---|
| Dienstanbieter | `Synology` |
| Hostname | z. B. `svwoernitzstein` → `svwoernitzstein.synology.me` |
| Konto | euer Synology-Konto |

Status muss danach **„Normal"** sein.

### VPN Server einrichten

**VPN Server → OpenVPN** – die Voreinstellungen passen:

| Einstellung | Wert |
|---|---|
| Port | `1194` |
| Protokoll | `UDP` |
| Verschlüsselung | `AES-256-CBC` oder `Auto` |
| Authentifizierung | `SHA512` |
| **Clients Zugriff auf das LAN des Servers erlauben** | **anhaken** |

Der letzte Punkt ist wichtig, sonst erreichst du nur die NAS selbst.

**Übernehmen** → dann **Konfiguration exportieren** → du bekommst eine
ZIP-Datei mit der `.ovpn`-Datei.

!!! danger "PPTP nicht verwenden"
    PPTP steht in derselben Liste, gilt aber seit Jahren als gebrochen. Die
    Verschlüsselung lässt sich mit vertretbarem Aufwand knacken. Finger weg.

### Berechtigung setzen

**VPN Server → Privileg** → bei den Personen, die VPN nutzen dürfen, den
Haken bei **OpenVPN** setzen.

### Port im Router freigeben

**UDP 1194** auf die NAS weiterleiten. Das ist die einzige nötige Freigabe.

!!! danger "Nur diesen Port"
    Port **8080** (die App) und Port **22** (SSH) bleiben **geschlossen**.

### Client einrichten

1. **OpenVPN Connect** installieren (Handy: App Store / Play Store;
   Rechner: [openvpn.net](https://openvpn.net/client/))
2. Die `.ovpn`-Datei importieren
3. In der Datei die Zeile `remote YOUR_SERVER_IP 1194` auf euren
   DynDNS-Namen ändern, also z. B.
   `remote svwoernitzstein.synology.me 1194`
4. Mit DSM-Benutzername und -Passwort verbinden

---

## Testen

**Wichtig: WLAN ausschalten** und über Mobilfunk gehen – sonst bist du
ohnehin im Heimnetz und merkst nicht, ob der Tunnel wirkt.

1. VPN bzw. Tailscale einschalten
2. `http://svwnas:8080` öffnen – oder die IP-Adresse

---

## Wenn es nicht klappt

| Problem | Ursache / Lösung |
|---|---|
| OpenVPN verbindet nicht | Portfreigabe prüfen: **UDP** 1194, nicht TCP |
| Verbunden, NAS nicht erreichbar | „Clients Zugriff auf das LAN erlauben" anhaken |
| Name wird nicht gefunden | Interne IP statt Name verwenden |
| Klappt im WLAN, nicht mobil | Anschluss ohne öffentliche IPv4 (DS-Lite) – dann Tailscale nehmen |
| Tailscale: NAS erscheint nicht | Beide Geräte mit demselben Konto angemeldet? |

---

## Und ohne alles?

Solange kein Tunnel steht, ist die App von außen nicht erreichbar – das ist
so gewollt, sie hat keine Anmeldung.

Du kannst sie trotzdem **prüfen**, ohne sie zu öffnen: siehe
[Erste Einrichtung → Ohne Weboberfläche arbeiten](ERSTE_EINRICHTUNG.md#ohne-weboberflache-arbeiten).
