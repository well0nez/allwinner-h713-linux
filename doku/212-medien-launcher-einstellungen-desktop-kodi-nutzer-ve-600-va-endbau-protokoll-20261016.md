# 212 - Das Nebenprojekt Medien, zweiter Teil: Launcher, Einstellungsseite, Desktop und Browser, Kodi als Nutzer, die VE mit 600 MHz, der VA-Treiber `0015` bis `0017`, der Endbau (15. und 16.10.2026)

**Kurz:** Fortsetzung von `doku/211`. Der Eintrag fasst die Messungen zusammen, die nach dem Stand von `doku/211` dazukamen, und
ist der Beleg, auf den `docs/` für diese Aussagen zeigt. Die Rohlogs liegen im lokalen Arbeitsordner des Nebenprojekts und sind nicht
veröffentlicht. **Gemessen wurde nur am HY310** (Kernel 6.18.38, Zweig `medien`); der HY300PRO-G-EU ist in keinem Punkt
nachgemessen, jede Gruppe unten hat dafür eine Zeile in `TODO.md`. Was nicht gemessen wurde, steht in §8.

**Berichtigung zu `doku/211` §3 und §8 (16.10.2026):** der VE-Takt von 432 MHz (Patch `0293`) war nur für den AV1-Kern gesenkt und gilt
seit `0315` nur noch, solange dieser Kern eingeschaltet ist (§5). Die "28,4 bis 28,8 Bilder/s" der VE bei 4K-HEVC in Kodi (`doku/211` §8) sind
großenteils ein Artefakt des 10-Sekunden-Testclips in der Schleife (§5); H.264 2160p war dagegen VE-gebunden.

## 1 Launcher, Moduswechsel und Standby aus jedem Weg (15.10.)

Der Launcher ist eine deckende Seite über dem ganzen Panel (innerhalb eines 5-%-Randes, die Schrift Quicksand); `KEY_HOMEPAGE` öffnet sie,
Kodi bekommt bei offener Seite keine Taste, die Einträge sind Dateien in `/etc/h713/launcher.d/`. Jeder Weg in den Schlaf endet mit Bild und Modus
(`h713-sleep-pre`/`-post`, `h713-mode`).

| Prüfung | Ergebnis |
|---|---|
| HDMI -> Kodi -> HDMI, zehn Mal | HDMI -> Kodi (bis Oberfläche und JSON-RPC stehen) **4,16 bis 4,24 s** (Mittel 4,20), Kodi -> HDMI **0,39 bis 0,44 s** (Mittel 0,42); 60 bis 62 präsentierte Kodi-Bilder in den 2 s danach; `h713-tv` und `h713-warp` in allen zehn Zyklen dieselben Prozesse |
| Taste mal Zustand (vier Zustände, 14 Tasten) | bei offenem Launcher bekommt Kodi in 0 Fällen eine Taste. Zwei Funde, behoben und nachgemessen: Home blieb hängen (das Greifen der Geräte kam vor dem Loslassen), und OK/Menu erreichten Kodi nie (eine udev-Regel legt sie unter Code 248; Kodi bekommt jetzt `return -> Select` und `menu -> ContextMenu`) |
| Taste bis sichtbare Änderung | Auswahl wechseln: über HDMI **52,7 ms** Mittel (max. 85,0), über Kodi **81,8 ms** (max. 109,6), bis `osd show` beantwortet; der Flip kommt höchstens 16,8 ms danach und ist nicht mitgemessen. Das Öffnen der Seite: 230 bis 302 ms im Daemon |
| Standby aus jedem Weg, je fünf Zyklen | **35 von 35**: HDMI (Powertaste, Launcher-Eintrag, `systemctl suspend`) Ring nach **7,5 bis 11,2 s**; Kodi (dieselben drei und Kodis eigenes `System.Suspend`) Kodi wieder da nach **9,9 bis 15,3 s**; `suspend_stats` 35 erfolgreich, 0 fehlgeschlagen; `0314` im Kernel, in keinem Zyklus fehlten Bilder |

## 2 Die Einstellungsseite (15. und 16.10.)

