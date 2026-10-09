# 180 - HDCP-Härtung eingebaut und per FEL gemessen: Übergabe ohne Adresse, einmal pro Boot, Watchdog über den Treiber (09.10.2026, 20:30)

**Kurz:** Das Paket vom 07.10. (`doku/161`, TODO 6.1/6.2/6.5/6.6/6.9) ist auf die heutigen Köpfe gesetzt, gebaut, am
HY310 per FEL gemessen und in Forks, Spiegel und `main` übernommen. Marco: "mach es ready und dann testen und dann
main". Die Firmware lief nur im RAM; die eMMC der Box trägt es mit dem nächsten Abbild (1.1a). Paket
`arbeit/hdcp-haertung-20261009/`, Zweig `versuch/hdcp-haertung`.

## 1 Was eingebaut ist

| Ort | Commit | Inhalt |
|---|---|---|
| TF-A `0028` | `4f7e073c7` | BL32-Gerüst raus (6.9); der Boot-Watchdog bleibt als `H713_BOOT_WATCHDOG`, 12 s wie bisher. Neu aufgesetzt: die Standby-Commits hatten `sunxi_bl31_setup.c` und `platform.mk` geändert, ihre `SUNXI_SYSTEM_SUSPEND`-Quellen bleiben |
| TF-A `0029` | `e2298a919` | der Schlüssel-Dienst nimmt keine Adresse mehr: BL31 nennt die Ablage, prüft die Struktur beider gespeicherter Kopien selbst und schreibt die Senke einmal pro Boot (6.1, 6.2); ohne Konflikt übernommen |
| TF-A `0030` | `5a7806892` | Kommentar: wo der Reset eines abgelehnten Standbys endet (zu `doku/179`) |
| U-Boot `0097` | `74ae0367abf` | eigene Zeile für "STBY" im Gate (`doku/179`) |
| U-Boot `0098`-`0100` | `7b1ea388da0d` | `h713_hdcp14_wait` weg (6.6); Ablage dort, wo EL3 sagt, eine Schreibung pro Boot; Wächter um die Übergabe über den Watchdog-Treiber statt fester Register (6.5) |
| Repo | `a818eb0`, `1fa1eb0` | `check-hdcp-artifacts.sh` fragt nach dem adressfreien Dienst; der Bau verweigert ein BL31 ohne ihn (an das neue `uboot-build.sh` angepasst) |

Die Commit-Texte nennen jetzt die Messung; die Bäume sind dieselben wie gemessen (geprüft per Baum-Hash). Spiegel
`uboot-h713/` 100 Patches (Baum `9ed108eda593`), `tfa-h713/` 30 Patches (Baum `b60113cc5ddd`), beide gegen die Köpfe geprüft.

## 2 Bau

BL31 mit `SUNXI_SYSTEM_SUSPEND=1`, crust `ecf2ddc` (`scp.bin` bitgleich mit dem der Box, `892a3b06`), U-Boot hy310 +
release mit SCP; die Befehle von `build-all.sh` Schritte 1, 1b und 2 (`bau.sh`). BL31 ohne Warnung, U-Boot dieselben 142
Warnungen wie bisher. `check-hdcp-artifacts.sh`: "green". Im BL31 "key set from the stage", kein "BL32 at"; im U-Boot kein
`h713_hdcp14_wait`. Nach dem Umschreiben der Commit-Texte neu gebaut: BL31 weicht in 9 Bytes ab (der Commit-Name im Banner);
der gemessene Stand baut bitgleich nach, der Bau ist reproduzierbar.

## 3 Gemessen (FEL, UART nur gelesen bis auf T3, ThinkPad i915 an HDMI-2)

| Stufe | Ergebnis |
|---|---|
| T0 | "BL31: watchdog armed (12 s)", Banner `fce031958`, kein "BL32 at", "WDT: Not starting watchdog@2051000", 4 CPUs, kein Reset |
| T1 `h713_hdcp14_wipe=1` | "WDT: Started watchdog@2051000 without servicing (6s timeout)", "H713 SiP: zeros into the sink: 0x0", Senke `0x93=0x41`; Quelle Undesired -> Desired, nach 2/5/10/20 s weiter **Desired** |
| T2 Standard, direkt danach | "H713 SiP: key set from the stage into the sink: 0x0", "1.4 key set handed to the receiver", Senke `0x93=0x45`; Quelle **Enabled nach 2 s**; kein "staged copy"-Fehler, kein Reset nach dem Wächter |
| T3 Prompt, zweimal `h713_hdcp14` | erste Übergabe wie T2; zweite: "the key sink is closed for this boot"; die des Bootablaufs danach ebenso |
| T4 `h713_hdcp14=0` | "skipped on request (h713_hdcp14=0)", "key sink closed for this boot, nothing written" |

T1 ging ein normaler Neustart voraus (Box länger als 10 min an, wie in den FEL-Läufen vom 08.10.); dessen altes U-Boot
nullte die Senke ebenfalls, über den alten Weg. Nicht gelaufen: T5 (fremder Watchdog). Das Environment der Box ist danach
wie vorher (`h713_hdcp14`, `h713_hdcp14_wipe` leer, `h713_gate=1`).

## 4 Was bleibt

- Die eMMC der Box hat weiter das alte U-Boot und BL31; das neue kommt mit dem Abbild 1.1a.
- Push der Forks nur mit Marcos Ja (TODO 1.6): U-Boot `h713-hy310` +11, TF-A `sun50i-h713` +25, crust neu.
