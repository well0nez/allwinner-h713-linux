# S6 — Der Scaler-Blocker ist gefallen: die Firmware programmiert ihn selbst

07.09.2026, 21:30–23:10 · Auslöser: Marcos Hinweis auf cstengers Baum

## Woher der Hebel kam

`github.com/cstenger/allwinner-h713-mainline`, Branch `h713-display-video-path`. Er hat am
05./06.09. genau an dieser Stelle gearbeitet und drei Dinge gefunden, die uns gefehlt haben:

- **Die MIPS-Firmware hat eine Debug-Shell**, erreichbar von der ARM-Seite über einen
  RTT-artigen Ringpuffer im DRAM (`ff48f28c`). Kontrollblock-Zeiger bei System `0x4B232C20`.
- **`dtv get_fb`** als Kommando, das die Firmware den VideoInfo-Descriptor lesen lässt (`6dc63e47`).
- **`Wce_SetWindow` endet auf der MIPS-Seite in einem Stub** (`9f70bcb5`) — das erklärt rückwirkend
  jeden unserer RPC-Versuche.

## Die Shell läuft bei uns

Kontrollblock identisch zu seinem Befund: Zeiger `0x4B232C20` → `0xABD01000` → System
`0x4bd01000`, acID `"RV… TERMINAL"`, `aUp[0]` bei `0x4bd01300` (0x41c00), `aDown[0]` bei
`0x4bd01200` (0x100). Eigenes Werkzeug geschrieben (`mipsshell.py`), beide Richtungen bestätigt:

```
$ mipsshell.py --cmd cmds
app  bs  crtc  tcd3  dtv  hal  elog  memory_agent  pq
regw  regr  clear  keys  vars  cmds  users  help  setVar  win
VS:/$
```

**Wir haben eine lebende interaktive Shell in die Displayfirmware.** Zwei Ausgabekanäle: das
Kommandogerüst antwortet über den Ring, die Rümpfe der Debug-Kommandos schreiben ins elog.

Die Falle aus seinem Code, die wir dadurch nicht selbst gefunden haben: der MIPS-Carveout kommt
über `/dev/mem` als **DEVICE-Speicher**; Pythons `mmap`-Slicing macht ein `memcpy` und stirbt mit
SIGBUS, nichtdeterministisch nach Länge. Jeder Zugriff muss durch eine ctypes-uint32-Sicht.

## Die Ursache — und sie war unsere eigene

`win wm` zeigte `m_refresh_node : 0` gegen Stocks `refresh_node:2`, aber `win rn 2` setzte nur das
Flag und löste nichts aus. Der eigentliche Befund kam aus dem Detektor selbst. Über den Singleton
bei ARM `0x4b27266c` ausgelesen, bei anliegender **720p**-Quelle:

```
STM=2
+0xb0   61770000 00000002 00000780 00000438 ...    (Arbeitskopie)
+0x140  61770000 00000002 00000780 00000438 ...    (Latch)
```

Beide halten **1920×1080** — und sind byteidentisch. Der Descriptor bei `0x4d95f000` ebenso. Also:

1. Unser AFBD schreibt den VidDec-Descriptor **einmal pro Boot**, mit der Geometrie des ersten
   Enable.
2. Der VideoDec-Detektor der Firmware liest genau diesen Descriptor.
3. Arbeitskopie == Latch → die Firmware schließt korrekt „nichts geändert" → **kein
   `HandleSignalEvent`, kein `UpdateWce`, kein Fensterneubau, kein Scaler.**

Das erklärt jede Messung des Tages, auch die irreführenden: INCAP stellt sich um, weil das der
**HDMI**-Aufnahmepfad ist und unabhängig läuft; die Fenster- und Scalerseite hängt am
**VideoDec**-Descriptor, und den frieren wir selbst ein.

Der Kommentar in `sun50i-h713-afbd.c` behauptete ausdrücklich das Gegenteil („The HDMI capture and
the WCE behind it never look at it"). Für die Capture stimmt das, für die WCE nicht — und diese
halbrichtige Aussage hat den ganzen Tag gekostet.

## `0117` — und das Ergebnis

Der Patch veröffentlicht den Descriptor im Ring-Modus bei Geometriewechsel neu. Eine Zeile
(`write_record = differs && (!h->video_info_published || ring)`), plus die Korrektur des falschen
Kommentars.

Gemessen, Quelle 1080p → 720p:

| | vorher | nachher |
|---|---|---|
| Descriptor | `0x780 x 0x438` | **`0x500 x 0x2d0`** |
| Detektor `+0xb0` / `+0x140` | 1920×1080 | **1280×720, beide** |
| `0x05180008` | `0x43010000` (1:1) | **`0x3200AA66`** |
| `0x0518003C` | `0x00010000` (1:1) | **`0x0000AAAA`** |
| `0x05180014` Bit 27 | gesetzt | **gelöscht** |
| PROC `0x05140104/124` | 1920 / 1920 | **852 / 1280** |

**Die Firmware hat den Scaler selbst programmiert.** Und die Werte bestätigen die Herleitung aus
[`S3`](S3-scaler-gefunden-und-bewiesen.md) unabhängig: vorhergesagt war `0x3200AAAA`, gemessen
`0x3200AA66` — Modusfelder 3/2 exakt getroffen, das Verhältnis auf zwei Stellen, die Differenz ist
die firmware-eigene Rundung der Quellbreite (`0xAA66`/65536 = 0,6656 = 1278/1920).

## Was noch fehlt: K3

Die Veröffentlichung schaltet die Aufnahme ab (MemoryAgent `+8` → `memory_agent_onoff` löscht
`0x06940928` Bit 31), und **der Wiederanlauf bringt sie nicht zurück**:

```
[59s] Freigabe: Capture laeuft wieder nach 10 ms
[92s] Freigabe: nach 2000 ms bewegen sich die Flip-Zeiger nicht
0x06940928 = 0x600202D0     <- Bit 31 geloescht
```

Das ist RE-Frage **K3** aus [`doku/86`](../86-video-plane-nv16.md) §4, seit dem 06.09. geparkt:
„Doing that a second time froze the picture and left the capture wedged until the next cold start;
why it does not recover is open." Wir haben sie reproduziert — aber jetzt ist bekannt, was ihre
Lösung einbringt: **den vollständigen, firmware-eigenen Fensterneubau samt Scaler.**

Und wir haben ein Werkzeug dafür, das es beim letzten Anlauf nicht gab: die Shell. `memory_agent`,
`crtc`, `hal` und `regr` stehen darin bereit, um die Firmware direkt zu fragen, warum sie die
Freigabe nicht wieder setzt.

## Stand

Serie 87 Patches (`0108` zurückgenommen, `0115`–`0117` neu). Gerät nach Abschluss sauber auf 1080p
mit Bild und `0 ohne Antwort`. `hy310-tv` hat für den Versuch einen Umgehungsschalter
(`H713_TV_SKALIERTEST`), der bleibt, bis K3 gelöst ist.
