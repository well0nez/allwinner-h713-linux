# 159 - Presets computer/game/hdr und das Merken über den Neustart (06.10.2026)

**Kurz:** TODO 2.17 und 2.20 geschlossen. Die drei nie geprüften Presets setzen am Gerät genau die Herstellerdaten der
Box und zeigen ein intaktes Bild. Preset, Regler und Startmodus überleben einen warmen Neustart - das war seit Plan 113
im Code, nur nie gemessen. Ein Vergleich mit Stock (Gamma, Weißabgleich) findet nicht statt (Marco). Arbeitspaket
lokal: `arbeit/presets-20261006/`.

## 1 Presets (HY310, 17:53 UTC)

`h713-pq show HDMI1 <preset> --json` gegen `h713-tv ctl preset <preset>` und `ctl list`:

| Preset | picture_mode | Helligkeit, Kontrast, Sättigung, Farbton, Schärfe, TNR, SNR, DCI, Schwarz | gleich |
|---|---|---|---|
| computer | 6 | 50 50 50 50 0 0 0 0 0 | ja |
| game | 3 | 50 50 50 50 50 1 0 0 0 | ja |
| hdr | 12 | 50 50 50 50 50 1 1 0 0 | ja |

Kamerafoto je Preset: Bild intakt. Gamma: die Kurve der Box selbst (`gamma-tse.bin`, ProjectID 0x30, 2,2).
Weißabgleich/CTM: die CRTC-CTM des Kernels nutzt kein Werkzeug; ohne Stock-Vergleich gestrichen. Ein Regler dafür wäre
ein neues Feature.

## 2 Merken über den Neustart (17:55 UTC)

`tv.conf` auf dem Gerät: `start = last`, `preset = last`. `ctl preset cinema`, `ctl set brightness 55`, `ctl save`,
`ctl off` (-> `/var/lib/h713-tv/modus` = `off`), `systemctl reboot`. Nach dem Boot: `start=last; saved=off` -> Konsole
statt Bild, Journal `preset cinema …`, `saved 9 values … brightness=55`, `ctl list` Helligkeit 55, picture_mode 7.
Danach zurück: `ctl on`, `werte` aus `/root/sicherung-presets/` (md5 gleich), `ctl preset standard`; Warp, Modus und
Trapez unverändert.
