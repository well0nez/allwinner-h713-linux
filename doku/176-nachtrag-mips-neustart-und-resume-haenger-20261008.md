# 176 - Nachtrag 08.10. abends: MIPS-Neustart am HY310 (V2, V3, V8) und die Suche nach dem Resume-Hänger (L-B, L-A, L-C) (08.10.2026, 16:00-21:40; geschrieben 09.10.2026)

**Kurz:** Der Abend des 08.10. stand bisher nur im Protokoll (`arbeit/crust-20261007/STATE.md` 15:55-21:40), in der
Übergabe `arbeit/crust-release-20261007/UEBERGABE-20261008-abend.md` und in Commit-Texten (`0225`, `0231`, `0236`,
`0237`). `doku/172` §2 verweist für L-A auf `doku/170`, dort stehen die Läufe nicht. Dieser Eintrag holt den Abend nach.
Zwei Ergebnisse: Die Anzeige-MIPS lässt sich am HY310 unter Linux neu starten, aus dem Lauf und aus dem Park, und das
Bild kommt zurück. Und ein echter Standby hing mit angemeldetem HDMI-Empfänger, weil jedes LINK-Lesen nach dem
Self-Refresh den Bus anhält, solange die MIPS geparkt ist. Alles lief in Kopien (Teststand aus `/run`, Testmodule in
`updates/` der Box mit Sicherung, Abbild r1test2, FEL-Bild `v1`); `main` trug nichts davon.

## 1 MIPS-Neustart ohne Schlaf (Teststand, Marco an der Wand)

Teststand-Treiber `arbeit/mips-reload-20261008/teststand/` (h713-mips-test), cpu_comm mit 0167/0167c/0167d, hdmirx mit
einer Testzeile. Belege `arbeit/mips-reload-20261008/geraet/V3/` (V0, V2, V3, V8 als Registerabzüge und dmesg).

| Versuch | Ablauf | Ergebnis |
|---|---|---|
| V2 | Modultausch cpu_comm/hdmirx im Lauf | Lücke 67 ms, Übernahme gut, VP_INIT 1, Bild wieder da |
| V3 | Dienste aus, Halt wie der Hersteller (`0x0200160c` = `0x00030001`), `display.bin` laden, Start wie der Hersteller | "ready after 330 ms"; Konsole und TCON-Schachbrett bleiben die ganze Zeit sichtbar; hdmirx binden, h713-tv und warp starten: Laptopbild wieder da |
| V8 | Park wie R1 beim Einschlafen (`0x0200160c` = 0, `0x02001600` = 0), laden, Start wie U-Boot (Takt `0x80000002`, Reset-Leiter je 12 ms) | ready nach 330 ms, Bild wieder da (Marco: "ja klappt"), kein -EBUSY/-ENODEV, crust err 0 |
| V8A | afbd ab- und wieder anmelden um den Neustart | vblank/flip_done-Zeitüberschreitungen, Bild schwarz: kein Weg |

Damit ist das Schwarz nach einem Neuladen am HY300PRO-G-EU (`doku/138`) dort eine Eigenheit; am HY310 bleibt der
Ausgang in jedem Schritt an. Nicht abgedeckt war ein echter Schlaf (DRAM, Stromdomänen).

**V10 ist nicht belegt.** Eine Arbeitsnotiz der Sitzung sagt "V10: dreimal hintereinander gleich", und der Commit-Text
von `0231` übernimmt das ("three times in a row in V10"). Mitschnitte zu V10 gibt es aber nicht, und in den
Werkzeugausgaben der Sitzung stehen nur drei "ready after"-Zeilen (V3, V8 und eine um 18:49). Wiederholt gemessen ist
der Neustart erst mit dem Treiber: `doku/172` §4 (6 von 6 nach echtem Standby), `doku/173` (30 von 30).

## 2 Der Resume-Hänger mit angemeldetem Empfänger

FEL-Bild `v1` (crust a5723aa im SR-Bau), Box r1test2, Belege `arbeit/crust-release-20261007/geraet-20261008/`.

