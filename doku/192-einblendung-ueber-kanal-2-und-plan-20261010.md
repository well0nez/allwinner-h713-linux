# 192 - Einblendung über dem HDMI-Bild in Hardware: über Kanal 2, nicht OSD-A; Kernel 0251 und der Gesamtplan (10.10.2026)

**Kurz:** Der Auftrag war, die Hardware-Ebene OSD-A (AFBD-Kanal 1) zu öffnen, damit Linux eine Einblendung über das
unverzerrte HDMI-Bild legen kann wie Stock seine Android-Oberfläche (TODO 2.41). Ergebnis des Pakets
`arbeit/osd-a-20261010/` (eigene Sitzung, 10.10. abends): **Stock benutzt OSD-A gar nicht**, ein "Tor" für Kanal 1 gab
es nie. Stock legt seine Oberfläche auf **Kanal 2 (OSD-B)** - den Kanal, auf dem unsere Konsole läuft - und die Hardware
mischt Kanal 2 über das Video. Dass Video und Konsole sich bei uns ausschließen, war **unsere Treiberentscheidung**
(Selektor ohne Bit 28). Am HY310 gemessen: Kanal 2 mit Alpha je Bildpunkt über laufendem, gewarptem HDMI-Bild,
59,3 Bilder/s, kein Bild verloren, keine Mehrlast; vorverzerrt passt die Einblendung zum Trapez. Kernel-Patch **0251**
macht das über DRM verfügbar (Standard unverändert). Dazu ein mit Marco abgestimmter **Gesamtplan** für Einblendungen,
Tasten, Desktop und einen sparsameren Warp (§5) - die Richtung für alles Weitere an der Anzeige.

## 1 Was Stock tut (offline, Belege im Paket `laeufe/p1-*`)

| Befund | Beleg | geprüft |
|---|---|---|
| Der Stock-HWC schickt seine Oberfläche immer an `osd_id 1` | `vendor_a_hwcomposer.ares.so`, `Compositor::setupOsdLayerConfig` @0x27BFE: `movs r0,#1; str r0,[r4,#8]; str r0,[r4,#4]` | von der Hauptsitzung am Maschinencode nachgesehen |
| `osd_id 1` = fb0 "TV303 SVP OSD3" = AFBD-Kanal 2 (`0x05600140`), Ebenen-Block `0x0524C000`, Selektor `0x051C006C`; `osd_id 0` (OSD-A) nutzt der HWC nicht | `ge2d_dev.ko` | Paket |
| `OSD_AFBD_REG_OFFSET` (`.rodata+0x280`) = `{0x05600100, 0x05600140}`; `osd_afbd_irq` liest `0x05600128`/`0x05600168` | `ge2d_dev.ko` (ELF32) | Hauptsitzung: `.rodata+0x280` gelesen, stimmt |
| In allen Stock-Abzügen ist OSD-A zu: `0x0524801C = 0`, `0x051C0060 = 0`, `0x0520002C = 0`, ch1 ohne Adresse und Geometrie (`0x110`-`0x13c` = 0); was in ch1 steht, ist ge2ds Kaltöffnung beim Start. **`0x104 = 0` unter Stock heißt "nie geschrieben", nicht "verbraucht"** | Stock-Abzüge, `init_osd_plane` | Paket |
| Mischen: `tgd_put_plane_info` setzt den Selektor auf `alt \| 0x29000000` (Alpha-Modus 1) oder `(alt & 0xD6FFFFFF) \| 0x21000000`, Alphawert in `0x051C0070[7:0]`; Bit 28 (Video-Weg) bleibt stehen | Dekompilat ge2d | Paket |
| Byte-Reihenfolge: `PLANE+0x1C` = `(alt & 0xFFF000ED) \| (swz << 8) \| (fmt << 16)`; RGBA8888 `swz = 0xE4`, AFBC `0x1B` | Dekompilat ge2d | Paket |
| Kein Firmware-Auftrag für OSD (81 Routinen; Stock schickte im mitgeschnittenen Boot 45 Aufträge, keiner OSD-bezogen), kein Firmware-Registerschreiber der OSD-Ketten, kein OSD-Bit im memory_agent, Takte/Resets/Power am Prompt bitgleich zu Stock | `display.bin`, Mitschnitte | Paket (nicht vollständig gegengeprüft: die Analyse-Läufe wurden wegen des Verbrauchs abgebrochen) |
| **Trapez unter Stock:** der HWC gibt der Firmware für das HDMI-Bild nur ein Rechteck; SurfaceFlinger (Transaktion 1050) speichert die Ecken und verzerrt in `GLESRenderEngine::keystoneRendering` - also mit der GPU in der Komposition. Keine Hardware-Verzerrung gefunden | HWC, SurfaceFlinger | Paket, offline, **mittel sicher**; der TV-Input-HAL lag nicht im Material, AP2ks "NULL-Sideband" (`doku/131`) wäre dann für den Trapez-Fall unvollständig |

