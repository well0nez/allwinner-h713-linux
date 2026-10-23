# 219 Die Fernbedienung unter der Hersteller-ARISC, Einschalten aus dem Gate, Release-Bau v0.97-beta und der Merge nach main - Protokoll

Datum: 22.-23.10.2026. Geräte HY310 und HY300PRO-G-EU, beide mit der Hersteller-ARISC (`doku/218`). Marco an Fernbedienung, Box und
Wand, die Aufsicht am PC. Pakete und Belege (lokal): `arbeit/medien/ir-arisc/`, `ir-fix/`, `crust-audit/`, `gate-ir/` (UART-Mitschnitte in
`laeufe/r2-hy310-*`), `test11-ir-nachruest/`, `R-rel2/`, Laufprotokoll `arbeit/medien/AUFSICHT.md`. TODO 2.139, 2.140, 2.65, 2.134, 2.137, 1.0.

## 1 Ausgang

Nach der Rückkehr zur Hersteller-ARISC (`doku/218` §3) reagierte der HY300PRO-G-EU unter Linux nicht mehr auf die IR-Fernbedienung:
`sunxi-ir` zählte seit dem Start einen einzigen Interrupt. Ein erster Befund am 22.10. gegen 18:30 ist **unbelegt**: die Mitschnitte liefen,
ohne dass eine Taste gedrückt wurde. Belegt ist der Lauf gegen 19:15 mit gesperrtem Bluetooth: Tasten gedrückt, keine Reaktion.

## 2 Ursache und Fix

| Was | Ergebnis |
|---|---|
| Ursache (Mythos, Paket ir-arisc; am G-EU gelesen) | Die Hersteller-ARISC schreibt beim Start `PL_CFG1` (R_PIO `0x07022004`) = `0x222222ff`. Damit ist PL9 (`s_cir`) aus. crust tat das nicht. |
| Gegenprobe | `sunxi-ir` unbind/bind stellt `0x2222223f` her. Danach 224 Interrupts, alle Tasten der HY310-Fernbedienung per IR dekodiert (NEC-Adresse `0x02`). |
| Kernel `0328` | setzt den Pin nach dem Bind der ARISC wieder (pinctrl sleep -> default). `dmesg`: `PL9 applied again after the ARISC start`. `PL_CFG1` `0x2222223f` nach jedem Start, G-EU 22.10. und 23.10., HY310 23.10. |
| Kernel `0329` | Tastentabelle der originalen HY300-Fernbedienung, NEC-Adresse `0x00`. Zuordnung mit Marco am 22.10.: Power `0x14`, OK `0x07`, oben `0x03`, unten `0x02`, links `0x0e`, rechts `0x1a`, Home `0x48`, Zurück `0x5c`, Menü `0x13`, lauter `0x0b`, leiser `0x58`, Stumm `0x01`, Maus `0x82`, Bildschirm `0x93`, Doppelpfeil `0x98`. |
| Tastentest originale Fernbedienung, G-EU 22.10. (Marco) | OK, Pfeile, Menü, lauter/leiser, Stumm, Maus, Bildschirm/Doppelpfeil (Fokus; der G-EU hat keinen Motor), Power-Countdown mit Abbruch über Zurück, Home öffnet den Launcher - alle erkannt. |
| HY310-Fernbedienung per IR (Bluetooth gesperrt) | Zuerst 0 IR-Interrupts: die Fernbedienung hing an ihrem Bluetooth-Zustand. Nach einem Batteriewechsel alle Tasten richtig (Hoch `0x209`, Runter `0x201`, Links `0x20a`, Rechts `0x208`, OK `0x20b`, Home `0x20d`, Zurück `0x21f`, lauter `0x215`, leiser `0x211`, Stumm `0x202`). |
| Tabellen im laufenden Kernel (`EVIOCGKEYCODE_V2`), beide Boxen 23.10. | HY300 `0x0014` -> `KEY_POWER`, `0x0007` -> `KEY_ENTER`; HY310 `0x021d` -> `KEY_POWER`, `0x020b` -> `KEY_ENTER`. |

**Was wegen crust sonst wegfiel** (Mythos, Paket crust-audit, 30 Stellen geprüft): unter der Hersteller-ARISC fehlten wirklich nur
(1) der IR-Pin (oben), (2) das Einschalten per Fernbedienung aus dem Aus, das bisher nur crust konnte (§3), (3) veraltete Doku-Zeilen
(gehen in die Doku-Runde, TODO 1.0 (5)). Alles andere ist sauber abgeschaltet.

## 3 Einschalten per Fernbedienung aus dem Gate (U-Boot `0102`)

