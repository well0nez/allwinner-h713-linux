# 122 - Handoff Werkzeug-Umbau (abgeschlossen 15.09.2026 mit Release v0.6-beta)

Wer hier einsteigt, liest: dieses Blatt, dann `umbau/STATUS.md` (lebender Stand, alle Pakete mit Review-Zeiger),
dann `umbau/plan/geraetetest.md`. Der Plan dahinter ist [`121`](121-plan-werkzeug-umbau.md).

## Was fertig ist

- **Integrationsbaum:** `umbau/src` = Klon von `repo-neu` (GitHub-Remote `origin`), Zweig `tools-refactor`,
  ~20 Commits über `main`. Nichts gepusht. `repo-neu/` und alle funktionierenden Ordner sind unberührt.
- **Stufe 0-2** (Fixtures, Profile, Golden-Tests; Paket `h713`; gehärtetes Verhalten) - `umbau/reviews/A*, B*, C*`.
- **Stufe 3** (englische CLI): `installer/h713-install` (identify/dump/install/restore/restore-stock/extract),
  `h713-mkimage` (build/check/tree-*), `h713-extract`, `mkimage-selftest.py`, `mkimage-inputs.sh`; alte Namen als
  Weiterleiter mit Hinweiszeile; Doku `docs/tools/h713-*.md`, FLASHING.md ohne Transkript (kommt vom Gerätetest);
  `release/build-all.sh` und `rootfs/*.sh` englisch - `reviews/D1, D2, D4, D5`.
- **Stufe 4** (Boards): `boards/<id>/board.env` + `check.sh` (sechs Boards, nur hy310 `verified` mit Profil);
  Kernel-DTS `sun50i-h713-hy310` (Patch 0160); U-Boot-Fork `src/mainline/external/u-boot` Zweig `h713-hy310` auf
  `e4dadcb` (E3b Basis+Rollen, E3a Lader nach Board-Fakten, E5 Sonden-Profilzeile; **nicht gepusht**, der
  Submodul-Zeiger im Repo zeigt darauf); `release/build-all.sh --board` verweigert ungetestete Boards -
  `reviews/E1, E2, E3a, E3b, E6`.
- **Prüfungen:** Suite `installer/tests/run.sh --local --slow` 102 Tests grün (inkl. Selbsttest gegen den eigenen
  Bau); `boards/check.sh` grün; `release/sperr-scan.py .` leer; U-Boot-Matrix im Container gebaut, Defconfig-
  Beweis auf .config- und Binärebene; voller Release-Bau `v0.6-beta` aus `umbau/src` grün (Selbsttest ALL GREEN).

## Erledigt am 15.09. (Release v0.6-beta: https://github.com/well0nez/allwinner-h713-linux/releases/tag/v0.6-beta)

Alle Punkte unten sind durch; offen bleibt nur das nächste Paket: geräteseitige Werkzeuge (`h713-fel`, `h713-tv`, `h713-pq`) englisch (doku/61).

## Was ausstand (in dieser Reihenfolge)

1. ~~Letzter Bau von vorn~~ **erledigt 22:05**: 18 min, Repo c8bd780 (0 lokale Änderungen), U-Boot e4dadcb, Selbsttest
   ALL GREEN (`umbau/build/logs/build-all-final.log`, Stempel `umbau/src/installer/out/h713-hy310-v0.6-beta.BUILD.txt`).
   Release-Ordner wie ein Fremder ihn bekäme: `umbau/build/release-v0.6-beta/` (drei Teile, Tabelle, sha256, README, `u-boot-installer.bin`, `sunxi-fel`, `u-boot-h713-probe.bin`); Repo-Stand 51e0589 (README-Befehl nennt den Ordner; Teile byteidentisch zum Bau von vorn).
2. ~~Entscheidungen Marco~~ **getroffen 15.09.**: Abzug-Dateinamen jetzt englisch (alte Namen werden gelesen), Sondenlauf 6b ja.
3. ~~Der eine Gerätetest~~ **grün 15.09. 00:2x-01:5x** (Schritte 1-8 und 6b; Ergebnisse je Schritt in `umbau/plan/geraetetest.md`,
   Logs und `script`-Transkript in `umbau/test-20260915/`). Drei Befunde, alle behoben: Sonden-Signatur (Fork 642214c),
   `identify`-Wortlaut auf unserem Layout (b37b015), `install` braucht den Vollabzug (bleibt, Todo doku/61).
   **Offen:** kurze Wiederholung 4 → 5 → 7 mit Bau 2 (`umbau/build/release-v0.6-beta/`, Repo a311c5b, Fork 642214c),
   damit getestet = ausgeliefert; das am Gerät getestete Abbild liegt in `umbau/build/release-v0.6-beta-getestet-20260915/`.
4. Danach: `tools-refactor` → `main` (Merge, kein Force), Sperr-Scan, Push von Repo **und** U-Boot-Fork
   (`git -C umbau/src/mainline/external/u-boot push origin h713-hy310`), Release `v0.6-beta` mit den Dateien
   aus `installer/out` + `u-boot-installer.bin` + `sunxi-fel` + `u-boot-h713-probe.bin`; Release-Seite wie ein
   Fremder lesen; FLASHING-Transkript aus dem Test eintragen.
5. `repo-neu/` durch den Stand von `umbau/src` ersetzen (Klon neu ziehen), `umbau/` archivieren wie das Backup
   `/opt/Projekte/backup/h713-arbeitsstand-20260914.tar.zst`.

## Wo was liegt

| Was | Wo |
|---|---|
| Lebender Stand, Pakettabelle | `umbau/STATUS.md` |
| Reviews (eine Datei je Paket) | `umbau/reviews/*.md` |
| Agentenausgaben (nie integriert kopieren, nur lesen) | `umbau/work/<paket>/` |
| Vendor-Bytes (nie ins Repo) | `umbau/fixtures-local/` |
| Bau-Logs, U-Boot-Beweise | `umbau/build/logs/`, `umbau/tools/uboot-*.sh` |
| Regeln für Agenten | `umbau/plan/agent-regeln.md` |
| Späte Todos aus dem Umbau | [`61`](61-todo.md) Nachträge 14.09. |

## Was man nicht tun darf

- Nichts in `repo-neu/`, `mainline/`, `analyse/release/arbeit/`, `userspace/`, `release/` ändern (121 §5).
- Kein Abbild für ein Board ohne grünen Besitzerbericht (`build-all.sh --board` erzwingt es).
- Nicht pushen, bevor `release/sperr-scan.py .` leer ist und der Gerätetest grün war.
