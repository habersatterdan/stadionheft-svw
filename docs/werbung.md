# Werbung verwalten

Werbung ist reine Dateiarbeit. Kein Programm, keine Konfiguration – nur der
Ordner auf der NAS.

---

## Wo die Anzeigen liegen

```
Stadionheft/02_Werbung/
├── vorne/                    ← Werbeblock vor den Mannschaftsseiten
│   ├── 010_bayern-fcn-freundschaftsspiel__bis_2026-08-01.pdf
│   ├── 020_teamshop-jako.pdf
│   ├── 030_jako-katalog-1.pdf
│   ├── 031_jako-katalog-2.pdf
│   ├── 040_ullmann-universa.pdf
│   ├── 050_maedchenfussball.pdf
│   └── _pausiert/            ← ausgeblendete Anzeigen
├── hinten/                   ← Werbeblock nach den Mannschaftsseiten
├── zwischen/                 ← zwischen zwei Mannschaftsblöcken
├── kontaktlisten.pdf
├── impressum.pdf
└── ruecktitel.pdf
```

Der Ordner ist gleichzeitig deine Übersicht: Was hier liegt, ist im Heft.

---

## Die vier Handgriffe

| Was du willst | Was du tust |
|---|---|
| **Anzeige aufnehmen** | PDF in den Ordner legen |
| **Anzeige entfernen** | Datei löschen oder nach `_pausiert/` schieben |
| **Reihenfolge ändern** | Zahl am Dateianfang ändern |
| **Anzeige befristen** | `__bis_JJJJ-MM-TT` an den Namen anhängen |

Mehr ist es nicht. Beim nächsten Heft ist die Änderung drin.

---

## Reihenfolge

Sortiert wird nach Dateiname. Deshalb die Zahl am Anfang – am besten in
**Zehnerschritten**, dann lässt sich später etwas dazwischen schieben, ohne
alles umzubenennen:

```
010_teamshop.pdf
020_jako-katalog-1.pdf
021_jako-katalog-2.pdf     ← gehört zur vorigen, deshalb 021
030_ullmann.pdf
```

Soll eine neue Anzeige zwischen 020 und 030? Dann `025_neu.pdf`.

---

## Befristete Anzeigen

Ankündigungen für ein Spiel oder ein Fest sollen nach dem Termin verschwinden.
Dafür kommt das Datum in den Dateinamen:

```
010_sommerfest__bis_2026-07-15.pdf
020_hallenturnier__ab_2026-12-01__bis_2027-01-06.pdf
```

* `__bis_` – ab dem Tag danach fällt die Anzeige heraus
* `__ab_` – vorher erscheint sie noch nicht
* Beides zusammen ergibt ein Zeitfenster

Das Datum wird **immer** als `JJJJ-MM-TT` geschrieben, also Jahr zuerst.

!!! success "Das erspart das Daran-Denken"
    Niemand muss sich merken, eine abgelaufene Ankündigung herauszunehmen.
    Unter dem Ergebnis steht dann:

    > Anzeige „sommerfest" ist seit dem 15.07.2026 abgelaufen und wurde nicht
    > eingebunden.

!!! warning "Tippfehler im Datum"
    Wird das Datum nicht erkannt, bleibt die Anzeige sicherheitshalber im
    Heft – lieber eine Anzeige zu viel als eine fehlende Kundenanzeige.
    Deshalb nach dem Umbenennen einmal das Ergebnis prüfen.

---

## Anzeige vorübergehend aussetzen

Ein Kunde pausiert, kommt aber wieder? Datei in den Unterordner `_pausiert/`
schieben. Sie bleibt erhalten, ist aber nicht im Heft. Unter dem Ergebnis
erscheint ein Hinweis, wie viele Anzeigen dort liegen.

---

## Anforderungen an die PDF-Dateien

| | |
|---|---|
| Format | A5 hoch, 148 × 210 mm |
| Anschnitt | 3 mm, wenn die Anzeige randabfallend ist |
| Farbraum | CMYK für den Druck |
| Schriften | eingebettet |

!!! note "Anderes Format ist kein Beinbruch"
    Das Programm bringt alle Seiten auf ein gemeinsames Format und zentriert
    sie. Weicht eine Anzeige deutlich ab, erscheint ein Hinweis – dann bitte
    vor dem Druck kurz ansehen.

---

## Neue Anzeigen aus einem alten Heft holen

Liegt eine Anzeige nur als Teil eines fertigen Hefts vor, lässt sie sich
herausschneiden. Das macht ein Administrator mit:

```bash
stadionheft seiten-uebernehmen --aus altes_heft.pdf --seiten 4-11 \
    --einzeln --als vorne
```

Danach die Dateien sinnvoll benennen.
