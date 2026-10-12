# 209 - Die 5.x-Runde, Teil B mit Marco am HY310, alles nach `main`, das Panel mit den Beamer-Begriffen; Handoff (13.10.2026, nachts)

**Kurz:** Fortsetzung von `doku/208`. Teil B des Messplans (`arbeit/testabbild-20261012/MESSPLAN.md`) mit Marco am HY310 (`runde5x1`):
bestanden. Danach Dienste, Kernel/ARISC, TF-A und das neue Panel nach `main` (lokal, **nicht gepusht**).

## 1 Teil B (12./13.10., Mitschnitte `arbeit/testabbild-20261012/laeufe/teilb-*.log`)

| # | Gemessen | Ergebnis |
|---|---|---|
| B2 | Power: Countdown, zweiter Druck = Standby, dritter Druck beim Einschlafen (zwei Anläufe) | 1. Anlauf: der dritte Druck kam in den Schlaf (4,9 s, `wake key (0x95)`); 2. Anlauf: geweckt nach **860 ms**. Beide Male Bild nach 4-5,5 s, DSP im 1. Versuch, Tastendrücke aus dem Einschlafen verworfen. **Ein Abbruch entsteht am HY310 so nicht:** der Druck landet bei crust, das sofort weckt; `pm_wakeup_irq` leer, `fail` 0. U2 bleibt die Absicherung für andere Weck-Interrupts |
| B3 | 2 s 440 Hz vom ThinkPad über HDMI, Amplitude 3000, Box auf Lautstärke 30 | Marco: gehört; Box: `audio source present=1 rate=48000`, Pegel 74/74; danach zurückgestellt |
| B4 | Marco sieht das neue Panel an | "sieht deutlich besser aus", aber Wortwahl zu weit vom Beamer (§3) |
| B5 | `h713-arisc set vendor` + Neustart; Aus; Taste; `set crust` + Neustart; Aus über crust; Taste | vendor: "module option", kein Standby, Aus = "PSCI: power off, resetting into the boot gate", Gate wartet auf die Taste. crust: "PSCI: power off, crust takes the rails", danach **"R_WDOG found armed (MODE 0x1 STA 0x1), fed and stopped"** (der neue Text, zurückgelesen), Kernel: "as meant" |

## 2 Nach `main`

Dienste (U2, U3, U5, U6 + Testgerüst), Kernel `0263`-`0267` + `CONFIG_PM_DEBUG` + Patch-Texte, `h713-arisc`/`--arisc`/Installer-Zeile
(je Einzel-Commit, `main` 6a73813); TF-A `sun50i-h713` auf 287dca2fe (lokal vorgespult), Spiegel `tfa-h713/` 32 Patches, Baum der Serie
= Baum des Kopfs (`3e52076b`), Zeiger in `main` (eaaa7b4); das Panel (09026a7, §3). `release/tor.sh --tests` grün, 73 Panel-Tests grün.

## 3 Das Panel

PR 1 aus `well0nez/h713-panel-dev` (Seite neu, Server = die verworfene Fassung vom 11.10.), Unit mit `/etc/hosts` und den h713-logs-Pfaden
(Marco: die zwei Zeilen übernehmen; Werkzeug-Doku und `PRODUCT.md` weg). Ein Sonnet-Agent (`arbeit/panel-wording-20261012/`) setzte 35
Beamer-Begriffe zurück (Keystone, Projection mode, Autofocus, Focus, Edge blend, …); nachgeprüft: alle 292 Attribute und 32 Befehle gleich,
nur Texte. Marco am Gerät fand dann: **die Off..High-Reihen (Rauschunterdrückung usw.) bleiben nicht aktiv** - Ursache: `ctl set` nimmt
`tnr`/`snr`/`dci`/`black`, `ctl list` druckt `temporal_noise_reduction`/…; der Server suchte den Wert unter dem Kurznamen, die Seite zeigte
immer Off, und markierte eine gedrückte Stufe erst beim Neuladen. Der Test hatte `ctl list` mit Kurznamen nachgebildet. Behoben (027c262):
Zuordnung im Server, Markierung sofort, Test mit der Ausgabe des Geräts. Marco: "passt". Gesetzt hat das Panel die Werte immer.

## 4 Handoff (13.10.2026, nachts)

**`main`:** dieser Eintrag + TODO, **nicht gepusht** (seit 234282c alles; Reihenfolge `TODO.md` §1).

**HY310** (`.131`): `runde5x1` + Schnell-Deploys `h713-arisc` (1b54a21) und Panel (`main` 09026a7); Sicherungen `/root/sicherung-arisc/`,
`/root/sicherung-panel-wording/`. `/etc/modprobe.d/h713-arisc.conf` = `firmware=crust` (gleichwertig zum Gerätebaum). Warp an; Rauschunterdrückung
tnr/snr auf High (Test, zurück mit dem Panel). Testmaterial `/root`.

**Nächstes:** 7.19 Doku-Runde (Panel-Seiten, `standby.md`, `FLASHING.md`) -> 1.1a Release-Neubau -> 1.6/1.7a/1.7 nur mit Marcos Ja je Push
(crust-Fork auf GitHub anlegen, 5.15 dabei). Nach dem Release: 5.17, die Reste von 5.14.
