# 230 HY320: AirPlay-Bildschirmspiegelung (h713-airplay) - Protokoll

Datum: 05.11.2026 (Gerätezeit falsch, April 2026). Gerät: der HY320 des Besitzers, Profil `desktop`, im Netz `h713`
(192.168.4.1). Augen: **keine** - der Besitzer war nicht da; die Wand wurde mit `kmsgrab` (die Ebene mit Framebuffer) und
`h713-warp ctl dump` (die Luma des zuletzt gezeichneten Bildes) gelesen. **Kein iPhone**: jeder Strom am Gerät kam von
`h713-airplay sendtest` auf dem Gerät selbst an 127.0.0.1:7000 - das ganze Protokoll (`/info`, `fp-setup`, Paarung,
SETUP/RECORD, der verschlüsselte Bildstrom, Ton, TEARDOWN) -, auf dem Arbeitsrechner von doubletake. Stand: Zweig
`feat/hy320-airplay` (lokal, nicht gepusht); auf dem Gerät Empfänger, Warteseite und Presenter von `375e7e99`, h713-warp
von `975b332d`. Gebaut auf dem Arbeitsrechner (`make cross` gegen das Sysroot aus
`userspace/h713-airplay/tools/make-sysroot.py`), nicht im Build-Container. Doku: [h713-airplay](../docs/tools/h713-airplay.md),
[h713-warp](../docs/tools/h713-warp.md). Rohlogs und Prüfskripte liegen außerhalb des Repos; die Zahlen hier sind aus ihnen
abgeschrieben.

## 1 FairPlay (Arbeitsrechner)

- `crates/fairplay` gegen UxPlays `playfair` (UxPlay `df67c212`, über einen kleinen C-Treiber, gcc 15.2, `-O2`; `-O0` gibt
  dieselben Bytes): Zufallsfälle in allen vier Modi, 1000 je Modus (Saat `0x5eed`, nachgefahren mit `0x1ead0001`) und
  10000 je Modus (Saat `0xa1a2a3a4`): **0 Abweichungen**. Die festen Vektoren (`playfair_vectors.txt`) passen. Gegenprobe:
  eine geänderte Hex-Ziffer in Zeile 50 lässt den Vektortest fallen; zurückgesetzt besteht er.
- doubletakes Go-Seite auf denselben 1000 Fällen je Modus: m4-Bytes und Schlüssel in allen vier Modi 1000 von 1000 gleich.
- `decrypt_key`: etwa 23 µs je Aufruf (Release, x86-64).

## 2 Ende zu Ende auf dem Arbeitsrechner (doubletake)

- doubletake (`-test`: ein synthetisches Bild, Ton an) gegen `h713-airplay run`; an Stelle des Presenters ein Stellvertreter,
  der schreibt, was er bekommt. Zustand `streaming`; `ctl status` zählte 376 Bilder H.264 1920x1080 und 1614 Tonpakete
  (ALAC, 44.1 kHz, stereo). Der Mitschnitt: 377 Bilder, von FFmpeg ohne eine Fehlerzeile dekodiert; der Ton 12.89 s, ebenso.
- Nach TEARDOWN war der Zustand nach 0.0185 s `idle`.

## 3 Gefunden werden (von einem zweiten Rechner im Netz `h713`)

- mDNS-Abfrage, 3 s: 7 Antworten von 192.168.4.1 - A `hy320.local`, dazu PTR, SRV (Port 7000) und TXT für
  `HY320._airplay._tcp` und `<deviceid>@HY320._raop._tcp`; im TXT `features=0x527FFEE6,0x400`, `model=AppleTV3,2`,
  `pw=false` und `pk`. Ohne avahi: der Responder ist im Empfänger (mdns-sd).
- `GET /info RTSP/1.0` mit `CSeq: 1`: `200 OK`, `application/x-apple-binary-plist`, ein Display 1920x1080 mit `maxFPS 60`,
  Name `HY320`. `OPTIONS`: 200.
- Zweimal gemessen: zuerst mit dem Empfänger allein als vorübergehende Unit aus /tmp (`6166dab0`), am Ende mit der
  installierten `h713-airplay.service` nach den Strömen des Tages - beide Male dasselbe.

## 4 Leerlauf

