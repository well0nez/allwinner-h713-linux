# 187 - Offline-RE A, B, C ausgewertet: Stock-"Aus" über PL6, TVCAP bleibt im Standby an, die SKE-Zeile ist die cost-tick-Zeile (10.10.2026)

**Kurz:** Die drei Cloud-Aufträge aus TODO 8.10 (privates Repo `well0nez/h713-offline-re`, Zweige `a-aus`, `b-einschlafen`,
`c-loglevel`) haben geliefert: A und B direkt auf ihren Zweig (`cf89e87`, `a1b202f`), C als Pull Request
(`c-loglevel-ergebnis`, `424e64a`). Alle drei Berichte sind reine Listing-Analysen, **nichts davon am Gerät gemessen**. Die
tragenden Aussagen habe ich gegen das Material selbst nachgeprüft (Abschnitt 4); sie halten. Ergebnisse in einem Satz je
Thema: **A** - das Hersteller-"Aus" ist ein Reset in einen Wartezustand, in dem die ARISC-Firmware die eine Freigabeleitung
**PL6** (vdd-cpu, vdd-sys, vcc-pll, vcc-dram) auf low legt und allein wach bleibt; **B** - der Herstellerkernel schaltet die
TVCAP-Power-Domain im Standby nie ab (ihr Tabelleneintrag ist leer), und sein Audiotreiber hat keine PM-Haken; **C** - die
Firmware gibt den Funktionsnamen `MsgHandle_SKE_SEND_EKS` nie aus, die Zeile `HDCP Process cost tick` **ist** der Beweis für
SKE_Send_Eks. Lokale Kopie aller Zweige: `arbeit/cloud-re-20261010/repo`.

## 1 A - "Aus" wie Stock (TODO 2.32)

Material: Stock-Kernel 5.4.99 des HY310 (ELF, kallsyms), Stock-BL31 des HY310, Hersteller-ARISC-Firmware des
HY300PRO-G-EU und des HY310, Stock-Gerätebaum des G-EU.

| # | wer | Schritt | Beleg |
|---|---|---|---|
| 1 | Kernel | `kernel_power_off` -> `machine_power_off` -> `pm_power_off` = `psci_sys_poweroff` -> SMC `0x84000008`; kein Treiber schaltet auf dem Weg Schienen, keine Nachricht an die ARISC | `psci_0_2_init` setzt `pm_power_off` |
| 2 | BL31 | `system_off`: RTC-GP2 (`0x07090108`) := **2**, Nachricht an die ARISC Typ **0x24** ("sys op") mit Argument 1, dann `wfi` | BL31-Ladeadresse `0x48000000`, `system_off` bei `+0xe0c`, Nachricht `+0x6704` |
| 3 | ARISC | "sys op 1": CEC-Einstellung in RTC-GP4, dann **Watchdog-Reset des SoC** (R_WDOG `0x07020400`) | ARISC `0xe9e8`, `0xcd70` |
| 4 | BL31 | nach dem Reset sieht der Monitor (SMC `0x8000ff14`, Aufrufer boot0/U-Boot) GP2 = 2, lädt und startet die ARISC und schickt Typ **0x19** ("fake poweroff") | BL31 `+0x682c`, `+0x67c8` |
| 5 | ARISC | Wecker scharf (Power-Taste PL4 als EINT mit 50 ms Entprellung, IR, CEC, BT-Taste), ARM-Kerne aus, LEDs, DRAM-Controller in Self-Refresh, PLLs aus, Busse auf Quelle 0, Oszillatorbits; **PL6 low**, wenn GP2 = 2; dann Schlafschleife | ARISC `0xeaa8`, `0xdef0`, PL6 bei `0xe20c`-`0xe38c` |
| 6 | ARISC | Wecken: **PL6 high**, 10 ms, GP2 := **0xf**, 5 ms, Watchdog-Reset -> gewöhnlicher Kaltstart | ARISC `0xd6cc`, `0xeb88`-`0xebd4` |

Der Kaltstart nach Netz-Ein läuft durch dieselbe Weiche: bei GP2 = 0 liest BL31 `/box_start_os0 : start_type` und wählt
Wartezustand (GP2 = 2) oder Hochlaufen (0xf) - das Stock-Gegenstück zu unserem `h713_gate`. RTC-GP5 benutzt die
Herstellerkette nicht; unsere Wörter dort (`RUN1`, `GATE`, `STBY`) kollidieren also nicht. Kein RTC-Alarm als Weckquelle.

