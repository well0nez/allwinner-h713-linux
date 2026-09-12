# Plan 104 — Einschalt-Gate Stufe 2: Stock-Standby über die ARISC

**Status: geparkt (Marco 10.09. 01:30, niedrige Priorität), Vorarbeit S39/S40 abgeschlossen.** Nutzen ehrlich: < 1 W statt 4 W (≈ 25 kWh/Jahr), Wecken per
Fernbedienung/CEC, Sofort-an in 2–3 s. Für das Release ([`105`](105-plan-release.md)) nicht nötig; Fernbedienungs-Wecken geht billiger über
IR-Polling in der Gate-Schleife (103 §2.2 Option 1b). Vor einem Start: 104 §2 Schnittstellen ausformulieren, Welle 0 (S41 Weckweg, S42 MIPS/Parameterblock).
Stufe 1 ([`103`](103-plan-einschaltgate.md)) bleibt der Rückfall: Bereitschaft 4 W, Betrieb 47 W. Stufe 2 soll die 4 W deutlich unterbieten
und Wecken per Fernbedienung und CEC bringen. Faktenbasis: [`nachtlog/S39`](nachtlog/S39-re-stock-standby-ablauf.md) (Stock-Ablauf Ende zu
Ende, statisch aus Firmware und BL31 dekodiert), [`S35`](nachtlog/S35-re-arisc-standby-led-key.md) (Taste, LED, DTB-Parser).

## 1. Wie der Stock schläft (S39 §1, Kurzfassung)