Die Seite (`h713-settings`) liegt als Launcher-Eintrag über dem Panel; jede Zeile ist ein vorhandener Befehl oder ein `key = value` einer Datei in `/etc/h713`.

| Prüfung | Ergebnis |
|---|---|
| Jede Einstellung einmal gesetzt und zurück | bestanden: Helligkeit, Kontrast, Farbe, Farbton, Schärfe je 50 -> 55 -> 50; Bildmodus, Seitenverhältnis, Rücksetzen; jeweils im Werkzeug oder in der Datei gelesen |
| Warmstart | 14 von 15 Feldern vorher und nachher gleich (u. a. Helligkeit, Kontrast, Bildmodus, Seitenverhältnis, Quelle, Lautstärke 75, Zoom, Projektion, Ecken); **Stumm bleibt nicht**: die Box ist nach dem Start hörbar, die Lautstärke bleibt (Entscheidung, nicht über den Boot zu halten) |
| Taste bis sichtbare Änderung (30 Tasten: 12 Bereichswechsel, 1 Eintritt, 8 Zeilen, 9 Reglerschritte) | Gate Mittel unter 120 ms. Erster Lauf (15.10.) **190,8 ms**. Nach dem Umbau des Vorverzerrens (ganze Seite 37 ms statt 169 bis 199 ms): mit dem Keystone der Box **66,2 ms** (Median 37,0, max. 366), mit zurückgesetztem Keystone 52,5 ms, mit einem Thread 104,6 ms |
| Keine Doppelwirkung | zwei Zustände (HDMI darunter, Kodi darunter) mal 13 Tasten bei offener Seite = 26 Zellen: Kodi bekam in 0 Zellen eine Taste |
| HDMI ohne offene Seite unverändert | `h713-warp ctl check 300`: 300 Bilder, 0 mit abweichenden Zeilen, nach dem Warmstart und nach dem ganzen Seitenbetrieb |

Die Raten wurden dabei nicht eigens verglichen. Nicht gefahren: Power bei offener Seite über Kodi (nur über HDMI); die Schärfe nach "Autofocus now" an der Wand.

## 3 Desktop und Browser als Modi (15.10.)

`labwc` mit foot (Desktop) und Firefox ESR 153.5 in einem eigenen labwc (Browser), je als eigener Systemnutzer (`h713-desktop`), als Clients des Warp-Servers.

| Prüfung | Ergebnis |
|---|---|
| Wechsel von HDMI zum Desktop bzw. zum Browser und zurück, je zehn Mal | erstes Client-Bild nach **1,0 bis 1,2 s** bzw. 1,0 bis 1,1 s, Ring zurück nach **2,5 bis 2,7 s**, `h713-warp` und `h713-tv` unverändert (gleiche PIDs), keine Treiberereignisse |
| mpv 1080p60 im Desktop, rund 5 min (`--hwdec=vaapi`) | 60,0 Bilder/s dekodiert, 3 verworfen, 0 vom Dekoder, MemAvailable 559 bis 590 MiB von 924 |
| Firefox, 1080p60-Clip lokal, 40 s, Vorgabe (Sandbox des Dekoder-Prozesses an) | `Failed to create VA-API device context`, **Software**: 47,1 Bilder/s dekodiert, VE 0/s, 1884 von 2103 Bildern nicht gezeichnet |
| dasselbe mit `MOZ_DISABLE_RDD_SANDBOX=1` | `VA-API FFmpeg init successful`, 60,0 Bilder/s, VE 60 Interrupts/s, **883 von 2748 (32 %) nicht gezeichnet**; mit cage statt labwc 887 von 2765: die Grenze ist Firefox' Zeichnen von 1080p60 auf dieser GPU, nicht das zweite Compositing |
| 720p30 | 30,04 Bilder/s, 22 von 555 nicht gezeichnet (mit dem Schalter) |
| Speicher mit einem Video-Tab | Firefox-Prozesse zusammen **970 MiB** RSS (gemeinsame Seiten mehrfach gezählt), MemAvailable 354 MiB (labwc) bzw. 329 (cage) von 924 |
| `about:support` | WebRender auf Wayland, Inhalts-Sandbox Stufe 6 auf Seccomp, `hasUserNamespaces` **false** (der Kernel hat keine User-Namespaces) |
| Standby je drei Zyklen | Browser 3 von 3; Desktop 3 von 4 (ein Zyklus scheiterte am Test: das Messskript rief `h713-mips-restart` zugleich mit dem Hook des Systems auf, beide starteten h713-tv und h713-warp neu) |