Was daraus folgt: Die 0,3 W des Stock-"Aus" kommen nach dem Code aus **PL6 low** - alle vier Versorgungen hängen an dieser einen
Leitung, im Stock-Baum des G-EU **und** des HY310 (`standby_param`: `vdd-cpu`, `vdd-sys`, `vcc-pll`, `vcc-dram` = `"PL6"`,
`power_key = "PL4"`, LEDs PL0/PL1). Die ARISC läuft nach PL6 low weiter, ihre Domäne hängt also nicht daran. Unser crust schaltet
PL6 heute nirgends; der Unterschied 2,4/2,9 W gegen 0,3 W ist damit erklärt, aber **nicht gemessen**. Der Bericht schlägt zwei
Wege vor: crust übernimmt "Aus" nach Stock-Muster (eigene Anforderung statt Gate-Schleife), oder das Gate bleibt, und nur der
dunkle Wartezustand wandert in crust. Beides ist Thema der Besprechung 1.1b/2.32.

Nebenbefund: Die vorbereiteten OR1K-Listings im Cloud-Repo waren Müll - die ARISC-Binärdateien aus dem Abzug liegen **wortweise
byte-vertauscht** (jedes 32-Bit-Wort little-endian abgelegt, der Kern ist big-endian), und `objdump` lief ohne `-EB`
(`referenz/irrwege.md`).

## 2 B - Einschlafen und Aufwachen beim Hersteller (C1, TODO 2.37)

Material: derselbe Stock-Kernel und die Module `sunxi_tvtop`, `cpu_comm_dev`, `hidtvreg_dev`, `mcu_comm_dev`,
`snd_alsa_trid`.

- **TVCAP-Domäne:** In `tv303_pm_domains` (Stock-Kernel `0xc0ea3dac`, 5 Einträge zu 7 Wörtern) haben `pd_gpu`, `pd_tvfe`,
  `pd_ve`, `pd_av1` echte Werte, der Eintrag von **`pd_tvcap` ist ganz Null**. Mit diesem Eintrag ist `power_off` für TVCAP ein
  Nicht-Ereignis (kein Registerzugriff), `power_on` läuft in ein 10-ms-Timeout mit Fehlermeldung. Der Hersteller hat den
  Hänger C1 (TVCAP aus, während die Schreib-DMA der Aufnahme läuft) also vermutlich nicht, **weil er TVCAP gar nicht
  abschaltet** - nicht, weil er die Aufnahme in der richtigen Reihenfolge anhält. Einen Aufnahme-Stopp vor dem Suspend gibt es in
  den gelieferten Teilen nicht (die nicht gelieferten Module `decd`, `ge2d_dev`, `demux_dev` und der Hersteller-Userspace
  bleiben offen). Prüfbar am Stock-Gerät: `dmesg` sollte `failed to set domain 'pd_tvcap'` zeigen.
- **MIPS-Park** im Stock in der Phase `suspend` (wir: `suspend_late`), vom eingebauten `mipsloader`: Shared-Memory-Register
  `0x03061024/28` sichern, dann Soft-Reset, Bus-Gate, Cold-Reset, Bus-Reset, MIPS-Gate einzeln - **ohne Wartezeiten** (wir: je
  12 ms). Das Resume lässt den Kern im Soft-Reset; gestartet wird später aus dem Userspace, mit Pausen von 20-25 µs.
- **`cpu_comm`** schickt im Suspend nichts an die MIPS; es baut die gemeinsame Region schon beim Einschlafen neu auf und
  schreibt beim Aufwachen `0x03061024 := 0x4e300000`, `0x03061028 := 0x500000`.
- **TV-Top:** `sunxi_tvtop_suspend`/`_resume` schreiben nur eine Logzeile; `.complete` ruft einen HDCP-SMC (Inhalt nicht
  untersucht). Die Arbeit steckt in den Ein-/Ausschaltfolgen der Teilmodule (Referenzzähler): beim Wiedereinschalten von TVCAP
  die TV-Top-Wörter (`0x01111117`, `0x404`, `0x00111111`, Setzen-Löschen-Setzen wie U-Boot) und danach **`0x06940000 := 1`**
  (INCAP); beim Einschalten von TVFE Resets, Takte mit festen Raten, drei Pausen von 10-15 ms und **`0x06700000 := 0x003003ff`**
  (TVFE-Top) - bei uns nicht dokumentiert.
- **Audio-DSP:** `snd_alsa_trid` hat **keine** PM-Haken (Plattformtreiber nur mit `probe`/`remove`). Einen Neuaufbau des DSP nach
  dem Aufwachen gibt es im Stock-Kernel nicht; wenn er stattfindet, dann im Userspace oder als Nebenwirkung der TVFE-Folge.

## 3 C - Log-Stufe der Display-Firmware (TODO 2.36)

- `0x8B150068` ist `elog_output(level, tag, file, func, line, fmt, ...)` (EasyLogger-Abkömmling). Die `MsgHandle_*`-Strings sind
  **Funktionsnamen-Argumente**, keine Meldungen. Der Aufruf in `MsgHandle_SKE_SEND_EKS` (`0x8B13AE84`) hat Stufe 1 und das Format
  `port%d HDCP_base:0x%x HDCP Process cost tick:%d` - die einzige Aufrufstelle dieses Textes im Abbild. Die anderen
  `MsgHandle_*`/`AKE_*`-Aufrufe sind reine Fehlerpfade.
