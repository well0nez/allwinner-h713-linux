# 165 - Der erste vollständige Standby-Zyklus auf dem HY310 (07.10.2026, 12:08)

**Kurz:** Mit crust (TF-A startet es beim Boot), geparkter Display-MIPS und gesperrter Power-Taste läuft auf dem HY310
zum ersten Mal ein Standby-Zyklus vollständig durch: einschlafen, 5 s schlafen, per crust-Zeitgeber aufwachen,
`PM: suspend exit`, danach stabil mit CPU0 allein und mit allen vier Kernen. Fortsetzung von `doku/163` und `164`, wieder
ohne Marco unter Hand-Watchdog mit Schutzeinheit. Belege: `arbeit/crust-20261007/BERICHT.md` §15 (Nachtrag 12:07),
`belege/phase4c-20261007/`.

## 1 Aufbau des Laufs B2

- FEL-Abbild `release-standby-0031` (Standby-BL31 aus tfa 0001-0004, crust mit 0029-0031), Linux mit RAM-Bootargs
  (`modprobe.blacklist=sun50i_h713_arisc,sun50i_h713_hdmirx,hy310_cpu_comm,sun50i_h713_afbd`, `systemd.mask=h713-hdcp-key.service`).
- cpu_comm und afbd aus dem Paket (0191: parken MIPS und Scanout nur bei Suspend-to-RAM), Testmodul 0187d behält crust.
- `systemd-inhibit --what=handle-power-key`, Mitschnitt der gpio-keys-Ereignisse, vorübergehende Unit, die den
  Hand-Watchdog bei jedem Herunterfahren abschaltet (`referenz/irrwege.md`).

## 2 Gemessen

- `cpu_comm: standby: coprocessor parked` -> `PSCI: system suspend` -> 5 s -> `back from system suspend` -> Weckwort
  `0xc0000000` -> `Restarting tasks: Done` -> `PM: suspend exit`. 32 s CPU0 allein, CPU1/2/3 einzeln online (rc=0), 20 s
  alle vier Kerne, kein Reset, Watchdog am Ende aus, GP-Wörter unverändert. Danach normaler Neustart in die eMMC-Kette.
- Beim Aufwachen meldet gpio-keys `KEY_POWER` gedrückt/losgelassen (code 116) - das erklärt das Herunterfahren in B1.
  Die Korrektur crust 0031 (EINT-Status nach dem Zurückschalten löschen) verhindert es **nicht** - offen.
- Ohne geparkte MIPS (A2-A4) bleibt das System kurz nach dem Aufwachen stehen; ohne cpu_comm/afbd (B1) wacht es auf.
  Die Ursache liegt also im MIPS-/Display-Pfad, der den Schlaf nicht übersteht, wenn die MIPS weiterläuft.

## 3 Offen

- Der falsche `KEY_POWER` beim Aufwachen (Quelle der Flanke; Kernel-seitig oder crust-seitig beheben).
- Die MIPS kommt nach dem Aufwachen nicht wieder (0189 parkt ohne Neuladen; FB-MIPSRELOAD, TODO 3.3) - kein Bild bis zum Neustart.
- Stufe B (DRAM-Selbstauffrischung) und C (Tiefschlaf), Wecken per Taste/IR, Leistungsmessung.