Die Entscheidung: `MOZ_DISABLE_RDD_SANDBOX` ist **nicht** die Vorgabe (Firefox lädt Webinhalte; der Dekoder-Prozess liefe ohne Sandbox), die Zeile steht auskommentiert in der Einheit. Firefox 153 hat kein Pref, das der Sandbox des Dekoder-Prozesses die Gerätedateien öffnet (nur Umgebungsvariablen: alles oder nichts); `media.rdd-process.enabled = false` mit Whitelists wäre eine ungeprüfte Hypothese.

## 4 Kodi als eigener Nutzer, `source = auto`, polkit (16.10.)

| Prüfung | Ergebnis |
|---|---|
| Rechte | cage, `kodi-standalone`, `kodi`, `kodi.bin` alle uid/gid 988 (`h713-kodi`), Gruppen audio, video, render, `NoNewPrivs 1`, **kein root-Prozess**; `/var/lib/h713-kodi` gehört dem Nutzer (0 von 58 Dateien fremd); als Nutzer: `/dev/mmcblk0`, `wifi.env`, Schreiben nach `/etc/h713`, Lesen des Hostschlüssels - alles verweigert |
| HDMI -> Kodi -> HDMI | Kodi bis JSON-RPC 3,84 bis 4,08 s (erster Start 4,28 und 4,53 s), zurück 0,35 s |
| Dekodieren als Nutzer | H.264 und HEVC 8 Bit 1080p je 20 s gemessen: `ff-*-vaapi`, VE 30 Interrupts/s, 59 Client-Bilder/s, 0 Treiberereignisse; MPEG-2 nicht gemessen (kein Clip auf der Box) |
| Neustart von h713-tv mit laufendem Kodi | mit `source = auto` in der Konfiguration des Abbilds: Kodi nach **1,7, 2,0 und 1,9 s** wieder präsentiert; ohne die Zeile (das Verhalten vorher): Quelle `hdmi`, Kodi-Einheit `active`, aber nichts präsentiert |
| Kodi starten, solange h713-tv steht | die Einheit startet, Kodi ist 1,6 s nach dem Start von h713-tv sichtbar (der alte Befehl `h713-tv ctl source auto` hätte die Einheit scheitern lassen) |
| Standby mit Kodi als Nutzer | zwei Zyklen (`systemctl suspend`, Launcher-Eintrag): Kodi vor dem Schlaf beendet, danach wieder da (58,7 und 59,4 s nach dem Auslöser mit 45-s-Wecker), 0 Zyklen ohne Bilder |
| Kodis eigenes Power-Menü | als Nutzer hatte Kodi zunächst keinen Suspend- und Shutdown-Eintrag mehr (logind verlangt eine Berechtigung). `polkitd` (5 Pakete) und eine enge Regel in `/etc/polkit-1/rules.d/50-h713-kodi.rules`: `CanSuspend`, `CanPowerOff`, `CanReboot` = yes für `h713-kodi` (`CanHalt` challenge, `CanHibernate` no), für `nobody` `CanSuspend` challenge; Kodi meldet `System.CanSuspend`, `CanPowerDown`, `CanReboot` true; ein `System.Suspend` per JSON-RPC mit RTC-Wecker schlief, danach Kodi und Bild zurück (60 Bilder in 2 s). `PowerOff` und `Reboot` selbst nicht ausgelöst |
| `MemoryDenyWriteExecute=yes` | trägt für cage, Kodi und VA-Dekodieren; Python lief nicht (kein Skript- oder Dienst-Add-on aktiv), darum nicht in die Einheit übernommen |

