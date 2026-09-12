# Plan: HDMI-Audio — vom Zuspieler über den HDMI-Eingang zum Lautsprecher

**Stand 08.09.2026, 12:25.** Nächster Schritt nach dem Bildpfad. Marco: Fable 5.1 plant, orchestriert und
verifiziert; Opus-5-Agenten machen die RE- und Code-Arbeit. Board (192.168.8.141), Zuspieler (192.168.8.162)
und `mainline/patches/` fasst nur die Hauptsitzung an. Protokoll: `nachtlog/S16-hdmi-audio.md`, Agentenberichte
`S17`…`S20`. Rohdaten `re/captures/weltneuheit/s16-audio-20260908/`.

## 0. Ziel und Abnahme

Ein Ton, der am Zuspieler über HDMI-2 gespielt wird, kommt aus dem Lautsprecher des Beamers. Gemessen mit dem
Webcam-Mikrofon am Arbeitsrechner (C920, `parecord`, FFT): 1-kHz-Sinus ≥ 40 dB über dem Rauschgrund, Tonhöhe
±0,5 %, danach Musik hörbar sauber (kein Knacken, keine Aussetzer über 60 s). Audio folgt dem Bild: an, wenn
`hy310-tv` das Bild zeigt, still bei Konsole. Latenz Bild↔Ton später messen (Ziel < 100 ms).

## 1. Was steht (gemessen 08.09., 11:50–12:20)

