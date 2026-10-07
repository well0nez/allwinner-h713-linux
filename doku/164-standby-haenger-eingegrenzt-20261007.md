# 164 - Standby mit crust: der Stillstand nach dem Aufwachen liegt bei Display-MIPS/afbd (07.10.2026, Vormittag)

**Kurz:** Fortsetzung von `doku/163`. Ohne Marco an der Box, unter einem von Hand gesetzten Watchdog (Marcos Freigabe für
Folgeläufe), wurde der Stillstand nach dem Aufwachen eingegrenzt: TF-As Hotplug ist in Ordnung, die Nebenkerne sind nicht
die Ursache, und **ohne `hy310_cpu_comm` und `sun50i_h713_afbd` wacht die Box zum ersten Mal vollständig auf**
(`PM: suspend exit`). Danach fuhr sie sich selbst herunter, und TF-As Ausschalt-Reset scheiterte am noch laufenden
Hand-Watchdog - seit 10:35:30 angehalten in BL31, Stromschnitt durch Marco nötig. Belege: `arbeit/crust-20261007/BERICHT.md`
§15 (Nachtrag 10:27-10:40), `belege/hotplug-20261007/`, `belege/phase4b-20261007/`.

## 1 Gemessen

| Lauf | Aufbau | Ergebnis |
|---|---|---|
| Hotplug 1 | installiertes System, CPU3 aus/an, Hand-Watchdog, Füttern per MODE aus/ein | CPU3 aus/an rc=0, Reset 16,5 s nach dem Scharfschalten - das Füttern wirkte nicht |
| Hotplug 2 | wie 1, Füttern per CTRL-Ping `0x14AF` (`doku/72`), 60 s Last | kein Reset - **CPU_OFF/CPU_ON über TF-A ist in Ordnung** |
| A4 | Standby Stufe A, CPU1..3 vorher offline | Stillstand direkt nach `board-mgr fan: resumed` (wie A3), Watchdog-Reset nach 16,4 s |
| B1 | wie A4, dazu `cpu_comm` und `afbd` gesperrt | `Restarting tasks: Done`, `PM: suspend exit`, Skript läuft weiter - **vollständig aufgewacht** |

Nach B1: 0,2 s nach dem Aufwachen `poweroff.target`, `reboot: Power down`; TF-A `power off, resetting into the boot gate`,
dann `system reset failed, board stays powered`.

## 2 Gelernt

- Der Hand-Watchdog (`0x02051000`, CFG `+0x10`, MODE `+0x14`, CTRL `+0x0c`) setzt die Box auch mit gestecktem USB-Kabel
  zurück, sie bootet normal. Füttern: `0x14AF` nach CTRL - MODE aus/ein startet den Zähler nicht neu
  (`referenz/geraete.md`, Aussage vom Vortag als überholt markiert).
- TF-A schreibt beim Ausschalten MODE (0,5 s) in einen schon laufenden Watchdog; das verschluckt den Reset (erschlossen,
  `referenz/irrwege.md`). Härtung für die Linie: vorher MODE aus, CTRL anpingen (TODO 2.25).
- Das Herunterfahren nach dem Aufwachen passt zu einem `KEY_POWER` aus gpio-keys, wenn crust PL4 beim Aufwachen auf EINT
  zurückstellt (aus dem Code, nicht gemessen).

## 3 Nächster Lauf (vorbereitet, nicht gelaufen)

cpu_comm und afbd aus den Paketmodulen `*-0191.ko` (parken MIPS und Scanout bei Suspend-to-RAM) statt gesperrt; die
Power-Taste während des Laufs per `systemd-inhibit` sperren und die Eingabeereignisse mitschneiden; den Hand-Watchdog vor
jedem möglichen Herunterfahren ausschalten. Erst danach Taste/IR als Weckquelle und Stufe B.
