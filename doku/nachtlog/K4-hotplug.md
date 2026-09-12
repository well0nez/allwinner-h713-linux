# K4 — Hot-Plug nach dem Boot (Board-Agent = Hauptsitzung)

Messung 06.09.2026, 21:47–21:57, Board seit Kaltstart 21:08 in der Sequenz aus Nachtplan Abschnitt 1.
Alle Abzüge: `re/captures/weltneuheit/ours-20260907-nacht/00-ausgangszustand/`.

## 0. Instrument zuerst geprüft (Regel 7)

**Kamera.** `exposure_auto = 3` (Automatik), `exposure_absolute = 333`, `gain = 118` — **nichts verstellt**.
Die überbelichtete Aufnahme `01-nach-unlock-2147.jpg` (mean 247,5 / std 14,2) entstand nicht durch eine
stehengebliebene Einstellung, sondern weil `ffmpeg` das **allererste** Bild nach dem Öffnen des Geräts nimmt:
das trägt noch die Belichtung der **vorigen** Szene (vorher lief der dunkle Sperrbildschirm). Dieselbe Szene
eine Minute später: mean 206,3 / std 43,7 (`02-wiederholung-2148.jpg`).
Gegenprobe im Dunkelsprung 21:50:56: ohne Vorlauf mean 172,6 — mit Vorlauf mean 139,5 (gleiche Szene,
`03-aus-ohne-vorlauf.jpg` / `04-aus-mit-vorlauf.jpg`).
→ `analyse/hdmi-seq/wandcheck.py` verwirft jetzt `WARMUP` (Vorgabe 30, `WAND_WARMUP=` übersteuerbar) Bilder,
bevor es auslöst. **Die Belichtung wird weiterhin nicht angefasst.**

**elog.** Erster Durchgang: über die ganze K4-Sequenz **null Zeilen** (`rd=wr=2066`). Positivkontrolle mit einem
harmlosen, unveränderten RPC (`SetBacklightLevel 100`) blieb ebenfalls stumm → **der elog war kein gültiges
Instrument**, aus seinem Schweigen folgt nichts. Ursache: globaler Level `0x4B48BD9C` stand auf **1** (nur `E/`),
obwohl `prep_after_boot.sh` ihn auf 5 setzt — die Firmware hat ihn nach dem Prep überschrieben.
Nach dem dokumentierten Verfahren aus doku/63 (Level 5, Tabellenmodus aus) liefert derselbe RPC 122 Zeilen
inkl. `Session19(RETURN): WAIT ACK completion`. Erst danach wurde gemessen.

## 1. Signalverlust ohne HPD-Wechsel (`xrandr --output HDMI-2 --off/--auto`)

| Zeit | Aktion | INCAP `0x06940104` | Wand | HPD-Zähler `0x11722c` |
|---|---|---|---|---|
| 21:50:56 | Quelle aus | eingefroren (`0x3EEA045B` zweimal in 1 s) | **letztes Bild bleibt stehen** | 0 |
| 21:51:20 | Quelle an | läuft wieder (+61/s) | Bild zurück, mean 141,0 → 141,4 | 0 |

Firmware-Sicht (elog, Stufe 5): `port1 SwitchState from 5 to 3` → `W/hdmirx port1 invalid signal!!!` →
`SetSignal dwSignal = 0x20003` → `app_top_projector.cpp:919 CallbackOfSignalChange` →
`app_callback.cpp:66 NotifySignalChange`, `source_id = kHalSourceID_HDMI_1`.
Bei Rückkehr `SwitchState 3 → 4 → 5`, danach die volle Timing-Erkennung.

**Das ist der Befund, den Paket E braucht:** der `SignalChange`-Callback der Firmware feuert bei
Signalverlust **und** -rückkehr von selbst. `V4L2_EVENT_SOURCE_CHANGE` kann daran hängen; Polling auf den
INCAP-Zähler ist dafür nicht nötig.

## 2. HPD über die ARISC (`PullHotPlug` 0x0211, Port 0)

| Zeit | Aktion | Zuspieler `card0-HDMI-A-2/status` | HPD-Zähler | INCAP |
|---|---|---|---|---|
| 21:51:54 | DOWN (value 2) | **disconnected** | Max `[0,0,0]` | eingefroren |
| 21:52:13 | UP (value 1) | **connected** | Max `[1,0,0]`, danach wieder 0 | läuft (+60/s) |

Nach UP erkennt die Firmware das Timing vollständig neu:
`numTotalPixelsPerLine 0 → 3300 → 2200`, `numActivePixelsPerLine 0 → 2880 → 1919`,
`numActiveLines 0 → 1080`, `numTotalFrameLines 0 → 1083`, `field frequency f`,
dazu AVI/VSI-InfoFrame-Auswertung (`Limit_Range`, `BT709`, Quelle erkannt als `Intel | Integrated gfx | PC`).

## 3. Antwort auf die Frage des Nachtplans

**Der Zähler `0x11722c` ist kein Ereigniszähler.** Er ist ein **Anforderungsfach**, das die ARISC selbst wieder
leert: bei DOWN bleibt er durchweg 0, bei UP steht für einen Moment genau **1** darin und ist danach wieder 0.
Das deckt sich mit doku/68 („`[0x11722c+port]` von Linux aus auf ≥1 schreiben" löst HPD aus) — das Fach ist der
Weg **hinein**, nicht die Buchführung. Wer HPD-Ereignisse zählen will, kann ihn nicht lesen; die belastbare
Quelle ist der elog bzw. der `HdmiHotPlugByPort`-Callback.

**Nicht beantwortet:** ob die ARISC auf 5-V-Detect **von sich aus** reagiert. Das braucht ein echtes Ziehen des
Kabels (nur Marco) oder die Disassembly des Handlers `0x0411 SET5VFlag` in `analyse/arisc-frame/full-disasm.txt`.
→ **Anfrage an Marco:** einmal das HDMI-Kabel am Beamer ziehen und wieder stecken, während `elog_tail` auf
Stufe 5 mitläuft; dann ist die Frage in einer Minute erledigt.

## 4. Belege

- `elog-k4-level5-20260907.txt` (851 Zeilen, ANSI entfernt) — der komplette Mitschnitt beider Versuche.
- `nacht-00-vor-A.txt` — vollständiger Registerabzug des Ausgangszustands (107 KB).
- Fotos `00-vor-A-2147.jpg` (Sperrbildschirm), `02-wiederholung-2148.jpg` (Spirale, korrekt belichtet),
  `04-aus-mit-vorlauf.jpg` (Quelle aus, Bild steht), `05-an-mit-vorlauf.jpg`, `06-nach-hotplug.jpg`.
- Zuspieler: Sitzung um 21:47 entsperrt (`loginctl unlock-sessions`), Bildschirmschoner aus (`xset s off -dpms`),
  damit die Nacht über die Regenbogenspirale als Quelle steht statt des Sperrbildschirms.