| | Stand | Beleg |
|---|---|---|
| **Ausgabepfad** Codec → HP-Verstärker → Lautsprecher | **läuft** auf unserem Board: cstengers Patches `0082`–`0086` (Karte 0 `h713-audio-codec`, `pcmC0D0p`). `speaker-test 1 kHz` am Board → Mikro-Spitze 1001 Hz, **83 dB** über dem Rest | `s16-audio-20260908/mic-speakertest-1khz-board.wav` |
| **Messkette** Mikro + FFT | steht (`parecord --device=alsa_input.usb-046d_HD_Pro_Webcam_C920_…`, 32 kHz, numpy-FFT) | dito |
| **Quelle sendet Audio** | erst nach `xrandr --output HDMI-2 --set audio on` **plus Modeset**: dann ELD gültig (`eld#2.3`, „SGD SX8", 2 SADs), PipeWire-Profil `output:hdmi-stereo-extra1` verfügbar, Ton gespielt. Unser EDID trägt Basic Audio + LPCM 8 ch 32/44.1/48 kHz | Zuspieler `/proc/asound/card0/eld#2.3` |
| **Reaktion am Board** | **keine sichtbare:** MIPS-elog Stufe 5 zeigt beim Ton keine `Audio N/CTS`-Zeilen (nur `reset system_pd_audio_t`, `HdmiRxAEC_Enable bEnable = 1` beim Einrasten); Audio-Top-Register `0x06146000` (AUDIF), `0x06148000` (AUDBRG), `0x06144000` (DSP-Mailbox), `0x0614a000` lesen **0**, auch nach Setzen der CCU-Gates `0xd48/0xd4c/0xd50` Bit 31 und `0xd80` Bit 0 | `elog-audio1-hdmi-ton-ohne-audiozeilen.txt` |
| **Firmware-Anteil (MIPS)** | `display.bin` enthält den HDMI-RX-Audiotreiber (`THDMIRx_TV303_Audio_Driver.cpp`): APLL-Berechnung aus N/CTS, `HdmiRx_AEC_Enable`, `SetHandlerOnNewAudioInfoPacket`, ARC-Pfade (`TurnOnARCAudioPath`, `SwitchARCTXPath`) | `strings display.bin` |
| **Stock-Pfad** (aus DTB, Legacy-Port, März-RE) | HDMI-RX → **AUDIF** `0x06146000` (SPDI1/2-Eingänge, I2SO/ABPO-Ausgänge, **IRQ 113**) → **AUDBRG** `0x06148000` (OSTREAM-Ringe = Capture, ISTREAM = Playback, Delaylines, **IRQ 115**; Zuordnung laut S19 — im `dtsi` vertauscht) → **MSP-Audio-DSP** (Mailbox `0x06144000`, Firmware `patch_msp` aus `libmspsound.so`, ARM↔MIPS-Mutex `0x02031078/0x02032078`) → I2S → Codec-DAC (`DAC_DPC` Bit 29 = I2S-Quelle) → HP-Amp → Lautsprecher. Stock-ALSA-Karte `TridentALSA` (`snd_alsa_trid.ko`) | `legacy/drivers/audio/bridge/`, `re/notes/AGENT_HANDOFF_AUDIO_MIPS_DSP.md`, `re/notes/PHASE3_AUDIO_PLAN.md` |
| **Blocker von März** | „MIPS App Ready = 0" — **entfällt**: unsere MIPS-App läuft (cpu_comm 4/4, RPCs, Rückrufe) | doku/97 |
| **Takte** (Linux-Sicht) | `hdmi-audio`, `bus-hdmi-audio`, `audio-cpu/umac/ihb`, `i2s2`, `owa0-rx` alle `en=0`; Stock-`tvtop` fährt `audio_cpu` 400 MHz, `audio_umac`/`audio_ihb` 200 MHz, `hdmi_audio_clk` **1152 MHz** — unser CCU-Modell hat dafür nur AHB-Gates (Bit 31) mit Parent `ahb` 100 MHz; die Felder in `0xd48` (`0x2`), `0xd50` (`0x7`) sind unbeschrieben | `legacy/drivers/tvtop/sunxi_tvtop_data.c`, `ccu-sun50i-h713.c` |
| DTS bei uns | `audio_bridge@203042c` (`vs,trid-audio-bridge`, `status = "okay"`, kein Treiber bindet), `i2s2@2034000` (`CLK_HDMI_AUDIO` als „pll_tvfe") und `spdif@2036000` (`CLK_HDMI_AUDIO`, `owa0-rx`) `disabled` | `sun50i-h713.dtsi` |

**Material:** Stock-Modul `re/vendor/HY310-DEV/stock_modules/modules_full/snd_alsa_trid.ko` (arm32), Stock-Libs
`re/vendor/HY310-DEV/stock_audio_libs/` (`libmspsound.so`, `libmspdriver.so`, `libhalsound.so`,
`audio.primary.ares.so`, `libtinyalsa_audio.so`), Stock-`vmlinux` symbolisiert (`re/vendor/HY310/extracted/vmlinux.elf`,
IDA-DB `re/ida/HY310/extracted/vmlinux.elf.i64`), `display.bin` (`re/ida/HY310-DEV/display.bin`, IDA-DB
`re/ida/weltneuheit/re_chain/display.bin.i64`), Stock-DTB `re/vendor/HY310/extracted/bootpkg-full.dts`, Legacy-Port
`legacy/drivers/audio/` (Codec/CPU-DAI/Machine + `bridge/`), März-Notizen `re/notes/{audio,PHASE3_AUDIO_PLAN,
PHASE3_CODEC_RE,AGENT_HANDOFF_AUDIO_MIPS_DSP,AGENT_TASK_AUDIO_BRIDGE_FIXES}.md`, cstengers `docs/audio.md`,
`docs/hdmi-in.md`, `docs/handoff-2026-09-02-audio-hdmi.md` (im Git `mainline`, Commits `a0545ff`, `64439d6`, `e844f42`).

## 2. Architektur — zwei Stufen *(Stand 14:15: Stufe 1 gemessen tot, Stufe 2 ist der Weg — siehe §6)*

**Stufe 1 (Ziel dieses Plans): Capture-Schleife ohne DSP.** Kernel-Treiber `sun50i-h713-audbrg` (Mainline-Stil:
Takte/Resets/IOMMU aus dem DT, keine `/dev/mem`-Pokes) stellt den HDMI-Audiostrom des AUDBRG als **ALSA-Capture**
bereit (OSTREAM-Ring → PCM). `hy310-tv` (oder eine Unit daneben) kopiert Capture → Karte 0 Playback und schaltet
mit dem Bild. Messbar in kleinen Schritten: (a) Block lebt, (b) AUDIF sieht den HDMI-Strom (Status/Fs), (c) Ring
füllt sich mit Sinus (numerisch prüfbar), (d) Ton am Lautsprecher.

**Stufe 2 (optional, später): Hardware-Durchleitung wie Stock** über den MSP-DSP (Init-Kette aus `libmspsound`,
`Sound_Path_Connect`), Codec auf I2S-Quelle — keine CPU-Kopie, geringste Latenz, aber DSP-Firmware und
Mutex-Protokoll. Nur, wenn Stufe 1 an Latenz oder Qualität scheitert oder Marco es will.

Nicht Teil des Plans: ARC/eARC, S/PDIF-Ausgang, Mikrofon (nicht bestückt, cstenger).

## 3. Offene Fragen → Agenten

| # | Frage | Wer | Bericht |
|---|---|---|---|
| **F1** | Warum liest der Audio-Top (`0x06144000/6000/8000/a000`) null? Takte (was sind die Felder in CCU `0xd48/0xd4c/0xd50/0xd80/0xd84`, Parent/PLL, Raten aus Stock), Resets, Power-Domäne, Reihenfolge in Stock (`sunxi-tvtop`, `snd_alsa_trid` `REG_Init`, CCU-Treiber im `vmlinux`). Ergebnis: **Einschaltrezept** als geordnete Registerliste | Agent A (RE vmlinux/tvtop/CCU) | `S17-re-audio-top-einschalten.md` |
| **F2** | Was macht die MIPS-Firmware mit HDMI-Audio: schaltet sie beim Einrasten den Audioausgang des HDMI-RX ein (AEC, APLL) oder wartet sie auf einen RPC? Wohin geht der Strom (SPDI1/SPDI2/I2S des AUDIF, Registerschreibungen nach `0x0614xxxx` aus dem MIPS)? Welche HDMI-RX-Register zeigen von der ARM-Seite „Audio da / N / CTS / Fs / Kanäle"? Welche RPCs/Rückrufe gibt es (AudioInfoPacket, Mute, ARC)? | Agent B (RE display.bin) | `S18-re-mips-hdmi-audio.md` |
| **F3** | Capture-Rezept des AUDBRG **ohne DSP**: AUDIF-SPDI-Aktivierung, OSTREAM-Konfiguration (Start/End/Ptr/Step/Cfg), Ringformat, IRQs, Sample-Format/Fs-Erkennung; was davon zwingend den DSP braucht. Ergebnis: Schrittliste zum Handtest (`rd.py -w`) + Treiberentwurf | Agent C (RE snd_alsa_trid.ko + Legacy-Port + März-Notizen) | `S19-re-audbrg-capture.md` |
| **F4** | Stock-DSP-Pfad: HDMI-Quellwahl im Audio-HAL/`libhalsound`, `Sound_Path_Connect`, Minimalkette für „HDMI → DAC", `patch_msp`/Module als Dateien extrahiert; gibt es einen DSP-losen Bypass im Bridge? Codec-I2S-Eingang (`DAC_DPC` Bit 29, Fenster `0x02031000`) | Agent D (RE libmspsound/libmspdriver/libhalsound/audio.primary) | `S20-re-msp-dsp-pfad.md` |
| F5 | Zuspieler: ELD erst nach `audio on` + Modeset — Regel für `wechsel.sh`/Doku | Hauptsitzung | S16 |

## 4. Arbeitspakete

| # | Paket | Abnahme | Abhängigkeit |
|---|---|---|---|
| **A0** | Board: Einschaltrezept aus F1 anwenden, Audio-Top liest sinnvolle Werte; AUDIF-Status bei laufendem HDMI-Ton (F2/F3) | Register ≠ 0, Fs-Anzeige folgt 44,1/48 kHz-Wechsel am Zuspieler | F1 |
| **A1** | Kernel `sun50i-h713-audbrg`: Platform-Treiber (DT `vs,trid-audio-bridge` + Takte/Resets/IOMMU), debugfs-Registerdump, Capture-PCM aus OSTREAM (F3) | `arecord -D hw:1,0` liefert den Sinus (FFT der Datei: 1 kHz) | A0, F3 |
| **A2** | Userspace: Schleife Capture → Karte 0 (zuerst `alsaloop`, dann in `hy310-tv`: `ctl audio on\|off\|status`, an mit Bild, aus bei Konsole) | Mikro misst 1 kHz vom Lautsprecher, Musik 60 s sauber | A1 |
| A3 | Stufe 2 (DSP) — nur bei Bedarf | Latenz/Qualität | F4 |
| A4 | Doku, Handoff, Memory; `wechsel.sh` um Ton ergänzen | | |

## 5. Regeln für die Agenten (Marco, 08.09.: „niemals in aktive Kernel-Ordner, nie echte Dateien patchen")

- **Kein Board, kein Zuspieler.** Messungen nur durch die Hauptsitzung.
- **Nichts unter `mainline/`** — weder `mainline/patches/`, noch die Bäume `mainline/build/linux-*`, noch `mainline/build/out`
  — und **nichts unter `userspace/`**. Auch nicht „nur kurz" oder „nur zum Kompilieren".
- **RE-Agenten** arbeiten lesend; IDA-Datenbanken nur als Kopie in `analyse/ida/db-audio-<name>/` (bestehende `db-*`
  nicht anfassen), Skripte `analyse/ida/ida_a<NN>.py`, Rohausgaben `re/captures/weltneuheit/audio-*-20260908.log`.
- **Code-Agenten** bekommen eine **eigene Kopie** der betroffenen Dateien unter `analyse/audio/arbeit/<paket>/` (die
  Hauptsitzung legt sie aus dem guten Baum an: `a/` unverändert, `b/` zum Bearbeiten) und liefern eine **Patchdatei**
  (`diff -u a/ b/`, Kernel-Stil, mit Beschreibung) plus Notiz nach `analyse/audio/arbeit/<paket>/README.md`.
  Probeübersetzen nur gegen diese Kopie oder eine eigene Kopie des Baums, die sie selbst unter `analyse/audio/arbeit/`
  anlegen — nie im Container-Baum. Einspielen in `series`, Bau im Container, Test am Board: Hauptsitzung.
- Belegt/vermutet trennen, Adressen nennen; ein Kriterium, das nicht scheitern kann, prüft nichts. Berichte auf
  Deutsch nach `doku/nachtlog/`.

## 6. Ergebnisse

- **F1 (S17, 12:50):** Audio-Top hängt am Demod-Bus (CCU `0xd64`); CCU-Treiber-Fehler: `0xd80` Gates sind Bit 31/30,
  `audio-cpu/umac/ihb` und `hdmi-audio` sind Teiler mit PLL-Mux. **Am Gerät (S16, Versuche 1–7):** mit allen 16
  TVFE-Gates + Bus + Router + `audio_top_clk_init` leben Audio-Top-Takt, `0x06142044`, **Mailbox** und **AUDBRG**;
  **AUDIF `0x06146000` hängt das Board bei jedem Zugriff** (4 Hänger) → F1b (S21) läuft.
- **F3 (S19, 13:15):** DSP-loser Capture-Pfad laut `snd_alsa_trid.ko` **ja**: SPDI1 → OSTREAM0 fest verdrahtet,
  Scharfschaltung kurz (AUDIF `+0x00 = 0x300052`, `+0x08 = 0x400`, `+0x04 |= 0x300052`, `+0x38 = 0x3000`,
  `+0x34 = 0x90000000`; AUDBRG START/END/STEP/`CFG = 0x2207`, `+0x390 = 0`, Flush, IRQ-Bit 4), Zeiger `+0x118`, Ring
  `0x10000`. I2S2/OWA0 sind **kein** Weg (externe Pins; owa1 = ARC-Sender). Korrekturen: IRQs vertauscht, SPDI hat
  vier Register je Kanal.
- **F4 (S20, 13:25):** Stock-Quellwahl HDMI = Pfad `0x89` (`Sound_Path_Connect`), HDMI-Audio betritt den DSP **als I2S**
  (`DSP[0x8034]`), Minimalkette = `sound_lowlevel_init` → `DSP[0x00EE]` Takt → Firmware `patch_msp` (2896 B, extrahiert
  nach `re/work/audio/`) → `DSP[0x0002]` Bit 15 → HDMI-Rx ein → Codec `DAC_DPC` Bit 30+29. **Bypass ohne DSP: nein**
  für Lautsprecher; für OSTREAM-Capture ebenfalls nein (Widerspruch zu F3) — Messkriterium: OSTREAM-Zeiger bei
  laufendem HDMI-Ton ohne DSP beobachten. `sound_preset.bin`/`libmsp_util.so` fehlen im Repo. MIPS ist nur
  Mutex-Partner; für den HDMI-Zulauf (APLL/AEC) bleibt F2.
- **F2:** Agent zweimal beim Start hängengeblieben, dritter Anlauf läuft (S18). **F1b (S21)** läuft: was fehlt dem AUDIF.
- **Board 13:09:** OSTREAM0 auf freiem Puffer konfiguriert, HDMI-Ton an — Zeiger steht (ohne SPDI1-Freigabe erwartet).
  IOMMU ist bei uns **an** (Kernel-Log); Treiberentwurf S19 §9 entsprechend anpassen.
- **F5 (S23, 14:40):** `sound_preset.bin` (60480 B) und `libmsp_util.so` liegen in `super.fex` →
  `vendor_a` → `/vendor/etc/` bzw. `/vendor/lib/`; extrahiert nach `re/work/audio/stock/` (ohne sudo/mount:
  Sparse entpacken, LP-Metadaten, `debugfs`). Preset-Format und `gActionTable` entschlüsselt.
  **Pfad `0x89` = `HDMI2PCM_MIXED_TO_SPEAKER`; HDMI-Audio kommt auf `I2SIN1` (`0x9600`, DSP `0x0012/0x0013`,
  Quellcodes `0x16/0x17`) an**, Ausgang `I2SOUT1` (`0x9A00`, DSP `0x0020`, Format `0x001E = 0xA440`,
  `0x001F = 0x3000`). Vollständige Registerliste (26 Verbindungsschreibzugriffe + Grundzustandsaktionen)
  in S23 §4; der kürzere Stock-Pfad `0xC1` `HDMI2PCM_TO_SPEAKER` braucht nur 14. `MSPD` hat **0 YBIN**,
  die vier Klangmodule entfallen auf diesem Board.

- **F1b (S21, 13:30) + Board 13:32:** AUDIF hing, weil `audio_top_clk_init` (`0x0614A000 |= 0x700`) nie im selben
  Lauf vor dem Zugriff stand; mit Tor-Prüfung liest AUDIF (echter Slave). **A0 damit erledigt:** ganze Insel erreichbar.
- **Board 13:33:** S19-Handtest SPDI1→OSTREAM0 bei HDMI-Ton: kein Sync, kein Zeiger, Ring leer → der HDMI-RX liefert
  keinen Audiostrom. **Quelle sendet nachweislich** (ACR N=6144/CTS folgt der Bittiefe), aber die Firmware bekommt kein
  `0x3000`-Ereignis, Fs-Messung 0, APLL unprogrammiert (F2/S18; Vertiefung F2b/S22 läuft).

- **Stufe 2 / DSP-Download (Board 13:50–15:05, Protokoll S16):** Insel + Mailbox laufen; die Stock-Sequenz
  (`0x00EE` Takt 3, Reset `0xFFF7/0x0000`, 200 ms, 724 Paare `patch_msp`) endet mit **`DSP1[0x80FF] = DSP2[0x80FF] = 0`**
  — mit/ohne Mutex, mit `audio_ihb` 200 MHz, mit I2S/OWA-Bus-Gates. Mailbox-Format per Disassembly bestätigt; Kernel- und
  Userspace-Init des Stock machen an Audio-Top und Mailbox exakt dasselbe; MIPS-Flags `0x5`, MIPS kennt den DSP nicht; alle fünf
  Power-Domains an; `patch_msp` ist der einzige DSP-Code im ganzen Stock-Abbild (MSPM nur in `libmspsound`). `0xFFFF` ist das
  Low-Byte für 24-Bit-Register (kein Seitenregister); die großen Blöcke sind verschlüsselter Code für einen ROM-Lader.
  **DSP2 antwortet nicht** (konstant `0x0400`, Schreibungen wirkungslos). Fehlend ist ein Hardware-Enable des Kerns
  (Takt/Reset) — **Agent F6 (S24) sucht statisch**; Kandidaten: `0x06142000 = 0x00F003FF` (Bits 19:10 = 0), Mailbox `+0x08 = 0x80000000`,
  weitere Bits in `0x0614A000`. Fünfter Hänger 14:26 (Abtastlauf + `resync` ohne Marker) → Regel: Board-Ausgaben streamen.
- **Für später notiert:** cstenger-Codec exportiert nur `DAC Playback Volume` und `Line Out Source Playback Route` — der
  `DAC Src Select = I2S` (`DAC_DPC` Bits 30/29, Stock `media-speaker-i2s`) fehlt und braucht einen kleinen Codec-Patch.
- **17:05 — DSP1-Patch angenommen (S16):** Ursache war das Mailbox-Protokoll, nicht ein fehlendes Enable: der DSP1-Monitor verarbeitet
  Schreibungen nur, wenn Lesungen folgen. Rezept (`scratchpad/dsp_island2.py --periph1 --quiet --strict --readevery=1 --gap=0 --dsp1only`,
  3/3): Demod-Bus-Reset, Audio-Takte auf pll-periph1 (Stock-Raten), Insel-Rezept, 300 ms, `0x00EE`, Reset, nur Typ-0100-Blöcke mit
  Lesung nach jedem Wort → **`DSP1[0x80FF] = 1`, `0x0001 = 0x0C19`, `0x00FC = 0x21FF`**. DSP2 antwortet nicht (Blöcke übersprungen).
  Graph `0xC1` wird angenommen; **offen: I2SOUT1 → ABPO1 → Codec** (F7/S25) — `0x06146008` ist Puls/Write-only, Codec-I2S-Fenster
  `0x02031000` unkonfiguriert, `DAC_DPC`-Bits 30/29 vom Treiber nicht gesetzt. Nebenbefund: `pll-periph0` bei uns N=50 (VCO 1200) statt
  Stock N=100 (VCO 2400) — ob Vendor-Abgriffe (`-2x`, `2400M`, `800M`) halbiert laufen, ist zu prüfen (betrifft evtl. vincap-dma, i2h, dtmb).

- **17:55–18:05 — HDMI-Ton am Lautsprecher (S16):** Direktroute I2SIN1 → I2SOUT1 und die Stock-Kette ohne DELAY1 (DRC → Klangregler →
  PEQ → VOLUME → I2SOUT1) liefern den 1-kHz-Laptop-Ton am Lautsprecher (Mikro 76–82 dB über Rauschen, Tonhöhe korrekt). Ausgangsseite
  nach S25: Codec-I2S-Fenster `0x02031000` (21 RMW), Codec-I2S Master + RXEN, `DAC_DPC` Bits 30/29, DAC von `aplay`-Stille gehalten.
  Lautstärke: DSP `0x0052/0x0053` (Viertel-dB, Bits 15:6), Stumm: `0x0050/0x0051 = 0x8000`. DELAY1 (`0x8D00`) schluckt das Signal
  (Betriebsart unentschlüsselt) — ist vermutlich die Lippensynchron-Verzögerung; vorerst umgangen.
  **Damit ist der Nachweis erbracht; ab hier Integration** (§7).

## 7. Integration — nächste Schritte (Stand 08.09. 18:05)

1. **Kernel: Treiber für Audio-Insel + DSP** (`sun50i-h713-msp`?): Demod-Bus-Reset/Gates, Audio-Takte auf pll-periph1 (oder CCU-Modell
   korrigieren, A1-Patch `0134` prüfen), Audio-Top `0x700`/`0x011A5E00`, Patch-Download mit Lesung nach jedem Wort (nur Typ-0100-Blöcke,
   Abbruch bei write-busy), Graph `0xC1` ohne DELAY1, Steuer-API: Quelle ein/aus, Mute, Lautstärke (qdB), Status (QPEAK-Pegel).
2. **Codec-Treiber (cstenger-Quirk) ergänzen:** I2S-Fenster-Init (S25 §2), Control „DAC Src Select" (APB/I2S) mit den drei CTL-Bits und
   `DAC_DPC` 30/29, DAC/Verstärker ohne laufenden PCM halten (DAPM-Pfad „I2S In → DAC"), Takte prüfen (pll-audio/codec_dac wie Stock).
3. **hy310-tv:** Audio folgt dem Bild — bei Signal + PCM (RX-Statusnibble, InfoFrame) Quelle einschalten, bei Verlust/Wechsel stumm;
   `ctl volume/mute`; 44,1 kHz läuft (getestet 18:10), 32 kHz offen, Nicht-PCM (kein DSP2) stumm schalten; Resync stört den Ton nicht.
4. **Offen/Risiko:** DSP-Hänger bei fehlerhaftem Mailbox-Verkehr (Insel-Reset als Heilung), `pll-periph0`-VCO (halb?), DELAY1/Lippensynchronität,
   DSP2 (Decoder) tot, Verhalten bei Quellenwechsel/Kaltstart, Lautstärkekurve/Limiter aus dem Preset.

- **08.09. 20:30 — Offene Punkte vor dem Treiber (Auftrag Marco 18:15), Stand:**
  1. **DSP-Hänger: gelöst.** Ursache war das Mailbox-Protokoll des ROM-Monitors, nicht Hardware: Lesungen *innerhalb* eines MSPM-Blocks
     stören (Latch/Codeladung), Lesungen *zwischen* Blöcken sind der nötige Weckruf. Referenz `mbx dl -R -s 3 -K` (C, S16 20:15):
     **20/20** voller Strom inkl. DSP2-Blöcke, 15 ms, `DSP1[0x80FF] = 1`. Die früheren Python-„Erfolge" hatten den Code-Download nie ausgelöst.
     Erholung nach jedem Hänger: Insel-Reset (`0xd64`), 65/65, kein Neustart nötig. Leseregel: Ready-Bit 5 **und** Bit 31 (`+0x10`) gelöscht.
  2. **DELAY1 (S26): geklärt** — im Stock `0x0034 = 0x8488` + vier DRAM-Ringe über AUDBRG/AUDIF; HY310 nutzt 2 ms → Umgehung verlustfrei.
  3. **DSP2 (S27): geklärt** — Effekt-Kern (SRS/DTE/PEQ), für PCM unnötig; wird von DSP1 aus den 0102-Blöcken geladen; Flag bleibt bei uns 0 (nicht nötig).
  4. **pll-periph0 (S27): nicht halbiert** (600 MHz beide); Mainline-CCU-Modell falsch (300) → `ccu-sun50i-h713.c` wie H616 korrigieren (`.m`, `.p`, post_div 2).
  5. **Nicht-PCM:** `DSP1[0x0008] |= 0x8000`, `DSP1[0x800A]` Bit 5 = komprimiert (S27) — im Treiber: stumm schalten.
  6. **TVFE-Gates:** Modewechsel löscht nichts (Wächter); frühere Beobachtung passt zu einem Watchdog-Reset. `pll-audio` wird vom Codec-Treiber gesetzt.
  7. **Quellraten: 32/44,1/48 kHz laufen** (echter Patch), sobald die Codec-Rate (ALSA-Streamrate → DAC_FIFOC) der RX-Fs folgt (S16 20:45).

### 7.1 Regeln für den Treiber (aus S16 18:20–20:45, S25–S27)

- **Mailbox:** Schreiben = Busy-Bit 4 abwarten, `+0x0C := addr<<16|val`. Lesen = `+0x10 := addr<<16`, fertig bei Ready-Bit 5 **und** Bit 31 in `+0x10` = 0
  (Ausstehend-Zeichen muss gesehen werden; Timeout ⇒ Insel-Reset). 8-Bit-Register über Adresse | 0x8000. 24-Bit über `0xFFFF`-Latch, dazwischen **nichts** lesen.
- **Patch:** `patch_msp` blockweise (MSPM-Kopf erkennen): Block ohne Lesung schreiben, **eine** Lesung an der Blockgrenze; voller Strom erlaubt (DSP2-Blöcke
  schaden nicht); Erfolg = `DSP1[0x80FF] = 1`, `0x0001 = 0x0C19`; sonst Insel-Reset und Wiederholung (max. 3). Referenz `mbx.c dl -R -s 3 -K`.
- **Insel:** Demod-Bus-Reset/Gate `0xd64`, Audio-Takte `0xd48/4c/50` (pll-periph1-Elternteil oder korrigiertes CCU-Modell), TVFE-Router, Audio-Top
  `0x700`/`0x011A5E00`, 300 ms ROM-Boot vor dem ersten Mailbox-Zugriff. Insel-Reset ist die Heilung für jeden Mailbox-Hänger.
- **Graph:** Pfad `0xC1` ohne DELAY1 (`0x0020 = 0x6263`), Volumes `0x0052/0x0053` (Viertel-dB), Master-Mute `0x0050/0x0051 = 0x8000`; Nicht-PCM
  (`0x800A` Bit 5 nach `0x0008 |= 0x8000`) ⇒ stumm.
- **Codec:** I2S-Fenster 21 RMW (S25 §2), Master + RXEN, `DAC_DPC` Bits 30/29, DAC an ohne PCM (DAPM); **Codec-Rate = RX-Fs** (32/44,1/48).
- **CCU:** `pll-periph0`-Modell wie H616 korrigieren (`.m` Bit 1, `.p` Bit 0, post_div 2); danach `audio_cpu/umac/ihb` regulär modellieren.

