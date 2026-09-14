# S32 — Paket E: `hy310-tv`, der Ton folgt dem Bild (Patch `hy310-tv-audio.patch`)

**08.09.2026, zwei Agentenläufe (17:55–18:10 und 18:25–18:50). Reine Schreibtischarbeit — kein Board, kein Bau des
aktiven Baums.** Auftrag `t-e-hy310tv/AUFTRAG.md`, Plan
[`101`](../101-plan-audio-treiber.md) §1 E, §2, §4; Änderung gegenüber dem Auftrag: Entscheidung 08.09. 22:10 (Lautstärke
im Codec, §4.1 unten). Belege: [`S16`](S16-hdmi-audio.md) 17:55–20:45, [`S25`](S25-re-i2sout-codec.md), [`S30`](S30-treiber-c-codec.md)
(Codec-Regler), [`S31`](S31-treiber-d-hdmirx.md) (V4L2-Regler). Quelle `userspace/hy310-tv/` (main.c 2284 Zeilen, Stand
10:40) → `analyse/audio/arbeit/t-e-hy310tv/a/`, geändert in `b/`.

## 1. Was geliefert wird

| Datei | Inhalt |
|---|---|
| `analyse/audio/arbeit/t-e-hy310tv/patches/hy310-tv-audio.patch` | `diff -Nur a b` mit Kopf (75 KB); anwenden mit `cd userspace && patch -p1 < …` |
| `hy310-tv/main.c` | +1273 / −31 Zeilen (2284 → 3662): Automat `audio`, libasound-Zugriff nach Reglernamen, `ctl audio/volume/mute`, Status, Optionen `-a`, `-t/--hdmi-trim` |
| `hy310-tv/Makefile` | `pkg-config … libdrm alsa` (nativ), `-ldrm -lasound` (quer), Kommentar zur Abhängigkeit |
| `hy310-tv/README.md` | Kopf, §5 Abhängigkeiten (`libasound2-dev`), §6 Optionen und Journal, §6a `ctl`, **neu §6b Ton** (Automat als Tabelle), §8 Grenzen, §9 Verweise |
| Unit `hy310-tv@.service`, `99-hy310-tv.rules` | unverändert |

Neue Abhängigkeit: **libasound** (ALSA-Control-API, kein PCM). Debian-Paket `libasound2-dev` gehört ins Board-Root
(`ssh root@192.168.8.141 apt install libasound2-dev`) — auch der Querbau nimmt Header und Linkernamen von dort; heute
liegt dort nur `libasound.so.2` (Laufzeit), kein Header.

## 2. Der Automat

Eingänge: Plane an/aus (`d->on`, die Bildmaschine entscheidet zuerst), die drei schreibgeschützten V4L2-Regler
`H713 Audio Present`/`H713 Audio Rate`/`H713 Audio Compressed` (0136; `VIDIOC_SUBSCRIBE_EVENT V4L2_EVENT_CTRL` je
Regler, sonst 250-ms-Abfrage), Karte `hy310hdmi` (0137), Karte `H713 Audio Codec` (0135), `ctl audio|volume|mute`,
zwei timerfds (100 ms Entprellung einmalig; Kartensuche 1 s / Abfrage 250 ms periodisch, abgeschaltet sobald
unnötig). Alle Regler werden **bei jedem Zugriff über den Namen** gesucht (ein Ioctl mehr, dafür nie eine veraltete
Elementnummer); Karten über Kurz-/Lang-/ID-Name, ersatzweise die erste Karte mit allen benötigten Reglern.