| Lauf | Aufbau | Ergebnis |
|---|---|---|
| V1' (3 Läufe) | alle Treiber, Schlaf 60 s und 5 s | Schlaf und Wecken gut (crust step `0x619`), dann Linux-Hänger im Resume, Reset nach 16,5 s durch den Linux-Zeitschalter |
| E1 | hdmirx abgemeldet | Hänger schon beim Einschlafen (crust-Budget 15 s, path `0x102`) |
| T1 | Linux-Zeitschalter aus | Hänger nach dem msp-Resume, R_WDOG setzt zurück: der Zeitschalter rettet, er verursacht nicht |
| T2 | ohne msp | letzte Zeile afbd "scanout restored", dann Hänger |
| T3, T4 | ohne afbd und hdmirx | Resume komplett (T4: "net released after 2 ms") |
| T5 | AFBD im Park lesen | lesbar (`0x03001901`): der Park allein hält den Bus nicht an |
| T6 | Vsync im Park | läuft mit 60 Hz weiter |
| T7, T7b | alle Treiber, Timer-Modul mit sysrq | keine Ausgabe, die Konsole bricht mitten in einer Zeile ab: die CPU steht hart |
| T8 | hdmirx-Testmodul, Audio-Abfrage ruht ab PM_SUSPEND_PREPARE | kein Linux-Hänger, aber CPU0 kam nicht zurück (crust CAUSE_RESUMING nach 60 s) |

Dann das hdmirx-Testmodul mit dem Schalter `bank_poll` und Brotkrumen in den RTC-GP-Wörtern, die einen Reset überstehen
(GP1 `0x07090104` die Abfrage: `0xA1` vor dem Lesen, `0xA2` danach; GP4 `0x07090110` die Phase: `0xB3` resume_noirq,
`0xB5` Abfrage wieder an):

- **L-B** (Abfrage läuft durch): GP1 = `0xa1000004`, GP4 = `0xb3000003`. Das LINK-Lesen (`0x0684xxxx`) der
  Audio-Abfrage begann nach resume_noirq und endete nie.
- **L-A 1** (Abfrage ruht bis 3 s nach dem Wecken): kein Bus-Hänger, TF-A zurück; dann die USB-Kamera mit -110, Reset.
- **L-A 2**: Resume komplett (0,56 s). 3 s danach die erste Abfrage: GP1 = `0xa1000001`, GP4 = `0xb5000000`, Reset 16 s
  später. Jedes LINK-Lesen hängt also, solange die MIPS nach einem Self-Refresh geparkt ist, nicht nur im noirq-Fenster.
- Behebung im selben Abend: `0236` (`cpu_comm_firmware_up()`) und `0237` (hdmirx liest nach dem Park nie wieder LINK).
  **L-C 1:** "LINK is not read any more", kein Bus-Hänger, Resume bis USB; dann eine -110-Schleife der Kamera, Reset.

Warum LINK nach dem Schlaf hängt, zeigte erst der 09.10. (`doku/172` §1): genpd schaltet TVFE/TVCAP im Schlaf aus und
an, und die TV-Top-Wörter fallen auf ihre Vorgabewerte.

## 3 Was daraus wurde

- Kamera und WLAN nach dem Aufwachen (L-C 2, ld1-ld6; Stand 08.10. 2 von 6 gut): das war Fehler B, gemessen und behoben
  in `doku/171` (`0238`).
- E1 und T8 (Hänger beim Einschlafen, CPU0 kommt nicht zurück) wurden C1: `doku/173`, `0240`.
- Eigener Fehler in ld3: Das Testmodul las in syscore suspend GICC `+0x0c` (IAR) mit. Das Lesen quittiert einen
  Interrupt, CPU0 kam nicht zurück (dasselbe Bild wie T8). Modul danach ohne IAR. Steht jetzt in `referenz/messregeln.md`.
- Entscheidung Zeitschalter (Marco, 16:3x): `RuntimeWatchdogSec` und `RebootWatchdogSec` 16 s ins Abbild
  (`70edea5`, seit `c4a3924` in `main`).
