# S16 — HDMI-Audio: Materialcheck und erste Messungen (08.09.2026, 11:45–12:30)

Plan: [`../100-plan-hdmi-audio.md`](../100-plan-hdmi-audio.md). Rohdaten `re/captures/weltneuheit/s16-audio-20260908/`.
Agentenberichte (Opus 5, parallel gestartet 12:28): S17 Audio-Top einschalten (F1), S18 MIPS-Anteil (F2),
S19 AUDBRG-Capture (F3), S20 Stock-DSP-Pfad (F4).

## 11:50 Lautsprecherpfad und Messkette — beides steht

`speaker-test -D hw:0,0 -c 2 -t sine -f 1000 -l 1` am Board (Karte 0 `h713-audio-codec`, cstenger `0082`–`0086`,
Mixer `Speaker`, `Line Out`, `DAC`), gleichzeitig `parecord` vom Webcam-Mikro C920 am Arbeitsrechner (32 kHz,
mono, 6 s). FFT: stärkste Linie **1001 Hz**, 1-kHz-Band **83 dB** über dem Median 200–8000 Hz, RMS 8420,
Spitze 17131 (kein Clipping). Damit ist der Ausgabepfad auf unserem Board abgenommen (Legacy-Known-Issue 14
„in series, am Gerät nicht abgenommen" erledigt) und das Mikro ist ein taugliches Instrument.
Datei `mic-speakertest-1khz-board.wav`.

## 12:00 Quelle: Zuspieler sendet erst nach `audio on` + Modeset

- Unser EDID am Zuspieler (`/sys/class/drm/card0-HDMI-A-2/edid`, 256 B, CEA v3): Basic Audio 1, Audio-Block
  `3f 07 50 09 7f 01` (LPCM 8 ch 32/44,1/48 kHz 16/24 bit; zweiter SAD), Speaker-Block `4f 00 00`, HDMI-VSDB.
- Trotzdem: alle ELD-Pins `monitor_present 0, eld_valid 0`, PipeWire-HDMI-Profile „available: no". Nach
  `xrandr --output HDMI-2 --set audio on` **und** einem Modeset (aus/an): `eld#2.3 present=1 valid=1`, Monitor
  „SGD SX8", HDMI, `sad_count 2`. Danach Profil `output:hdmi-stereo-extra1+input:analog-stereo` setzbar, Senke
  `alsa_output.pci-0000_00_1f.3.hdmi-stereo-extra1`, `speaker-test -D pipewire` 1 kHz gespielt (12:16:49 und
  40 s ab 12:17:31). Der Modeset setzt das Profil zurück — Reihenfolge: audio on → Modeset → Profil → Senke.
- Zurückgestellt auf `output:analog-stereo+input:analog-stereo` (12:20).

## 12:10–12:20 Board: keine sichtbare Reaktion

- MIPS-elog Stufe 5 (`elog-audio1-hdmi-ton-ohne-audiozeilen.txt`, 538 Zeilen): beim Einrasten
  `HdmiRxAEC_Enable bEnable = 1` und `reset system_pd_audio_t!!!`; während des HDMI-Tons **keine** Zeile
  `Audio N … CTS …`, `N change`, `audio param` (Strings existieren in `display.bin`). Offen, ob Log-Level oder
  inaktiver Pfad (F2/C).
- Audio-Top-Fenster lesen 0: `0x06146000…7c` (AUDIF) komplett 0, `0x06148384/388/38c/390` 0, OSTREAM/ISTREAM-
  Zeiger 0, `0x0614a000/0c` 0, DSP-Mailbox-Status `0x06144000` 0 — vor und nach dem Setzen der CCU-Gates:
  `0xd48` `0x00000002→0x80000002`, `0xd4c` `0x00000002→0x80000002`, `0xd50` `0x00000007→0x80000007`, `0xd80`
  `0xc0000000` (Bit 0 war schon 1), `0xd84` `0x80000000` (unverändert), `0xd48`… bleiben so gesetzt.
  → Block ist nicht am Netz (Reset? anderer Takt? Domäne? — F1).
- genpd: AV1, VE, TVCAP, TVFE, GPU alle `on`; Linux-Taktbaum: `hdmi-audio`, `bus-hdmi-audio`, `audio-cpu/umac/ihb`,
  `i2s2`, `owa0-rx/tx` `en=0` (Refcount, nicht Hardware — Falle aus cstengers Handoff).
- `hy310-tv`: Bild stand die ganze Zeit (Modeset am Zuspieler → kurzer Konsolenmoment, dann 1080p).

## 21:42 Gegenprobe Quelle: kein Fehler unseres EDID/HPD

`audio` am Zuspieler zurück auf `auto`, dann HPD-Puls vom Board (`echo "hpd 0 down"`/`"hpd 0 up"` nach
`/sys/kernel/debug/h713-arisc/cmd`, 300 ms): Zuspieler liest das EDID neu (256 B, Basic Audio 1), ELD bleibt
**gültig** (`eld#2.3 present=1 valid=1 sad_count 2`), Bild nach dem Hotplug wieder da. Die Nachhilfe von 12:00 war
also ein einmalig veralteter Zustand des Laptops (i915 hatte Audio früher als „nein" bewertet und bis zum
erzwungenen Modeset nicht neu geprüft), kein Fehler unserer Seite. Bleibt: PipeWire meldet das HDMI-Profil weiter
„available: no", lässt es sich aber setzen — Laptop-Eigenheit. Nach dem nächsten Kaltstart des Boards einmal ohne
Nachhilfe prüfen (F5).

## 12:49 Einschaltversuch 1 (S17-Rezept) — harter Hänger

`audio_top_enable.py --do --no-router` (Reset `0xd64` lösen → `audio_cpu/umac/ihb` Gates → `0xd64` Gate → Reset →
`0x06700000` lesen → Audio-Fenster lesen): Board **hart gehängt**, kein Ping, kein ssh; Steckdose 12:52, nach
36 s wieder da, Bild und Dienst normal. Welcher Schritt: unbekannt — die ssh-Ausgabe lief durch `tail` (gepuffert,
mit der Sitzung verloren), das Journal des vorigen Boots endet lange davor (NFS nicht mehr geschrieben), UART lief
nicht mit. Unterschied zum bewiesenen Lauf vom 06.09. (`tvfe_enable.py`, kein Hänger): dort waren **alle 16
TVFE-Gates** an, hier nur die drei Audio-Takte; `tvfe_1296M` (`0xd20`) liest heute **0** (aus).
Lehren: Ausgabe nie durch `tail`, sondern in eine lokale Datei streamen; Marker mit `<3>`; UART mitlaufen lassen.

## 12:56 Einschaltversuch 2 — bewiesene Reihenfolge, Board lebt

`audio_top_step.py --do` (Ablauf wie `tvfe_enable.py` vom 06.09.: **alle 16 TVFE-Gates** `0xd10…0xd60` Bit 31,
dann `0xd64 |= 0x10001`, dann lesen; jede Zeile vor dem Zugriff nach stdout und `<3>`-kmsg, Ausgabe per `tee` in
`scratchpad/audio-top-versuch2.log`): `0xd64 = 0x00010001`, **`0x06700000 = 0x000007ff`**, Board antwortet.
Damit ist der Unterschied zu Versuch 1 eingegrenzt: mit nur den drei Audio-Takten (und `tvfe_1296M` `0xd20` aus)
hängt der Zugriff auf den TVFE-Raum; mit den 16 Gates nicht. Kein UART-Adapter erreichbar (weder hier noch am
Zuspieler — dessen `ttyUSB0…2` sind das LTE-Modem), Zuordnung deshalb über die gestreamten Marker.

## 12:57 Versuch 3 — Audio-Fenster lesen: **AUDIF hängt**, zugeordnet

Nach Versuch 2 (Bus an, Bild lief weiter, Flip-Zeiger wanderten) die Fenster einzeln mit Marker gelesen
(`scratchpad/audio-top-versuch3.log`): `0x0614a000` = 0, `0x06142044` = 0, `0x06144000` = 0 — alle ohne Hänger;
**`0x06146000` (AUDIF) hängt das Board.** Vor dem Einschalten des Demod-Busses las dieselbe Adresse 0 ohne Hänger:
der Bus dekodiert die Region jetzt, der AUDIF-Block selbst ist aber nicht getaktet/aus dem Reset. Steckdose 12:58,
Board nach 35 s zurück. Konsequenz für die Reihenfolge: erst `audio_top_clk_init` (S17 Schritte 11–13, Register
`0x0614a000/0c`, die ohne Hänger lesbar sind) und der TVFE-Router, dann Schreib-Lese-Probe, **erst danach** AUDIF.

## 12:59 Versuch 4 — Audio-Top lebt

`audio_top_step.py --do --router --topclk --probe` (`scratchpad/audio-top-versuch4.log`): 16 Gates, `0xd64 = 0x10001`,
`0x06700000` `0x7ff` → Router `:= 0x003003FF` (liest zurück); **`audio_top_clk_init`**: `0x0614a000 |= 0x700` →
liest `0x700`; `0x0614a00c := 0x001a5e00`, dann `|= 0x01000000` → liest **`0x011a5e00`**; Schreib-Lese-Probe
`0x06142044` Bits 7:0 `:= 0x5a` → liest `0x5a` → **Block lebt**. Board antwortet. Damit ist F1 am Gerät bestätigt:
Demod-Bus + alle TVFE-Gates + Router + Audio-Top-Takte. Was davon genau nötig ist (Router? alle 16 Gates?), bleibt
für den Treiber zu klären; die Reihenfolge ist jetzt eine, die nicht hängt.

## 13:00 Versuch 5 — AUDIF hängt auch mit Audio-Top-Takten

Nach Versuch 4 (Block lebt) die Fenster erneut einzeln (`audio-top-versuch5.log`): `0x0614a000`, `0x06142044`,
`0x06144000` lesbar (0), **`0x06146000` (AUDIF) hängt wieder.** Steckdose 13:02. Also fehlt dem AUDIF eine eigene
Versorgung jenseits von Demod-Bus, TVFE-Gates, Router und `audio_top_clk_init` — Kandidaten: der MSP-DSP-Takt
(S20: DSP-Reg `0x00EE` über die Mailbox), ein Reset im Audio-Top (`0x0614a000` weitere Bits), oder die
MIPS-Firmware (`reset system_pd_audio_t`). Bis F2 (MIPS-Anteil) vorliegt, nur noch Zugriffe auf Register, die
nachweislich lesbar sind (Audio-Top-Takt, Mailbox, `0x06142044`), plus AUDBRG als Frage.

## 13:04 Versuch 6 — Mailbox und AUDBRG leben

Nach Kaltstart erneut Einschalten (16 Gates, Bus, Router, `audio_top_clk_init`, Probe grün), dann
(`audio-top-versuch6.log`): **DSP-Mailbox antwortet** — `0x06144000` = 0, Lesen über `0x06144010` mit Bit 5 sofort:
`DSP[0x0002] = 0x0000`, `DSP[0x00EE] = 0x0200`, `DSP[0x80FF] = 0x0000` (keine Firmware geladen, wie erwartet).
**AUDBRG lebt**: `0x06148100 := 0x00ABCDEF` liest zurück, `0x06148384/388/38c/390/118` = 0. Board lebt.

## 13:05 Versuch 7 — DSP-Takt gesetzt, AUDIF hängt trotzdem

`DSP[0x00EE] := 0x0180` (`SetDSPClockSpeed(3)`) über die Mailbox geschrieben; danach las der Mailbox-Status
**`0x00000010`** (Bit 4 = Write busy blieb stehen — der DSP hat die Schreibung nicht quittiert), und der folgende
AUDIF-Lesezugriff hängte das Board (Hänger Nr. 4, `audio-top-versuch7.log`). Steckdose 13:06. Schluss daraus:
AUDIF hat eine eigene Versorgung, die weder Demod-Bus, TVFE-Gates, Router, Audio-Top-Takt noch der DSP-Takt-Schreibbefehl
liefern; keine weiteren AUDIF-Zugriffe bis F1b (`S21`) und F2 (`S18`) vorliegen. Alles andere (Mailbox, AUDBRG, Audio-Top)
ist ohne Hänger zugänglich.

## 13:09 OSTREAM0-Test ohne AUDIF — kein Datenfluss (erwartet, hängerfrei)

Einschalten (Gates, Bus, Router, Audio-Top-Takt, Probe grün), dann S19-Handtest Schritte 1–2 auf einem freien Puffer
(`P = 0x6d000000`, letztes MiB von `framebuf_reserved`, `no-map`, seit KMS unbenutzt): Ring mit `0xA5` gefüllt,
`0x06142044 = 0x60`, OSTREAM0 `START 0xd00000 END 0xd00fff STEP 0x40 CFG 0x2207`, Sync 0, Flush. Zeiger
`+0x108 = 0xd00040`, `+0x118 = 0xd00000`. Ohne Ton 3 s und **mit HDMI-Ton 6 s: Zeiger unverändert, IRQ-Status 0, Ring
komplett `0xA5`**. Ohne SPDI1-Freigabe (AUDIF, Schritt 3 — nicht zugänglich) fließt nichts; das entscheidet den
Streit F3/F4 (DSP nötig?) noch nicht. Nebenbefund: **die IOMMU ist bei uns an** (`iommu: Default domain type:
Translated`, `video-codec` in Gruppe 0) — S19 §9 nahm sie als aus an; ein Bridge-Treiber muss die IOMMU
mitbedenken (`iommus = <&iommu 6 1>` im Stock-DTB).
Skripte/Logs: `s16-audio-20260908/audio_top_step.py`, `ostream_test.py`, `audio-top-versuch*.log`, `ostream-setup.log`.

## 13:15–13:30 Quelle bewiesen, RX rastet ACR ein, Firmware sieht kein Ereignis (F2-Messplan)

- **Quelle:** PipeWire hatte den Ton nie an die HDMI-Hardware gegeben (alle HDMI-PCMs `closed`, Senke `SUSPENDED`).
  Direkt `speaker-test -D hw:0,3 -r 48000` → `RUNNING 48000`; i915: Pipe B, `HDMI-A-2`, `audio support: yes`,
  **`bpp=36` (12-bit Deep Colour)**. Wrapper-Bytes (S18 §4.1, byteweise): **N=6144, CTS=222750** = 48 kHz bei
  TMDS 222,75 MHz → die Quelle sendet ACR, der RX rastet es ein. `xrandr --set "max bpc" 8` + Modeset → kurz
  N=2/CTS=24 (Reset), dann **N=6144, CTS=148494**. Danach 44,1 kHz (`RUNNING 44100`): N bleibt 6144 — die
  ACR-Bytes folgen nur einmal nach dem Relock.
- **Firmware:** 1-ms-Poll 9 s: `+0x11`/`+0x13` = 0, `+0x40 = 0x07` (Statusnibble 0), **`+0x15F = 0` (Fs-Messung 0)**,
  `+0x56 = 0`, Route `+0x15E/+0x160 = 0`; elog Stufe 5 zeigt Mute-/Relock-Zeilen, aber **keine** `Audio N/CTS`-,
  `PLL CALC`-, `audio param`-Zeile. Alle Wrapper-Bytes gleich dem Stock-Abzug nach HDMI-Start (bis auf unser echtes CTS).
- **Takt-Irrtum korrigiert:** `pll-video3 = 0xb8002f00` → N-Feld 0x2f → VCO **1152 MHz**; `0xd84 = 0x80000000`
  (Teiler 1) war also schon Stock (S17 §5.4 nahm 2400 MHz an). Meine Halbierung `0xd84 := 0x80000001` (13:19)
  brachte nichts und ist zurückgenommen (13:27).
- **RX-Kern:** rk3588-Offsets (`0x1104` ACR, `0x5030` INT) lesen 0 — Registerkarte passt nicht 1:1;
  `MAINUNIT_STATUS 0x0150 = 0x04d4f300`.
- Nächste Frage an F2b (S22): warum kein `0x3000`-Ereignis trotz ACR-Änderung; Test: Port-Neuaktivierung (Rebind)
  bei eingerasteten ACR-Werten.

## 13:31 Port-Neuaktivierung (Rebind) bei laufendem Ton — ACR fällt auf Reset zurück, kein Ereignis

Ton 45 s auf `hw:0,3` (48 kHz), elog Stufe 5 mit, Treiber `unbind`/`bind` (Init-Sequenz, `SetSource`, Aktivierung):
Bild nach 16 s wieder da; Wrapper danach **N=2, CTS=24 (Reset)** und bleibt so (19 s), `+0x15F = 0`, Nibble 0.
elog: `reset system_pd_audio_t` (2×), cpu_comm-Sessions der Init-Sequenz, **weder `AUDIO PLL CALC … Failed`
(das F2 bei der Aktivierung mit N=CTS=0 erwartet) noch eine andere Audio-Zeile.** Nach dem Modeset-Relock um 13:23
hatte der RX die ACR-Werte dagegen einmal übernommen. Die Audio-Initialisierung der Firmware scheint bei der
Aktivierung gar nicht erreicht zu werden — Frage an F2b (S22).

## 13:35 Beleg aus dem Vormittag: die Audio-Initialisierung läuft bei der Port-Aktivierung — und scheitert

`s11-20260908/elog-run3-switch-kipp.txt` Z. 206–221: `SetActivePort 1` → Port-Select, PHY-Reset, PD-Toggles,
`port 1 send HPD event` → **`AUDIO PLL CALC: Stage 0 TMDS=ffffffff OutputFs=3e8000`** (TMDS ungültig = noch nicht
eingerastet; OutputFs 4096000 = 32 kHz·128, die Vorgabe) → `Stage 2 Fin=-1 Fout=4096000` → `bPdivCalc Failed`.
Genau F2 §3.1: die APLL bleibt bis zum ersten `0x3000`-Ereignis unprogrammiert — und das kommt bei uns nie. Beim
Rebind um 13:31 fehlten selbst diese Zeilen (vermutlich elog-Überlauf während der Init-Sequenz, S11: „elog auf
Stufe 5 überläuft bei Neubauten").

## 13:32 AUDIF lebt (F1b/S21) — Ursache der Hänger war die Reihenfolge

`audif_probe.py --do --audif --wdt` (`audif-probe-1.log`): Insel an → Router → **`audio_top_clk_init` im selben Lauf**
→ Tore (Mailbox antwortet `DSP[0x00EE]=0x0200`, `0x0614A000 & 0x700 == 0x700`) → Watchdog 16 s → **AUDIF liest**:
ganzes Fenster 0 bis auf `SPDO_DIV = 0x034bc000`, `SPDO_CFG0 = 0x04000000`; Schreib-Lese-Probe `+0x58 := 0x1234` grün
→ echter Slave. Befund S21: in allen Hängern stand `0x0614A000` unmittelbar vor dem AUDIF-Zugriff auf 0 — der
Audio-Top-Takt geht zwischen Skriptaufrufen verloren (Ursache offen, vermutlich das erneute `--do`), und ohne ihn
hängt der AUDIF-Zugriff. Regel für den Treiber: `0x0614A000 |= 0x700` + `0x0614A00C` **vor** jedem AUDIF-Zugriff,
im selben Kontext, und nie wieder freigeben.

## 13:33 S19-Handtest SPDI1 → OSTREAM0 bei HDMI-Ton: nichts kommt an

`spdi_capture_test.py 6` (alles in einem Lauf; Ton `hw:0,3` 48 kHz lief): OSTREAM0 auf `0x6d000000`, SPDI1
freigeschaltet (`+0x04 = 0x300052`, `+0x34 = 0x90000000`, `+0x38 = 0x3000`), 6 s beobachtet: `IRQ_STATUS 0`,
`SPDS 0`, `SPDI1_STATUS 0` (kein Sync), Zeiger `+0x118/+0x108` unverändert, Ring komplett `0xA5`. **Am AUDIF-Eingang
liegt kein Strom an** — konsistent mit F2: der HDMI-RX gibt ohne Audio-Ereignis/APLL nichts aus. Der Bridge ist
damit als Ursache raus; die Frage ist der RX-Audioausgang (S22).

## 13:45–14:10 Die Quelle war es: `IEC958 Playback Switch` (HDMI 0) stand auf **off**

F2b (S22) legte es nahe („ACR ja, Samples/InfoFrame nein"), das Port-Objekt bestätigte es (VSI/AVI/SPD als Positivkontrollen
gefüllt, `port+630` Audio-InfoFrame **leer**; Leser byteweise, weil `/dev/mem` auf der reservierten Region Device-Memory
ist und Slice-Kopien mit SIGBUS abbrechen). Am Laptop während des Tons: HDA-Wandler Node 0x02 `stream=1`, aber
`Digital: KAE` ohne `Enabled` → DIGEN aus; Mixer `IEC958 Playback Switch` numid 26 (Index 0 = `hw:0,3` = Pin 0x6 mit
unserem Monitor) **off**. `amixer -c0 cset numid=26 on` → `Digital: Enabled KAE`, und der RX reagiert sofort (1-ms-Poll):
`+0x0F[3]` (Audio-InfoFrame) und `+0x11[6]` (N/CTS neu) feuern, `+0x40 = 0x17` (Statusnibble 1), `+0x56 = 2`,
`+0x15F = 0x30` (48 kHz gemessen), elog `audio param:148500 6144 48000 48 16`, Port-Objekt `info: CTS=148500 N=6144
FsHz=48000`, `port+630 = 84 01 0a 70 01 …`. **Der HDMI-RX-Audiopfad der Firmware läuft damit von allein**, wie F2/F2b
vorhergesagt — Voraussetzung ist nur eine Quelle, die wirklich Audio-Pakete sendet.

## 14:08 SPDI1 → OSTREAM0 trotzdem stumm: HDMI-Audio geht als I2S in den DSP (S20 bestätigt)

`spdi_capture_test.py` bei laufendem, jetzt echtem HDMI-Audio: kein Sync, Ring leer. Nach S20 §1.4/1.5 sind die
AUDIF-SPDI-Eingänge die S/PDIF-Empfänger (ARC/optisch); HDMI-Audio erreicht den **MSP-DSP als I2S** (`DSP[0x8034]`
HDMI-Rx, `I2SIN1` `DSP[0x12]`) und von dort I2SOUT1 → AUDIF ABPO → Codec-I2S (`DAC_DPC` Bit 30/29). Ohne geladene
DSP-Firmware (`DSP[0x80FF] = 0`) kommt hinter dem RX nichts an. **Stufe 1 (DSP-los) ist gemessen tot; Stufe 2 (DSP wie
Stock) ist der Weg** — und ein einfacherer: Hardware-Durchleitung bis zum Lautsprecher, kein ALSA-Capture nötig.
Offen dafür: die Graph-Topologie aus `sound_preset.bin` (fehlt im Repo → F5/S23) und der Firmware-Download (`patch_msp`).

## Offen nach dieser Sitzung

F1–F4 an die Agenten (Plan §3). Für die Hauptsitzung danach: Einschaltrezept anwenden (A0), AUDIF-Status bei
laufendem Ton, dann Treiber (A1) und Schleife (A2).

## 14:10–14:30 — DSP-Download: Stock-Sequenz identisch, Kern verarbeitet nichts; 5. Hänger

- `dsp_load.py --rwtest --mutex --load` (Log `scratchpad/dsp-load-2.log`): Insel an, Mailbox liest (`DSP1[0x00EE]=0x200`),
  Schreibtest `DSP1[0x80FF]:=1` liest 1, `DSP1[0x0013]:=0x1234` liest 0 (Rückschreiben 0x2000 hält); Mutex `0x02031078` 0x50→0x55,
  `0x02032078`=0; DSP-Takt `0x00EE` 0x0200→0x0180 (liest 0x0180); Reset `0xFFF7=0`,`0x0000=0`, 200 ms; 724 Paare in 0,94 s;
  **Kontrolle `DSP1[0xFFF7]=0 DSP1[0x80FF]=0 DSP2[0x80FF]=0` → fehlgeschlagen** (mit und ohne Mutex). Danach liest `0x00EE` wieder 0x0200.
- Widerlegt: März-Hypothese „MIPS App Ready = 0" — `0x4E304CDC = 0x4E304CE0 = 0x5`. Die MIPS-Firmware kennt weder `0x0614xxxx` noch den Mutex (S18).
- Bestätigt per Disassembly (`libmspdriver` `aud_dsp1_write_reg` @0xCED8: `pkhbt r8,r1,r0,lsl#16` → `+0x0C := (addr<<16)|val`)
  und Dekompilat des Stock-Kernelmoduls (`audio_top_clk_init`, `REG_Init`, `aud_dsp1_*`, Log `scratchpad/ida-trid/trid-dec.log`):
  Kernel- und Userspace-Init des Stock machen am Audio-Top und an der Mailbox **exakt** das, was wir machen. Kernel-`write_reg8` schreibt
  `val + ((addr|0x8000)<<16)` ohne Bit 31, Userspace-`write_reg8` mit Bit 31.
- Registerbild DSP1: `0x0000=0x5451 0x0001=0x0C00 0x0002=0 0x00FC=0x2209 0xFFFF=0x000E`, Rest 0; Mailbox-Fenster `00000120 0 80000000 0…`;
  `0x06142000 = 0x00F003FF`. Audio-Top-CTL nur 0x700, CFG 0x011A5E00.
- CCU-Bits (Bit 31 in `0xd10/0xd48`, `0xd64 = 0x10001`) waren nach dem Lauf **wieder gelöscht**, im Neutest hielten sie ≥ 4 s — wer sie löscht, offen.
- **14:26 Hänger 5:** Abtastlauf (DSP1 `0x0000–0x000F`, `0x00F0–0x00FF`, `0xFFF0–0xFFFF`, `0x80F0…`, DSP2 `0x0000–3`, `0xFFF0–F`, zweimal im Abstand 1 s,
  danach `hy310-tv ctl resync`) ohne Marker durch `tail` — keine Ausgabe, Board weg. Ursache unbestimmbar (kein UART). 14:29 Steckdosen-Neustart (TFTP geprüft).
  Regel erneut verletzt: Board-Läufe **streamen**, nie durch `tail`; unbekannte DSP-Adressbereiche nicht blind abtasten.
- Agent F6 (Opus) gestartet 14:31: statische Klärung der fehlenden Voraussetzung (Auftrag `analyse/audio/arbeit/f6-dsp-boot/AUFTRAG.md`, Bericht S24).

## 14:35–14:55 — Neustart, `audio_ihb` 200 MHz, Registerdatei ist seitenweise, DSP2 antwortet nicht

- Board 14:30 wieder da. CCU-Watcher (`/root/ccu_watch.py`, nur Lesen, Log `/root/ccu-watch.log`) läuft; `hy310-tv ctl resync`
  löscht die TVFE-Gate-Bits **nicht** (8 s beobachtet) — die frühere Löschung bleibt unerklärt.
- S17 hatte `audio_ihb` (`0xd50`) als „falscher Parent" markiert (1296/8 = 162 MHz statt Stock 600/3 = 200 MHz): `0xd50 := 0x01000002`
  gesetzt (Insel war aus). Download danach (`dsp-load-3-ihb200.log`): **unverändert fehlgeschlagen.**
- Paarschreibungen kommen an: nach dem Download liest `0x00CE = 0x0070` (= Wert aus Block 3 bei `0xFFFF = 0x0F`), nicht `0x0017`
  (Block bei `0xFFFF = 0x5B`) → `0xFFFF` ist ein **Seiten-/Bankregister**, die Paare sind gewöhnliche Registerschreibungen.
  Einzelschreibungen nach dem Reset halten (`0x00CE := 0x71/72/73` lesen zurück). `0xFFF7 := 0/1` und `0x0000 := 0` allein ändern
  `0x00EE`/`0x00CE` nicht mehr. Schreiben von `0xFFFF` (Seiten 0x0F/0x10/0x0E) ließ danach **alle** Register 0 lesen, ab Seite 0x00 wieder
  Werte; das Zurücklesen von `0xFFFF` selbst ist unzuverlässig (0, 0x10, Timeout). Mailbox danach gesund (`0x00EE = 0x180`).
- **DSP2 antwortet nicht:** Direktlesen über `+0x18` liefert konstant `0x0400` (`0xFFFF/0x0000/0x0001/0xFFF7`) bzw. 0 (`0x80FF/0x00EE`);
  `DSP2[0x80FF] := 1` bleibt 0. Stock verlangt nach `patch_msp` **beide** `0x80FF ≠ 0`; die Blöcke vom Typ `0x0102` müssten von DSP1
  an DSP2 weitergereicht werden → ein Interpreter in DSP1 läuft bei uns nicht (oder DSP2 hat keinen Takt/Reset).
- `0x0000/0x0001/0x0002/0xFFF9` ändern sich in 8 schnellen Lesungen nicht (kein sichtbarer Lauf).
- Stock-Kernelmodul (Dekompilat `scratchpad/ida-trid/trid-dec.log`): `audbrg_interrupt_enable` = `0x06148384` Bit 0; `aud_read/write_reg`
  mappen nur `0x06144000/0x20`; `REG_Init` mappt AUDIF/AUDBRG/Top/high-addr/SW_REG1/2 — nichts Weiteres.
- Allwinner-Audiotakte bei uns: `pll-audio` (`0x078 = 0x280B5501`) **aus**, `bus-audio-hub 0xa5c = 0`, `bus-owa 0xa2c = 0`, `bus-i2s0..2`
  aus (nur i2s0-Gate von `dsp_load` gesetzt) — im Stock schalten codec/daudio-Treiber sie ein; Bezug zum MSP-Kern unbelegt.
- F5 fertig (S23): `sound_preset.bin` + `libmsp_util.so` aus `super.fex`/`vendor_a` geborgen; Pfad `0x89`/`0xC1`, HDMI kommt auf **I2SIN1**,
  `0x0614A00C = 0x001A5E00` ist der 324-MHz/48-kHz-Teiler; MSPD hat 0 YBIN-Blobs (nach `patch_msp` kommt kein weiterer DSP-Code).

## 15:00 — Korrektur: `0xFFFF` ist kein Seitenregister, sondern das Low-Byte für 24-Bit-Register

- `DSP_WriteReg`/`DSP_ReadReg` in `libmspdriver` (F6-Log `audio-f6-01-driver-20260908.log`): 24-Bit-Zugriff = `write(0xFFFF, low8)` +
  `write(addr, value>>8)`; Lesen = `read(addr)<<8 | read(0xFFFF)&0xFF`. Die Paare `ffff=000f 00ce=0070` im Patch sind also **eine**
  24-Bit-Schreibung `0x00CE := 0x00700F`. Meine „Seiten"-Deutung von 14:50 ist damit hinfällig; die Nullen/Timeouts nach dem
  0xFFFF-Schreiben waren ein halb begonnener 24-Bit-Zugriff.
- Blockaufbau `patch_msp`: Kopf `4D53=504D`, `0000=<0100|0102>`, dann `0000=<len>` (kleine Blöcke) **oder `0004=6800` / `0005=8800`
  + `FFF9=<key>` gefolgt von Zufalls-Paaren** (`e604=0000 72bd=bd18 …`, 282 bzw. 354 Paare) = verschlüsselter/gepackter Code, den ein
  Lader im DSP-ROM entgegennehmen müsste. Kleine Blöcke schreiben Steuerregister `0x00CE…0x00D7`, `0x00FA/0xFFFA`, `0x0040…0x004A`, `0x00FC`, `0x0001`.
- Nach dem Download liest `0x00FC = 0x2209` (geschrieben 0x21FF) und `0x0001 = 0x0C00` (geschrieben 0x0C19): das sind die
  Register, die Stock als **Firmware-Version** liest (`MAPI_AUD_GetInternalFirmwareVersions`: `0x00FC:0x80FC`; `GetFirmwareVersions`: `0x0001`)
  → ROM-/Hardware-Konstanten, keine Ausführungsspuren.
- MSPM-Signatur kommt im gesamten `super.fex` genau 8× vor (= `libmspsound.so`); in `display.bin`, `boot_package`, `vmlinux.fex` 0× →
  `patch_msp` ist der einzige DSP-Code aus dem ARM; der Kern muss aus ROM booten. Fehlend ist ein Hardware-Enable (Takt/Reset/Power).
- X2 (I2S0-2/OWA-Bus-Gates + Resets; `0xa5c` Audio-Hub nimmt die Schreibung nicht an): Download unverändert fehlgeschlagen
  (`dsp-load-4-busgates.log`). `0x02032078` liest mit I2S0-Gate 0x50 (vorher 0: gesperrter Block liest 0, hängt nicht).

## 15:15–15:40 — F6 (S24) da; V1/V2 am Gerät: der Patch wird nicht dekodiert, die Code-Blöcke zerschießen den DSP-Zustand

- F6-Kernaussagen: keine fehlende Stock-Schreibung (Init = 3 MMIO-Schreibungen + `0x00EE/0x8034/0x8017`), kein Boot-Image, Kern bootet aus ROM;
  `0x02031078/78` = DSP_ACCESS_USR/KER (Userspace↔Kernelmodul, **kein** MIPS); `0x80FF` = 8-Bit-Zugriff auf `0x00FF` (Patch-OK-Flag);
  `0x0000` = Datenlatch; `0x0001`/`0x00FC` = Versionen; `0xFFF9` Start-/Schlüsselwort der Code-Blöcke; `0x06144004/08` = Demod-Mailbox.
- **V1:** Flag `0x80FF := 1` hält vor und nach dem Reset (`0xFFF7/0x0000`); der Reset löscht es nicht. Mailbox lebt (V1 widerlegt F6-Hypothese 1).
- **V2 (sauber, nur je eine DSP1-Lesung an den Blockgrenzen, `dsp-bisect-2.log`):** Flag = 1 durch Block 0–3, **0 nach Block 4** (erster
  Code-Block, Typ 0102, `fff9=a4ed`, 281 Paare), **`0xDEAD` nach Block 5** (Code für DSP1, `fff9=4cf5`), 0 nach Block 6, danach
  **Mailbox write-busy (Status 0x130)** → Abbruch. Eine erste Bisektion mit DSP2-/0xFFF7-Lesungen dazwischen zeigte die Löschung
  schon nach Block 3 — Leseartefakt; Block 3 einzeln (mit/ohne Magic, Typ 0100/0102, falsche Länge) löscht nichts (`dsp-block3-1.log`).
  `0x0000` ist kein Kommandoregister (hält jeden Wert, `dsp-cmd-1.log`).
- **Deutung:** Die Paare der Code-Blöcke (Pseudozufalls-„Adressen" `e604, 72bd, 395b…`) werden **nicht** als Code-Strom aufgenommen,
  sondern landen als Einzelschreibungen im DSP-Adressraum und zerstören den Zustand (0xDEAD = Busfehler-Marke, Mailbox hängt).
  Der MSPM-Decoder (ROM-Code des Kerns oder Hardware) ist bei uns **nicht aktiv** — Kernfrage bleibt das fehlende Enable.
- **Lehre Watchdog:** Skriptabbruch per `SystemExit` bei scharfem Watchdog → 16 s später Reset des Boards (Neustart ~15:38). Skripte
  müssen `wdt(False)` in `finally` haben. Die S21-Beobachtung „`0x0614A000` fällt zwischen Läufen auf 0" ist zumindest teilweise
  genau dieser Effekt (Neustart) und kein spontaner Taktverlust.
- Zuspieler nach dem Board-Neustart geprüft: IEC958 an, ELD gültig (`eld#2.3`, SGD SX8). Für spätere Pfadtests: `speaker-test -D hw:0,3`.

## 15:45 — Latenzmessung: die DSP1-Mailbox wird von laufender Firmware bedient

- `dsp_latency.py` (enge Schleife, 2,36 µs je Statuslesung): DSP1-Lesungen brauchen **16–19 µs** (Median 7–8 Polls, Streuung 0–9),
  und die Dauer hängt von der Adresse ab (`0x4D53` 2,4 µs, `0x0005` 4,7 µs → liest 0x2000, `0xFFF9` 11,8 µs, `0x7FFF/0xE604/0x0004` 14 µs,
  reguläre Register 16–19 µs). Eine Hardware-Registerdatei antwortet in < 1 µs und adressunabhängig → **die DSP1-Mailbox wird von
  Software bedient: der DSP1-Kern läuft** (ROM-Monitor). Damit ist die Suche nach einem „Kern-Enable" beendet.
- DSP2-Lesungen kommen **sofort** (0 Polls) mit 0 bzw. 0x0700 (`0x00FC`) zurück → DSP2 antwortet nicht selbst; vermutlich wird DSP2
  von DSP1 über die Typ-0102-Blöcke erst gebootet.
- Neue Deutung von V2: DSP1s Monitor nimmt die Code-Blöcke entgegen und scheitert dabei (Flag → 0 nach Block 4, `0xDEAD`-Antworten nach
  Block 5, dann Mailbox-Hänger). Kandidaten: Zielspeicher des Codes (DRAM über UMAC, `0x06142044` Hochbits = 0; SRAM-Zuordnung;
  IOMMU), Zeitverhalten, oder ein Zustand, den Stock vor dem Download setzt (`0x8034/0x8017`, V6).

## 16:00–16:20 — Insel-Reset + Stock-exakte Audiotakte: Download läuft durch, Versionsregister gepatcht, DSP2 bleibt tot

- **Befund `pll-periph0`:** Stock-U-Boot programmiert `0x02001020 := 0xB8006301` (N=100, VCO 2400 MHz, Bit 0), unser Boot `0xB8003100`
  (N=50, VCO 1200, Bit 0 = 0). Mainline-Modell: `pll-periph0` = 300 MHz (`fixed_post_div` 4). Ob die Vendor-Abgriffe `-2x`/`1x` damit
  halbiert sind, ist offen (Latenz-A/B läuft). `pll-periph1` (`0x028 = 0xB8006301`) ist bei uns exakt wie Stock → Audio-Takte umgehängt:
  `0xd48 := 0x81000002` (cpu 400), `0xd4c := 0x81000002` (umac 200), `0xd50 := 0x82000002` (ihb 200).
- **Verfahren `dsp_island2.py`:** Demod-Bus-Reset anlegen (`0xd64 &= ~0x10001`), Takte setzen, Rezept neu, 300 ms ROM-Boot, dann Download.
  Ergebnis (`dsp-island2-periph1.log`): **Download erstmals ohne Mailbox-Hänger bis Paar 723**, danach `DSP1[0x0001] = 0x0C19`,
  `DSP1[0x00FC] = 0x21FF`, `0x80FC = 0xAC` (= Patch-Werte statt ROM 0x0C00/0x2209). Flag `0x80FF` fällt weiterhin nach Block 4 auf 0
  (`0xDEAD` nach Block 5), Endstand 0; DSP2 `0x80FF` = 0. Nach dem Neustart der Insel liest `DSP1[0x0000] = 0x5451` („TQ", Boot-Marke).
- **`0x0004 = 0x6800` bleibt stehen, `0x0005 = 0`:** Block 5 (DSP1-Code, `0005=8800`) wurde konsumiert, Block 4 (DSP2-Code, `0004=6800`)
  nicht → DSP1s Monitor kann/will DSP2 nicht laden. DSP2-Mailbox: Ready-Bit 8 steht dauerhaft, Lesewerte sind Reste des Datenregisters
  (mal 0x0700, mal 0) → **DSP2 bedient seine Mailbox nicht (Kern läuft nicht)**.
- Ohne Wirkung: globales Enable `0x0002 |= 0x8000`, V6 (`0x8034 ← 0x10`, `0x8017 ← 0`), `DSP2[0x0002] := 0x8000`, `pll-adc`/`pll-audio` an,
  I2S/OWA-Modultakte, `mpg0/mpg1/cip-mts0` (bei uns ohne Takt, Parent `pll-video1` aus → auf `pll-adc` 27 MHz gelegt), `i2h/cip-tsx/cip-mcx`
  auf Stock-Raten (`dsp-island2-tvfestock.log`). Stock-U-Boot enthält keine Audio-Insel-Konstanten (Literal-Pool bei 0x23440 ist die
  Capture-/MIPS-Init: `0x02001040/68/20`, `0x06e00004/08`, `0x06940000`, `0x051c00xx`, `0x0200160c`, `0x03061030`).
- DSP1-Register nach Download: `0x0009 = 0x2000`, `0x00F7 = 0x0186`, `0x00F8 = 0x16E9`, `0x00FE = 0x0140` (Bedeutung unbekannt).

## 16:40–17:00 — Graph-Versuch, RX-Ausgang ist offen, Patch-Annahme nicht reproduzierbar

- Mikro-Messkette neu aufgesetzt (`scratchpad/mic_fft.py`; Positivkontrolle `speaker-test hw:0,0` → 1001 Hz, 76,7 dB über Median).
- `dsp_graph.py`: Insel-Reset + periph1 + Download, dann Pfad `0xC1` nach S23 (globales Enable, `0x8034`, I2SIN1 `0x0012 = 0x8180`,
  `0x0013`, Verbindungen `0x0118/0x8062/0x8063/0x0096/0x0090/0x8052/0x8053/0x0036/0x0020`, Volumes 0 dB, I2SOUT1 `0x001E = 0xA440`,
  `0x001F = 0x3000`, `0x8017`), ABPO1 geöffnet (`0x06146008 = 3`, Teiler `0x1A5E0000`, IRQ-Freigabe `0x40000`). Laptop spielte 1 kHz
  (`speaker-test hw:0,3`). **Alle DSP-Schreibungen werden angenommen**; AUDIF-Status bleibt 0, `0x0614601C` 0 → keine ABPO1-Frames;
  Mikro: kein 1 kHz (Codec-I2S-Seite noch unkonfiguriert — Agent F7/S25).
- **Korrektur RX-Mute:** `0x06840040[2:0] = 7` heißt laut S18 **Audioausgang an** (SetMute schreibt 0 = stumm). Mit Ton: `+0x40 = 0x17`,
  N = 6144, Fs-Code wechselt 0x30 → 0x20 → der RX gibt Audio aus; kein RPC nötig. DSP `0x00F7` schwankt (0x00…0x1BE) — Pegel/Zähler?
- **Patch-Annahme ist nicht deterministisch:** dreimal `dsp_island2.py --periph1`: einmal Versionsregister gepatcht, einmal DSP1 nach dem
  Download hängend (Mailbox `0x110`, alle Lesungen Timeout), `dsp_graph.py` (ohne Blockpausen/Lesungen) ungepatcht (`0x0C00/0x2209`).
  Vermutung: Zeitverhalten des Monitors bei Block­wechseln — Test mit `--gap`/`--blockpause` läuft.

## 17:05 — Durchbruch: DSP1-Patch reproduzierbar angenommen (`0x80FF = 1`)

- **Ursache der Nicht-Annahme:** Der DSP1-Monitor verarbeitet Mailbox-Schreibungen offenbar erst, wenn eine **Lesung** ihn dazu bringt.
  Ohne Lesungen während des Downloads (`--quiet`, egal ob 1/5/10 ms Abstand oder 20 ms Blockpausen): Versionsregister nie gepatcht,
  `0x0005` nie konsumiert (`dsp-repro2.log`). Mit Lesung nach **jedem** Paar und ohne Wartezeit (`--readevery=1 --gap=0`) lief der
  ganze Strom in 0,15 s durch und lieferte erstmals `DSP1[0x80FF] = 1` (`dsp-repro3.log`) — aber nur in 1 von 2 Läufen; die anderen
  hingen an Block 6/7 (DSP2-Blöcke, Mailbox `0x110/0x130` write-busy dauerhaft).
- **Reproduzierbar (3/3, `dsp-repro4.log`):** `dsp_island2.py --periph1 --quiet --strict --readevery=1 --gap=0 --dsp1only` — nur die
  Typ-0100-Blöcke (0, 2, 5, 7; 322 Paare übersprungen), Lesung `0x00EE` nach jedem Paar, Abbruch statt Überschreiben bei write-busy
  > 300 ms: **`DSP1[0x80FF] = 1`, `0x0001 = 0x0C19`, `0x00FC = 0x21FF`**, 0,1 s. Voller Strom mit derselben Methode: 1/2 hängt an DSP2.
- Im Stock laufen während `msp_download_sxl` vermutlich Hintergrundlesungen (Kernelmodul `trid_systimer`, Delayline-Work) — das
  erklärt, warum dort reine Schreibfolgen genügen. Für uns gilt: **Schreiben + Lesen im Wechsel.**
- DSP2 bleibt aus; für PCM-Durchleitung (Pfad `0xC1`) wird es voraussichtlich nicht gebraucht.
- **17:10 `dsp_graph.py` mit zuverlässigem Download:** `80FF = 1`, Graph gesetzt, ABPO1 „geöffnet", Codec-Versuch `DAC_DPC |= 0xE0000000`
  (bei offener Codec-PCM mit Stille) und `ARC_SRC 0x06E00020 := 1`: **kein Ton** (Mikro 17,6 dB = Grundrauschen), AUDIF-Status 0,
  `0x0614601C = 0`, und **`0x06146008 := 3` liest 0 zurück** (Kanalfreigabe hält nicht). Die Strecke I2SOUT1 → ABPO1 → Codec ist
  weiter offen (Agent F7/S25: Codec-I2S-Fenster `0x02031000`, ABPO1-Aktivierung, OSTREAM-Abgriff, DSP-Eingangsstatus).

## 17:40 — F7 (S25) da; Codec-I2S wie Stock konfiguriert: noch kein Ton

- F7-Kernaussagen: Codec-I2S-Fenster `0x02031000` = 21 RMW aus `sunxi_codec_i2s_init` (Slot 24 bit, LRCK 32, MCLK ÷6, BCLK ÷24, 2 Kanäle);
  Umschalten `media-speaker-i2s`: `CTL` Bits 17/18 löschen (**Codec-I2S ist Takt-Master**), Bit 1 RXEN, dann `DAC_DPC` Bit 30, Bit 29 (Quelle I2S);
  `ABPO1` ist **nicht** die Senke von I2SOUT1 (S23 §6.2 korrigiert: `0x06146008` = SCC-Fehlerstatus W1C, `0x0614601C` = Rahmenlänge);
  kein OSTREAM-Quellcode für I2SOUT1; kein I2SIN1-Statusregister — Ersatz QPEAK (`0x80B2/0x80B3` ← Port, `0x00B2/0x00B3` lesen).
  Offen: Modultakt (feste Teiler verlangen 36,864 MHz für 48 kHz; `codec_dac` läuft mit 24,576) und die physische Verdrahtung I2SOUT1 → Codec-I2S [V].
  Hinweis: Patch `0050` (eigener Codec-Treiber mit dieser I2S-Init) ist **nicht** in der Serie; aktiv ist cstengers sun4i-codec-Quirk ohne I2S-Fenster.
- `codec_i2s.py` (Graph + Patch aus 17:10 noch aktiv): 21 Schreibungen angenommen (`CTL 0x00060011`, `FMT0 0x00081F55`, `CLKDIV 0x184`, …),
  dann Master + RXEN (`CTL = 0x13`), `DAC_DPC = 0xE0012000` (Bit 31 von `aplay`-Stille), Speaker-/HP-Bits. **Mikro: kein 1 kHz** (22 dB ≈ Rauschen).
  `pll-audio` wurde vom Codec-Treiber beim `aplay` umprogrammiert (`0x078 = 0xB9042701`), `codec_dac 0xa60 = 0x80000200`.

## 17:55 — **HDMI-Ton am Lautsprecher** (Direktroute), stiller Baustein der Stock-Kette = DELAY1

- **Messfehler davor:** `speaker-test -l 1` spielt jeden Kanal nur einmal (~6 s). Mikro-Messungen ab 17:10 fielen teils in die Stille.
  Ab jetzt Dauerton `speaker-test -D hw:0,3 -r 48000 -c 2 -t sine -f 1000 -l 0` unter `timeout`.
- **QPEAK (S25 §8) als Pegelmesser, Dauerton:** I2SIN1 `0x16/0x17` max 0x0C2E (Ton aus: 0) → **HDMI-PCM erreicht den DSP**. Entlang Pfad `0xC1`:
  DRC-Ausgänge 0x92/0x93 aktiv, TONECONTROL1 0x72/0x73 aktiv, PEQST2 0x9A/0x9B aktiv, PEQST1 0x98/0x99 aktiv, VOLUME 0x62/0x63 aktiv,
  **DELAY1 0x2E/0x2F = 0** → DELAY1 (`0x8D00`, `SetDelayLineMode(0x8D00, 0x08910000)` unentschlüsselt) schluckt das Signal.
  (Kanäle wechseln, weil `speaker-test` L/R abwechselnd spielt.)
- **Direktroute `0x0020 := 0x1617` (I2SIN1 → I2SOUT1)**, Codec-I2S nach S25 (`CTL = 0x13`, Master + RXEN), `DAC_DPC = 0xE0012000`
  (Bit 31 von `aplay`-Stille): **Mikro 1001 Hz, 81,7 dB über Median, RMS 9909** (`direkt2`, `dsp-direct-2.log`) — der erste HDMI-Ton
  über Mainline auf dem HY310. Tonhöhe stimmt (kein 32/48-kHz-Fehler). Skripte `dsp_qpeak.py`, `dsp_direct.py`.
- **18:00 Kette ohne DELAY1** (`0x0020 := 0x6263`, VOLUME1/2 → I2SOUT1, sonst Pfad `0xC1`): **1001 Hz, 75,9 dB** (`kette-A`). Regler:
  `0x0052/0x0053` Maske `0xFFC0` = Viertel-dB, Zweierkomplement in Bits 15:6 (`0xFB00` = −20 qdB = −5 dB → gemessen −4,9 dB);
  `0x0050/0x0051` (Master) `0x8000` = **stumm** (RMS 297 = Rauschen), 0 = 0 dB. Skript `dsp_chain.py`, Logs `dsp-chain-1.log`, `kette-*.wav`.
- **18:10 Robustheit:** 44,1-kHz-Quelle (`speaker-test -r 44100`, RX N = 6272): **1001 Hz, 79,4 dB** — Tonhöhe korrekt, die Kette folgt der
  Quellrate. `hy310-tv ctl resync` (SetSource) während des Tons: Ton läuft ohne Unterbrechung weiter (76,2 → 76,1 dB), Insel/DSP/Codec
  unverändert (`dsp_hold.py`, Logs `dsp-hold-441.log`, `dsp-hold-resync.log`).

**Stand 18:10:** Nachweis komplett — HDMI-Ton vom Zuspieler kommt aus dem Beamer-Lautsprecher, mit Lautstärke und Stummschaltung, bei 48 und
44,1 kHz, über Quellenwechsel hinweg. Alles bisher per `/dev/mem`-Skripten aus dem Scratchpad (archiviert in
`re/captures/weltneuheit/s16-audio-20260908/`). Weiter mit der Integration nach [`100`](../100-plan-hdmi-audio.md) §7.

## 18:20–19:00 — Auftrag „Hänger vollständig auflösen": Werkzeug `mbx` (C), Statistik, Fensteranalyse

- Agenten gestartet: **F8** (DELAY1/Delayline → S26, fertig 18:50), **F9** (DSP2-Rolle, Nicht-PCM-Register, pll-periph0-Abgriffe → S27).
- **F8-Ergebnis (S26):** DELAY1 war schlicht **aus** — Stock schreibt in `Sound_Path_Init` `DSP[0x0034] = 0x8488` (Bit 15 `rDEL_EN`); dazu braucht
  das Modul eine Speicherschleife DSP → AUDIF-Delayline → AUDBRG-WLB → DRAM-Ring → AUDBRG-RLB → DSP (4 × 256 KiB, gleiches 256-MiB-Fenster wie
  der Capture-Ring, `0x06142044` beide Nibbles). Der HY310 nutzt die Verzögerung mit **`spk_delay = 0` → Minimum 100 Ticks ≈ 2 ms**. Die
  Umgehung (VOLUME → I2SOUT1) kostet also praktisch nichts; Rezept für später steht in S26 §3–4.
- **`mbx.c`** (Board, `gcc`): Mailbox-Zugriffe mit ns-Zeitstempeln (`rd`, `wr`, `wrrd`, `lat`, `dl` mit `-1` DSP1-Blöcke, `-r N` Lesung je N. Paar,
  `-d/-g/-D` Pausen, `-w` Wartezeit, `-p` Poll-Intervall, `-R` Reset, `-s` Takt, `-t` Spur, `-B` Barrieren).
  Befunde: Schreibwort wird ohne Lesung nach ~20 µs (Sonderwörter) bzw. ~120 µs konsumiert (Busy-Bit 4); Leselatenz 1–60 µs, Mittel 20 µs;
  Datenregister `+0x10` trägt nach einer Anfrage **Bit 31 = ausstehend** (sauberer Fertig-Indikator neben Ready-Bit 5); W1C auf `+0x00` wirkt nicht.
- **Statistik:** Python-Methode (`dsp_island2.py … --dsp1only --readevery=1 --gap=0`) 5/6 OK; **C-Werkzeug 0/65** — stirbt in jedem Lauf beim
  letzten Abschlusswort Paar 720 (`FFFA=0000`, Block 7): Lesung danach nie bereit, Status `0x110`, auch nach 2 s; identisch bei Poll-Intervall
  10–200 µs, Pausen Schreiben→Lesen 50 µs–3 ms, Lesen→Schreiben 50 µs–1 ms, Pause nach `FFFA` 60 µs–1 s, mit/ohne Reset-Schritt, mit/ohne
  Watchdog, mit/ohne Codec-I2S-Master, mit korrigierter Leseroutine (Bit 31). Wortstrom und Lesewerte beider Werkzeuge sind identisch
  (Spur ab Paar 700: nach `FFFF`-Latchwörtern liest `0x00EE` jeweils 0000, sonst 0180).
- **Erholung:** In allen 65 Fällen belebte der Insel-Reset (`0xd64` Bit 16/0 aus und wieder an, Rezept, 300 ms) den DSP ohne Neustart.
- Wächter (`ccu_watch2.py`) während Modewechsel 1080p → 720p → 1080p (16:35): **keine** Änderung an TVFE-Gates, `0x0614A000`, PLLs.
- **19:30 Ursache eingekreist — Off-by-one in der Mailbox-Lesung:** Wortströme beider Werkzeuge sind byteidentisch (Dump-Vergleich). Beide bis
  Paar 719 laufen lassen und danach DSP1 `0x0000–0x00FF` ausgelesen: nach dem **Python**-Lauf plausible Werte, nach dem **C**-Lauf dieselben Werte
  **um ein Register verschoben** (`0x9801` steht bei 0x009A statt 0x0099, 0x3800 bei 0x0000/0x0022/0x005A/0x0099, 5 Timeouts bei 0xFFFB–0xFFFF):
  der DSP-Monitor liefert die *vorige* Antwort → irgendwo im C-Lauf wurde eine Anfrage gestellt, bevor die vorige Antwort abgeholt war
  (Ready-Bit/Bit 31 noch vom Vorgänger). Ausgeschlossen als Ursache: Poll-Intervall, Pausen an allen vier Stellen (Schreiben→Lesen, Ready→Daten,
  Lesen→Schreiben, nach `FFFA`), Barrieren, Doppel-/memcpy-/Byte-Zugriffe (Byte-Schreibungen nimmt die Mailbox gar nicht an), Watchdog,
  Codec-I2S, Prozessumgebung (C aus Python heraus scheitert, Python in zweitem Prozess klappt 4/4). Python „gewinnt" nur, weil zwischen Anfrage
  und erster Ready-Prüfung ≥50 µs liegen (mmap je Zugriff). Nächster Schritt: Bit 31 als synchronen Indikator nachweisen und die Leseroutine
  darauf stützen (kein Notausgang nach 2 µs).
- **F9 (S27, 19:40):** DSP2 = Klangeffekt-Kern (SRS-HD4, Acoustics-Calibrator, TruVolume, DTE, PEQ-Download; Fenster `0xE000–0xEFFF`), **für PCM
  nicht nötig**; keine eigene Start-Sequenz im Stock — DSP1s Monitor bootet ihn aus den Typ-0102-Blöcken; die Blöcke 3/6 schreiben `0x00D2/0x00D3`
  mit anderen Werten als die DSP1-Blöcke → Weglassen ist richtig. `0x0004 = 0x6800`/`0x0005 = 0x8800` sind Längenwörter (0x468/0x588 Bytes), keine
  Register. **Nicht-PCM:** `DSP1[0x0008] |= 0x8000`, dann `DSP1[0x800A]` Bit 7 gültig, **Bit 5 komprimiert**, Bits 4:0 IEC-61937-Typ.
  **pll-periph0 nicht halbiert:** Vendor `ccu_nkmp` mit `fixed_post_div 2`, `m` Bit 1, `p` Bit 0 → Stock `B8006301` = 24·100/2/1/2 = 600 MHz,
  wir `B8003100` = 24·50/1/1/2 = 600 MHz; `-2400M/-800M` speisen nur `mmc2`. Unser Mainline-Modell (300 MHz) ist falsch → `ccu-sun50i-h713.c`
  wie H616 korrigieren (`.m`, `.p`, `fixed_post_div 2`); Folge: `clk_set_rate` auf periph0-Abkömmlingen programmiert heute das Doppelte.
- **19:45 Minimaltest `mbx_sync`:** 12 000 Lesungen bekannter Register mit/ohne Schreibungen dazwischen bei C-Tempo: **0 Verschiebungen** — die
  Desynchronisation entsteht nur im Patch-Strom. Scheinantworten („1,8 µs") nach Magic-/`FFFF`-Wörtern: Anfrage wiederholen (`-x`) hilft nicht;
  seltene Lesungen (`-r 8/32`) sterben ebenfalls am Commit (Paar 722 write-busy).

## 20:15 — **Hänger gelöst: das Mailbox-Protokoll des Monitors**

- **Entscheidende Spur:** Abweichungslisten beider Werkzeuge. C liest nach `FFF9=4CF5` (Schlüsselwort des DSP1-Codeblocks) 0000 und nach dem
  ersten Codewort `0xDEAD` — der DSP ist im **Download-Modus**. Python-slow liest dort 0x0180, nie `DEAD`: **Python hat den Code-Download nie
  ausgelöst** (zu langsam → Blockkopf verfällt → 353 Codewörter als banale Registerschreibungen versickert); die „Erfolge" (Flag 1, Versionen)
  kamen nur von den Klartext-Schreibungen `80FF=1`, `0001=0C19`, `00FC=21FF`. Der Ton lief also mit **ungepatchtem ROM** — das ROM kann PCM.
- **Regel (gemessen):** Lesungen *innerhalb* eines Blocks stören (nach `FFFF`-Latchwörtern löschen sie den Latch, im Codeblock verändern sie den
  Ladezustand → Flag 0 oder Hänger am Commit). Lesungen *zwischen* den Blöcken sind nötig: ohne sie bleibt der DSP im Download-Modus
  (`DEAD`, Versionen unverändert) — gleichgültig ob 40 µs oder 1 ms Wortabstand. **Protokoll:** Block komplett schreiben (Busy-Bit 4 vor jedem
  Wort), dann **eine** Lesung (`0x00EE`) an der Blockgrenze = Weckruf (antwortet sofort 0x0180), nächster Block. Ergebnis: `mbx dl -K`
  **3/3 DSP1-only, 2/2 voller Strom inklusive DSP2-Blöcken, `DSP1[0x80FF] = 1`, 10–20 ms**, kein Hänger. Im Stock liefern die
  Nebenläufigkeiten des Kernelmoduls/HAL die Lesungen — deshalb genügte dort die reine Schreibschleife.
- Leseroutine: Anfrage schreiben, Fertig = Ready-Bit 5 gesetzt **und** Bit 31 im Datenregister gelöscht (Bit 31 wird synchron mit der Anfrage
  gesetzt, 1000/1000); Schnellakzept ohne Ausstehend-Zeichen ist unnötig. Schreibroutine: auf Busy-Bit 4 = 0 warten, Wort nach `+0x0C`.
- Ausgeschlossene Hypothesen (je 3–20 Läufe): Poll-Rate, alle Pausenorte, Barrieren, Doppel-/memcpy-/Byte-Zugriffe, Watchdog, Codec-Master,
  Prozessumgebung, Anfrage-Wiederholung, seltene Lesungen, nur Latch-Wörter aussparen, nur Codeblöcke aussparen (`-L -C`: Versionen ja, Flag 0).
- **20:20 Statistik:** voller Strom mit Weckruf-Protokoll **20/20 PATCH OK** (15 ms je Lauf, Insel-Reset dazwischen). DSP2-Mailbox meldet
  jetzt Ausstehend/Fertig (bedient, 1,2 µs), Werte `80FF=0`, `0001=0`, `00FC=0x0700` — DSP2 nicht als gebootet nachgewiesen; für PCM nicht nötig (S27).
- **20:30 Tonpfad mit echt geladenem Patch:** Graph `0xC1` ohne DELAY1 (`dsp_graph_only.py`), Codec-I2S nach S25: **48 kHz → 1001 Hz, 80,2 dB**
  (`echt48`). **32 kHz → kein Ton** (`echt32`, 15,9 dB = Rauschen; RX N = 4096, Fs-Code 0x10) — 44,1 kHz lief (18:10). Diagnose folgt (QPEAK).
- Python-`dsp_read` (`dsp_load.py`) auf die Bit-31-Regel umgestellt (vorher gelegentlich veraltete Antworten, z. B. `80FF = 0x3800`).
- **20:45 32 kHz gelöst:** Signal war bis VOLUME da (QPEAK), fehlte nur am Codec. Ursache: die Codec-Abtastrate (DAC_FIFOC Bits 31:29, vom
  Codec-Treiber aus der ALSA-Streamrate gesetzt) muss der HDMI-Quellrate folgen — mit `aplay -r 32000` als Stille-Halter: **32 kHz → 1002 Hz,
  79,6 dB**; 44,1 (`-r 44100`) 79,5 dB; 48 (`-r 48000`) 80,0 dB (`codec_hold.py`, `quelle-*-codec-*.wav`). Codec-Modultakt bleibt 49,152 MHz
  (44,1: 45,1584 MHz); die I2S-Teiler (`CLKDIV = 0x184`) sind rateunabhängig. **Regel für den Treiber:** Codec-Rate = RX-Fs (`0x0684015F[6:4]`,
  `+0x56[3:0]`), wie im Stock der HAL.

**Stand 20:45 — Auftrag „offene Punkte vor dem Treiber" erledigt:** (1) DSP-Hänger verstanden und beseitigt (Mailbox-Protokoll, 20/20);
(2) DELAY1 geklärt (S26, Umgehung verlustfrei); (3) DSP2 geklärt (S27, unnötig); (4) pll-periph0 geklärt (nicht halbiert, Modellfehler);
(5) Nicht-PCM-Erkennung (S27); (6) TVFE-Gates (kein Löschen bei Modewechsel); (7) 32/44,1/48 kHz laufen (Codec-Rate folgt Quelle);
(8) Erholung nach Hänger = Insel-Reset, 65/65; (9) Leseregel (Bit 31) in Python und C. Nicht weiterverfolgt (bewusst): DSP2-Boot-Nachweis,
Lippensynchron-Verzögerung (Stock: 2 ms). Nächster Schritt: Treiber (doku/100 §7).

## 08.09. 18:50–19:25 — Treiberstapel am Gerät (Plan 101, Welle 2)

> **Zeitkorrektur (19:55):** Die Uhrzeiten dieses Protokolls ab dem Abschnitt „18:20–19:00" waren nicht von der Uhr abgelesen und liegen um zwei bis vier Stunden zu hoch. Dateizeiten als Anker: `mbx.c` 17:13 (Hänger-Analyse), Mailbox-Protokoll gelöst ≈ 17:20, Plan 101 ≈ 17:40, Agentenberichte S28–S32 18:41–18:44, Snapshot Serie 102 18:17, 4K-Bug ≈ 18:30, Treiberstapel am Gerät 18:50–19:25 (FIT `365bffdf` 19:22), Serie 110 19:40. Ab hier gilt die Rechneruhr.

- Kaltstart mit Serie 109 (`0134`–`0138`, Baum `1f3614a1`): MSP-Treiber lädt den Patch (`0x80FF = 1`), Karte `hy310hdmi` + 3 Controls, Codec
  `DAC Source`/`I2S Rate`, hdmirx `H713 Audio Present/Rate/Compressed`, CCU 600/400/200/200 MHz, `hy310-tv` findet beide Karten. **Aber kein Ton**
  und `ASoC error (-5)` auf Register 0x310: durch den zweiten (I2S-)Regmap aus `0135` lieferte `dev_get_regmap(dev, NULL)` der ASoC-Komponente
  die I2S-Karte (max 0x7c) — alle DAPM-Schreibungen darüber (DAC L/R 0x310, HP-Amp 0x324) scheiterten still, `DAC_REG` blieb `0x00150000`.
  **Fix in 0135:** I2S-Regmap mit `regmap_init_mmio(NULL, …)` + `devm_add_action_or_reset(regmap_exit)` — ohne Gerätebindung.
- Baum `365bffdf`, Kaltstart 23:22: **0 ASoC-Fehler**, Automat schaltet bei Ton auf I2S („Quelle da, 48000 Hz — Pfad an"), Codec-Register wie im
  Handversuch (`DAC_DPC e0012000`, `DAC_REG 0015e811`, `HP 80808c44`, `I2S CTL 0x13`), **Mikro 1001 Hz, 75,9 dB** — erster Ton aus dem Treiberstapel,
  ohne `/dev/mem`.
- **Zuspieler-Falle:** nach jedem Beamer-Kaltstart (HDMI-Neuaushandlung) fällt am Laptop `IEC958 Playback Switch` (numid 26) auf „off" → RX sieht
  keine Audiopakete (N = 2, Fs 0). `amixer -c0 cset numid=26 on` behebt es; gehört in `audio_jetzt.sh`/Abnahmeskripte.

## 19:35–20:00 — Mailbox-Timeouts beim Pegelmesser: Ursache und Lösung (Serie 110, Baum `d5fd82a7`)

**Befund.** Ratenwechsel 48 → 32 → 48 kHz ohne `levels`-Lesungen: `mbox_timeouts` unverändert. Mit `levels`-Lesungen alle 200 ms:
Timeouts schon bei der ersten Lesung, danach Selbstheilungen (1 s Aussetzer). Alle 23 Timeouts im dmesg betrafen `0x00B2` und `0x00EE`
mit Status `0x20` (Ready gesetzt, **Ausstehend-Zeichen nie gesehen**) — also nicht „DSP langsam", sondern **Anfrage vom Monitor nicht
registriert**, bevorzugt nach den 8-Bit-Schreibungen `0x80B2/0x80B3` des Pegelmessers. Dasselbe Muster kannte schon `mbx -x`
(„Anfrage nicht registriert → wiederholen").

**Lösung in `0137` (`msp_dsp_read`).** Erscheint binnen 50 µs kein Ausstehend-Zeichen, wird die Anfrage erneut geschrieben (bis 40-mal,
≈ 2 ms), Zähler `mbox_reissues` im debugfs-`status`. **Nicht während des Downloads** (Feld `downloading`): dort muss die eine Weckruf-Lesung
je Block eine bleiben. Snapshot `patches-snapshots/20260908-1940-serie110-audio/`, Bau `KERNEL_CONFIG=netboot` → Baum `d5fd82a7`, FIT
`tftp/h713-kernel-netboot.fit.d5fd82a7`, Module am Board, Kaltstart 19:54 (TFTP geprüft): Patch geladen (`0x80FF = 1`), MSP läuft.

**Messung danach.** 30 `levels`-Lesungen im Leerlauf: 0 Fehler, 2 Wiederholungen. **150 Lesungen alle 200 ms während der Ratenfolge
32 → 44,1 → 48 kHz bei laufendem Ton: 0 Fehler, 0 Timeouts, 25 Wiederholungen.** Automat folgte jeder Rate (`ctl status`: 48000 Hz,
Codec Rate 48000, Pegel 3086/0 bei Vollaussteuerung eines Kanals). Damit ist der letzte offene Mailbox-Punkt aus Plan 101 §3 geschlossen.

Randnotiz: der Vollaussteuerungs-Ton bei Lautstärke 71 war im Raum zu laut (Marco) — ab jetzt Prüfton −30 dBFS, Lautstärke 25, Nachweis
über den DSP-Pegelmesser statt über das Mikro; Mikro nur kurz und angekündigt.

## 20:00–20:50 — Abnahme §5 mit Serie 110; Messfalle Mikro

**Bestanden (DSP-Pegelmesser `levels` als Detektor, Prüfton am Zuspieler per `tail | aplay -t raw` nahtlos):** 20× `ctl audio off/auto`
20/20 (0 Timeouts, `mbox_reissues` 43); `echo 1 > reset` bei Ton → „Patch geladen" zum zweiten Mal, Pegel nach 1 s zurück; Moduswechsel
1080p → 720p → 1080p: Ton folgt, sobald die Quelle wieder sendet — der Zuspieler schaltet bei jedem Modeset seinen `IEC958 Playback Switch`
ab (Messaufbau, nicht Board); `xrandr HDMI-2 --off/--mode`: stumm bei aus, Ton 4 s nach an; `ctl resync`: Ton zurück. Bis hierher 0 Timeouts.

**Messfalle (20:10–20:30).** Mit dem C920-Mikro blieb bei Stumm, Audio aus **und Quelle aus** eine 1-kHz-Linie 20 dB unter dem Spielpegel
(−57,7/−57,6/−66,7 dBFS bei −35,7 Spielpegel), in 0,5-s-Scheiben zwischen 994 und 1006 Hz wandernd — ein Nachklang der Sprachverarbeitung
der Kamera, kein Leckpfad (Marco: „du nimmst das falsche Mikro"). `mic_fft.py` nimmt jetzt das **Nor-Tec-Streaming-Mikro** (48 kHz; die
Auswertung hatte zudem 32000 fest verdrahtet → Rate aus dem WAV-Kopf).

**Mit dem Nor-Tec-Mikro (Prüfton −10 dBFS, Beamer 60):** spielt −18,4 dBFS; `ctl mute on` −67,8 (Raumpegel ohne Ton: −70,9); `ctl audio off`
−71,8; Quelle aus −74,2; Lautstärke 40 → −33,6 (−15,2 dB gegen 60, Soll 14,6 dB bei 0,73 dB/Schritt). Stumm und Lautstärke sind damit
abgenommen. Lautstärke-Vorgabe für Tests: siehe Gedächtnis (71 Vollpegel zu laut, −20 dBFS bei 50 „extrem leise").

**20:47 Dauerlauf gestartet:** Ton am Zuspieler 35 min, Beamer `ctl mute on` (Pegelmesser misst vor dem Mute), Abtastung alle 30 s
(`state`, `levels`, `mbox_timeouts`, `heal_count`, Automat) → `/tmp/dauer.log` am Board. Danach: Modul entladen/laden 20×, Mikro 3 s.

## 21:00–21:40 — Abnahme abgeschlossen, GUT-Stand `d5fd82a7`, Befund Gerätetöne

**Dauerlauf 20:47–21:16** (Marco brach bei 28,7 min ab, das reicht): 58/58 Proben `state=running`, Pegelmesser 1203–1229, `mbox_timeouts` 0,
`heal_count` 0, Automat durchgehend an. **Modul 20× entladen/laden** (`analyse/audio/modul_zyklen.sh`, Dienst gestoppt): 20/20, 34 s gesamt, Patch
jedes Mal neu geladen, danach Dienst wieder an, Ton an. **GUT-Stand:** `tftp/h713-kernel-netboot.fit.GUT-d5fd82a7` (identisch mit dem aktiven FIT),
`mainline/build/modroot.GUT-d5fd82a7`, Serie `patches-snapshots/20260908-1940-serie110-audio/`.

**EDID:** Marco entscheidet 21:25, die proprietäre Stock-EDID nicht zu verändern; die vorbereitete Variante ohne 4K wurde verworfen. Der 4K-Fall
wird in Treiber/`hy310-tv` abgefangen (BUG-4k-Notiz).

**Gerätetöne (Plan 101 §5, Frage „ein Regler"):** `ctl volume` ist der eine Regler (Codec-DAC, letzte Stufe für beides). Aber: bei laufendem
HDMI-Ton (48 kHz) ist `aplay -D hw:0,0 500 Hz` am Mikro nicht vorhanden (−59,5 dBFS bei 1 kHz −25,2); nach Ende des Prüftons hält der Laptop den
HDMI-Audiostrom mit 44,1 kHz Stille offen (`present=1`, 12 s beobachtet), Codec bleibt I2S, `aplay` scheitert an `hw params`. Mit PC-Quelle gibt
es also keine Gerätetöne. Stock löst das im DSP (Pfad `0x89`, `MIXER2`, S23) — Vorschlag: Paket „Audio-Bridge + Mischgraph" (Plan 102).

## 21:50–22:05 — Lippensynchronität abgenommen; Falle: PipeWire verliert die HDMI-Senke

**Lippensynchronität:** Marco schaut ein YouTube-Video (Firefox am Zuspieler, 48 kHz) über die Kette HDMI → MSP-DSP (ohne DELAY1) → Codec:
**„es ist perfekt — synchron“.** Damit ist Plan 101 §5 vollständig. Ein Sync-Testvideo (Blitz + Piep je Sekunde, roter Balken kreuzt die Mitte
beim Piep) liegt als `/tmp/lipsync.mkv` am Zuspieler (ffmpeg-Rezept in diesem Abschnitt der Sitzung), falls später objektiv gemessen werden soll.

**Zuspieler-Falle Nr. 2:** Nach `xrandr HDMI-2 --off/--mode` und meinen direkten `aplay -D hw:0,3` war in PipeWire die HDMI-Senke weg
(Standardsenke `auto_null`, Karte aber im Profil `output:hdmi-stereo+input:analog-stereo`, Port „available“). `xrandr --set audio on` + Modeset
half nicht; **Profil aus und wieder an** (`pactl set-card-profile alsa_card.pci-0000_00_1f.3 off`, dann wieder das HDMI-Profil) legte die Senke
neu an; danach `set-default-sink`, laufende Streams mit `move-sink-input` umziehen, `amixer -c0 cset numid=26 on`. Ohne das spielt ein Browser
still ins Leere, und der Beamer bekommt nur den 44,1-kHz-Leerstrom.
