# 203 - Standby und Warmstart am G-EU behoben: afbd liest die Aufnahme nicht zu früh, die Sperren wie die Firmware (12.10.2026)

**Kurz:** Marco am Morgen nach `doku/202`: eine über Nacht laufende Offline-Sitzung meinte, die Warmstarts seien behoben; der
Standby mache weiter Probleme. Geprüft, gefunden und behoben: **(1) Standby (TODO 2.64):** afbd-Patch `0255` las beim Aufwachen
im Vsync-Interrupt das Register der Aufnahme, bevor der MIPS wieder lief - der Bus hing, der SoC-Watchdog setzte nach 16,4 s in
crusts Phase "resuming" zurück, dreimal von drei. `0258` sperrt diese Lesezugriffe ab dem Standby, bis der HDMI-Empfänger neu
gebunden ist. **(2) Warmstart dunkel (TODO 2.63):** unser Nachbau der gemeinsamen Sperren benutzte andere Bytes als Firmware und
Herstellertreiber (Befund der Offline-Sitzung, gegengelesen); `0259` übernimmt deren Verfahren und gibt beim Start Sperren frei,
die ein früherer Lauf als "ARM hält" hinterließ. Gemessen am HY300PRO-G-EU: 15 von 15 Standbys zurück, 12 von 12 Warmstarts sauber.
Dazu am G-EU `h713_gate=0` (Marco, unterwegs) und der Sonoff am G-EU. Pakete: `arbeit/mips-sperre-20261012/` (Offline-Sitzung),
`arbeit/standby-20261012/` (Standby), `arbeit/kernel-abend-20261011/` (Kernel).

## 1 Was die Offline-Sitzung lieferte, und was davon hält

Bericht `arbeit/mips-sperre-20261012/BERICHT.md`: Firmware (`display.bin`, `tridspinlock.c`) und Herstellertreiber
(`cpu_comm_dev.ko`) benutzen denselben 12-Byte-Eintrag - Byte 0 "wer ist im kritischen Abschnitt", Byte 1 "wer hält die Sperre",
Hardware-Lock id+2. Unser Nachbau schrieb Byte 3 statt 0, wartete dort nicht und schrieb Byte 1 nie: eine Sperre, die der ARM
hielt, sah für den MIPS frei aus. Gegenseiten-Test am Gerät: altes Modul 6 Firmware-Asserts in 30 s, neues 0 in 60 s; 8 Warmstarts
mit dem Modul sauber. Den Code habe ich gegengelesen.

Nicht im Bericht: im Start **direkt nach** einem abgestürzten Standby (11.10. 23:03) trat mit dem gepatchten Modul wieder
`SpinUnLock(2): no thread_id` auf, diesmal `owner=0` (ARM) - ein Sperrzustand, den der abgestürzte Lauf im gemeinsamen Speicher
hinterließ (der Start übernimmt den Bereich). Das Sicherheitsnetz `h713-tv-rescue` griff (Bild nach 4,3 s). Dagegen in `0259`:
`comm_SpinLockForgetArm()` gibt beim Übernehmen jede Sperre frei, die als "ARM hält" oder "ARM im kritischen Abschnitt" steht -
in dem Moment hält dieser Treiber noch keine.

## 2 Der Standby-Hänger (2.64)

UART-Mitschnitt mit `console_suspend=N`, `dmesg -n 8`, Standby per RTC (`arbeit/standby-20261012/s3-test.py`, wie h713-power):

```
438.484  sunxi-wdt: re-armed (timeout=16 sec)
438.518  hy310-cpu-comm: standby: display clocks restored
         ... 16,4 s nichts ...
         U-Boot SPL, "crust before this boot: state 0x124 step 0x619 ... net 16447 ms", "gate: a standby did not finish"
```

