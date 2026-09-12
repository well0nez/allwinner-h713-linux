# Die Debug-Shell der MIPS-Displayfirmware

Gefunden über cstengers Baum (`github.com/cstenger/allwinner-h713-mainline`, Branch
`h713-display-video-path`, Commits `ff48f28c`, `6dc63e47`, `9f70bcb5`), auf unserem Gerät
verifiziert und um den vollständigen Befehlsindex ergänzt.

## Zugang

`display.bin` fährt denselben Kommandoparser auf zwei Threads: `shell_thread_uart` über UART4
(dessen Pinwege wir nicht haben) und `shell_thread_monitor` über einen **Ringpuffer im DRAM**.
Der ist ARM-seitig erreichbar, und darüber läuft alles Folgende.

Das Protokoll ist SEGGER-RTT-artig. Ein Zeiger bei System **`0x4B232C20`** verweist auf den
Kontrollblock; bei uns steht dort `0xABD01000` (MIPS kseg1) = System **`0x4bd01000`**:

```
+0x00  acID[16]        "RV\0\0\0\0 TERMINAL\0"
+0x10  MaxNumUp    (3)
+0x14  MaxNumDown  (3)
+0x18  aUp[3]      je 24 Byte {sName, pBuffer, SizeOfBuffer, WrOff, RdOff, Flags}
+0x60  aDown[3]    dito
```

Live gemessen: `aUp[0]` Puffer `0x4bd01300` Größe `0x41c00`, `aDown[0]` Puffer `0x4bd01200`
Größe `0x100`. Adressumrechnung MIPS→System: kseg0/kseg1 minus `0x80000000` bzw. `0xA0000000`,
plus `0x40000000`. Zeilenende `\r` (die Tastentabelle bindet `0x0d` und `0x0a`).

**Falle, die einen Anlauf kostet:** der MIPS-Carveout kommt über `/dev/mem` als **DEVICE**-Speicher.
Auf arm64 sind dort nur ausgerichtete 32-Bit-Zugriffe erlaubt. Pythons `mmap`-Slicing ist ein
`memcpy` und stirbt mit SIGBUS — **nichtdeterministisch**, weil es davon abhängt, welchen
memcpy-Pfad die Länge wählt. Jeder Zugriff muss durch eine ctypes-uint32-Sicht.

Werkzeug: `analyse/hdmi-seq/mipsshell.py` (`--status`, `--drain`, `--cmd "…"`), läuft auf dem Board.

## Zwei Ausgabekanäle

Das **Kommandogerüst** (Befehlsliste, `help`, Prompt `VS:/$`) antwortet über den Ring. Die
**Rümpfe der Debug-Kommandos** schreiben über die Logfunktion der Firmware ins **elog**. `cmds`
kommt also zurück, `win wm` nicht — dessen Ausgabe steht im elog. Beide Kanäle mitlesen.

## Befehlsindex — vollständig, von der Firmware bestätigt

Zwei Wege führen zum selben Ergebnis, und beide sind gegangen: die Tabellen im Abbild auszählen
(12-Byte-Einträge `{Handler, Name, Hilfetext}`, mit Nullen abgeschlossen — `allcmds.py`, idalib)
und **das nackte Kommando absetzen**, denn jedes druckt seine eigene Hilfe. Ins elog, nicht in den
Ring; deshalb sieht man nichts, wenn man nur den Ring liest.

**Oberste Ebene** (aus `cmds`): `app  bs  crtc  tcd3  dtv  hal  elog  memory_agent  pq  regw
regr  clear  keys  vars  cmds  users  help  setVar  win`

| Kommando | Unterbefehle | Tabelle |
|---|---|---|
| **`app`** | `set_src` set source · `dump_para` dump app top parameters · **`dump_cfg` dump display_cfg.xml** · `sm_on`/`sm_off` seamless · `cb_on`/`cb_off` call back · **`win_on`/`win_off` window manager** · `tfd_on`/`tfd_off` tfd update · `set_ll` low latency · `set_pm` picture mode · `set_wm` wide mode · `set_mm` mirror mode | `8B1EB550` |
| **`bs`** | `dump_bs` Dump BlueScreen Status | — |
| **`crtc`** | `dump_cfg` dump CRTC config · `stop_frl`/`start_frl` freerun lock | `8B1F0AAC` |
| **`tcd3`** | **`dump_sig` dump signal status** · `dbg` debug mode of mode detection · `pause`/`resume` mode detection · `mo` motion detection | `8B1F82AC` |
| **`dtv`** | `set_ds` set dtv stop · **`get_fb` get dtv frame info** | `8B1F8EA0` |
| **`hal`** | **`dump_src` dump context of hal_source** · `set_src` set source · (`vbi`, `atvsnow` stehen in der Tabelle, nicht in der Hilfe) | `8B1F9288` |
| **`memory_agent`** | **`en` enable memory agent (0-9 / all)** · **`dis` disable …** | `8B1FBB24` |
| **`pq`** | `set_fc` set free mode wait max count | — |
| **`win`** | `os` set overscan · `rn` set refresh node · **`wi` get all win size info** · **`wm` get win mgr info** | `8B207298` |

