# 188 - "Aus" über crust: die Schienen aus (PL6), 0,3 W wie Stock, Timer, Fernbedienung und Taste wecken (10.10.2026)

**Kurz:** Ein `poweroff` endet auf dem HY300PRO-G-EU nicht mehr in U-Boots Gate (ein ARM-Kern in einer Schleife,
2,4 W), sondern in crust: Cluster in Reset, DRAM in Self-Refresh, VDD_SYS getrennt, dann die eine Freigabe der
Schienen PL6 low (vdd-cpu, vdd-sys, vcc-pll, vcc-dram) - wie die Hersteller-Firmware (`doku/187` §1). Gemessen an der
Steckdose ohne USB-Kabel: **0,3 W**, so viel wie Stock-Android aus. Taste, IR-Fernbedienung und (im Testbau) ein Timer
wecken; crust hebt PL6, schreibt `RUN1` in RTC-GP5 und setzt den SoC über den R_WDOG zurück, U-Boots Gate bootet durch.
Alles per FEL gemessen, die Bootkette in der eMMC blieb unberührt. Der HY310 ist nicht gemessen und bekommt das Aus erst
danach. Paket `arbeit/aus-pl6-20261010/` (BERICHT, Patches, Skripte, `test/laeufe/records.txt` mit den Kernelzeilen).

## 1 Was gebaut ist

| Teil | Stand | Inhalt |
|---|---|---|
| crust | Fork-Zweig `h713` `d8a8d56`, Spiegel `crust-h713/` 0082-0087 | Port-3-Auftrag 0x19 (Stock "fake poweroff"), nur außerhalb eines Standbys: Phase 7 `POWEROFF`, SoC-Watchdog aus, PB5 und PL3 low (wie im Gate), nach 50 ms der ganze Cluster in Reset (`css_power_off()`: Linux parkt CPU1..3 beim Ausschalten nur in einer Schleife), `system_shutdown()`. Im Shutdown nach dem Self-Refresh: VDD_SYS-Reset und AVCC-/Bit-8-Gating (Stock `0xdea8`), dann PL6 low. Wecken: PL6 high, 10 ms, VDD_SYS frei, GP5 `GATE` -> `RUN1`, R_WDOG-Reset. `H713_POWER_OFF` (BUILD2 Bit 24) nur in `h713_hy200_qz713df_a1_sr_defconfig`; Testbauten `*_sr_off_test_defconfig` wecken sich nach 60 s selbst |
| TF-A | `sun50i-h713` `1dd03734`, Spiegel `tfa-h713/` 0031 | `SYSTEM_OFF`: erst `GATE` in GP5 wie bisher, dann `sunxi_scp_power_off()`: nur bei crust mit Vertrag v5, BUILD2 Bit 24, Herzschlag und Phase OFF/RELEASED; crust bestätigt mit Phase 7 binnen 20 ms. Sonst der Reset ins Gate wie bisher, TF-A-Ereignis 5 mit Grund |
| Kernel | `0250` | der Treiber nennt Phase 7 "poweroff", BUILD2 Bit 24 ", power off" und TF-A-Ereignis 5 |
| h713-power | Vorgabe `short = poweroff`, neu `h713-power set KEY VALUE` | die Vorgabe aus 2.29; umstellen ohne Datei-Editor: `h713-power set short standby`; `status` sagt, wer ausschaltet (crust oder Gate) |

## 2 Die Läufe (HY300PRO-G-EU, FEL, Marco am Gerät mit Steckdosen-Wattmeter)

Der Kernel-Treiber ersetzt beim Start ein laufendes crust, das nicht der Datei `hy200-qz713df-a1-crust.bin` entspricht
(0192) - der erste FEL-Start lief deshalb mit dem alten crust weiter und wurde nicht ausgeschaltet. Für die Läufe lag in
`/lib/firmware` das jeweilige Test-crust (Marcos Freigabe, Original gesichert und danach zurück, md5 `77f560d2...`).

| Lauf | crust | Kernelzeile des nächsten Starts (gekürzt) | Ergebnis |
|---|---|---|---|
| geu1b | erster Stand | Phase 7, Schritt `0x60a` (SUSPEND_COMPLETE), GP5 `GATE` | dunkel, Taste nötig: kam aus dem Gate |
| geu2 | + SoC-Watchdog-Stopp | gleich | gleich - der Watchdog war nicht die Ursache |
| geu3 | + Spur: ms im Aus, Zeitpunkt der Schienen | Schienen aus bei 52 ms, crust zählte bis 57 ms, GP5 `GATE` | **2,1 W** (Gate, A-A-Kabel steckt): der SoC setzte sich ~5 ms nach PL6 low zurück |
| geu4 | + VDD_SYS-Reset und Gating vor PL6 | 60062 ms im Aus, Schritt `0x613`, GP5 `RUN1`, R_WDOG `0x00010001` | **0,3 W** (Kabel steckt), Timer weckt, zurück ohne Taste |
| geu5 | Release-Konfiguration, **ohne Kabel** | 117148 ms im Aus, Schritt `0x613`, GP5 `RUN1` | **0,3 W**, Fernbedienung weckt, Uptime danach 26 s |
| geu7 | Release-Konfiguration | 21892 ms im Aus, Schritt `0x613`, GP5 `RUN1` | Power-Taste am Gerät weckt, zurück 54 s nach dem `poweroff` |

