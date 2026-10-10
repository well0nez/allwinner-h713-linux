# 191 - Kaltstart-Gate über crust: nach dem Einstecken wartet crust statt U-Boot, 0,3-0,6 W, die Fernbedienung weckt (10.10.2026)

**Kurz:** Seit `doku/188` endet ein `poweroff` aus Linux in crusts Aus (0,3 W). Nach dem Einstecken wartete U-Boots Gate aber
weiter selbst, mit einem ARM-Kern in einer Schleife: 2,4 W am G-EU, 2,9 W am HY310 (`doku/181`). Jetzt übergibt das Gate bei
einem echten Kaltstart das Warten an crust, auf demselben Weg wie Linux' `poweroff` (PSCI `SYSTEM_OFF`). Eine Datei in U-Boot,
`board/sunxi/board.c` (Fork-Patch `0101`); TF-A und crust bleiben, wie sie seit `doku/188`/`doku/190` sind. Gemessen per FEL am
HY300PRO-G-EU mit nachgestelltem Kaltstart: dunkel, 0,3-0,6 W, die IR-Fernbedienung weckt. Auf Marcos Entscheidung in `main`
**vor** dem echten Netzstecker-Test und vor einer Messung am HY310 - beides kommt mit dem Release-Neubau (TODO 1.1a). Paket
`arbeit/kaltstart-gate-20261010/` (BERICHT, Bauskript, Patch).

## 1 Das Gespräch (Plan `doku/189` §4.4)

| Frage | Marco |
|---|---|
| a) nur `board.c` im U-Boot-Fork, sonst bleibt das Gate, wie es ist | ja ("mach das erstmal") |
| b) das Warten nach dem Einstecken übernimmt crust, 0,3 W statt 2,4 W | ja |
| c) die IR-Fernbedienung darf auch nach dem Einstecken wecken | ja |
| d) ein missglückter Standby (GP5 `STBY`) | bleibt in der alten Schleife (mein Vorschlag, Marco: einverstanden) - ein Aus über crust überschriebe crusts Protokoll des Fehlers, das der nächste Start meldet; es zu retten bräuchte TF-A dazu |
| e) wie getestet wird | erst bauen, dann Bescheid; "klug, sinnvoll, ohne Hackymacky" |

## 2 Was U-Boot jetzt tut

Im Gate, nach der 3-s-Prüfung der Taste und vor der Warteschleife: ist GP5 `0` (Netz-Ein) und meldet crust auf seiner
Vertragsseite (SRAM A2 `0x00123800`) MAGIC `"H713"`, Vertrag >= 5 und BUILD2 Bit 24, dann Zeile `gate: crust holds the board off,
the power key or the remote wakes it` und `psci_system_off()`. BL31 schreibt `GATE`, prüft wie bei Linux Herzschlag und Phase,
crust zieht PL6. Taste oder IR wecken: `RUN1`, R_WDOG-Reset, das Gate bootet durch.

| GP5 / Lage | vorher | jetzt |
|---|---|---|
| `0`, crust mit Aus | Schleife | crust hält aus |
| `0`, kein crust (Hersteller-ARISC) oder crust ohne Aus | Schleife | Schleife, Zeile `gate: no crust on the ARISC` bzw. `... cannot hold the board off`, kein Reset |
| `0`, crust mit Aus, aber hängt | Schleife | BL31 lehnt ab (Ereignis 5), **ein** Reset mit `GATE`, dann Schleife |
| `GATE`, `STBY`, unbekanntes Wort | Schleife | Schleife (unbekannt jetzt mit eigener Zeile statt "cold start") |
| `RUN1`, `h713_gate=0`, Taste beim Einstecken 3 s | bootet | bootet, unverändert, kommt vorher |

Höchstens ein `SYSTEM_OFF` je Einstecken, also keine Neustart-Schleife. Notausgang, falls crusts Aus je nicht weckt: die Taste
beim Einstecken halten. Installer, Netboot, FEL-MMC und Host-Bauten haben kein Gate und sind unberührt (Installer-Rolle mit der
Änderung gebaut: keine Warnung in `board.c`).

## 3 Bau

`arbeit/kaltstart-gate-20261010/bau.sh hy310|geu` im Container `h713-build`, von vorn: BL31 `1dd037344` (`H713_STANDBY=1`), crust
`h713` `54e4a08` mit der Release-Konfiguration des Boards (`H713_POWER_OFF`), U-Boot release aus dem Zweig. Warnungen BL31 0,
crust 0, U-Boot 141/142 - dieselben Arten wie ohne Änderung, keine in `board.c`. Ein zweiter Bau aus dem Commit gab bytegleiche
Abbilder (G-EU `35b0a62c...`, HY310 `64b06e33...`).

## 4 Lauf k1 (HY300PRO-G-EU, 21:22, FEL, ohne UART - der ESP war nicht erreichbar)

GP5 aus Linux von `RUN1` auf `0` gesetzt (Kaltstart nachgestellt), `h713-fel --yes`, FEL-Abbild geladen 21:22:19. Danach kein Netz.
Marco: dunkel, **0,3-0,6 W** mit gestecktem A-A-Kabel (die Schleife: 2,1-2,4 W), Wecken mit der **IR-Fernbedienung**. Start aus der
eMMC, der Kernel meldet:

```
previous run (record of TF-A): crust in phase poweroff, step 0x613, cause 0 (none), err 0x0 (detail 0x00000000, data 0x00000000),
97165 ms in the phase, reset path 0x0, exception 0x00000000, cycle 0; TF-A word 0x00000000, R_WDOG 0x00010001, GP5 0x52554e31
```

Die U-Boot-Zeile selbst ist ohne UART nicht gesehen; Beleg sind Protokoll (Phase poweroff, 97 s, ohne vorheriges `poweroff` aus
Linux) und Wattmeter zusammen. **Bestanden.**

**Nicht gemessen:** der echte Netzstecker (braucht das neue U-Boot in der eMMC), der HY310 mit diesem U-Boot, das Wecken mit der
Taste (Marco: wie IR; aus crusts Aus belegt in `doku/188` geu7 und `doku/190` hy2), der Notausgang, crust ohne Aus.

## 5 In der Linie

U-Boot `h713-hy310` auf `61ea018` (`0101`), Spiegel `uboot-h713/` 101 Patches, Baum `595b6941482e` am Fork-Kopf geprüft; `main`:
Zeiger, `docs/uboot/power-gate.md` (neuer Abschnitt "A cold start through crust"), `docs/subsystems/standby.md`, `docs/hardware.md`,
`docs/known-issues.md`; TODO 2.39 erledigt. Nichts gepusht.

## 6 Nebenbei

Dieselbe IR-Taste, die den G-EU weckte, ließ den laufenden HY310 daneben an - er hat unter Linux keine IR-Belegung (TODO 2.35).
Kommt die Belegung, hören beide Boxen denselben Code: ein Druck würde die eine wecken und die andere ausschalten.
