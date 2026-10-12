# 206 - Wurzeln: PID 255 als "Sperre frei", die DSP-Blockgrenze, die Ringgröße aus INCAP, der Ring ohne Ereignis; Handoff (12.10.2026, nachmittags/abends)

**Kurz:** Marco: die sechs Befunde aus `doku/205` "am Schopf identifizieren und an der Wurzel lösen, keine Workarounds". Paket
`arbeit/wurzeln-20261012/` (`PLAN.md`, `BERICHT.md`, Skripte, Rohdaten, Offline-Auftrag `re-auftrag/`). Vier Kernel-/Userspace-Fixe, alle
gemessen, alle in `main`; einer Punkt entschieden, einer wartet aufs Release.

| # | TODO | Ursache (gemessen) | Fix | Abnahme |
|---|---|---|---|---|
| 1 | 2.67 | **PID 255.** Unser `cpu_comm` schrieb die Prozess-ID als Thread-Wort der Sperre; `0xff` ist die Markierung "frei" (Firmware: unteres Byte, `tridspinlock.c:326`; wir: ganzes Wort 255). h713-tv bekommt beim Warmstart in ~1 von 20 Fällen PID 255 → das eigene Unlock überspringt, Sperre bleibt `own=0 ref=1`, MIPS wartet ohne Timeout, jedes `open()` abgewiesen, Netz greift | Kernel **0261**: `tgid << 8 \| 1` (unteres Byte nie 0xff) | Spur (L2T) zeigt es zweimal Schritt für Schritt (Zyklus 12 und 21, beide pid255); 50 Warmstarts mit Fix ohne Treffer (vorher 3 von 41); Kodierung am Gerät nachgelesen (`tid=0x5f8701` für pid 24455) |
| 2 | 2.37 | **nicht** der Insel-Start (Selbsttest 52/52 sofort nach 300 ms): das eine 50-ms-Lesen von `0x00EE` an einer **Blockgrenze des Patch-Downloads** (`msp_kick`) lief in den Timeout und brach den ganzen Download ab → Insel-Reset = "attempt 2". Der DSP ist dort mit dem Block beschäftigt und beantwortet die **nächste** Anfrage sofort | Kernel **0262**: an der Blockgrenze bis zur eigenen 500-ms-Frist weiterfragen, leise; nach 500 ms ohne Antwort bleibt der Fehler | 30 Standbys, Ton 30x im 1. Versuch, **5 verspätete Rufe abgefangen** (Block 4/5, "answered after 50 ms, 1 request unanswered"); Messfassung davor: 2 Treffer in 20 |
| 3 | 2.68 | Nach einem Moduswechsel nennt der Firmware-Record das Signal sofort, **INCAP folgt erst mit dem Umbau der Capture-Kette** (Sekunden), ohne Callback; dazu las der Warp nur `G_FMT`, das unter einer laufenden Queue stehen bleibt (V4L2), und hing an h713-tvs letzter Abfrage | Kernel **0260**: `geometry_work` alle 100 ms, wandert active/rowbyte/out gegenüber der letzten Erkennung → `SOURCE_CHANGE`; **h713-warp**: `QUERY_DV_TIMINGS` vor `G_FMT`, jedes Ereignis = stop, neu fragen, neu importieren | 0 von 48 Wechseln (vorher 5 von 30); Treiber meldete 10 Bewegungen, der Warp folgte jedes Mal |
| 4 | 2.69 | **unsere Formel** (0136f: Höhe = Quellhöhe·Pitch/Quellbreite, Breite = Pitch) riet 912x728; die Firmware skaliert mit Panelhöhe/Quellhöhe, begrenzt durch **beide** Panelseiten, und schreibt Breite/Höhe nach INCAP `+0x86c/+0x870` (Listing: `VIncap_ConfigDownScaler`, `CalcWinSize`) | Kernel **0260**: Ring = `+0x86c` × `+0x870` beim Skalieren, Pitch = rowbyte, unplausibel → `-ENOLCK`; Scaler-Quercheck weg | Slot-Füllhöhe gemessen (letztes geändertes Byte): 1280x1024 **720** Zeilen à 912, 1366x768 718, 800x600 600; 14/14 Modi mit Bild; Marco an der Wand: 1280x1024 und 1360x768 "komplett" |
| 5 | 2.4f | GPU 64 vs. Firmware 16: rowbyte-Override wirkt nicht (INCAP schreibt weiter mit altem Pitch, auch nach Enable aus/an; die Firmware setzt ihn bei jedem Umbau neu) | **entschieden (Marco): bleibt so** - Bild ohne Trapez, Status sagt es; Weg B (linearer Import im Warp) als Entwurf in TODO | `docs/tools/h713-warp.md` "Limits", `docs/known-issues.md` |
| 6 | 2.66 | - | - | 51 Standbys heute ohne 0-fps-Fall; nach dem Release mit Fire TV |
| + | 2.55 | Fernbedienung ist Tastatur für den VT; Weg 2 (Marco) | **h713-tv** `console_restore()`: steht hinter dem letzten "login:" auf tty1 etwas, bekommt der agetty SIGTERM (getty@tty1 startet neu) | eingespeiste Tasten → `ctl off` → Prompt sauber, eine Journalzeile; sauberer Prompt → kein Neustart |

