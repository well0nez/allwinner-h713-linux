# TODO — die eine Liste

**Die einzige Todo-Liste dieses Projekts.** Neue Punkte hierher; erledigte nach §10 — nicht löschen.
Changelog ist [RELEASES.md](RELEASES.md). Letzter Handoff: `doku/209` (13.10. nachts, 5.x-Runde abgeschlossen, alles in `main`). `known-issues.md` und `ROADMAP.md` beschreiben dem Leser,
was nicht geht und wohin es geht — sie führen keine Arbeit. Gestartet 05.10.2026 aus `doku/151`.

## 1 Release — in dieser Reihenfolge

- [ ] 1.1a **Release-Neubau** mit allem seit dem v0.96-Bau vom 05.10. (Baustand `be4f8e1`; der alte Hash `819a09a` ist seit dem
      Identitäts-Rewrite unerreichbar): Kernel 0184/0185 und pwm-sun8i (`5e4475a`), Warp (Zoom, Moduswechsel,
      Stale-Schwelle, Import), EDID-Beschnitt, Panel (Auth, Zoom-Schieber), h713-tv (Aspect zoom), Installer-Texte, die neu
      erzeugte Kernel-Serie; vorher die zwei Patches aus `arbeit/hdcp-wait-env-20261007/patches/` (6.6: U-Boot in den Fork,
      Spiegel `uboot-h713/` neu, `check-hdcp-artifacts.sh`). In einer Kopie, Gerät vorher sichern, Bauverzeichnisse von vorn.
      Dazu das HDCP-Härtungspaket (6.1/6.2/6.5/6.9, `arbeit/hdcp-haertung-20261007/`, enthält 6.6 schon als `uboot/0001`):
      erst per FEL messen (Plan dort §8, BL31 vorher frisch bauen), TF-A und U-Boot nur zusammen; danach `referenz/messregeln.md`
      HDCP und `docs/subsystems/hdcp.md` (eine Schreibung pro Boot, keine Adresse)
      - **09.10.:** `main` trägt seit c4a3924 crust als HY310-Firmware und den Standby (R1, R2). Der Neubau braucht
        `CRUST_SRC` (crust-Klon auf ecf2ddc, bis 5.15) und die Entscheidung 2.29 (mit oder ohne `--standby`)
      - **10.10. später abends:** `CRUST_SRC` ist jetzt der crust-Klon `arbeit/crust-20261007/crust` auf `h713` `54e4a08` (= Kopf in
        `crust-h713/SERIES.txt`, sonst meldet build-all "not reproducible"); der Klon auf `ecf2ddc` (`arbeit/r2-20261009/crust`) ist weg
      - **09.10. abends (Marco, `doku/178`):** das HDCP-Paket kommt ganz mit, 6.5 eingeschlossen - **erledigt 20:xx** (`doku/180`):
        in Forks, Spiegeln und `main`, per FEL gemessen; 1.1a baut es einfach mit
      - **09.10. abends (Marco, 2.29):** mit `--standby` bauen, `power.conf` Vorgabe `short = poweroff` (Standby experimentell,
        per Schalter), Doku und Release-Text sagen "experimentell"; 2.30 ist gemessen und mit Kernel `0245` in `main`; die U-Boot-Zeile
        (`0097`) und der TF-A-Kommentar (`0030`) sind seit `doku/180` in den Forks
      - **12.10. abends, Generalprobe:** `build-all.sh --board hy310 --standby` aus einem frischen Worktree von `main` db558e3 (`CRUST_SRC`
        wie oben) baut in 28 min 48 s ein reproduzierbares Abbild (286 Patches); per FEL auf dem HY310 installiert und gemessen
        (`arbeit/hy310-main-20261012/BERICHT.md`). Der HY310 läuft damit `main`. Bleibt für 1.1a: 7.19 vorher, Release-Version, Tag
- [ ] 1.2a **Z4 zweiter Boot** (~80 s nach Strom-an, Ursache unbekannt, Journal war flüchtig - **06.10.: ist es im
      Abbild weiter**, `10-h713.conf` `Storage=volatile` schlägt `/var/log/journal`, `doku/155` §3): Journal im
      Abbild persistent machen (`/var/log/journal`), ggf. pstore/ramoops, 5 weitere Kaltstarte beobachten
      - 11.10. nachts: der G-EU startete um 04:57 neu, das Journal davor war weg - es war Marco (vor dem Schlafen); ohne ihn
        wäre die Ursache nicht feststellbar gewesen (`doku/196` §3), ein weiterer Grund für das persistente Journal
- [ ] 1.2b **Reinstall über unser Layout verwirft `/etc/h713`** (wifi.env → AP-Modus, warp.conf, keystone,
      tvconfig): der Installer soll die Nutzer-Einstellungen wie die 44 Herstellerdateien zurücklesen und
      übernehmen — oder `build-all.sh --wifi-env` ist Pflicht. Bis dahin: Sicherung vorher (`/root/pre-v096`)
      - 12.10. aus 5.18: dazu einen vom Nutzer geänderten Hostnamen (`/etc/hostname`) mitnehmen
- [ ] 1.3 **WLAN-Timeouts verifizieren** (`82cb57e`): im Abbild drin, 5 Boots je ~9 s bis Finished — der Hängefall
      (Funk absichtlich verklemmen) ist noch nicht provoziert
      - **12.10. provoziert** (G-EU, ein `install`-Hänger in modprobe.d, `arbeit/remote-reihe-20261012/` H): `timeout 30` greift, aber
        systemd wartete danach 90 s auf den hängenden Rest der cgroup - Boot fertig nach 2 min 15 s, ssh ab 127 s. Mit `TimeoutStopSec=10`
        (`c809c23`, in `main`): ssh ab 46 s, fertig nach 54 s. Ins Abbild mit 1.1a
- [ ] 1.6 Forks pushen (Stand 09.10. 20:xx, nach der HDCP-Härtung `doku/180`): U-Boot `h713-hy310` +11 (Kopf `7b1ea388da0d`, lokal
      Zweig `versuch/hdcp-haertung-uboot`: 0096 crust-Ablage, 0097 Gate-Zeile, 0098-0100 HDCP), TF-A `sun50i-h713` +25 (Kopf
      `5a7806892`, lokal `versuch/hdcp-haertung-tfa`: 0007-0027 Standby, 0028-0030 HDCP und Kommentar), sunxi-tools gleich;
      **neu: crust** - der Fork liegt noch nicht auf GitHub (Repo anlegen, Zweig mit 81 Patches auf `499a362`, Kopf `c5b536f` seit 10.10. (G-EU-Konfig), davor `ecf2ddc`,
      lokal `arbeit/crust-mips-drop-20261008/crust` Zweig `versuch/mips-drop`); die Spiegel `uboot-h713/`, `tfa-h713/`,
      `crust-h713/` stehen schon auf diesen Köpfen.
      - **10.10. mittags:** lokal aufgeräumt - `h713-hy310` und `sun50i-h713` auf die Köpfe vorgespult (fast-forward), ihre
        `versuch/*` gelöscht; im crust-Klon der Zweig `h713` auf `c5b536f`. Gepusht wird also der Fork-Zweig selbst. Der crust-Klon
        hat kein brauchbares `origin` (zeigt auf einen gelöschten lokalen Pfad): beim Anlegen des GitHub-Repos neu setzen.
        Noch ausgecheckt in alten Paket-Worktrees und darum stehen geblieben: TF-A `versuch/crust-release-tfa` (enthalten), crust
        `master`, `release-v5` (enthalten) und `versuch/dram-exit-delays` (ein eigener Commit `3206083`, Versuch vom 08.10.)
      Früherer Stand:
      — **vor** `main` (06.10.: Submodul-Remotes per `git submodule sync` wieder auf GitHub - TF-A und sunxi-tools
      zeigten auf einen geloeschten lokalen Pfad; Identitaets-Hooks gelten jetzt auch in den Forks. Der S-EL1-Versuch
      `824eb0bd` ist aus Fork-Branch, Spiegel und Zeiger raus (Marco: "el1 weg, Hauptsache HDCP funktioniert");
      BL31 mit und ohne ihn bytegleich gebaut, `doku/153`; der Beleg-Branch ist seit 07.10. gelöscht - Marco: S-EL1 nicht
      gewollt, `doku/160`)
      Beim selben Push den alten GitHub-Branch `origin/hy300-pro-ab` loeschen (Marco 06.10.: ja; Inhalt ist in `main`, 7.8)
      - **10.10. abends:** TF-A `sun50i-h713` Kopf `1dd0373449df` (0031 Aus über crust), crust `h713` Kopf `d8a8d56f8c46`
        (0082-0087); U-Boot unverändert `7b1ea388da0d` (*überholt:* seit 10.10. später abends `61ea018712c8`, 0101 Kaltstart über crust, `doku/191`). Spiegel `tfa-h713/` und `crust-h713/` stehen auf diesen Köpfen
      - **10.10. später abends:** crust `h713` Kopf `54e4a08ab9f3` (0088 Aus am HY310, `doku/190`), Spiegel `crust-h713/` 88 Patches,
        Baum `4ac41f6b88ee` am Fork-Kopf geprüft. Aufgeräumt: alle Paket-Worktrees und -Klone weg (Inhalt in `main` bzw. den Fork-Köpfen geprüft,
        Klone mit eigenen Commits als Bundle im Paketordner, `referenz/pakete.md`); Zweige `versuch/mips-drop`, `release-v5` (crust),
        `versuch/crust-release-tfa` (TF-A), `versuch/aus-pl6` (Repo) gelöscht, alle enthalten. Es bleibt nur crust
        `versuch/dram-exit-delays` (`3206083`, Versuch vom 08.10., nicht gebraucht - Fehler B waren die Anzeige-Takte, `doku/171`).
        Der crust-Klon `arbeit/crust-20261007/crust` steht auf `h713`
- [ ] 1.7 `main` pushen (06.10. +113, 09.10. 19:00 +199; aktuell `git rev-list --count origin/main..main`)
      - **10.10. (Marco): veröffentlicht wird nur `main`.** Die lokalen Zweige `versuch/*` und `integration/*` (alle in `main`
        enthalten, ohne Upstream) bleiben lokal und kommen weg, sobald der alte G-EU-Worktree weg ist (`versuch/geu-crust` ist dort
        ausgecheckt). In den Forks nur die Zweige, auf die `main`s Submodul-Zeiger zeigen (U-Boot `h713-hy310`, TF-A `sun50i-h713`,
        crust als `h713` aus dem lokalen `versuch/mips-drop`); deren `versuch/*` bleiben lokal. Auf GitHub liegen außer `main` noch
        `master`, `legacy`, `hy300-pro-ab` - **alle drei können weg** (geprüft 10.10.: `master`/`legacy` = Stand 31.08., Vorfahren
        von `main`; `hy300-pro-ab` hat zwei Commits mehr, die nur den U-Boot-Zeiger verschieben, und dessen Ziel `fda5ce0` steckt
        im Fork-Kopf `7b1ea388da0`; der Rest wurde am 06.10. gemessen, 7.8). Löschen = Push, mit Marcos Ja im selben Zug
      - **10.10. mittags:** alter G-EU-Worktree gelöscht (vorher geprüft: Commit in `main`, Arbeitsbaum sauber, Submodul-Köpfe im
        Haupt-Klon, Kernelbaum nur um `0249` anders); die sechs lokalen Zweige `integration/r2-main`, `versuch/{crust-release,
        geu-crust,hdcp-haertung,r2-standby,standby-gate}` gelöscht. In `repo-neu` gibt es nur noch `main`
- [ ] 1.7a **Vor jedem Push: Identitäts- und Leck-Prüfung** (Marco 10.10.: "das wäre beinahe in die hose gegangen" - 23 Commits und
      Spiegel-Patches trugen die private Adresse, ein Kernel-Patch einen Firmennamen, bemerkt kurz vor dem Push). Über **alles, was
      rausgeht**, nicht nur den neuen Teil: `main` und jeder Fork-Kopf (U-Boot, TF-A, crust) samt Submodul-Commits; je Commit Autor,
      Committer, `Co-Authored-By`/`Signed-off-by`, Nachricht; je Datei der Inhalt, auch `From:`-Zeilen der Spiegel-Patches
      (`uboot-h713/`, `tfa-h713/`, `crust-h713/`) und `mainline/patches/`. Gegen: private Adresse, Arbeitgeber-/Firmenname, Klarname
      (die Liste außerhalb des Repos, `sperr-scan.py` Regel 8), dazu Seriennummern/MACs. Nach dem Push gegen einen **frischen Klon**
      wiederholen (Gedächtnis "Identität in veröffentlichten Repos"). Erst dann gilt der Push als fertig
- [ ] 1.8 `RELEASES.md`: neuer Abschnitt; Release-Tag; Baustempel - darin die Fernbedienung und die Einblendungen (`h713-keys`,
      `h713-osd`, `doku/193`/`195`) statt "nothing acts on the remote's keys yet except Power" (7.18)
- [ ] 1.9 `docs/known-issues.md` Zeile „HY300 Pro dunkel" nach test10-Foto

## 2 Am Gerät offen (keine Blocker, aus `144` §2 und known-issues)

- [ ] 2.4b **Warp kennt kein Seitenverhältnis:** zieht jede Quelle auf das Quad; 4:3-Quellen
      (1024×768, 1280×1024, 576p) werden mit Warp breitgezogen, ohne Warp pillarboxt die Firmware.
      Fix: Letter-/Pillarbox im Quad aus dem Capture-Format (h713-warp), noch nicht gemessen
- [ ] 2.4d Prüfstand-Kleinfunde (BERICHT §2.2–2.12) — **erledigt 05.10.:** `ctl status` wirft den Warp ab
      (Frist 1000 ms), Journal-Spam ohne Signal, `test mask` markiert tl, Firmware-Zoom im Warp-Commit
      (h713-tv-0001 + 0183). **Offen:** laxe `atoi`-Prüfung bei zoom/edge, `check` halbiert fps
      (dokumentieren), Musterwechsel = Konsolenblitz, Client ohne Newline blockiert 500 ms,
      `evaluate()` gibt bei -ENOLCK sofort frei, Textreste „primary plane"
      - **12.10.** (`arbeit/remote-reihe-20261012/` G): `atoi`, Client ohne Zeilenende (500 ms -> keine Lücke über 20 ms) und die Texte in
        `main` (`62d1887`), am G-EU gemessen. `evaluate()` bei -ENOLCK gebaut (Zweig `versuch/warp-reste` `f089cdd`), aber in 9 Versuchen
        nie ausgelöst (HDCP-Neuanforderung wirft den Warp gar nicht ab) - nicht in `main`. Offen: `check` halbiert fps, Musterwechsel
- [ ] 2.28 **Physische Adresse im HDMI-VSDB** (war 2.26 auf `versuch/crust-release`, Commit 9d95b89): crust schreibt für Port 0/1/2 1.0.0.0 / 2.0.0.0 / 3.0.0.0, der Blob 0.0.0.0 /
      2.0.0.0 / 0.2.0.0 (gemessen 07.10., `doku/163`). Von Belang nur für CEC und AV-Receiver in einer Kette. Offen: die
      Formel des Blobs aus seinem `HostHDMIMAP` lesen; in Stufe A0 einmal mit einer CEC-fähigen Quelle prüfen

- [ ] 2.34 **Grüner Streifen auf der Konsole** (Marco 10.10. nachts): kurz nach dem Booten links, nach dem Aufwachen aus dem
      Standby rechts, geht von selbst weg; HY310 und HY300PRO-G-EU. Ursache offen (Marco: DRAM? - ein alter Bildspeicher-Inhalt,
      bevor der erste Frame steht); nicht dringend
      - **12.10. abends (HY310, `arbeit/hy310-main-20261012/` §3):** Marco: "immer grün beim Warpen, egal ob Standby oder nicht; die
        Konsole hat grüne Streifen mal links, mal rechts, wenn's aus dem Standby kommt" - **keine Prio, bleibt TODO**. Gemessen: Grün =
        YUV-Puffer ohne Inhalt (Y=U=V=0; der Code nennt es selbst so, h713-tv `display_create_fb`, h713-warp `warp_engage`); nach dem
        Aufwachen geht die Ebene im Bypass auf **volle** Ringplätze (3 Läufe, `ebene-wach.py`), der erste Warp-Puffer ist beim Flip
        gefenct (afbd nutzt `drm_atomic_helper_commit`). Offen: Inhalt des ersten Warp-Puffers (nicht über `/dev/mem` lesbar), die
        Konsolen-Streifen (`/dev/fb0` direkt nach dem Wecken). Die Box-Kamera sieht den Rand nicht - kein Messmittel dafür
- [ ] 2.42 **Netzteil fiept auch im Aus über crust** (Marco 10.10. abends, HY310, Lauf `hy2`): im Standby fiept es leise (2.31),
      im Aus über crust ebenso. Mit dem Stock-Abzug gegenhalten (Stock-Android aus: fiept es da auch?) - erst dann ist es ein Befund
      über unser System oder über das Netzteil bei kleiner Last
- [ ] 2.45 **Regel: wer auf Kanal 2 zeichnet, zeichnet verzerrt - Vorplanung Desktop** (`doku/192` §5.3-5.4): ein späterer
      Compositor setzt die Trapez-Matrix als letzten Durchgang und zeichnet die Einblendung davor; Kanal 2 gehört dann dem Desktop
      (Alpha je Bildpunkt über der Video-Ebene); Zeichnen und Ausgabeort trennen; DRM-Master heute `h713-tv`, später der
      Compositor - nichts dauerhaft an `h713-tv` binden; fbcon bleibt unverzerrte Notfallkonsole, die Alltags-Konsole wird ein
      Terminal im Desktop (ersetzt 2.7a, sobald der Desktop kommt)
      - 11.10.: vorbereitet - Zeichnen (`libh713osd`) und Ausgabe (`h713-osd` + Kanal in `h713-tv`) sind getrennt, die Matrix eine
        Bibliothek (`libh713geom`); `docs/architecture.md` "The display stack". Der Desktop selbst steht aus

- [ ] 2.65 **Frage (Marco 12.10.): weckt IR auch aus dem Aus über crust, wie aus dem Standby?** Am HY310 bestanden (`doku/190`: Taste,
      IR, Selbstwecken), am G-EU "Taste oder Fernbedienung weckt" (`doku/188`). Mit dem Kernel aus `main` 234282c am G-EU nachmessen,
      je einmal: Standby -> IR-Power; Aus über crust -> IR-Power; dabei 2.40 (`0257`) im Log des Starts danach ansehen (Info statt
      Warnung). Braucht Marco vor Ort (IR)
      - 12.10.: IR weckt aus dem Aus über crust (Marco, `doku/204`). **Offen, Marcos eigentliche Frage:** IR nach einem Kaltstart,
        wenn das Gate (`h713_gate=1`) auf die Taste wartet - der G-EU steht derzeit auf Gate 0, HY310 auf 1
- [ ] 2.51 **Mikrofon der Fernbedienung hörbar machen** (11.10., `doku/193` §3): per Bluetooth kommt beim Halten ein Tonstrom
      (60-Byte-HID-Berichte, ~63/s, ~3,8 kB/s), Format unbekannt - kein IMA-ADPCM, kein fester Kopf, komprimiert. Codec aus der
      Sprach-App/dem Audio-HAL der Stock-Firmware bestimmen, dann `CONFIG_HIDRAW` und ein Dekoder in Userspace. Nicht dringend
      - 11.10. G-EU (`doku/195`): ~125 Pakete/s (≈7,5 kB/s), doppelt so viele wie am HY310 - vielleicht eine andere Abtastrate;
        Nutzdaten in `arbeit/einblendungen-geu-20261011/laeufe/mikro-geu/handle34.txt`
      - 11.10. abends: der HY310 liefert ebenfalls ~125 Pakete/s (die ~63/s zählten die Pause mit); 60 Byte je 8 ms passen genau
        auf SBC mono 8 Subbänder/16 Blöcke/Bitpool 26 bei 16 kHz. Marco: Mikro und Maus jetzt interpretieren und vorbereiten, die
        Maus bedient später Desktop/Apps; Codec in den Stock-Bibliotheken suchen (lesend) erlaubt
      - **11.10. abends: Maus erledigt** - im Mausmodus `REL_X`/`REL_Y` (~90/s) und OK als echter Linksklick (`BTN_LEFT`, im
        Mausbericht Byte 0 Bit 0, btmon Handle 0x38), außerhalb OK = `KEY_SELECT`; die Maus-Taste selbst sendet nichts. Für einen
        Desktop ist nichts zu tun. **Mikro offen:** kein ATV-Voice-ADPCM (kein Zähler, Codes gleichverteilt), Byte 0 hat nur 37
        Werte und wandert langsam (Kopf-/Parameterbyte). Nächster Schritt: die Sprachkomponente aus dem Stock-`super` lösen
        (Marco: lesend erlaubt) und den Codec dort nachlesen
- [ ] 2.52 **Tasten, Reste aus 2.46** (11.10.): welche Taste die Eingangsumschaltung HDMI/Konsole bekommt (Marco; `keys.conf`
      `input_keys`, leer); welche Richtung "Fokus hoch" an der Wand fährt (beide Lesarten gesehen); ob die BLE-Fernbedienung beim
      Halten wiederholt (dann fährt der Fokus durch wie per IR)
      - 11.10. G-EU (`doku/195` §2): **ja, sie wiederholt** - aber alle ~40 ms (Softwarewiederholung des Kernels), per IR ~130 ms; die
        Lautstärke rast beim Halten. Angleichen: `EVIOCSREP` auf dem BLE-Gerät oder in h713-keys drosseln. Dazu: **OK kommt per
        Bluetooth als `KEY_SELECT`** (HID "Menu Pick", 353), per IR als `KEY_OK` - h713-keys soll beide als OK lesen
      - 11.10. nachts gebaut (`doku/196` §1): `EVIOCSREP` 500/125 ms für die Bluetooth-Fernbedienung (wie IR), `KEY_SELECT` =
        `KEY_OK`; Rechner-Tests 22/22. **11.10. früh gemessen** (Marco hielt Lauter/Leiser per Bluetooth: erste Wiederholung
        nach ~510 ms, dann alle 132 ms wie per IR, Marco: "bt funktioniert") - in `main` (`fc04088`). Offen in 2.52 nur noch:
        Eingangstaste, Fokusrichtung an der Wand
- [ ] 2.53 **Einblendungen: Feinschliff, optional** (11.10.): Ausblenden in Stufen statt schlagartig; das Stumm-Zeichen in stark
      gestauchten Bildecken schärfer (Mehrfachabtastung beim Vorverzerren); die Einblendungen am G-EU (720p) am Gerät ansehen
      (**11.10. erledigt**, `doku/195`: Lage und Größe passen, Marco)
