# 201 - Der Warp: GPU-Zeit gedrittelt, CPU-Takt ruhig, kein Bild Latenz mehr (11.10.2026, abends)

**Kurz:** Marco nach `doku/200`: "kannst du dir den Warp angucken und wirklich alles in Betracht ziehen - das Zeichnen selbst und
die CPU-Lastigkeit von Warp und CPU-Regler". Gemessen (CPU je Schritt mit `CLOCK_THREAD_CPUTIME_ID`, GPU-Zeit vom Abschicken bis zum
Signal der Out-Fence - Panfrosts `GL_EXT_disjoint_timer_query` ist CPU-gefälscht) und drei Dinge gefunden: **(1)** die GPU brauchte
**6,05 ms je Bild** bei 696 MHz, davon 4,4 ms für die Soft-Edge-Rechnung *nach* dem Texturabruf - die Ein-Kern-Mali-G31 versteckt
keine Texturlatenz hinter Rechnung; die Kante ist jetzt ein eigener geblendeter Ring (zehn Vertices, 1,5 Maskentexel breit),
die Bildshader ein nackter Abruf: **1,78 ms**. **(2)** der CPU-Takt pendelte 40×/s zwischen 480 und 1296 MHz, weil schedutil bei
laufenden RT-Tasks Maximaltakt anfordert und die Panfrost-IRQ-Threads (SCHED_FIFO 50) viermal je Bild laufen; `h713-cpufreq.service`
setzt sie auf SCHED_OTHER (und das 20-ms-Limit, das tmpfiles beim Boot nicht setzte): **480 MHz zu 98 %, sugov 0,1 %**. **(3)** mit
Kernel 0255 ist der übergebene Slot fertig - `hold off` ist Vorgabe (ein Bild weniger Latenz), `hold on` wäre jetzt sogar
riskant. Dazu `edid_prefer = file` als Vorgabe (Marco: 1080p bleibt 1080p). Paket `arbeit/warp-zeichnen-20261011/` (BERICHT,
`laeufe/m00-m31`, `bau/gles31-probe.c`, `kette.py`, `quellstill.py`, `stall-trace.py`).

## 1 Messwerkzeug im Warp: `ctl trace N [gpu]`

Je Bild: CPU-µs dieses Threads für Dequeue, Luma-Pass, Chroma-Pass, Fence, h713-tv-Antwort; mit `gpu` wartet die Schleife die
Out-Fence aus (das Bild ist schon übergeben, der nächste Slot eine Vsync weg) und nennt die GPU-Zeit. Bei 1296 MHz: dequeue 20,
draw 470-600 (luma 220-290, chroma 230-270), fence 180-200, tv 60 µs ≈ 0,8 ms; bei 480 MHz das 2,7-fache. Mesa-Aufrufe sparen
(Uniform-Orte, Matrix nur bei Änderung, VBO, ein Texturbind je Bild) brachte ~30 µs - die Kosten sind der Batch-Aufbau (~125 µs je
Pass) und die Ioctls.

## 2 Die GPU: 6,05 → 1,78 ms je Bild

| Variante (GPU fest 696 MHz) | GPU ms | Quelle |
|---|---|---|
| Original (Edge in den Bildshadern) | 6,05-6,10 | m13, m14 (288 MHz: 14,96; 432: 9,9 - skaliert exakt mit dem Takt) |
| `edge 0` (Uniform-Zweig überspringt die Rechnung) | 6,05 | m15 - die Rechnung ist nicht der Punkt |
| nur Luma-Pass | 4,78 | m16 |
| ohne Clears | 6,11 | m16 - Clears sind frei |
| **Kopier-Shader** (nur `texture2D` → Ausgabe) | **1,65** | m16 |
| mediump | 6,74 / 5,9 (zweigfrei) | m16, m17 |
| Kopie + ein konstanter `mix` nach dem Abruf | 2,2 | m18 |
| Kopie + `y * edge_keep()` | 4,33 | m18 |
| **Ring-Edge** (Bildshader nackt, Kante als geblendeter Ring) | **1,78** (Kante aus: 1,68) | m27 |
| Compute-Dispatch (GLES 3.1, imageStore in den importierten Puffer, `gles31-probe`) | 2,1 (Kopie) bei 357 µs CPU | m09/m10 - verworfen |

