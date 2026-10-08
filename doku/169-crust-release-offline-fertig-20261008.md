# 169 - crust und die Standby-Kette in Release-Qualität: offline fertig, nichts gemessen (08.10.2026, 05:45)

**Kurz:** Der gesamte Standby-Code (crust, TF-A, Kernel, U-Boot, Einbindung) wurde auf Release-Qualität durchgesehen,
neu entworfen, umgesetzt, gegengeprüft und nachgearbeitet. Ein R1-Testabbild (crust als normale Firmware des HY310,
noch ohne Standby für Nutzer) und die FEL-Testbilder für die Gerätestufen sind gebaut. Am Gerät ist davon **nichts**
gelaufen; alles liegt in Kopien (Arbeitsordner, Branch `versuch/crust-release`), `main` trägt nur diesen Text.
Fortsetzung von `doku/168`. Einstieg: `arbeit/crust-release-20261007/integration/TESTPLAN.md`, Protokoll
`arbeit/crust-20261007/STATE.md`.

## 1 Was entstanden ist

- **Durchsicht** (`arbeit/crust-20261007/PRUEFUNG5-20261007.md`): sieben Prüfer, drei Tiefschlaf-Studien, Gegenprüfung;
  13 Blocker, 24 schwere, 54 kleinere Funde bestätigt, 10 widerlegt.
- **Entwurf** (`arbeit/crust-release-20261007/DESIGN-RELEASE.md`): Meilenstein R1 (crust als Firmware, Sicherheitsnetze,
  ohne Standby für Nutzer) und R2 (Standby, erst mit TODO 3.3). Netze: Linux überwacht den SoC-Watchdog im Betrieb (mit
  richtigem Registerlayout, TODO 2.25), crust einen zweiten Watchdog im Dauerstrom-Bereich vom Einschlafen bis Linux
  wieder bestätigt; TF-A füttert vor jedem Reset. Vertragsseite Version 5. Tiefschlaf ohne VDD_SYS-Reset.
- **Umsetzung** in neun Paketen: crust (41 Commits auf 1957ee6, Kopf a5723aa, mit erster Tiefschlafstufe), Prüfmodell,
  TF-A (3d2992566), Kernel-Treiber, Kernel-Watchdog und Devicetrees, Anzeige/Board, Release-Bau mit Tasten-Dienst
  `h713-power`, Geräteskripte. Jedes Paket unabhängig gegengeprüft, nachgearbeitet und nachgeprüft: kein Fund "nicht
  behoben".
- **Abnahme (Tor G0)**, selbst nachgebaut: crust-Prüfmatrix `GESAMT PASS` (53 Endprüfungen, 732 Emulatorläufe, eingebaute
  Fehler erkannt); TF-A und alle Kernel-Module und Devicetrees bitgleich zur Lieferung; Repo-Tore mit 427 Tests grün.
- **R1-Testabbild** `h713-hy310-v0.0-r1test1` (Branch `versuch/crust-release` 19b91e4, Kernel 248 Patches, reproduzierbar,
  crust- und HDCP-Tor grün) und **sieben FEL-Testbilder** für die Stufen W1, V1', N1-N4, D1a'.

## 2 Was offen ist

- **Alles am Gerät:** Abend 1 (S0a, W1, N0, A0 = R1-Abbild installieren, W2, M1), Abend 2 (Standby-Stufen im
  Testaufbau, Taste/IR, Licht/Lüfter, Strom, erste Tiefschlafstufe). Plan: `integration/TESTPLAN.md`.
- **TODO 3.3** (MIPS nach dem Aufwachen neu laden): Voraussetzung für Standby im Produkt.
- Einspielen in die echte Linie (Forks, Patchspiegel, `main`) erst nach den Messungen.
