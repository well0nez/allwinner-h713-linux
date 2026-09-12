"""h713-focus -- den Fokusmotor des HY310 bedienen, ueber die sysfs-Schnittstelle
des Treibers hy310-focus-motor.

Vier Module, streng getrennt -- wie bei h713-pq:
    geraet   -- die einzige Naht zum Dateisystem: sysfs suchen, lesen, schreiben
    zustand  -- motor_limit auslegen und die Sicherheitsregeln; kein I/O
    fahren   -- der bewachte Fahrlauf (kleine Schritte, pruefen, abbrechen)
    ausgabe  -- druckt; rechnet nicht und faehrt nicht

Das Werkzeug bewegt echte Mechanik. Die Regeln, die daraus folgen, stehen in
zustand.pruefe() und in fahren.lauf() -- und nur dort.
"""

__version__ = "0.1"