- Die Format-Masken je Stufe werden beim Start fest auf `0xA7` gesetzt (LVL, TAG, TIME, Datei, Zeile - **ohne** `FUNC`); nichts
  sonst schreibt sie. Der Funktionsname erscheint deshalb auf **keiner** Stufe.
- Folgerung: Die Zeile `HDCP Process cost tick:643` am G-EU (`doku/184`) **ist** die SKE_Send_Eks-Zeile; die Log-Stufe war nicht die
  Ursache. Die Zeile vom 05.10. am HY310 (`doku/152`, `docs/subsystems/hdcp.md`: `... MsgHandle_SKE_SEND_EKS ... HDCP Process
  cost tick:108`) hat keinen Rohmitschnitt, der den Funktionsnamen zeigt; sie war offenbar aus Listing und Log zusammengesetzt.
  Der Beweis bleibt derselbe, nur das Suchwort war falsch: gesucht wird `HDCP Process cost tick` (bzw. `THDMIRx_HDCP22.cpp`).
- `display_cfg.xml` setzt die Log-Einstellungen einmal beim Start (`<elog_init_setting>`: output, route, mode, level,
  async_display, tag_level); Werte außerhalb des Bereichs hängen die Firmware (Assertion mit Endlosschleife). Was U-Boots
  `elog=` tut, ist im Bericht offen.
- Gegenprobe am Gerät (nur lesen, noch nicht gemacht): Wort bei physisch `0x4B48BE84` muss `0x000000A7` lesen.

## 4 Wie nachgeprüft wurde

- **C:** im Listing `0x8B13AE5C`-`0x8B13AE84` gelesen (`li a0,1`; `a3` -> `0x8B1F7434` = `MsgHandle_SKE_SEND_EKS`, Format
  `0x8B1F744C`); die Strings an diesen Offsets stimmen; genau eine Stelle lädt das Format; Masken-Init `0x8B151058`-`0x8B15108C`:
  Basis `0x8B48BD9C`, `fmt_set[0] = 0`, `fmt_set[1..5] = 0xA7`. Im Journal und in `arbeit/` keinen Rohmitschnitt mit
  `SKE_SEND_EKS` gefunden.
- **A:** Byte-Vertauschung nachgeprüft (Strings wie `fake poweroff req`, `standby_param` erscheinen erst nach dem Tausch); mit
  unserem `or1k-elf-objdump -EB` selbst disassembliert - **identisch** mit dem korrigierten Listing des Berichts. BL31 `+0xe0c`
  (GP2 := 2, `bl 0x6704` mit Argument 1, `wfi`) und `+0x6704` (Typ-Byte 0x24) gelesen. ARISC: PL6-Abschnitt (`0xe20c`ff: GP2 == 2
  oder `power_down`, dann je Schiene Ausgang setzen und Datenbit im R_PIO löschen), Watchdog-Reset `0xcd70` und die Weckfolge
  `0xeb88`ff gelesen. `standby_param` im Stock-Baum des HY310 nachgesehen: dieselben Pins wie am G-EU.
- **B:** `tv303_pm_domains` aus dem Kernel-ELF selbst ausgelesen (Eintrag 2 sieben Nullen, die anderen vier gleich gebaut);
  Relokationen der Treiberstruktur `snd_trid_driver` gelesen: nur `probe`, `remove`, Name, Modul, `of_match_table`.
- Nicht nachgeprüft: die Einzelschritte von `0xdef0` (A, 4.4) und die Takt-/Reset-Folgen von `tvtop` (B, 3.2) im Detail; sie
  sind Grundlage für Versuche, nicht für Aussagen.

## 5 Was daraus wird

- **2.32 / 1.1b:** "Aus" über crust heißt im Kern **PL6 low** aus crust, nachdem DRAM und ARM-Seite sicher unten sind, Wecken
  über PL6 high und Reset. Erster Versuch als Bankmessung am HY310 mit Wattmeter (Ziel 0,3 W), in einer Kopie und erst nach der
  Besprechung mit Marco.
- **C1 / 2.37:** Versuch: die TVCAP-Domäne im Systemschlaf nicht abschalten (wie Stock) und dann prüfen, ob der INCAP-Stopp
  vor dem Suspend noch nötig ist; die TVFE-Folge (Pausen, `0x06700000 := 0x003003ff`) gegen unseren msp-Neuaufbau halten.
- **2.36:** Messregel und `docs/subsystems/hdcp.md` korrigiert (Suchwort `HDCP Process cost tick`); offen nur die Gegenprobe
  `0x4B48BE84 = 0xA7` am Gerät.
- Das Cloud-Repo kann weg, sobald Marco es löscht; alles liegt im lokalen Klon.
