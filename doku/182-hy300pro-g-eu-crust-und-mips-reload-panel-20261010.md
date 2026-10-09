# 182 - HY300PRO-G-EU: crust läuft, und der schwarze MIPS-Reload ist das Panel - es braucht einen Stromzyklus (09./10.10.2026, 21:00-02:00)

**Kurz:** Marcos HY300PRO-G-EU (Platine HY200 QZ713DF A1, Stock `projector05061226`) hat ein Testabbild mit crust
bekommen (`v0.0-geucrust1-TEST`). crust läuft dort als ARISC-Firmware, HDMI-Bild, EDID/HPD und der HDCP-1.4-Schlüssel
stimmen. Der MIPS-Reload ließ die Wand aber schwarz, wie schon am 03.10. (`doku/138`). Ursache gefunden: Das LCD-Panel
des Boards (eigener Timing-Controller) verliert beim Neustart der Display-Firmware den LVDS-Takt und rastet erst nach
einem **Stromzyklus** wieder ein (PF6 300 ms aus, dann an). Der Reset-Puls allein reicht nicht. Der HY310 mit seiner
DLP-Brücke rastet von selbst ein. Behebung im MIPS-Treiber (Panel-Pins optional im Gerätebaum), dazu fehlte PF6 in der
Pin-Tabelle des H713. Am Gerät 3 von 3 von Hand und 3 von 3 mit dem Treiber. Alles in Kopien (Paket
`arbeit/geu-crust-20261009/`, Zweig `versuch/geu-crust`, crust-Zweig `versuch/geu-crust`); `main` trägt nur diesen Text.
Protokoll: `arbeit/crust-20261007/STATE.md` 21:2x-02:0x.

## 1 Das Abbild und crust

- crust für das Board: die SR-Konfiguration des HY310 mit Board-Kennung 3 (`h713_hy200_qz713df_a1_sr_defconfig`, crust
  `c5b536f` auf `ecf2ddc`). Belegt aus dem Stock-Gerätebaum des Geräts (eigener Abzug): Power-Taste PL4, IR-Empfänger und
  LEDs PL0/PL1 wie beim HY310; die DRAM-Worte, die crust nutzt, sind in U-Boots `hy310`- und `hy200_qz713df_a1`-Konfig
  gleich, der Takt der Variante ist 792 MHz. Kernel `0246` nennt crust im Gerätebaum (`hy200-qz713df-a1-crust.bin`) und
  lässt den MIPS-Knoten an. `CRUST_DEFCONFIG` steht in `board.env` (build-rootfs.sh und boards/check.sh lesen nur dort;
  der erste Bau brach in Schritt 7 daran ab). Die andere Variante (`projector09220931`, 624 MHz) braucht vor einem
  Standby eine eigene crust-Konfig.
- Installation über Stock-Android: FEL per `adb reboot efex` (adb über USB braucht eine udev-Regel oder einen
  adb-Server als root); `h713-install` mit dem kleinen Pflichtabzug in den Paketordner, Herstellerdateien aus der
  vorhandenen Extraktion von Marcos Abzug (nur gelesen). Rückvergleich: Secure Storage byte-gleich, HDCP-1.4-Satz da.
- Am Gerät: "crust is running", contract v5, build2 "DRAM 792 MHz, board 3"; EDID angenommen und zurückgelesen,
  HPD-Ablauf an Port 0 komplett; HDMI 1080p60; Senke `0x93=0x45`. Leistung aus (Gate) mit diesem Abbild 2,4 W, mit
  Stock-Android 0,3 W (Marco, TODO 2.32).

## 2 Der schwarze Reload - was es nicht war

Reload über `h713-mips-restart` (Treiber `0231`/`0239`): Bildpfad nach 3,7 s, Firmware ready, HDMI-Signal erkannt,
Lampe und Lüfter an, Wand schwarz - bei allen 7 Neustarts, die Marco an der Wand beurteilt hat, mit und ohne Quelle,
einer davon über Park und U-Boot-Start (Leiter).
Widerlegt, jeweils am Gerät:

