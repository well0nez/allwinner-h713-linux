# 178 - HDCP-Härtungspaket: Entscheidungen für den Release-Neubau, Korrektur zu 6.5 (09.10.2026, abends)

**Kurz:** Marco hat über das Paket aus `doku/161` entschieden, nachdem `doku/175` es gegen die heutigen Köpfe geprüft
hatte: Das Paket kommt ganz in den Release-Neubau 1.1a, 6.5 eingeschlossen. Die beiden TF-A-Patches werden vorher auf
`175c6948f` neu aufgesetzt. `doku/175` §4 hatte 6.5 falsch eingeschätzt; die Korrektur steht unten in §2. Nichts gebaut,
nichts am Gerät.

## 1 Entscheidungen (Marco, 09.10.2026)

| Punkt | Entscheidung |
|---|---|
| TF-A `0001` (BL32-Gerüst raus, Boot-Watchdog bleibt), `0002` (Senke ohne Adresse, einmal pro Boot) | auf `175c6948f` neu aufsetzen; sie kollidieren mit den 21 Standby-Commits (`doku/175` §2) |
| 6.5 (Watchdog um die Übergabe über den U-Boot-Treiber, keine festen Register mehr) | mitnehmen |
| wann | alles zusammen mit 1.1a, in einer Kopie, per FEL gemessen (Plan `arbeit/hdcp-haertung-20261007/BERICHT.md` §8) |

## 2 Korrektur zu `doku/175` §4 (6.5)

Dort steht: U-Boot 0003 starte den Watchdog in U-Boot mit 6 s, und mit den neuen Regeln könne ein langsamer Weg bis Linux
die Box zurücksetzen. Das stimmt nicht. Nachgelesen im Code:

- Den 6-s-Wächter gibt es schon heute (U-Boot `87b2a44`, `arch/arm/mach-sunxi/h713_hdcp14.c`, `wdt_guard_on()`/
  `wdt_guard_off()`). Er wird nur um die Übergabe des HDCP-1.4-Schlüssels an die Senke geschaltet, die Mikrosekunden
  dauert, und direkt danach wieder ab. Läuft der Watchdog schon, rührt er ihn nicht an.
- Den Weg bis Linux sichert der 12-s-Watchdog, den BL31 bei jedem Boot schärft (`sunxi_bl31_setup.c`,
  `H713_WDOG_BRINGUP`); U-Boots sunxi-Watchdog-Treiber hält ihn an, wenn er das Gerät bindet. Daran ändert 6.5 nichts.
- U-Boot `0003` macht dasselbe über die WDT-uclass (`wdt_start(dev, 6000)`, `wdt_stop(dev)`) statt mit festen Adressen,
  eigenem Schlüssel und eigener Intervallkodierung. Danach stehen im Objekt weder `0x0205101x` noch `0x16aa` noch
  `0x48a00000` (`arbeit/hdcp-haertung-20261007/BERICHT.md` §4). Neu ist eine Log-Zeile je Übergabe:
  `WDT:   Started watchdog@2051000 without servicing  (6s timeout)`.

6.5 ist also weder überholt noch ein Risiko für den Start; es ist Aufräumen im Sinn der Härtung, mit gleichem Verhalten.
Nicht gemessen: der Patch lief noch auf keinem Gerät.
