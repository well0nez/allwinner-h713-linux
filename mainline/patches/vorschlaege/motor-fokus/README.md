# Vorschlag: Fokusmotor + Endschalter

Bearbeitet 07.09.2026 vom Agenten aus `doku/auftraege/AGENT-fokus-motor-homing.md`.
Nichts davon ist in die Serie eingebaut — das entscheidet die Hauptsitzung.

Zuerst **`BEFUND.md`** lesen, dann **`TESTPLAN.md`**. Der Testplan gehört ans Gerät,
unter Aufsicht; der Agent hat die Hardware nicht angefasst.

Reihenfolge der Patches (0002 setzt auf 0001 auf):

    0001  Kernelbaum, -p1   Ursache des Endschalter-Fehlers
    0002  Kernelbaum, -p1   manuelle Fahrbefehle (Fokus)
    0003  Kernelbaum, -p1   DTS: Stock-Eigenschaftsnamen
    0004  Kernelbaum, -p1   Kconfig-Text
    0005  REPO-Datei,  -p1 aus mainline/   Treiber als Modul bauen

0001–0004 wurden gegen den konfigurierten 6.18.38-Baum geprüft: greifen sauber,
übersetzen warnungsfrei, der DTB baut. Arbeitsordner mit den idalib-Rohausgaben und
der Bauprobe: `agenten/motor-fokus/`.

Kurz: der Endschalter ist nicht defekt. Stock liest ihn am selben Gerät (Beleg im
Befund), unser Treiber trieb die Leitung beim Anfordern als Ausgang, ließ den
Pad-Bias offen und wertete das Signal genau verkehrt herum aus — er fuhr deshalb
nie zurück. Und es gibt keinen zweiten Motor: `motor_ctr` **ist** der Fokusantrieb.
