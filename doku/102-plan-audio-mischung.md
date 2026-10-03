# Plan 102 - Gerätetöne mit HDMI-Ton mischen (Audio-Bridge + Mischgraph)

**Status: in work - built and measured once, not on main** (section 6; filed as a todo 08.09.2026 21:50 by Marco's decision).
Voraussetzung erfüllt: Plan [`101`](101-plan-audio-treiber.md) abgenommen, GUT-Stand `d5fd82a7`.

## 1. Warum

Der Codec-DAC nimmt eine Quelle: I2S (HDMI über den MSP-DSP) **oder** APB (Linux-PCM `hw:0,0`). Ein PC-Zuspieler hält seinen
HDMI-Audiostrom dauerhaft offen (PipeWire, 44,1 kHz Stille) → der Automat bleibt auf I2S, `aplay` ist unhörbar oder wird abgewiesen
(S16 21:35). Stock mischt im DSP (Pfad `0x89` `HDMI2PCM_MIXED_TO_SPEAKER`, S23 §5). Ziel: wie Stock - HDMI und Gerätetöne gemischt,
ein Regler (Codec `DAC Playback Volume`, `h713-tv ctl volume`).

## 2. Was bekannt ist

- Graph `0x89` (S23 §5, Mux-Tabelle vollständig): `I2SIN1 (HDMI) → SURRDEC → SURRPOSTPRO → MIXER2.in2/in3`, `DECODER3.out0/1 → MIXER2.in0/in1`,
  `MIXER2.out0 → DRC1 → … → I2SOUT1`. Register: Mixer-Quellwahl `0x8100…0x8103` (Maske `0xFF`), Mixer-Verstärkung `0x0100…` (Maske `0x00FF`),
  Einspeisung `0x0118` (`0xFF00 ← 0x7C00`). Ob SURRDEC/SURRPOSTPRO im PCM-Fall transparent sind, ist offen (Variante: DECODER3 + I2SIN1 direkt auf MIXER2).
- Linux-PCM in den DSP: Audio-Bridge `0x06148000` (AUDBRG, ISTREAM/OSTREAM, DRAM-Ringe; S17/S20, `legacy/drivers/audio/bridge/`,
  Stock-Modul `snd_alsa_trid.ko`, `libmspsound.so`). Nicht kartiert: Ringformat, Doorbell/Interrupt, wie `DECODER3` den ISTREAM liest, Taktdomäne.
- DSP2 läuft nicht (S27) - falls `MIXER2` oder `DECODER3` auf DSP2 liegen, muss DSP2 gebootet werden (S27: Effektkern, Blöcke Typ 0102 im Patch).
- Mailbox-Regeln und Treibergerüst aus `0137` (Graph-Tabelle, Selbstheilung, Zähler) sind wiederverwendbar.

## 3. Pakete (Agenten in Kopien unter `analyse/audio/arbeit/`, kein Board, keine aktiven Bäume)

| Paket | Inhalt | Liefert |
|---|---|---|
| F | RE Audio-Bridge ISTREAM: Register, Ringformat, Start/Stop, Doorbell; wie `DECODER3` daran hängt; DSP1 oder DSP2 | Bericht S33 + Registerkarte |
| G | RE Graph `0x89` minimal: welche Module für PCM-Mischung nötig sind, Verstärkungen, Stock-Werte aus `audio_mixer_paths.xml` | Bericht S34 + Mux-Liste |
| H | Treiber: ALSA-PCM-Wiedergabe auf Karte `hy310hdmi` (DMA-Ring → AUDBRG ISTREAM), Ratenwandlung oder feste 48 kHz; MSP-Treiber Graph `0x89` | Patches `0139…` |
| I | `h713-tv`: Automat bleibt bei HDMI-Quelle auf I2S, Gerätetöne laufen über das neue PCM; Lautstärke unverändert am Codec | Patch |

## 4. Abnahme

1. HDMI-Ton (−10 dBFS, Lautstärke 60) + `aplay` 500 Hz auf dem neuen PCM: beide Linien am Nor-Tec-Mikro, HDMI-Pegel unverändert.
2. Nur Gerätetöne ohne HDMI-Quelle und mit stiller HDMI-Quelle: hörbar.
3. `ctl volume` regelt beides gemeinsam; `ctl mute` schweigt beides.
4. 20× Wechsel HDMI an/aus während Geräteton läuft, 0 Mailbox-Timeouts; Kaltstart.

## 5. Risiken

DSP2-Abhängigkeit (dann größer), Ringformat der Bridge unbekannt, Latenz der Mischung (Lippensynchronität erneut prüfen).

## 6. State after FB-AUDIO and FB-AUDIOb (26./27.09.2026)

Packages F and G never ran as packages of their own; the journals S33 and S34 do not exist. FB-AUDIO did that
reverse engineering itself (idalib on `snd_alsa_trid.ko` and `audio.primary.ares.so`) and delivers it as
`umbau/work/FB-AUDIO/excerpts/bridge-istream-register-card.txt` (F: the ring registers, CFG 0xAA08, the STEP
interrupt, flush and UMACREQ, the AUDIF frame token, no routing register from an ABPO to a decoder) and
`graph-0x89-mux-list.txt` (G: the eight mux directors, MIXER2 gains 32, DRC source 0x7C7D, DECODER3 untouched
by the preset); the summary is section 2 of `umbau/work/FB-AUDIO/REPORT.txt`. The "not mapped" items of section
2 above are mapped there. Package H is the kernel patches 0169 (the bridge PCM `hw:hy310hdmi,0`, 48 kHz S16_LE
stereo, path 0x89, the control "HDMI Input Mute Switch") and 0170 (the AUDBRG window and both interrupts on the
MSP node); package I is the h713-tv patch 0001 of the same package (the DAC stays on I2S, the codec is parked at
48 kHz, the automaton's silence is the input mute). All three are held out of main until the device test has
settled the driver's two knobs, `istream` and `graph` (`umbau/reviews/FB-AUDIO.md`).

Device test 27.09.2026 (review FB-AUDIO): the bridge PCM is audible on input stream 2 only - the pairing is
istream 2 -> DECODER3, not ABPO1 as inferred - so the default changes to 2 before integration. Items 1 to 3 of
section 4 are met (both lines, the device tone alone with a silent source, volume and mute act on both); the
levels are not: HDMI drops 3.5 dB while the bridge plays and the bridge line is 8.7 dB louder with HDMI active
than alone (the mixer gains 32, DECODER3's pre-gain 0x0162). The graph=2 comparison is the next measurement,
steps 7 (20 x audio off/auto) and 8 (DSP reset) are open. FB-AUDIOb adds the shipped default
(`rootfs/overlay/usr/share/alsa/cards/H713-MSP.conf`, loaded by alsa-lib only while the card is present, and
`/etc/asound.conf` with the names `bridge` and `codec`), the PCM's state in `ctl status` ("audio sounds") and
the plan for removing the knobs (`umbau/work/FB-AUDIOb/excerpts/knob-removal-plan.txt`).