Der Ring: `gl_edge_ring()` legt zehn Vertices (außen/innen abwechselnd) um das Quad, Breite 1,5/E je Achse (E = Maskenzahl der
Firma), ein Triangle-Strip je Ebene, `SRC_ALPHA`/`ONE_MINUS_SRC_ALPHA` gegen Video-Schwarz der Ebene; innen ist keep exakt 1,
darum darf der Ring dort enden. Host-Test T1d: Kantenrampe ±1 LSB gegen die CPU-Referenz, Kante aus byteexakt. Am Gerät
`ctl check 300` mit Film: 0 abweichende Zeilen. Folge: der GPU-Regler parkt bei 288-432 MHz (vorher 600-696).

## 3 Der CPU-Regler: RT-Boost durch die GPU-Interrupt-Threads

`/proc/sys/kernel/sched_util_clamp_min_rt_default` fehlt (kein `CONFIG_UCLAMP_TASK`) → schedutil fordert bei runnable RT-Task den
Maximaltakt. `irq/329-panfrost-job` (FIFO 50) läuft 4× je Bild (239 IRQs/s). Messreihe (m30/m31, Warp an, 1080p60, 20 s):

| IRQ-Threads | rate_limit | Zeit bei 1296 | Wechsel/s | sugov:0 | alle Kerne | fps |
|---|---|---|---|---|---|---|
| FIFO 50 | 462 µs | 13 % | 14 | 18,0 % | 10,7 % | 59,8 |
| FIFO 50 | 20 ms | 43 % | 40 | 2,5 % | 4,2 % | 59,7 |
| **SCHED_OTHER** | 20 ms | 2 % | 1,6 | 0,1 % | 4,6 % | 59,7 |
| **SCHED_OTHER** | 462 µs | 0 % | 0,3 | 0,1 % | 4,4 % | 59,7 |

Die "% aller Kerne" bleiben gleich - aber bei 480 MHz statt zur Hälfte bei 1296 (Energie, Wärme). Das tmpfiles-`w` für die 20 ms
lief vor dem Erscheinen des schedutil-Verzeichnisses (drei Boots mit 462 µs) → `userspace/h713-cpufreq/` (Skript + Unit, wartet auf
beides). Kernel-Weg als TODO 2.60.

## 4 Latenz: `hold off`

Mit 0255 übergibt afbd im Vsync den im letzten Bildgrenzpunkt fertigen Slot; der Schreiber kommt nach 33 ms zurück. `hold on`
(eine Vsync warten) las ihn bis zu 36 ms + GPU-Zeit nach der Grenze → riskant; `hold off` liest ≤ 20 ms + GPU-Zeit danach.
Selbsttest 300 Bilder mit Film, `hold off`: 0 Zeilen abweichend; Zweitzeichnung jetzt 4 ms nach der ersten (12 ms liefen in den
nächsten Schreibvorgang, Zeilen 0..34).

## 5 Die "Hänger" - was es nicht war, und wie man es misst

Marco sah mit dem ThinkPad als Quelle alle ~11 s einen Hänger (ein Bild bleibt 330 ms, dann Aufholen). Gemessen am Ring
(`kette.py`: CRC32 der ganzen Luma-Ebene des fertigen Slots je Quellbild): Läufe von 19-21 gleichen Bildern, streng alle 11,0 s -
**mit und ohne Warp, mit Original-afbd und mit 0255, mit altem und neuem h713-tv, mit allen Bildverbesserern aus**; der
Schreibindex stand dabei nie (`stall-trace.py`), die Pixel kamen 20× gleich an. Mit der Gamma-Umschaltung als Quelle keine
Läufe; glxgears zählte 300-302 Bilder je 5 s - der Laptop legte also hinter dem Bildaufbau identische Bilder auf HDMI (dort lief
`rustdesk --server`, ein Bildschirmgreifer; nicht weiter verfolgt). **Fire-TV-Stick als Quelle: keine Stillstände**, Bypass 59,8/s
gezeigt, Warp 59,7 fps, 0 Verwürfe. Lehre: erst die Quelle am Ringinhalt messen (`kette.py`), nicht am Zeiger.