## 2 Gemessen am HY310 (10.10.2026 abends, mit Marco)

Von Hand über `/dev/mem` (Sicherung `/root/sicherung-osd-a/` auf der Box), Wandfotos mit der Kamera der Box:

| Lauf | was | Ergebnis |
|---|---|---|
| K1 | Kanal 2 an (`0x05600140 = 0x03001901`, Latch), Selektor `0x39000000` / `0x31000000` | Latch verbraucht, aber nur Video sichtbar - **Bit 28 = nur Video** |
| K1 c2 | `0x29000000` + globales Alpha `0x80` | Muster und Video gemischt |
| K1 e | **`0x21000000`, Alpha `0xff`** | **Video überall, das deckende Muster darüber** - Alpha je Bildpunkt |
| K3 | 30 s Einblendung über laufendem Warp | **59,3 Bilder/s, kein zusätzlich verworfenes Bild**, Last wie ohne (`h713-warp` 13,6 %, `sugov:0` 14,6 % eines Kerns) |
| K5 | Rahmen und Lautstärke-Pille, auf dem Host mit der Homographie des Warps vorverzerrt | liegen auf dem verzerrten Bild - die Hardware-Einblendung passt zum Trapez, ohne dass der Warp sie zeichnet (ein Foto) |
| K7 | Byte-Reihenfolge `0x0524C01C[15:8]`: U-Boots `LogoRegData` lässt `0x06` (Farben XRGB, **Alpha aus dem Blau-Byte**); `0xC6` = Alpha aus Byte 3 | mit `0xC6` Rot, Grün, Blau richtig, Video durch die durchsichtigen Stellen |
| D1-D4 | Kernel `main` 8b663b8 + **0251** per Schnell-Deploy, `drmtest.py` (rohe DRM-ioctls) | Primär-Ebene `zpos` 2: Kanal 2 an, Selektor `0x21000000`, `0xC6`; `zpos` 0 und Video aus: Register wie vorher - der Treiber schaltet allein über DRM wie die Handversuche; nach dem Boot Warp 59,4 Bilder/s, keine ausgefallene Unit |

Die Kamera übersteuert helle Flächen; Farben sind nach Marcos Blick und den Kamerakanälen richtig, genau gemessen nicht.

## 3 Kernel 0251

`0251-drm-h713-afbd-the-rgb-channel-over-the-video-plane.patch`: Primär-Ebene `zpos` 0..2 (Standard 0 = Verhalten wie
bisher), Video-Ebene `zpos` 1 fest. Mit `zpos` 2 bleibt Kanal 2 an, wenn die Video-Ebene läuft: ARGB8888 -> Selektor
`0x21000000` + Byte-Reihenfolge `0xC6`, XRGB8888 -> deckend; zurück auf `0x39000000` und den Ruhewert, sobald die Ebene
wieder darunter liegt oder das Video ausgeht. Neues optionales DT-Fenster `osd` (`0x0524C000`, 0x100); ohne es wird ARGB über
dem Video abgelehnt. Gebaut ohne Warnung (`W=1`), am HY310 gemessen (§2 D1-D4). Der HY310 läuft seitdem diesen Kernel
(damit erstmals auch 0246-0250 dort), Rückweg `/root/osd-a-rueckweg.sh`. **Nicht gemessen:** Bildrate der Aufnahme mit 0251
während einer Einblendung mit laufendem Warp (von Hand K3: 59,3/s), Farben genau, `premultiplied` gegen `coverage` (0251 bietet
keine Blend-Mode-Eigenschaft an), `zpos`-Wechsel bei laufendem Seitenwechsel, Signalverlust/-rückkehr, Standby mit
Einblendung, der G-EU.

## 4 Was im Journal falsch stand

| Eintrag | stand dort | richtig |
|---|---|---|
| `doku/64` §2/§6, `doku/86` §1, `doku/85` B.3-B.5 | "Stock hat AFBD-Kanal 1 aktiv und bedient", "das Tor für ch1 liegt außerhalb der AFBD-Seite", OSD wird "vor dem PROC" eingemischt | ch1 ist unter Stock zu (`0x104 = 0` = nie geschrieben); Stocks Oberfläche liegt auf Kanal 2, gemischt am Selektor (`0x21000000`/`0x29000000`) |
| `doku/84` §3.4 | `OSD_AFBD_REG_OFFSET` = `0x05600300`/`0x05600340` | `0x05600100`/`0x05600140` |
| `doku/62` (Zeile ~391) | `0x1A000005`/`0x00350000`/`0x08100035` nach `0x05200040/50/54` | nach `0x051C0014/24/28` |
| `doku/131` (Nachtrag 23.09.) | drei Versuche, das "Tor" für OSD-A am U-Boot-Prompt zu öffnen | die Prämisse trug nicht; dazu standen in den Vorlagen AP3j/AP3n/OSD1 (lokal) zwei Vorzeichenfehler: `0x05248000 = 0x80FC0208` (nicht `0x7F03FDF8`), `0x05600100 = 0x83001901` (nicht `0x7CFFE6FF`) |
| (Paket-Befund, nicht nachgeprüft) | memory_agent-TVTOP-Gruppe bei `0x068B00xx` | `0x068C00xx` |

