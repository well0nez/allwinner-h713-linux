# 101 — Plan: HDMI-Audio als Treiber (Kernel + Codec + hy310-tv)

**Stand 08.09.2026, 21:10.** Voraussetzung erfüllt: der Weg HDMI-RX → MSP-DSP → Codec → Lautsprecher läuft per Skript, alle
Mechanismen sind verstanden ([`100`](100-plan-hdmi-audio.md) §7, [`nachtlog/S16`](nachtlog/S16-hdmi-audio.md) ab 15:45, S25–S27).
Ziel dieses Plans: dasselbe ohne `/dev/mem`, aus Kernel und `hy310-tv`, abgenommen am Gerät. Arbeitsweise wie bisher: Opus-Agenten
liefern Patches aus Arbeitskopien, die Hauptsitzung spielt ein, baut im Container, testet am Board.

## 1. Architektur

```
HDMI-RX (MIPS-Firmware, autonom) ──I2S──► MSP-DSP1 (Insel 0x0614xxxx) ──I2SOUT1──► Codec-I2S-Fenster 0x02031000 ──► DAC ──► HP-Amp ──► Lautsprecher
   │ Status: Fs, Vorhandensein, Nicht-PCM         │ Patch, Graph 0xC1 ohne DELAY1,             │ „DAC Source" = I2S, Rate folgt Quelle
   ▼ (Paket D: V4L2-Controls + Ereignisse)         ▼ Lautstärke/Stumm (Paket B: ALSA-Card)      ▼ (Paket C: Codec-Patch)
                          hy310-tv (Paket E): Audio folgt dem Bild, ctl audio/volume/mute
```

| Paket | Inhalt | Ort im Kernel/Userspace | Patch |
|---|---|---|---|
| **A** CCU | `pll-periph0` wie H616 (`.m` Bit 1, `.p` Bit 0, `fixed_post_div 2`); `audio_cpu/umac/ihb` als Div+Mux mit echten Eltern; TVFE-/Audio-Gates (0xd80 Bits 31/30, `bus-demod` Reset) — A1-Vorarbeit `0134` einarbeiten | `drivers/clk/sunxi-ng/ccu-sun50i-h713.c`, `include/dt-bindings/clock/sun50i-h713-ccu.h` | `0134` |
| **B** MSP-Treiber | Insel hochfahren, Patch laden (Mailbox-Protokoll §7.1), Graph `0xC1` ohne DELAY1, ALSA-Card **nur mit Controls** (`HDMI Audio Switch`, `HDMI Playback Volume` (TLV, ¼ dB), `HDMI Mute Switch`), Status in debugfs/sysfs, Selbstheilung (Mailbox-Timeout → Insel-Reset → neu) | neu `sound/soc/sunxi/sun50i-h713-msp.c` (+Kconfig/Makefile), Firmware `h713/msp-patch.bin` | `0137` |
| **C** Codec | zweites Fenster `0x02031000`, I2S-Init (S25 §2), Control `DAC Source` {APB, I2S} (S25 §4.2, DAC/HP ohne PCM an), Control `I2S Rate` {32000, 44100, 48000} (DAC_FIFOC-Ratenfeld + Takte) | `sound/soc/sunxi/sun4i-codec.c` (H713-Quirk), Codec-DT-Knoten | `0135` |
| **D** hdmirx | schreibgeschützte, flüchtige V4L2-Controls `H713 Audio Present` (bool), `H713 Audio Rate` (Hz), `H713 Audio Compressed` (bool) aus dem RX-Wrapper (`+0x40`, `+0x56`, `+0x15F`, `+0x160`), 100-ms-Poll, `V4L2_EVENT_CTRL` bei Änderung, debugfs-Zeile | `drivers/media/platform/sunxi/sun50i-h713-hdmirx/sun50i-h713-hdmirx.c` | `0136` |
| **E** hy310-tv | Audio-Zustandsautomat: Capture läuft ∧ Audio vorhanden ∧ PCM → Codec `I2S Rate` = Fs, `DAC Source` = I2S, MSP Switch an; Verlust/Wechsel/Nicht-PCM → MSP Mute, Source = APB; `ctl audio on\|off\|auto`, `ctl volume N` (0…100 → dB-Kurve), `ctl mute on\|off`; README | `userspace/hy310-tv/main.c`, `README.md` | Patchdatei |
| **F** DT + Firmware + Doku | Knoten `audio-dsp@6144000`, Codec-Fenster, Firmwaredatei installieren, `50-befehle` Betrieb, `00-STATUS` | dtsi, `/srv/h713-rootfs/lib/firmware/h713/` | `0138` (Hauptsitzung) |

## 2. Schnittstellen (verbindlich für die Agenten)

