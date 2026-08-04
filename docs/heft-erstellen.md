# Heft erstellen

Fünf Schritte, etwa eine Minute Arbeit.

---

## 1. Seite öffnen

Im Browser die Adresse des Programms aufrufen – frag im Verein nach, wie sie
bei euch lautet. Typischerweise:

```
http://svwnas:8080
```

!!! tip "Lesezeichen setzen"
    Am Handy lohnt sich „Zum Home-Bildschirm hinzufügen" – dann liegt ein
    Symbol wie bei einer App auf dem Startbildschirm.

    * **iPhone (Safari)**: Teilen-Symbol → *Zum Home-Bildschirm*
    * **Android (Chrome)**: Drei-Punkte-Menü → *Zum Startbildschirm hinzufügen*

---

## 2. Mannschaften anhaken

Setz einen Haken bei jeder Mannschaft, die im Heft vorkommen soll.

Unter jedem Namen steht, welche Seiten dafür entstehen – zum Beispiel
*Trenner, Gegner, Tabelle, Torjäger, Spielerstatistik*. Wer das ändern möchte,
findet es in der [Konfiguration](INSTALLATION_NAS.md).

---

## 3. Angaben ergänzen (freiwillig)

| Feld | Wofür |
|---|---|
| **Spieltag** | Erscheint im Heft, z. B. „3. Spieltag" |
| **Titelseite** | Normalerweise *Automatisch* – dann kommt das nächste Heimspiel auf den Titel. Nur ändern, wenn ausdrücklich eine andere Mannschaft aufs Cover soll. |
| **Dein Name** | Wird nur im Protokoll vermerkt, damit man später weiß, wer das Heft erzeugt hat |

Bei **„Woher kommen die Daten?"** im Normalfall nichts ändern.

---

## 4. Auf „Stadionheft erstellen" klicken

Es dauert etwa fünf bis zehn Sekunden. Du siehst live mit, was gerade
passiert. Die Seite aktualisiert sich von selbst – einfach warten.

---

## 5. Ergebnis prüfen und herunterladen

Oben steht **„Stadionheft ist fertig"** mit Dateiname und Seitenzahl.

**Bitte immer die Hinweise darunter lesen.** Dort steht in Klartext, was
aufgefallen ist – zum Beispiel:

> Die Datei `herren2_torjaeger.csv` fehlt – die zugehörige Seite bleibt leer.

> Anzeige „bayern-fcn-freundschaftsspiel" ist seit dem 01.08.2026 abgelaufen
> und wurde nicht eingebunden.

Diese Hinweise sind **keine Fehler**. Das Heft ist fertig. Sie sagen dir nur,
was du vielleicht noch ergänzen willst, bevor es in den Druck geht.

Danach: **PDF herunterladen** – oder das Heft direkt auf der NAS unter
`05_Ausgaben` abholen.

---

## Vor dem Druck durchsehen

Ein kurzer Blick lohnt sich immer:

- [ ] Steht auf der Titelseite der **richtige Gegner** mit richtigem Datum?
- [ ] Ist das **Vorwort** aktuell oder noch das vom letzten Mal?
- [ ] Passt der **Gegnerkader** zum Gegner auf der Titelseite?
- [ ] Sind die **Tabellenzahlen** aktuell? (Steht als „Stand:" unter jeder Tabelle)
- [ ] Ist die **Seitenzahl** durch vier teilbar? Sonst mit der Druckerei klären.

---

## Ein früheres Heft noch einmal erzeugen

Neben jedem Heft liegt eine Datei `..._snapshot.json`. Darin stehen alle
Daten, aus denen das Heft entstanden ist.

Damit lässt sich dasselbe Heft jederzeit unverändert neu bauen – auch Wochen
später und ohne Internet. Praktisch, wenn im Vorwort ein Fehler war und alles
andere gleich bleiben soll. Sprich dafür einen Administrator an.