- Der Empfänger ohne Sender, 60 s, utime+stime aus `/proc/<pid>/stat` (CLK_TCK 100): **0 Ticks**. Zuerst (frisch
  gestartet, `6166dab0`): 9 Threads, alle `S`, 3.6 MB resident. Am Ende (installierte Unit nach vier Sitzungen mit
  zusammen über einer Minute 1080p60, derselbe Prozess seit dem Einspielen): wieder 0 Ticks in 60.01 s, 9 Threads, alle
  `S`, 4.3 MB resident. Kein Presenter-Prozess.

## 5 Das Bild an der Wand

### 5.1 Der erste Weg: RGB im Presenter, dann der Warp

Der Presenter wandelte die NV12-Flächen des Decoders auf der GPU in RGB, h713-warp zeichnete das RGB-Bild durch die
Keystone-Matrix. Dekodiert wurde mit 60/s (cedrus 60 Interrupts/s, etwa 1.1 ms je Bild), an der Wand kamen 25-30 Bilder/s
an: die zwei GPU-Durchgänge kosteten zusammen 14-21 ms je Bild. Der Engpass war die GPU, nicht der Decoder.

### 5.2 NV12 von Wayland-Clients in h713-warp (`975b332d`)

h713-warp bietet NV12 LINEAR an, wenn der Render-Knoten R8 und GR88 importiert (auf dem HY320: 71 Formate statt 70), und
zeichnet Y und CbCr mit den Shadern des Rings in **einem** Durchgang durch Rand, Letterbox und Keystone. Gemessen mit
`h713-airplay-show --feed` (ein 1080p60-H.264-Clip, ohne Netz):

- 1220 Bilder als NV12-Fläche übergeben, 0 gewandelt; h713-warp zeigte 59.1 Bilder/s, der Presenter 1219 von 1237
  dekodierten.
- GPU je Bild 6.55 ms im Mittel, 10.6 ms höchstens (180 Bilder, 200 MHz, Chip 86.6 °C); die CPU-Seite des Zeichnens
  1.1 ms. Ein 720p-Panel mit 348 MHz brauchte 1.78 ms - bei 2.25-mal so vielen Pixeln und 200 MHz derselbe Aufwand je Pixel.
- Ein Testclient mit einem bekannten Muster in vier GBM-Puffern: der Dump las die acht Luma-Balken genau (16, 47 ... 233)
  und den Rand bei 235, 6.93 ms GPU je Bild. Ein Vorrat von 20 NV12-Puffern wurde angenommen (die alte Grenze von acht
  Importen je Client hätte den neunten abgewiesen; jetzt zählen gehaltene Puffer bis 32, der Cache freigegebener bleibt bei 8).
- Kodi (AR30, AFBC, Modifier `0x800000000000062`) und die Kein-Signal-Seite unverändert.

### 5.3 Das ganze Protokoll, 1080p60

`h713-airplay sendtest --target 127.0.0.1:7000 --fps 60 --audio tone --seconds 32`, Messfenster 20 s, gestartet aus dem
Kein-Signal-Zustand (Launcher zu, Panel von niemandem beansprucht):

| | H.264 | H.265 |
|---|---|---|
| h713-warp, Client-Bilder gezeigt | 1204 in 20.06 s = 60.0/s | 1204 in 20.07 s = 60.0/s |
| Format beim Warp | NV12 LINEAR, durchgereicht | NV12 LINEAR, durchgereicht |
| cedrus-Interrupts | nicht gelesen (falscher Name im Skript) | 1204 = 60.0/s |
| Presenter: dekodiert / gezeigt / verworfen | 1472 / 1437 / 33 | 1462 / 1437 / 23 |
| Presenter: fps, Hardware, gemeldete Latenz | 59.99, ja, 23 ms | 59.99, ja, 19 ms |
| CPU (Anteil eines Kerns): Presenter, Empfänger | 1.9 %, 1.5 % | 2.0 %, 1.3 % |
| Presenter resident | 34.3 MB | 36.9 MB |
| ALSA | card1 `RUNNING` | card1 `RUNNING` |

- Der Dump im H.265-Lauf zeigt das Testbild (Bild 284) durch den Keystone verzogen.
- Das Ende (TEARDOWN des Senders): `sendtest` rc 0, Zustand `idle`, Presenter-Unit `inactive`, der Launcher geht auf
  (h713-keys: `ended by itself: the launcher opens, HDMI input chosen`), h713-warp hat 0 Clients, 0 Zombies.