## 1 Wie gemessen

- **Kernelbaum** aus der Serie neu erzeugt (`build.sh kernel`, `linux-6.18.38-8163a3c7…`): hdmirx.ko bitgleich zum Gerät (`8d909ad5`) -
  Module aus diesem Baum über `/lib/modules/6.18.38/updates/`, Sicherung `/root/sicherung-wurzeln/`, Rückweg `/root/rueckweg-wurzeln.sh`.
- **INCAP** (`incap-dump.py`, Diff über Modi): `+0x874` active, `+0x86c/+0x870` Scaler-Ausgabe, `+0x864/+0x87c` Faktor (0xb400/65536 = 720/1024),
  `+0x924` rowbyte. **Slots** (`slot-grenze.py`): die drei Luma-Slots 1 MiB per `/dev/mem` vor/nach dem Wechsel, letztes geändertes Byte / Pitch.
- **2.68** (`repro-2.68.sh`): im schlechten Zustand INCAP schon neu, Warp alt; Journal: drei `SOURCE_CHANGE` mit altem Ring, danach INCAP-Bewegung ohne Ereignis.
- **2.67** (`cpu_comm` mit L2T-Spur: jeder ARM-Schritt an Sperre 2 mit Zeit, CPU, PID, den drei Wörtern; Ausgabe bei "no thread_id"):
  `lock: taken ... own=0 ref=1 tid=000000ff` bei `pid255`. Kein Doppeleintritt, keine Firmware-Zeile "leave Critical" im Ring. Der
  Offline-Agent (ein Opus-Auftrag, `re-auftrag/BERICHT.md`) hatte vorher das Listing durchsucht: kein weiterer Schreiber in `display.bin`,
  Shmem ungecacht (KSEG1), derselbe Hardware-Lock `0x03004130` - "die Ursache liegt auf der ARM-Seite". Richtig, nur anders als gedacht
  (er tippte auf Doppeleintritt). Der deterministische Test mit PID 255 geht nicht: nach dem PID-Umlauf vergibt der Kernel ab 300.
- **2.37** (`msp` Messfassung: Selbsttest bis 3 s wiederholen und Zeit loggen; `msp_kick` bei Timeout bis 500 ms weiterfragen):
  Selbsttest immer 0 ms, die Fehlversuche saßen in `msp_kick`. Die Hersteller-TVFE-Folge (`re-auftrag/BERICHT.md` §3: 30-45 ms, kein
  Bereitschaftsbit, kein Mailbox-Zugriff) ist dokumentiert, nicht übernommen - nicht die Ursache.
- **Reihen**: `reihe-1-2.sh` (Warmstart → 55 s → Standby 20 s per RTC → Prüfung): 21 Zyklen Messfassung (Treffer 12, 21), 20 Zyklen mit 0261
  + Messfassung msp (2 Kick-Treffer), 30 Zyklen mit 0261 + 0262 (30/30, 5 Rufe abgefangen).

## 2 Was nicht gemacht wurde

HY310 (nicht angeschlossen; 0260 nimmt dort den alten Pfad "Ring = Quelle", 0261/0262 betreffen ihn genauso); Weg B für 2.4f;
Bluetooth unter Mikro-Last; 2.66 mit Fire TV. Die Testbauten mit Spur/Logging sind nicht in `main` und nicht mehr auf dem Gerät.

## 3 Handoff (12.10.2026, ~19:30)

**`main` 6ae51b7, nicht gepusht** (seit d826479: 0260-0262, Warp-Fix, h713-tv 2.55, TODO, docs). Alles seit 234282c ist ungepusht;
Reihenfolge beim Push in `TODO.md` §1.

**HY300PRO-G-EU:** Kernel aus `main` 234282c (FIT `5fc51625`) **plus** aus `updates/`: hdmirx `3124442e` (0260), hy310-cpu-comm `18d01b80`
(0261), msp `979f95f4` (0262); h713-warp `d123adac`, h713-tv `74df3200` (beide = `main`); Originale in `/root/sicherung-wurzeln/`. `h713_gate=0`,
Sonoff `.179` an, Quelle ThinkPad 1080p60, Warp im Bypass, Journal dauerhaft (~100 Testboots heute). **Der nächste Abbild-Bau (1.1a) macht
`updates/` überflüssig**; bis dahin: `/root/rueckweg-wurzeln.sh` entfernt die Module (dann Serienstand ohne die Fixe).

**Offen:** 1.1a Release-Neubau mit allem; 2.66 nach Release (Fire TV); 2.49 Mikro-Last; 2.62 HY310 nachmessen (jetzt auch 0260-0262);
2.65 IR nach Kaltstart mit Gate 1 (Marco).