**Gemessener Fehler, offen:** ein `SIGKILL` von h713-tv lässt die Einheit scheitern; `OnFailure=` lädt die Display-MIPS neu und startet h713-warp, `BindsTo=` beendet dabei `h713-kodi.service`. Das HDMI-Bild ist nach etwa 16 s wieder da, Kodi bleibt aus und der Modus wird nicht gemerkt (`systemctl restart h713-tv@N` ist davon nicht betroffen: Kodi bleibt). **Kodi schreibt `guisettings.xml` beim Beenden neu**, mit dem Vorgabewert des Augenblicks für `powermanagement.shutdownstate` (ohne `CanSuspend` fiel er auf 0), das ist Kodis Eigenverhalten.

## 5 Die VE mit 600 MHz (Patch `0315`) und die Funde der Kernel-Prüfung (15./16.10.)

`0315`: cedrus wählt 432 MHz nur, wenn ein aktiver Knoten `allwinner,sun50i-h713-av1` im Device Tree steht, sonst die 600 MHz der H6-Variante (eine Zeile `module clock … Hz` beim Probe). Die CCU zeigt unter Last `PLL_VE 0xb8002301` (432 MHz) vorher und `0xb8001800` (600 MHz) nachher. Dazu `0316` (ein `collocated_ref_idx` außerhalb der aktiven Liste wird vor dem ersten Registerzugriff mit `-EINVAL` abgelehnt), `0317` (`cedrus_vp9_finish` hält 15 Byte statt 2 KiB auf dem Stapel), `0318` (der Knoten `av1-decoder@1c0d000` aus `0024`, den kein Treiber bindet, fällt weg), `0319` (der überholte Kommentar "no IOMMU").

| Messung | 432 MHz | 600 MHz |
|---|---|---|
| mpv H.264 2160p30, VE-Bilder/s über 40 s | 26,64 | **30,02** |
| Dekodieren allein (GStreamer, fakevideosink), H.264 2160p | 24,3 | **28,6** |
| dasselbe HEVC 8 Bit / 10 Bit 2160p | 49,0 / 43,3 | 55,4 / 49,2 |
| Kodi H.264 2160p30 (10-s-Clip in Schleife), VE-Bilder/s über 60 s | 24,75 | **27,61** |
| Kodi HEVC 2160p30 (10-s-Clip in Schleife), VE-Bilder/s über 60 s | 28,63 | 28,61 |

H.264 2160p ist VE-gebunden; **HEVC 2160p in Kodi ist es nicht** (gleiche Rate bei beiden Takten, die Rate wechselt je 5-s-Fenster zwischen 30 und etwa 27, weil der kurze Clip in der Schleife neu startet). Gates mit dem 600-MHz-Kernel (der die Patches `0315` bis `0319` trägt): bitgenau 33 von 33 Clips mit Interrupts gleich Bildern, 0 Treiberzeilen; Dauerlauf 55 min mit 112 von 112 Clip-Läufen exakt; drei Ströme gleichzeitig exakt, Paare 19 von 20 (das bekannte Paar VP8 plus VP9: 596 von 600 Bildern, ein Timeout ohne Fault, wie bei 432 MHz), das Paar allein 20 von 20; keine IOMMU-Fault-Zeile. **Eine Stunde Kodi HEVC 2160p30:** VE **29,75 Bilder/s** (107 107 Bilder in 3600 s, kein 30-s-Fenster unter 29), **0 Timeouts, 0 IOMMU-Faults, 0 mmc-Fehler**, Zonen höchstens 68,4 C (CPU) und 70,6 C (GPU), MemAvailable mindestens 204 MiB; 15 min Kodi H.264 2160p30: 28,85 Bilder/s, 0 Ereignisse.

## 6 Der VA-Treiber `0015` bis `0017` (15.10.)

