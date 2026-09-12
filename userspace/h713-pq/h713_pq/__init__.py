"""h713-pq -- Stock-PQ-Daten des HY310 lesen und in Kernel-Schnittstellen umrechnen.

Drei Module, streng getrennt:
    quellen  -- liest (SQLite, INI, XML), rechnet nichts
    modell   -- rechnet (Kette Eingang x Bildmodus -> Zielwerte), liest nichts
    ausgabe  -- druckt und schreibt Dateien, rechnet nichts
"""

__version__ = "0.1"
