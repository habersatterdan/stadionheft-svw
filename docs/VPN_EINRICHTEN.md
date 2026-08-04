# VPN einrichten – Zugriff von unterwegs

Mit VPN verhält sich dein Handy oder Laptop so, als wärst du zu Hause im
Vereinsnetz. Danach funktioniert `http://svwnas:8080` von überall – und alles
andere auf der NAS gleich mit.

**Das ist der sichere Weg.** Nichts wird offen ins Internet gestellt.

Dauer: etwa 20 Minuten, danach pro Person 5 Minuten.

---

## Voraussetzung: Erreichbarkeit von außen

Ein VPN-Server muss von außen ansprechbar sein. Prüfe zuerst, was ihr habt.

### Habt ihr eine feste IP oder DynDNS?

Die meisten Privatanschlüsse bekommen alle 24 Stunden eine neue IP-Adresse.
Deshalb braucht es einen Namen, der immer auf die aktuelle zeigt.

Synology bringt das kostenlos mit:

**Systemsteuerung → Externer Zugriff → DDNS → Hinzufügen**

| Feld | Eingabe |
|---|---|
| Dienstanbieter | `Synology` |
| Hostname | z. B. `svwoernitzstein` → ergibt `svwoernitzstein.synology.me` |
| E-Mail / Konto | euer Synology-Konto (`sv.woernitzsteinberg@gmx.de`) |

Nach dem Speichern sollte der Status **„Normal"** sein.

!!! warning "Kabelanschluss? Erst prüfen!"
    Bei Vodafone/Kabel-Anschlüssen gibt es oft nur **DS-Lite** – dann seid ihr
    von außen gar nicht direkt erreichbar, und VPN funktioniert nicht ohne
    Weiteres.

    **Test:** Bei [wieistmeineip.de](https://www.wieistmeineip.de) die
    öffentliche IP ansehen und mit der WAN-IP im Router vergleichen. Sind sie
    verschieden, habt ihr DS-Lite.

    In dem Fall: beim Anbieter eine „echte IPv4-Adresse" beantragen (bei
    vielen kostenlos auf Anfrage) – oder auf den Reverse-Proxy-Weg ausweichen
    (siehe unten).

---

## Schritt 1: VPN Server installieren

**Paket-Zentrum** → nach `VPN Server` suchen → **Installieren**

---

## Schritt 2: WireGuard aktivieren

**VPN Server** öffnen → links **WireGuard** → Haken bei
**WireGuard-VPN-Server aktivieren**

| Einstellung | Wert |
|---|---|
| Port | `51820` (Standard, so lassen) |
| Dynamische IP-Adresse | `10.6.0.0/24` (Standard) |

**Übernehmen** klicken.

??? note "Warum WireGuard und nicht OpenVPN?"
    WireGuard ist deutlich schneller, verbraucht weniger Akku und die
    Einrichtung am Handy geht per QR-Code. OpenVPN funktioniert auch, ist aber
    umständlicher.

---

## Schritt 3: Port im Router freigeben

Das ist die **einzige** Freigabe, die ihr braucht – und sie ist ungefährlich,
weil dahinter nur der verschlüsselte VPN-Tunnel liegt.

**FRITZ!Box:** Internet → Freigaben → Portfreigaben → **Gerät für Freigaben
hinzufügen** → SVWNAS auswählen → **Neue Freigabe**

| Feld | Wert |
|---|---|
| Anwendung | Andere Anwendung |
| Bezeichnung | `WireGuard` |
| Protokoll | **UDP** |
| Port | `51820` bis `51820` |
| An Port | `51820` |

!!! danger "Nur diesen einen Port"
    Port **8080** (die App) und Port **22** (SSH) bleiben **geschlossen**.
    Die erreichst du künftig durch den VPN-Tunnel.

---

## Schritt 4: Profil für eine Person anlegen

**VPN Server → WireGuard → Peer hinzufügen**

* Name: z. B. `daniel-handy` – für **jedes Gerät ein eigenes Profil**
* **Erstellen**

Danach erscheint ein **QR-Code** und ein Download-Knopf für die
Konfigurationsdatei.

!!! tip "Ein Profil je Gerät"
    Nicht dasselbe Profil auf mehreren Geräten benutzen. So kann man den
    Zugang einer einzelnen Person später sperren, ohne alle anderen zu stören.

---

## Schritt 5: Gerät verbinden

### Handy (iOS und Android)

1. App **WireGuard** installieren (kostenlos, vom WireGuard-Entwicklerteam)
2. In der App auf **+** → **Aus QR-Code erstellen**
3. Den QR-Code aus DSM abfotografieren
4. Namen vergeben, speichern
5. Schalter umlegen – verbunden

### Windows / Fedora / macOS

1. WireGuard von [wireguard.com/install](https://www.wireguard.com/install/)
   installieren (unter Fedora: `sudo dnf install wireguard-tools`)
2. In DSM die Konfigurationsdatei herunterladen (`.conf`)
3. In WireGuard **Tunnel importieren** → Datei auswählen
4. **Aktivieren**

---

## Schritt 6: Testen

**Wichtig: Zum Testen das WLAN ausschalten** und über Mobilfunk gehen – sonst
bist du ja ohnehin im Heimnetz und merkst nicht, ob das VPN wirkt.

1. VPN einschalten
2. Im Browser `http://svwnas:8080` öffnen

Klappt der Name nicht, die interne IP nehmen, z. B.
`http://192.168.178.42:8080`.

!!! tip "Name funktioniert nicht?"
    Über VPN wird der NAS-Name nicht immer aufgelöst. Zwei Möglichkeiten:

    * Einfach die interne IP als Lesezeichen speichern
    * Oder in DSM unter **VPN Server → Allgemeine Einstellungen** die NAS als
      DNS-Server für VPN-Clients eintragen

---

## Alltag

VPN einschalten → App benutzen → VPN wieder ausschalten.

Auf dem Handy sind das zwei Fingertipps. Wer die App oft nutzt, kann
„Bei Bedarf verbinden" aktivieren – dann geht das VPN automatisch an.

---

## Wenn es nicht klappt

| Problem | Ursache / Lösung |
|---|---|
| Verbindung kommt nicht zustande | Portfreigabe prüfen: **UDP** 51820, nicht TCP |
| Verbunden, aber NAS nicht erreichbar | Interne IP statt Name probieren |
| Klappt im WLAN, nicht per Mobilfunk | DS-Lite-Problem – siehe Kasten oben |
| DDNS zeigt „Fehler" | Hostname schon vergeben, anderen wählen |
| Nach Router-Neustart tot | DDNS-Status in DSM prüfen |

---

## Alternative ohne VPN

Wenn VPN nicht geht (z. B. wegen DS-Lite), bleibt der Reverse Proxy:

1. **DSM → Anmeldeportal → Reverse Proxy** → Regel von
   `stadionheft.svwoernitzstein.synology.me` (HTTPS, 443) auf
   `localhost:8080`
2. **Zertifikat** über Let's Encrypt in DSM anfordern
3. **Passwortschutz einschalten** – in `config.yaml`:
   ```yaml
   zugang:
     passwortschutz: true
     benutzername: "svw"
     passwort_umgebungsvariable: "STADIONHEFT_PASSWORT"
   ```
   Das Passwort im Container Manager unter **Umgebung** setzen.
4. Port **443** im Router freigeben

!!! warning "Punkt 3 ist nicht optional"
    Ohne Passwortschutz stünde die App offen im Internet. Der Schutz wirkt
    nur zusammen mit HTTPS aus Punkt 2 – über eine unverschlüsselte
    Verbindung wären die Zugangsdaten mitlesbar.
