# Interne Kamera des Beamers

Realtek `0bda:5803` „Generic HD camera", UVC 1.00, an `ehci@4200000` (USB-Port 1, VBUS über PL3).
Ein Format: **YUYV 4:2:2, 640×480**. Stock benutzt sie für den Autofokus ([`doku/94`](../../doku/94-fokusmotor-endschalter.md)).

**Seit 11.09. angebunden.** Sie wurde vom Bus immer erkannt, aber es gab keinen Treiber: `uvcvideo` war
nicht gebaut. Drei Schalter im defconfig (`MEDIA_CAMERA_SUPPORT`, `MEDIA_USB_SUPPORT`, `USB_VIDEO_CLASS=m`)
— kein eigener Treiber nötig, kein Patch, kein Firmware-Blob. Das Modul lädt udev von selbst, sobald es im
Rootfs liegt (`modroot.e88af5af` oder neuer).

## Geräteknoten

| Knoten | Was |
|---|---|
| `/dev/video2` | das Bild (`VIDEO_CAPTURE`) |
| `/dev/video3` | **kein zweites Gerät** — der Metadatenknoten derselben Kamera (`META_CAPTURE`, Zeitstempel je Frame). Standard bei `uvcvideo`. |

Die Nummern hängen von der Ladereihenfolge ab (`video0` Cedrus, `video1` HDMI-RX). Sicher finden:
`grep -l "HD camera" /sys/class/video4linux/*/name`.

## Werkzeuge (laufen am Gerät mit blankem `python3`, kein `v4l2-ctl`, kein `ffmpeg`)

| Skript | Zweck |
|---|---|
| `camprobe.py DEV` | Fähigkeiten, Formate, Bildgrößen |
| `camgrab.py DEV AUSGABE.ppm [WxH] [VORLAUF]` | ein Einzelbild per MMAP-Streaming, YUYV → PPM; `VORLAUF` = verworfene Bilder für die Belichtung |
| `camset.py DEV ID [WERT]` | eine V4L2-Steuerung lesen/setzen (IDs siehe `analyse/hdmi-seq/camctl.py`) |

```bash
scp camgrab.py root@192.168.8.141:/tmp/
ssh root@192.168.8.141 'python3 /tmp/camgrab.py /dev/video2 /tmp/foto.ppm 640x480 30'
scp root@192.168.8.141:/tmp/foto.ppm . && python3 -c "from PIL import Image; Image.open('foto.ppm').save('foto.png')"
```

## Macke, gemessen 11.09.

Direkt nach dem Laden liefert die Kamera **schwarz** (Y ≈ 5, reines Rauschen 3…9), auch nach 90 verworfenen
Bildern und auch mit hellem HDMI-Bild an der Wand. Sobald **eine beliebige Steuerung geschrieben** wurde
(`Exposure Time` reichte), war das nächste Bild sofort normal belichtet (Y ≈ 187). Die Belichtungsautomatik
läuft danach von selbst; manuelle Belichtung 313 vs. 800 ändert nichts am Ergebnis. `camgrab.py` schreibt
deshalb vor dem Stream die Belichtung einmal unverändert zurück.

Beispiel: [`foto-e313.png`](foto-e313.png) — die Wand vor dem Gerät, HDMI an.