Dreimal gleich (16 403 / 16 404 / 16 447 ms), schon mit dem alten Kernel (11.10. 21:24). Gegenprobe zur Laufzeit:
`echo 0 > /sys/module/sun50i_h713_afbd/parameters/ring_select` (die Flip-Zeiger statt `INCAP +0xa0c`) - derselbe Standby kam
zurück. `0258`: `incap_live` wird beim Standby falsch und erst wieder wahr, wenn der HDMI-Empfänger seinen Flip-Notifier neu
anmeldet (er bindet nur an einem laufenden MIPS, `h713-mips-restart`); bis dahin die Zeiger. Mit `ring_select=1`: zurück, Bild
nach 5,5 s, danach `anzeige.py`: 59,70 von 60 gezeigt, Zeiger 56,00 - die Aufnahme liest wieder selbst.

## 3 Gemessen mit dem Kernel aus der Serie (FIT `5fc51625`, 283 Patches, Baum `8163a3c7`, Module aus dem Baum)

| Reihe | Ergebnis |
|---|---|
| 12 Warmstarts (`warmstart-reihe.sh`) | 12/12: h713-tv aktiv, Bild an, 0 Sperr-Meldungen, Netz nie gebraucht |
| 2 Standbys RTC | zurück nach 5,5 / 6,0 s |
| A Warp an (`tl x 50`) | zurück, 59,60 fps gezeigt, Warp an |
| B 60 s geschlafen | zurück, 59,80 fps |
| C 5 Standbys hintereinander | 5/5 zurück; 1-4 ohne Bild, weil der Fire TV eingeschlafen war ("no signal"), 5/5 59,80 nach Marcos Tastendruck am Fire TV |
| D `ctl off`, Standby, `ctl auto` | zurück, Konsole bleibt bei `off`, nach `auto` 59,80 fps |
| E 3 Standbys, ThinkPad als Quelle | 3/3 zurück; 59,60 / 0 / 59,60 - beim zweiten rastete der Laptop erst nach ~20 s wieder ein (Signal 436-455 s) |

Bei allen 15 Standbys: `audio DSP rebuilt (attempt 1)`, `hci0 UP RUNNING`, `h713_gate=0`. Nicht gemessen: Wecken per Taste oder
IR (Marco), `0257` (braucht ein Aus über crust), die UCLAMP-Messreihe (2.60).

## 4 Gate und Sonoff am G-EU

Marco (unterwegs, Fernbedienung über mich): `fw_setenv h713_gate 0` (vorher 1, Umgebung in `/root/uboot-env-vor-gate0.txt`). Nach
dem Umstecken auf den Sonoff (jetzt `<geschwaerzt 23.10.2026: Heimnetz-Adresse>`) bootete die Box selbst: UART `gate: off (h713_gate=0, GP5 00000000)`. Ein
gescheiterter Standby und Netz-Ein booten jetzt durch; Standby und "Aus über crust" weckt weiter nur Taste/Fernbedienung/RTC - aus
der Ferne über den Sonoff zurückholbar. UART-Schreiben im Notfall erlaubt (Marco).

## 5 Handoff (12.10.2026, ~09:30)

**In `main` (nicht gepusht):** der Kernel-Zweig (`0256`-`0259`, UCLAMP, `h713-cpufreq`), der Hostname-Zweig (5.18, G-EU verified),
`doku/203`, Doku `cpu-comm.md` und `standby.md`. Zweige danach gelöscht; geparkt und archiviert: Panel
(`arbeit/panel-20261011/panel-einstellungen.bundle`), `warp-einpass`, `warp-konsole` (Bündel in ihren Paketordnern).

**G-EU:** Kernel `5fc51625` aus der Serie, keine Module mehr in `updates/`, `h713_gate=0`, Journal dauerhaft, Sonoff dran.
Rückweg: `/boot/h713-kernel.fit.alt` + `/lib/modules/6.18.38.alt` (Abendkernel 2).

**Offen:** Wecken per Taste/IR prüfen (Marco), `0257` messen (Aus über crust), UCLAMP-Messreihe (2.60), BT unter Last (2.49),
ein Release-Abbild mit allem (1.1a); 2.51 Mikro, 2.54 Panel (Mockup zuerst) geparkt.