## 6 Gerätestand G-EU, offen

afbd 0255 (`10806bf3`), `h713-tv` d6134496 + `edid_prefer = file` in `tv.conf`, `h713-warp` Ring-Edge (`e65b25d5`, hold off),
`h713-cpufreq` installiert und aktiv, Mess-Keystone `tl x 50`. Offen: 2.60 (UCLAMP), 2.61 (ein Batch), HY310 mit 0255 und
diesem Warp nachmessen (Marco), Panel-Pixeltakt 2.59.

## 7 Handoff (11.10.2026, ~20:00 UTC)

**In `main` (nicht gepusht):** `dd3ed00` (Kernel-Patch 0255: Ringplatz aus `INCAP +0xa0c`, `doku/200`) und `48305cb` (dieses
Paket). Beide Zweige (`versuch/viddec-bildrate`, `versuch/warp-zeichnen`) sind integriert, Worktrees entfernt, Zweige lokal.
Push nur mit Marcos Ja; Reihenfolge `TODO.md` §1.

**G-EU installiert und gemessen:** afbd `10806bf3` (0255, `ring_select=1`), `h713-tv` `fd90d1ef` (= main, `edid_prefer = file`
Vorgabe; `/etc/h713/tv.conf` nennt es zusätzlich), `h713-warp` `e65b25d5` (= main: Ring-Edge, `hold off`, `ctl trace`),
`h713-cpufreq` installiert und aktiv, `warp.conf` wieder Original (Keystone 0 → Bypass). Sicherungen: `/root/sicherung-viddec-bildrate/`
(afbd Original `764ca830`, h713-tv `9212dcd6`/`d6134496`, TSE, EDID-Datei, display_cfg), `/root/sicherung-warp-zeichnen/`
(h713-warp `15f5f062`, warp.conf, Regler- und Bildverbesserer-Stände). Rückwege: `sh /root/tausch-afbd.sh zurueck`;
`mv /root/sicherung-warp-zeichnen/h713-warp.orig /usr/local/bin/h713-warp && systemctl restart h713-warp`. Bildverbesserer
zurück auf Vorgabe (black_extension Low, TNR Middle, DCI Middle, SNR Low).

**Quelle am HDMI:** Fire-TV-Stick (1080p60). Der ThinkPad (`rustdesk --server`) lieferte alle 11 s 330 ms identische Bilder -
als Testquelle nur mit `kette.py` daneben.

**Marco hat abgenommen:** 0255 (Bild sauber), Warp/Regler ("das passt").

**Offen (TODO):** 2.59 Panel-Pixeltakt (Rest 0,3 Sprünge/s), 2.60 `CONFIG_UCLAMP_TASK` statt chrt, 2.61 ein Batch je Bild (Warp-CPU),
HY310 mit 0255 und diesem Warp nachmessen (`anzeige.py`, `ctl trace 30 gpu`, `messe-warp.py`). Release: `TODO.md` §1.

**Gelernt (für `referenz/` eingetragen):** GPU-Zeit nur über die Out-Fence; keine Rechnung hinter dem Texturabruf auf der G31;
RT-Tasks treiben schedutil; tmpfiles trifft cpufreq-Sysfs nicht; Hänger am Ringinhalt (`kette.py`) und mit Quellenwechsel
nachweisen, nicht am Zeiger und nicht am Player-Zähler; Marco glauben, wenn er sagt "es ist nicht die Quelle" - und trotzdem messen.
