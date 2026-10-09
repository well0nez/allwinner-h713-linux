# 175 - HDCP 1.4 übersteht den Standby; was vom HDCP-Härtungspaket bleibt (09.10.2026, 17:40)

**Kurz:** Marco fragte, ob die am 07.10. vorbereitete HDCP-Härtung (`doku/161`, TODO 6.1/6.2/6.5/6.6/6.9) inzwischen
erledigt oder überholt sei. Im Code: nichts davon ist eingebaut. Gegen die heutigen Köpfe geprüft und am Gerät die
entscheidende Frage gemessen: der HDCP-1.4-Schlüssel bleibt über Standby und MIPS-Neustart in der Senke, eine Schreibung
pro Boot genügt also auch mit Standby. Alles nur gelesen und gemessen; keine Änderung an Firmware oder Box.

## 1 Was im Code steckt

TF-A `175c6948f` trägt noch das BL32-Gerüst (`H713_WITH_BL32`, `H713_BL32_AARCH32`, `H713_WDOG_BRINGUP`) und keinen
`HDCP14_STAGE`/`HDCP14_ONCE`; U-Boot `87b2a44` kennt noch `h713_hdcp14_wait`. Der Boot zeigt weiter
"H713 SiP: key set from 0x48a00000 into the sink".

## 2 Passt das Paket auf die heutigen Köpfe?

Probeweise angewendet (Wegwerf-Klone, `git am --3way`):

| Patch | Ergebnis |
|---|---|
| TF-A 0001 (BL32-Gerüst raus, Boot-Watchdog) | Konflikt in `sunxi_bl31_setup.c` und `platform.mk` - die 21 Standby-Commits `4c1bd8c6..175c6948f` ändern beide (Watchdog-Regeln, SYSTEM_SUSPEND) |
| TF-A 0002 (Senke ohne Adresse, einmal) | Konflikt in `platform.mk` |
| U-Boot 0001 (`h713_hdcp14_wait` weg), 0002 (Ablage nach EL3), 0003 (Watchdog über den Treiber) | passen auf `87b2a44` |
| Repo 0001 (Tor) | passt; Repo 0002 (Bau) nicht - `uboot-build.sh` hat sich mit dem crust-Release geändert |

## 3 HDCP 1.4 nach dem Standby (gemessen)

Box r2test4, ThinkPad (i915, nur HDCP 1.4) an HDMI-2. Nach sechs Standbys mit MIPS-Neustart im selben Boot (Reihe V4):
`h713-tv ctl hdcp` "key-1.4: loaded (LINK 0x93=0x45)", `Content Protection` Undesired -> Desired: Enabled nach 2 s. Dann
ein siebter Standby (RTC 20 s, Bild und Audio-DSP zurück), danach wieder Undesired -> Desired: Enabled nach 2 s, Schlüssel
weiter "loaded". Geschrieben wurde der Schlüssel nur beim Boot. Der Schlüssel übersteht also den Stromzyklus der TV-Domänen
und den MIPS-Neustart; wo die Senke liegt, ist damit nicht gemessen, nur dass sie hält. Die Messregel "Senke übersteht
einen Warmstart" gilt damit auch für den Standby.

## 4 Folgerung

- 6.1/6.2 (eine Senken-Schreibung pro Boot): kein Widerspruch zum Standby; TF-A 0002 auf `175c6948f` neu bauen.
- 6.6: unverändert gültig.
- 6.9: weiter nötig; TF-A 0001 neu, den Boot-Watchdog-Teil gegen die Regeln des crust-Release abgleichen (BL31 schärft
  12 s, U-Boot hält ihn an, Linux übernimmt mit 16 s; `doku/170`).
- 6.5: neu bewerten - U-Boot 0003 startet den Watchdog in U-Boot mit 6 s; mit den neuen Regeln kann ein langsamer Weg bis
  Linux die Box zurücksetzen. Nicht gemessen.
- Einbau weiter mit dem Release-Neubau 1.1a, in einer Kopie, per FEL gemessen.
