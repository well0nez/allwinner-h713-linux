# 166 - Standby mit DRAM-Selbstauffrischung auf dem HY310 (07.10.2026, 12:47)

**Kurz:** Stufe B läuft durch. crust versetzt den DRAM im Standby in die Selbstauffrischung, schaltet DRAM-Takt und
`PLL_DDR` ab, weckt nach 5 s per Zeitgeber, holt den DRAM zurück, und Linux läuft danach stabil weiter (CPU0 allein,
dann alle vier Kerne). Fortsetzung von `doku/165`, ohne Marco unter Hand-Watchdog mit Schutzeinheit (sein Ja für Stufe B
am 07.10.). Belege: `arbeit/crust-20261007/BERICHT.md` §15 (Nachtrag 12:46), `belege/phase4d-20261007/`.

## 1 Aufbau des Laufs C1

- FEL-Abbild `release-standby-sr-0031` (Standby-BL31 aus tfa 0001-0004, crust mit 0029-0031 im Bau mit
  `CONFIG_H713_DRAM_SELF_REFRESH`), Linux mit denselben RAM-Bootargs wie B2 (`doku/165` §1).
- Wie B2: cpu_comm und afbd aus dem Paket (0191, MIPS geparkt), Testmodul 0187d behält crust, Power-Taste per
  `systemd-inhibit` gesperrt, gpio-keys-Ereignisse mitgeschnitten, Schutzeinheit gegen den Hand-Watchdog.
- Neu: das Wurzeldateisystem ist während des Schlafs **read-only**, alle Schreibzugriffe gehen nach `/run`. Kommt der
  DRAM falsch zurück, soll nichts davon auf die eMMC gelangen.

## 2 Gemessen

- Linux: `crust is running (..., build 0x05003ee0: self-refresh ir), image kept` - der laufende crust ist der
  Selbstauffrischungs-Bau (Build-Wort Bit 24), Version v0.6.32.
- `PSCI: system suspend` -> 5,06 s (Host-Uhr) -> `system counter restored, 5000 ms asleep added` -> `back from system
  suspend` -> Weckwort `0xc0000000` -> `Restarting tasks: Done` -> `PM: suspend exit`. 32 s CPU0 allein, CPU1/2/3 einzeln
  online (rc=0), 20 s alle vier Kerne, kein Reset, Watchdog am Ende aus, GP-Wörter unverändert.
- crust-Diagnose nach dem Aufwachen: `step 0x619` (`STEP_RESUME_COMPLETE`), `slept_ms 5000`. Der Einschlafweg wartet
  ohne Zeitgrenze, bis der Controller `STATR = SELFREF` meldet, und schaltet erst dann Takt und PLL ab; der Aufwachweg
  wartet ebenso auf `STATR = NORMAL`. Ohne erreichte Selbstauffrischung stünde crust auf `STEP_SUSPEND_DRAM`; ohne
  erhaltenen DRAM-Inhalt liefe Linux nicht weiter.
- Wieder `KEY_POWER` gedrückt/losgelassen beim Aufwachen (code 116), wie in B2.
- Zurück per `systemctl reboot` in die eMMC-Kette: Hersteller-ARISC, EDID, vier Kerne, `/` beschreibbar, Dienste laufen.

**Nicht gemessen:** `STATR` während des Schlafs, die Stromaufnahme, Schläfe länger als 5 s.

## 3 Offen

- Der falsche `KEY_POWER` beim Aufwachen (crust 0031 hilft nicht).
- Die MIPS kommt nach dem Aufwachen nicht wieder (TODO 3.3) - kein Bild bis zum Neustart.
- Stufe C (Tiefschlaf), Wecken per Taste/IR, Leistungsmessung, längere Schläfe.
