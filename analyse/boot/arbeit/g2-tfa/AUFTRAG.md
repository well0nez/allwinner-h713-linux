# G2 — TF-A: `poweroff` → GATE-Flag + Reset (Plan 103 §2.3), Bericht S37

Lies zuerst `../REGELN.md` und `doku/103-plan-einschaltgate.md` §2. Original nur lesen: `mainline/external/arm-trusted-firmware`
(HEAD 47ee829f7). Kopie: `kopie/sun50i_h713/` (unser Plattformordner) und `kopie/ref/` (H616 `sunxi_power.c`, `sunxi_native_pm.c`, nur Referenz).

## Zu liefern
1. Eigene `sunxi_power_down()` für `sun50i_h713` statt des `#include` des H616-Codes (oder ein sauberer Haken davor — begründen):
   - `mmio_write_32(0x07090114, 0x47415445)` („GATE"), Datenbarriere, dann Systemreset (`sunxi_system_reset()`-Pfad bzw. der Watchdog-Reset, den
     `sunxi_native_pm.c` nutzt — nachschauen, was auf H713 tatsächlich resettet; H616-Pfad `sunxi_system_reset()` prüfen).
   - Ergebnis: Linux `poweroff` (PSCI `SYSTEM_OFF`) landet nach dem Reset im U-Boot mit GP5 = GATE → Gate.
   - `SYSTEM_RESET` (`reboot`) bleibt unverändert (kein Flag).
2. Prüfe, ob `sunxi_power_down()` auf H713 überhaupt erreicht wird (`pmic` unbekannt → H616-Code kehrt früh zurück; unser Pfad muss **vor** dieser
   Prüfung liegen) und ob die RTC-GP-Register aus BL31 beschreibbar sind (Secure-Zugriff; RTC-Basis `0x07090000`; vergleiche `sunxi_h713_dtb.c`,
   GP3-Schreibung `0xb00f` — wer schreibt die? ARISC-Treiber im Kernel oder BL31? Bitte klären, es hilft der Hauptsitzung).
3. Patch `patches/0001-tfa-h713-poweroff-enters-the-boot-gate.patch`, Bericht `doku/nachtlog/S37-tfa-poweroff-gate.md` mit Bauhinweis (Container
   `h713-build`, doku/50) und Testrezept (`poweroff` aus Linux, UART: U-Boot muss GATE lesen).
