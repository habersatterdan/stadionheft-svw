"""Daten aus einer normalen Webseite gewinnen.

Moderne Websites bauen ihre Seiten im Browser zusammen. Die Daten dafuer
liegen aber meist schon **im HTML** -- als JSON in einem ``<script>``-Block.
Bekannte Varianten:

* ``<script id="__NEXT_DATA__" type="application/json">`` (Next.js)
* ``<script type="application/json">`` (allgemein)
* ``window.__NUXT__ = {...}`` (Nuxt)
* ``self.__next_f.push([1,"..."])`` (neuere Next.js-Versionen)

Dieses Modul holt jedes JSON heraus, das es findet. Was davon eine Tabelle
oder eine Torschuetzenliste ist, entscheidet danach
:mod:`stadionheft.sources.erkennung` anhand der Struktur.

Der Vorteil gegenueber dem Raten von API-Adressen: Die **oeffentliche
Teamseite** hat eine stabile, bekannte Adresse -- sie steht in der
Konfiguration. Es muss nichts erraten werden.

Bewusst kein HTML-Parser als Abhaengigkeit: Gesucht werden nur
``<script>``-Bloecke, dafuer genuegen regulaere Ausdruecke. Ein zusaetzliches
Paket auf der NAS waere die Sache nicht wert.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterator

from ..logging_setup import logger

_SCRIPT = re.compile(
    r"<script\b[^>]*>(.*?)</script>", re.IGNORECASE | re.DOTALL)
_TYP_JSON = re.compile(r'type\s*=\s*["\']application/(?:ld\+)?json["\']',
                       re.IGNORECASE)
_SCRIPT_MIT_ATTRIBUTEN = re.compile(
    r"<script\b([^>]*)>(.*?)</script>", re.IGNORECASE | re.DOTALL)
_ZUWEISUNG = re.compile(
    r"(?:window|self)\.__[A-Z_]+__\s*=\s*(\{.*?\})\s*;?\s*$",
    re.DOTALL | re.MULTILINE)


def _json_oder_nichts(text: str) -> Any | None:
    text = text.strip()
    if not text or text[0] not in "[{":
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


#: Zusammengehoerige Klammern. Listen zaehlen mit, weil neuere
#: Next.js-Versionen ihre Daten als ``self.__next_f.push([1,"..."])``
#: ausliefern -- die Nutzlast steckt dort in einem Array, nicht in einem
#: Objekt.
_KLAMMERN = {"{": "}", "[": "]"}


def _objekte_im_text(text: str, mindestlaenge: int = 60) -> Iterator[Any]:
    """Sucht in freiem JavaScript nach vollstaendigen JSON-Werten.

    Geht die Klammern durch und gibt jeden ausbalancierten Block aus, der sich
    als JSON lesen laesst. Anfuehrungszeichen und Escapes werden dabei
    beruecksichtigt, damit eine Klammer im Text nicht mitzaehlt.
    """
    tiefe = 0
    start = -1
    auf = ""
    im_text = False
    escaped = False

    for stelle, zeichen in enumerate(text):
        if im_text:
            if escaped:
                escaped = False
            elif zeichen == "\\":
                escaped = True
            elif zeichen == '"':
                im_text = False
            continue
        if zeichen == '"':
            im_text = True
        elif zeichen in _KLAMMERN and (tiefe == 0 or zeichen == auf):
            if tiefe == 0:
                start, auf = stelle, zeichen
            tiefe += 1
        elif auf and zeichen == _KLAMMERN[auf]:
            if tiefe > 0:
                tiefe -= 1
                if tiefe == 0 and start >= 0:
                    block = text[start:stelle + 1]
                    if len(block) >= mindestlaenge:
                        gelesen = _json_oder_nichts(block)
                        if gelesen is not None:
                            yield gelesen
                    start, auf = -1, ""


def json_aus_html(html: str) -> list[Any]:
    """Alle JSON-Daten, die in einer HTML-Seite eingebettet sind."""
    if not html:
        return []

    gefunden: list[Any] = []

    # 1. Saubere JSON-Bloecke (Next.js, JSON-LD, allgemein)
    for attribute, inhalt in _SCRIPT_MIT_ATTRIBUTEN.findall(html):
        if _TYP_JSON.search(attribute) or "__NEXT_DATA__" in attribute:
            gelesen = _json_oder_nichts(inhalt)
            if gelesen is not None:
                gefunden.append(gelesen)

    # 2. Zuweisungen wie window.__NUXT__ = {...}
    for treffer in _ZUWEISUNG.findall(html):
        gelesen = _json_oder_nichts(treffer)
        if gelesen is not None:
            gefunden.append(gelesen)

    # 3. Jedes grosse JSON in einem Skriptblock, auch in freiem JavaScript.
    #
    #    Das lief frueher nur, wenn oben gar nichts kam. Das war ein Fehler:
    #    Eine Seite kann einen winzigen JSON-LD-Block enthalten (Adresse des
    #    Vereins o. Ae.) und die eigentlichen Spieldaten trotzdem in freiem
    #    JavaScript fuehren. Dann galt die Seite als ausgewertet, obwohl das
    #    Wesentliche nie angesehen wurde. Der Durchlauf kostet nur Rechenzeit.
    for inhalt in _SCRIPT.findall(html):
        if len(inhalt) < 200:
            continue
        for gelesen in _objekte_im_text(inhalt):
            gefunden.append(gelesen)

    # 4. In Next.js-Streams stecken die Daten als JSON *in einer Zeichenkette*.
    #    Solche Zeichenketten noch einmal aufloesen.
    ausgepackt: list[Any] = []
    for eintrag in gefunden:
        ausgepackt.append(eintrag)
        ausgepackt.extend(_zeichenketten_aufloesen(eintrag))

    logger().debug("Aus HTML gewonnen: %d JSON-Blöcke", len(ausgepackt))
    return ausgepackt


#: Next.js-Streams stellen ihren Nutzdaten eine Kennung voran:
#: ``3:["$","div",...]``. Ohne das Abschneiden ist der Rest kein gueltiges JSON.
_STROM_PRAEFIX = re.compile(r'^\s*[0-9a-zA-Z]{1,4}:\s*(?=[\[{])')


def _zeichenketten_aufloesen(knoten: Any, tiefe: int = 0) -> list[Any]:
    """Findet JSON, das als Text in einem JSON-Feld steckt."""
    if tiefe > 4:
        return []
    ergebnis: list[Any] = []
    if isinstance(knoten, str):
        # 60 Zeichen: kurz genug fuer einen kleinen Datensatz, lang genug,
        # dass nicht jede Beschriftung durch den JSON-Leser geschickt wird.
        # Zuvor standen hier 200 -- damit fiel eine Tabelle mit drei Zeilen
        # durchs Raster, obwohl sie sauber verpackt war.
        if len(knoten) >= 60:
            text = _STROM_PRAEFIX.sub("", knoten, count=1)
            if text.lstrip()[:1] in "[{":
                gelesen = _json_oder_nichts(text)
                if gelesen is not None:
                    ergebnis.append(gelesen)
                    # Der Strom verschachtelt weiter: Nutzdaten stecken oft
                    # noch einmal als Text in dem, was gerade ausgepackt wurde.
                    ergebnis.extend(_zeichenketten_aufloesen(gelesen, tiefe + 1))
        return ergebnis
    if isinstance(knoten, dict):
        for wert in knoten.values():
            ergebnis.extend(_zeichenketten_aufloesen(wert, tiefe + 1))
    elif isinstance(knoten, list):
        for wert in knoten:
            ergebnis.extend(_zeichenketten_aufloesen(wert, tiefe + 1))
    return ergebnis
