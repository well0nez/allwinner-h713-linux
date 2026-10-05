# Plan 132 - Fable-Pakete ohne Geraet (26.09.2026)

Marco, 26.09.: "mach direkt hdcp 1.4 und 2.2, edid, geraetetoene mischen, ge2d, und die keystone-sachen: plaene, die
agenten duerfen in eigene ordner ihre patches und arbeiten machen, nichts an live, nichts ins git bzw. wenn git nur in
deren eigenen ordnern, workspace clear davon lassen."

## Regeln (umbau/plan/briefs/FB-common.md)
- Agenten schreiben nur nach `umbau/work/FB-*/`. `umbau/src` ist tabu (kein Edit, kein git, kein Bau). Git nur per
  `git init` im eigenen Ordner.
- Code als Patches gegen `umbau/src` @ `79afae3` (main), Kernel-Patches im Stil der Serie gegen den gepatchten Baum.
  `patch -p1 --dry-run` muss im Bericht stehen.
- Tests laufen in der eigenen Kopie des Werkzeugs. Kein Geraet. Verbotene Ordner wie immer (re/, analyse/hdcp-keys/,
  hy310-sicherung*, fixtures-local/secure*, work/PQ1/material/).
- Jeder Brief nennt einen Massstab (Datei + Zeilen); der Bericht misst mit `wc -l`.
- Integration nur durch Claude, nach Review (`umbau/reviews/FB-*.md`), dann Geraetetest am HY310 nach der Liste im
  Bericht.

## Pakete
| Paket | Inhalt | Liefert | Geraetetest danach |
|---|---|---|---|
| FB-HDCP14 | HDCP 1.4 ueber die Crypto Engine (Plan 112/114): CE-Task im Vendor-Deskriptor, Key-Select 3, Senke 0x03041400, vor dem MIPS-Start; KAT als Selbsttest davor; SMC-Frage | Kernel-/U-Boot-/TF-A-Patches, h713-hdcp-key-Erweiterung, Testfolge | KAT, SID Bit 17, Transfer; Stromzyklen laut Bericht |
| FB-HDCP22 | HDCP-Zustand sichtbar machen (Version, authentifiziert, Key geladen, letztes Ereignis) in `h713-tv ctl status` | RE-Tabelle, Patch(es) | HDCP-pflichtige Quelle stecken, zwei Zeilen lesen |
| FB-EDID | EDID-Bloecke gegen die Firmware-Modustabelle: Decoder, CSV, Blockmaske erklaert, 1600x900 und 1080p100/120 als Entscheidung | tools/edid-modes.py, CSV, Patches | PC-Modusliste durchfahren |
| FB-AUDIO | Plan 102 H+I: ALSA-PCM auf hy310hdmi ueber die Audio-Bridge in Graph 0x89, h713-tv-Automat | Kernel-Patches, h713-tv-Patch | Plan 102 4 (Mikro) |
| FB-GE2D | Inventar des Vendor-Displaystacks, Luecken mit Urteil, Design; Patch nur fuer <100 Zeilen und einen Stromzyklus | CSV, Bericht, evtl. ein Patch | je Luecke |
| FB-KSREF | keystone-auto rechnet ohne Referenzdatei gegen das Ideal (0,0,1 g), Referenz verfeinert; Seite zeigt es; Tests | Patches h713-keystone/h713-panel, Tests | Sensor-Einbaufehler mit Wasserwaage messen |
| FB-AFWAIT | Autofokus wartet, bis das Muster an der Wand ist; Tests fuer return_to_best und die Verweigerungstexte; h713-focus bekommt tests/ | Patch h713-autofocus, Tests | Kaltstart, ein Lauf, `stopped: peak` |

Briefs: `umbau/plan/briefs/FB-*.md`. Nicht als Paket, weil nur am Geraet: HDCP 2.2 selbst (Quelle stecken), PWM-Info
auch fuer den HY310, Lampen-Pulsieren in FEL, Sensor-Offset messen.

## Reihenfolge
Alle sieben parallel (Fable, Hintergrund). Review in der Reihenfolge, in der sie fertig werden; integriert wird erst
nach Marcos Blick auf den Bericht, Geraetetests gebuendelt, wenn der HY310 wieder da ist.

## Ergebnis der Welle (26.09., alle sieben fertig, nichts integriert)
| Paket | Kern | Bericht | Geraetetest |
|---|---|---|---|
| FB-KSREF | Ideal-Referenz umgesetzt (+22 Zeilen, 143+25 Tests); Referenz vom 22.09. liegt 9,15 Grad Pitch neben dem Ideal - erst messen (Wasserwaage, 180-Grad-Drehung), dann Regel <1/1-3/>3 Grad | 192 Z. | 10 min, 0 Zyklen |
| FB-GE2D | kein Port noetig; ein Kandidat LVDS-FIFO-Waechter (0x05880FE0 / 0x05700088 Bit 8) - erst messen; DLPC3435 toter Code; Suspend-Fakten fuer Plan 104; Spiegelung = 40 Zeilen im Warp | 326 Z., 179 Fkt. | 12 min lesend |
| FB-AFWAIT | Ursache dunkler Erstlauf = Kamera-Schwarzbild; warm_up wartet auf Pegel-Plateau >= 3227, weckt die Kamera; Tests fuer return_to_best; h713-focus hat tests/ | 170 Z. | Kaltstart, ein Lauf |
| FB-HDCP22 | `ctl hdcp` (Version, authentifiziert, Keys, Firmware-Ereignis) ueber debugfs+elog; "LoadKey ok" ist nur Formatpruefung | 182 Z. | 2.2-Quelle stecken |
| FB-HDCP14 | Treiber h713-ce.c (KAT -> RSSK-Probe -> Senke), Reload-RPC nach dem Bring-up, SID Bit 17, h713-hdcp-key beide Items; TF-A-Variante entworfen | 264 Z. | 9 Schritte, 1-3 Zyklen |
| FB-AUDIO | S33/S34 gab es nie - RE nachgeholt; PCM hw:hy310hdmi,0 ueber Audio-Bridge -> ABPO1 -> DECODER3 -> MIXER2, Graph 0x89; h713-tv-Automat | 246 Z. | 30 min, 2 Zyklen |
| FB-EDID | zwei EDIDs im Bin; Block 1 bringt 1080p100/120 (Records 13/15 aktiv); Blockmaske ist Bench-Knopf (kein debugfs im Release); Stufe A: S_EDID mit einer Haelfte, `edid = block0|block1`, `ctl edid`; 1600x900 unloesbar ohne TSE-Aenderung | 282 Z. | 25 min, 1 Zyklus |

Naechster Schritt: Reviews `umbau/reviews/FB-*.md` (Claude), Kernel-Patches im Container bauen (0167/0167a/b, 0168,
0169/0170, 0136z/0167-EDID - Nummernkollision 0167 zwischen HDCP14 und EDID Stufe B beim Integrieren aufloesen),
dann Geraetetage am HY310 gebuendelt: KSREF-Messung, GE2D-FIFO-Lesung, AFWAIT-Kaltstart, HDCP22 mit Quelle,
HDCP14 in 9 Schritten, AUDIO, EDID.
