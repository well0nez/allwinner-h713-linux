# 207 - HY310 auf `main`: Abbild hy310main1 gebaut und installiert, die offenen 2.x-Punkte gemessen; Handoff (12.10.2026, abends)

**Kurz:** Marco wollte die offenen 2.x-Punkte am HY310 - "wir haben in main zuletzt mit dem HY300 gebaut, für die nächsten Tests
baue ich jetzt den HY310 auf" - und zwar auf dem echten `main`, nicht auf einem Zwischenstand. Also: komplettes Abbild aus `main`
db558e3 (`build-all.sh --board hy310 --standby`, 28 min 48 s, reproducible), per FEL installiert (Sicherung `/etc/h713`,
Bluetooth-Bund, Hostschlüssel; kein Abzug, kein Rückweg-Abbild - Marco: "main ist der Rückweg"), dann die Reihe. Paket
`arbeit/hy310-main-20261012/` (`BERICHT.md`, `install.sh`, `skripte/`, `laeufe/`, `fotos/`). Vorher 2.5 (gelöst) und 2.9
(gestrichen) auf Marcos Ansage geschlossen.

## 1 Ergebnis

| TODO | gemessen | Stand |
|---|---|---|
| 1.1a | Generalprobe des Bauwegs: frischer Worktree, drei Submodul-Köpfe von Hand nachgezogen (sie liegen noch nicht auf GitHub, 1.6), `CRUST_SRC` = crust 54e4a08; Abbild reproducible, 286 Patches; Installer schreibt und vergleicht in 3 min, Schritt 4 (PARTLABEL) wie gehabt von Hand | HY310 läuft `main` |
| 2.36 | `0x4B48BE84` = `0xA7` am Gerät (alle fünf Masken), `fmt_set[0]` = 0 | erledigt |
| 2.22 | 5 Warmstarts, bei 151 s fünf Plattenzugriffe mit Zeitlimit: 5/5 sofort, 0 mmc-Zeilen | nicht reproduziert |
| 2.49 | 11 Starts (5 warm, 6 Standby) mit 0256: Bluetooth 11/11 beim 1. Versuch, 0 HCI-Fehler | Last-Test offen |
| 2.62 | Warp an: Ebene 59,43/s, Quelle 60,02/s, **Panel 59,42 Hz** (erstmals), 0 Sprünge; fps 59,5, 0 drop; CPU warp 9,8 %, alle 4,6 %, 100 % bei 480 MHz; GPU 432 MHz 76 %, 6,2 ms je Bild (1080p); Bypass 0,57 Sprünge/s (Takt 59,42 zu 60,02, wie `doku/200`) | erledigt |
| 2.26 | ThinkPad i915, Moduswechsel 1080p50 -> 60, Anforderung nach d s: d=0 Enabled nach 3,06 s, d=0,5 bis 3 nach 1,14-1,21 s - kein "bleibt auf Desired" am HY310 | gemessen |
| 2.16 | busy 0 von 11230 nach 12 min, 3 von 238 beim Warp-Start | normal |
| 2.37/2.64 | 6 Standbys per RTC zurück, DSP 6x im 1. Versuch, 59,4 Bilder/s | 6/6 |
| 2.34 | siehe §2 | offen, keine Prio (Marco) |

## 2 Der grüne Streifen (2.34)

Marco an der Wand: "immer grün beim Warpen, egal ob Standby oder nicht; die Konsole hat grüne Streifen mal links, mal rechts,
wenn's aus dem Standby kommt" - und: wenn nichts gefunden wird, als TODO lassen, keine Prio.

Gemessen: Grün ist ein YUV-Puffer ohne Inhalt (Y=U=V=0 = dunkelgrün); der Code sagt es selbst (h713-tv `display_create_fb`:
"the flat green that the empty ring produces", h713-warp `warp_engage`: "green on the first frame of each return"). Nach dem
Aufwachen (`ebene-wach.py`, AFBD +0x70 im 0,25-ms-Takt, drei Läufe): Ebene aus bis ~8-10,6 s, dann im Bypass auf **volle**
Ringplätze (0 von 32 Nullwörtern in Zeile 0/540/1079), nach ~370 ms Claim (Konsole ~100 ms), dann der erste Warp-Puffer. Der
Warp übergibt den Out-Fence als `IN_FENCE_FD`, afbd nutzt `drm_atomic_helper_commit` (Commit-Tail wartet den Fence ab) - der
erste Warp-Puffer ist beim Flip fertig gerendert. Nicht lesbar: sein Inhalt (System-RAM, `/dev/mem` verweigert). Die Box-Kamera
(Fotoserie alle 0,4 s ab dem Wecken) sieht den Projektionsrand nicht und taugt dafür nicht. Offen: der erste Warp-Puffer aus dem
Warp selbst gelesen, und ein `/dev/fb0`-Abzug der Konsole direkt nach dem Wecken (die Konsolen-Streifen liegen im RGB-Pfad,
nicht in unseren YUV-Puffern).

