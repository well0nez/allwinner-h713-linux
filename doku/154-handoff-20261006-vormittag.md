# 154 - Handoff 06.10.2026, Vormittag (06:00-10:45) - Aufräumen, Regeln, Verknüpfungen

Fortsetzung von `152` (Abend 05.10.) und `153` (S-EL1 raus). Die eine Liste bleibt `TODO.md`.
Nichts gepusht; `main` lokal 112 Commits vor GitHub.

## 1 Was erledigt ist

- **§7 Doku/Repo:** 13 von 18 Punkten erledigt (7.1-7.13 ausser 7.14-7.18). Journal ist eine Quelle
  (Repo-Kopie), alter Master liegt lokal als Archiv. Branches: nur noch `main`; `hy300-pro-ab-lokal`
  gemessen (561 Dateien, 0 fehlen in main) und geloescht.
- **Arbeitsregeln fuer Agenten** (7.1): nicht in die veroeffentlichte `AGENTS.md`, sondern lokal in
  `referenz/arbeitsregeln.md`; geladen ueber `/opt/Projekte/h713/CLAUDE.md` (Symlink) und einen Block
  in `~/.claude/CLAUDE.md`. Kern: immer in einer Kopie (`versuch/<thema>`, `arbeit/<thema>/`,
  Geraetesicherung), Lieferung = Bericht + Patches + Kompilat, `release/tor.sh && git commit`, Identitaet
  nur noreply, kein Push ohne Marco, UART ein Client.
- **Sitzungen gehoeren in `/opt/Projekte/h713`:** Auto-Memory (64 Eintraege) und MemPalace-Hooks haengen am
  Startordner; aus `<geschwaerzt 23.10.2026: lokaler Pfad>` gestartete Sitzungen (05.10. abends, 06.10. frueh) bekamen beides nicht.
  Memory zusammengefuehrt, zwei Transkripte von Hand eingelesen (131 808 Drawers).
- **Forks:** Submodul-Remotes TF-A/sunxi-tools per `git submodule sync` wieder auf GitHub; Identitaets-Hooks
  gelten in den Forks; `pre-push` prueft nur noch, was ein Push hinzufuegt (Upstream-Baeume tragen fremde
  Adressen). TF-A-Linie ohne den S-EL1-Test (`153`): Kopf `4c1bd8c6`, Spiegel 6 Patches, BL31 bytegleich.
- **Graphify** lief seit 05.10. 22:08 nicht mehr (Hook in `.git/hooks` durch `core.hooksPath` stumm);
  `.githooks/post-commit`/`post-checkout` reichen jetzt weiter. **MemPalace**: der SessionStart-Hook speist
  nichts ein (Code: pass through), die Hooks speichern nur; Suche liefert Rauschen - Bilanz 12.10. (8.2).
- referenz/: alle Seiten `verified: 2026-10-06`; neu `arbeitsregeln.md`, Landkarte des Projektordners in
  `baeume.md`, Messtisch-Skripte in `werkzeuge.md`, Geraete-Fallen in `geraete.md`. `arbeit/skripte/` haelt
  `deploy-test.sh`.

## 2 Naechste Schritte (Reihenfolge wie `152` §4)

1. Release-Pfad: Bau mit allen Fixes (0183, 0184, Warp, EDID, Panel) - **in einer Kopie**, Geraet vorher sichern.
2. 1.2a Z4-Doppelboot: Journal persistent, pstore, fuenf Kaltstarts **mit UART**.
3. 1.2b Installer uebernimmt `/etc/h713`. 1.3 WLAN-Haengefall. 1.4 HY300 Pro G-EU. 1.5 STAGE4.
4. 1.6 Forks pushen (U-Boot +6, TF-A +1), dann 1.7 `main`, 1.8 RELEASES.md - nur mit Marcos Ja.
5. §7 Rest: 7.14, 7.16 allein moeglich; 7.17 braucht Box und Kamera; 7.18 ein Satz von Marco.

## 3 Offen an Marco

- 7.18 Release-Satz zur Fernbedienung so lassen?
- `arbeit/mail-pruefung/` (Identitaetsbericht) loeschen?
- `origin/hy300-pro-ab` auf GitHub loeschen (= Push, erst bei 1.6)?
