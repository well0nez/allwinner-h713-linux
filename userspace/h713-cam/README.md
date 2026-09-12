# h713-cam — die interne Kamera ansprechen

Ein Skript, Python 3, ohne Abhängigkeiten. Realtek `0bda:5803` „Generic HD
camera", UVC, an USB-Port 1 (VBUS über PL3). Ein Format: **YUYV 4:2:2,
640×480**. Stock benutzt sie für den Autofokus (`doku/94`).

```
h713-cam probe                    # Treiber, Formate, Bildgrößen
h713-cam controls                 # alle Steuerungen mit Bereich und Istwert
h713-cam get exposure             # eine Steuerung lesen (Name oder 0x-ID)
h713-cam set brightness 100       # eine Steuerung setzen
h713-cam grab                     # Einzelbild nach /data/cam.png
h713-cam grab /tmp/x.ppm --warm 30
```

Der Geräteknoten wird **gesucht**, nicht geraten: `/dev/video2` ist die Kamera
nur, weil Cedrus (`video0`) und HDMI-RX (`video1`) vorher geladen wurden. Das
Skript geht über `/sys/class/video4linux/*/name` und nimmt den Knoten mit
`VIDEO_CAPTURE` — der zweite mit demselben Namen ist der Metadatenknoten
derselben Kamera, kein zweites Gerät. `--dev` übersteuert.

Namen für `get`/`set` dürfen verkürzt sein (`exposure`, `bright`); ist der
Treffer nicht eindeutig, sagt das Skript welche passen.

## Die Macke

Frisch geladen liefert die Kamera **schwarz** (Y ≈ 5, reines Rauschen), auch
nach 90 verworfenen Bildern und mit hellem HDMI-Bild an der Wand. Sobald
**irgendeine Steuerung geschrieben** wurde, ist das nächste Bild normal
belichtet (Y ≈ 187) und die Automatik läuft. `grab` schreibt deshalb vor dem
Stream die Belichtung einmal unverändert zurück. Kommt trotzdem Y < 16 heraus,
sagt das Skript es dazu.

Gemessen 11.09.2026, Beleg `analyse/beamer-cam/README.md` und `foto-e313.png`.

## Warum ohne PIL, v4l2-ctl, ffmpeg

Das Release-Rootfs trägt nichts davon (`packages.txt`: „kein Paket für alle
Fälle"). PNG entsteht aus `zlib` der Standardbibliothek, die YUYV→RGB-Rechnung
ist BT.601 in reinem Python — auf dem A53 einige Sekunden für 640×480, dafür
läuft es überall, wo `python3` liegt.

## Herkunft

Zusammengelegt am 12.09.2026 aus `analyse/beamer-cam/{camprobe,camset,camgrab}.py`.
Die Originale bleiben dort als Messbeleg. Neu gegenüber den dreien: die
Gerätesuche, `controls`, Namen statt nur IDs, PNG.

Was die Kamera **tun** soll (Autofokus wie Stock, nur mit Testbild — siehe
`h713-focus/README.md`), ist eine eigene Aufgabe nach dem Release.
