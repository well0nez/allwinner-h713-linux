# 221 Die Nachtpakete vom 25./26.10.: zusammengeführt, am HY300PRO-G-EU gemessen und nach main - Protokoll

Datum: 25.10.2026 abends bis 26.10.2026 mittags. Gerät: HY300PRO-G-EU (v0.97-beta vorgefunden), dazu der ThinkPad als
HDMI-Quelle. Marco an Box, Kabel, Fernbedienung und Auge, die Sitzung am PC. Plan und Belege (lokal):
`arbeit/nacht-20261026/` (`PLAN.md`, `logs/`, `install-geu/`, `abnahme/`), die Pakete `arbeit/builder-20261024/`,
`arbeit/libva-repro-20261026/`, `arbeit/installer-nutzerstand-20261025/`, `arbeit/tv-rettung-20261026/`,
`arbeit/kleinkram-20261025/`, `arbeit/fb-mikro-20261026/`, `arbeit/rgb-ebene-20261025/`.
TODO 1.2a, 1.2b, 1.10 g), 2.34, 2.51, 2.108, 2.113, 2.125, 2.126, 2.130c, 2.136, 2.137, 2.145, 5.15, 5.17, neu 2.147-2.149.

## 1 Ausgang

Sieben Pakete entstanden in der Nacht in eigenen Sitzungen, jedes auf einem eigenen `versuch/*`-Zweig, gebaut und am PC
geprüft, keins am Gerät: der Builder (5.17 Weiterbauen nach Abbruch, 5.15 crust als Submodul; M1-M5 am PC), libva über
Baupfade (2.136), der Installer übernimmt den Nutzerstand (1.2b, 2.137), h713-tv nach einem Absturz (2.125), sechs kleine
Punkte (2.130c, 1.2a, 2.108, 2.113, 2.145, 1.10 g), das Mikrofon der Fernbedienung (2.51) und der Strich am G-EU (2.126).
Ziel des Tages: alles einmal am Gerät messen und nur das Bestandene nach `main` nehmen.

## 2 Aufbau

- **Integration:** `versuch/nacht-integration` = `main` b78a6d9d + alle sieben Zweige, jeder Merge mit `release/tor.sh`.
  Zwei Konflikte: die Testliste von h713-tv (`test_crtc` neben `test_bare`/`test_curve` aus der L018-Arbeit) und die
  Kernel-Serie (0345 hinter dem L018-Abschnitt). `tor.sh --tests` und `boards/check.sh` grün.
- **Testabbild:** `build-all.sh --version v0.0-nacht --board hy200-qz713df-a1 --variant projector05061226 --profile
  media,desktop` aus dem Integrationszweig, ohne `CRUST_SRC`: 37 min 39 s, alle 15 Schritte gebaut, `reproducible: yes`,
  crust v0.6.89 aus dem Submodul. Zwei Fehlstarts vorher, beide an der neuen Arbeitskopie, nicht am Code: Git klont die
  Submodule aus lokalen Pfaden erst mit `-c protocol.file.allow=always`, und der abgebrochene erste Lauf hinterließ crust
  halb ausgecheckt (`git reset --hard` im Submodul der eigenen Kopie).
- **Installation:** `h713-fel`, A-auf-A-Kabel (Marco), Probelauf `--no-write`, dann `h713-install install … --small
  --keep-env --dump <Abzug vom 20.10.>` mit dem Installer des Zweigs über v0.97-beta; vorher Sicherung des Nutzerstands
  auf dem Gerät und am PC und eine Prüfsummenliste (MAC-Adressen maskiert).

## 3 Ergebnisse

