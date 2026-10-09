# 183 - Handoff 10.10.2026 nachts: Stand und Plan (HY300-Tests mit geucrust2 stehen an)

Einstieg für die nächste Sitzung. Davor: `doku/177` (R2 in `main`), `doku/179` (dunkles Gate), `doku/180`
(HDCP-Härtung), `doku/181` (Leistung), `doku/182` (HY300: crust, Reload-Schwarz = Panel). Die eine Aufgabenliste ist
`TODO.md`; das laufende Protokoll `arbeit/crust-20261007/STATE.md`.

## 1 `main` und die Linie

- `main` 3942941 + diese Seite, **208 Commits vor `origin`, nichts gepusht.** Push nur mit Marcos Ja je Push, Forks zuerst
  (TODO 1.6): U-Boot `h713-hy310` +11 (Kopf `7b1ea388da0d`), TF-A `sun50i-h713` +25 (Kopf `5a7806892`), crust-Fork neu
  (Kopf `ecf2ddc`, 80 Patches; der G-EU-Commit `c5b536f` liegt nur auf `versuch/geu-crust`), dann `main`.
- Seit R2 in `main`: Doku je Subsystem; `0245` (missglückter Standby endet dunkel im Gate, GP5 "STBY"); HDCP-Härtung in
  den Forks (eine Senken-Schreibung pro Boot, ohne Adresse, Watchdog über den Treiber; BL32-Gerüst raus); Leistung
  (Standby 2,4 W < Aus 2,9 W am HY310); TODO 2.29 entschieden (Standby im Release experimentell, Vorgabe aus), 2.30, 2.31
  erledigt, neu 2.32 (Aus 2,4-2,9 W gegen Stock 0,3 W), 5.16, 5.17.
- Kernel-Serie in `main`: 270 Patches (bis `0245`).

## 2 Offene Zweige und Pakete

| Zweig / Paket | Inhalt | Stand |
|---|---|---|
| `versuch/geu-crust`, Worktree `arbeit/geu-crust-20261009/repo` | Kernel `0246` (G-EU: crust im Gerätebaum, MIPS-Knoten an), `0247` (PF6 in der Pin-Tabelle), `0248` (Panel-Stromzyklus nach dem MIPS-Neustart, PF6/PH16 im Gerätebaum); `board.env` `CRUST_DEFCONFIG`; build-all/build.sh: `--standby` für ein `--test-image` | gebaut als `geucrust1` (ohne 0247/0248, ohne Standby), **`geucrust2` baut gerade** (mit allem, `--standby`); nicht in `main`, Basis ist `main` von vor `3942941` (Merge nötig) |
| crust `versuch/geu-crust` (Klon `arbeit/geu-crust-20261009/crust`) | `h713_hy200_qz713df_a1_sr_defconfig` (HY310-SR, Board-ID 3) | `c5b536f` auf `ecf2ddc`; nach den Tests in den Fork und den Spiegel `crust-h713/` |
| `versuch/standby-gate`, `versuch/hdcp-haertung` | in `main` übernommen | Worktrees entfernt, Zweige als Beleg |

## 3 Die Geräte

| Gerät | Adresse | Stand |
|---|---|---|
| HY310 | `.131`, UART Orange Pi `192.168.8.180:2000` | r2test4 + Schnell-Deploy `0245` (FIT mit DTB-Gate-Wort, Modul), `h713_gate=1` (Netz-Ein wartet auf die Taste), `power.conf` Standby an |
| HY300PRO-G-EU | `.245`, UART-ESP `192.168.8.105` (2001 lesen, 2000 schreiben nur nach Rückfrage) | `geucrust1-TEST` + Schnell-Deploy (Kernel mit PF6, DTB mit Panel-Pins, Modul mit Panel-Zyklus; Sicherung `/root/sicherung-panel/`); crust läuft, Reload bringt das Bild zurück (3/3) |

## 4 Plan für die nächsten Schritte

1. **`geucrust2` installieren** (`arbeit/geu-crust-20261009/geu-install2.sh`): Sicherung `/etc/h713` + Host-Schlüssel,
   FEL per `h713-fel`, `h713-install` über unser Layout **ohne `--dump`** (kein neuer Schlüsselspeicher-Abzug),
   Herstellerdateien aus `re/device-dumps/hy300pro-plus-marco/h713-extract-out` (nur lesen), Sicherung zurück. Den UMS-
   Abschluss erledigt der ESP nur, wenn er Strom hat; sonst Marco: USB ziehen, Netz aus/an, Power-Taste. Danach die
   Arbeitskopie `work-copy2.img` löschen (TODO 5.11).
2. **Tests am HY300**, in dieser Reihenfolge, Ergebnis je Zeile in ein neues Journal:
   - crust läuft (Kennung, Board 3), Reload ohne Schnell-Deploy (Panel-Zyklus im Log), 3x;
   - Standby über h713-power: RTC-Wecker, dann Power-Taste, dann IR (Marco an der Box); Bild und Ton zurück; der Lüfter
     läuft im Standby weiter (PB5 bleibt an, bekannt);
   - HDCP-1.4-Paar mit dem ThinkPad (Nullen-Boot -> Desired, Standard-Boot -> Enabled), HDCP 2.2 mit dem Fire-TV-Stick,
     Ton über HDMI;
   - Leistung im Standby (Wattmeter, USB gezogen).
3. **Bei grünen Tests:** `versuch/geu-crust` mit `main` zusammenführen (Merge), crust-Commit in den Fork und Spiegel
   `crust-h713/` neu, Doku (mips.md Panel-Zyklus, standby.md, boards/hy200-qz713df-a1, known-issues), Tore, `main`.
   Ob die Variante dann `verified` heißt, entscheidet Marcos Bericht.
4. **Danach:** TODO 2.32 (Aus über crust statt U-Boot-Schleife) besprechen - mit der allgemeinen ARISC/crust-Runde;
   Release-Neubau 1.1a (HY310, `--standby` mit Vorgabe `short = poweroff`, HDCP-Härtung und `0245` sind schon in der
   Linie; das U-Boot-Banner zu `--standby` ist veraltet, TODO 5.16).

## 5 Was man wissen muss

- Panel-Stromzyklus gilt nur für Boards, deren Gerätebaum `panel-power-gpios` nennt (G-EU); der HY310 (DLP-Brücke) nicht.
- Ein Pin, der im Gerätebaum benutzt wird, muss in der Pin-Tabelle des H713 stehen (`pinctrl-sun50i-h713.c`), sonst hängt
  die Probe still mit -517.
- Den Kernel im build-all-Baum von Hand bauen: der erste `make` baut alles, danach inkrementell (TODO 5.17).
- Tore im Worktree: auf einem `git checkout-index`-Export (TODO 5.13).
