# 217 HY300PRO-G-EU: Ein und Aus mit der Fernbedienung, Augentests des Abends - Protokoll

Datum: 20.10.2026 (abends, 21:05-21:32 UTC). Gerät HY300PRO-G-EU, Abbild geu3 (`medien` `306a2a2`) mit den Deploys des Tages
(h713-tv `530cbf11`, h713-remote-pair `ef84c417`), Gate 0, Marco an der Wand, Aufsicht an der Box. Laufprotokoll:
`arbeit/medien/AUFSICHT.md` (lokal). Ergebnisse in TODO 2.84 (a, b, g, h, k, l), 2.87, 2.109, 2.126, 2.131.

## 1 Ein und Aus mit der Fernbedienung

| Zeit (UTC) | Was | Ergebnis |
|---|---|---|
| 21:19:34 | Power über die nachgebildete BT-Fernbedienung (uhid), RTC-Wecker 90 s gestellt | 15-s-Countdown, dann **Aus** über crust: am G-EU gilt `power.conf short = poweroff`. Lampe und Lüfter aus (Marco). Der RTC-Wecker weckt aus dem Aus nicht - gewollt, aus dem Aus wecken nur Taste und Fernbedienung (`docs/tools/h713-power.md`) |
| ~21:23 | Marco drückt Power auf der Fernbedienung | frischer Boot (Systemzeit 21:23:45, arisc: "powered off through crust, back by the R_WDOG"), Launcher 21:23:54 |
| 21:24:33 | `systemctl suspend`, RTC-Wecker 60 s | `standby 1: wake rtc (0xc0000000), slept 59837 ms`, Bildweg nach 6,5 s, HDMI-Bild zurück (Marco) |
| 21:30:23 | Marco drückt Home auf der Fernbedienung (nach dem Neustart, BT noch getrennt) | Launcher offen 21:30:23,34 - die Taste kam **per IR**; das BT-Gerät meldet sich 0,3 s später, h713-keys hört ab 21:30:28 darauf. Vorher `Connected: no` (die Fernbedienung schläft bis zum ersten Druck) |
| 21:31:07 | `h713-tv ctl mute on`, `systemctl suspend` (RTC 150 s nur als Netz); Marco drückt nach ~9 s Power | `standby 2: wake ir (0x9b), slept 8580 ms`, Bildweg nach 4,9 s; h713-tv: `ctl mute on -- kept from the run before`. Danach `ctl mute off` |

Marco (20.10.2026): Ein- und Ausschalten mit der Fernbedienung funktioniert über BT und IR. Gemessen ist davon heute am G-EU: Aus
über die Power-Taste der (nachgebildeten) BT-Fernbedienung, Wecken aus dem Aus und aus dem Standby über die Power-Taste per IR,
die erste Taste nach dem Neustart per IR. Die echte BT-Taste für Standby/Aus ist am HY310 gemessen (`doku/174` §1), am G-EU nur
nach Marcos Gebrauch, nicht mit Protokollzeile.

## 2 Weitere Augentests des Abends

| Was | Ergebnis |
|---|---|
| Strich ganz links unter dem Launcher (2.126) | weg, die schwarze Abdeckung unter Seiten wirkt (Marco 21:30); die Ursache bleibt offen |
| schwarzer Block unten im Launcher bei jedem zweiten Zug (2.131) | nicht nachgestellt: zwei Läufe 21:06/21:08 mit Ebenenbild je Zug, der Launcher wechselt zwischen zwei Puffern, beide ohne Loch; Marco sah keinen Block. Der Block auf dem Foto sitzt am Ort der Lautstärke-Pille |
| `h713-tv ctl set backlight_level 50/100` | keine sichtbare Wirkung (zweimal je 10 s), wie 2.11 am HY310 |
| 3 x Kodi -> Desktop -> Browser -> HDMI über den Launcher | nichts aufgefallen, kein Lichtflackern unter der Last (Marco: ruhiger als der HY310) |
| Kippen, Trapez folgt (2.109) | von Marco selbst getestet, funktioniert; `after_move` steht nach seiner Vorgabe auf `off` |

## 3 Nicht gemessen

- Leistungsaufnahme im Aus und im Standby an diesem Abend (Werte in `docs/hardware.md` stammen aus `doku/188`).
- Die Mausfunktion der Fernbedienung in den ersten Sekunden nach dem Wecken (2.130: bis BT steht, kommen die Tasten per IR, die
  Maus fehlt).