| These | Messung |
|---|---|
| Panel-Takt/LVDS/Timing/Panel-Strom-Pins verstellt | PLL N+1 36, LVDS 8 bit, Mixer 1360x760, PF6/PH16 high - gleich wie gut |
| Kompositionsfenster `0x05000434/438/534/538` | nach dem Reload anders; von Hand auf gut gesetzt: schwarz. Am HY310 stehen die "schlechten" Werte schon vor dem Reload, mit Bild |
| Firmware ohne TSE-Tabellen, Standard 1080p | `E/TSEXX ... magic code incorrect` steht im elog des guten Boots genauso (beide Logs inhaltsgleich), am HY310 auch; kein 1080p-Wert nur im schwarzen Zustand |
| TCON-Latch fehlt (U-Boot `h713_disp_latch_panel_timing`) | Latch-Puls von Hand: schwarz; der Rasterzähler läuft auch im guten Zustand bis ~1019 |
| Startweg | Park + U-Boot-Start: schwarz |
| Reset des Panels | PH16 2 ms low: schwarz |

Blockvergleich gut/schwarz (je zwei Abzüge, Zähler herausgefiltert, 15 bzw. 5 Blöcke der Anzeigekette und CCU): bis auf
Status- und Zählerworte gleich; `0x05000a00` Bit 3 und afbd `0x05600184` Bit 0 sind Live-Status (nicht schreibbar).

## 3 Was es war

Nach dem Reload PF6 300 ms low, dann high (U-Boots `h713_disp_stock_panel_power`-Pin, Stock `panel_power_en`):

| Lauf | nach dem Reload | Bild |
|---|---|---|
| 1 | PH16-Puls | nein |
| 1b | PF6-Zyklus + PH16-Puls | ja |
| 2 | PF6-Zyklus + PH16-Puls | ja |
| 3 | nur PF6-Zyklus | ja |

Behebung (Paket `patches/kernel-panel/`): `sun50i-h713-mips` nimmt optional `panel-power-gpios`/`panel-reset-gpios`
(angefordert wie U-Boot sie ließ) und schaltet nach jedem Start, der "ready" meldet, das Panel aus und an wie U-Boot
beim Boot (300 ms aus, an, 20 ms, Reset 2 ms). Der Gerätebaum des Boards nennt PF6 (aktiv high) und PH16 (aktiv low).
Dafür musste PF6 in die Pin-Tabelle des H713 (`pinctrl-sun50i-h713.c` kannte in Bank F nur PF0-PF5; ohne PF6 bleibt die
Probe mit -517 hängen und der ganze MIPS-Treiber ungebunden). Mit Modul, Gerätebaum und Kernel (PF6) als Schnell-Deploy
(FIT nach `/boot`, Modul in `updates/`, Sicherung `/root/sicherung-panel/`): drei Reloads über `h713-mips-restart`, je
"panel supply cycled (300 ms off), reset pulsed", Bildpfad 3,15-3,21 s, Marco: Bild jedes Mal da.

## 4 Eigene Fehler dieses Abends

- Eine Zeile über den Schreib-Port des UART-ESP (2000) landete in Marcos laufender Konsole (`ping`); danach nur noch 2001.
- Der erste elog-Leser starb an SIGBUS: `/dev/mem` auf Gerätespeicher nur wortweise lesen.
- Der erste PF6-Eintrag kam nie im Baum an (Muster wegen `IRQ_BANK(0xe…)` nicht getroffen, der Fehler lief im Hintergrund
  unbemerkt), danach ein Vollbau umsonst. Der Handbau im build-all-Baum ist nicht inkrementell (TODO 5.17).
- Eine 1080p-Erklärung und eine Rasterzähler-Deutung wurden vor der Gegenprobe ausgesprochen; beide widerlegt.

## 5 Was bleibt (TODO 1.4)

- In die Serie: PF6 in der Pin-Tabelle, Panel-Zyklus im MIPS-Treiber + Pins im Gerätebaum, Kommentar in `0246`.
- Testabbild `geucrust2` mit `--standby` (build-all erlaubt `--standby` heute nur für bestätigte Boards); im Standby
  bleibt PB5 (Lüfter-Schiene) auf diesem Board noch an.
- Auf dem HY300 noch offen: HDCP-1.4-Paar mit Quelle, HDCP 2.2, Ton über HDMI, Standby.
- Die Box läuft `geucrust1` + Schnell-Deploy (Kernel mit PF6, Gerätebaum mit Panel-Pins, Modul), WLAN `.245`,
  UART-ESP `192.168.8.105` (2000 schreiben, 2001 lesen).