- [ ] 2.54 **Knopf im Panel: "Fernbedienung neu koppeln"** (Marco 11.10.: "kein Fehler, als TODO hinterlegen, Button ins Panel
      re-pair remote - das reicht"; `doku/195` §4): `h713-remote-pair watch` koppelt nur, wenn gar keine Fernbedienung bekannt ist,
      und löscht einen Bund mit Absicht nie (eine schlafende Fernbedienung soll ihn behalten). Ist er veraltet - die Fernbedienung
      merkt sich nur eine Box, an einer anderen gekoppelt -, scheitert jedes Verbinden. Der Knopf in `h713-panel` ruft
      `h713-remote-pair forget`; der laufende Dienst sucht dann von selbst und koppelt, sobald Links+Rechts gehalten wird -
      **am G-EU 11.10. 02:40 so gemessen** (forget → gekoppelt und verbunden in Sekunden, `arbeit/einblendungen-geu-20261011/`).
      Dabei mitnehmen: `h713-remote-pair` schreibt unter systemd die Erfolgszeilen ("found", "ok paired") gepuffert und damit nicht
      ins Journal (nur die Fehler, stderr) - Zeilenpuffer setzen (**11.10. nachts erledigt**, `71e0fd0`)
      - **11.10. abends (Marco):** dazu alles, was heute nur per Kommandozeile geht, ins Panel - **WLAN eingeschlossen** (UART ist
        der Rückweg); nicht: SSH-Schlüssel, `focus_command`, `rpc`. Der Knopf zeigt auch auf dem Gerät ~10 s einen Hinweis.
        Lautstärke/Stumm bleiben **ungespeichert** (Marco: auf keinen Fall)
      - **11.10. nachts: verworfen (Marco: "extrem unübersichtlich", "debug optionen ... einfach so direkt mit allem
        vermischt")** - ein Agent baute alle Einstellungen in Reiter mit langen Listen, Diagnose und Expertenwerte zwischen den
        Alltagsreglern; am G-EU gesehen und sofort zurückgespielt (`/root/sicherung-panel-einstellungen/`). Geparkt, lokal:
        Zweig `versuch/panel-einstellungen` (`arbeit/panel-20261011/`, 72 Tests, WLAN mit 120-s-Rückfall, Hostname über
        hostnamectl - die Technik ist brauchbar, die Seite nicht). Neu nur mit **Mockup zuerst**: Alltagsregler vorn, Debug und
        Expertenwerte getrennt, Gefährliches (WLAN, Aus) mit Rückfrage
      - Marco dazu (12.10. nachts): **die vielen Optionen sind gewollt** ("find ich geil"), aber gruppiert, **jede Gruppe ein
        eigenes Menü**, nicht zusammengewürfelt; das Design der Agentenfassung ist "abgrundtief schlecht". Ursprünglich gemeint war
        nur der eine Knopf "Fernbedienung neu koppeln" - der Rest ist der Wunsch "alles, was nur per Kommandozeile geht, ins Panel"
      - **12.10. nachts (Marco): der Panel-PR** aus `well0nez/h713-panel-dev` (Neugestaltung in sechs Bereichen, Server = die verworfene
        Fassung vom 11.10.) ist auf `versuch/panel-redesign` (e7598aa, `arbeit/panel-redesign-20261012/`) mit Unit und Doku der Referenz;
        gelesen, 72 Tests grün. Im Testabbild `runde5x1` zum **Ansehen** - nach `main` erst nach Marcos Ja. Offen: `docs/guides/settings-page.md`
      - 12.10. aus 5.18: der Hostname gehört zu den Einstellungen, die im Panel änderbar sein sollen
      - **13.10. in `main`:** das neue Panel (PR aus `h713-panel-dev`, Server mit allen Befehlen, Unit mit `/etc/hosts` und den
        h713-logs-Pfaden), die Beamer-Begriffe zurück (Sonnet-Agent, `arbeit/panel-wording-20261012/`), die Off..High-Reihen zeigen den
        echten Wert (der Server suchte unter den Kurznamen). Marco am Gerät: "passt". Offen: `docs/guides/settings-page.md` und
        `docs/tools/h713-panel.md` auf die neue Seite (7.19); die Ecken zeigen ihr Maximum nicht mehr, der Chip "picture" fehlt
- [ ] 2.66 **Nach dem Standby zweimal 0 Bilder/s gezeigt, obwohl h713-tv "plane on" meldet** (12.10., G-EU, 20 Standbys per RTC,
      Quelle ThinkPad, `arbeit/remote-reihe-20261012/` C): `anzeige.py` 4 s, ~10 s nach ssh, in st6 und st18 0,00 Wechsel/s, die anderen
      18 bei 59,6-59,8; der jeweils nächste Standby wieder normal. Ungeklärt, ob zu früh gemessen (Skript- und Journalzeit gingen über die
      Suspend-Zeit nicht sauber auf) oder ein echter Stillstand. Nächster Schritt: nach jedem Aufwachen 30 s `anzeige.py` mit Zeitstempel
      in CLOCK_MONOTONIC wie das Journal, dazu Augen an der Wand
      - Marco 12.10.: vielleicht hat der ThinkPad wieder nichts gesendet (wie die Stillstände mit `rustdesk --server`, `referenz/geraete.md`)
        - nicht sicher; **den Test nach dem Release wiederholen**, dann mit einer zweiten Quelle (Fire TV) als Gegenprobe

- [ ] 2.70 **Watt im Standby am HY300PRO-G-EU** (aus 1.4, 12.10.): mit crust, Lüfter aus (PB5 beim Board-Manager) - mit dem
      Messgerät an der Steckdose; am HY310 zum Vergleich der Wert aus `doku/188`
- [ ] 2.71 **`h713-bt-reset` am HY300PRO-G-EU** (aus 1.4, 12.10.): dort nie probiert; ein Warmstart mit und ohne den Reset vorab,
      `hci0` UP RUNNING beim 1. Versuch zählen (wie 2.49 am HY310)
- [ ] 2.72 **GPU-Takt (0268-0270) am HY300PRO-G-EU nachmessen** - am HY310 bestanden (13.10.2026, `arbeit/medien/A-takt/BERICHT.md`: A1 halbiert, A2 150/200/300/600 MHz
      exakt, A3 2,49 ms bei 600, A4 45 min GPU-Zone max 55 C), am G-EU nicht gemessen und nicht eingebaut. Dasselbe Skript `arbeit/medien/A-takt/takt.sh` mit `H=root@<G-EU-Adresse aus referenz/geraete.md>`
      (Pfade prüfen: `hwmon` des Lüfters, `thermal_zone`-Reihenfolge, Warp-PID). Tests: A1 vorher (Soll 0,5 +-0,05, sonst anderes CCU-Verhalten), A2 nachher (599/299/199/150 +-2 %),
      A3 (`h713-warp ctl trace`; **720p-Panel**, Zeit je Bild anders als am HY310), A4 verkürzt auf 15 min (GPU-Zone < 85 C, dmesg leer; anderes Gehäuse und Lüfter),
      A5 über die Register. Vorher Sicherung `/root/sicherung-takt-geu/` und den Rückweg (`/boot/h713-kernel.fit.alt`, `/lib/modules/6.18.38.alt`) bereitstellen.
      Bestanden: Eintrag nach 10. Nicht bestanden oder Hitze: nur den OPP-Satz ändern (`0269`), `0268`/`0270` bleiben.

## 3 Geparkt — mit Wiedereinstiegsbedingung

- [ ] 2.59 **Panel-Pixeltakt näher an 60 Hz** (11.10. abends, Marcos Frage nach dem Rest von 0,3 Sprüngen/s): das Panel läuft mit
      59,71 Hz (1360×760 bei 61,71 MHz aus U-Boot, PLL 24 MHz × N / 14, N = 36), eine 60,00-Hz-Quelle verliert damit ein Bild in 200
      (`doku/200` §4); Stock nennt `pclk 62000000` (= 59,98 Hz). Prüfen, ob die Panel-PLL einen anderen Teiler kennt (`h713_mips.c`,
      `doku/197` §3) oder ob 62 MHz anders erreichbar ist; Messung mit `anzeige.py` (Sprünge/s → ~0,02). Nur mit Augen an der Wand
      (`doku/199`: Timing-Änderungen können flackern/abdunkeln)
      - **11.10. geparkt:** Marco: Sinn fraglich (ein Bild in 200, Risiko Panel-Timing) - nach dem Release, wenn überhaupt; genau 62 MHz geht mit ganzzahliger PLL nicht, Ausweg wären feste Totale (1357×758 → 59,998 Hz)
- [ ] 2.61 **Warp-CPU je Bild: ein Batch statt zwei** (11.10. abends): 2 × ~125 µs Batch-Aufbau + 4 GPU-Jobs je Bild; Luma und
      Chroma in einem R8-FBO (Höhe 1,5) als zwei Draws (nicht T1e's einer), Chroma-Fragment je Byte mit dFdx-Snap auf die Paarmitte;
      ~−150 µs CPU, +25 % GPU (1,8 → ~2,3 ms). Nur mit Augen an der Wand und T1-Tests; vorher 2.60
      - **11.10. geparkt:** nach 2.60 läuft die CPU fast immer bei 480 MHz, Gewinn ~0,5 Prozentpunkte gegen mehr GPU-Last und das Kantenrisiko von `versuch/warp-einpass`; wieder aufmachen, wenn die Warp-CPU nachweislich stört
- [ ] 3.5 `Reserve0_a/b` und `private` von einem **unangetasteten** Gerät abziehen (bei uns überschrieben) (aus `61`)
- [ ] 5.1 ST3-RESTORE F1: Schema-Feld `layout.disk_sectors_from = unit|image` statt Heuristik
      - **12.10. geparkt (Marco):** die Heuristik `_size_is_a_units` (`h713-install`) arbeitet und ist getestet; betrifft nur
        `restore-stock` auf fremden Boards. Wieder aufmachen, wenn ein Profil sie falsch beantwortet

## 4 Boards und Fremdgeräte

- [ ] 4.1 `hy300-pro` (Issue #1): test10 aus `main` nach dem Release (0168, 0182, 2de0cc8, Gamma, project 0x34)

## 5 Installer und Werkzeuge

- [ ] 5.14 **Reste der Durchsicht des Standby-Codes** (`arbeit/review-r2-20261009/FUNDE.md`, alle minor/info): CC-1 (Neustart mit
      Zeitüberschreitung öffnet die Aufrufe), CC-3..CC-6, U2 (abgebrochener Standby zählt als verweigert), U3..U6 (hdcp-key-Reste,
      Sperre, kein Zeitlimit für den Neustart), TFA-R2-1/2 (Zeitgutschrift ab Überlauf, R_WDOG-Meldung), CR-3 (50 ms ohne WFI-
      Prüfung), CR-4 (MIPS_DROP zählt Aux-Abweisungen), B2/B4 (Standby-Abbild nur per Text erkennbar, spätere sleep-Drop-ins), KM-3/4
      - **12.10. gegen den heutigen Code geprüft und entschieden (Marco, Durchsicht 5.x):** keiner der Funde ist nebenbei behoben.
        - **abgehakt:** B2 (überholt - der Standby kommt experimentell ins Release, 2.29/3.3), CR-4 (im Review widerlegt, Absicht und so
          beschriftet), KM-4 (der Test liegt nur im alten Paket, nicht im Repo)
        - **jetzt:** das Banner in `build-all.sh` mit `--standby` ("not a release before TODO 3.3", C1, kein Ton, Wecken ungemessen -
          alles überholt); CC-3 (Meldung nennt -ENODEV, Aufrufer bekommen -EBUSY); TFA-R2-2 (R_WDOG zurücklesen, Text nur bei Erfolg
          "stopped") **vor dem Push 1.6**; U2 (Abbruch durch Weck-Ereignis -> anbleiben, nur echte Verweigerung schaltet aus,
          `last_failed_errno`); U5 (scheitert `h713-hdcp-key`, den Empfänger einfach binden - Bild ohne HDCP 2.2 statt keins); U6
          (Zeitgrenze 120 s für h713-mips-restart); CC-1; CC-6; U3; B4
        - **nach dem Release:** CC-4, CC-5, U4, CR-3, KM-3
        - **gestrichen:** TFA-R2-1 (falsche Zeitgutschrift erst nach 49,7 Tagen Schlaf am Stück)
        - **12.10. in `main`** (Paket `arbeit/werkzeuge-20261012/`): Banner (07a9355), B4 (b79df7e, 7f6c2f2: `check-crust.py` wertet alle
          `sleep.conf` und Drop-ins aus, `build-rootfs.sh` lehnt fremde Drop-ins ab). Dabei gefunden und behoben (Marco: behalten):
          `check-crust.py` verlangte ohne `--standby`, dass `h713-power` fehlt - seit 2.38 ist es auf jedem Abbild, jeder Bau ohne
          `--standby` wäre in Schritt 10 gescheitert
        - **12.10. abends, Schritt 2 auf `versuch/dienste`** (`arbeit/dienste-20261012/`, nicht in `main` bis zur Gerätemessung):
          U2 (243ef22, über `pm_wakeup_irq`, braucht `CONFIG_PM_DEBUG`), U6 (6f5db52, 120 s), U5 (495b1c8 + 68ba120), U3 (169e98a);
          Rechner-Tests grün, Gegenproben gegen die alten Fassungen scheitern
        - **Rest aus 5.16, zweitgeprüft 12.10. abends:** gilt noch, und **U2 macht ihn zum Normalfall** - der zweite Tastendruck beim
          Einschlafen bricht am Anfang von `suspend_late` ab, vor dem Park; `msp_resume` setzt blind `error`, obwohl `pd_tvfe` nie
          abgeschaltet war, niemand baut den DSP neu auf: Bild an, Ton weg. **Entschieden (Marco): Wurzel im Kernel** - `msp_resume`
          liest Routerwort und Taktbit des Audio-Top und baut bei intakter Insel selbst neu auf. Schritt 3; nachstellbar mit
          `pm_test=devices`
        - **12.10. nachts, Schritt 3 auf `versuch/kernel`** (`arbeit/kernel-20261012/`): Kernel `0263` (CC-1), `0264` (CC-3), `0265`
          (CC-6), `0266` (msp misst den Stromverlust), `CONFIG_PM_DEBUG=y`; gebaut, W=1 ohne Warnung. **Schritt 4 TF-A** auf dem Fork-Zweig
          `versuch/wdog-readback` 287dca2fe (TFA-R2-2, `arbeit/tfa-wdog-20261012/`): BL31 gebaut, gleich groß wie der unveränderte Kopf,
          nur die zwei Texte anders; nicht gespiegelt. Alles im Testabbild `runde5x1` (Zweig `versuch/testabbild`)
        - **12.10. 23:00-23:21 Teil A am HY310** (`arbeit/testabbild-20261012/MESSPLAN.md`, Ergebnis dort): `runde5x1` installiert;
          Arbeitskopie gelöscht, Abzug gehört dem Nutzer, `v4l2-ctl` da, Hostname, `pm_test=devices` -> DSP neu aufgebaut (0266),
          10/10 Standbys (DSP 10/10 im 1. Versuch), U5 per Bind-Mount bestanden, 5/5 Warmstarts. CC-3 nicht beobachtbar.
          **Offen Teil B mit Marco:** zweiter Tastendruck (U2), Ton, Panel ansehen, ARISC hin/zurück, R_WDOG nach Aus über crust
      - **13.10.: in `main`** - Banner, B4, CC-1, CC-3, CC-6, U2, U3, U5, U6, TFA-R2-2 (TF-A 287dca2fe, Spiegel 32), der msp-Rest (0266);
        Teil A und B am HY310 bestanden (`doku/209`). **Offen bleiben nur die Punkte nach dem Release:** CC-4, CC-5, U4, CR-3, KM-3.
        Gelernt (B2): der zweite Tastendruck beim Einschlafen landet bei crust und weckt sofort (860 ms) - ein Abbruch entsteht am
        HY310 so nicht; U2 bleibt die Absicherung für andere Weck-Interrupts
- [ ] 5.15 **crust als Submodul** (`mainline/external/crust`) statt `CRUST_SRC`: sonst kann niemand außer uns ein HY310-Abbild bauen;
      braucht den veröffentlichten Fork (1.6)
      - 12.10. geprüft: `build-all.sh` sucht schon in `mainline/external/crust` (Z. 181), es fehlt nur das Submodul; `well0nez/crust`
        gibt es auf GitHub noch nicht. Vorschlag: vorbereiten, Commit erst mit dem Push 1.6 - **Entscheidung Marco offen**
- [ ] 5.16 **Reste der Doku-Runde 09.10.** (`2f7875f`, Entwürfe und Notizen in `arbeit/doku-r2-20261009/*/NOTIZEN.md`):
      Commit-Texte beim nächsten Serienumbau - `0231` nennt V10 "three times in a row" (nicht belegt, `doku/176` §1), `0240`
      sagt "not yet measured" (gemessen, `doku/173`), `0243` sagt "until a reboot" (siehe 3.3); Lüfterdrehzahl 4860
      (`hardware.md`, `board-mgr.md`) / 4770 (`known-issues.md`) / ~4800 (`0222`) vereinheitlichen; Größe des
      Hersteller-ARISC-Abbilds 140 KiB (`arisc.md`) gegen ~172 KB (`hardware.md`); `known-issues.md` "fix pending" beim
      720p-Warp-Fall gegen `0183` prüfen; `docs/uboot/README.md` "0096 is not published yet" nach dem Push (1.6) streichen;
      R_WDOG als Netz im Schlaf in `standby.md`. Aus dem Code gelesen, nicht gesehen: bricht ein Standby nach
      `msp_suspend`, aber vor dem Park ab, bleibt msp auf "error" und `h713-mips-restart` läuft nicht (nur bei "parked")
      - Ton bis zum Neustart weg; gehört zu 5.14.
      - 11.10. nachts erledigt (`77c8920`): 720p+Warp in `known-issues` (durch 0183 behoben), Lüfterdrehzahl, ARISC-Größe; R_WDOG
        stand schon in `standby.md`. Offen: die Commit-Texte (nächster Serienumbau), `docs/uboot/README.md` (nach 1.6)
      - **12.10. (Marco: ok):** die Commit-Texte von `0231` (1 Stelle), `0240` (1), `0243` (2) jetzt mit dem Kernel-Paket;
        `docs/uboot/README.md` Z. 65-66 (nennt noch den Kopf `7b1ea388da0d`, heute `61ea018712c8`, und "unveröffentlicht") nach 1.6
      - **12.10. nachts:** die drei Commit-Texte auf `versuch/kernel` (96a92a3); `docs/uboot/README.md` bleibt für nach 1.6
      - **13.10.:** die Patch-Texte 0231/0240/0243 sind in `main`; offen nur `docs/uboot/README.md` nach 1.6
- [ ] 5.17 **`build-all.sh` muss nach einem Abbruch weiterbauen können** (Marco 09.10.: "nicht entwicklerfreundlich"). Anlass:
      G-EU-Testbau 09.10. stieg in Schritt 7 (Rootfs) aus, nach ~25 min Kernel/Mesa/Sysroot; danach lief alles von vorn, und
      eine Kommentaränderung im Gerätebaum-Patch kostete den Kernel noch einmal. Heute gibt es `--skip-bl31/-uboot/-kernel/
      -rootfs`, die nur "wenn vorhanden" prüfen, nicht ob es zum Stand passt. Vorschlag: jeder Schritt schreibt einen
      Eingabe-Stempel (wie der Kernelbaum schon über den Eingabe-Hash und die Sysroot über den Paketstempel), `--resume`
      nimmt fertige Schritte mit passendem Stempel und baut ab dem ersten abweichenden; Release-Bauten bleiben ohne
      `--resume` von vorn (Regel "Release-Bauten immer von vorn"). Dazu: ein reiner Kommentar im Patch sollte den
      Kernel nicht neu bauen müssen (Hash über den Inhalt ohne Kommentar ist heikel - erst abwägen)
      - 10.10. nachts: auch ein `make Image.gz` von Hand im fertigen Kernelbaum eines build-all-Laufs (eine geänderte Datei,
        pinctrl PF6) übersetzte alles neu (>1100 Objekte) - die Schalter/Umgebung des Baus sind von außen nicht nachstellbar;
        `build.sh kernel` sollte einen "nur bauen, nicht neu konfigurieren"-Weg für einen vorhandenen Baum haben
      - **ENTSCHIEDEN 10.10. abends (Marco: "der installer ist schon kompliziert genug ... noch mehr parameter adden?"):
        keine neuen Parameter, Weiterbauen geschieht von selbst.** Nächstes Paket nach den `geuaus1`-Kurztests, vor 5.20.
        1. Jeder Schritt schreibt nach Erfolg einen Stempel `mainline/build/stempel/<schritt>`: Hash seiner Eingaben (Bäume der
           Submodule bzw. des crust-Checkouts, Patchserie, Defconfigs/Fragmente, Board/Variante, Schalter wie `--standby`,
           `--test-image`, `--version`, die Prüfsummen der Ergebnisse seiner Vorstufen) und die Prüfsummen seiner Ergebnisse.
        2. Jeder Lauf prüft die Stempel und übernimmt einen fertigen Schritt nur, wenn Eingabe-Hash und Ergebnis-Prüfsummen
           stimmen; ab dem ersten abweichenden wird gebaut - spätere Schritte fallen über die geänderten Vorstufen-Ergebnisse
           von selbst mit. Ein Abbruch: denselben Befehl noch einmal, er macht dort weiter.
        3. `--skip-bl31/-uboot/-kernel/-rootfs` **entfallen** (sie prüfen nur "vorhanden", nicht "passend") - vier Parameter
           weniger. Der Stempel des Abbilds nennt ehrlich, welche Schritte übernommen wurden; "reproducible: yes" nur, wenn
           jeder übernommene Schritt aus demselben Commit stammt.
        4. Release-Bauten bleiben von vorn ohne Schalter: aus einem frischen Klon, der keine Stempel hat (Regel "Release-Bauten
           immer von vorn", `RELEASES`-Ablauf 1.1a).
        5. Kernel: ein geänderter Patch baut den vorhandenen Baum inkrementell nach, statt ihn neu auszupacken, wenn nur
           Dateien der Serie sich geändert haben (abwägen: sicher nur, wenn die Serie bis zum geänderten Patch gleich ist;
           sonst wie heute neu). Der Weg "nur nachbauen, nicht neu konfigurieren" für `build.sh kernel`.
        6. Messen: ein Lauf abbrechen (z. B. in Schritt 7), neu starten -> nur ab 7 gebaut, Abbild bytegleich zu einem Lauf
           von vorn; eine Kommentaränderung in einem DTS-Patch -> nur Kernel(-DTB) und Folgeschritte; ein unverändertes
           Zweitlauf -> nichts gebaut, Abbild bytegleich. Den Installer auf dem Gerät (`h713-install`) fasst das nicht an.
      - **12.10. (Marco, Durchsicht 5.x): nach dem Release, aber unbedingt.** Geprüft: noch nicht angefangen (die vier `--skip-*`
        stehen, kein `stempel/`). Vorschlag dazu: Punkt 5 (Kernel teilweise inkrementell) zurückstellen - der riskante Teil, und den
        häufigsten Fall fängt der Kernel-Cache über den Eingabe-Hash schon ab

## 6 HDCP-Härtung — Einbau mit dem Release-Neubau 1.1a (`doku/144` TEE-1…5, `doku/161`)

**Erledigt 09.10. abends (`doku/180`):** das ganze Paket ist in Forks, Spiegeln und `main` und per FEL gemessen; 1.1a baut es
mit. Die Einzelpunkte stehen jetzt in 10, der Verlauf bleibt hier.

**Stand 09.10. (geprüft im Code):** 6.3, 6.4, 6.7, 6.8 erledigt bzw. gestrichen. 6.1, 6.2, 6.5, 6.9 und 6.6 sind **vorbereitet,
nicht eingebaut, nicht gemessen**: TF-A `175c6948f` trägt noch das BL32-Gerüst (`H713_WITH_BL32`, `H713_BL32_AARCH32`) und
keinen `HDCP14_STAGE`/`HDCP14_ONCE`, U-Boot `87b2a44` noch `h713_hdcp14_wait`. Die TF-A-Patches des Pakets stehen auf
`4c1bd8c6`; vor dem Einbau auf `175c6948f` (21 Standby-Commits darüber) nachziehen, bauen, per FEL messen (Plan im Paket §8).
**09.10. abends geprüft (`doku/175`):** TF-A 0001/0002 kollidieren mit den 21 Standby-Commits (`sunxi_bl31_setup.c`,
`platform.mk`), U-Boot 0001-0003 passen, Repo 0002 nicht. HDCP 1.4 übersteht Standby und MIPS-Neustart (gemessen) - eine
Schreibung pro Boot bleibt richtig.
**09.10. abends entschieden (Marco, `doku/178`):** das ganze Paket mit 1.1a, 6.5 eingeschlossen (6.5 ändert nur den Weg - Treiber statt fester
Register -, nicht das Verhalten; die Einschätzung "eher überholt" in `doku/175` §4 war falsch). TF-A 0001/0002 vorher auf `175c6948f` neu aufsetzen.

**Erledigt 09.10. abends (`doku/180`, Paket `arbeit/hdcp-haertung-20261009/`):** 6.1, 6.2, 6.5, 6.6, 6.9 in den Forks (TF-A
`5a7806892`, U-Boot `7b1ea388da0d`), Spiegel und `main`; per FEL am HY310 gemessen: T0 (12 s Watchdog, kein BL32, 4 CPUs),
T1/T2 das Paar aus der Ablage (Desired, dann Enabled nach 2 s), T3 zweite Übergabe im selben Boot abgewiesen, T4 Verschluss
ohne Schreibung. Die eMMC der Box trägt es mit dem nächsten Abbild (1.1a). T5 (fremder Watchdog) nicht gelaufen.

## 7 Dokumentation und Repo

- [ ] 7.14 Deutsch in Code → Englisch: Kommentare in Modulen/Patches ab `0146` (aus `61`; Nutzer-Sichtbares ist durch)
- [ ] 7.15 Wissensdatenbank: `doku/` + `analyse/` je Teilsystem destillieren — **läuft** (referenz/, MemPalace, Graphify)
      - 12.10. nachts: MemPalace und Graphify ausgebaut (8.2) - es bleiben `referenz/` und das Journal
- [ ] 7.16 Testskripte veröffentlichen — Auswahl, was ohne unseren Tisch läuft (aus `61`)
- [ ] 7.17 Fotos: Standbilder der projizierten Bilder (ROADMAP „Pictures")
- [ ] 7.19 **Doku-Runde: die Neuerungen auf beiden Geräten** (Marco 10.10.): seit R2 kamen dazu - HY310: dunkles Gate nach
      missglücktem Standby (0245), HDCP-Härtung, Leistung; HY300PRO-G-EU: crust, Standby, Panel-Zyklus, PB5 (0246-0249,
      `doku/182`/`184`/`185`). Nachziehen: README (Board-Liste: G-EU-Status), `docs/README.md`, `STATUS.md`, `ROADMAP.md`,
      `docs/known-issues.md` durchsehen, `boards/README.md`, `RELEASES.md`-Entwurf für 1.8; die Subsystem-Seiten sind schon
      nachgezogen (`e78eacd`, `4767f6f`). Vor 1.1a

## 8 Lokale Werkzeuge

- [ ] 8.6 `settings.json.vor-mempalace-*` und `settings.json.vor-graphify-*` nach Probewoche löschen
      - **12.10. nachts erweitert:** dazu die Daten der beiden ausgebauten Werkzeuge (8.2) - `~/.config/mempalace/` (2,9 G,
        schlüsseltragend, `referenz/artefakte.md`), `repo-neu/graphify-out/`, die venvs und Binaries in `~/.local/`, die Sicherungen
        `~/.claude/settings.json.vor-ausbau-mempalace-20261012` und `CLAUDE.md.vor-ausbau-mempalace-20261012`. Löschen: **Marco**
- [ ] 8.7 cognee gestrichen — in der Recherche-Datei vermerken

## 9 Spät / groß (aus `61` §8 und ROADMAP)

- [ ] 9.0 **Nach dem Release (Marco 09.10.): schneller ans Bild nach dem Standby.** Vom Wecken bis zum Bild ~11 s, davon
      ~4-5 s, weil h713-tv nach dem MIPS-Neustart den HPD 300 ms auf low zieht und die Quelle (Laptop) neu synchronisiert
      (`doku/174` §1). Bei unveränderter EDID den Replug sparen; vorher messen, ob die Quelle ohne ihn wieder sendet
- [ ] 9.0b **Stumm über den Standby** (Marco 11.10.: optional, nach dem Release): h713-tv startet nach jedem Standby neu und
      vergisst die Stummschaltung; speichern wie die Lautstärke - das Stumm-Zeichen kommt dann von selbst mit (h713-osd fragt
      h713-tv beim Neuverbinden)

- [ ] 9.1 **AV1**: erst klären, ob RE-Stand oder lauffähig; H713 ist der erste Allwinner mit AV1
      - 12.10. abends (`arbeit/medien/vorarbeit/BERICHT.md`): bei cstenger lauffähig und bitgenau (Zweig `h713-av1-probe`,
        Kernel `0140`-`0148`, verisilicon-Variante, 30.09.); dazu VP9 (`0143`), MPEG-2, VP8, alles über megis `libva-v4l2_request`.
        In unserem Abbild nicht gemessen
- [x] 9.1a **GPU läuft womöglich mit halbem Takt** (cstenger `0152`, 02.10., gemessen über Panfrost-fdinfo): Bit 0 von PLL_GPU
      (`CCU+0x030`) ist ein Ausgangsteiler ÷2, den unser `0001` nicht modelliert; `CCU+0x670` hat einen M-Teiler. Am HY310 12.10.
      gelesen: `0x02001030 = 0x28000b01` (Bit 0 gesetzt). Die Halbierung selbst ist bei uns nicht gemessen: unter Warp-Last
      `drm-cycles`/`drm-engine` gegen devfreq. Stimmt sie, lief der Warp bei 216 statt 432 MHz; Stock fährt fest 600 MHz
      (`0153`: 150/200/300/600). Nach dem Release, vor jeder Desktop-Planung
      - **13.10. erledigt** (Paket A des Nebenprojekts `arbeit/medien/`, `A-takt/BERICHT.md`): Halbierung gemessen (Verhältnis
        0,500 an allen vier Punkten), mit `0268`-`0270` in `main` 150/200/300/600 MHz exakt, Warp 2,49 ms je Bild bei 600 MHz
        statt 3,97 ms bei 348 echt, 45 min ohne Trip. Am G-EU offen: 2.72
- [ ] 9.2 Cedrus/GPU Testmatrix Decoder × Auflösung × Ausgabe; der KASAN-Fall steht
- [ ] 9.3 Hardware-Video-Decode und IOMMU in **diesem** Image nachmessen (aus cstengers Baum übernommen)
- [ ] 9.4 Verwaltungsoberfläche (WLAN, Presets, Startmodus, Updates ohne SSH) — Zuschnitt offen
- [ ] 9.3a **B6-Fix `0308`/`0309` (medien, 14.10.2026) am HY300PRO-G-EU nachmessen** (am HY310 bestanden, `arbeit/medien/B6-mythos/BERICHT.md` §5g):
      hevc8-/hevc10-Fehlersätze mit Probe nach jedem Clip ohne Hänger, B1-Kurzsatz HEVC, B5-Paare (AV1 ist seit 0310 aus, kein AV1-Teil).
      Werkzeuge `B6-mythos/b6m.sh`, Box-Skripte aus `/root/b6m/` des HY310.
- [ ] 9.3b **AV1 wieder aufnehmen** (Marco 14.10.2026: "AV1 ist mir völlig egal, zumindest für jetzt"): `0310` entfernen, `CONFIG_VIDEO_HANTRO=m`,
      dann die Gates von C (C1-C5) und B6 nebeneinander wiederholen; offen bleibt, warum die Port-Freigabe der VE neben laufendem AV1 Bilder kostet
      oder den SoC anhält (`arbeit/medien/B6-mythos/BERICHT.md` §5b-5f).
- [ ] 9.5 Windows: Installer nie dort gelaufen; `sunxi-fel.exe` nach Rückmeldungen
- [ ] 9.6 Zweites Augenpaar auf die Sicherheitspfade (Gate, Recovery, Installer-Verweigerungen)
- [ ] 9.7 Recovery-Weg **von einer zweiten Person** gegangen; 20 Gate-Zyklen; HDMI-Modustabelle vollständig (aus `61` A.2)
- [ ] 9.10 Settings-Seite: PIN auf der Leinwand statt Passwort (wie Chromecast), Sitzungs-Cookie — braucht eine
      Einblendung im Warp/h713-tv (Marco 05.10.: später)
      - 11.10.: Einblendungen gibt es jetzt (`h713-osd` über Kanal 2); für eine PIN fehlt noch Text in `libh713osd` (wie bei 2.38)
- [ ] 9.11 **Abschalt-Plopp beim Poweroff** (aus 2.6). Gemessen 05.10. mit dem ThinkPad-Mikro
      (`arbeit/edid-sweep-20261005/plopp/`): Plopp 1 beim Stream-Ende (DAPM nimmt PL2) -> behoben, Kernel 0184.
      Plopp 2 am Poweroff-Ende, 42-54x Grundrauschen, immer +10,96 s nach dem Befehl; harter Netz-Cut mit PL2 an
      nur 9x; PL2 von Hand fallen lassen ploppt, Mute davor (DAC, Line Out, beides, 1,5 s) aendert nichts.
      **Widerlegt:** TF-A nimmt PB5/PL3 vor dem Gate-Reset weg und wartet 600 ms (Fork-Branch
      `versuch/plopp-pb5-pl3-vor-reset` - am 07.10. gelöscht, Marco - in die eMMC geschrieben und gehoert: unveraendert laut) -> der
      Verstaerker haengt nicht (nur) an PB5/PL3, oder der Knall kommt nicht von PL2, sondern vom Zusammenbruch
      der Codec-Versorgung beim Reset. Naechster Schritt braucht Oszilloskop/Schaltplan: welche Schiene
      versorgt den Verstaerker, was tut der Reset mit ihr. Bis dahin: so lassen
- [ ] 9.12 **Bluetooth-Ursache A nach dem Release messen** (aus 2.3, Marco 06.10.): warum der erste HCI-Befehl nach
      einem warmen Reboot ohne den Reset vorab manchmal unbeantwortet bleibt (FB-BTRESET 9.1). Verdacht: `hciattach any`
      öffnet die UART erst mit 115200 und schaltet dann auf 1500000; seit dem Fix öffnet `h713-bt-reset` sie als Erster.
      Messung: 10 warme Reboots mit der alten Unit (Drop-in, btmon ab Boot), dann 10 mit `hciattach -s 1500000`.
      Dazu 9.2: der Kernel verliert seinen Close-Reset beim tty-Detach (`hci_ldisc.c`, upstream-würdig).
      **Früher wieder aufmachen,** sobald trotz Helfer `not UP` oder `no answer` im Journal von h713-bluetooth steht
      - 12.10. dazu aus 2.49: **Last-Test** der HCI-UART mit 0256 (Warp + WLAN + Mikrofon der Fernbedienung gleichzeitig), HCI-Fehlerzeilen zählen
- [ ] 9.13 Webpanel-Konzept (aus 5.10): Ecke/Kante, Seitenverhältnis, Undo/Redo, Vorschau = Warp (`61` Z. 555ff) - Marco 06.10.:
      erst einmal geschoben
- [ ] 9.14 Automatischer Standby, wenn lange kein Signal kommt (aus 2.29; Marco 09.10.: Userspace, erst viel später)
- [ ] 9.15 **Eigenständiges Update-Werkzeug** (Marco 12.10., ganz spät, nach dem Release): ein neues Abbild mit dem Abzug einspielen,
      den der Nutzer ohnehin hat (groß oder klein), ohne den ganzen Installer-Lauf

## 10 Erledigt — aus `61` und `144` gestrichen, damit es nicht wieder auftaucht

HDCP 1.4 über die Crypto Engine (05.10.) · Beta-Warnung in README/Release/Installer · Alle
Werkzeuge ins Englische (Nutzer-Sichtbares) · Fremdgeräte-Profile HY300 Pro · Installer liest
`.zst` und findet Binaries neben der Tabelle · Kleiner Abzug aus der GPT statt Konstanten ·
Mitgelieferte GPT gegen errechnete prüfen (Test `stock_gpt_crosscheck`) · Gerätetöne mit HDMI
mischen (v0.96) · Bluetooth mit Stock-Fernbedienung (v0.96) · Bitgleiche Bauten
(`SOURCE_DATE_EPOCH`, v0.96) · Autofokus nur mit Testbild (v0.95) · `ge2d` — **nicht nötig**
(ROADMAP 26.09.) · `tvtop/tvfe/nsi` — **nicht nötig** (ROADMAP) · Platzhalter-Sonderfall —
Layout v4 hat keine Platzhalter · bl31 vom 10.09. in der Bootkette · U-Boot-Firmware-Debugging
per Board (`commdev`/`elog`) · Agenten-Scratch löschen (05.10., 74 Klone) · Wickelschlüssel im
Installer ablegen (`144` 06:0x) — **entfällt**, op 1 entschlüsselt nicht · Konfiguration der
HDCP-Teile prüfen (`144` 06:1x) — `check-hdcp-artifacts.sh`.

### Aus den Abschnitten 1-9 hierher verschoben (10.10.2026; Nummern bleiben, Verweise gelten weiter)
- [x] 2.56 **720p als bevorzugter Modus auf 720p-Boards** - erledigt 11.10. mittags (Marco: freie Hand; `doku/198`): `h713-tv`
      setzt das CTA-Timing des Panels als erstes EDID-Timing, wenn das erste Timing der Datei größer ist (`edid_prefer = panel`,
      Vorgabe; `file` = Dateireihenfolge). Gemessen G-EU: Quelle folgt der EDID → 720p60 → 59,7 von 60 Bildern (vorher 35-57)
- [x] 2.58 **Low Latency gesondert ansehen** - 11.10. mittags gemessen: an/aus ohne Wirkung auf die Sprünge (54,1 → 54,3/55,2 → 54,8/s);
      bleibt als V4L2-Control vorhanden (`doku/198`)
- [x] 2.57 **1080p60 am 720p-Panel verliert jedes 4.-5. Bild** - erledigt 11.10. abends (Kernel-Patch `0255`, `doku/200`;
      Paket `arbeit/aufnahme-takt-20261011/`). Weg: Deskriptor-Bildrate (widerlegt, §7), Firmware-Takt/Kopplung/Bus/TNR (widerlegt,
      `doku/197`), vierter Ringplatz (nicht möglich, `doku/198`), Panel-Kopplung (rastet ein, flackert/dunkelt, `doku/199`). Lösung:
      die Aufnahme schreibt alle Bilder strikt rotierend und nennt ihren Schreibindex in `INCAP +0xa0c`; afbd wählt den Ringplatz
      daraus statt aus dem Firmware-Zeiger (`ring_select`, Vorgabe 1; Ebene = Platz in Arbeit, Notifier = zuletzt fertiger; langsame
      Quellen Platz−1). Gemessen G-EU: 1080p60 59,70 von 60 (vorher 32,9), Warp 59,7 fps, 1080p30/50 und 720p60 jedes Bild; Bild
      sauber. Rest 0,3/s = Takt (→ 2.59). Offen daraus: dasselbe am HY310 messen (1.x Test mit Marco)

**1 Release — in dieser Reihenfolge**

- [x] 1.1 Test-Images gebaut 05.10. 20:36: `installer/out/h713-hy310-v0.96-beta-{a,b,c}.img`, Check 10/11
      „everything in order" (inkl. `check-hdcp-artifacts.sh`). Drei Bau-Stolpersteine dabei behoben:
      0183 kompilierte nicht (`c5f2f5e`), Sysroot-Wiederverwendung ohne Paketprüfung, `doku-index`
      zählte Bauausgaben (`eebb33e`)
- [x] 1.2 HY310: 5 Kaltstarte + HDCP-Paar mit dem v0.96-beta-Abbild (Marco: statt 22 Zyklen), 05.10. 20:50–21:07,
      Ergebnisse in `doku/142` (Abschnitt 05.10. abends): 5/5 gebootet, 0 failed, wipe→Desired, push→Enabled,
      WLAN ~9 s, 720p+Warp richtig, BT UP. Auffälligkeit Z4: ein zweiter Boot ohne Spur → 1.2a
- [x] 1.5 STAGE4-Marker füllen und löschen - **erledigt** (b110ec1, `doku/143`); 09.10. geprüft: `git grep STAGE4` findet keinen Marker mehr

**2 Am Gerät offen (keine Blocker, aus `144` §2 und known-issues)**

- [x] 2.1 **Zoom** (Marco 04.10.: „bringt das Gerät durcheinander") - 06.10. behoben, `doku/155`: der Aspect „zoom"
      (Firmware-Modus 5) legte den Bildweg lahm, auch gespeichert beim nächsten Start -> Kernel 0185, h713-tv lehnt ab,
      Panel ohne; der Zoom-Schieber kippte schiefe Trapeze -> rechnet jetzt durch die Trapez-Homographie und schaltet
      unter 100 % den Warp ein. Von Marco an der Wand abgenommen
- [x] 2.3 Bluetooth nach warmem Reboot: erster HCI-Befehl verloren (2 von 5 mit der alten Unit) - **abgefangen**
      (Marco 06.10.: vorerst schließen): seit `h713-bt-reset` vor dem Attach 0 Ausfälle in 7 warmen Reboots, jedes Mal
      Reset auf Versuch 1 und `hci0 UP after 0 ms` (`doku/156`). Die Ursache bleibt offen -> **9.12**, nach dem Release
- [x] 2.4 HDCP 2.2 Session-Beweis: Fire-TV-Stick am HY310, 05.10. — `h713-tv ctl hdcp` meldet
      „2.2 (session stands), authenticated: yes", Firmware-Log zeigt SKE_SEND_EKS; über acht
      Moduswechsel (1080p60 ↔ 720p50/60) jedes Mal neu authentifiziert. Beide Schlüssel sitzen
      (1.4 aus U-Boot, LINK 0x93=0x45; 2.2 vom Kernel beim Probe)
- [x] 2.4a **720p-Quelle + Warp: Bild doppelt und gestaucht** (Fire TV 720p60, 05.10.). Der
      Warp-Frame selbst ist sauber (`h713-warp ctl dump`), ohne Warp ist 720p sauber — also
      liest der Kompositionsblock der Firmware den 1920er Warp-Puffer weiter mit dem
      Ring-Stride 1280 (Patch 0107: „nothing behind the reader gets reprogrammed"; dort als
      „not yet measured on the wall" markiert — jetzt gemessen). Fix-Kandidaten: beim Wechsel
      Ring→FB den Descriptor mit FB-Geometrie publizieren und WCE abwarten (afbd), oder den
      Warp in Quellgröße rendern lassen. Vor dem Release entscheiden — trifft jede
      Nicht-1080p-Quelle mit Keystone
      → Prüfstand 05.10. (`/opt/Projekte/h713/arbeit/warp-pruefstand/BERICHT.md`): Ursache gemessen,
      der Kernel verweigert das Neuschreiben des VidDec-Descriptors außerhalb des Ring-Modus
      (`afbd.c:602`); Fix Kernel-Patch 0183. **Hardware-Test offen:** 720p + Warp, dann
      Signalereignisse erzwingen (HDCP-Neuverhandlung, Aussetzer) — übersteht die Capture das?
      Das war der Grund der alten Regel. Kamera als Auge: `kamera-gitter.py`
      **05.10. 20:30 am Gerät bestanden:** Kernel mit 0183 per Schnell-Deploy (FIT + Module +
      Daemons, Sicherung `/root/sicherung-vor-0183/`); Register folgen dem Puffer (Komposition
      0x05000444 = 1920x1080, Skalierer 1920x1080, Descriptor 1920 1080 … 1920), Kamera: ein Gitter;
      sechs Moduswechsel mit Signalabriss → neun saubere Republishes (Ring ↔ Framebuffer), kein
      „did not reprogram", 56 fps. Offen: HDMI-Stecker ziehen/stecken, 720p50/1366x768 als Quelle
- [x] 2.4e **Warp-Flackern bei Ringen mit Zeilenabstand ≠ 64er-Vielfaches** (480p, 576p, 1366×768, 1280×1024 …):
      Panfrost lehnt den Slot-Import ab, der Warp versuchte es jede Sekunde neu und nahm dabei jedes Mal den
      Plane (47 Republishes/min, Wand blinkt, erster Frame grün). Jetzt Import **vor** dem Claim und kein
      neuer Versuch bis zur nächsten Ring-Geometrie — gemessen 05.10. 22:02: 0 Republishes, Bypass still
      (Einzeltest `arbeit/edid-sweep-20261005/`). Offen: Keystone für diese Modi (CPU-Kopie in einen
      64-aligned Puffer, oder Firmware-Ring breiter) → 2.4f
- [x] 2.4g Warp bei 24/25-Hz-Quellen = schwarze Wand: der feste 28-ms-Stale-Schutz warf jeden gehaltenen Slot
      zurück (Slots kommen bei 24 Hz im 34/50-ms-Takt; 334 stale, 0 Frames). Schwelle folgt jetzt dem gemessenen
      Slot-Abstand (×1,25, nie unter 28 ms). 05.10. 22:12: 1080p24 → 24,0 fps, p25 → 25,0, p30 → 30,0, p60 → 59,4,
      0 Drops; Kamera: Bild da
- [x] 2.4c 1366×768 (Pitch 1376): gemessen 05.10. — rastet, Warp geht in den stillen Bypass; ist derselbe
      Ausrichtungsfall wie 2.4e/2.4f, kein eigener Punkt mehr
- [x] 2.7 Geometrie: Ceiling-Beweis kopfüber; Kalibrierkarten in gespiegelten Modi - 06.10., `doku/157`: Karten und
      Bild in allen vier Modi richtig (Fotos gedreht statt Beamer, Marco); beim Moduswechsel blieb das Trapez nicht am
      Gehäuse -> `ctl mode` sortiert die Ecken jetzt um wie Stocks `setKeystoneNormalXY`, Rahmen in allen Modi
      deckungsgleich. Nicht gemessen: die Automatik mit wirklich kopfüber liegendem Sensor
- [x] 2.8 Autofokus: eine Wand, ein Abend; Metrik-Spanne nur +11 % (Belichtung) - **gestrichen 06.10. (Marco)**. Der Autofokus
      ist abgenommen (`doku/134` A4, Läufe enden scharf); weitere Wände und die Schärfekurve werden nicht gemessen.
      Ungeprüfte Deutung der +11 %: Läufe starten nahe am Fokus, das Optimum ist ein flaches Plateau
- [x] 2.10a Interlace-VICs 7, 6, 21 (480i/576i) aus unserer EDID, die die Firmware nicht rasten kann: h713-tv
      beschneidet jede veröffentlichte Hälfte um die SVDs ohne Tabelleneintrag (`edid_prune`) und veröffentlicht
      die servierte Hälfte beim Start einmal so, wenn nötig (ein HPD-Puls). Am Gerät 05.10. 21:30: 17 VICs offered,
      all in the firmware's table; ThinkPad bietet 720x480i/576i nicht mehr an; Programmneustart = kein zweiter
      Puls (`c33df12`). Offen: `1024x768i` (Established Timing im Basisblock, kein SVD) — rastet das?
- [x] 2.11 `backlight_level` / `dynamic_backlight` ohne Wirkung — Firmware nimmt den Aufruf, Lampe ändert nichts - **geschlossen
      06.10.: die Lampe ist auf HY310 und HY300 nicht dimmbar**, auch unter Stock nicht (Marco); der Stock-Devicetree nennt
      PWM2/PB4, aber dessen Tastgrad 100..0 % ändert nichts (gemessen, cstenger ebenso: Dimmer nicht verdrahtet). Die Regler
      bleiben für Boards mit Dimmer (L018: drei Stufen, Lüfter folgt)
- [x] 2.12 AP-Latenzspitzen (3 ms ↔ 2 s bei −50 dBm, Durchsatz ok) - **06.10. nicht nachvollziehbar** (`doku/158`): Box als
      AP mit der ausgelieferten `wifi.env`, dieser PC als Client bei −47 dBm, Stromsparen der Box an: 100 Pings à 0,2 s
      1,2-124 ms, 60 Pings à 1 s 2,6-14 ms (Median 3,4), keine Spitze. Station-Modus 1-59 ms
- [x] 2.13 Settings-Seite Port 8080: seit 05.10. HTTP Basic Auth, Passwort beim ersten Start erzeugt (`/etc/h713/panel.env`,
      0600), `h713-panel --show-password`; am Gerät geprüft (401/401/200), 33 Tests grün. PIN auf der Leinwand → 9.x
- [x] 2.15 `afbd`-Modultausch zur Laufzeit bringt kein neues Fenster (Firmware nimmt Republikation nicht) - **geschlossen
      06.10. (Marco): kein Nutzerfehler**, Regel: afbd-Änderungen per Neustart testen (`known-issues.md` behält die Zeile,
      gemessen 22.09. am HY300 Pro, `doku/128`). Eine echte Lösung käme mit 3.3
- [x] 2.17 Presets `computer`/`game`/`hdr` nie geprüft; Gamma 2,2 Sichtprüfung gegen Stock; Weißabgleich/CTM ohne Stock-Vergleich (aus `61`)
      - 06.10., `doku/159`: die drei Presets setzen am Gerät exakt die Herstellerdaten der Box, Bild intakt; Gamma ist die
      eigene Kurve der Box. Stock-Vergleich (Gamma, Weißabgleich/CTM) gestrichen (Marco: wird nicht getestet)
- [x] 2.18 `h713-pq brightness` sagt angeblich ohne Wirkung - laengst korrigiert: `model.py` sagt seit 11.09. (Plan 113 A.6)
      measured, effective mit Verweis auf nachtlog/I0; der Punkt aus `61` war ueberholt (05.10.)
- [x] 2.19 `h713-tv ctl replug` gibt es längst (HPD-Puls, S_EDID); „Plane liest Ring direkt' ist seit 0107/0117
      das Design (hdmi-ring-Modus), kein Mangel — Punkt aus `61` überholt (05.10.)
- [x] 2.20 Preset beim Start wählbar, Regler über Neustart merken; Startmodus `auto|manuell` merken (aus `61`) - seit Plan 113
      (Mitte September) im Code (`tv.conf` `start`/`preset`, `ctl save`); 06.10. am Gerät gemessen (`doku/159`): cinema +
      Helligkeit 55 + Startmodus off überleben einen warmen Neustart
- [x] 2.21 Kamera mit hellem Bild nie geprüft; WLAN-Station zwei Ecken offen; Telefon am AP (aus `61`/known-issues) - 06.10.:
      **Kamera erledigt** - über zwanzig Wandfotos der projizierten Leinwand mit der Box-Kamera (Belichtung 5000 / Gain 255,
      Luma im Mittel 60-110, Spitzen 255, Text und Rahmen erkennbar; `doku/155`, `157`, `159`). **WLAN-Ecken und Telefon am AP
      gestrichen** (Marco: nie relevant) - Android und das DNS des AP, zwei Standardrouten mit LAN-Adapter
- [x] 2.23 KEY_POWER-Politik (poweroff ueber logind, auch die BT-Fernbedienung; kein Standby) steht in
      `docs/hardware.md`; WLAN-Band der Koexistenzmessung in `doku/134` nachgetragen: 2,4 GHz Kanal 4, 5 GHz ungemessen
      - 07.10. abends, nicht gemessen: ein Abbild mit `--standby` bekommt `h713-power` (kurz Standby, ab 3 s Ausschalten,
        ein KEY_POWER bis 2 s nach einem Wecken per Taste wird ignoriert) unter einer logind-Sperre statt
        `HandlePowerKey=ignore`; ohne `--standby` bleibt poweroff. `docs/tools/h713-power.md`; das Fenster misst Stufe K
- [x] 2.25 **Linux bindet den Watchdog mit dem falschen Registerlayout** - **erledigt 09.10.:** mit dem R2-Merge in `main` (c4a3924) (Gegenprüfung der HDCP-Härtung 07.10., aus dem Code;
      gemessen schon 07.09., `doku/72` Z. 1633 ff.: der Treiber schreibt ohne Schlüssel und trifft nichts, der DT-Fix steht dort
      als „noch nicht umgesetzt"). Kernel-DT `watchdog@2051000` sagt `sun50i-h6-wdt`/`sun6i-a31-wdt` (CTRL 0x10/CFG 0x14/MODE 0x18,
      kein Schlüssel); die Hardware hat CTRL 0x0C/CFG 0x10/MODE 0x14 mit Schlüssel 0x16aa - wie U-Boots DT (`sun55i-a523-wdt`).
      Folgen: `RebootWatchdogSec=16s` (`customize.sh`) schaltet nichts scharf, obwohl `mainline/docs/status.md` und `roadmap.md` es
      sagen; unter Linux gibt es kein Hängernetz. Mit dem richtigen Compatible und `RuntimeWatchdogSec` wäre ein Hänger aus der
      Ferne behebbar, auch mit gestecktem USB-Kabel (Reset im SoC, kein Stromschnitt) - wichtig für Crust-/Standby-Nächte.
      - **08.10. auf dem R1-Testabbild gemessen** (`doku/170`, Branch `versuch/crust-release`, nicht in `main`): `sunxi-wdt` mit
        A523-Layout, 16 s; W2 12/12 (Testprogramm hört auf zu füttern, `sysrq-c`, reboot/poweroff unter dem Zeitschalter).
        Erledigt, wenn die Serie in `main` ist
      Messen: Compatible tauschen (Modul/DT, in einer Kopie), `wdctl`, dann gezielter Hänger -> Reset? Auch prüfen, ob ein Hänger
      am ARISC-Hilfsblock (`irrwege.md`, 0x07091014) vom Watchdog überhaupt zurückgesetzt wird. Erst danach `docs` richtigstellen (`doku/161` §3)
      - 07.10. (`doku/164`): von Hand gesetzt wirkt er und setzt die Box auch mit gestecktem USB-Kabel zurück; Füttern = `0x14AF`
        nach CTRL. **Dazu TF-A härten:** der Ausschalt-Reset (`sun50i_h713/sunxi_power.c`, MODE = `key|1`) scheitert, wenn der
        Watchdog schon läuft - vorher MODE aus und CTRL anpingen
      - 07.10. abends (Release-Entwurf `arbeit/crust-release-20261007/`, W1/W2 im Kernel, T1 in TF-A): `RuntimeWatchdogSec=16s`
        und `RebootWatchdogSec=16s` kommen erst nach bestandener Stufe W2 und Marcos Entscheidung ins Abbild;
        `release/check-crust.py` verweigert schon jetzt ein rootfs mit Watchdog ohne BL31 mit dem fütternden Reset, ebenso
        einen DT, der den Watchdog mit dem H713-Layout (`sun55i-a523-wdt`) bindet: dann schaltet jeder Neustart ihn wirklich scharf.
        Offen: `dt_binding_check`/`dtbs_check` der neuen Bindung, sobald dtschema im Bau-Container ist
      - **09.10.:** die Watchdog-Bindung (0186-0188, 0223/0224) ist mit dem R2-Merge in `main` (`doku/170`, `doku/171`-`doku/174`)
- [x] 2.29 **Standby oder Ausschalten - wann, wie, was im Release** (Marco 09.10., eigenes Thema, besprechen): Standby
      funktioniert jetzt (Bild und Ton zurück, Taste, IR, Minuten-Schläfe, `doku/174`). Offen zu entscheiden: bietet das
      Release-Abbild `--standby` an; Vorgabe für den kurzen Druck (`short = standby|poweroff`) und für einen verweigerten
      Standby (`refused`); die Fernbedienung; ein Gate an oder aus (`h713_gate`); automatischer Standby ohne Signal; was
      Nutzer in `docs/` lesen. Dazu fehlt die Leistung im Standby gegen das Gate (4 W) - messen (M1/M2)
      - **Entschieden 09.10. abends (Marco):** 1.1a bietet Standby an (`--standby`), aber **experimentell und aus**: Vorgabe
        `short = poweroff`, einschalten mit `short = standby` in `/etc/h713/power.conf`; `docs/` sagt "experimentell, auf dem HY310
        getestet". Kurz = Standby, 3 s halten = Aus (bleibt so). Fernbedienung wie die Taste (`remote = on`, unverändert).
        Marcos Box: Standby im Alltag; wenn Nächte im Standby halten und die Leistung gemessen ist, wird Standby im Release
        danach die Vorgabe. Missglückter Standby -> dunkel ins Gate: 2.30. Automatischer Standby ohne Signal: viel später, 9.14
      - Umsetzung in 1.1a (Vorgabe `short = poweroff`, "experimentell"); die Leistungsmessung ist jetzt 2.31
- [x] 2.30 **Ein missglückter Standby endet dunkel im Gate** (Marco 09.10.: "lieber dunkel" statt Neustart mit Lampe an).
      Heute läuft jeder Reset aus einem Standby (crust-Budget 15 s bei C1, Linux-Zeitschalter 16 s) als Warmstart am Gate
      vorbei. Vorschlag: vor dem Einschlafen (vor dem noirq-Fenster, wo C1 hängt) `GATE` ins RTC-Wort GP5, nach dem vollständigen
      Aufwachen wieder `RUN1`; jeder Reset dazwischen landet im Gate wie ein `poweroff`. Lücke: hängt crust selbst, fängt
      es nur R_WDOG (CR-1, Stufe S0). Mit `h713_gate=0` (Marcos Box) bootet sie trotzdem durch. Messen mit einem
      provozierten Hänger (Testmodul), Marco an der Taste
      - **Erledigt 09.10. abends** (`0245`, `doku/179`, Paket `arbeit/standby-gate-20261009/`): `sun50i-h713-mips` hält GP5 als
        vierte reg, "STBY" ab PM_SUSPEND_PREPARE bis der Kern wieder läuft, Reboot-Notifier schreibt "RUN1". Gemessen 4/4 mit
        `h713_gate=1`: Kontrolle, Hänger syscore suspend (crust 15 s -> Gate dunkel), Hänger syscore resume (crust 60 s ->
        Gate dunkel), reboot bei "STBY" bootet. U-Boot-Zeile (`0097`) und TF-A-Kommentar (`0030`) seit `doku/180` in den Forks;
        crust-Hänger im Schlaf fängt
        weiter nur R_WDOG (CR-1)
- [x] 2.31 **Leistung messen: Gate (mit crust), Standby, Betrieb** (aus 2.29) - **erledigt 09.10. 21:00** (`doku/181`, Marco mit
      Wattmeter, USB gezogen, ohne Sonoff): Standby **2,4 W**, Gate **2,9 W**, Betrieb ohne Signal ~24 W, Sonoff ~0,5 W. Standby ist
      sparsamer als Aus. Offen: Betrieb mit Bild neu messen (09.09.: 47 W), Netzteil fiept im Standby leise
- [x] 2.32 **"Aus" braucht mit unserem System 8-10x so viel wie Stock** (Marco 09.10. abends). Gemessen: HY300PRO-G-EU mit
      Stock-Android eingesteckt und aus **0,3 W**, mit unserem Abbild (geucrust1) **2,4 W**; HY310 im Gate 2,9 W (`doku/181`), Stock
      vermutlich auch ~0,3 W (nicht gemessen). Bei uns wartet U-Boot im Gate auf einem ARM-Kern in einer Schleife auf die Taste;
      Stock schaltet offenbar wirklich ab und lässt nur die ARISC-Firmware wachen. Weg: "Aus" über crust - ARM-Kerne aus, DRAM
      aus, nur crust und RTC wach, die Taste weckt (wie der Standby, nur ohne Self-Refresh) - statt der U-Boot-Schleife. Vor dem
      Release wenigstens bewerten und den Stock-Wert am HY310 messen; gehört zur ARISC/crust-Besprechung mit Marco
      - **10.10. Cloud-RE A (`doku/187`, aus Listings, nicht gemessen):** Stock-"Aus" = BL31 `SYSTEM_OFF` setzt RTC-GP2 = 2 und lässt
        die ARISC den SoC per Watchdog zurücksetzen; nach dem Reset schickt BL31 "fake poweroff", die ARISC macht Wecker scharf
        (PL4, IR, CEC), legt ARM-Seite, DRAM und PLLs still und zieht **PL6 low** - die eine Freigabe von vdd-cpu/vdd-sys/vcc-pll/
        vcc-dram, an G-EU **und** HY310. Wecken: PL6 high, GP2 = 0xf, Watchdog-Reset, Kaltstart. Unser crust schaltet PL6 nirgends.
        Nächster Schritt nach der Besprechung: Bankmessung am HY310 (crust zieht PL6 im dunklen Wartezustand, Wattmeter, Ziel 0,3 W)
      - **10.10. abends (`doku/188`, Marcos Freigabe): am HY300PRO-G-EU gebaut und gemessen** - crust `h713` `d8a8d56` (0x19,
        PL6 low nach Stock-`0xdea8`), TF-A `sun50i-h713` `1dd03734` (crust zuerst, Gate als Rückfall), Kernel `0250`: **0,3 W** ohne
        USB-Kabel, Timer, Fernbedienung und Taste wecken in einen frischen Start. Vorgabe `short = poweroff`, umschalten mit
        `h713-power set short standby`. Offen: **HY310 messen** (`h713_hy310_sr_off_test_defconfig`), dann `H713_POWER_OFF` in
        dessen Release-Konfiguration; G-EU-Abbild mit Kurztests vor `main` - **10.10. abends erledigt** (`geuaus1`, `doku/188` §4,
        alles bestanden, 0,3-0,7 W im Aus)
      - **Nächster Schritt: HY310 messen** (Marco 10.10.: die nächste Sitzung), Ablauf `doku/189` §3
      - **Erledigt 10.10. später abends am HY310** (`doku/190`, Marcos Freigabe "weiter im Plan"): per FEL, eMMC unberührt, drei
        Läufe - Testbau weckt sich nach 60062 ms selbst, Power-Taste nach 111 s, IR-Fernbedienung nach 5 s; jedes Mal Phase 7,
        Schritt `0x613`, R_WDOG-Reset, Warmstart mit GP5 `RUN1`. crust `h713` `54e4a08` (0088: `H713_POWER_OFF` in
        `h713_hy310_sr_defconfig`), Spiegel 88 Patches. **Watt am HY310 nicht gemessen** (Marco: baugleich mit dem G-EU). Der HY310
        selbst läuft weiter `r2test4` aus der eMMC - dort endet ein `poweroff` noch im Gate, bis ein neues Abbild drauf ist (1.1a).
        Rest: Netzteil fiept auch im Aus (2.42), Kaltstart-Gate (2.39)
- [x] 2.39 **Kaltstart-Gate über crust** (Marco 10.10. abends: nach dem Einstecken 2,4 W): Nach Netz-Ein wartet U-Boots Gate weiter
      mit einem ARM-Kern auf die Taste; nur `poweroff` aus Linux geht seit `doku/188` in crusts Aus (0,3 W). Stock geht auch beim
      Kaltstart in den ARISC-Wartezustand (BL31 GP2 = 0 -> `start_type` -> fake poweroff, `doku/187` §1). Vorschlag: das Gate ruft
      PSCI `SYSTEM_OFF`, statt selbst zu warten - TF-A fragt crust wie beim `poweroff`, crust zieht PL6, die Taste weckt mit `RUN1`;
      nimmt crust nicht an, wartet das Gate wie bisher. Verhalten unverändert (dunkel, Taste, 3-s-Bypass), nur der Verbrauch sinkt.
      Etwa zehn Zeilen in U-Boot (`board/sunxi/board.c` `h713_gate_wait`), per FEL messen. **Ändert das Gate - nur mit Marcos
      ausdrücklichem Ja** (Gedächtnis "Gate nicht anfassen")
      - **10.10. später abends, Gespräch mit Marco (`doku/189` §4.4):** a/b ja ("mach das erstmal"), c) IR darf wecken - ja, vorher
        prüfen, ob sie es heute schon tut; d) ein missglückter Standby (`STBY`) bleibt in der alten Schleife (sonst überschreibt das Aus
        crusts Fehlerprotokoll); e) erst bauen, dann Bescheid, gemessen wird später. **Gebaut, nicht gemessen:** U-Boot
        `versuch/kaltstart-gate` `61ea018` (Paket `arbeit/kaltstart-gate-20261010/`, Testplan im BERICHT), FEL-Abbilder für G-EU und HY310
      - **Erledigt 10.10.2026 abends** (`doku/191`): U-Boot `0101` (`h713-hy310` `61ea018`), in `main` auf Marcos Entscheidung **vor** der
        Messung am HY310 und vor dem echten Netzstecker-Test ("nimm es einfach mit in main für hy300 und hy310 - testen tun wir dann
        beide"). Gemessen: FEL-Lauf k1 am G-EU (Kaltstart nachgestellt, 0,3-0,6 W, IR weckt). Offen, mit 1.1a: echter Netzstecker an
        beiden Boxen, HY310 überhaupt; die R_WDOG-Warnung nach jedem Wecken ist 2.40
- [x] 2.41 **OSD-A (AFBD-Kanal 1) öffnen wie Stock** (10.10. abends, aus Marcos Frage "wie lässt Stock Overlay auf HDMI"):
      Stock legt Androids Oberfläche auf die Hardware-Ebene OSD-A über das unverzerrte HDMI-Bild (Stock-Abzug `doku/64` §6:
      Kanal 1 aktiv, Kanal 2 aus; Entwurf AP3n). Bei uns nimmt Kanal 1 keine Bilder an, auch mit Stock-Registerwerten; am
      23.09. am U-Boot-Prompt dreimal versucht, das Tor liegt außerhalb der drei bekannten Blöcke (`doku/131`). Offen: wer es
      bei Stock öffnet (vermutlich ein Firmware-Auftrag an den Display-MIPS aus dem HAL/HWC, oder ein Takt-/Reset-Bit).
      Gewinn: OSD ohne GPU, das Video bliebe im Ring, der Warp könnte bei Identität wieder schlafen. Eigenes RE-Paket,
      getrennt vom Warp-Baum; bis dahin mischt die GPU (2.38, 2.7a). Nicht dringend
      - **10.10. später abends (Marco: "das wäre der Hammer"):** Paket `arbeit/osd-a-20261010/` für eine eigene Sitzung (Fable),
        Worktree `versuch/osd-a` ab `8b663b8`, `AUFTRAG.md`/`REGELN.md`, Material (Stock-Binaries, Mitschnitte, AP3n/AP3j/OSD1) und
        IDA-Arbeitskopien bereitgelegt, idalib + Hex-Rays geprüft. Der HY310 gehört bis auf Weiteres diesem Paket; Haltepunkt vor
        dem ersten Schreiben am Gerät ist die Kandidatenliste fürs Tor
      - **Erledigt 10.10.2026 abends, anders als gedacht** (`doku/192`, Paket `arbeit/osd-a-20261010/`): Stock benutzt OSD-A nicht,
        ein Tor gibt es nicht; die Einblendung geht über **Kanal 2** (OSD-B) über dem Video - Kernel 0251, weiter in 2.43-2.48
- [x] 2.33 **HY300PRO-G-EU: Lüfter (und Lampe?) im Standby an** - **erledigt 10.10. nachts** (`doku/185`): Stock-Baum nennt PB5 als
      `panel_bl_en` und `fan-power-gpio` wie der HY310; Kernel `0249` gibt PB5 dem Board-Manager statt des Hogs, im Standby "fan power
      rail off", Lüfter aus, Lampe dunkel, nach dem Wecken alles zurück. crust musste nicht angefasst werden. Bisher (Marco 10.10. nachts: "das soll definitiv nicht so sein";
      danach "die fan/lampe geschichte in crust"). Gemessen `doku/184`: im Standby dunkel, Lüfter dreht. `hy310-board-mgr` schaltet
      die Lüfterschiene beim Suspend nur ab, wenn der Gerätebaum sie ihm gibt (`0211`); der G-EU-Baum tut es nicht ("fan power rail
      not ours, left as it is"). Am HY310 trägt PB5 Lüfter und LED-Boost zusammen; am HY300 Pro des Melders schaltete PB5 Licht
      und Lüfter (19.09., Regel "Fremde Boards nur mit Registerbeweis"). Erst den Stock-Gerätebaum des eigenen Abzugs lesen
      (welche Pins für Lüfter/Lampe, was Stock im Standby tut), dann entscheiden: Kernel (Schiene an den Board-Manager) oder crust

**3 Geparkt — mit Wiedereinstiegsbedingung**

- [x] 3.1 **Standby Stufe 2** (<1 W, ARISC, IR/CEC): PSCI-Suspend erreicht DRAM, **kein Wecken** (`doku/139`). FB-STANDBY + 0167c rein, wenn Wecken bewiesen
      - **gestrichen 07.10. (Marco)**: mit der Hersteller-ARISC-Firmware ist das eine Blackbox (eine Nacht, ~15 Proben, kein
      Wecken); echter Tiefschlaf, wenn überhaupt, über Crust (3.2)
      - 07.10., statisch, nicht gemessen (`doku/162` §2): der Blob liest beim DRAM-Ausgang seine DRAM-Werte aus `arisc_para`, und
        unser Treiber füllt den Block mit Nullen - ein möglicher Mitgrund für „Aufwachen nie". Bleibt gestrichen
- [x] 3.2 FB-CRUST — **erledigt 09.10.:** crust als Firmware (R1) und Standby (R2) in `main` c4a3924 (`doku/169`-`doku/174`);
      Reste: 2.29, 5.14, 5.15, Stufe S0 für das crust-Netz (Durchsicht CR-1), C1 im Gebrauch beobachten. Verlauf: **Weg (Marco 07.10.):** nach dem Release; zuerst Crust nur im Normalbetrieb (HDMI, EDID, HPD,
      MIPS-Kanal wie die Hersteller-ARISC; Rückweg = Dateiname, kein Flash, Testplan `FB-CRUST/REPORT.txt` §2), erst dann Schlaf.
      Tiefschlaf braucht zusätzlich die DRAM-Selbstauffrischung (in Crust nur entworfen) und das MIPS-Neuladen (3.3)
      - **07.10. als Paket vorbereitet, nicht gemessen** (`doku/162`, `arbeit/crust-20261007/`): crust für Normalbetrieb und
        Standby, DRAM-Selbstauffrischung und Tiefschlaf aus dem Blob portiert (Spuren gleich), Kernel 0186-0191, TF-A 0001-0004,
        U-Boot 0001, vier FEL-Abbilder, zwei Prüfrunden (41 + 17 Funde) behoben. Nächster Schritt **mit Marco in Reichweite**
        (kein Hängernetz, TODO 2.25): Phase 1 `skripte/phase1.sh 0..9` (~1 h), dann FEL `release-crust`, dann Standby A/B/C nur
        mit Marco an der Box. Offen: HDCP 1.4 nach Tiefschlaf (eine Senken-Schreibung pro Boot mit `doku/161`), CEC-Wecken
      - **07.10. am Gerät** (`doku/163`): Phase 1 (Normalbetrieb) und Phase 2 (TF-A startet crust) bestanden; Standby Stufe A
        wacht auf (erstes Aufwachen überhaupt), crust 0029 (EDID-Gate) und 0030 (Startadressen der Nebenkerne) am Gerät bestätigt.
        **Offen:** Stillstand ~0,1-16 s nach dem Aufwachen an wanderndem Ort; nächste Schritte offline: crusts Schlafpfad Register
        für Register gegen den Blob, BL31 nach dem Aufwachen GIC/Takte auf die UART ausgeben lassen, Kernel mit `CONFIG_PM_DEBUG`.
        Physische Adresse Port 0 wie der Blob (0.0.0.0). Läufe nur mit Marco in Reichweite oder mit einem von Hand gesetzten Watchdog
      - **07.10. Vormittag** (`doku/164`): Stillstand eingegrenzt - Hotplug über TF-A in Ordnung, Nebenkerne nicht schuld,
        **ohne cpu_comm/afbd wacht die Box vollständig auf**. Nächster Lauf: cpu_comm/afbd aus `*-0191.ko` (MIPS parken),
        Power-Taste per `systemd-inhibit` sperren (Herunterfahren nach dem Aufwachen, vermutlich `KEY_POWER` aus PL4), Hand-Watchdog
        vor jedem Herunterfahren aus
      - **07.10. 12:08 erster vollständiger Standby-Zyklus** (`doku/165`): mit geparkter MIPS (0191-Module) und gesperrter
        Power-Taste wacht die Box auf und läuft stabil weiter, alle vier Kerne wieder online. Offen: falscher `KEY_POWER` beim
        Aufwachen (gemessen, crust 0031 hilft nicht), MIPS nach dem Aufwachen neu laden (3.3), dann Stufe B/C und Taste/IR
      - **07.10. 12:47 Stufe B bestanden** (`doku/166`): Standby mit DRAM-Selbstauffrischung (crust-Bau `self-refresh`,
        Takt und PLL_DDR aus), 5 s Schlaf, Linux läuft danach stabil auf allen vier Kernen; `/` war read-only. Offen wie oben
        (`KEY_POWER`, 3.3), dazu Stufe C, Taste/IR, Leistungsmessung, längere Schläfe
      - **07.10. 13:46 falscher `KEY_POWER` behoben** (`doku/167`): crust 0032 löscht die Flanke von PL4 erst nach den
        Debounce-Abtastungen; C2 und C3 (Self-Refresh) ohne Tasten-Ereignis und ohne Interrupt. Offen: Wecken per Taste gibt
        weiter `KEY_POWER` (Regel in Linux/logind, Messung mit Marco an der Taste), 3.3, Stufe C (zuerst LOSC/32-kHz-Quarz
        prüfen), Leistungsmessung
      - **07.10. 14:45 Stufe C vorbereitet, nicht gelaufen** (`doku/168`): crust 0033 (LOSC wie vorgefunden), 0034
        (VDD_SYS- und LDO-Schritt abschaltbar), Bau D1a ohne beide, `standby-wd5.sh`. **Nächste Läufe nur mit Marco an der
        Box:** V1 (SR, 20-s-Timer unter dem 16-s-Watchdog: trägt das Netz im Schlaf?), dann D1a. Bis V1 gemessen ist,
        Standby-Läufe ohne Marco nur in schon gelaufenen Varianten
      - **07.10. abends Release-Integration vorbereitet, nichts gemessen** (`arbeit/crust-release-20261007/`, Entwurf
        `DESIGN-RELEASE.md`): crust-Bau in `build-all` (Schritt 1b, or1k-Compiler aus gepinnten Quellen), Spiegel
        `crust-h713/`, Tor `release/check-crust.py`, HY310 `CRUST_DEFCONFIG=h713_hy310_sr_defconfig`, `--standby` (bis 3.3
        aus), `h713-power`, `docs/subsystems/standby.md`. **Gerätestufen R1** (crust Standard-Firmware des HY310, ohne
        Standby): S0a (R_WDOG, R_PRCM nur lesen), W1 (TF-A-Reset mit Füttern), W2 (Kernel-Watchdog), A0 (Wachbetrieb gegen
        den Blob, 24 h, HDCP-Paar), M1 (Leistung im Gate mit crust). **R2** (Standby im Abbild): S0b-S0d, V1', N0-N4,
        K (Taste, IR), L (Licht und Lüfter 1 h), M2 (Leistung im SR), R-a bis R-d (Produktbild), Hörtest, dazu 3.3.
        Jeder Lauf nur mit Marcos Ja. **Merge-Bedingung:** `CRUST_DEFCONFIG` im HY310-`board.env` kommt nur zusammen mit
        der crust-Quelle (Submodul `mainline/external/crust`, bis dahin `CRUST_SRC`), dem HY310-DT mit `hy310-crust.bin`
        und dem U-Boot-Patch für `scp.bin` (`SUNXI_SCP_BASE`) nach `main`: ohne Quelle hält `build-all --board hy310` an,
        ohne die anderen beiden verweigert Schritt 10. `release/tor.sh` und `boards/check.sh` sehen das nicht
      - **08.10. 05:45 Release-Arbeit offline fertig** (`doku/169`): Durchsicht, Entwurf (R1/R2), Umsetzung in 9 Paketen,
        Gegen- und Nachprüfung, Abnahme G0 grün, R1-Testabbild und FEL-Testbilder gebaut (`versuch/crust-release`). Nächstes:
        Gerätestufen nach `arbeit/crust-release-20261007/integration/TESTPLAN.md` mit Marco an der Box
      - **08.10. 13:15 Abend 1 am Gerät bestanden** (`doku/170`): S0a-S0d, W1, N0, A0 (R1-Abbild: Kabel, Quelle, `h713-tv`,
        HDCP-Paar, Ton), W2. Zwei Funde behoben und auf `r1test2` nachgemessen: MIPS-Fehlalarm (crust `ecf2ddc`, Blob-Regel) und
        R_WDOG bleibt über seinen Reset scharf (TF-A `175c6948f`, T7 Vorgabe). Offen: Langlauf, M1, Abend 2, dann 3.3; der
        Typfilter des Blobs für DispMips (0x11828) erst, wenn der Typ auch für 0x17 gemessen ist (0x16: Typ 2)
- [x] 3.3 FB-MIPSRELOAD/b — **erledigt 09.10.:** Bild und Ton kommen nach dem Standby zurück (0239, `h713-mips-restart`, `doku/172`,
      `doku/174`), in `main` c4a3924. Rest: msp-Meldung sagt noch "until a reboot" (Text in 0243). Verlauf: rein, wenn der Bildfehler nach Reload verstanden ist (`doku/138`) - löst 2.15 mit (Firmware nimmt nach einem afbd-Reload keine neue Publikation an)
      - **Platzhalter (Marco 07.10.):** ohne MIPS-Neuladen hat der Projektor nach jedem Standby kein Bild (Release-Durchsicht
        KD-1/INT-04, `arbeit/crust-20261007/PRUEFUNG5-20261007.md`) - Standby ist ohne 3.3 nicht auslieferbar. Weg: Neuladen
        (nicht die Übergangslösung „nach dem Aufwachen neu starten"). **Reihenfolge:** erst crust fertig, dann 3.3
      - **09.10. Bild nach dem Standby gemessen, R2-Testabbild** (`doku/171`, `doku/172`, `arbeit/r2-20261009/BERICHT.md`):
        Fehler B behoben (0238, Display-Takte über den Schlaf aus), der MIPS-Neustart aus dem Park hängte nach einem echten
        Schlaf die SoC (TV-Top-Wörter 0x06e00000 vom Schlaf gelöscht) - behoben (0239); sechs Standbys über h713-power in
        einem Boot, 6 von 6 Bild zurück. Zweig `versuch/r2-standby` (nicht `main`). **Offen vor einem Release:** C1 (Hänger
        beim Einschlafen, R2 3 von 13, crust setzt nach 15 s zurück), der echte Tastendruck mit Marco, HDMI-Ton und HDCP 2.2
        nach dem Neustart, `power.conf refused` zurück auf `poweroff`, Durchsicht UEBERGABE §7 vor `main`
      - **09.10. nachmittags Durchsicht und r2test3** (`doku/173`, `arbeit/review-r2-20261009/BERICHT.md`): 46 Funde, behoben
        0240-0244 (C1: Aufnahme vor dem Schlaf anhalten; msp nach dem Standby "error"; CC-2, KM-1, Q6), h713-power U1,
        crust-Spiegel ecf2ddc. r2test3: 30/30, C1 0 in 50 seit dem Aufnahme-Stopp (vorher 5 in 111). **Offen:** CR-1 (Netz gegen crust-Hänger, Stufe S0), Gerätestufen mit
        Marco (Taste, IR, lange Schläfe, Leistung, Hörtest), `power.conf` auf der Box zurück auf `refused = poweroff`
      - **09.10. abends mit Marco** (`doku/174`): Taste, IR-Fernbedienung, 3,5 und 8,4 min Schlaf, langer Druck - alles gut;
        Ton nach dem Standby zurück (h713-mips-restart baut den Audio-DSP neu auf, bis 3 Versuche). Offen: msp-Meldung sagt
        noch "until a reboot" (Text in 0243 anpassen), Leistung im Standby, Wartezeit bis zum Bild ~11 s (-> 9.0, nach dem Release)
      - **09.10.** `release/sperr-scan.py` erkennt in einem Git-Worktree das Git nicht (`.git` ist dort eine Datei,
        `os.path.isdir` falsch) und durchsucht die ignorierten, root-eigenen Bauordner -> PermissionError, Tor rot. Umgehung:
        Tore auf `git checkout-index -a --prefix=...`. Behebung: `os.path.exists` (eine Zeile) - gehört nach `main`

**4 Boards und Fremdgeräte**

- [x] 4.2 `hy200-qz713-v2`: Layout-v4-Defconfig + eigener Baum **vor** jedem TEST-Image; Q5 tREFI - **gestrichen 06.10.
      (Marco)**: nur auf Anfrage eines Besitzers per Issue; die Beschreibung in `boards/` bleibt
- [x] 4.3 `hy200-qz713df-a1`: 09-22-Einheit unbekannt (eMMC, DRAM, Sensor, Kamera, Motor) → per-Variante-Overlay - **gestrichen
      06.10. (Marco)**: nur auf Anfrage per Issue. Die Firmware hat dieselbe Produktkennung (`h713_tuna_p3`) wie die des
      HY300PRO-G-EU, aber einen Fokusmotor im Devicetree - wohl dieselbe Platine, andere Bestückung; Beschreibung bleibt
- [x] 4.4 FEATURES der Boards ohne Besitzerbericht bleiben leer; `boards/check.sh` soll FEATURES-Namen prüfen - **gestrichen
      06.10. (Marco)**: drei von uns gepflegte Einträge, `h713-features` warnt am Gerät ohnehin; die Regel „leer ohne
      Besitzerbericht" wird eingehalten
- [x] 4.5 `boards/README.md`: Tabelle „welcher Ordner ist mein Gerät" (im README drin, dort nicht) - 06.10.: Abschnitt
      „Which directory is my projector?" mit der Tabelle aus dem README
- [x] 4.6 An cstenger zurückmelden: Composition-Befund (`89`), D1-CCU Port 1, SIDDQ, Doorbell im MIPS-Sendepfad (aus `61`) -
      **gestrichen 06.10. (Marco)**: er nutzt GitHub nur zum Verfolgen

**5 Installer und Werkzeuge**

- [x] 5.2 `h713-hdcpkey` braucht eine `docs/tools/`-Seite - 06.10.: `docs/tools/h713-hdcpkey.md` (Beispiel aus einer synthetischen
      Region der Tests), verlinkt in README und `docs/README.md`; das Werkzeug meldet eine nicht lesbare Datei jetzt mit einer Zeile
      statt eines Tracebacks
- [x] 5.3 `hdcpitems.py` `KNOWN_SETS`: neue Geräte eintragen, sobald welche auftauchen - **gestrichen 06.10. (Marco)**: ein
      Ablauf, keine Aufgabe; der Installer druckt den Fingerabdruck zum Einfügen
- [x] 5.4 **`analyse/hdcp-keys/` nach `re/hdcp-keys/`** (entschieden 12.09., nie gemacht; jetzt 0700, aber falscher Ort) (aus `61`)
      - 06.10. verschoben (Umbenennung, 7 Dateien, Hashes gleich, 0700/0600); `referenz/` nachgezogen, `sperr-scan` deckt `re/` ab
- [x] 5.5 Netzwerkwerkzeuge im Rootfs prüfen: `ping`, `curl`, `wget`, `nc` (aus `61` — Stand unklar) - 06.10. am HY310: alle da,
      dazu `ip` und `ss`
- [x] 5.6 Kein Pflichtabzug, wenn Mainline drauf ist — prüfen, ob umgesetzt (aus `61`, zweimal gefordert) - umgesetzt
      (`h713-install` Schritt 3, N2); am 05.10. bei der Neuinstallation gesehen: kein neuer Abzug
- [x] 5.7 Drei tote defconfig-Zeilen `CONFIG_SND_SOC_SUNXI_H713_{CODEC,CPUDAI,MACHINE}=m` (aus `61`) - 06.10.: längst weg,
      stehen nur noch im zurückgenommenen Patch 0050
- [x] 5.8 19 Patches der Serie greifen mit Fuzz/Versatz (`.orig` im Baubaum) — neu aufsetzen (aus `61`) - 06.10.: es waren
      **66** (drei Hunks mit Fuzz, in 0001 und 0067), aus je einem Commit pro Patch neu erzeugt; neue Serie auf frisches
      Vanilla 6.18.38: 0 Versatz-/Fuzz-Meldungen, Baum identisch (`339822a8…`). Werkzeug `arbeit/patches-fuzz-20261006/`
- [x] 5.9 `identify.py` druckt „our layout" — Code-Reste aus ST5-DOCAUDIT §5 - 06.10.: „v3, doku/109" -> v4 mit Verweis auf
      `docs/subsystems/emmc-layout.md`; Versionszeile von `h713-install`/`dump.py` „0.1 (draft, doku/110)" -> 0.2 (Paket)
- [x] 5.10 Webpanel-Konzept (Ecke/Kante, Seitenverhältnis, Undo/Redo, Vorschau = Warp) (`61` Z. 555ff) - verschoben nach **9.13**
      (Marco 06.10.)

**6 HDCP-Härtung — Einbau mit dem Release-Neubau 1.1a (`doku/144` TEE-1…5, `doku/161`)**

- [x] 6.1 **TEE-2** EL3 liest den Schlüssel selbst; `push_from` ohne Aufrufer-Adresse ← zuerst. Mit 6.2 und 6.5 ein Paket:
      reine Härtung, nichts ist kaputt (heute schlimmstenfalls ein falscher Schlüssel durch Root, auslesen geht nicht).
      Marco 07.10.: als Agentenpaket machen. **07.10. vorbereitet, nicht gemessen** (`doku/161`): 6.1, 6.2, 6.5 und 6.9 als
      ein Paket in `arbeit/hdcp-haertung-20261007/` (TF-A 2, U-Boot 3 - davon `0001` = 6.6 -, Repo 2 Patches), gebaut,
      gegengeprüft. Gewählt: BL31 nennt die Ablage (`HDCP14_STAGE`), eine Senken-Schreibung pro Boot (`HDCP14_ONCE`),
      danach zu; EL3 liest den Schlüssel nicht selbst (eigener MMC-Treiber in EL3 unverhältnismäßig). Einbau und Messung mit **1.1a**
- [x] 6.2 **TEE-3** Strukturprüfung nach EL3 spiegeln - im Paket 6.1 (07.10.)
- [x] 6.3 TEE-1 S-EL1 nur, wenn eine zweite Nutzlast es lohnt (damals: `tfa-h713/0007`, gibt es seit 06.10. nicht mehr) - **gestrichen 07.10. (Marco: S-EL1
      nicht gewollt, weder in TF-A noch in U-Boot)**; der Testcode ist gelöscht, die Befunde stehen in `doku/153`, `irrwege.md`
- [x] 6.4 TEE-4 die 32 Byte Anhang des 320-Byte-Datensatzes erklären - **gestrichen 07.10. (Marco)**: Neugier, mit 288 Byte geht es
- [x] 6.5 TEE-5 Watchdog über Treiber; `0x48a00000` und Fenster ableiten statt Konstante - im Paket 6.1 (07.10.): WDT-uclass,
      Fenster als `SUNXI_TEE_WINDOW_*` in BL31 mit Herkunft (aus dem DT nicht ableitbar)
      - **09.10. (Marco): mitnehmen**, mit 1.1a (`doku/178`)
- [x] 6.6 `h713_hdcp14_wait`-Env ganz entfernen? (entschärft, existiert noch) - **07.10. vorbereitet**: U-Boot-Patch + Gegenstück für
      `check-hdcp-artifacts.sh` in `arbeit/hdcp-wait-env-20261007/patches/`, hy310/release gebaut (gleiche Warnungen wie vorher,
      Schalter weg aus dem Binary), passt auf die Linien; Einbau und Messung mit **1.1a** (Marco 07.10.: ja)
- [x] 6.7 Warteschleifen-Patch (`0035`, Suche der Wait-Site) prüfen: noch nötig, seit die Senke rechtzeitig gefüllt ist? (Marco 14.09.: „muss am Ende weg")
      - **beantwortet, bleibt**: am 05.10. gemessen hängt die Box mit scharfer Warteschleife auch mit Schlüssel in der Senke
- [x] 6.8 BL32-Experiment (5 unversionierte Dateien in `FB-HDCP14h/uboot`): Branch oder löschen - **gelöscht 07.10. (Marco)**
- [x] 6.9 **BL32-/S-EL1-Gerüst aus dem TF-A-Fork** (Patch 0006, Kopf `4c1bd8c6`; Marco: kein S-EL1 in TF-A): TSP-Definitionen
      (`platform_def.h`), Hersteller-OP-TEE-Übergabe (`H713_BL32_AARCH32`), `optee@48600000`-Reservierung (`H713_WITH_BL32`),
      Schalter in `platform.mk`. **Zuerst klären:** `H713_WDOG_BRINGUP` ist immer gesetzt und schaltet bei jedem Boot den
      Watchdog „for the BL32 bring-up" scharf - **ja, das ist das Netz gegen Hänger beim Booten** (07.10. gelesen: ~11 s ab BL31,
      setzte am 05.10. einen Hänger zurück): er bleibt, raus aus dem BL32-Block, ehrlich benannt. `H713_VENDOR_SECURITY_SETUP` ist
      ebenfalls immer an und kein Gerüst (Sicherheitskonfiguration wie der Hersteller-BL31) - bleibt. Raus: TSP-Block,
      AArch32-Übergabe, optee-Reservierung, BL32-NOTICE, `H713_SKIP_SECURITY_SETUP`-Probe, die Schalter. Ändert das BL31 (der
      BL32-Eintrag wird heute immer befüllt) - also Boot-Test mit 1.1a.
      Nachweis wie `doku/153`: BL31 vorher/nachher vergleichen (gefunden von der Gegenprüfung 07.10., `doku/160` §3)
      - **07.10. im Paket 6.1** (`doku/161`): Gerüst raus, `SPD` ungleich `none` bricht den Bau ab, `H713_BOOT_WATCHDOG`;
        6.9 allein ändert nur `bl31_early_platform_setup2`, die Watchdog-Schreibzugriffe identisch. Gelernt: das Netz reicht
        nur bis U-Boots Watchdog-Init (`sunxi_wdt_probe()` stoppt ihn)

**7 Dokumentation und Repo**

- [x] 7.1 `AGENTS.md` besprochen (06.10.): die vollstaendigen Arbeitsregeln (Kopie, Lieferung mit Kompilat, tor.sh,
      Identitaet, Geraet, Subagenten, Projektordner-Karte) liegen **lokal** in `referenz/arbeitsregeln.md` und werden
      ueber `/opt/Projekte/h713/CLAUDE.md` (Symlink) und einen Block in `~/.claude/CLAUDE.md` in jede Sitzung und jeden
      Subagenten geladen; die veroeffentlichte `AGENTS.md` bleibt absichtlich unveraendert (Marco: nicht committen).
      Erzwingbares ist in Hooks: `.githooks/pre-commit`, `pre-push` (auch in den Forks), `release/tor.sh`
- [x] 7.2 OKF-Frontmatter (`verified`, `stale_after`) in allen `referenz/`-Seiten, `referenz/stale.py` listet Faelliges (06.10.)
- [x] 7.3 Unzitierte Journaleintraege: 25 Ueberholt-/Umgesetzt-Marker (alte Handoffs, erledigte Plaene); `doku-index`
      zaehlt Nachtlog-Belege nicht mehr als unzitiert, kennzeichnet Marker; Analysen 89/72/73 aus `display.md` zitiert.
      Rest: 95 netboot (gueltiges How-to ohne Heimat), 149/150/152 (aktuell) (06.10.)
- [x] 7.4 Journal: eine Quelle. Repo-Kopie war in allen 40 abweichenden Dateien die neuere (satzweise geprueft:
      Zeichensatz + Redaktion); drei Abschnitte aus `40-display.md` uebernommen; alter Master jetzt
      `/opt/Projekte/h713/doku-archiv-bis-20261005/` (0700, Originale). Links `121`/`86` waren in Ordnung (06.10.)
- [x] 7.5 `hy310-logs` war ein identisches Duplikat von `h713-logs` im Overlay; jetzt Symlink, wie `build-rootfs.sh` ihn prueft (06.10.)
- [x] 7.6 Verweise auf geloeschte Pfade: nichts Lebendes kaputt - die lokalen Fixture-, Arbeits- und Firmware-Pfade,
      die Skripte nennen, existieren; nur historische Briefe (`analyse/boot/arbeit/`, `mainline/docs/wifi-*`) nennen
      alte Kernelbaeume. Die Tore (sperr-scan Regel 7) finden Verweise auf den alten Arbeitsordner in Leserdoku (06.10.)
- [x] 7.7 Sicherungs-Tags `vor-main-umzug/*` (3) geloescht - alle in main (06.10.)
- [x] 7.8 Branches: `fable-main`, 9x `von-src/*`, `sicherung/main-vor-mailfix`, `arbeit/doku-7` geloescht (alle in
      main; 06.10.), Fork-Sicherungen ebenso. `hy300-pro-ab-lokal` (+145 Commits, Stand 20.09.) am 06.10. gemessen:
      561 geaenderte Dateien, 0 fehlen in main, Code zu 90-100 % enthalten, der Rest ist main's neuere Fassung
      (ST3-BOARDMERGE) - geloescht (Marco). Auf GitHub bleibt `origin/hy300-pro-ab` (aelterer Stand, loeschen = Push)
- [x] 7.9 Drei Abzuege gehasht (06.10.): stock emmc-voll `33e1ffc4…`, HY300-Pro emmc-full `af2deb6a…`,
      bootbereich-8mib `e16acad0…` - in `referenz/artefakte.md`
- [x] 7.10 `doku/149` §5 Stand 06.10. nachgetragen und in die Repo-Kopie uebernommen (lag nur im Master)
- [x] 7.11 `SICHERUNG-{tee-experiment,tfa,wifi}` in FB-HDCP14h geloescht (06.10.); Geraetesicherungen bleiben
- [x] 7.12 `referenz/irrwege.md`: rchar, OOM/ROOM-Regex, `ssh -n`, modroot ohne aic8800, `kill -9` auf MemPalace,
      Hypothese vor Messung, Agent ohne Kompilat (06.10.)
- [x] 7.13 `/home/user/AGENTS.md` ist seit 06.10. ein Symlink auf `~/.claude/CLAUDE.md` — eine Quelle

**8 Lokale Werkzeuge**

- [x] 8.1 MemPalace vollständig: Transkripte (~67 000 + 86 000 sweep), referenz/ (268),
      repo-neu ohne Submodule (20 373) — 175 798 Drawers, Endstand 05.10. 17:15.
      Lehre: `mine`/`sweep` nie laufen lassen, während Claude antwortet — der Stop-Hook
      sperrt den Palast und einzelne Dateien scheitern (dann erneut sweepen, idempotent)
- [x] 8.3 Graphify installiert, `--code-only` über `repo-neu/` (7 862 Knoten, 0 Token),
      Eintrag in `werkzeuge.md`, `.graphifyignore` + `graphify-out/` in `.gitignore` (05.10.)
- [x] 8.10 Worktrees aufräumen, sobald Marco die Testabbilder nicht mehr braucht - **erledigt 09.10. 16:56** (Marco), Referenzabbild
      `arbeit/r2-20261009/abbild-r2test4/` bleibt; auch der Worktree von 2.30 ist weg: `arbeit/crust-release-20261007/wp8-bau/repo`,
      `arbeit/r2-20261009/repo` (r2test1-3), `arbeit/r2-20261009/main-int` (r2test4, läuft auf der Box); Zweige bleiben
- [x] 2.35 **IR-Fernbedienung kann keinen Standby auslösen**: der IR-Empfänger hat unter Linux keine Tastenbelegung
      (`rc-empty`, nur `lirc`), `h713-power` sieht kein `KEY_POWER` von dort. Gekoppelt per Bluetooth geht es (G-EU, `doku/184`),
      Wecken per IR geht über crust. Vorschlag: eine Keymap (NEC, Power-Code der Stock-Fernbedienung, crust kennt die 19 Codes)
      mit `KEY_POWER` im Abbild - dann geht die Fernbedienung auch ohne Kopplung (hilft, wo Bluetooth wackelt, 1.4)
      - 10.10.: am HY310 genauso (keine IR-Belegung; dort geht Power über die gekoppelte BLE-Verbindung). Gleiche Fernbedienung an
        beiden Boxen (Marco); am G-EU war sie nur noch nicht mit unserem System gekoppelt. Verbesserung für beide, nicht dringend
      - 10.10. abends (Marco, Lauf k1 Kaltstart-Gate): Power auf der IR-Fernbedienung weckte den G-EU aus crusts Aus, der laufende
        HY310 daneben blieb an - wie erwartet ohne IR-Belegung. Bedenken, wenn 2.35 kommt: beide Boxen hören denselben Code; ein
        Druck würde dann die eine wecken und die andere ausschalten
      - **Erledigt 11.10.2026** (`doku/193`, Paket `arbeit/einblendungen-20261011/`): Kernel 0252-0254 - der Empfänger mit 8 MHz
        statt 24 (die Ursache, dass NEC nie dekodierte), die Keymap `rc-h713-fd02` mit Power; am HY310 alle 14 Tasten, Power geht an
        h713-power/logind. Das Bedenken bleibt: beide Boxen hören denselben Code
- [x] 2.43 **Ein Einblende-Zeichner auf Kanal 2** (Gesamtplan `doku/192` §5, Marco 10.10.: "überlebenswichtig"): alle
      Einblendungen (Lautstärke, Stumm, Fokus, Ausschalten 2.38) gestapelt in **einem** ARGB-Bild auf Kanal 2 über dem Video
      (Kernel 0251, Primär-Ebene `zpos` 2). Zeichnen aus Deepseeks `osd.c` (Paket `warp-konsole`) übernehmen, **die Optik neu**
      (Marco: Ausführung ungenügend). Bei Trapez mit derselben Homographie wie der Warp vorverzerrt (gemessen K5), neu gerechnet
      nur bei Änderung von Inhalt oder Ecken. Committen muss der DRM-Master: heute `h713-tv` (`ctl osd ...`, Zeichner als
      Bibliothek) oder per DRM-Lease. Löst den Weg "OSD im Warp" (2.7a, Paket `warp-konsole`) ab - das Paket umlenken
      - **Erledigt 11.10.2026** (`doku/193`): `h713-osd` (Dienst) mit `libh713osd` (Zeichnen, SDF, eigene Optik nach Mock-ups:
        Pille unten mittig, Stumm-Zeichen oben rechts, Fokus-Ende rot), vorverzerrt über dem Warp, Kanal in `h713-tv`
        (`osd claim|show|hide|picture|release`, mitreisend im Warp-Commit); 7-15 ms je Einblendung, 0 verlorene Warp-Bilder.
        Ohne Signal keine Einblendung (Marco: P5 gestrichen). Das Ausschalten 2.38 braucht noch Text (eine Schrift)
- [x] 2.44 **Eine Matrix-Quelle für die Trapez-Geometrie** (`doku/192` §5.4a): Ecken, Zoom, Projektionsmodus an einer Stelle mit
      Änderungsnachricht; Warp, Einblende-Zeichner (2.43) und später der Desktop-Compositor rechnen mit derselben Funktion
      - **Erledigt 11.10.2026** (`doku/193`): `libh713geom` = `matrix.c` + `config.c` aus h713-warp (dessen Code und Daten bitgleich)
        plus die Rückwärts-Abbildung (`inverse.c`); `/etc/h713/warp.conf` ist die Quelle, h713-osd liest sie per inotify
- [x] 2.46 **Tasten: `h713-keys` (IR + Bluetooth) erweitern** um Home, Menü, Maus, Record, Steuerkreuz (`doku/192` §5.5); dazu die
      IR-Belegung 2.35 (beide Boxen hören denselben Code)
      - **Erledigt 11.10.2026** (`doku/193`): `h713-keys` - Lautstärke und Stumm über h713-tv (Lauter und Leiser heben Stumm auf),
        Fokus 20 Schritte je Druck über h713-focus, Home/Menü/Zurück/Steuerkreuz/OK erkannt und vorgemerkt; Maus und Mikrofon senden per
        IR nur `0x0266` (Kopplungswunsch, jetzt `KEY_F6`); Record gibt es nicht - die Eingangstaste bleibt leer (2.52)
- [x] 3.4 IR FB-REMOTEb + fd02-Keymap — rein, wenn rx_resolution-Trunkierung / ARISC-Schreibpfad geklärt
      - **11.10.:** wird Teil von 2.46 (Tasten, Paket `arbeit/einblendungen-20261011/`): die vier Empfangs-Patches des IR-Pakets vom 03.10.
        (`doku/138`; 8 MHz, PL9 nach ARISC-Start und Resume) neu auf die Serie, die fd02-Belegung
        (15 Tasten, sieben am G-EU geprüft) als Kernel-Keymap mit Power - ohne sie kommt unter Linux kein IR-Code an (11.10. am HY310
        mit `nec` an: kein einziger Scancode). Damals offen geblieben: Maus- und Mikrofon-Taste senden per IR denselben Code
        (`0x66`, `doku/141`) - per IR nicht zu unterscheiden, per Bluetooth schon
      - **Erledigt 11.10.2026** in 2.35/2.46 (`doku/193`): 8 MHz und die Keymap ja, die PL9-Teile nein (sie antworteten auf die
        Hersteller-ARISC; mit crust PL9 Funktion 3, gemessen). Maus und Mikrofon `0x66` bestätigt
- [x] 1.1b **ARISC/crust: Taktik fürs Ausliefern, vor 1.1a besprechen** (Marco 10.10. nachts: "ich wollte crust eig zum
      default machen"). Heute wählt der Gerätebaum je Board die Firmware (`firmware-name`): HY310 crust, jedes andere Board
      die des Herstellers aus dem eigenen Abzug (`h713-arisc.bin`, `docs/subsystems/arisc.md`). Stand der zwei Modelle:
      HY310 mit crust abgenommen (R1/R2, `doku/177`); HY300PRO-G-EU: crust läuft seit 09.10. (`doku/182`), Standby, HDCP
      und Ton dort mit crust sind die offene Testmatrix aus 1.4 - **noch nicht gemessen**. Zu klären:
      - crust als Vorgabe für welche Boards: die zwei mit eigener crust-Konfig (HY310, G-EU `projector05061226`); die andere
        G-EU-Variante `projector09220931` (624 MHz) braucht eine eigene Konfig; Boards ohne gemessene Konfig (`hy300-pro`,
        `hy300-t08`, `hy350`, `hy200-qz713-v2`) bekommen ohnehin kein Abbild, nur Testabbilder - dort crust mit
        geliehener Konfig oder die Hersteller-Firmware?
      - der Weg mit der Hersteller-Firmware (Treiber, `h713-extract`): als Rückfall behalten oder abbauen
      - crust-Vorgabe ist nicht Standby-Vorgabe: Standby bleibt experimentell per Schalter (2.29)
      - Voraussetzungen: crust-Fork veröffentlicht (1.6, mit der G-EU-Konfig `c5b536f`), crust als Submodul statt `CRUST_SRC`
        (5.15), Spiegel `crust-h713/` neu
      - im selben Gespräch: 2.32 (echtes Aus über crust statt U-Boot-Schleife, 2,4 W gegen 0,3 W Stock)
      - **ENTSCHIEDEN 10.10. abends (Marco: "das klingt perfekt"):** **crust ist die Vorgabe auf jedem Board mit gemessener
        crust-Konfiguration** (HY310, HY300PRO-G-EU `projector05061226`), weil nur damit Standby und das echte Aus (0,3 W,
        `doku/188`) gehen. **Die Hersteller-Firmware bleibt als Rückfall** - immer aus dem eigenen Abzug mitinstalliert
        (`h713-extract` -> `/lib/firmware/h713-arisc.bin`, wie heute) und **einen Befehl entfernt**, nicht abgebaut. Boards
        ohne gemessene crust-Konfiguration (G-EU `projector09220931`, `hy300-pro`, `hy300-t08`, `hy350`, `hy200-qz713-v2`)
        laufen weiter mit der Hersteller-Firmware; keine geliehene Konfiguration (PB5-Vorfall 19.09.). Standby ist nicht die
        Vorgabe: `short = poweroff`, Standby per `h713-power set short standby` (2.29, 2.32). Umsetzung: **5.20**.
        Vor dem Release außerdem: crust-Fork auf GitHub (1.6, Kopf `54e4a08`), crust als Submodul (5.15), Spiegel
        `crust-h713/` auf dem Kopf (88 Patches); das Aus am HY310 ist seit `doku/190` gemessen (2.32)
      - **11.10. geschlossen** (Durchsicht der TODO mit Marco): entschieden 10.10. abends (Marco: "das klingt perfekt"): crust Vorgabe auf gemessenen Boards, Hersteller-Firmware als Rückfall; Umsetzung **5.20**
- [x] 2.6 Audio: Abschalt-Plopp -> **9.11 (spaet)**, Messungen und widerlegte Hypothese dort
      - **11.10. geschlossen** (Durchsicht der TODO mit Marco): war nur ein Verweis - der Abschalt-Plopp steht in **9.11**
- [x] 2.7a **Konsole durch den Warp** (aus 2.7, Marco 06.10.: bleibt offen): ohne Signal zeigt h713-tv die Konsole auf
      der primären Ebene, ohne Trapez und ohne Spiegelung - im ceiling-Modus steht sie auf dem Kopf. Wege: fbcon
      `rotate_all = 2` für ceiling (nur Drehung, kein Spiegeln), Firmware-Spiegel per RPC (FB-MIRROR 2.3/F3) oder der
      Warp liest `fb0` als Textur und zeichnet die Konsole mit (wie Stock, eigenes Paket)
      - **10.10. später abends (`doku/192`):** überholt durch den Gesamtplan - Einblendungen über Kanal 2 (2.43), die Konsole
        wird ein Terminal im Desktop (2.45), fbcon bleibt unverzerrte Notfallkonsole
      - 11.10.: dazu entschieden (Marco): **keine Einblendung auf der Konsole** - ohne Signal wartet h713-osd auf das Bild (`doku/193`)
      - **10.10. abends:** Weg entschieden - der Warp liest `fb0` als Textur und zeichnet die Konsole durch Trapez und Modus,
        zusammen mit dem OSD (2.38, 9.9). Paket `arbeit/warp-konsole-20261010/` für eine eigene Sitzung (`doku/189` §5)
      - **11.10. geschlossen** (Durchsicht der TODO mit Marco): **wird nicht gemacht** (Marco): fbcon bleibt die unverzerrte Notfallkonsole (`doku/192`), keine Einblendung auf der Konsole (11.10., `doku/193`) - Einblendungen gibt es nur über dem HDMI-Bild. Das Paket `arbeit/warp-konsole-20261010/` (Warp zeichnet Konsole und OSD) ist damit überholt; Zweig `versuch/warp-konsole` bleibt als Beleg, Worktree entfernt
- [x] 2.14 Reinstall setzt Einstellungen und Fernbedienungs-Pairing zurück — heute selbst erlebt (wifi.env → AP-Modus),
      Lösung in **1.2b** (Installer übernimmt `/etc/h713`); Pairing bleibt zusätzlich offen
      - **11.10. geschlossen** (Durchsicht der TODO mit Marco): aufgegangen in **1.2b** (Einstellungen) und **2.54** (Kopplung)
- [x] 2.48 **0251 nachmessen** (`doku/192` §3): Bildrate der Aufnahme mit 0251 während einer Einblendung bei laufendem Warp,
      Farben genau, `premultiplied`/`coverage` (keine Blend-Mode-Eigenschaft), `zpos`-Wechsel bei laufendem Seitenwechsel,
      Signalverlust/-rückkehr, Standby mit Einblendung, der G-EU
      - **11.10. gemessen** (`doku/193` §5): 81 Wechsel in ~5 s über dem Warp - 0 verlorene Bilder; gerades Alpha (zwei Testbilder,
        Marcos Augen); Signal weg/zurück und Standby sauber, die Einblendung kommt von selbst wieder. Farben: Marco "fühlt sich gut an".
        Offen: der G-EU (720p, nur am Rechner gerendert); `zpos`-Wechsel bei laufendem Seitenwechsel ist mit dem Mitreisen im
        Warp-Commit entfallen
      - **11.10. G-EU gemessen** (`doku/195`): dieselben zehn Stufen auf 720p bestanden, Stufe 7 erst mit einem Fix in h713-osd
        (das Stumm-Zeichen zieht nach, wenn der Warp nach dem Ring übernimmt). Offen nur noch: Farben genau gegen die Mock-ups
        (bisher Marcos Auge)
      - **11.10. geschlossen** (Durchsicht der TODO mit Marco): gemessen am HY310 (`doku/193` §5) und am G-EU (`doku/195`); die Farben nach Marcos Auge ("fühlt sich gut an", "passt") - kein eigener Punkt mehr
- [x] 5.13 `release/tor.sh` in einem gebauten Worktree: `sperr-scan` meldet die Bauerzeugnisse (`mainline/build/`, `*.img`) und
      bricht an root-eigenen Dateien (`installer/tmp/`) ab; am 08.10. lief das Tor deshalb auf einer sauberen Kopie des
      Commit-Stands. Entweder den Scan auf verfolgte Dateien plus Submodule begrenzen oder das Muster dokumentieren.
      **09.10.:** Ursache gefunden - in einem Git-Worktree ist `.git` eine Datei, `sperr-scan.py` prüft `os.path.isdir` und
      erkennt das Git nicht (Durchsicht B1); Behebung `os.path.exists`, eine Zeile. 09.10. abends bei 2.30 wieder getroffen. Bis dahin: Tore auf `git checkout-index`-Abzug
      - **11.10. geschlossen** (Durchsicht der TODO mit Marco): behoben 11.10. (`3bfdfa3`: `sperr-scan` erkennt die `.git`-Datei eines Worktrees und prüft nur verfolgte Dateien); das Tor lief am 11.10. im gebauten G-EU-Worktree grün
- [x] 7.18 Release-Text: „nothing acts on the remote's keys yet except Power" so lassen? [M]
      - **11.10. geschlossen** (Durchsicht der TODO mit Marco): überholt: seit 11.10. wirken Lautstärke, Stumm und Fokus (`h713-keys`, `doku/193`); der Release-Text nennt das mit **1.8**
- [x] 8.8 HY310: seit 10.10. 00:30 per `poweroff` aus, steht im Gate (Marco), Sonoff an. Nachtregel „herunterfahren" offen. **Vor Sonoff-aus USB ziehen.** Seit 09.10. abends `h713_gate=1`:
      nach Netz-Ein wartet die Box auf die Taste, ein Fern-Hartreset kommt nur bis ins Gate (`referenz/geraete.md`)
      - **11.10. geschlossen** (Durchsicht der TODO mit Marco): Zustandsnotiz vom 10.10., überholt - der Stand der Geräte steht in `referenz/geraete.md`
- [x] 8.10 **Cloud-Guthaben für Offline-RE nutzen** (Marco 10.10.: ~100 $ Claude-Cloud, Sonnet; 2-3 Aufgaben). Ein privates
      GitHub-Repo je Thema mit allem, was der Agent ohne unseren Tisch braucht: die Herstellerbinärdateien **ohne** Schlüssel,
      Abzüge, Seriennummern/MACs, dazu von uns vorbereitete Disassemblies (OR1K über unser `or1k-elf-objdump`, AArch64 über
      `llvm-objdump`, MIPS über capstone) und Ghidra-Exporte (Pseudo-C, Strings, Querverweise) - dann braucht der Agent kein
      Ghidra, nur Python/capstone. Auftrag nach `~/.claude/AGENT-KONTEXT-VORLAGE.md` (Zweck, Rechtsrahmen Art. 6 RL 2009/24,
      Ausgabe: ein BERICHT.md im Repo), Repos danach löschen. Heikles (TEE, HDCP) bleibt draußen. Themen:
      - **A "Aus" wie Stock (2.32):** was tun Herstellerkernel, Stock-BL31 (SYSTEM_OFF) und die Hersteller-ARISC-Firmware
        (`scp.bin`, OR1K) beim Ausschalten, dass das Gerät 0,3 W zieht - welche Schienen/Pins (Stock `standby_param`: vdd-cpu,
        vdd-sys, vcc-pll, vcc-dram alle an PL6), PLLs, DRAM, wie die Taste weckt. Grundlage für "Aus über crust"
      - **B Einschlafen ohne Hänger (C1):** wie der Herstellerkernel (tvcap/tvfe/INCAP-Module) die Aufnahme-DMA vor dem Suspend
        anhält; dazu der Audio-DSP (msp) beim Aufwachen (2.37)
      - **C klein: Log-Stufe der Display-Firmware (2.36):** in `display.bin` (MIPS) die Stelle, die `MsgHandle_SKE_SEND_EKS`
        loggt, und welche elog-Stufe sie braucht; `display_cfg.xml`-Auswertung
      - **Form (Marco 10.10.: "A B C sind perfekt"):** ein privates Repo, `main` mit Auftrag, Rechtsrahmen und gemeinsamen
        Werkzeugen, je Thema ein Zweig (`a-aus`, `b-einschlafen`, `c-loglevel`) nur mit dessen Material; der Cloud-Agent arbeitet
        auf seinem Zweig und liefert per PR (BERICHT.md, Notizen, ggf. Patch-Entwürfe). Lokal vorbereiten, dann anlegen
      Repo anlegen und Hochladen = Veröffentlichen an einen Dienst -> nur mit Marcos Ja
      - **10.10.: alle drei geliefert und ausgewertet** (`doku/187`; A und B direkt auf ihren Zweig, C als PR #1). Kernaussagen
        gegen das Material nachgeprüft. Lokaler Klon mit allen Zweigen: `arbeit/cloud-re-20261010/repo`. Offen: Marco löscht das
        Repo `well0nez/h713-offline-re` auf GitHub
      - **11.10. geschlossen** (Durchsicht der TODO mit Marco): alle drei Aufgaben geliefert und ausgewertet (`doku/187`); übrig ist nur Marcos Löschen des Repos auf GitHub
- [x] 8.9 L018 (`.127`) und HY350 (`.163`) heute nicht erreichbar
      - **11.10. geschlossen** (Durchsicht der TODO mit Marco): Tagesnotiz - die Adressen stehen in `referenz/geraete.md`
- [x] 9.8 **Warp-Check: CPU-Last senken?** h713-warp hat heute 1 h 26 min CPU in ~10 h gebraucht (Prüfstand);
      messen, wo die Zeit hingeht (Readback/`check`, Fence-Warten, Poll-Takt), und ob der GPU-Pfad bei
      Identität ganz schlafen kann (Marco, 05.10.)
      - **11.10. geschlossen** (Durchsicht der TODO mit Marco): aufgegangen in **2.47** (Warp sparsamer)
- [x] 9.9 Fernbedienung auswerten (war 2.2): 16 Tasten + Maus kommen als Events an, nur Power wirkt — braucht
      einen Desktop/eine Oberfläche, die etwas damit anfängt (Marco 05.10.: spät)
      - 10.10. abends: Lauter/Leiser, Stumm, Fokus (BLE: 115/114, 113, F4/F5) mit OSD im Paket `arbeit/warp-konsole-20261010/`
        (neues `h713-keys`); Power bleibt bei `h713-power`
      - **11.10. geschlossen** (Durchsicht der TODO mit Marco): erledigt mit 2.46 (`h713-keys`, 11.10.): Lautstärke, Stumm, Fokus wirken per IR und Bluetooth, Home/Menü/Zurück/Pfeile werden erkannt; was die Navigationstasten tun, gehört zur Oberfläche (9.4, 2.45)
- [x] 5.21 **`build/build.sh kernel` ohne U-Boot-Submodul:** `find_mkimage` baut `mkimage` aus dem U-Boot-Submodul und packt
      ohne es keinen FIT; Rückfall auf das `mkimage` des Systems (der Container hat `/usr/bin/mkimage` 2025.10). Gefunden im
      Paket `osd-a` (`doku/192` §6)
      - 11.10.: `MKIMAGE=` als Handweg in `build.sh` (`8f2c992`, so im Container gebaut); offen: der Rückfall von selbst
      - **11.10. geschlossen:** erledigt 11.10. nachts (`ee4b5b8`, `doku/196`): ohne U-Boot-Submodul packt das `mkimage` des Systems den FIT; ein vorhandenes, kaputtes Submodul bleibt ein Fehler. Im echten Kernelbau des Pakets `warp-sparsam` bestätigt (lief ohne `MKIMAGE=` durch)
- [x] 5.22 **Kernel-Patchordner aufräumen:** die zurückgenommene `0011-misc-add-sunxi-nsi.patch` liegt noch in `patches/kernel/`
      statt in `zurueckgenommen/`; `mainline/patches/README.md` nennt veraltet "0001 ... 0161, 149"
      - **11.10. geschlossen:** erledigt 11.10. nachts (`647ad00`): 0011 liegt in `zurueckgenommen/`, der Serien-Index zählt 278 (0001 … 0254); `series` und Eingabe-Hash unverändert
- [x] 2.47 **Warp sparsamer** - eigenes Paket, erst messen (`doku/192` §5.6): `sugov:0` kostet 14,6 % eines Kerns, so viel wie der
      Warp (14 %). Ansätze: fester Takt oder `rate_limit_us`; `-O3 -mcpu=cortex-a53`, LTO, NEON; der Warp committet selbst statt
      über den `h713-tv`-Socket; EGLImage je Slot einmal; GPU-Fences statt Abfragen; gleiche Bilder überspringen; Luma/Chroma in
      einem Durchgang; GPU-Takt
      - **11.10. G-EU** (`doku/195` §4): nach dem Start aus dem Bypass lief der Warp mit ~50-56 fps (7-9 verspätete Bilder/s),
        ohne Wärmedrosselung; nach einem Aus/An 59,3 fps. Momentaufnahme davor GPU 600 statt 696 MHz, `sugov:0` 13 % - Verdacht
        GPU-Regler, nicht gemessen. Erste Messung des Pakets: Warp aus dem Bypass starten und `devfreq` mitschreiben
      - **11.10. nachts gemessen und zum Teil erledigt** (`doku/196`, Paket `arbeit/warp-sparsam-20261011/`): CPU-Last mit Warp
        **halbiert** (alle Kerne 5,9 → 2,9-3,1 %) - schedutil `rate_limit_us` 462 µs → 20 ms per tmpfiles (`179ba83`), h713-tv
        zählt verspätete Bilder statt je Bild eine Journalzeile (`d6574fa`). Compilerflags: kein Effekt. GPU-Regler: unauffällig.
        Die fehlenden Bilder (30-41 fps) setzt die Aufnahme selbst, am Flip-Zeiger gemessen, auch ohne Warp; ein afbd-Versuch
        dagegen ist widerlegt. **Offen:** (a) mit bewegtem Bild messen, ob die Aufnahme dann 60 liefert (`zeiger.py` im
        Bypass und mit Warp) - bei stehendem Bild fallen vermutlich nur Wiederholungen weg; (b) ein Render-Durchgang je Bild
        statt zwei (NV12-Ziel als ein R8-Bild Breite × 1,5 Höhe): ~250 µs CPU je Bild weniger, braucht Augen an der Wand
      - **11.10. früh:** (a) mit kreisendem Mauszeiger am gesperrten ThinkPad weiter ~40 Bilder/s, auch ohne Warp - die
        Aufnahme verliert also wirklich Bilder (gültig nur, wenn der Zeiger auf der Wand zu sehen war; mit Video
        wiederholen); Gegenprobe am HY310 (1080p-Panel, dort 59,5 fps) steht aus. (b) **gebaut, gemessen, verworfen**
        (Zweig `versuch/warp-einpass`, Test T1e: gleich den zwei Durchgängen bis 2 LSB): 14 % weniger Warp-CPU, aber die GPU
        meist auf Höchsttakt und ~1 Bild/s `busy` verworfen - die zwei Durchgänge bleiben
      - **11.10. früh: Ursache der fehlenden Bilder gemessen** (`doku/196`): ThinkPad-Ausgang kurz auf 1280×720 @ 60 -
        Aufnahme am G-EU **59,8 Bilder/s**, jeder Abstand eine Bildzeit, still wie bewegt; zurück auf 1920×1080 @ 60 - 30-53/s.
        Die Firmware verliert Bilder beim **Herunterskalieren 1080p → 720p** in der Aufnahme, nicht der Warp, nicht der
        Treiber, nicht der Takt, nicht der Bildinhalt (der HY310 mit 1080p-Panel skaliert nicht: 59,5 fps). Weiter in 2.56
      - **11.10. abends erledigt** (`doku/201`, Paket `arbeit/warp-zeichnen-20261011/`, Marco: "wirklich alles in Betracht ziehen"):
        **GPU-Zeit je Bild 6,05 → 1,78 ms** (Soft-Edge als eigener Ring-Durchgang; die G31 versteckt keine Texturlatenz hinter
        Rechnung), GPU-Regler parkt bei 288-432 statt 600-696; **CPU-Regler:** die Panfrost-IRQ-Threads (SCHED_FIFO) trieben
        schedutil 40×/s auf 1296 MHz - `h713-cpufreq.service` setzt sie auf SCHED_OTHER und das 20-ms-Limit (tmpfiles griff beim
        Boot nicht): Takt 98 % bei 480 MHz, sugov 0,1 %; **Latenz:** `hold off` Vorgabe (mit 0255 ist der Slot fertig; `hold on`
        wäre jetzt riskant); `ctl trace N gpu` zeigt CPU je Schritt und GPU-Zeit aus der Fence. Warp-CPU je Bild bleibt ~0,8 ms
        bei 1296 MHz (Mesa/Panfrost je Batch, Compute-Dispatch gemessen und verworfen). Offen → 2.60, 2.61
- [x] 2.10 EDID: 1080p100/120 weiter hinter `ctl edid block1` (Entscheidung offen). **Geklärt 05.10.:** 1600×900,
      1920×1200, 1600×1200, 2560×1600 und 1024×768i rasten nicht, weil die Firmware-Tabelle sie nicht kennt —
      unsere EDID bietet sie auch nicht an (der i915 generiert sie selbst); kein Fehler unsererseits
      - **11.10. geschlossen (Marco):** nein - 1080p100/120 bleibt hinter `ctl edid block1`, "braucht keiner"
- [x] 2.24 Kleinkram aus `61`: `regulatory.db` load failed -2; `r8152` will `rtl8153b-2.fw` - Marco 05.10.: **nicht
      jetzt**, Pakete `wireless-regdb`/`firmware-realtek` erst, wenn jemand sie braucht
      - **11.10. geschlossen:** `regulatory.db` lag längst im Rootfs (`wireless-regdb`); cfg80211 ist eingebaut und sucht sie, bevor das Rootfs hängt. `h713-wifi` macht jetzt `iw reg reload` vor `iw reg set`, damit das Land aus `wifi.env` (`country=`) gilt statt still 00 - am G-EU gemessen (00 → DE). r8152: Marco benutzt keinen USB-LAN-Adapter mehr, Meldung bleibt (keine Firmware-Blobs)
- [x] 2.27 **`h713-tv ctl off` hält nicht** (08.10., r1test2): Status zeigt `console` etwa 1 s, dann wieder `warped`, ohne
      `ctl auto` und bei stehendem Signal (Belege `arbeit/crust-release-20261007/geraet-20261008/kamera/`). Laut Hilfe gilt
      `off` "until auto". Ursache klären (Signal-Ereignis der Quelle? `start=last`?), dann beheben (Marco 08.10.)
      - **11.10. geschlossen:** Ursache: `warp claim` prüfte `POLICY_OFF` nicht, der Warp fragt jede Sekunde und bekam das Bild zurück. h713-tv lehnt den Claim bei `off` jetzt ab. G-EU, Trapez an: vorher nach 2 s wieder `warped`, nachher 8/8 s `console`, `ctl auto` → `warped` nach 2 s
- [x] 2.50 **Lüfter-Notaus (Paket FB-SAFETY 0001/0002)**, geparkt seit 02.10. und beim Umzug nach `TODO.md` am 05.10. verloren
      gegangen, wiedergefunden im Patch-Abgleich 11.10.: `hy310-board-mgr` schaltet nach einem Lüfterstillstand als Rückfall hart aus,
      und der Stillstand-Poweroff greift erst, wenn der Tacho einmal Drehung gemeldet hat. Am Gerät nie gemessen (Test B7, `doku/134`:
      Lüfterstecker unzugänglich). Neu auf die Serie setzen und einen Weg finden, den Stillstand ohne Stecker vorzutäuschen
      - **11.10. geschlossen (Marco):** der Stillstand-Poweroff (0159/0159a/0211) ist verifiziert und gilt als funktionierend; die zwei FB-SAFETY-Extras (harter Rückfall, erst nach gesehener Drehung scharf) entfallen

### Aus den Abschnitten 1-9 hierher verschoben (12.10.2026 nachts; Nummern bleiben, Verweise gelten weiter)

- [x] 2.4f Keystone für Ringe mit unausgerichtetem Pitch (SD- und PC-Modi): Warp braucht einen 64-aligned Import
      - 12.10. (`arbeit/wurzeln-20261012/` §5): betrifft 800x600 (Pitch 800), 720x576/720x480 (720), 1280x1024 (912). Weg A (Ring 64-ausgerichtet
        anlegen) **geht nicht**: INCAP schreibt nach einem Override von `+0x924` weiter mit dem alten Pitch, auch nach Enable aus/an, und die Firmware
        setzt den Wert bei jedem Umbau neu (Pitch = Breite auf 16). Bleibt Weg B: linearer Import im Warp (Textur 2048 breit, Shader adressiert
        `y·pitch + x`, bilinear von Hand), ~+1 ms GPU, ~ein halber Tag. Entscheidung Marco
      - **12.10. abends entschieden (Marco): bleibt so** - "die Auflösung nimmt eh niemand"; Bild ohne Trapez, der Warp sagt es im Status.
        Festgehalten in `docs/tools/h713-warp.md` "Limits" und `docs/known-issues.md`; Weg B steht hier als Entwurf, falls es doch gebraucht wird
- [x] 2.5 HY300-Lampe: Testplan `doku/143` §11 (Foto gegen Stock, PWM-Block lesen)
      - **12.10. (Marco): längst gelöst** - die blasse Wand am HY300 war das LVDS mit 6 Bit (`doku/137`, U-Boot `2de0cc8`, in `main`);
        die Lampe ist auf HY310 und HY300 auch unter Stock nicht dimmbar (06.10.). Nichts mehr zu messen
- [x] 2.9 Keystone: Langlauf 05.10. ~8 h Warp an, 59 fps, RSS flach, 20× an/aus ohne Leck (Prüfstand) — der
      Langlauf-Teil ist erledigt; offen: automatische Korrektur ohne `/etc/h713/keystone-ref` gegen Ideal-Pose
      - **12.10. (Marco): gestrichen** - die Automatik gegen die Ideal-Pose ist seit 26.09. so gebaut wie Stock gegen `GsInitXYZ`
        (`docs/tools/h713-keystone.md`); eine eigene Messreihe dafür ist "zum jetzigen Zeitpunkt und auch generell unnötig"
- [x] 2.16 Frame während laufendem Commit wird verworfen (`ok busy`) — Prüfstand 05.10.: normal 2–5 busy auf
      100–16 000 Commits, einmal 31/59 bei 50-Hz-Quelle (Schwebung 50↔60 Hz). Design mit drei Puffern; nur beobachten
      - 12.10. abends (HY310, `main` db558e3, `arbeit/hy310-main-20261012/`): 2 von 1927, 0 von 11230 nach 12 min, 3 von 238 direkt
        nach einem Warp-Start - normal, nur beobachten
      - **12.10. abends erledigt (Marco):** beobachtet, normal - zu
- [x] 2.22 eMMC: `data error cmd18` am GEU (einmal); **05.10. 23:03 am HY310:** ~2 min nach dem Boot haengt jeder
      Plattenzugriff (ls /boot, dmesg ueber Shell, Konsolen-Login), ssh/uptime antworten - Kernel 0184 frisch gebootet,
      Ursache offen, nach Stromzyklus alles normal, keine mmc-Fehler im Log. Beobachten. *Überholt (11.10.):* "Journal ist persistent" - stimmt nicht, `10-h713.conf` hat `Storage=volatile`, siehe 1.2a
      - **12.10. abends** (HY310 auf `main` db558e3): 5 Warmstarts, je bei 151 s fünf Plattenzugriffe mit Zeitlimit (ls /boot, dmesg,
        Datei lesen, schreiben+sync, journalctl) - 5/5 sofort, 0 mmc-Fehlerzeilen (`arbeit/hy310-main-20261012/laeufe/warmstart-reihe.txt`)
      - **12.10. abends erledigt (Marco):** nicht reproduziert; wieder öffnen, wenn ein Hänger auftritt
- [x] 2.26 **HDCP 1.4 nach einem Moduswechsel der Quelle** (`doku/170` §3): fordert der ThinkPad (i915) sofort beim Modeset an,
      bleibt er auf `Desired`; 2 s später angefordert steht `Enabled` nach 5 s. Mit der Hersteller-ARISC-Firmware und dem
      Fire-TV-Stick vergleichen (Auflösungswechsel), erst dann entscheiden, ob der Empfänger früher bereit sein muss
      - 10.10. (G-EU, crust, `doku/184`): auch nach Neustart und Standby der Box fragt i915 nicht von selbst neu an (`Desired`),
        mit neuer Anfrage sofort `Enabled`; der Fire-TV-Stick (2.2) verhandelte nach jedem Neustecken von selbst neu
      - **12.10. abends gemessen (HY310, `main` db558e3, ThinkPad i915, `hdcp-verzoegerung.sh`):** Moduswechsel 1080p50 -> 1080p60, Anforderung
        nach d s: d=0 **Enabled nach 3,06 s**, d=0,5 bis 3 nach 1,14-1,21 s. "Bleibt auf Desired" tritt am HY310 nicht auf; der Vergleich
        mit der Hersteller-ARISC-Firmware braucht 5.20
      - **12.10. abends erledigt (Marco):** am HY310 kein Stall; am G-EU war es das Verhalten der Quelle (i915 fragt nicht von selbst neu an), kein Fehler bei uns
- [x] 2.36 **HDCP-2.2-Beweis am G-EU ohne `SKE_SEND_EKS`-Zeile**: gleiche `display.bin` wie der HY310 (`16c74a28...`), aber im
      Firmware-Log (Abbild-Stufe, `h713_disp init` ohne `elog=`) nur "HDCP Process cost tick". Klären, ob die HY310-Zeile vom
      05.10. aus einer höheren Log-Stufe kam; `referenz/messregeln.md` HDCP 2.2 danach nachziehen. Bis dahin: Bit LINK 0x422 +
      neue Sitzung je Neustecken
      - **10.10. Cloud-RE C (`doku/187`): geklärt aus dem Listing.** `MsgHandle_SKE_SEND_EKS` ist nur der Funktionsname des
        Log-Aufrufs; die Format-Maske (`0xA7`, fest beim Start) druckt Funktionsnamen auf keiner Stufe. Die Zeile
        `HDCP Process cost tick` (Stufe 1, einzige Stelle) **ist** der SKE_Send_Eks-Beweis - am G-EU also erbracht. Die HY310-Zeile
        vom 05.10. war zusammengesetzt. Messregel, `docs/subsystems/hdcp.md` und h713-tv-README korrigiert. Rest: Gegenprobe am Gerät
        (`0x4B48BE84` liest `0xA7`), dann schließen
      - **12.10. abends erledigt:** Gegenprobe am HY310 - `0x4B48BE84` = `0x000000A7`, alle fünf Masken `0xA7`, `fmt_set[0]` = 0
        (`arbeit/hy310-main-20261012/skripte/reg-a7.py`, vor und nach der Neuinstallation)
- [x] 2.40 **"TF-A: R_WDOG found armed" nach jedem Aus über crust** ist eine Warnung für den vorgesehenen Rückweg (crust setzt
      über den R_WDOG zurück, BL31 entschärft ihn). Im Kernel (`arisc_tfa_report`) als Info melden, wenn der Record des vorigen
      Laufs Phase `poweroff` hat; sonst bleibt es eine Warnung
      - 11.10. abends: Kernel-Patch `0257` gebaut und am G-EU installiert (`versuch/kernel-abend`); noch nicht gemessen - braucht ein
        Aus über crust und den Start danach
      - **12.10. gemessen** (`doku/204`): nach Aus über crust beide Zeilen als Info - erledigt
- [x] 2.37 **msp-Neuaufbau nach dem Standby brauchte am G-EU einmal 3 Versuche** (Standby s2, `doku/184`; am HY310 5/5 in
      höchstens 2). Drei ist die Grenze von `h713-mips-restart` - beobachten; gehört zu 5.14
      - **10.10. Cloud-RE B (`doku/187`, aus Listings):** der Stock-Kernel baut den DSP nach dem Standby **nicht** neu auf
        (`snd_alsa_trid` ohne PM-Haken); seine TVFE-Einschaltfolge (`tvtop_tvfe_enable`) hat drei Pausen von 10-15 ms, Takte mit
        festen Raten und am Ende `0x06700000 := 0x003003ff` (TVFE-Top) - bei uns nicht drin. Kandidat für die Fehlversuche, nicht belegt
      - **10.10. zu C1 (B):** der Stock-Kernel schaltet die **TVCAP-Domäne im Standby nie ab** (`tv303_pm_domains`: Eintrag
        `pd_tvcap` ganz Null, im ELF nachgelesen); MIPS-Park schon in `suspend`, ohne Wartezeiten. Versuch, wenn Standby wieder
        dran ist: TVCAP im Systemschlaf an lassen, dann prüfen, ob der INCAP-Stopp vor dem Suspend noch nötig ist
      - 11.10. G-EU (`doku/195` Stufe 8): ein Standby, DSP im **2. Versuch**
      - 12.10. G-EU, 20 Standbys (`arbeit/remote-reihe-20261012/` C): 17 x im 1., 2 x im 2., **1 x im 3. Versuch** - an der Grenze
      - **12.10. behoben** (`arbeit/wurzeln-20261012/`, Kernel `0262`, in `main` 8ac1226): nicht der Insel-Start (Selbsttest 52/52 sofort), sondern
        das eine 50-ms-Lesen von `0x00EE` an einer Blockgrenze des Patch-Downloads (`msp_kick`) brach den Download ab; der DSP beantwortet die nächste
        Anfrage sofort. Jetzt wird bis zur 500-ms-Frist des Aufwachrufs weitergefragt. 30 Standbys, Ton 30 x im 1. Versuch, 5 verspätete Rufe
        abgefangen. Die TVFE-Folge des Herstellers (`re-auftrag/BERICHT.md` §3) ist dokumentiert, nicht übernommen - nicht die Ursache
- [x] 2.60 **CONFIG_UCLAMP_TASK statt chrt** (11.10. abends, `doku/201`): der Kernel-Weg gegen den RT-Takt-Boost ist
      `CONFIG_UCLAMP_TASK` + `kernel.sched_util_clamp_min_rt_default` (dann bleiben die Panfrost-IRQ-Threads FIFO und schedutil
      ignoriert sie trotzdem). Kernelconfig im Patchspiegel, Bau, Messung wie `h713-cpufreq` (m30/m31), dann das chrt im Skript weg
      - 11.10. abends: Kernel mit `CONFIG_UCLAMP_TASK` gebaut, `h713-cpufreq` schreibt `sched_util_clamp_min_rt_default = 0`
        ("was 1024"), am G-EU aktiv. Die Messreihe wie m30/m31 steht aus; nicht in `main` bis 2.63 geklärt ist
      - **12.10. erledigt** (`doku/204`): in `main` (a27f245); gemessen mit Warp an, auch mit bewegtem Bild: 86-87 % bei 480 MHz,
        ~3 Wechsel/s (Zwangsboost 35/s, alte chrt-Lösung 4-6/s), unter Last sofort 100 % bei 1296 MHz, 59,7 fps
- [x] 2.62 **HY310 mit 0255 und dem Warp aus `doku/201` nachmessen** (11.10., Handoff `doku/201` §7; HY310 offline, Marco: nach
      hinten): `anzeige.py`, `ctl trace 30 gpu`, `messe-warp.py`; dazu die Panel-Hz des HY310 (nie gemessen) und 2.49 dort
      - **12.10. abends erledigt** (HY310 auf `main` db558e3, `arbeit/hy310-main-20261012/laeufe/2.62.txt`): Warp an 59,43 Wechsel/s, Quelle
        60,02/s, **Panel 59,42 Hz**, 0 Sprünge; fps 59,5, 0 stale/late/drop; CPU warp 9,8 % (alle 4,6 %) bei 100 % 480 MHz, GPU 432 MHz 76 %;
        GPU 6,2 ms je Bild (1080p, submit bis Fence), draw 1,09 ms CPU. Bypass: 0,57 Sprünge/s (Takt 59,42 zu 60,02, wie `doku/200`)
- [x] 2.63 **HY300PRO-G-EU: nach einem Warmstart stirbt der MIPS beim Anmelden der Routinen - wieder** (11.10. ~23:50, Kernel
      `versuch/kernel-abend`): Linux übernimmt beim Warmstart den laufenden MIPS ("adopting the live shared region"), meldet seine
      Routinen an, der MIPS kopiert dafür seine Routinentabelle unter Sperre 2 neu und stirbt dabei (wie `doku/72`). Sperre 2 bleibt
      `refcnt=1 thread=0xff` stehen, `SpinUnLock(2): no thread_id, skipping`, jedes Öffnen von video0 endet in "the callbacks cannot
      be registered (-16)", h713-tv stirbt dreimal, systemd gibt auf: Lampe an, Wand dunkel, Panel und Quelle in Ordnung (Konsole
      sichtbar). `h713-mips-restart` von Hand holt das Bild in 3,4 s zurück, ein Kaltstart auch. Offen: warum der MIPS beim Resync
      stirbt; ob es seit UCLAMP (2.60, langsamerer Takt beim Boot) häufiger ist - Kontrollversuch Warmstarts alter/neuer Kernel;
      danach entweder die Ursache oder als Rückfall h713-mips-restart, wenn h713-tv am blockierten Empfänger scheitert
      - **12.10. nachts (Marco): die Ursache als eigener Offline-Auftrag**, getrennt zu übergeben: Auftrag mit Fragen, Quellen
        (IDA-Datenbanken `display.bin`, `mcu_comm_dev.ko`, `doku/72`, `re/notes/`), Journalauszügen und Lieferform liegt lokal in
        `arbeit/mips-sperre-20261012/AUFTRAG.md`. Frage: wie nimmt der MIPS Sperre 2 (`spinLock(2,quick)`), und warum schließen sich
        sein Weg und unser Nachbau (`cpu_comm_hw.c`) beim Warmstart nicht aus. Bis dahin das Sicherheitsnetz (h713-tv-rescue)
      - **12.10. behoben** (`doku/203`): Kernel `0259` - die Sperren wie Firmware und Herstellertreiber (Byte 0 kritisch, Byte 1
        Besitzer), dazu Freigabe von Sperren, die ein früherer ARM-Lauf hinterließ. 12/12 Warmstarts sauber mit dem Serienkernel.
- [x] 2.64 **HY300PRO-G-EU: Standby kam nicht zurück** (11.10. 21:24, Auswahl Standby in der Ausschalt-Einblendung): 15,5 s
      geschlafen, "back from system suspend", sofort danach Reset ins dunkle Gate ("a standby did not finish", crust Phase
      resuming, ohne Ursache). Linux schreibt beim Aufwachen nichts auf die UART, das Journal war flüchtig - keine Spur. Der folgende
      Warmstart blieb dunkel, ohne Sperr-Meldungen (anders als 2.63). Seit 23:3x ist das Journal am G-EU dauerhaft (`h713-logs
      persistent`, zurück: `h713-logs volatile`); nächster Versuch mit `echo N > /sys/module/printk/parameters/console_suspend`
      - **12.10. behoben** (`doku/203`): afbd `0258` - nach einem Standby kein Lesen von `INCAP +0xa0c` (0255), bis der
        HDMI-Empfänger neu gebunden ist; vorher Bus-Hänger, Watchdog nach 16,4 s, 3/3. Danach 15/15 Standbys zurück (Warp an, 60 s,
        fünf hintereinander, `ctl off`), 59,6-59,8 fps. Offen: Wecken per Taste/IR (Marco)
- [x] 2.49 **Bluetooth: Fehler auf der HCI-UART** (Marco 11.10., HY310 mit Kernel 8b663b8 + 0251): im dmesg 18-mal
      `hci0: Frame reassembly failed (-84)`/`(-90)`, dazu `Received unexpected HCI Event 0x00`, `unexpected event 0x04 length: 62 > 10`,
      `unknown link type 35`, `SCO packet for unknown connection handle 278` - alle bei Uptime 1564-1796 s (10.10. ~22:55); der
      H4-Datenstrom auf der UART (1,5 MBd, Flusssteuerung) kommt zerstückelt an. Dazu passt 1.4 (G-EU: 245-Byte-Schreibvorgänge
      unvollständig, RTS/CTS?). Ursache offen; zuerst prüfen, ob es mit Last (Warp, WLAN) zusammenfällt. Dabei aufgefallen: am HY310
      ist zurzeit **keine Fernbedienung gekoppelt** (`h713-remote-pair status`: no remote bonded) - 11.10. neu gekoppelt (der erste
      Versuch kam im Scan nicht vor, der zweite klappte; `doku/193` §3)
      - 11.10. G-EU (`doku/195`): kein HCI-Fehler im dmesg eines Boots mit Kopplung, Tasten, Maus und Mikro-Ton
      - 11.10. abends (Marco): im Betrieb Timeouts, nach dem Boot kommt Bluetooth nicht immer hoch. Verdacht (nicht gemessen):
        8250_dw ohne `UART_CAP_AFE` - RTS/CTS nur in Software. Erst lesen: MCR +0x10 Bit 5, CPR +0xF4, `/proc/tty/driver/serial`
      - **11.10. abends gemessen:** UART1 `MCR.AFCE = 0`, `CPR = 0` - die Flusssteuerung lief in Software. Kernel-Patch `0256`
        (Kompatibel `allwinner,sun50i-h713-uart`, CPR-Wert mit 64-Byte-FIFO und AFCE, `DW_UART_QUIRK_CPR_VALUE`): danach `MCR = 0x2b`,
        `AFCE = 1`. Erster BT-Start nach einem Warmstart beim ersten Versuch (vorher zweimal nach 8 s ohne Antwort, Neustart der
        Unit). Offen: mehr Starts zählen, Last-Test; der Patch liegt auf `versuch/kernel-abend` (`arbeit/kernel-abend-20261011/`)
      - **12.10. abends (HY310, `main` db558e3 mit 0256):** 5 Warmstarts + 6 Standbys, Bluetooth 11/11 beim 1. Versuch, 0 HCI-Fehlerzeilen.
        Offen nur noch der Last-Test (Warp + WLAN + Mikro)
      - **12.10. abends erledigt (Marco):** 0256 in `main` und im HY310-Abbild, 11/11 sauber; der Last-Test steht bei 9.12
- [x] 2.55 **Sonderzeichen im Login-Feld der Konsole nach dem Schlaf** (Marco 11.10., beide Geräte): Verdacht, nicht geprüft - die
      Fernbedienung ist für den Kernel auch eine Tastatur, Pfeile und F4/F5/F6 landen als Escape-Folgen im versteckten getty auf
      tty1 und erscheinen, sobald die Konsole sichtbar wird. Erst nachweisen (Taste drücken, `/dev/vcs1` lesen), dann entscheiden:
      die Fernbedienungs-Geräte vom VT fernhalten oder den getty auf tty1 ändern
      - 11.10. nachts: `sunxi-ir` hängt am Handler `kbd` (`/proc/bus/input/devices`), die Tasten gehen also ans VT; der Weg ins
        Login-Feld selbst ist nicht gemessen (braucht eine gedrückte Taste)
      - **12.10. nachgewiesen** (`arbeit/remote-reihe-20261012/` E): KEY_UP/KEY_LEFT in `sunxi-ir` eingespeist -> `/dev/vcs1` zeigt
        `hy310 login: ^[[A^[[D`. **Marco entschieden: vorerst Weg 2** - das Login auf tty1 neu starten, wenn die Konsole sichtbar wird, aber
        nur wenn dort niemand angemeldet ist (getty noch am Prompt). Nicht an HDMI koppeln: die Fernbedienung soll später den Desktop
        bedienen; die Trennung Fernbedienung/VT (EVIOCGRAB + Power über uinput) gehört zum Desktop
      - **12.10. abends umgesetzt** (h713-tv, in `main`): `console_restore()` liest tty1; steht hinter dem letzten "login:" etwas, bekommt
        der agetty SIGTERM (getty@tty1 startet neu), sonst nichts. Am G-EU gemessen: Tasten eingespeist → `ctl off` → Prompt sauber,
        Journalzeile "getty restarted"; sauberer Prompt → kein Neustart
- [x] 2.67 **Warmstart: die Sperre 2 bleibt wieder liegen, ohne vorherigen Absturz** (12.10., G-EU, `warm14` von 20 mit dem Kernel aus
      `main` 234282c, `arbeit/remote-reihe-20261012/laeufe/warm14-journal.txt`): `SpinUnLock(2): no thread_id`, dann `routine spinlock 2
      not free after AddInRoutine (owner=0 refcnt=1 thread=0xff)`, 22 x "callbacks cannot be registered (-16)"; `h713-tv-rescue` holte das
      Bild nach 4,46 s. Anders als `doku/203` §1: kein abgestürzter Lauf davor, und `0259` fand beim Übernehmen keine ARM-Sperre ("free
      lock carried" fehlt) - die Sperre entstand erst bei `AddInRoutine`. `0259` deckt also nicht alles ab (1 aus 20; doku/203 0 aus 12).
      Ursache offline klären (wie `arbeit/mips-sperre-20261012/`), das Netz bleibt bis dahin
      - **12.10. behoben** (`arbeit/wurzeln-20261012/`, Kernel `0261`, in `main` 8ac1226): die Ursache war **PID 255** - unser Treiber schrieb die
        Prozess-ID als Thread-Wort der Sperre, und 0xff ist die Markierung "frei" (Firmware: unteres Byte, wir: ganzes Wort); h713-tv bekommt
        diese PID in ~1 von 20 Warmstarts. L2T-Spur zeigt es Schritt für Schritt (zweimal reproduziert). Fix: `tgid << 8 | 1`. 50 Warmstarts ohne
        Treffer, Netz (`h713-tv-rescue`) griff nie mehr
- [x] 2.68 **Warp: nach einem Moduswechsel bleibt die alte Ringgröße stehen** (12.10., G-EU, Quelle ThinkPad, Warp an,
      `arbeit/remote-reihe-20261012/` J Befund 3): in 2 von 4 Durchläufen durch 14 Modi meldete der Treiber (`G_FMT`) nach dem Wechsel
      weiter die Größe des vorigen Modus - einmal 1152x720 für 720x576/720x480/640x480, einmal 640x480 für 1280x720, 17 s lang bis zum
      nächsten Wechsel; der Warp importiert dann diese Größe. Ohne Warp nicht gesehen (h713-tv baut seinen Puffer selbst neu). Vermutung,
      nicht geprüft: der Ring-Record der Firmware wird nicht neu veröffentlicht, solange der Warp das Panel hält (vgl. Prüfstand 05.10.
      2.1/`0183`). Widerlegt: im Warp das Format einmal je Sekunde neu lesen hilft nicht (G_FMT selbst ist veraltet; Zweig
      `versuch/warp-reste` `52eff45`). Offen: an der Wand ansehen (unscharf oder verschert?), dann die Ursache im Treiber/Record
      - **12.10. behoben** (`arbeit/wurzeln-20261012/`, Kernel `0260` + h713-warp, in `main` 8ac1226): INCAP folgt dem Record erst mit dem Umbau
        der Capture-Kette, ohne Ereignis; der Treiber beobachtet INCAP (100 ms) und meldet `SOURCE_CHANGE`; der Warp fragt `QUERY_DV_TIMINGS` selbst
        (G_FMT bleibt unter einer laufenden Queue stehen) und baut je Ereignis neu. 0 von 48 Wechseln (vorher 5 von 30)
- [x] 2.69 **Die Firmware legt für manche PC-Modi einen Ring an, der höher ist als das Panel** (12.10., G-EU, `arbeit/remote-reihe-20261012/`
      J Befund 2): 1280x1024 -> Ring 912x728 ("by the rowbyte"), 1360x768 -> einmal 1280x722, einmal 1280x720 (dieselbe Quelle); h713-tv weist
      "larger than the panel 1280x720" ab, die Konsole bleibt. **Marco: nicht beschneiden** - entweder richtig rechnen oder ablehnen
      (wie heute); die Ursache lösen: warum rechnet die
      Firmware eine Höhe über 720 (Seitenverhältnis gehalten, Ausrichtung?), was Stock mit derselben Quelle tut, wo im Treiber
      (`hdmirx`, "the firmware scales") oder in `display.bin` die Ringgröße entsteht
      - **12.10. behoben** (`arbeit/wurzeln-20261012/`, Kernel `0260`, in `main` 8ac1226): die 728 waren **unsere** Formel (Höhe aus dem
        Seitenverhältnis); die Firmware skaliert auf das Panel, begrenzt durch beide Seiten, und schreibt Breite/Höhe nach INCAP `+0x86c/+0x870`
        (Slot-Füllhöhe gemessen: 720 Zeilen; Listing `CalcWinSize`). Der Treiber liest sie jetzt, unplausibel → `-ENOLCK`. 1280x1024 → 900x720,
        1360x768 → 1274x720, 1366x768 → 1280x718; alle 14 Modi mit Bild. **Augen an der Wand (Marco, 12.10. abends): 1280x1024 und 1360x768 komplett**
- [x] 5.18 **Hostname je Board** (Marco 10.10. nachts: der HY300PRO-G-EU meldet sich im Netz als `hy310`). Heute fest im
      Rootfs: `rootfs/overlay/etc/hostname` = `hy310`, `rootfs/overlay/etc/hosts` `127.0.1.1 hy310`, dazu der Rückfall
      `hy310` in `h713-wifi` (DNS-Name im Zugangspunkt-Modus). Jedes Board heißt also `hy310`, zwei Boxen im selben Netz
      kollidieren. Vorschlag: das Abbild wird ohnehin je Board gebaut - ein Feld `HOSTNAME` in `board.env` (sonst der Name
      des Board-Ordners), `build-rootfs.sh` schreibt `/etc/hostname` und `/etc/hosts` daraus, `h713-wifi` nimmt
      `/etc/hostname` ohne festen Rückfall, `boards/check.sh` prüft das Feld (gültiger Hostname). Der Installer setzt nichts
      selbst, nimmt aber bei einer Neuinstallation einen vom Nutzer geänderten Namen mit (gehört zu 1.2b: `/etc/h713` und
      Host-Schlüssel sichern). Namen je Board mit Marco festlegen (Packungsname, z. B. `hy300pro`, statt
      `hy200-qz713df-a1`). Getrennt davon, nicht in diesem Zug: die Partitionsnamen `hy310-boot`/`hy310-rootfs` gelten
      für alle Boards (Layout v4, `root=PARTLABEL=…`) - umbenennen wäre eine Layout-Änderung
      - **11.10. abends (Marco):** Namen `hy310`, `hy300pro` (G-EU), `hy300proplus`, sonst der Board-Ordner; im Panel änderbar
      - **12.10. geschlossen (Marco, Durchsicht 5.x):** umgesetzt in `234282c` (seit 11.10. in `main`, `doku/202` §9): `HOSTNAME_BOARD`
        (variant.env vor board.env, sonst `BOARD_ID`), `install-projekt.sh` schreibt `/etc/hostname` und `/etc/hosts` und weist
        ungültige Namen ab, `h713-wifi` fällt auf `h713` zurück. Am G-EU als `hy300pro` noch nicht gesehen - mit dessen nächstem
        Abbild. Reste: "im Panel änderbar" -> 2.54, "bei Neuinstallation mitnehmen" -> 1.2b
- [x] 5.19 **`boards/check.sh` urteilt über alte Gerätebäume**: es liest `mainline/build/out/<dtb>.dtb` des Checkouts; in
      `repo-neu` liegen die vom 05.10. (vor crust), daher am 10.10. zwei falsche FAILs (hy310, hy200-qz713df-a1 "device tree
      names h713-arisc.bin"); im frisch gebauten Worktree grün. Den DTB nur mit passendem Kernelbaum-Stempel werten, sonst "note"
      - 12.10. nachgestellt: dieselben zwei FAILs. **Entschieden (Marco): kein Hash** - den DTB-Teil aus `check.sh` (Prüfung 9)
        streichen. Ob Gerätebaum und Firmware zusammenpassen, prüft `build-all.sh` Schritt 10 (`check-crust.py`) am frisch gebauten
        Abbild; `check.sh` prüft nur die Quellen (`board.env`, crust-Konfiguration vorhanden)
      - **12.10. erledigt** (d78e089, in `main`): mit den DTBs vom 05.10. grün (vorher 2 FAILs), falsche Konfiguration 1 FAIL
- [x] 5.23 **Unbekannte Android-Firmware -> Issue** (Marco 12.10.): wer ein Gerät mit einer Hersteller-Firmware hat, die der Installer
      nicht kennt, soll ein Issue aufmachen, damit wir das Profil ergänzen können. Ein Satz im README und derselbe Hinweis in der Meldung,
      mit der der Installer eine unbekannte Firmware ablehnt
      - **12.10. erledigt** (39c2c17, in `main`): die vier Texte nennen ein Issue mit der Zeile und die Adresse; README-Absatz unter
        "Boards"; 5 Tests
- [x] 1.4 HY300 Pro G-EU (`boards/hy200-qz713df-a1`): Boot, Bild, HDCP 1.4 mit geteiltem Satz, 2.2 (Marco 06.10.:
      später). Dazu Bluetooth dort: erster Attach nach Kaltstart hängt an `0x1003`, 245-Byte-Schreibvorgänge kommen
      unvollständig an (FB-BTRESET 9.3, RTS/CTS?); `h713-bt-reset` auf dem Board noch nie probiert
      - **09./10.10. nachts (`doku/182`):** Testabbild `geucrust1` mit crust installiert, crust läuft, HDMI/EDID/HDCP-1.4-Schlüssel
        gut; MIPS-Reload war schwarz -> Ursache LCD-Panel braucht Stromzyklus (PF6), Behebung im MIPS-Treiber + PF6 in der
        Pin-Tabelle, 3/3 per Schnell-Deploy. Offen: Patches in die Serie, `geucrust2` mit `--standby` (build-all erlaubt es
        nur bestätigten Boards; PB5 bleibt im Standby an), HDCP-Paar, HDCP 2.2, Ton, Standby am HY300
      - **10.10. nachts (`doku/184`):** `geucrust2` (0246-0248, `--standby`) installiert und gemessen: Reload 3/3, Standby per RTC,
        Taste und Fernbedienung (BLE schläft ein, IR weckt), HDCP-1.4-Paar und nach Standby, HDCP 2.2 mit zwei Neuverhandlungen,
        Ton nach Standby gehört. In `main` (`63fd053`, crust-Spiegel `01bdbfb`). Offen: Watt im Standby (Marco: heute nicht),
        `h713-bt-reset`, 2.33-2.37; ob die Variante `verified` heißt, entscheidet Marco
      - **10.10. früh:** komplettes Abbild aus `main` 4767f6f gebaut (`arbeit/geu-main-20261010/`, `v0.0-geumain1-TEST`,
        reproducible: yes, 273 Patches) und per FEL installiert (Bluetooth-Kopplung mitgesichert, Fernbedienung bleibt gekoppelt);
        bootet, 0 failed, crust läuft, PB5 beim Board-Manager. **Noch nicht** darauf gemessen: Ton (ThinkPad an HDMI), ein Standby
        mit Lüfter aus, ein Reload - als Kurztest beim nächsten Einschalten; dazu Watt im Standby
      - 11.10.: läuft `main` 8f2c992 + Einblendungsfix als Schnell-Deploy; IR, Bluetooth, Einblendungen, Standby per RTC (Bild nach
        6,5 s, DSP im 2. Versuch) gemessen (`doku/195`). Offen bleiben: Watt im Standby, `h713-bt-reset`, ob die Variante `verified`
        heißt (Marco)
      - **11.10. abends (Marco):** der G-EU (`projector05061226`) wird **verified**
      - **12.10. nachts erledigt (Marco):** verified seit 11.10.; die zwei Reste stehen als 2.70 (Watt im Standby) und 2.71
        (`h713-bt-reset` am G-EU) in §2
- [x] 2.38 **Ausschalten mit OSD** (Marco 10.10. abends): ein Druck auf Power (Gerät oder Fernbedienung) blendet auf afbd ein
      "Ausschalten in 15 s" mit "Standby" daneben; ein zweiter Druck schaltet sofort aus, links/rechts + OK wählt, Zurück bricht
      ab, nach 15 s gilt `power.conf` `short`; ein langer Druck (3 s) schaltet ohne OSD aus. Rückfall: stirbt der Dienst, schaltet
      logind aus. Braucht das afbd-OSD (Marcos Plan) und die IR-Belegung 2.35 (dann auch mit der IR-Fernbedienung, Pfeiltasten
      9.9). h713-power bekommt dafür eine Zwischenstufe "Aus angefordert" mit Schnittstelle zum Wählen und Abbrechen
      - 10.10. abends: der OSD-Weg (Texturen im Warp, `osd = on`) entsteht im Paket `arbeit/warp-konsole-20261010/` - Version 1
        nur Lautstärke, Stumm, Fokus; die Bauweise muss dieses Element später ohne Umbau aufnehmen (`doku/189` §5)
      - **11.10.: überholt** - die Einblendungen laufen über `h713-osd` auf Kanal 2 (2.43, `doku/193`), nicht im Warp. Für dieses
        Element fehlen noch: Text (eine Schrift für "Ausschalten in 15 s"), eine Auswahl (links/rechts, OK) in `libh713osd`, und
        die Zwischenstufe in h713-power; die IR-Belegung (2.35) ist da
      - **11.10. abends entschieden (Marco):** Standby **und** Aus werden angeboten, Auswahl links/rechts, OK bestätigt, Zurück
        bricht ab, ein zweiter Druck führt die Auswahl sofort aus, 3 s halten = aus ohne Einblendung; nach 15 s gilt die Vorgabe
        `default = poweroff|standby` in `power.conf` (ersetzt `short`, Vorgabe poweroff). Standby nur, wo er gerade geht (crust
        bereit); ohne Signal sofort wie heute. h713-power kommt auf jedes Abbild. Erst 2-3 Mockups (`osd-mockup`), Text vorerst nicht
      - **12.10. nachts erledigt (Marco):** der 15-s-Countdown mit Auswahl Standby/Aus ist seit 386ad38 auf jedem Abbild (h713-power,
        h713-osd), am G-EU am 11.10. benutzt; ein Text in der Einblendung wäre ein neuer Punkt
- [x] 8.2 **Bilanz 12.10.** für MemPalace *und* Graphify: findet eine neue Sitzung von selbst,
      was sie braucht? Sonst raus, bevor es Gewohnheit wird
      - **12.10. nachts (Marco): beide raus.** Ausgebaut: Hooks aus `~/.claude/settings.json`, MCP `mempalace-light` abgemeldet,
        Graphify-Git-Hooks umbenannt, Skill nach `~/.claude/skills-ausgebaut/`, `.graphifyignore` aus dem Repo; Anweisungen und
        `referenz/` nachgezogen (`arbeitsregeln.md`, `werkzeuge.md`). Die Daten löscht Marco (8.6)
- [x] 8.4 Graphify-Doku-Extraktion nur bei Bedarf (geht an ein LLM) — Stand: nein, Doku bleibt
      bei referenz/ + MemPalace
      - **12.10. nachts gestrichen:** Graphify ist ausgebaut (8.2)
- [x] 8.5 Graphify-Gemeinschaften heißen „Community N" (ohne LLM keine Namen). Bei der Bilanz
      entscheiden, ob `graphify label --backend claude-cli` erlaubt ist (schickt nur Symbolnamen)
      - **12.10. nachts gestrichen:** Graphify ist ausgebaut (8.2)
- [x] 5.11 `h713-install` löscht seine Arbeitskopie (`image-filled.img`, im Abzugsordner oder `--work-copy`) nie; sie enthält die
      geräteeigenen Dateien. Nach bestandenem Rückvergleich löschen, außer `--keep-work-copy` (08.10., `doku/170`)
      - 10.10.: sie entsteht außerdem **für alle lesbar** (`0644`, root, weil `h713-install` unter sudo läuft) - Arbeitskopie und
        Abzug mit `0600` anlegen, ihre Ordner `0700`. Die eigenen Sicherungsskripte schrieben das Archiv mit den privaten
        Host-Schlüsseln und `wifi.env` ebenso mit `0664` (behoben: `chmod 600`, `umask 077` im Installationsskript)
      - **12.10. entschieden (Marco, Durchsicht 5.x):** keine Rechte-Verschärfung ("übertrieben" - das Backup ist seins, er
        entscheidet). Stattdessen: Abzug, Ordner und alles, was `h713-install` anlegt, gehören **dem Nutzer, der sudo aufgerufen hat**
        (`SUDO_USER`), statt root. Die Arbeitskopie (1,2 GB je Installation, der Linux-Teil des Abbilds mit den eingefüllten
        Gerätedateien) wird **nach bestandenem Rückvergleich gelöscht**; scheitert er, bleibt sie liegen; `--work-copy DATEI` behält
        sie (keine neue Option)
      - **12.10. in `main`** (5382cce, 288f2f5, Paket `arbeit/werkzeuge-20261012/`): Übergabe an den sudo-Nutzer - ein Ordner, den
        der Lauf anlegt, ganz; ein leerer oder unser Abzugsordner gibt ab, was der Lauf schrieb; ein fremder Ordner bleibt unberührt
        (Marco: so ok); dazu die entpackten Release-Teile. Gemessen am PC (13 Tests, echter chown als root, `sudo h713-install dump`
        auf eine Test-eMMC). **Offen: das Löschen der Arbeitskopie am Gerät** (braucht einen echten Schreiblauf) - Schritt 7
      - **13.10. erledigt:** in `main`; am HY310 mit `runde5x1` gemessen (A1): Arbeitskopie nach dem Vergleich gelöscht, Abzug gehört dem Nutzer (`doku/209`)
- [x] 5.12 `v4l2-ctl` (Paket `v4l-utils`) ins Rootfs: zum Lesen der HDMI-RX-Steuerungen am Gerät fehlte es (Marco 08.10., klein)
      - **12.10. entschieden (Marco):** das Debian-Paket `v4l-utils` in `packages.txt` (kein eigener Bau); die Ausschlusszeile
        "gstreamer1.0-*, mpv, ffmpeg, v4l-utils" so ändern, dass nur cstengers Video-Laufzeit draußen bleibt
      - **12.10. in `main`** (d88b433), Abnahme prüft `/usr/bin/v4l2-ctl`. **Nicht gebaut** - Größe und `v4l2-ctl` am Gerät mit dem
        Testabbild (Schritt 6/7)
      - **13.10. erledigt:** in `main`; `v4l2-ctl` 1.30.1 liest am HY310 Treiber, Steuerungen und DV-Timing des Empfängers (A3, +4,5 MiB)
- [x] 5.20 **ARISC-Wahl: Anzeige im Installer und Umschalter `h713-arisc`** (Entscheidung 1.1b, Marco 10.10. abends). Eigenes
      Paket `arbeit/arisc-wahl-<datum>/`, **nach** dem G-EU-Abbild `geuaus1` und seinen Kurztests. Ziel: crust bleibt die
      Vorgabe, die Hersteller-Firmware ist ohne Neuinstallation erreichbar, und jeder sieht, welche läuft.
      1. **Kernel (neuer Patch, `sun50i-h713-arisc`):** Moduloption `firmware=<name>` überstimmt `firmware-name[0]` des
         Gerätebaums. Erlaubt nur `h713-arisc.bin` (Hersteller) oder den crust-Namen des eigenen Baums; alles andere wird mit
         Warnung ignoriert. Die Nachlade-Regel `0192` bleibt: läuft (von BL31 gestartet) crust und die Option sagt
         Hersteller, lädt der Treiber die Hersteller-Datei und ersetzt crust - das ist am 10.10. nebenbei belegt worden (der
         Treiber ersetzte ein FEL-crust durch die Datei, `doku/188` §2). Die Startzeile sagt, welche Firmware warum läuft
         ("firmware: vendor (module option)").
      2. **Werkzeug `h713-arisc` (Userspace, wie `h713-power set`):** `h713-arisc status` (welche läuft, Version/Build,
         was das heißt: Standby ja/nein, Aus über crust oder Gate), `h713-arisc set vendor|crust` schreibt/löscht
         `/etc/modprobe.d/h713-arisc.conf` (`options sun50i_h713_arisc firmware=h713-arisc.bin`), sagt "wirkt nach dem
         nächsten Neustart"; braucht root; Tests nach dem Muster `userspace/h713-power/tests`. Weigert sich auf einem Board,
         dessen Abbild keine Hersteller-Datei hat (Abzug ohne `scp`).
      3. **Nichts an U-Boot und Gate:** BL31 startet weiter crust aus dem FIT; mit der Hersteller-Firmware findet TF-A keinen
         crust-Vertrag und fällt von selbst zurück (Standby verweigert, Aus = Gate, TF-A-Ereignis 5) - das ist bereits so
         gebaut (`sunxi_scp_off.c`, `sunxi_standby.c`).
      4. **Installer (`h713-install`, Abschluss):** eine Zeile "ARISC: crust (Board-Konfiguration ..., Standby und Aus 0,3 W)"
         oder "ARISC: Hersteller-Firmware aus deinem Abzug (TV-303 ... ), kein Standby, Aus = Gate", dazu der Hinweis auf
         `h713-arisc set vendor`. Quelle: der Gerätebaum des Abbilds (`firmware-name`) und die extrahierte `arisc_version`.
         Eine Install-Option `--arisc vendor` legt die modprobe-Datei gleich mit an (für Boards, auf denen crust stört).
      5. **Messen am G-EU** (Kopie, FEL oder installiertes Testabbild): `set vendor` + Neustart -> Hersteller-Firmware läuft,
         EDID/HPD und Bild ok, Standby sauber verweigert, `poweroff` -> Gate (~2,4 W); `set crust` + Neustart -> crust, Aus 0,3 W.
      6. **Doku:** `docs/subsystems/arisc.md` (die Wahl, der Umschalter, was ohne crust fehlt), `docs/tools/h713-arisc.md`,
         README/Board-Liste (welches Board welche Firmware als Vorgabe hat), `RELEASES.md`.
      7. **Später (eigenes Paket, nur mit Besitzerbericht und Registerbeweis):** crust ohne Standby für fremde Boards - nur Aus
         und der HDMI-Vertrag, die Pins (PL6, PB5, PL3, Taste) aus `standby_param` des eigenen Stock-Gerätebaums; dann hätten
         auch sie 0,3 W im Aus, ohne dass wir ihr DRAM kennen
      - **12.10. (Marco, Durchsicht 5.x): schlank umsetzen** - Kernel-Option, `h713-arisc status|set vendor|crust` (`status` liest die
        Zustandsdatei aus `0205`, die es schon gibt), die Zeile im Installer, Doku; **ohne** die Install-Option `--arisc vendor` (keine
        neuen Parameter). Geprüft: die Hersteller-Datei ist bei jeder Installation Pflicht (`vendorfiles.py` `REQUIRED_FILES`), die
        Weigerung in 2. trifft also kaum je zu. **Gemessen wird erst, wenn die übrigen besprochenen 5.x-Punkte fertig sind** (Marco)
      - **12.10. nachts gebaut** (`arbeit/kernel-20261012/`, `versuch/kernel`): Kernel `0267` (`firmware=vendor|crust`, `firmware_from=`),
        `h713-arisc status|set` (7 Tests), `h713-mkimage --arisc` + Tabellenschlüssel `arisc`, Schlusszeile von `h713-install`, Doku. Im
        Testabbild `runde5x1`; die Messung hin und zurück kommt zuletzt
      - **13.10. erledigt:** in `main` (Kernel `0267`, `h713-arisc`, Installer-Zeile); am HY310 hin und zurück ohne Neuinstallation gemessen
        (B5): vendor -> kein Standby, Aus ins Gate; crust -> Aus über crust, R_WDOG-Zeile neu (`doku/209`)
