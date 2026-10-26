# 220 Der L018 als eigenes Board bis nach main, der Autofokus über offenen Seiten und die Validierung auf drei Geräten - Protokoll

Datum: 24.-26.10.2026. Geräte: L018 (Marcos eigener, Stock Android 11 vom 14.05.2025), dazu HY310 und HY300PRO-G-EU für die
Validierung vor dem Push. Marco an Gerät, Wand, Fernbedienung und Ohr, die Sitzung am PC. Pakete und Belege (lokal):
`arbeit/l018-stock-20261024/` (Stock-Abgleich), `arbeit/l018-board-20261024/` (`BERICHT.md`, `runde2/`, `runde3/`,
`VALIDIERUNG.md`), `arbeit/autofocus-launcher-20261025/` (TODO 4.9h). TODO 4.0, 4.7-4.9h.

## 1 Ausgang

Der L018 ist ein Zwilling des HY310: dieselben DRAM-Wörter, dasselbe Panel (Projekt `0x30`), dieselbe Display-Firmware. Er
unterscheidet sich im Stock-Gerätebaum und im Pin-Zustand unter Stock (am laufenden Gerät gelesen, 24.10.): Neigungssensor
LSM6DSV an twi2 (PH4/PH5) statt SC7A20 an twi1, Fokusmotor an PF0..PF3 mit Endschalter PB1, Lüfter-Tacho PH13, Lüfter-PWM0
auf PH17, die **Lampe** auf PWM2/PB4 (dimmt mit steigendem Tastgrad), ein NTC an GPADC-Kanal 1 (der HY310 hat keinen), zwei
LEDs an der Power-Taste (PL0, PL1). Am 24.10. lief das Testabbild `h713-l018-v0.97-test2-TEST` (Bild gespiegelt, Lampe und
Lüfter im Gate an); daraus wurde ein eigenes Board.

## 2 Was am L018 gebaut und gemessen ist