| Zustand | Bedingung | was gesetzt wird (in dieser Reihenfolge) | → |
|---|---|---|---|
| **stumm** | Bild ∧ Present ∧ ¬Compressed ∧ Rate ∈ `I2S Rate`-Menü (oder `audio on`) | `HDMI Mute Switch`:=1, `I2S Rate`:=Rate, `DAC Source`:=I2S, `HDMI Audio Switch`:=1, Timer 100 ms | Entprellung |
| **Entprellung** | nach 100 ms erneut gelesen, Bedingung noch wahr | Codec-Schalter:=an (außer `ctl mute on`), `HDMI Playback Volume`:=max+Abgleich, `HDMI Mute Switch`:=0 | **an** |
| **Entprellung** | Bedingung inzwischen falsch | `Mute`:=1, `Switch`:=0, `Source`:=APB | stumm |
| **an** | Bedingung falsch (kein Bild, kein Ton, Bitstrom, `audio off`, Ende) | `Mute`:=1, `Switch`:=0, `Source`:=APB — sofort | stumm |
| **an** | Quellrate ≠ programmierte Rate | `Mute`:=1, `I2S Rate`:=neu, `Source`:=I2S, `Switch`:=1, Timer 100 ms | Entprellung |
| jeder | `ctl mute on` / `off` | DSP-Mute (nur wenn *an*: 0/1 nach Regel), Codec-Schalter aus/an; Reihenfolge: leise zuerst, laut zuletzt | gleich |
| jeder | `ctl volume N` | Codec `DAC Playback Volume` := min + (max−min)·N/100 | gleich |
| Ende | SIGTERM/SIGINT/Fehler | Ton stumm + `Source`:=APB, Codec-Schalter zurück (falls von uns aus), dann Plane aus | — |

Der Weg nach oben ist entprellt (`Present` flattert beim Moduswechsel), der Weg nach unten nie. Rate „unbekannt"
(`audio on` ohne 0136 oder Rate 0): der Codec behält seine Rate, das nächste Ereignis korrigiert. Ein Wert, den der
Codec nicht kennt (nicht 32/44,1/48 kHz), heißt stumm mit Begründung `"I2S Rate" kennt die Quellrate nicht`.

## 3. Benutzte Schnittstellen (alle aus 101 §2, wörtlich)

Karten `hy310hdmi` / `H713 Audio Codec`; Regler `HDMI Audio Switch`, `HDMI Playback Volume` (Bereich vom Treiber
gelesen, 0 dB = Maximum), `HDMI Mute Switch`, `DAC Source` {APB, I2S}, `I2S Rate` {32000, 44100, 48000} (Menütexte
werden gesucht, nicht Indizes geraten); sysfs `/sys/class/sound/cardN/device/state` und `levels` (Kartennummer aus der
Suche); V4L2 `H713 Audio Present/Rate/Compressed`. Zusätzlich vom bestehenden Codec: `DAC Playback Volume` (0…63,
TLV −73,08…0 dB) und als Stummschalter der erste vorhandene aus {`DAC Playback Switch`, `Line Out Playback Switch`} —
der H713-Codec hat keine Mischstufe (0135-Kommentar zu 0x314), also den zweiten (S16 11:50 sah `Line Out` auf der Karte).
Beide sind **willkommen, nicht Pflicht**.

## 4. Entscheidungen

1. **Lautstärke im Codec** (08.09. 22:10): `ctl volume` = `DAC Playback Volume`, 0…100 linear auf den Reglerbereich,
   0 = kleinster Wert (−73 dB, leise, nicht aus). Die Antwort wird **von der Karte gelesen** (Wert + dB aus der TLV des
   Reglers), nie aus dem Gedächtnis: ein `amixer` von anderswo erscheint im Status statt überschrieben zu werden; beim
   Start wird die Lautstärke nicht angefasst. Ein `ctl volume` vor dem Erscheinen der Karten wird gemerkt und beim
   Finden geschrieben. DSP-Volume/-Mute bleiben Automatik.
2. **Option des Abgleichs heißt `-t DB` / `--hdmi-trim DB`, nicht `-a`.** `-a TON` (auto|on|off|none) war vom
   ersten Lauf bereits belegt und in Usage/README dokumentiert; die Langform ist wie gewünscht. 0 dB Vorgabe, bis
   −100, Viertel-dB, Komma erlaubt.
3. **Beide Karten oder keine.** Lautstärke ohne Route und Route ohne Mute sind keine halbe Kette, sondern werden
   nicht angefasst.
4. **Codec-Schalter beim Beenden zurück**, falls `ctl mute on` stand — sonst wäre das nächste `aplay` aus einem Grund
   still, den niemand mehr sieht. Der Automat selbst fasst den Codec-Schalter nur beim Lautwerden an (an).
