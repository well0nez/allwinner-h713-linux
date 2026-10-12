# 205 - Remote-Reihe am G-EU: Kaltstarts, Standbys, Warmstarts, HDCP, PC-Modi, WLAN-Hänger (12.10.2026, vormittags)

**Kurz:** Marco unterwegs, der HY300PRO-G-EU am Sonoff, UART-ESP mitlesend, ThinkPad als Quelle. Elf Messreihen ohne Hände am Gerät
(Paket `arbeit/remote-reihe-20261012/`, dort `BERICHT.md`, Skripte, Rohdaten). Ergebnis: **vier Befunde gefunden** (2.66 bis 2.69, alle noch
am selben Tag in `doku/206` an der Wurzel gelöst), **zwei Fixe direkt** (Warp-Steuersocket 2.4d, WLAN-Hängefall 1.3), zwei Punkte geschlossen
(2.36, 2.55 nachgewiesen), Kaltstarts und Bluetooth ohne Befund.

| Reihe | TODO | Ergebnis |
|---|---|---|
| A 8 Kaltstarts über den Sonoff | 1.2a | 8/8: ssh nach 20-23 s, **kein zweiter Boot** in 240 s, je ein `U-Boot SPL`, `gate: off`, 0 failed, 0 mmc-Fehler. Nebenbefund: das dauerhafte Journal hält nur ~30-40 Boots (88 MB) |
| B Bluetooth | 2.49 | 48 Starts (kalt, warm, Standby) jeder beim 1. Versuch, 0 HCI-Fehler; unter WLAN-Last (44 Mbit/s) + Warp + LE-Suche 0 Fehler. Der Mikro-Strom der Fernbedienung (~7,5 kB/s) blieb ungetestet (braucht die Fernbedienung) |
| C 20 Standbys per RTC | 2.37, 2.66 | 20/20 zurück (5,0-6,0 s); DSP 17x im 1., 2x im 2., **1x im 3. Versuch** (Grenze); 2x "0 Bilder/s" nach dem Aufwachen (st6, st18) - Marco: evtl. der ThinkPad, nach dem Release mit Fire TV wiederholen (2.66) |
| D 20 Warmstarts | 2.63 → 2.67 | 19 sauber, **warm14**: Sperre 2 `own=0 ref=1 tid=0xff`, 22 abgewiesene `open()`, `h713-tv-rescue` holte das Bild nach 4,46 s - ohne vorherigen Absturz, ohne "free lock carried" |
| E Tasten im Login-Feld | 2.55 | **nachgewiesen:** KEY_UP/KEY_LEFT in `sunxi-ir` eingespeist → `/dev/vcs1`: `hy310 login: ^[[A^[[D` |
| F Log-Maske | 2.36 | `0x4B48BE84 = 0xA7`, `fmt_set[1..5] = 0xA7` wie im Listing - geschlossen |
| G Warp-Reste | 2.4d | `zoom 50abc`/`edge 4x` angenommen → jetzt `error`; ein Client ohne Zeilenende hielt die Render-Schleife 500 ms → jetzt keine Lücke > 20 ms (Steuersocket hält die halbe Zeile zwischen zwei Schleifendurchläufen); Texte "XRGB8888/primary plane" berichtigt. In `main` 62d1887. Der 2.12-Patch (evaluate bei -ENOLCK) wurde in 9 Versuchen nie ausgelöst, nicht übernommen |
| H WLAN-Hängefall | 1.3 | nachgestellt (`install`-Hänger in modprobe.d): `timeout 30` greift, aber systemd wartete danach die Stop-Frist **90 s** auf den hängenden Rest der cgroup - Boot fertig nach **2 min 15 s**, ssh ab 127 s. Mit `TimeoutStopSec=10`: ssh ab 46 s, fertig nach 54 s. In `main` c809c23 |
| I HDCP 1.4 nach Moduswechsel | 2.26 | ThinkPad: sofort angefordert → `Enabled` nach 3,07-3,09 s (4x), ab 1 s Verzögerung nach 1,15 s. Anders als `doku/170` §3 am HY310 (blieb 40 s `Desired`) - Board oder Stand, nicht getrennt |
| J 14 PC-/SD-Modi, Bypass und Warp | 2.4f, 2.68, 2.69 | Bypass: 12 von 14 mit Bild, **1280x1024 (Ring "912x728") und 1360x768 ("1280x722") Konsole** (2.69). Warp an: Pitch 800/720/912 abgewiesen (2.4f); in 2 von 4 Durchläufen behielt der Warp nach dem Wechsel die alte Ringgröße (2.68) |

Panne: `sonoff_ctl on` fand den Sonoff per mDNS nicht, nachdem `off` geklappt hatte - die Box war ~20 s stromlos, dann `--host`; seither
schaltet das Skript immer mit Adresse und wiederholt `on`.

Schreibzugriffe am Gerät: Skripte nach `/root/`, `systemctl restart getty@tty1`, Testmodule h713-warp/h713-tv (zurückgetauscht,
Sicherung `/root/sicherung-warp-reste/`), ein Drop-in für H (entfernt), Strom/Neustarts/Standbys.