- **ALSA-Card des MSP** (`snd_card_new`, Kurzname `hy310hdmi`, Langname `HY310 HDMI Audio`, kein PCM): `HDMI Audio Switch` (bool), `HDMI Playback Volume`
  (integer 0…400 = −100…0 dB in ¼ dB, TLV `DECLARE_TLV_DB_SCALE(-10000, 25, 0)`, wirkt auf DSP `0x0052/0x0053` Maske `0xFFC0`), `HDMI Mute Switch`
  (bool, DSP `0x0050/0x0051 = 0x8000`). sysfs unter dem Gerät: `state` (`off|booting|patched|running|error`), `levels` (QPEAK `0x00B2/0x00B3`),
  `reset` (write → Insel-Reset + neu). debugfs `h713-msp/status`.
- **Codec-Controls** (auf der bestehenden Karte `H713 Audio Codec`): `DAC Source` (enum `APB`, `I2S`), `I2S Rate` (enum `32000`, `44100`, `48000`).
- **hdmirx-Controls** (private CIDs ab `V4L2_CID_USER_BASE + 0x1090`, Namen exakt `H713 Audio Present`, `H713 Audio Rate`, `H713 Audio Compressed`),
  alle `V4L2_CTRL_FLAG_READ_ONLY | VOLATILE`, Ereignis `V4L2_EVENT_CTRL` bei Wertänderung.
- **Firmware**: `/lib/firmware/h713/msp-patch.bin` = `re/work/audio/patch_msp.bin` (2896 B, unverändert), `MODULE_FIRMWARE("h713/msp-patch.bin")`.
- **DT-Knoten (Vorschlag, Paket B legt fest):** `compatible = "allwinner,sun50i-h713-msp"`, `reg` Mailbox `0x06144000 0x20`, Audio-Top `0x0614a000 0x10`,
  Steuerung `0x06142000 0x80`, AUDIF `0x06146000 0x90`, TVFE-Router `0x06700000 0x100` (Überschneidung mit `tvtop@5700000` prüfen →
  ggf. `syscon`), `clocks` `bus-demod` (+ `resets` `RST_BUS_DEMOD`), `audio-cpu`, `audio-umac`, `audio-ihb`, `tvfe_1296m` und die übrigen
  TVFE-Takte aus `dsp_island2.py TVFE_CLKS`, `power-domains` `pd_tvfe`; `assigned-clock-rates` 400/200/200 MHz.

## 3. Mailbox-Protokoll (aus S16, Pflicht für Paket B)

1. Schreiben: Busy-Bit 4 in `+0x00` abwarten (Timeout 50 ms), Wort `addr<<16 | val` nach `+0x0C`; 8-Bit-Register über `addr | 0x8000`.
2. Lesen: `addr<<16` nach `+0x10`; fertig, wenn Ready-Bit 5 gesetzt **und** Bit 31 in `+0x10` gelöscht, nachdem das Ausstehend-Zeichen einmal
   gesehen wurde (Bit 31 kommt synchron); Timeout 50 ms ⇒ Fehler ⇒ Selbstheilung.
3. Patch: Strom in MSPM-Blöcke zerlegen (`4D53=504D`-Kopf), **Block ohne Lesung schreiben, nach jedem Block genau eine Lesung** (`0x00EE`),
   voller Strom (DSP2-Blöcke mitschreiben). Vorher `0x00EE` Maske `0x7F80 := 0x0180`, `0xFFF7 := 0`, `0x0000 := 0`, 200 ms. Erfolg:
   `0x80FF = 1`, `0x0001 = 0x0C19`. Referenz `re/captures/weltneuheit/s16-audio-20260908/mbx.c` (`dl -R -s 3 -K`, 20/20).
4. 24-Bit-Register: `0xFFFF := low8`, dann `addr := high16` — dazwischen keine Lesung. Keine Lesungen während laufender Blockübertragung.
5. Insel: `bus-demod` Reset anlegen/lösen, Takte, Router `0x06700000 := 0x003003FF`, Audio-Top `0x0614A000 |= 0x700`,
   `0x0614A00C := (alt & 0xFF000000) | 0x001A5E00`, dann `|= 0x01000000`; **300 ms** bis zum ersten Mailbox-Zugriff (ROM-Boot).
