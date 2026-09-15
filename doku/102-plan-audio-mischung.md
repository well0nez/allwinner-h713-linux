# Plan 102 - Gerätetöne mit HDMI-Ton mischen (Audio-Bridge + Mischgraph)

**Status: TODO, nicht begonnen** (angelegt 08.09.2026 21:50, Entscheidung Marco: als Todo hinterlegen).
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