| Paket | gemessen am G-EU | Urteil |
|---|---|---|
| Builder 5.17/5.15 | Testabbild mit `--variant` gebaut, bootet; Abnahme 25/0/5 | bestanden, `main` 0ce66773 |
| libva 2.136 | `vainfo` H.264 High, HEVC Main; Abnahme mit Kodi grün | bestanden, `main` cac846a1 |
| Installer 1.2b/2.137 | §4.1 | bestanden, `main` 36586276 |
| h713-tv 2.125 | §4.2 | bestanden, `main` 24d2b6cc |
| Kleinkram | 2.113 Auge und Register; 1.2a Journal über vier Boots; 2.108 Wert übernommen; 2.130c am G-EU nicht auslösbar | bestanden, `main` 8471a26b |
| Mikrofon 2.51 | `h713-mic` live über hidraw | bestanden, `main` 725ebbc5 |
| Strich 2.126 (0345) | §4.3: schadet nicht, Heilung nicht messbar | bleibt auf `versuch/rgb-ebene` |
| Histogramm 1.10 g | zählt, Skript liest zu früh an | Skript berichtigen, außerhalb des Repos |

Abnahme (`abnahme.sh -n 1 -t wechsel,direkt,settings,rw,ps,ns,on -K`, HDMI-Quelle ThinkPad): **25 bestanden, 0 nicht
bestanden, 5 nicht gemessen** (die Kamera-Zellen) - Zelle für Zelle gleich dem Lauf mit v0.97-beta vom 22.10.

## 4 Die Messungen im Einzelnen

### 4.1 Neuinstallation (1.2b, 2.137)

Der Abzug vom 20.10. trägt in `uboot-env.bin` noch `h713_gate=0`, das Gerät 1 - genau der Fall vom 22./23.10. Der neue
Installer meldet "the device and …/uboot-env.bin of 20.10.2026 disagree -- h713_gate=1 on the device, 0 in the dump; the
device's value is taken" und übernimmt aus dem alten Rootfs: `keystone.conf`, `mediathek.conf`, `panel.env`, `warp.conf`,
`wifi.env`, sechs Dateien Hostschlüssel, neun Dateien Bluetooth, den Zustand von h713-tv; 67 Dateien zurückgelesen und gleich,
Secure Storage bytegleich, HDCP-1.4-Satz da. Nach dem Neustart (Marco): im WLAN nach ~100 s (kein AP-Modus), ssh mit strenger
Prüfung gegen den alten Hostschlüssel, `h713_gate=1` ohne Handgriff, die Fernbedienung gekoppelt, Keystone wie vorher,
`systemctl --failed` leer. Die Prüfsummenliste vorher/nachher ist gleich bis auf `tv.conf`: die bleibt mit Absicht die des
Abbilds (sie bringt den neuen Kommentar `volume_curve`; die Werte des Geräts waren die Vorgabe). Nebenbefund im Log:
"pq/audio_config.ini: not on the device" - der G-EU behält die eingebaute Lautstärkekurve wie bisher.

### 4.2 h713-tv nach einem Absturz (2.125)

Aufbau nach `arbeit/tv-rettung-20261026/BERICHT.md` §7: alte Fassung = h713-tv aus `main` b78a6d9d, neue = die des
Testabbilds, ein zweiter Prozess hält `/dev/dri/card1` offen (verhindert den letzten close, wie der Halter am 20.10.), die
Rettungsmarke steht, Kodi stumm. Debugfs ist im Kernel nicht eingeschaltet; der CRTC-Zustand ist aus dem Journal geschlossen.

- **Der Auslöser ist enger als gedacht:** ein SIGKILL bei laufendem Kodi lässt den Modus stehen (der Warp zeichnet auf die
  Videoebene, auf der Hauptebene liegt der Konsolenpuffer) - auch mit der alten Fassung. Der Fehler kommt nur, wenn
  h713-tv stirbt, während eine seiner Einblendungen auf der Hauptebene liegt; gemessen mit offenem Launcher.
- **Alt, Launcher offen, SIGKILL:** dreimal "no CRTC drives a mode", "Start request repeated too quickly", `failed` - das
  Bild vom 20.10.
- **Neu aus genau diesem Zustand:** "crtc none drives a mode (the last run's framebuffer went with the primary plane) -- the
  console first", "crtc 36, mode 1280x720", das Kodi-Bild eine Sekunde später, ohne Handgriff. Danach dreimal Launcher offen und
  SIGKILL: jedes Mal dieselben zwei Zeilen und das Bild zurück.
