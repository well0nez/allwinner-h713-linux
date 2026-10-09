# 173 - Durchsicht des Standby-Codes, C1 im TVCAP-Abschalten eingegrenzt, Ton nach dem Standby abgesichert; r2test3 (09.10.2026, 14:30)

**Kurz:** Der R2-Stand (crust ecf2ddc, TF-A 175c6948f, Kernel 0225-0239, h713-power) ist vollständig durchgesehen
(Workflow mit sieben Prüfern und Gegenprüfungen, 46 Funde, keiner kritisch im Code der Bild-Rückkehr). Der seltene Hänger
beim Einschlafen (C1) steht laut Brotkrumen in der PPU-Abschaltung von TVCAP, unter der noch schreibenden
HDMI-Aufnahme (INCAP); hält hdmirx die Aufnahme vor dem Schlaf an, kam C1 in 50 Schläfen nicht mehr (vorher 5 in 111).
Der Audio-DSP verliert im Schlaf den Strom; der Treiber meldet das jetzt ehrlich, statt den toten Block anzufassen.
Alles in Kopien (R2-Zweig `versuch/r2-standby`, Pakete `arbeit/review-r2-20261009/` und `arbeit/r2-20261009/`); `main`
trägt nichts davon. Fortsetzung von `doku/172`.

## 1 Die Durchsicht

Auftrag aus der Übergabe vom 08.10. abends (§7) plus 0236-0239. Je Bereich ein Prüfer und eine Gegenprüfung, schwere
Funde ein zweites Mal; nur gelesen, Bäume danach unverändert. Ergebnis in `arbeit/review-r2-20261009/BERICHT.md`, alle
Funde mit Belegen in `FUNDE.md`. Behoben in dieser Runde (Serie 0240-0244 und h713-power):

| Fund | Was | Behebung |
|---|---|---|
| Q1-Q3 | C1 im TVCAP-Abschalten unter laufender INCAP-DMA | 0240: hdmirx hält die Aufnahme im Suspend an |
| Q5 | Audio-DSP nach dem Standby stromlos, Treiber meldet "running" | 0243: Insel gilt als verloren, Zustand "error" |
| CC-2 | nach gescheitertem Neustart keine Display-Takt-Abschaltung | 0241 |
| KM-1 | Meldung "core held" statt "parked" | 0242 |
| Q6 | PPU-Fehlschläge stumm | 0244 |
| U1 | Tastendrücke aus der Schlafphase nach dem Wecken bewertet | h713-power verwirft sie |
| B3/CR-5 | crust-Spiegel nannte a5723aa | Spiegel auf ecf2ddc, Abbild jetzt "reproducible: yes" |

Offen und bekannt: kein Hardware-Netz gegen einen Hänger von crust selbst im SR-Bau (CR-1), Wecken per Taste/IR, lange
Schläfe und Leistung nicht gemessen (CR-2), sperr-scan erkennt im Worktree das Git nicht (B1).

## 2 C1

Messung mit einer schnellen Schleife auf der Box (`arbeit/r2-20261009/c1/`: Schlaf 3 s, Bild-Rückkehr, 8 s Nachlauf;
Protokoll mit fsync) und Brotkrumen in RTC-GP1/GP4.

- **Ort:** fünf von fünf C1 mit Krumen hingen zwischen TVCAP PRE_OFF und TVCAP OFF (wb2, zwei in der Grundrate, zwei
  in der Kontrolle). Das PPU-Statuswort von TVCAP war beim PRE_OFF "an und idle" (`0x00010000`): die PPU hält die Domäne
  für ruhig, die Aufnahme schreibt trotzdem.
- **TV-Top-Aus-Schritt vor dem Abschalten:** kein Unterschied (C1 in Zyklus 12) - widerlegt.
- **INCAP im noirq-Fenster anhalten:** nicht möglich - schon das Lesen von INCAP `+0x928` hielt die Box an (Stufenmarke).
  Ab dem Park antwortet INCAP der CPU nicht mehr.
- **INCAP vor dem Einfrieren anhalten** (Bit 31 der beiden Ausgabe-Freigaben, wie `memory_agent_onoff`, 40 ms warten):
  Testmodul 20 von 20 ohne C1; dieselbe Stelle als Patch 0240 in hdmirx (Suspend, MIPS läuft noch) im Abbild r2test3:
  30 von 30 ohne C1.

| Arm (gleiche Schleife) | Schläfe | C1 |
|---|---|---|
| ohne Eingriff (Grundrate) | 88 | 2 |
| Testmodul, nur messen | 11 | 2 |
| TV-Top-Aus-Schritt | 12 | 1 |
| Aufnahme vor dem Einfrieren angehalten (Testmodul) | 20 | 0 |
| r2test3 mit 0240 | 30 | 0 |

0 in 50 gegen 5 in 111: ein Hinweis (p etwa 0,15), kein Beweis. Ein C1 heilt sich durch den Neustart selbst; der
Gebrauch zeigt den Rest.

## 3 Ton nach dem Standby

Gemessen (q5a): das Audio-Top-Wort `0x0614a000` las nach dem Boot `0x700`, nach einem Standby und dem MIPS-Neustart `0`;
msp meldete weiter "running". `echo 1 > reset` setzte das Audio-Top wieder, aber die Mailbox des DSP antwortete nicht
("Mailbox timeout during read of 0x00ee"). Mit 0243 gilt die Insel nach jedem Standby als verloren (Zustand "error",
ehrliche Meldung, keine Mailbox-Timeouts mehr in R3); HDMI-Ton gibt es nach einem Standby erst nach einem Neustart.
Warum der DSP nach dem Stromzyklus nicht wieder hochkommt, ist offen.

## 4 r2test3

Gebaut aus `versuch/r2-standby` c640dbe (268 Patches, reproduzierbar), per FEL eingespielt (Schritt 4 wegen eines
verzögerten Partitionslabels von Hand). Reihe R3, 30 schnelle Zyklen: 30 von 30 mit Bild zurück, kein C1, keine
Warnung der neuen Patches. Nicht gemessen: echter Tastendruck, Wecken per IR, Schläfe über 20 s, Leistung, HDMI-Ton mit
Hörtest, HDCP 2.2 nach dem Neustart.
