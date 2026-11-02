# 226 HY320: crust als ARISC-Firmware, von Linux geladen - Protokoll

Datum: 01.11.2026 abends. Gerät: der HY320 seines Besitzers, TEST-Abbild mit Kernel bis `0348` (Kern und Module von Hand
eingespielt), Quelle eine Xbox One X. crust `v0.6.90-g74d64d759f99`, `h713_hy320_sr_defconfig` (Board-ID 4, 20776 B, sha256
`7b2e50c1...`), angeboten als well0nez/crust#1. Plan: `CrustScope` S0-S10 (S0 = Commit `1b2697d7`). Augen und Ohren: der Besitzer.

## 1 S2: Hersteller-Firmware mit dem neuen Baum

`h713-arisc set vendor`, Neustart: `firmware "h713-arisc.bin" (module option)`, DDC-Porttabelle wie in `doku/225`, Port 1,
1920x1080p60, 48 kHz. `0348`: `fan0: fan-power-gpio 37 set HIGH` (PB5 beim Board-Manager), 3960 U/min. `0347`: `&mips` an.

## 2 S3: crust, von Linux geladen

`h713-arisc set crust`, warmer Neustart:

- `crust contract v5, build 0x05005128 (20776 bytes self-refresh ir), build2 0x01004318 (DRAM 792 MHz, board 4, R_WDOG code 0, power off)`,
  `state`: `err=0x00000000`, `exception=0`.
- `EDID port 1 read back (256 B), extension 02 03 4c ...`, `EDID/HPD sequence on port 1 completed` - crust schreibt das DDC-RAM je
  Port direkt, keine Porttabelle, also keine `0336`-Korrektur nötig (und keine Zeile dazu).
- Zweimal `the display MIPS sent hotplug or reset frames during the EDID sequence ... not repeated` (das "ADT-3 2024"-display.bin).
- `sunxi-ir: PL9 applied again after the ARISC start`; PL_CFG1 `0x07022004 = 0x2222223f` (PL9 = 3).
- Xbox 1920x1080p60, `audio source present=1 rate=48000`, HDCP `2.2 (session stands)`, LINK `0x93 = 0x45`. Besitzer: Bild und Ton
  normal.

## 3 S4: Ausschalten über crust

`systemctl poweroff`: Besitzer - ganz dunkel, Lüfter aus, **kein Brummen**, rote LED. Netztaste: Logo, Start. Nächster Start:
`previous run (record of Linux): powered off through crust, back by the R_WDOG (0x00000000), cycle 0`; Bild wieder da.

## 4 Offen

S5 ff.: ein Abbild mit `--standby` (BL31 mit `SYSTEM_SUSPEND`, crust ab dem Start), Netz-Ein über crust, `h713-mips-restart`
(bleiben `0x051c0014`/`0x051c0028` danach?), Standby mit RTC/Taste/Fernbedienung, Zyklen, Leistungsmessung. Das Abbild läuft
weiter mit crust (`/etc/modprobe.d/h713-arisc.conf`).