- **Falle:** die Unit erlaubt drei Starts in einer Minute (`StartLimitBurst=3`); drei Abbrüche im Abstand von 12 s enden in
  `failed`, unabhängig von der Fassung. Mit 70 s Abstand bestanden.
- Die Testfassung, die jeden Commit beim Weg hinaus ablehnt, lehnte hier nur die Konsolen-Commits ab und stellte den Zustand
  nicht her; der Arm mit dem offenen Launcher zeigt denselben Mechanismus.

### 4.3 Der Strich am G-EU (2.126, 2.34)

`0x051C01A8` (Lage der RGB-Daten) gegen `0x051C0180` (Bildanfang) in zehn Boots: sechs mit v0.97-beta (der vorgefundene und
fünf Warmstarts), vier mit dem Testabbild - **jedes Mal gleich, `00300530`, L = 48 wie bei Stock**. Am 20.10. (Abbild geu3,
damals mit crust) waren es 50. Der Fehler hängt vom Boot ab und kam heute nie; die eigentliche Probe (heilen die Wörter, die
Stocks `ge2d_dev.ko` schreibt, einen schlechten Boot?) ging nicht. Gegenprobe auf dem guten Boot: die Schritte a (Puls auf
`0x051C0010`), b (dazu `0x0014/24/28`) und c (`0x058C0000`) verschieben `01A8` nicht, der Bildzähler `0174` läuft weiter;
mit b nehmen die Rücklesewörter `0168`/`016C` genau die Stock-Werte `b0`/`94` an (sonst `b4`/`98`). Der Kernel-Kandidat 0345
läuft im Testabbild in jedem Boot ("0x051c0010 00000045 -> 00000000, RGB window 00300530 -> 00300530") und schadet nicht.
Er bleibt auf seinem Zweig, bis ein Boot mit Versatz kommt. Offene Frage: ändert die Hersteller-ARISC (seit 22.10. statt
crust) den Start der Anzeige?

### 4.4 Mikrofon, Weißabgleich, Fernbedienung, Journal, Histogramm

- **2.51:** mit `CONFIG_HIDRAW=y` liest `h713-mic record` die Fernbedienung über `/dev/hidraw0`: 332 Rahmen = 2,66 s, ffmpeg
  macht daraus WAV mit 16 kHz, im Pegel Sprache (Ruhe ~100, Silben bis 2 356). `h713-mic` ist nicht im Abbild.
- **2.113:** Marco: "white balance funktioniert, das weiß passt sich an". `h713-tv ctl wb sliders 10 -6` gibt die Gewinne
  R 480 / B 500 und nennt die Stellungen in der Antwort.
- **2.130c:** die Fernbedienung hat am G-EU nur einen Eingabeknoten (Tasten, Wiederholung und Maus in einem); einen Mausknoten
  ohne EV_REP, den Fehlerfall, gibt es dort nicht. Keine Warnzeile, Mausmodus geht (Marco).
- **1.2a:** nach drei Warmstarts stehen vier Boots in `journalctl --list-boots`, der vorige bis "Journal stopped" lesbar, 6 MB.
- **1.10 g):** die 32 Wörter `0x051C0380`-`0x051C03FC` sind die Fächer des Panel-Histogramms, ihre Summe ist ein Bild
  (921 598 von 921 600 Bildpunkten bei 1280x720); `0x0378`/`0x037C` davor sind laufende Zähler (~200 Mio/s), keine Fächer.

## 5 Stand

In `main` (lokal, nicht gepusht): die sechs bestandenen Zweige als Merges 0ce66773, cac846a1, 8471a26b, 24d2b6cc, 36586276,
725ebbc5; `main` ist damit der gemessene Integrationsstand ohne 0345. `tor.sh --tests` grün, nachdem ein veraltetes
v0.96-Abbild aus `installer/out` beiseite gelegt war (2.148), `boards/check.sh` grün. Der G-EU läuft das Testabbild
`v0.0-nacht`; Rückweg v0.97-beta. Offen: alles am HY310 nachmessen (2.147), 0345 bei einem Boot mit Versatz, das
Histogramm-Skript berichtigen.
