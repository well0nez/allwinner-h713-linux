# 218 Das Summen des Netzteils mit crust, die Messreihe mit Mikrofon und die Entscheidung für die Hersteller-ARISC - Protokoll

Datum: 20.-22.10.2026. Gerät HY300PRO-G-EU (Abbild geu3, `medien`), Marco am Netzteil bzw. ein USB-Mikrofon am Host wenige cm neben dem
Netzteil. Pakete und Belege (lokal): `arbeit/medien/standby-summen/` (HYPOTHESEN, TESTPLAN, T5c, `mythos-analyse/`, `fix-bericht/`,
`laeufe/`), `arbeit/medien/arisc-default/`, `arbeit/medien/AUFSICHT.md`. TODO 2.42, 1.0 (0).

## 1 Ausgang

Mit crust (unserer ARISC-Firmware) summt bzw. fiept das Steckernetzteil hörbar im Standby und im Aus über crust; im U-Boot-Gate ist es
still. WLAN und HDMI sind es nicht (20.10.). Marco: "das können wir so nicht ausliefern".

## 2 Gemessen

| Was | Ergebnis |
|---|---|
| Mikrofon-Referenzen (21.10., Release-crust, Band 2-8 kHz) | Stille (Stecker gezogen) -66,0 dBFS; Standby -63,8 mit Tönen 1,6/3,5 kHz; Aus -61,8 mit 2,4/5,9/7,4 kHz; Gate mit Hersteller-ARISC -67,7, Netzteil taktet ~20,5 kHz, Marco "absolut still" |
| T5c (CPUS auf Quelle 1 zwischen den Polls) | stoppte sich im ersten Standby selbst; Quelle 1 läuft nicht mit der angenommenen Rate (Mythos: ~23,7-kHz-RC) |
| summen-fix, Nacht 21./22.10. (Blöcke C2-I, Kontrollen im Wechsel) | ARISC-Takt (IOSC/1, IOSC/256, Duty 0-100 %), LEDs, vdd-cpu-PWM, PLL-LDO, Quarz-Bit: keine Änderung der Töne; Verstärker-/WLAN-Enable (PL2/PM1, im Schlaf high) verschieben nur das Muster; Tiefschlaf-Standby (PLLs aus) lauter (-60,6); **Standby ohne DRAM-Self-Refresh still** im Mikrofon (-67,4, Netzteil im Dauerbetrieb 20,7 kHz) |
| Wattmeter (22.10. morgens, Marco) | Release-Standby **2,0 W**, Fiepen; Standby ohne Self-Refresh **2,4 W**, ebenfalls Fiepen (für Marcos Ohr; das Mikrofon zeigte darunter nur die Linie um 20,69 kHz - Widerspruch nicht geklärt) |

Deutung (Mythos, gestützt auf die Spektren): ein Netzteil im Leichtlastbetrieb, dessen Pulsmuster mit der kleinen Dauerlast in den
Hörbereich wandert; still erst im Dauerbetrieb (Gate 2,9 W). Die Hersteller-ARISC schläft auf einem 16-MHz-RC und schaltet PLL-LDO und
PLLs ab - nachgebaut änderte das am Ton nichts.

## 3 Entscheidung (Marco, 22.10.2026)

"crust laden wir mit hoch, bleibt experimental - genau wegen dieser Probleme. Aber wir gehen fest zur ARISC zurück und kein Standby."
Umgesetzt im Paket arisc-default (`medien` 258c9b5f, Mythos go): Abbild ohne `--standby` lädt die Hersteller-ARISC
(`/etc/modprobe.d/h713-arisc.conf`), das U-Boot-FIT trägt ohne `--standby` kein crust mehr (sonst endete jedes Einstecken über U-Boot
`0101` im summenden crust-Aus), Kernel `0327` lädt das DT-crust, wenn der Abzug keine `h713-arisc.bin` hat; `h713-arisc set crust` bleibt
der Weg zum Experiment. Am G-EU gemessen (G1-G6): Bild und Bildrate wie unter crust, kein Standby angeboten, Umschalter in beide
Richtungen, fehlende Datei hängt nichts. Aus dem Gate startet die Taste am Gerät, nicht die Fernbedienung. `h713_gate` auf den Boxen
wieder 1 (G-EU 22.10. gesetzt).

## 4 Nicht gemessen

Das Gate-Aus mit dem neuen Release-Abbild (braucht die Taste am Gerät); der HY310 (anderes Netzteil); der Widerspruch Mikrofon/Ohr beim
Standby ohne Self-Refresh.