Vergleich: Stock-Android aus 0,3 W (09.10.), unser Gate 2,4 W (G-EU) bzw. 2,9 W (HY310, `doku/181`), Standby 2,4 W.
Nicht gemessen: Watt am HY310, Wecken per CEC (crust hat es nicht), die Zeit bis zum Bild nach dem Wecken.

## 3 Was dabei herauskam

- **Ohne die Stock-Trennung `0xdea8` setzt sich der SoC selbst zurück**, wenige Millisekunden nachdem PL6 fällt
  (geu3). R_PRCM `0x260` Bit 0 löschen (VDD_SYS in Reset), `0x250` Bit 2 und Bit 8 setzen, dann PL6 - so lebt crust weiter
  und hält 0,3 W (`referenz/irrwege.md`). Beim Wecken wieder zurück, bevor der R_WDOG zurücksetzt.
- **Linux hält den SoC-Watchdog scharf**: `sunxi-wdt: Watchdog enabled (timeout=16 sec)`, systemd `RuntimeWatchdogSec`
  und `RebootWatchdogSec` 16 s aus `10-h713-watchdog.conf` im Abbild, MODE `0xb1` gelesen. Er läuft über ein `poweroff`
  weiter; crust stoppt ihn jetzt, auch wenn er die Resets der ersten Läufe nicht verursacht hat (`referenz/geraete.md`).
- **crusts Takt hängt nicht an PL6**: crust zählt im Aus auf Quelle 0 (OSC24M) weiter, der Timer weckte nach 60062 ms.
- Ein FEL-Gerät, dessen USB-Kabel umgesteckt wurde, meldete sich am PC nur noch mit `device descriptor read error -110`
  und hing im FEL; nach einem Neustart des PCs war es wieder da. Kein Befund an der Box.

## 4 Das Abbild `geuaus1` (10.10.2026 abends)

Komplett gebaut aus `versuch/aus-pl6` `09fa4a7` (`v0.0-geuaus1-TEST`, 21 min 49 s, reproducible: yes, 274 Patches, TF-A
`1dd037344`, crust `d8a8d56`, Tore grün) und mit `h713-install` über unser Layout installiert (Secure Storage bytegleich,
HDCP-1.4-Satz da; `/etc/h713`, Bluetooth-Kopplung und Host-Schlüssel aus der Sicherung zurück). Kurztests mit Marco:

| Test | Ergebnis |
|---|---|
| crust | läuft aus dem FIT, die Datei passt (kein Nachladen), die Kernelzeile endet auf ", power off" |
| WLAN, Bluetooth | verbunden; die Fernbedienung verbindet sich erst nach einem Tastendruck (BLE), dann hört `h713-power` auf sie |
| HDMI, HDCP 1.4 | 1080p60 vom ThinkPad; nach neuer Anfrage `Enabled` binnen 3 s, `0x93=0x45` |
| Ton | 1 kHz, Amplitude 3000, 60 %, 6 s vom ThinkPad: `present=1`, 48 kHz, msp running, Pegel 75/75; Marco: gehört |
| Standby | Power der Bluetooth-Fernbedienung -> `short press: standby`; Wecken per IR (`0x9b`), 23,8 s geschlafen, Bild nach 6,4 s, DSP im 1. Versuch |
| Umschalten | `h713-power set short poweroff` -> `status`: "a power-off: crust (rails off ...)" |
| Aus | Gerätetaste kurz -> `short press: power-off`; Wattmeter 0,3-0,7 W (schwankt am unteren Rand); Wecken per Fernbedienung; Record "crust in phase poweroff", 11,5 s, GP5 RUN1 |

Gesehen nebenbei: nach dem Einstecken (Kaltstart ins Gate) zieht die Box weiter **2,4 W** - das Gate wartet dort noch mit
einem ARM-Kern; Stock geht auch hier in den ARISC-Wartezustand (TODO 2.39). Und nach jedem Aus über crust meldet der Kernel
"TF-A: R_WDOG found armed" als Warnung, obwohl das der vorgesehene Rückweg ist (TODO 2.40).

## 5 Was folgt

- HY310: einmal mit `h713_hy310_sr_off_test_defconfig` messen (gleiche Pins laut Stock-Baum), dann `H713_POWER_OFF` in
  `h713_hy310_sr_defconfig`.
- Ein Abbild aus diesem Stand für den G-EU und die Kurztests (crust, HDMI, Ton, Bluetooth, WLAN, Aus, Standby) vor `main`.
- Später (eigenes Paket): ein OSD auf afbd beim Ausschalten ("Ausschalten in 15 s" / "Standby", ein zweiter Druck schaltet
  sofort aus) und die IR-Belegung (TODO 2.35), damit auch die IR-Fernbedienung aus- und umschaltet.