Die alten Einträge bleiben; sie tragen jetzt einen Hinweis im Kopf.

## 5 Der Gesamtplan (Marco, 10.10.2026 abends - Richtung für die Anzeige)

1. **Kernel:** 0251 - Kanal 2 über der Video-Ebene, ARGB je Bildpunkt (§3).
2. **Ein Einblende-Zeichner für alle Einblendungen** (Lautstärke, Stumm, Fokus, später Ausschalten 2.38): gleichzeitige
   Einblendungen gestapelt in **einem** Bild, dieses eine Bild als ARGB auf Kanal 2. Das Zeichnen aus Deepseeks `osd.c`
   (Paket `warp-konsole`) übernehmen, **die Optik neu** (Marco: die Ausführung ist ungenügend). Bei Trapez mit derselben
   Homographie wie der Warp vorverzerrt (K5), neu gerechnet nur bei Änderung von Inhalt oder Ecken. Committen muss der
   DRM-Master: heute `h713-tv` (Zeichen-Bibliothek eingebaut, `ctl osd ...`) oder per DRM-Lease.
3. **Regel statt Konsolen-Sonderweg:** wer auf Kanal 2 zeichnet, zeichnet verzerrt - wie Stocks SurfaceFlinger
   (`keystoneRendering` als letzter Schritt). Ein späterer Desktop-Compositor setzt die Trapez-Matrix als letzten Durchgang
   und zeichnet die Einblendung davor. Die Kernel-Konsole (fbcon) kann nicht verzerren und bleibt unverzerrte Notfall- und
   Startkonsole; die Alltags-Konsole wird ein Terminal im Desktop.
4. **Was für einen späteren Desktop jetzt schon gilt:** (a) **eine Matrix-Quelle** für die Trapez-Geometrie (Ecken, Zoom,
   Projektionsmodus) mit Änderungsnachricht - Warp, Einblende-Zeichner und Compositor rechnen mit derselben Funktion, sonst
   nicht deckungsgleich; (b) Zeichnen und Ausgabeort trennen - der Zeichner liefert ein Bild, ohne Desktop legt ein dünner
   Ausgabe-Teil es auf Kanal 2, mit Desktop zeichnet der Compositor es als oberstes Element; (c) Video-Ebene unten, Desktop auf
   Kanal 2 mit durchsichtigen Stellen (Alpha je Bildpunkt, gemessen K3/K7); mit Trapez zwei GPU-Teile (Warp, Compositor),
   zusammenlegen wie Stock ist eine spätere Optimierung; (d) DRM-Master heute `h713-tv`, später der Compositor - nichts
   dauerhaft an `h713-tv` binden.
5. **Tasten:** `h713-keys` (IR + Bluetooth) bleibt, erweitert um Home, Menü, Maus, Record, Steuerkreuz.
6. **Warp sparsamer** (eigenes Paket, erst messen): der Takt-Regler `sugov:0` kostet 14,6 % eines Kerns, so viel wie der Warp
   selbst (14 %). Ansätze: fester Takt oder `rate_limit_us`; `-O3 -mcpu=cortex-a53`, LTO, NEON wo die CPU Pixel anfasst; der Warp
   committet selbst statt über den `h713-tv`-Socket; Aufnahme-Puffer einmal je Slot als EGLImage; GPU-Fences statt Abfragen;
   gleiche Bilder überspringen; Luma/Chroma in einem Durchgang; GPU-Takt prüfen. Andere Sprache: kein Gewinn erwartet.

## 6 Werkzeug-Funde nebenbei

- `release/tor.sh` meldet in einem gebauten Worktree Scheinfunde (203 459 im Paket), weil `sperr-scan.py` `os.path.isdir(".git")`
  prüft und `.git` dort eine Datei ist (TODO 5.13, Behebung `os.path.exists`).
- `build/build.sh kernel` packt den FIT nicht, wenn das U-Boot-Submodul fehlt (`find_mkimage` baut `mkimage` daraus); der
  Container hat `/usr/bin/mkimage` - Rückfall darauf.