Das U-Boot (Fork `h713-hy310`, Kopf `daa35622b0bf`, Spiegel `uboot-h713/` mit 102 Patches) dekodiert im Power-On-Gate NEC. Die
Power-Taste startet: HY310-Fernbedienung Adresse `0x02` Befehl `0x1d`, originale HY300-Fernbedienung `0x00`/`0x14`. Andere Tasten starten
nichts. Läuft crust auf der ARISC, liest das Gate die Fernbedienung absichtlich nicht (crust weckt dann selbst). Host-Test 44/44.

| Lauf | Ergebnis |
|---|---|
| FEL, G-EU 22.10. (nichts auf der eMMC) | Power an der originalen und an der HY310-Fernbedienung startet; die Taste am Gerät startet wie bisher; Home/OK im Gate ohne Wirkung (Marco). Register nachher = vorher. Gate mit IR-Dekoder still (Marcos Gehör). |
| eMMC, G-EU 22.10. 23:36 und 23:38 (nach der Installation) | `poweroff` -> Gate; Power an der originalen, dann an der HY310-Fernbedienung startet, je neue `boot_id` (Marcos Auge; der UART-Proxy des G-EU war nicht erreichbar). |
| eMMC, HY310 23.10. ~09:20 (nach der Installation, UART mitgelesen) | `gate: the remote's power key starts the board too`; originale Fernbedienung: `gate: remote power key (NEC 0014), booting`; HY310-Fernbedienung: `(NEC 021d)`; Kernelstart je ~3,6 s danach. |

## 4 Nachrüstsatz für den HY300 (Pro) aus Issue #1

Dessen Testabbild test11 läuft mit der Hersteller-ARISC (kein crust für sein Board), also mit demselben Pin-Fehler. Ein Nachrüstsatz im
Userspace (Dienst: nach dem Bind der ARISC `sunxi-ir` neu binden, dann die Tabelle der originalen Fernbedienung per `EVIOCSKEYCODE_V2`)
wurde am G-EU im Zustand des Testers geprüft (v0.97-beta-Kernel ohne `0328`/`0329`): `PL_CFG1` `0x222222ff` -> `0x2222223f`, 15 Tasten geladen,
Tastentest mit der originalen Fernbedienung bestanden (Marco). Dem Tester bereitgestellt; seine Rückmeldung steht aus (TODO 2.134). Der
Nachrüstsatz liegt nicht im Repository; mit dem nächsten Abbild ersetzen ihn `0328`/`0329`.

## 5 Release-Bau v0.97-beta und Installation an beiden Boxen

| Was | Ergebnis |
|---|---|
| Bau (22.10. abends, `R-rel2`) | aus `medien` `8da300c2` (ir-fix + gate-ir) von vorn, HY310 und G-EU, `--profile media,desktop`, ohne `--standby`: beide rc 0, Prüfschritt grün. |
| Installation G-EU 22.10. ~23:20, HY310 23.10. ~09:15 | `h713-fel` -> FEL -> `h713-install --small --keep-env`: Secure Storage unverändert (Byte für Byte gegen den Abzug), HDCP-1.4-Satz vorhanden; Einstellungen, Bluetooth-Bund und Hostschlüssel zurückgespielt. |
| Nach dem Start | Kernel-FIT und `aic8800_fdrv` gleich dem Bau, WLAN verbunden, Hersteller-ARISC, kein Standby (`CanSuspend` "no"), Aus = Gate, keine fehlgeschlagenen Units. |
| Installer-Fund (TODO 2.137) | `--keep-env` übernahm `h713_gate=0` aus der Umgebung im Abzug statt vom Gerät - an beiden Boxen. Danach von Hand `fw_setenv h713_gate 1`. |

Kein Volltest nach der Neuinstallation (Marco: Abnahme und Augentests liefen am 22.10. auf dem ersten v0.97-beta-Bau); geprüft wurde, was
sich geändert hatte.

## 6 Merge nach main

23.10.2026: `medien` in `main` (Merge `4b771442`), in einer Kopie. `main` hatte seit der Abzweigung nur README (Disclaimer) und TODO
geändert; Konflikte nur in `TODO.md`. `release/tor.sh --tests` (412 Tests) und `boards/check.sh` grün. Nicht gepusht.

## 7 Nicht gemessen

Watt im Gate mit dem IR-Dekoder. Am HY310 das Einschalten per FEL-U-Boot und eine Nicht-Power-Taste im Gate (gemessen nur am G-EU).
Ob der Nachrüstsatz beim Tester wirkt.