6. Graph (S23/S16): `0x0002 |= 0x8000`; `0x8034` Maske `0x90 := 0x10`; `0x0012 := 0x8180`; `0x0013` Maske `0xFF00 := 0x2000`; `0x0118 := 0x1617`;
   `0x8062 := 0x92`, `0x8063 := 0x93`; `0x0096 := 0x7273`; `0x0090 := 0x9A9B`; `0x8052 := 0x98`, `0x8053 := 0x99`; `0x0036 := 0x6263`;
   `0x0020 := 0x6263` (VOLUME → I2SOUT1, DELAY1 umgangen); `0x0052/0x0053` Maske `0xFFC0 := 0`; `0x0050/0x0051 := 0`; `0x001E := 0xA440`;
   `0x001F` Maske `0xF93F := 0x3000`; `0x8017` Maske `0x01 := 0`. Nicht-PCM-Erkennung: `0x0008 |= 0x8000`, `0x800A` Bit 5.

## 4. Regeln für die Agenten

- **Nie** in `mainline/`, `mainline/patches/`, `userspace/`, `tftp/`, `re/vendor/` schreiben. Kein Board, kein Container-Bau des aktiven Baums.
- Arbeitskopien: `analyse/audio/arbeit/t-<paket>/a/<pfad>` (Original aus `mainline/build/linux-6.18.38-a3097ce7…/`) und `b/<pfad>` (geändert);
  Patch `patches/NNNN-<titel>.patch` als `diff -Nur a b` mit Pfaden relativ zur Baumwurzel (`git`-Stil `a/… b/…`), Kernel-Stil (Betreff, Begründung,
  Belege mit S-Nummern), `Signed-off-by` weglassen. Userspace analog aus `userspace/hy310-tv/`.
- Kernelcodestil, keine `/dev/mem`-Hilfen, keine Magic-Zahlen ohne Kommentar mit Quelle (S16/S23/S25/S27, Register mit Adresse).
- Bericht `doku/nachtlog/S<nr>-treiber-<paket>.md` (≤ 200 Zeilen): was gebaut, offene Annahmen, wie testen. Abschlussmeldung ≤ 25 Zeilen.

## 5. Abnahme (Hauptsitzung, am Gerät)

1. Bau im Container, Module + Firmware installieren, Kaltstart (TFTP prüfen), `dmesg`: MSP `patched`/`running`, keine Timeouts.
2. Dauerton 48 kHz → Mikro 1 kHz ≥ 70 dB; 44,1 und 32 kHz ebenso (Rate folgt automatisch); `ctl volume 50/100`, `ctl mute on/off` messbar.
3. Quelle aus/an, `ctl resync`, Modewechsel 720p/1080p, HDMI-Stecker ziehen/stecken: Ton kehrt ohne Handgriff zurück, keine Störgeräusche.
4. 20 × `ctl audio off/on` und 20 × Kaltstart-Simulation (Modul entladen/laden): stabil. `echo 1 > reset` (Selbstheilung) → Ton zurück.
5. 30 min Dauerton: kein Aussetzer; `levels` plausibel. Lippensynchronität: Sichtprüfung Marco (Stock nutzt 2 ms Verzögerung).

**Stand 08.09. 22:05 — §5 vollständig abgenommen (Serie 110, Baum `d5fd82a7` = GUT-Stand, Belege S16 19:35–21:40):**

| Punkt | Ergebnis |
|---|---|
| 1 Kaltstart | ✅ 19:54: Patch geladen (`0x80FF = 1`), `running`, 0 Timeouts |
| 2 Ton/Raten/Regler | ✅ Rate folgt 32/44,1/48 kHz (150 `levels`-Lesungen dabei: 0 Timeouts); Mikro (Nor-Tec): Lautstärke 60 → −18,4 dBFS, 40 → −33,6 (−15,2 dB, Soll 14,6), Stumm → −67,8 (Raumpegel), 44,1/32 kHz nur per Pegelmesser |
| 3 Quelle/Resync/Modus/Stecker | ✅ IEC958-aus/an: Ton nach 2 s zurück; `resync`: zurück; 720p↔1080p: zurück (Zuspieler schaltet dabei seinen IEC958 ab — Messaufbau); `HDMI-2 --off/--mode`: stumm/zurück nach 4 s |
| 4 Zyklen/Reset | ✅ 20× `audio off/auto`: 20/20, 0 Timeouts; `echo 1 > reset` bei Ton: Patch neu geladen, Ton nach 1 s; Modul 20× entladen/laden (`modul_zyklen.sh`, `hy310-tv` gestoppt): 20/20, je 1,7 s, Patch jedes Mal neu geladen, 0 Timeouts |
| 5 Dauerlauf/Lippensynchronität | ✅ Dauerlauf 20:47–21:16 (28,7 min protokolliert, Beamer stumm, Pegelmesser 1203–1229, Automat an): 58/58 Proben `running`, 0 Timeouts, 0 Heilungen; Lippensynchronität: **Sichtprüfung Marco 22:05 mit YouTube-Video: „perfekt, synchron“** |