Ohne Unterbefehle, Argumente direkt: `regr`/`regw` (Register **aus Sicht des MIPS**), `elog`,
`setVar`, `clear`, `keys`, `vars`, `users`, `help`, `cmds`.

Kleinigkeit am Rande: `dtv`s Hilfetext ist mit „Usage: seamless" überschrieben — ein
Kopierfehler der Firmware, kein Hinweis auf etwas.

## Gemessene Ausgaben (07.09.2026, HDMI-1 mit 1080p)

`hal dump_src` → `hal_source_id: kHalSourceID_HDMI_1`
`app dump_para` → `picture_mode:1`
`app dump_cfg` → **leer** (die 852×480 kommen nicht aus `display_cfg.xml`)

`win wm`:
```
m_src_cfg        : [0, 0, 30720, 17280][0, 0, 30720, 17280]
m_dst_cfg        : [0, 0, 30720, 17280][0, 0, 30720, 17280]
m_src_active_win : [0, 0, 1920, 1080]
m_dst_active_win : [0, 0, 1920, 1080]
m_aspect_ratio 0 · mb_seamless 0 · m_mirror_mode 0 · m_refresh_node 0
data base: hde 1920 vde 1080 hs 44 vs 5 h_back_porch 88 v_back_porch 20
```
`m_src_cfg` bewegt sich **nicht**, wenn wir `Wce_SetWindow` mit anderen Werten senden — der RPC
endet MIPS-seitig in einem Stub (cstenger `9f70bcb5`, bei uns nachgemessen).

`crtc dump_cfg` (Panel):
```
PANEL TIMING   pclk 143001 kHz · hs 44 · vs 5 · h_back_porch 88 · v_back_porch 20
               h_total 2128 · v_total 1120 · frame_rate_max 59999
MAIN CRTC      m_tfd_cfg[0]  source 0 · pclk 143001 · htotal 2200 · phase_delay 70 · pll_divider 2
               m_final_cfg[0] dwRatioN 2 · dwRatioM 1 · htotal 2128 · vtotal 1120
               in_vtotal 1329..1358 · out_vtotal 1120..1120
```

`tcd3 dump_sig` gibt den **ATV/CVBS**-Detektor aus (`m_cvd_st`, SECAM/PAL-Erkennung,
`kAtvStd_NoSignal`) — für den HDMI-Pfad ohne Aussage.

## Was daran wertvoll ist

`win wm` liefert den Zustand des Fenstermanagers (`m_src_cfg`, `m_dst_cfg`, `m_src_active_win`,
`m_dst_active_win`, `m_refresh_node`, Panel-Timing); `win wi` die Geometrie aller fünf
Fensterknoten. `bs dump_sig` und `hal dump_src` geben den Signal- bzw. Quellenzustand aus Sicht
der Firmware. `memory_agent en/dis` schaltet genau den Baustein, der bei einer
Descriptor-Veröffentlichung die Aufnahmefreigabe löscht (`doku/86` §4). `app dump_cfg` schüttet
`display_cfg.xml` aus — die naheliegende Spur zu der Zielgeometrie 852×480, auf die die Firmware
bei einem eigenen Neubau verfällt.

`regr`/`regw` sind die Sicht des MIPS auf den Registerbus — nützlich für Register, die von der
ARM-Seite anders oder gar nicht aussehen.

## Sicherheit

Lesende Kommandos (`dump_*`, `wi`, `wm`, `cmds`, `help`, `keys`) sind ungefährlich. `set_*`,
`*_on`/`*_off`, `en`/`dis` und `regw` verändern den laufenden Zustand der Anzeige — nur mit
Sichtkontakt zur Wand und mit einem Rückweg (Quellenwechsel, im Zweifel Neustart **plus**
Quellenwechsel; ein Neustart allein hat nach einem Firmware-Neubau nicht gereicht).