- "Verworfen" heißt: dekodiert, aber vor dem Zeigen von einem neueren Bild ersetzt (die Anzeigeschlange hält eins).

## 6 Launcher und Warteseite

Die Tasten kamen von einer uhid-Fernbedienung auf dem Gerät (h713-keys liest sie wie die echte).

- Home: der Launcher mit sechs Einträgen, Screen Mirroring an zweiter Stelle mit dem AirPlay-Symbol.
- Ab, OK: die Warteseite (`h713-airplay page` als `h713-airplay-page.service`), deckend über dem ganzen Panel (`page open
  (opaque: the mode under it pauses)`): `HY320`, Wi-Fi `h713`, IP `192.168.4.1`, `Ready`.
- Back: `Screen Mirroring ended with 0: back to the launcher`, Screen Mirroring gewählt.
- Home während eines Stroms: der Launcher über dem laufenden Strom, im Kopf `18:15 · AirPlay` (kmsgrab), der Presenter
  läuft weiter.

## 7 Übernahme und Abbau

| Fall | Ergebnis |
|---|---|
| (a) Launcher offen, ein Strom kommt | der Launcher geht zu (`mode h713-airplay-show.service came up, not the launcher's: the launcher closes`) |
| (b) `h713-mode hdmi` während des Stroms | der Presenter endet, kein Launcher (`ended (h713-mode hdmi)`); der Sender bekommt `Broken pipe` |
| (c) Kodi läuft, ein Strom kommt | Kodi gestoppt (`Conflicts=`), der Strom an der Wand |
| (d) Home während des Stroms | der Launcher über dem Strom, Kopf `AirPlay` |
| (e) `h713-mode sleep-pre` / `sleep-post` während des Stroms | vor dem Schlaf beendet und in `/run/h713-mode.resume` gemerkt; danach wieder gestartet, ohne Sitzung von selbst beendet, der Launcher geht auf |
| (f) die Warteseite offen, ein Strom kommt | h713-keys stoppt die Seite (`Screen Mirroring (h713-airplay-page) is stopped`, `ended with 15 (stopped: a mode took the wall)`), Seite und Launcher zu, das Bild als NV12 an der Wand |
| (g) ein zweiter Sender während eines Stroms | der erste bekommt binnen 8 s `Broken pipe` (rc 1), der zweite streamt (Bilder 213 -> 334 in 2 s, Sitzungen 5 -> 6), der Presenter bleibt oben; nach seinem TEARDOWN `idle`, der Launcher geht auf |

Nach jedem Lauf: kein Presenter, h713-warp ohne Client, 0 Zombies. In (f) endete die Seite mit 15, nicht mit 16: h713-keys
war schneller als die Seite selbst.

## 8 Funde nebenbei

- Wer h713-keys neu startet, während der Launcher offen ist, lässt eine verwaiste Launcher-Seite im OSD zurück. Nicht Teil
  dieser Änderung, offen.
- `make test` von h713-warp: `connections 2-4 see the globals, the fifth gets an error` scheitert (3 von 4), am unveränderten
  Stand ebenso.
- Drei Fehler im Prüfskript sahen zuerst wie Fehler des Empfängers aus: `sendtest` wählt den Codec nach der Endung (eine
  Datei ohne `.h264`/`.h265` bricht sofort ab, der Zustand bleibt `idle`); ein Hintergrundjob in `ssh ... bash -s` braucht
  `< /dev/null`; h713-warp hat `PrivateTmp`, ein Dump nach `/tmp` landet dort - nach `/run/h713-warp/` schreiben.
- Der erste C7-Lauf ließ Kodi laufen (`sleep-post` startete es aus `/run/h713-mode.resume` wieder); beim Stoppen schrieb Kodi
  seine `guisettings.xml` einmal neu, mit den Einstellungen, die es geladen hatte.

## 9 Nicht gemessen

- Ein echtes iPhone, iPad oder ein Mac (Apples FairPlay-Seite, iOS 27): steht aus - der Besitzer probiert es.
- Vom Antippen von Screen Mirroring bis zum Bild, Glas zu Wand, Ton gegen Bild, verworfene Bilder über zehn Minuten.
