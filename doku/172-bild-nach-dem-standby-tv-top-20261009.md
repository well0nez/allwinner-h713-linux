# 172 - Bild nach dem Standby: der MIPS-Neustart aus dem Park hängte die SoC, weil der Schlaf die TV-Top-Wörter löscht; Behebung gemessen (09.10.2026, 09:47)

**Kurz:** Auf dem R2-Testabbild (v0.0-r2test1: crust ecf2ddc, TF-A 175c6948f, Kernel 0225-0238, h713-power mit
`h713-mips-restart`) laufen Schlaf und Aufwachen sauber, aber der Neustart der Anzeige-MIPS danach legte die ganze SoC
still, binnen 200 ms nach dem Start des Kerns, 3 von 3. Ursache gemessen: genpd schaltet TVFE und TVCAP im Schlaf ab und
wieder an, die Takt- und Resetwörter der TV-Blöcke (`0x06e00000`, +4, +8) stehen danach auf `0x10, 0, 0`; U-Boot setzt
sie vor dem MIPS-Start, der Neustart aus dem Park tat es nicht. Der Treiber `sun50i-h713-mips` macht jetzt U-Boots
Schritt, wenn die Wörter fehlen: sechs Standbys über h713-power in einem Boot, 6 von 6 mit Bild zurück. Alles in Kopien (Paket `arbeit/r2-20261009/`, Testabbild auf der Box mit
Sicherung); `main` trägt nur diesen Text.

## 1 Das Bild

Konsole zur Laufzeit an (`printk 7`, `console_suspend=N`), h713-power-Pfad (`suspend()`, dann `picture_back()`), RTC-Wecken
nach 20 s. Nach `U-Boot start: core released` und `cpu_comm: resumed (count=0)` kommt nichts mehr; 14 s später setzt
der systemd-Watchdog (16 s) zurück, crust meldet einen normalen Lauf (state 0x105). Mit Herzschlag in kmsg alle 0,2 s und
RCU-Stall-Bericht nach 3 s: letzter Herzschlag 23 ms nach dem Start, kein RCU-Bericht - alle CPUs stehen.

## 2 Eingrenzung

| Versuch | Ergebnis |
|---|---|
| Registervergleich vor/nach einem Schlaf ohne Neustart (CCU, PPU, R_CCU, DRAM-COM, SYS_CFG) | einziger Unterschied außer MIPS/GPU: DRAM-COM+0x004 [21:16] 0x20 -> 0x10 (crust stellt es nicht her) |
| COM+0x004 vor dem Neustart zurück auf 0x20 (s3g) | hängt genauso - widerlegt |
| TV-Top `0x06e00000` nach dem Schlaf lesen (s3h) | `00000010 00000000 00000000` statt `00111111 01111117 00000504` |
| U-Boots TV-Top-Schritt von Hand, dann Neustart (s3h) | bereit nach 290 ms, Bild zurück nach 3955 ms, Bildprobe live |

Das passt zum 08.10. (`doku/170`, L-A): jedes LINK-Lesen hing nach einem Self-Refresh, ein Park ohne Schlaf nicht -
LINK liegt in denselben TV-Blöcken.

## 3 Die Behebung

`sun50i-h713-mips` bekommt die TV-Top-Wörter als dritte reg (`0x06e00000`, nicht angefordert). Der U-Boot-Start prüft sie
und macht U-Boots Schritt aus `h713_disp_clocks()` (+4 0x01111117, +8 0x404, +0 0x00111111, alle 0, wieder, je 12 ms),
wenn sie fehlen; stehen sie, bleibt er weg. Ohne die reg verweigert der Start, statt den Bus zu hängen.

## 4 Messung

Test-FIT (Kernel von r2test1, DTB mit der dritten reg) und das Modul in `updates/`, sonst r2test1 unverändert. Je Lauf
`h713-power`s eigener Erfolgspfad eines kurzen Drucks (`suspend()`, dann `picture_back()`), RTC-Wecken nach 20 s,
danach Bildprobe mit der Box-Kamera (ThinkPad-Bild hell gegen gedimmt, das 99-%-Perzentil der Helligkeit muss folgen):

| Lauf | Laufzeit vor dem Schlaf | MIPS bereit | Bild zurück | Bildprobe |
|---|---|---|---|---|
| t1-t6 | 66 / 158 / 250 / 342 / 434 / 526 s | je 300 ms nach dem Start | je 3,9-5,2 s nach dem Aufwachen | 6 von 6 live |

Alle sechs im selben Boot, jedes Mal `TV top 0x00000010 0x00000000 0x00000000, U-Boot's step: reads 0x00111111
0x01111117 0x00000404`, kein Reset. Ohne Behebung 3 von 3 Hänger (s3c, s3d, s3g). In keinem der zehn Aufwachen auf R2
Kamera -110 oder WLAN-Timeout (Fehler B, `doku/171`).

## 5 Offen

- **C1**, der Hänger beim Einschlafen nach der arisc-Zeile (crust setzt nach 15 s zurück, die Box bootet neu): auf R2
  3 von 13 Schläfen (s3b, s3e, s3f). Die TV-Top-Wörter liegen in den Domänen, die genpd in genau diesem Fenster abschaltet;
  ob das zusammenhängt, ist nicht gemessen.
- Nicht gemessen: der Druck auf die echte Taste, HDCP 2.2 von der Quelle nach dem Neustart, HDMI-Ton nach dem Standby (der
  Audio-DSP liegt in TVFE und wird nach dem Schlaf nicht neu aufgebaut), Schläfe länger als 20 s, die Leistung im Schlaf.
- DRAM-COM+0x004 [21:16] stellt crust nach dem Schlaf nicht her (0x20 -> 0x10); für diesen Hänger widerlegt, sonst nicht
  gemessen.
