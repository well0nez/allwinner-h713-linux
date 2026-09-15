# Bug: nach einem 4K-Modus am Zuspieler kommt das 1080p-Bild nicht zurück (08.09.2026, ~22:15)

**Gemeldet von Marco:** Laptop auf 4K gestellt → Bild schwarz (erwartet, unsere Kette kann kein 4K), **Ton lief weiter** (HDMI-Audio über den
DSP ist vom Bildpfad unabhängig - schöner Nebenbefund). Zurück auf 1080p → Bild kaputt.

## Befund (Boardzeit 23:00-23:07, Host 22:00-22:07)

- Journal (`re/captures/weltneuheit/bug-4k-rueckkehr-20260908.log`): 23:00:52 „kein Signal", 23:00:53 **`QUERY_DV_TIMINGS: Numerical result out of
  range`** (4K), dmesg **`INCAP-Zeilenabstand 0x00780078 passt nicht zur Breite 4096`**; 23:01:07 „kein Signal"; 23:01:08 Signal 1920x1080p,
  Puffer/Plane gesetzt, dann **„Wechsel im Gang -- die Geometrie steht noch nicht"**, nach 40 Nachfragen aufgegeben.
- Foto `wand-aktuell/bug-4k-zurueck-1080p.jpg`: Bild sichtbar, aber **horizontal verdoppelt/versetzt** (Zeilenabstand passt nicht zum Ring-Inhalt).
- Treiberstatus: `signal: vorhanden`, `timings: 1920x1080p`, `capture: freigegeben`, aber **`streaming: nein`, 0 Frames**; Firmware-`signal-info`
  bleibt bei **`signal_id 19, 1280x720, 30 Hz`** (alter Zustand aus der 720p-Phase davor), `SignalChange` steht bei 24 und zählt nicht weiter;
  `v4l2-ctl --query-dv-timings` → **`No locks available`**.
- **`hy310-tv ctl resync`**: keine Wirkung (keine Ereignisse, kein dmesg). **`systemctl restart hy310-tv@video1`**: wieder „Geometrie nicht eingerastet",
  Konsole bleibt. Die Firmware liefert also nach der 4K-Phase keine gültige Signalinfo mehr; unsere Kette wartet korrekt, kommt aber nie weiter.

## Deutung

Die MIPS-Firmware kennt den 4K-Modus nicht (`kHalSignalID_*`, vgl. 60-offen „Firmware-Grenzen"); nach dem Rückweg meldet sie einen veralteten
Signalzustand und feuert keine `SignalChange`-Rückrufe mehr. Der Treiber bildet `QUERY_DV_TIMINGS` auf diese Firmware-Info ab (→ `ENOLCK`), obwohl
INCAP längst 1080p sieht. Offen: ob ein Quellen-Aus/Ein am Zuspieler (TMDS weg) die Firmware wieder aufweckt (Test unten), und ob der Treiber bei
„INCAP hat Geometrie, Firmware nicht" selbst nachhelfen sollte (SetSource-Zyklus wie `0130`, oder Timings aus INCAP statt Firmware).

## Erholung

| Versuch | Wirkung |
|---|---|
| `hy310-tv ctl resync` | keine (keine Ereignisse, kein dmesg, Firmware-Info bleibt 720p30) |
| `systemctl restart hy310-tv@video1` | Neuaufbau läuft, wieder „Geometrie nicht eingerastet", **Konsole** statt Bild |
| **HDMI am Zuspieler aus/an** (`xrandr --off`, 4 s, `--mode 1920x1080 --rate 60`) | **heilt:** `SignalChange` zählt weiter (26), Firmware `signal_id 21 1920x1080 60 Hz`, `QUERY_DV_TIMINGS` liefert 1920, Bild zurück (`wand-aktuell/bug-4k-nach-hdmi-neu.jpg`) |

Ton (Übergangslösung: DSP-Pfad, Halter) hat die ganze Episode ohne Handgriff überlebt; PipeWire-Sink am Laptop musste nach dem HDMI-Aus/An
nur neu als Standard gesetzt werden (Profil bleibt).

## Zu tun

1. **EDID:** keine Modi anbieten, die die Kette nicht kann (4096×2160/3840×2160, 120 Hz, 1600×900) - dann kann der Zuspieler sie nicht wählen (Prüfung der
   aktuellen `hy310-edid.bin` siehe unten/60-offen).
2. **Treiber/hy310-tv:** wenn INCAP eine gültige Geometrie zeigt, die Firmware aber keine Signalinfo liefert (kein `SignalChange`), nach Frist
   einen SetSource-Zyklus (wie `0130`) auslösen oder die Timings aus INCAP nehmen; `hy310-tv` sollte nach n Fehlversuchen die Quelle selbst
   neu anstoßen statt „bis zum nächsten Ereignis" zu warten.
3. Reproduzieren mit 3840×2160 und mit 4096×2160@24/30, um zu sehen, ob die Firmware beide gleich behandelt.

**Nachtrag 22:20:** Nach dem HDMI-Aus/An war der Zustandsautomat zwar wieder eingerastet, das Bild aber weiter horizontal gestaucht und doppelt
(Fotos `bug-4k-nach-hdmi-neu.jpg` - von mir zunächst falsch als „normal" gelesen). **Geheilt hat die Folge aus beidem** (Marco, 22:22): HDMI neu verbinden (Firmware rastet wieder ein) **und danach** ein Modewechsel am Zuspieler
(1280×720 → 1920×1080, `wechsel.sh`) für die Bildgeometrie - ein Modewechsel allein hatte vorher nicht geholfen, HDMI-Aus/An allein auch nicht. Laufende PipeWire-Streams mussten mit `pactl move-sink-input` auf den
HDMI-Sink geschoben werden (Standard-Sink allein reicht nicht für bereits laufende Wiedergabe). Offen bleibt die Ursache der Stauchung
(Ring-/Plane-Geometrie nach dem 4K-Versuch - Frage an den Bildpfad, nicht an Audio).

## Nachtrag 21:00 - EDID-Variante ohne 4K liegt bereit

Warum der Zuspieler 4096×2160 anbietet: die Stock-EDID (`analyse/arisc/hy310-edid.bin`, zwei 256-B-EDIDs: HDMI-1.4- und 2.0-Fassung)
nennt in beiden Video-Blöcken die VICs 93/94/95 (3840×2160p24/25/30), 98/100 (4096×2160p24/30), in der 2.0-Fassung zusätzlich 96/97/101/102
(2160p50/60, 4096p50/60) und 63/64 (1080p120/100), dazu HDMI-VICs 1-3 im VSDB und maxTMDS 340/300 MHz. Der Stock-Scaler nimmt 4K und
rechnet herunter; unsere Kette kennt diese Geometrien nicht (Firmware liefert dann veraltete Signalinfo, siehe oben).

**`analyse/arisc/hy310-edid-1080p.bin`** (512 B, md5 `33235180…`): beide CEA-Blöcke neu aufgebaut - VICs 63/64/93-102 entfernt, VSDB auf
10 Byte gekürzt (HDMI_Video_present aus, keine HDMI-VICs), **maxTMDS 150 MHz**, YCbCr-4:2:0-Blöcke (ext. Tag 14/15) entfernt, Audio-Blöcke,
Video-Capability und Vendor-Video-Block unverändert, Basisblöcke (DTD 1920×1080 @148,5 MHz, Name `SGD SX8`) unverändert, Prüfsummen neu.
Verbleibende VICs: 1.4: 31 32 33 34 16 1 4 7 6 3 2 17 18 19 21; 2.0: 16 34 32 31 20 5 4 7 6 3 2 1 17 18 19 21. Original bleibt als
`hy310-edid.bin` liegen (`re/captures/weltneuheit/s11-20260908/hy310-edid.orig.bin` ist die Sicherung).

Einspielen (nach dem Audio-Dauerlauf, mit Kaltstart): vom Board aus `install -m 0644` nach `/lib/firmware/hy310-edid.bin` (NFS-Root ist
host-seitig root-owned), Kaltstart mit TFTP-Prüfung, dann am Zuspieler `xrandr` - es dürfen keine 4K- und 120-Hz-Modi mehr erscheinen -
und den 4K-Fall nachstellen: nicht mehr anwählbar. Rückweg: Original zurückkopieren, Kaltstart.

**Entscheidung Marco 21:25:** Die EDID wird **nicht** verändert (proprietäre Stock-Daten bleiben, wie sie sind); die Variante wurde verworfen.
Der 4K-Fall ist stattdessen in Treiber/`hy310-tv` abzufangen: Geometrie ohne Firmware-Signalinfo → nach Frist SetSource-Zyklus statt endlos warten.

## Nachtrag 22:25 - mit Kernel `d5fd82a7` (GUT, Serie 110) nicht reproduzierbar

Drei Sequenzen am Zuspieler per `xrandr`, jeweils mit Status, `--query-dv-timings`, Journal und Foto (`wand-aktuell/4k-repro-zurueck.jpg`,
`4096-repro-zurueck.jpg`, `720-4096-1080.jpg`): **3840×2160@30 → 1080p**, **4096×2160@30 → 1080p** und die Originalfolge
**720p → 4096×2160@30 → 1080p**. Jedes Mal: Firmware meldet bei 4K `signal_id 0x18/0x19` mit 3840/4096×2160 (sie kennt die Modi also),
Treiber `QUERY_DV_TIMINGS → ERANGE` (erwartet), Bild schwarz, **Ton läuft weiter**; nach der Rückkehr `signal_id 0x15 1920×1080`, Timings
gültig, „Plane 38 an", **Bild korrekt** (keine Verdopplung), `SignalChange` zählt durchgehend weiter (14 → 28). Der Zustand vom Abend
(Rückrufe bleiben aus, Info bleibt bei 720p30) trat nicht ein. Unterschiede zu damals: frischer Kaltstart 19:54, Kernel `d5fd82a7` statt
`1f3614a1`, kein `/dev/mem`-Audiohalter mehr neben dem Treiber. Ob einer davon die Ursache war, ist offen - der Fall bleibt als Beobachtungspunkt,
der Robustheitsumbau (Frist + SetSource-Zyklus/HPD-Replug) wird **zurückgestellt**, bis er wieder auftritt. Werkzeug dafür läge bereit:
`echo "hpd 0 reset" > /sys/kernel/debug/h713-arisc/cmd` simuliert ein Neuverbinden (ungetestet im Fehlerfall). Arbeitskopien für einen
späteren Patch: `analyse/bild/arbeit/4k-robust/`.