| Teil | gemessen | Stand in main |
|---|---|---|
| U-Boot `0103` | Gate dunkel und leise, Bild richtig herum (PH9 low vor dem Panel-Reset), Start in der Stock-Stufe std (Lampe PWM2 50 %, Lüfter PWM0 70 %, 3240 U/min). HY310 ohne die Option: `board.o`/`h713_mips.o` byte-gleich | Fork `h713-hy310` `b0795ef3079` |
| U-Boot `0104` | Lampe und Lüfter ab Strom bis zum Start dunkel, kein Weiß mehr vor dem Logo (Marco) | `d54ab262cc3` |
| U-Boot `0105` | Taste im Gate rot, nach dem Start blau (PL0 rot, PL1 blau, beide aktiv-low; Marco) | `c97e5c6bb78` |
| Kernel `0331` (Baum) | NTC mit der Stock-Tabelle (38 Paare, 0..55 °C): 21,2-21,6 °C über 22 min bei Raumtemperatur, Umrechnung nachgerechnet; LEDs als `red:power`/`blue:power` (Betrieb: blau 1, rot 0) | `0331` |
| Kernel `0332` (Lampe) | Lampe und Lüfter mit einem Modusindex: std 50/70 %, low 75/60 %, high 30/95 % - die Register, die die Stock-Firmware am 24.10. schrieb; Lüfter folgt (3210/2880 U/min); Helligkeit der drei Stufen von Marco bestätigt; der Wärmemodus (ab 41 °C) **nicht gemessen** | `0332`, `userspace/h713-lamp` |
| Kernel `0333` | Abschaltung bei 51 °C per Gerätebaum-Eigenschaft `thermal-shutdown`, im L018-Baum gesetzt (ohne Thermometer: Stock-Tabelle und -Umrechnung, Marco hat keins); Eigenschaft am Gerät gelesen, **das Abschalten selbst nicht gemessen** | `0333`, `0331` |
| Lüfter-Notabschaltung (TODO 4.0) | PWM0 auf 0 %: Urteil nach 8 Takten, geordnet aus in 6,2 s, Gate. Am 25.10. ~23:50 im Betrieb ausgelöst: Marcos Lüfter fällt zeitweise aus (Defekt dieser Unit), das Gerät schaltete ab (Marcos Beobachtung; das Journal des L018 ist flüchtig) | - |
| Kernel `0334` (Sensor) | der LSM6DSV antwortet `WHO_AM_I` 0x71 (Mainline kennt 0x70; der Stock-Kernel prüft genau 0x71); danach `lsm6dsv_accel`, in Ruhe 1 g | `0334` |
| Kamera | „HYSD-VAF02-ZH04" (UVC); die Werkzeuge kannten nur „HD camera" -> gemeinsame Namensliste | `h713-features`, `-cam`, `-autofocus` |
| Fokus | der Endschalter PB1 liest an beiden Anschlägen 0, kein anderer Pin und kein ADC-Kanal ändert sich: tot auf Marcos Unit („liegt an meiner Unit"). Experimentell nur dort: gezählter Bereich -35..35 in `/etc/h713/focus.conf`, `h713-focus home`; das Abbild des L018 macht keine Referenzfahrt (`FOCUS_HOMING=0`, „bis jemand mit einem L018 kommt") | `h713-focus`, `boards/l018/board.env` |
| Fokus-Taste | 20 msteps je Druck waren „viel zu grob" (der ganze Weg ~110 msteps); 13: „passt so" (Marco) | `FOCUS_STEPS=13` |
| Keystone | (1) Der LSM6DSV zählt 16393 je g; nach dem Faktor 16 des Herstellers liefen die int32-Quadrate über, `once` sagte pitch NaN -> Teiler 16 (beim SC7A20 1, HY310 bitgleich). (2) Achsen in Marcos Halterung gemessen: pitch +z, roll +y, vertikal -x; der Bügel kippt nur um sein Scharnier. (3) Mit der HY310-Optik war das Bild von vorn oben zu schmal; mit dem Projektionsverhältnis der eigenen `camprjspe.ini` (1,1501 statt 0,8176): „sieht sehr gut aus" bei 18,6°, bei 29,9° „minimal off" (Marco) | `h713-keystone`, `KEYSTONE=` |
| Bluetooth-Fernbedienung | gekoppelt (Links+Rechts), Lauter/Leiser, Home, Pfeile, OK, Zurück, Fokus bis an beide Enden | - |
| HDMI | ThinkPad 1080p60 an der Wand mit Keystone, 59,4 Bilder/s; HDMI-Ton (440 Hz) aus dem Lautsprecher (Marco) | - |
| HDCP 1.4 | Paar nach Messregel: Start mit `h713_hdcp14_wipe=1` -> ThinkPad bleibt „Desired"; normaler Start -> „Enabled". HDCP 2.2 **nicht gemessen** (der ThinkPad kann nur 1.4) | - |
| Video in Hardware | `vainfo` (v4l2-request): H.264, HEVC, VP8, VP9, MPEG-2; 1080p30 H.264: ein VE-Interrupt je Bild; Kodi spielt flüssig mit Ton (Marco) | - |
| Lautstärke | Hörtest: acht Stufen im DSP bis 0 dB (Akkord, Rauschen, 100 Hz), 0 dB = Stock-Maximum „vollkommen ok, klingt nicht mal wie das Lauteste". Seitdem nimmt der L018 seine eigene Stock-Kurve aus `audio_config.ini` (50 = -12,5 dB, 100 = 0 dB statt -22/-9,5); nachgehört 50/100: „gut" | `h713-tv volume_curve`, Installer, `VOLUME_CURVE=vendor` |
| Kopfhörer | Buchse vorhanden, **nicht getestet** (keine Kopfhörer da) | - |

Gemessen wurde auch, was **nicht** geht: Die Kamera des Geräts sitzt am Objektiv und sieht jedes Bild rechteckig, auch ein
schräg projiziertes - die Trapezform ist nur von vorn zu beurteilen (Marco an der Wand), nicht mit der eigenen Kamera.

## 3 Der Autofokus über offenen Seiten (TODO 4.9h)