## 3 Irrweg des Tages

`ebene-wach.py` lief beim 4. Standby schon vor dem `suspend()`: beim Aufwachen las er INCAP/AFBD vor dem Strom der TV-Domäne -
Bus-Hänger, Watchdog-Reset 16,9 s nach "back from system suspend" (UART-Mitschnitt im Paket). Derselbe Mechanismus wie 2.64
(`doku/203`). Mit `h713_gate=0` fing sich die Box selbst. Regel in `referenz/irrwege.md`: Register der TV-Domäne erst nach
"picture path back" lesen; der Beobachter startet seitdem danach.

## 4 Handoff (12.10.2026, ~20:00)

**`main`: 4fc1284 + dieser Commit** (TODO, doku/207, docs hdmi-in; davor db558e3 = TODO 2.5/2.9, 4ac5e17 = doku/205/206), **nicht
gepusht** - alles seit 234282c ist ungepusht, Reihenfolge beim Push in `TODO.md` §1 (1.6 Forks zuerst, 1.7a Prüfung, 1.7 `main`).

**Geräte:**
- **HY310** (`.131`, UART-ESP `.224`): `main` db558e3 **komplett aus dem Abbild** `hy310main1` (FIT `c7f8f850`, h713-tv `74df3200`,
  h713-warp `d123adac`, crust 54e4a08, Module aus dem Baum, nichts in `updates/`); `/etc/h713`, Bluetooth-Bund und Hostschlüssel
  (`SBcCAf…`) vom Vorstand; `h713_gate=1`, `power.conf short = standby`, Warp an (Keystone `tl 283,0 tr 112,263 bl 224,28 br 45,0`),
  Journal flüchtig; Quelle **ThinkPad** HDMI-2 1080p60, dort steht `Content Protection = Desired` von der 2.26-Reihe. FEL-Kabel
  steckt vermutlich noch (Marco). Messskripte liegen in `/root` (`zustand.sh`, `anzeige.py`, `messe-warp.py`, `s3-foto.py`,
  `ebene-wach.py`, `reg-a7.py`, Kamera) - Testmaterial, nicht Teil des Abbilds; `/dev/shm` geleert.
- **HY300PRO-G-EU** (`.245`, UART-ESP `.105`, Sonoff `.179`): unverändert seit `doku/206` §3 (Kernel 234282c + 0260-0262 in
  `updates/`, `h713_gate=0`), heute Abend nicht erreichbar (aus).

**Paket `arbeit/hy310-main-20261012/`:** `BERICHT.md`, `install.sh`, `skripte/`, `laeufe/`, `fotos/`, Sicherung
`sicherung-hy310main1/`. Worktree `repo/` auf `versuch/hy310-main` = `main` db558e3 **ohne eigene Commits**, aber mit 5,2 GB
(Abbild 1,2 GB, Bauverzeichnis 4 GB inkl. Kernelbaum 6531a386 - brauchbar für Schnell-Deploys bis 1.1a). Entscheidung Marco:
jetzt löschen oder nach 1.1a; der Worktree geht dann mit `git worktree remove`.

**Was die Reihe gezeigt hat** (§1): 2.36 und 2.62 zu; 2.22 nicht reproduziert; 2.26 kein Desired-Stall am HY310; Bluetooth 11/11
mit 0256; Panel des HY310 59,42 Hz. **Offen aus der Reihe:** 2.42 (Ohr, Stock-Vergleich = `restore-stock`), 2.28 (CEC-Quelle +
`HostHDMIMAP` offline), 2.49 Last-Test (Warp + WLAN + Mikro), 2.34 ohne Prio (Marco) - nächster Schritt dort stünde in §2.
**Gelernt:** §3 (TV-Domäne nie über den Standby beobachten); die Box-Kamera sieht den Projektionsrand nicht; der Mint-Sperrbildschirm
ist als Testbild für Farberkennung unbrauchbar.

**Nächstes, in Reihenfolge:** 7.19 (Doku-Runde, vor dem Neubau) → 1.1a (Bauweg heute durchgespielt: frischer Worktree, Submodul-Köpfe
aus dem Haupt-Klon holen, `CRUST_SRC`, `--standby`, Release-Version statt `v0.0-…`) → 1.6/1.7a/1.7 nur mit Marcos Ja je Push → 1.8/1.9.
Daneben, wenn Marco am Gerät ist: 2.65 (IR nach Kaltstart mit Gate 1, jetzt am HY310 möglich), 2.52 (Eingangstaste, Fokusrichtung).