5. **Stereo-Regler werden ganz geschrieben.** `Line Out Playback Switch` ist `SOC_DOUBLE`; ein Wertstruct mit nur
   Kanal 0 hätte rechts abgeschaltet (Fehler des ersten Laufs, im zweiten gefunden und behoben: `alsa_write` setzt
   alle `count` Kanäle).
6. Ein `V4L2_EVENT_CTRL` löst **kein** `QUERY_DV_TIMINGS` aus (20 ms Messung für eine Antwort, die niemand wollte);
   nur `SOURCE_CHANGE` oder unbekannte Ereignisse bewerten das Bild neu.

## 5. Fehlerpfade (Bild in jedem Fall unbeeinflusst — kein ALSA-Aufruf liegt auf dem Weg zur Wand)

| Lage | Verhalten |
|---|---|
| Karte fehlt / Regler fehlt | 30 Versuche im Sekundentakt (MSP bootet Insel + Firmware nach eigenem Zeitplan), dann `warnung: ton bleibt aus nach 31 Versuchen in 31 s: es fehlt die Karte "hy310hdmi" mit … (Kernel 0137)`; `ctl status`: `ton aus -- …`; `ctl volume/mute/audio` antworten „gemerkt, …" |
| V4L2-Regler fehlen (Kernel ohne 0136) | kein Automat, Warnung einmal; `ctl audio on` schaltet den Pfad von Hand |
| `SUBSCRIBE_EVENT(CTRL)` abgelehnt | Abfrage alle 250 ms, Warnung einmal |
| Reglerschreiben scheitert (z. B. Codec `-EBUSY`, weil ein PCM mit anderer Rate läuft, S30 §4.3) | Warnung **einmal** (`der Tonpfad steht nicht so, wie dieses Programm ihn meldet`), `ctl volume` meldet `fehler`; `ton-karten` zeigt die Wahrheit |
| `-a none` | keine Karte geöffnet, timerfds bleiben −1 (poll ignoriert sie), `ctl audio/volume/mute` → `fehler … -a none` |
| `-n` | Karten und Lautstärke werden berichtet, nichts geschaltet, nichts stummgeschaltet |
| Ende | `audio_close()` vor `display_hide()`: erst Ton stumm, dann Konsole zurück |

## 6. Was geprüft wurde

| Prüfung | Ergebnis |
|---|---|
| Querbau `clang --target=aarch64-linux-gnu --sysroot=/srv/h713-rootfs -fuse-ld=lld -O2 -Wall -Wextra -Wshadow -Wvla` von `b/main.c` | übersetzt, **0 Warnungen**; `a/main.c` genauso (Kontrolle des Werkzeugs) |
| Link gegen die **echte** `libasound.so.2` des Board-Roots (`-l:libasound.so.2`) | alle 36 benutzten `snd_*`-Symbole aufgelöst (`nm -D`), darunter `snd_ctl_elem_tlv_read`, `snd_tlv_convert_to_dB`; Positivkontrolle: erfundenes `snd_ctl_gibtesnicht` → Linkfehler |
| ALSA-Header | im Board-Root **nicht** vorhanden (nur die Laufzeitbibliothek) → Prototypen als Nachbildung nach `control.h` im Scratchpad; der echte Bau braucht `libasound2-dev`. Die Bibliothek prüft die Symbole, die Nachbildung die Typen — ein Prototypfehler in der Nachbildung wäre nicht sichtbar |
| Patch gegen Kopie von `a/` mit `patch -p1` | wendet sauber an, Ergebnis byteweise = `b/` |
| Am Gerät | **nicht gelaufen** (Auftrag). Insbesondere ungeprüft: Knacken des `Line Out Playback Switch`, Verhalten bei `-EBUSY`, Reihenfolge Plane-an → Present |

## 7. Offene Annahmen

1. `Line Out Playback Switch` als Codec-Mute hat auf H713 keinen Rampenregler (0x31c fehlt) — ob es knackt, ist zu
   hören. Knackt es: `audio_codec_mutes[]` in `main.c` auf `"DAC Playback Switch"` allein kürzen (dann ist `ctl mute`
   nur der DSP-Mute; eine Zeile).
