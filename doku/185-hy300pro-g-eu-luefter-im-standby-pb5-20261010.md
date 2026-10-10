# 185 - HY300PRO-G-EU: Lüfter und Lampe im Standby aus - PB5 gehört dem Board-Manager (10.10.2026, 02:30-02:50)

**Kurz:** Im Standby lief am HY300PRO-G-EU der Lüfter weiter (`doku/184`, TODO 2.33; Marco: "das soll definitiv nicht so
sein"). Ursache: unser Gerätebaum des Boards hielt PB5 als gpio-hog und nahm dem Board-Manager `fan-power-gpio` weg; der sagte
beim Suspend "fan power rail not ours, left as it is". Der Stock-Gerätebaum des Geräts nennt PB5 aber genau wie der des HY310:
als `panel_bl_en` (Freigabe der Lampe) und als `fan-power-gpio` des Lüfters. Kernel `0249` gibt PB5 dem Board-Manager wie am
HY310. Gemessen: Lüfter aus, Lampe dunkel im Standby, nach dem Wecken alles zurück. crust musste nicht angefasst werden.

## 1 Beleg

- Stock-Gerätebaum aus `vendor_boot_a.img` des eigenen Abzugs (`re/device-dumps/hy300pro-plus-marco/partitions/`, nur gelesen;
  das DTB nach `arbeit/geu-crust-20261009/luefter/stock/` gezogen und dort zurückübersetzt): Knoten `fan`/`fan0`
  `fan-power-gpio = <&pio 1 5 0>` (PB5), `fg-gpio` PH13; Anzeige-Knoten `panel_bl_en = <&pio 1 5 0>` (PB5), `panel_power_en`
  PF6. Damit ist PB5 auf diesem Board dieselbe gemeinsame Schiene wie am HY310 (Lüfter und LED-Boost, `0211`). Der HY300 Pro
  aus Issue #1 (anderes Board, Vorfall 19.09.) behält den Hog.
- Der Board-Manager schaltet die Schiene nur in `suspend` (aus) und `resume` (an), nie im Betrieb.

## 2 Messung

`0249` als Commit in `arbeit/geu-crust-20261009/kgit` (Zweig `versuch/geu-luefter`); nur das DTB im gebauten Kernelbaum
übersetzt (`make ... allwinner/sun50i-h713-hy200-qz713df-a1.dtb`, nur DTC; der Baum danach zurückgesetzt, sein DTB wieder
bytegleich mit dem von `geucrust2`), FIT mit dem `geucrust2`-Kernel und dem neuen DTB (`luefter/fit/h713-kernel-pb5.fit`,
md5 `33acde02`) als Schnell-Deploy nach `/boot`, Sicherung `/root/sicherung-luefter/h713-kernel.fit` (md5 `895c31ae`).

| Schritt | Ergebnis |
|---|---|
| Boot | `fan0: fan-power-gpio 37 set HIGH` (statt "managed by hog") |
| Standby, RTC 30 s (`standby/f1`) | "suspended: fan power rail off"; Marco: Lüfter aus |
| Wecken | "resumed: fan power rail on", crust "wake rtc" nach 29810 ms, Bildpfad 5281 ms, audio DSP attempt 1; Marco: "wieder an mit Konsole" |

Ein Lauf. Nicht gemessen: die Leistung im Standby mit ausgeschaltetem Lüfter (Wattmeter, Marco heute nicht).

## 3 In `main`

`0249` in der Serie (2 Dateien: G-EU-Baum, Kommentar im HY310-Baum), Doku `standby.md`, `known-issues.md` (Zeile entfernt),
Board-Seite, TODO 2.33 erledigt. Die Box läuft `geucrust2` + dieses DTB.
