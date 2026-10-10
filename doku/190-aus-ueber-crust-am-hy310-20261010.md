# 190 - "Aus" über crust am HY310 gemessen: Selbstwecken, Power-Taste und IR-Fernbedienung (10.10.2026)

**Kurz:** Das Aus über crust aus `doku/188` läuft auf dem HY310 wie auf dem HY300PRO-G-EU. Drei Läufe per FEL, die
Bootkette in der eMMC blieb unberührt: Der Testbau weckt sich nach 60062 ms selbst, die Power-Taste weckt nach 111 s, die
IR-Fernbedienung nach 5 s. Jedes Mal steht im Record des nächsten Starts Phase 7 (`poweroff`), Schritt `0x613`, ein
R_WDOG-Reset und GP5 `RUN1`, und U-Boots Gate bootet durch. Darum hat jetzt auch die Release-Konfiguration des HY310
`CONFIG_H713_POWER_OFF` (crust `h713` `54e4a08`, Spiegel `crust-h713/` 0088). **Die Leistung im Aus ist am HY310 nicht
gemessen** (Marco: baugleich mit dem G-EU, dort 0,3 W). Paket `arbeit/aus-pl6-20261010/` (BERICHT §8, Skripte, Läufe
`test/laeufe/hy1` bis `hy3` mit UART-Mitschnitt und Kernelzeilen). Ablauf nach `doku/189` §3, TODO 2.32.

## 1 Aufbau

- **HY310** mit `r2test4` und dem Schnell-Deploy `0245` in der eMMC, `h713_gate=1`. Für jeden Lauf lädt `h713-fel` die Box
  ins FEL, `sunxi-fel` startet U-Boot, BL31 und crust aus dem RAM; Linux kommt aus der eMMC.
- **crust-Datei:** Der Kernel-Treiber ersetzt beim Start ein laufendes crust, das nicht der Datei in `/lib/firmware`
  entspricht (0192). Darum lag für die Läufe das jeweilige Test-crust unter `/lib/firmware/hy310-crust.bin` (Marcos
  Freigabe), das Original gesichert auf der Box (md5 `586873fe...`) und am Ende zurückgelegt.
- **UART** nur lesend über den ESP32-Proxy des HY310 (Lese-Port), nichts gesendet. A-auf-A-Kabel steckte in allen Läufen,
  kein Wattmeter.

| Bau | Quelle | sha256 (Anfang) |
|---|---|---|
| BL31 (beide) | TF-A `sun50i-h713` `1dd037344`, `H713_STANDBY=1` | `9f653738` |
| Testbau | crust `d8a8d56` mit `h713_hy310_sr_off_test_defconfig` (weckt sich nach 60 s, `H713_TEST`) | scp `d667393c`, Abbild `48d5c226` |
| Tasten-Fassung | crust `1738a09` = `d8a8d56` + `CONFIG_H713_POWER_OFF=y` in `h713_hy310_sr_defconfig` (Baum gleich `54e4a08`) | scp `f1d96705`, Abbild `ae36c4bd` |

Gebaut mit `bau.sh` im Container `h713-build`: Warnungen BL31 0, crust 0, U-Boot 142 (unverändert gegenüber dem HDCP-Paket).
Vor jedem Lauf bestätigt: BUILD2 `0x01001318` (Bit 24, Aus), BL31-Zeile `v2.15.0(release):1dd037344`, crust Vertrag v5.

## 2 Die Läufe (10.10.2026, 20:02 bis 20:11)

| Lauf | Bau | Wecken | Zeit im Aus (Record) | wieder per ssh | Ergebnis |
|---|---|---|---|---|---|
| hy1 | Testbau | von selbst (Timer) | 60062 ms | nach 91 s | bestanden |
| hy2 | Tasten-Fassung | Power-Taste am Gerät (Marco) | 111017 ms | nach 147 s | bestanden |
| hy3 | Tasten-Fassung | Power auf der IR-Fernbedienung (Marco, kurz nach dem Dunkelwerden) | 4973 ms | nach 36 s | bestanden |

Die Kernelzeile des Starts nach hy1, wörtlich:

```
sun50i-h713-arisc 100000.arisc: previous run (record of TF-A): crust in phase ?, step 0x613, cause 0 (none), err 0x0
(detail 0xfff00000, data 0x00000034), 60062 ms in the phase, reset path 0x0, exception 0x00000000, cycle 0; TF-A word
0x00000000, R_WDOG 0x00010001, GP5 0x52554e31
```

"phase ?" ist Phase 7: der Kernel in `r2test4` kennt sie noch nicht (`0250` nennt sie "poweroff"). Detail `0xfff00000` mit
Daten `0x34` ist die Spur des Testbaus: die Schienen fielen 52 ms nach dem Auftrag, wie am G-EU. hy2 und hy3 zeigen dieselbe
Zeile ohne Spur, nur mit 111017 und 4973 ms. Der UART-Mitschnitt zeigt in allen drei Läufen dieselbe Folge: `PSCI: power off,
crust takes the rails`, dann im nächsten Start das BL31 der eMMC mit `R_WDOG found armed (MODE 0x1 STA 0x1), fed and
stopped`, `crust before this boot: ... state 0x7 step 0x613`, `gate: warm start (GP5 52554e31), booting`.

## 3 Was nicht gemessen ist

- **Die Leistung im Aus.** Marco hat auf das Wattmeter verzichtet (baugleich mit dem G-EU). Am G-EU: 0,3 W (`doku/188`).
- **Ein Lauf ohne A-auf-A-Kabel.** Alle drei Läufe mit gestecktem Kabel; am G-EU weckte die Fernbedienung auch ohne Kabel (geu5).
- **Das installierte System.** Der HY310 läuft weiter `r2test4` aus der eMMC; dessen BL31 kennt den Auftrag an crust nicht,
  ein `poweroff` endet dort weiter im Gate (2,9 W, `doku/181`), bis ein Abbild aus `main` installiert ist (TODO 1.1a).

## 4 Beobachtung: das Netzteil fiept auch im Aus

Marco während hy2: das Fiepen des Netzteils bleibt im Aus über crust. Im Standby fiept es leise (`doku/181`). Ob es mit
Stock-Android aus genauso fiept, ist nicht verglichen - TODO 2.42.

## 5 Zurück und Integration

- Original-crust-Datei zurück (md5 geprüft), `systemctl reboot`: Start aus der eMMC, das laufende crust (build `0x05004e5c`)
  entspricht der Datei, kein Nachladen, `systemctl is-system-running` = `running`.
- crust `h713` von `d8a8d56` auf `54e4a08` (0088, Baum gleich dem gemessenen `1738a09`), Spiegel `crust-h713/` 88 Patches, auf die
  Basis angewendet Baum `4ac41f6b88ee` = Fork-Kopf. `docs/hardware.md`, `docs/uboot/power-gate.md`, `docs/subsystems/standby.md`,
  `docs/tools/h713-power.md` nachgezogen; TODO 2.32 erledigt, 2.42 neu. Nichts gepusht.
- Nächster Schritt laut `doku/189` §4: das Gespräch zum Kaltstart-Gate (2.39) - erst reden, dann Code.