2. `HDMI Playback Volume` 0 dB = Maximum des Reglers (101 §2). Der Abgleich zählt Viertel-dB, weil die TLV das tut;
   liefert 0137 einen anderen Schritt, stimmt die dB-Anzeige des Abgleichs nicht mehr (der Wert wird geklemmt).
3. Kartensuche 30 × 1 s: reicht, wenn der MSP-Treiber innerhalb von ~30 s nach dem Erscheinen von `/dev/video1`
   `running` ist. Dauert es länger, `AUDIO_SEARCH_MAX` erhöhen oder die Unit nach dem MSP ordnen.
4. Die Codec-Lautstärke wird beim Start bewusst nicht gesetzt; ohne `alsactl` steht sie nach Kaltstart auf dem
   Registerreset (DVOL 0 = 0 dB = `ctl volume 100`). Soll eine Startlautstärke her, wäre das eine Option wie `-p`.
5. `ctl volume 0` ist −73 dB, nicht Stille (Vorgabe „0 = Minimum"); Stille ist `ctl mute on`.

## 8. Testrezept am Gerät (Hauptsitzung, nach 0134–0138)

```sh
# 0) Abhängigkeit + Bau (Board-Root ist dasselbe wie der Sysroot des Querbaus)
ssh root@192.168.8.141 'apt install -y libasound2-dev'
make -C userspace/hy310-tv cross && sudo make -C userspace/hy310-tv install-cross DESTDIR=/srv/h713-rootfs
ssh root@192.168.8.141 'systemctl daemon-reload; systemctl restart hy310-tv@video1; journalctl -u hy310-tv@video1 -n 20'
#    erwartet: "ton  hy310hdmi (card N) + H713 Audio Codec (card M), Ereignisse, Lautstaerke 100 (0,0 dB),
#               HDMI-Abgleich 0,00 dB, Stummschalter Line Out Playback Switch, folgt dem Bild"
# 1) Ton folgt dem Bild: Quelle 48 kHz Dauerton -> Mikro 1 kHz >= 70 dB (S16-Messkette)
hy310-tv ctl status | grep -E '^ton'      # ton an (auto), 48000 Hz ... | ton-karten: Switch 1, Mute 0, Source I2S, Rate 48000
# 2) Rate folgt: Zuspieler auf 44100, dann 32000 -> Journal "Ratenwechsel 48000 -> 44100 Hz, kurz stumm", Ton zurueck
# 3) Lautstaerke/Mute messbar: ctl volume 50 (~ -36 dB am Mikro, Erwartung ~-36 dB), ctl volume 100, ctl mute on/off
hy310-tv ctl volume 50; hy310-tv ctl volume; hy310-tv ctl mute on; hy310-tv ctl mute off
amixer -c M cget name='DAC Playback Volume'   # muss zu "ctl volume" passen (gelesen, nicht geraten)
# 4) Verlust/Rueckkehr: HDMI ziehen/stecken, ctl resync, Modewechsel 720p/1080p -> "ton stumm (kein Bild)" sofort,
#    danach "Quelle da ... 100 ms Entprellung" -> "ton an"; keine Stoergeraeusche, kein Knacken beim Codec-Schalter
# 5) Nicht-PCM: Zuspieler auf Bitstrom -> "ton stumm (die Quelle sendet kein PCM (Bitstrom))"
# 6) Dauer: 20 x ctl audio off/on; aplay -D hw:M,0 -r 48000 parallel (Referenzzaehlung, S30 §2); 30 min Dauerton
# 7) Fehlerpfad: modprobe -r sun50i_h713_msp; systemctl restart hy310-tv@video1 -> nach 31 s "ton bleibt aus ...",
#    Bild laeuft weiter; modprobe zurueck; restart -> Ton wieder da
# 8) Abgleich: hy310-tv -t -6 ... -> Journal "HDMI-Abgleich -6,00 dB", Mikro ~6 dB leiser als bei 0 dB
```

## 9. Einspielen

`cd userspace && patch -p1 < ../analyse/audio/arbeit/t-e-hy310tv/patches/hy310-tv-audio.patch` (Hauptsitzung), dann §8
Schritt 0. Der Patch berührt nur `hy310-tv/main.c`, `Makefile`, `README.md`.
