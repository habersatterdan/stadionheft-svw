"""Auswertung der Spielerdaten.

Zwei Schritte, bewusst getrennt:

* :mod:`kennzahlen` berechnet einzelne Groessen -- Form, Einsatzzeit,
  Marktwerttrend, Gegnerstaerke. Jede liefert eine Punktzahl von -100 bis
  +100 **und** einen Satz, der sie erklaert.
* :mod:`bewertung` gewichtet diese Groessen zu einer Gesamtnote und macht
  daraus eine Empfehlung.

Diese Trennung ist der Grund, warum der Berater nie ein "Kaufen!" ohne
Begruendung anzeigt: die Begruendung entsteht bei der Berechnung, nicht
nachtraeglich.
"""

from .bewertung import Referenzwerte, bewerten, kader_bewerten

__all__ = ["Referenzwerte", "bewerten", "kader_bewerten"]