| Patch | Fehler | Prüfung |
|---|---|---|
| `0015` | ein Rennen: `vaDestroyContext` gab den Kontext frei, während ein anderer Thread `vaSyncSurface`, `vaQuerySurfaceStatus` oder `vaDestroySurfaces` mit einer Oberfläche aufrief, die noch darauf zeigte | Host-Test mit den echten Treiberquellen und einem Attrappen-Kontext, das Rennen per Link-Wrapper erzwungen, ASan: **vorher 4 von 4 heap-use-after-free, nachher 4 von 4 bestanden**. Das Rennen selbst am Gerät nicht (Fenster von Nanosekunden bis Millisekunden) |
| `0016` | Entry-Points fehlten: bei HEVC mit Kacheln und mehreren Kacheln je Slice bekam cedrus nur die erste | Parser-Test gegen FFmpegs `trace_headers`: 780 Slices, 330 mit Entry-Points, alle Offsets gleich. Kachelströme mit einer Kachel je Slice am Gerät vorher und nachher 119 von 119 bitgenau; mehrere Kacheln je Slice nicht (kein Kodierer) |
| `0017` | VP8: die Quantisierer-Deltas wurden aus einem schon geklemmten Segment 0 zurückgerechnet | Host-Test gegen die Rechnung von libvpx über 200 001 Rahmen: **vorher 356 414 falsche Indizes, nachher 0**; VP8-Clips am Gerät bitgenau, der Randfall selbst nicht |

Am HY310 mit dem neuen Treiber: die ganze Matrix über VA **34 von 34 bitgenau** (Interrupts gleich Bildern, 0 Zeilen im `dmesg`); Codec-Wechsel (hevc8, vp9, hevc8, h264, vp8, hevc8, mpeg2, vp9) 8 von 8; ein Auflösungswechsel (`h264-reswitch.ts`) alt und neu je 300 von 300 zweimal; mpv und Kodi mit HEVC 8 Bit 1080p und 2160p über VA je 30 s: mpv 30,0 Bilder/s ohne Verlust, Kodi `ff-hevc-vaapi` mit VE 29/s bzw. 28/s; in der ganzen Reihe 0 Treiberereignisse. Ein Vorher-Wert für Kodi 4K mit dem alten Treiber liegt nicht vor.

## 7 Der Endbau des Medienabbilds (16.10.)

`release/build-all.sh --board hy310 --profile media,desktop --standby` baut das Abbild in einem Lauf (mit Namensprüfung des Profils und `--standby`): Exit 0 nach **20 min 04 s** (elf Schritte, HDCP- und crust-Tor, `h713-mkimage check`), Rootfs-Tar 1 163 089 920 Byte, 619 Pakete, Baum **1152 MiB**. Der erste Lauf scheiterte: der Baum war von 896 MiB (vor Firefox, labwc, foot und polkit) auf 1152 MiB gewachsen, `mke2fs` fand im festen 1-GiB-Eingang keinen Platz. Ein Profilabbild bekommt seitdem ein 2-GiB-Rootfs (`ROOTFS_EXT4_SIZE=2G`, wächst beim ersten Start auf die ganze Partition), das Grundabbild bleibt bei 1 GiB. Das ist der Aufruf, den ein Fremder für das Medienabbild braucht (`BUILDING.md`). Zur Größe: das Profil `media` allein kostete im Baum +446 MiB (Host-`du` 284,8 auf 730,9 MiB, davon `plugins-bad` +197,8 MiB); die +272 MiB von `doku/211` §7 waren der Stand vor `plugins-bad`.

## 8 Nicht gemessen

* Alles am HY300PRO-G-EU: Launcher, Seite, Desktop, Browser, Kodi als Nutzer, `0315` bis `0319`, `0015` bis `0017`.
* Die echte Infrarot- und Bluetooth-Fernbedienung an Launcher und Kodi (die Läufe nutzten ein uhid-Gerät mit der Kennung der Fernbedienung); der Flip des Launchers an der Wand; ein Weckabbruch mit `pm_test` für das Netz in `h713-power`.
* Firefox mit 30 Bildern/s in Software; die Wirkung der Masken der PipeWire-Benutzereinheiten für einen zweiten Benutzer mit Sitzung; `PowerOff` und `Reboot` aus Kodi.
* Die Ursache der 32 % nicht gezeichneter Bilder in Firefox; die Ursache dessen, was Kodi bei 4K noch überspringt (GPU zu 92 % belegt, nicht VE-gebunden).
* Ein Abbildstart des Endbaus; das Kachel-Verhalten von `0016` bei mehreren Kacheln je Slice; der Randfall von `0017`.
