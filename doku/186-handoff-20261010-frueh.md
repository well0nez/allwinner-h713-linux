# 186 - Handoff 10.10.2026 früh: der HY300PRO-G-EU auf dem Stand des HY310, alles in `main`, nächste Schritte

Einstieg für die nächste Sitzung. Löst `doku/183` (10.10. nachts) ab. Die Nacht in Einträgen: `doku/184` (G-EU-Testreihe mit
`geucrust2`), `doku/185` (Lüfter und Lampe im Standby, PB5). Protokoll: `arbeit/crust-20261007/STATE.md` bis 04:0x.
Die eine Aufgabenliste: `TODO.md` - seit dieser Nacht stehen oben nur offene Punkte, alles Erledigte in Abschnitt 10.

## 1 Was diese Sitzung erreicht hat

| Thema | Ergebnis | Beleg |
|---|---|---|
| HY300PRO-G-EU auf HY310-Stand | crust, MIPS-Reload mit Panel-Stromzyklus, Standby mit RTC/Taste/Fernbedienung, HDCP-1.4-Paar und 1.4 nach Standby, HDCP 2.2 mit zwei Neuverhandlungen, Ton nach Standby: bestanden. Nicht gemessen: Watt im Standby | `doku/184` |
| Lüfter/Lampe im Standby (G-EU) | Ursache: PB5 stand im G-EU-Baum als gpio-hog; Stock-Baum nennt PB5 als `panel_bl_en` und `fan-power-gpio` wie beim HY310. Kernel `0249` gibt PB5 dem Board-Manager - Lüfter aus im Standby, nach dem Wecken alles zurück | `doku/185` |
| Integration | `versuch/geu-crust` gemergt (`63fd053`; Kernel 0246-0248, `--standby` für Testabbilder, Mesa-Prüfung), crust-Fork `versuch/mips-drop` auf `c5b536f` vorgespult, Spiegel `crust-h713/` mit 81 Patches (`01bdbfb`, Baum = Fork-Kopf), 0249 (`4767f6f`), Doku je Subsystem | `git log fcab042..main` |
| Kompletter Bau aus `main` | `v0.0-geumain1-TEST` aus `4767f6f`, 35 min, nichts wiederverwendet, **reproducible: yes**, Gates grün; per FEL auf den G-EU, Box bootet | `arbeit/geu-main-20261010/` |
| Bau-Fehler behoben | Mesa-Stufenprüfung starb an SIGPIPE (`grep -q` unter pipefail) | `d2abfc7`, `referenz/irrwege.md` |
| TODO aufgeräumt | 70 erledigte Punkte nach Abschnitt 10; neu 1.1b, 1.7a, 2.34-2.37, 5.18, 5.19, 7.19, 8.10 | `c8012be`, `eec54c8` |
| Cloud-RE vorbereitet | privates Repo `well0nez/h713-offline-re`, Zweige `a-aus`, `b-einschlafen`, `c-loglevel` mit Material und je einer `AUFTRAG.md` (Prompt) | TODO 8.10, §4 |

## 2 Stand

- **`main`** = dieser Commit, **225 Commits vor `origin`, nichts gepusht.** Veröffentlicht wird nur `main` (Marco 10.10., TODO
  1.7); vorher die Leck-Prüfung 1.7a, Forks zuerst (1.6: U-Boot `h713-hy310` Kopf `7b1ea388da0d` +11, TF-A `sun50i-h713`
  `5a7806892` +25, crust neu als `h713` aus `versuch/mips-drop` Kopf `c5b536f`, 81 Patches). Auf GitHub können `master`,
  `legacy`, `hy300-pro-ab` weg (Inhalt in `main`, geprüft).
- **Geräte:** beide aus. HY310: `r2test4` + Schnell-Deploy `0245`, `h713_gate=1`, im Gate, Sonoff an. HY300PRO-G-EU:
  `geumain1` (= `main` 4767f6f), `h713_gate=1`, `power.conf short = standby` (Testabbild), BLE-Fernbedienung gekoppelt;
  Marco hat ihn ausgeschaltet. Netz-Ein wartet bei beiden auf die Power-Taste.
- **Arbeitsordner:** `arbeit/geu-main-20261010/` (Worktree `repo`, detached auf 4767f6f, mit dem gebauten Abbild - Referenz
  für den G-EU; `geu-install.sh` sichert `/etc/h713`, **`/var/lib/bluetooth`** und die Host-Schlüssel); `arbeit/cloud-re-20261010/`
  (Stage + lokaler Klon des Cloud-Repos); `arbeit/geu-crust-20261009/` (Paket der Nacht, integriert; Worktree `repo` wartet
  auf Marcos Löschbefehl, §3).