1. Der Stock-Kernel hat keinen eigenen Standby-Code; er ruft BL31, BL31 spricht die ARISC über Msgbox **Port 3, Typ `0x22`** („cpu op req")
   an. Nutzlast fünf Wörter: `{mpidr, entrypoint, cpu_state, cluster_state, system_state}`; der Rahmen ist Kopfwort, `count`, dann die Daten.
2. Die ARISC schaltet Schienen und LED (rot), fährt den DRAM in Selfrefresh, schläft (`wait wakeup`) und wartet auf PL4 (EINT), CIR PL9
   (Codes aus `cir_param`) oder CEC — Weckquellen werden mit `0x25`/`0x26` gesetzt und gelöscht.
3. Beim Wecken: DRAM hochfahren (mit CRC-Prüfung, Fehlzweig = Endlosschleife), Schienen an — **nur wenn RTC-GP2 == 2** —, Resume-Adresse
   aus `paras[1]` nach `ALT_RVBAR_LO/HI`, CPU0 freigeben. Der Weckgrund kommt als Antwortwort (kein Register).
4. Der DTB-Zeiger kommt über **RTC-GP3** (nicht aus `arisc_para`); `0xb00f` in GP3 ist eine Fortschrittsmarke der laufenden Firmware.
   `arisc_para` wird von der DRAM-Standby-Routine trotzdem gelesen (Flags `+0x4c`, `+0x5c` Bit 16) — Layout ab `+0x4c` offen.

## 2. Was fehlt (S39 §4, als Pakete)

| Paket | Ebene | Inhalt | Beleg |
|---|---|---|---|
| H1 | TF-A | `get_sys_suspend_power_state` + Systempfad in `sunxi_pwr_domain_suspend`: Parameterblock füllen (`entrypoint` = Resume in BL31), Typ `0x22` auf Port 3, `WFI`; Resume-Pfad, danach Quittung Typ `0x11`. Msgbox-Treiber für H713 übersetzen (heute `SUNXI_PSCI_USE_SCPI := 0` mit `$(error)`-Riegel). Idle-Zustände optional. | S39 §4 #1–#5 |
| H2 | Kernel | ARISC-Treiber: Weckquellen setzen/löschen (`0x25`/`0x26`), Weckgrund entgegennehmen, `arisc_para` korrekt (Flags `+0x4c`/`+0x5c`), **DTB-Zeiger nach GP3** schreiben, damit `standby_param`/`cir_param` ankommen; Suspend-Ops; Taste und IR als `wakeup-source`. | S39 §4 #6–#9 |
| H3 | U-Boot | GP2 := 2 setzen wie der Stock (sonst keine Schienen nach dem Wecken); Resume läuft **nicht** durch U-Boot (Start bei `ALT_RVBAR`), Gate-Logik nur beim echten Kaltstart. | S39 §4 #16 |
| H4 | ARISC | Stock-`scp.bin` unverändert weiterverwenden; keine Firmware-Arbeit. | S39 §4 #10 |
| H5 | Userspace | `h713-tv`: vor dem Suspend HDMI-Capture und Audio stoppen, nach dem Resume MIPS-Zustand prüfen (siehe R7), Bild und Ton wieder anwerfen; `systemd` `HandlePowerKey=suspend` statt `poweroff`, `poweroff` bleibt Stufe 1. | — |
| H6 | Messung | Verbrauch im Standby; Weckzeit; 20 Zyklen. | 103 M5 |
| **H7** | Kernel | **MIPS-Suspend/Resume wie Stock:** die ARISC kennt die MIPS nicht (S40 §B, mit Positivkontrolle), die MIPS überlebt den Selfrefresh nicht. Stock: `mipsloader_suspend` → `mips_powerdown`, `mipsloader_resume` → `mips_reset` (+ Neuladen), an `mipsloader_pm_ops`. Bei uns fehlt das ganz (kein mipsloader, `cpu_comm` ohne PM-Ops). Neues Paket: PM-Ops in `cpu_comm`/tvtop-Teil: vor dem Suspend MIPS anhalten, nach dem Resume Reset + Firmware und Workspace neu laden (heute macht das U-Boot: `h713_mips.c`), dann SetSource und h713-tv-Neuaufbau. Fünf Schritte in S40 §B. | S40 |

## 3. Risiken (S39 §5) und was zuerst zu klären ist

- **R7 geklärt (S40):** Die ARISC fasst die MIPS nicht an; sie überlebt den Selfrefresh nicht → Paket H7 (Reset + Neuladen aus dem Kernel).
- **R1 `arisc_para` ab `+0x4c`:** Stock-Speicherabbild `0x00104008` (128 B) aus laufendem Stock-Android ziehen (braucht den Stock-Stand auf dem
  Gerät oder einen Dump) und mit unserem genullten Block vergleichen.
- **R2 erledigt (S40):** Stock-BL31 baut Kopf `state=2, attr=0, type=0x22, count=5` + Zeiger auf die fünf Wörter (`monitor.asm` 6541 ff., Sender `0x60a0`).
- **R13 neu (S40):** `set_wakeup_src` (`0xc830`) ist im Standby-Pfad wirkungslos — der Zuordner `0xc7c8` nimmt nur `0xffffffe0`, übergeben wird `p[0] & 0x3ff`; Feldaufbau `p[0]` = {Typ 31..30, C 29..20, B 19..10, A 9..0}, Typ 3 = Weck-Zeitgeber. Wie Taste/IR im Stock tatsächlich als Weckquelle scharf werden, muss vor H2 geklärt werden (S40 §7). R9–R12 siehe S40.
- **R6 kein Watchdog, DRAM-CRC-Endlosschleife:** jeder Versuch mit UART und Steckdose; nie auf Selbsterholung warten.
- **R8 FEL als Rückweg** vorher einmal prüfen.

## 4. Reihenfolge

1. ~~Statische Reste aus S39 §6~~ erledigt (S40). ~~R7~~ geklärt (S40).
2. R1 (Parameterblock ab `+0x4c`) und R13 (echter Weckquellen-Weg) klären, ohne Bauarbeit; Stock-`mips_reset` disassemblieren (S40 §7).
3. H3 + H2-Teil „GP3/arisc_para" (klein) → prüfen, dass die ARISC `standby_param` liest (Konsole `standby service ok` ohne `ERR:no cir_param`).
4. H1 (TF-A) als Agentenpaket, dann erster Standby-Versuch am UART: `echo mem > /sys/power/state`, Wecken per Taste.
5. H5, H6, dann IR/CEC-Wecken.

## 5. Abnahme

Standby-Verbrauch gemessen (Ziel < 1 W), Wecken per Taste in < 3 s mit Bild und Ton, Wecken per Fernbedienung, 20 Zyklen, `poweroff`
weiterhin ins Stufe-1-Gate, Kaltstart weiterhin ins Gate.