Befund am L018: Der Autofokus zeichnet sein Schachbrett in die Konsole; eine deckende Seite (Launcher, Einstellungen,
„No signal") bleibt bei `h713-tv ctl off` absichtlich stehen und deckt es zu -> „no picture". Gebaut in eigener Sitzung:
`h713-tv ctl bare SECONDS` hält für die Laufzeit alles Eigene von der Wand, der Autofokus fordert es an und gibt es zurück.

| Gerät, Fall | alter Stand | neuer Stand (Bildpegel, Untergrenze 3227) |
|---|---|---|
| L018, kein HDMI, Launcher offen | Ende 3 „no picture", Pegel 706 | Ende 0, 29586; Launcher danach wieder da |
| L018, Einstellungsseite / „No signal" / keine Seite | - | 34790 / 34695 / 34751 |
| L018, HDMI-Bild (Warp an) und Launcher | - | 33772; Warp und Launcher danach wieder da |
| HY310, HDMI-Bild und Launcher | Ende 3, Pegel 11 | Ende 0, 14968; Launcher danach wieder da |

**Nicht gemessen:** der Start über die eigene Zeile der Einstellungsseite, ein Tastendruck während eines Laufs.

## 4 Validierung vor dem Push (26.10.)

Integrationsstand = `main` + der L018-Zweig + der Autofokus-Zweig. Offline: Tore mit 473 Installer-Tests, h713-tv 9/9 (dabei
`test_bare`, `test_curve`), Keystone 230, Autofokus 51 grün; für andere Boards ändern sich nur der Board-Manager-Code
(`0332`/`0333`), eine Kennung im Sensortreiber (`0334`) und zwei Module im gemeinsamen Defconfig - ihre Gerätebäume nicht.

| Gerät | Ergebnis |
|---|---|
| L018 | Programme byte-gleich zum Integrationsstand, Neustart sauber, Kurzdurchgang (Taste, Lampe, Keystone, Lautstärke, Fokus, Autofokus) |
| HY310 (von v0.97) | Kernel + Module + Programme: Board-Manager-Start Zeile für Zeile wie vorher (keine Lampe), Lautstärke 100 = -9,5 dB (eingebaute Kurve), Keystone-Winkel wie vorher, Autofokus §3, Hardware-Video 300/300 |
| HY300PRO-G-EU (von v0.97) | dasselbe ohne Kamera und Fokus: Board-Manager wie vorher, Lautstärke 80 = -14,5 dB, Keystone wie vorher, Einstellungsseite, Video 300/300 |

Danach mit Marcos Ja: U-Boot-Fork `h713-hy310` `daa35622..c97e5c6b`, dann `main` bis `c94be434`.

**Pannen** (alle in `VALIDIERUNG.md`): (1) Beim ersten Kernel-Einspielen am HY310 fehlte die Modulquelle (der reine
Kernel-Bau legt kein `modroot` an); `kernel/` war schon gelöscht - sofort aus der Sicherung zurück, kein Neustart dazwischen,
danach mit Prüfung vor dem Tausch. (2) Am G-EU startete ein „4× runter, OK" der virtuellen Fernbedienung die Mediathek statt
der Einstellungen (sein Launcher hat einen Eintrag mehr) - sofort beendet. (3) Ein `;` statt `&&` ließ nach einem gescheiterten
Vorspulen den lokalen `main` pushen: 9 reine TODO-Commits (3 aus anderen Sitzungen), danach geprüft leakfrei; nicht
zurückgeholt.

## 5 Offen

Kopfhörer, HDCP 2.2 (Fire-TV-Stick), Wärmemodus und 51-°C-Abschaltung (bleiben ungemessen, Marco), Testabbild mit Profilen
und Abnahme („deutlich später"), Lüfter-Notabschaltung an HY310 und G-EU (nur mit abgesteckten Lüftern). Der mkimage-
Selbsttest wird erst mit dem nächsten Abbild-Bau grün (er vergleicht das zuletzt gebaute Abbild mit 44 Dateien).
