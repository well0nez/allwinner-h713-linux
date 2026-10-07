# 167 - Der falsche KEY_POWER nach dem Aufwachen ist behoben (07.10.2026, 13:46)

**Kurz:** Nach jedem Timer-Wecken meldete gpio-keys auf dem HY310 einen Druck auf die Power-Taste (B2, C1; in B1 fuhr
logind die Box deshalb herunter). Ursache gemessen: crust schaltet PL4 beim Aufwachen auf EINT zurück, und die Flanke
dieses Umschaltens erreicht das Statusregister erst nach den nächsten Abtastungen des Debounce-Takts; crust 0031
löschte zu früh. crust 0032 wartet und löscht danach. Zwei Läufe mit Self-Refresh (C2, C3): kein Tasten-Ereignis mehr,
kein Interrupt. Fortsetzung von `doku/166`. Belege: `arbeit/crust-20261007/BERICHT.md` §15 (Nachträge 12:55 und 13:03),
`PRUEFUNG3-20261007.md`, `belege/phase4e-20261007/`, `belege/phase4f-20261007/`.

## 1 Was gpio-keys tut

Drücken und Loslassen kamen in einem einzigen Rahmen mit derselben Zeit. In diesem Kernel geht das nur über den Pfad
„simulate wakeup key press" in `gpio_keys_gpio_isr()`: ein Interrupt der Weck-Taste, solange gpio-keys noch als
`suspended` gilt. Ein im R_PIO gehaltenes Statusbit sieht Linux beim Einschalten der Interrupts als Weck-Interrupt und
spielt es per Software-Resend nach. Der GIC und der IRQ-Kern halten nichts; der Ort ist das R_PIO-Latch. Gelesen in
den Quellen des installierten Kernels, dreifach geprüft (Workflow mit Gegenprüfung, `PRUEFUNG3`).

## 2 Gemessen

- Normalbetrieb: PL4 Funktion `0xe` (EINT), Modus beide Flanken, `PIO_INT_DEB` = 0 (LOSC, alle 30,5 µs eine Abtastung);
  der `power`-Interrupt zählt nach einem normalen Boot schon 1 (Linux schaltet PL4 beim `request_irq` um).
- crust 0032 legt den Status an vier Punkten in der Vertragsseite ab. In C2 und C3 gleich: vor dem Zurückschalten 0,
  direkt danach 0, **nach ≥1 ms Bit 4 gesetzt**, eine Wartezeit nach dem Löschen 0. Das Wegschalten beim Einschlafen
  speichert keine Flanke.
- Linux in beiden Läufen: `power`-Zähler 1 vor und 1 nach dem Schlaf, gpio-keys-Wakeup-Zähler 0 vor und nach, kein
  Eingabe-Ereignis. Vorher (B2, C1): code 116 gedrückt und losgelassen bei jedem Wecken.
- Ansonsten wie `doku/166`: 5 s Self-Refresh, `PM: suspend exit`, CPU0 allein, dann alle vier Kerne, GP-Wörter
  unverändert, zurück in die eMMC-Kette.

**Nicht gemessen:** Wecken per Taste oder IR, der leichte Standby mit 0032 (gleiche Folge im Kompilat), Tiefschlaf,
Läufe ohne `systemd-inhibit`.

## 3 Was nicht stimmte

Die erste Begründung zu 0032 nannte auch die Reihenfolge (crust gab die Pins erst nach dem Start der Kerne zurück). Die
Gegenprüfung hat das widerlegt: Linux nimmt Interrupts erst etwa 30 ms nach der Freigabe der Kerne. Es zählt nur das
Warten; die Reihenfolge bleibt als Ordnung.

## 4 Offen

- **Wecken per Taste** löst weiter `KEY_POWER` aus: das Loslassen kommt, während gpio-keys noch `suspended` ist. Kein
  Thema für crust; eine Regel in Linux oder logind (Ereignisse kurz nach dem Aufwachen verwerfen, oder
  `wakeup-event-action`). Messen nur mit Marco an der Taste.
- MIPS nach dem Aufwachen neu laden (TODO 3.3), Stufe C (vorher prüfen, ob ein 32-kHz-Quarz bestückt ist: der
  Debounce-Takt hängt an LOSC), Leistungsmessung, längere Schläfe.
