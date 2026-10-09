# 174 - Gerätetests mit Marco: Taste, Fernbedienung, lange Schläfe; der Ton kommt nach dem Standby zurück (09.10.2026, 15:30)

**Kurz:** Mit Marco an der Box (r2test3, Konsole mitgeschnitten, nur gelesen) liefen die Standby-Stufen, die ohne
Menschen nicht gingen: Standby und Wecken per Power-Taste, Wecken per IR-Fernbedienung, Schläfe von 3,5 und 8,4 Minuten,
der lange Druck. Alles verhielt sich wie vorgesehen. Der Ton nach dem Standby, in `doku/173` noch "erst nach einem
Neustart", kommt jetzt mit dem Bild zurück: `h713-mips-restart` baut den Audio-DSP nach dem Bild neu auf. Alles in
Kopien (R2-Zweig `versuch/r2-standby`, Box mit Sicherung); `main` trägt nichts davon. Protokoll:
`arbeit/crust-20261007/STATE.md` ab 14:35, Mitschnitt `arbeit/r2-20261009/marco-tests/uart.log`.

## 1 Die Stufen

| Test | Ergebnis |
|---|---|
| kurzer Druck -> Standby | Standby 31, ohne RTC-Alarm |
| Wecken per Taste | "wake key (0x95)"; der Weck-Druck zählt nicht als neuer Druck (kein zweiter Standby) |
| Wecken per Fernbedienung | "wake ir (0x9b)" nach 27 s |
| Schlaf 3,5 min / 8,4 min | gewacht per Taste, Bildpfad nach 3,9-5,3 s |
| langer Druck | `poweroff`, BL31 "resetting into the boot gate", U-Boot "gate: off (h713_gate=0)" -> bootet durch (Gate im Environment der Box aus, nicht angefasst) |
| Ton nach dem Standby (vor der Behebung) | Laptop-Ton über HDMI zweimal nicht hörbar, msp "error", ein Box-Ton (`aplay`) wird abgewiesen, kein Hänger |
| Ton nach einem Neustart | hörbar (Bezug) |

Vom Wecken bis zum Bild an der Wand vergehen etwa 11 s: MIPS-Neustart 4,5 s, dann setzt h713-tv beim Start den HPD
300 ms auf low, und der Laptop braucht gut 4 s, bis er wieder sendet. Bei unveränderter EDID ließe sich das sparen
(TODO).

## 2 Der Ton

Nach einem Standby stand msp auf "error" (0243). `echo 1 > reset` nach der Bild-Rückkehr: nach dem 8,4-min-Schlaf
"running", der Laptop-Ton war leise hörbar. Drei weitere Standbys mit dem Neuaufbau direkt nach der Bild-Rückkehr:
running, running, einmal Mailbox-Timeout und beim zweiten Versuch running (`arbeit/r2-20261009/ton/`). Vormittags auf
r2test2 (ohne 0243) war ein einzelner Versuch gescheitert; ob 0243 (Insel vor dem Schlaf sauber als verloren
markiert) oder der Zeitpunkt den Unterschied macht, ist nicht getrennt gemessen.

`h713-mips-restart` baut den DSP jetzt nach "picture path back" neu auf (msp "error" -> `reset`, bis drei Versuche;
ein DSP, der unten bleibt, ist eine Warnung, kein Exit-Code), mit fünf neuen Tests (56 Tests grün). Am Gerät: Standby
per RTC-Wecker, "audio DSP rebuilt (attempt 1)", danach Laptop-Ton über HDMI hörbar, ohne Neustart.

## 3 Offen

- Die Meldung von msp nach dem Standby sagt noch "no HDMI audio until a reboot" (Text in 0243 anpassen).
- Leistung im Standby, HDCP 2.2 von der Quelle nach dem Neustart: nicht gemessen.
- Ob C1 in langem Gebrauch ausbleibt (0 in 50 seit dem Aufnahme-Stopp), zeigt der Gebrauch.