Messfalle: Bis 20:30 lief das Mikro der C920 — deren Sprachverarbeitung lässt einen Dauerton als schwankende 1-kHz-Linie (996–1006 Hz)
20 dB unter dem Spielpegel nachklingen, auch nach Stumm und Quelle-aus. Das sah wie ein Leckpfad aus. Messmikro ist das Nor-Tec-Streaming-Mikro
(`mic_fft.py`, jetzt Rate aus dem WAV-Kopf statt fest 32000).

## 6. Ablauf

Welle 1 (parallel): A, B, C, D, E in Arbeitskopien. Welle 2 (Hauptsitzung): Einspielen 0134–0138, Bau, Board, Abnahme; Rückläufe an die
Agenten bei Fehlern. Welle 3: Doku (`00-STATUS`, `50-befehle`, `60-offen`, Handoff), cstenger-Rückmeldung.

## 7. Verlauf Welle 2 (Hauptsitzung)

- 08.09. 22:30–23:10: Patches eingespielt — `0134` (A), `0135`/`0135b` (C), `0136` (D, Patch aus der Agentenkopie erzeugt; DT-Teil als `0136b`
  auf 0135b/0138 rebasiert), `0137` (B), `0138` (DT aus B's Fragment); Defconfig `CONFIG_SND_SUN50I_H713_MSP=m`; Snapshots
  `patches-snapshots/20260908-2230/2245/2255/2305-*`. Bau ohne Warnungen in den geänderten Dateien; **Netboot-Kernel** (`KERNEL_CONFIG=netboot`)
  Baum `1f3614a1`, FIT `tftp/h713-kernel-netboot.fit.1f3614a1`. Falle: ein `.dtsi.orig`-Hunk in 0136b ließ `build.sh` still abbrechen (rc 0,
  nur „extract + patch" im Log) — Patches vor dem Einreihen auf `.orig`/`.rej` prüfen.
- `hy310-tv` mit E's Patch (main.c 3662 Zeilen, libasound) querbaut (0 Warnungen), Original gesichert als `userspace/hy310-tv.vor-audio-20260908/`.
- Agentenabbrüche: A, C, D, E stallten am Stream-Watchdog; A/E per Fortsetzungsagent, D aus der Kopie abgeschlossen; C's Patches waren fertig, Bericht S30 liegt vor.
- **18:50–19:25 (Zeiten korrigiert, S16):** Baum `365bffdf` am Gerät — Codec-Regmap-Falle behoben (zweiter `devm_regmap` verdrängte den
  Komponenten-Regmap → `regmap_init_mmio(NULL, …)` + `devm_add_action_or_reset`), Ton aus dem Treiberstapel 75,9 dB, Automat folgt 32/44,1/48 kHz.
- **19:35–20:00, Serie 110, Baum `d5fd82a7`:** letzter Mailbox-Punkt geschlossen — Leseanfragen werden gelegentlich nicht registriert
  (Status `0x20`, kein Ausstehend-Zeichen, vor allem nach den 8-Bit-Schreibungen des Pegelmessers). `0137` wiederholt die Anfrage nach 50 µs
  (max. 40×, außerhalb des Downloads), Zähler `mbox_reissues`. Messung: 150 `levels`-Lesungen während Ratenwechseln 32/44,1/48 → 0 Timeouts,
  25 Wiederholungen. Abnahme §5 läuft ab 20:00 mit leisem Prüfton (−30 dBFS, Lautstärke 25, Nachweis über DSP-Pegelmesser).

**Befund Gerätetöne (21:35, S16):** Der Codec-DAC nimmt nur eine Quelle. Bei laufendem HDMI-Ton ist `aplay -D hw:0,0` unhörbar (500 Hz auf
Rauschpegel), bei abweichender HDMI-Rate wird es abgewiesen (`hw params`). Ein PC-Zuspieler hält seinen HDMI-Audiostrom dauerhaft offen
(PipeWire, 44,1 kHz Stille) → Gerätetöne kämen mit PC-Quelle nie durch. Stock mischt im DSP: Pfad `0x89` `HDMI2PCM_MIXED_TO_SPEAKER`
(S23 §5): HDMI → `MIXER2.in2/in3`, Linux-PCM → Audio-Bridge ISTREAM → `DECODER3` → `MIXER2.in0/in1` → DRC1 → … → I2SOUT1.
**Nächstes Paket (Vorschlag, eigener Plan 102):** Audio-Bridge-Treiber (ALSA-PCM-Wiedergabe auf Karte `hy310hdmi`, DMA-Ring ARM → DSP,
RE: `legacy/drivers/audio/bridge/`, `snd_alsa_trid.ko`, S20/S23) + Graph `0x89` im MSP-Treiber statt `0xC1`; ein Regler bleibt der Codec.