## 3 Offen aus dieser Sitzung - zuerst

1. **Alten Worktree entfernen (Marco, root):** `sudo rm -rf /opt/Projekte/h713/arbeit/geu-crust-20261009/repo && git -C
   /opt/Projekte/h713/repo-neu worktree prune`. Danach löscht Claude die sechs lokalen Zweige (`integration/r2-main`,
   `versuch/{crust-release,geu-crust,hdcp-haertung,r2-standby,standby-gate}` - alle in `main`) und die `versuch/*`-Zweige
   in den Fork-Klonen.
2. **Kurztest auf `geumain1`** beim nächsten Einschalten des G-EU (TODO 1.4): ThinkPad an HDMI, leiser Ton
   (`arbeit/geu-crust-20261009/standby/`-Skripte, Ablauf `doku/184`), ein Standby mit RTC (Lüfter muss ausgehen), ein Reload.
   Dazu, wenn Marco umsteckt: Watt im Standby (USB gezogen, dann nur per ssh erreichbar).
3. **Cloud-RE starten (Marco):** je Zweig eine Cloud-Sitzung (Sonnet) auf `well0nez/h713-offline-re`, Prompt aus der
   `AUFTRAG.md`; Ergebnisse kommen als PR `<thema>-ergebnis`. Claude wertet aus, trägt Befunde ins Journal, dann Repo löschen
   (Marco). Themen: A "Aus" wie Stock (Grundlage für 2.32), B Einschlafen/Audio-DSP (C1, 2.37), C Log-Stufe (2.36).

## 4 Der Plan bis zum Release (TODO §1)

1. **1.1b ARISC/crust-Taktik mit Marco** (er will crust als Vorgabe) - zusammen mit **2.32** (echtes Aus über crust; Ergebnis
   von Cloud-Thema A abwarten). Nicht heute (Marco).
2. **7.19 Doku-Runde** für beide Geräte: README/Board-Liste (G-EU-Status), `docs/README.md`, `STATUS.md`, `ROADMAP.md`,
   `known-issues.md` durchsehen, `boards/README.md`, RELEASES-Entwurf.
3. **1.1a Release-Neubau** HY310 (und G-EU als Testabbild): `--standby` mit `short = poweroff` (Marco 2.29), Bauverzeichnisse
   von vorn, HDCP-Paar und Standby messen.
4. **1.7a Leck-Prüfung** über alles, was rausgeht, dann **1.6** Forks, **1.7** `main`, Zweige auf GitHub aufräumen, danach
   die Prüfung gegen einen frischen Klon; **1.8** RELEASES und Tag. Jeder Push nur mit Marcos Ja.

## 5 Was man wissen muss (neu)

- Der Stock-Gerätebaum eines Boards steht im `vendor_boot` des eigenen Abzugs (DTB herausziehen, zurückübersetzen); er hat
  heute PB5 entschieden. Ein Hog in unserem Baum ist kein Beleg (`referenz/irrwege.md`).
- Die BLE-Fernbedienung muss mit unserem System einmal gekoppelt werden (LINKS+RECHTS); ihre Kopplung liegt in
  `/var/lib/bluetooth` und überlebt eine Neuinstallation nur, wenn man sie sichert (1.2b). IR weckt, IR schläft nicht ein (2.35).
- Das ThinkPad fragt HDCP 1.4 nach einem Neustart oder Standby der Box nicht neu an - jedes Mal `Undesired` -> `Desired`
  (`referenz/messregeln.md`).
- Submodule in einem frischen Worktree: Commits aus `repo-neu/mainline/external/<x>` holen, GitHub hat die Fork-Köpfe noch nicht.
- UMS am Ende einer Installation beendet `uart_ums_reset.py` über den UART-ESP (Strg-C, `reset`); die Box startet ohne Handgriff.
- Lange Befehle in den Hintergrund, kurze Wartezeiten (Marco: Befehle liefen länger als nötig).

## 6 Weiter geplant (nach dem Release)

Grüner Streifen (2.34, DRAM?), IR-Belegung für Power (2.35), Hostname je Board (5.18), build-all mit Wiederaufnahme
(5.17), crust als Submodul (5.15), schneller ans Bild nach dem Standby (9.0), Bluetooth-Ursache (9.12), automatischer
Standby (9.14), test10 für den Tester (4.1).
