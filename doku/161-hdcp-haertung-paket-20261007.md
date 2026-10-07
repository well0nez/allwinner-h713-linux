# 161 - HDCP-Härtung als Paket vorbereitet (TODO 6.1, 6.2, 6.5, 6.9), offline, nicht gemessen (07.10.2026)

**Kurz:** Ein Agent hat die vier Härtungspunkte aus `doku/144` (TEE-2, TEE-3, TEE-5) und das BL32-Gerüst (TODO 6.9)
als Patches gegen die echten Fork-Köpfe gebaut. Fünf unabhängige Prüfer plus Gegenprüfung haben das Paket gelesen, ich
habe es selbst angewendet, gebaut und das Tor laufen lassen. Am Gerät ist **nichts** gemessen; Einbau und Messung gehören
in den Release-Neubau (TODO 1.1a). Lieferung: `arbeit/hdcp-haertung-20261007/` (`BERICHT.md`, `patches/`, `belege/`),
Gerätetest-Plan dort in §8.

## 1 Was das Paket ändert

- **6.9 TF-A ohne BL32-Gerüst:** TSP-Block, AArch32-Übergabe, `optee@48600000`-Reservierung, `H713_SKIP_SECURITY_SETUP`,
  die Schalter in `platform.mk`. `SPD` ungleich `none` bricht den Bau jetzt ab (sonst spränge der Upstream-Fallback auf
  `BL32_BASE = 0x40000000`, BL31 selbst). Der Watchdog aus BL31 bleibt, heißt `H713_BOOT_WATCHDOG`, Registerwerte gleich.
  `H713_VENDOR_SECURITY_SETUP` bleibt (dient der sicheren CE-Bank, also HDCP). Nachweis: im Funktionsvergleich ändert
  6.9 allein nur `bl31_early_platform_setup2`.
- **6.1/6.2 EL3 nimmt keine Adresse mehr:** neue Aufrufe `HDCP14_STAGE` (`0x8200001d`, BL31 nennt die Ablage
  `0x48a00000`, 8 KiB) und `HDCP14_ONCE` (`0x8200001e`, Schlüsselsatz, Nullen oder nichts). Eine Senken-Schreibung pro
  Boot, danach ist der Dienst zu. U-Boot legt beide gespeicherten Kopien ab, EL3 prüft Magic, Namen, Längen und Gleichheit
  selbst (dieselben Fälle wie U-Boot, 18 synthetische Datensätze, 0 Abweichungen) und schiebt die 288 Byte an den Anfang
  der Ablage: der Engine-Task ist Byte für Byte der gemessene aus `doku/148`. `PUSH_FROM` nur noch im Werkbank-Bau.
- **Verschluss:** jeder Ausgang von `h713_hdcp14_install()`, der nichts schreibt, schließt den Dienst sofort;
  `arch_preboot_os()` ist der Rückfall für Rollen ohne `h713_disp init`. Offen bleiben nur Starts ohne beides
  (`bootefi`, `go`, `bootelf` ohne `h713_disp init`).
- **6.5:** der Watchdog um den Push läuft über U-Boots WDT-Treiber (6 s); im Objekt stehen keine Watchdog-Adressen und
  kein `0x48a00000` mehr. Das Fenster `0x48600000..0x48b00000` hat einen Namen und eine Herkunft (`SUNXI_TEE_WINDOW_*`,
  Hersteller-OP-TEE-Ladeadresse und Antwort von op 2, `doku/146` §3) - gemessen ist davon weiterhin nur `0x48a00000`.
- **Tor und Bau:** `check-hdcp-artifacts.sh` verlangt jetzt, dass das geprüfte `bl31.bin` Byte für Byte im U-Boot steckt
  (vorher prüfte es nur das lose `bl31.bin`; ein `build-all --skip-uboot` nach einem Lauf mit altem BL31 hätte grün mit
  altem BL31 im Abbild ergeben), verlangt die neuen Zeilen auf beiden Seiten und lehnt ein Release-BL31 mit `PUSH_FROM`
  ab. `uboot-build.sh` und `build.sh uboot` brechen ab, wenn U-Boot den neuen Dienst braucht und das BL31 ihn nicht hat.

## 2 Selbst geprüft (07.10., 01:40-02:30)

- `git am` aller Serien auf die echten Basen (TF-A `4c1bd8c6a`, U-Boot `4913742a9a1`, Repo `711c737`): Baum-Hashes gleich
  dem Bericht (Endstand TF-A `fe84f831`, U-Boot `18ce819d`, Repo `cf931364`).
- Eigener Bau im Container: BL31 bytegleich bis auf den Bauzeitstempel (3 Byte), U-Boot hy310 + release bis auf
  Zeitstempel gleich, 142 Warnungszeilen wie vorher, keine in `h713_hdcp14.c`. `SPD=opteed` bricht mit der neuen Meldung ab.
- Tor: neu+neu grün; ein U-Boot mit altem eingebettetem BL31 neben einem losen neuen `bl31.bin` rot, mit Namen.
- Ein eigener Fehler dabei: mein erster U-Boot-Nachbau rief `merge_config.sh` ohne Arbeitsverzeichnis im Container auf,
  das Release-Fragment fehlte still (`bootdelay=2`, keine H713-Umgebung) - der Vergleich zeigte 638 000 abweichende Byte.
  Mit `-w` gleich. Wer U-Boot von Hand baut: `podman exec -w <ordner>` oder `uboot-build.sh`.

## 3 Was die Prüfung sonst fand

- **BL31 liegt in ungeschütztem DRAM.** Kein TZASC in unserer Kette, `no-map` hält `/dev/mem` nicht auf
  (`CONFIG_STRICT_DEVMEM` ohne `IO_STRICT_DEVMEM`). Root kann das Verschluss-Flag zurücksetzen; die Sperre ist eine
  Hürde, keine Grenze. Das galt schon vor dem Paket und gilt für jeden BL31-Code. Die Kommentare sagen es jetzt so.
  Der Kommentar „runs from secure DRAM" im Kernel-DT (`sun50i-h713.dtsi`) ist aus demselben Grund falsch.
- **Das Boot-Netz aus BL31 reicht nur bis zu U-Boots Watchdog-Init:** `sunxi_wdt_probe()` stoppt den Watchdog in
  `initr_watchdog`. Danach schützt bis Linux nichts außer den Sekunden um den Push.
- **Linux treibt den Watchdog mit dem falschen Registerlayout** (Kernel-DT `sun6i-a31-wdt`, die Hardware hat das Layout
  mit Schlüssel `0x16aa`, wie U-Boots DT `sun55i-a523-wdt`). Schon am 07.09. gemessen (`doku/72` Z. 1633 ff.), nie
  behoben. `RebootWatchdogSec=16s` schaltet damit nichts scharf. -> TODO 2.25.
- **Messregel HDCP 1.4:** mit dem Paket ist pro Boot nur noch **eine** Senken-Schreibung möglich. Das Paar aus
  `referenz/messregeln.md` (Nullen-Boot -> `Desired`, dann Default-Boot -> `Enabled`) bleibt ein gültiger Beweis, gerade
  weil die Senke den Warmstart übersteht: die Nullen aus Boot 1 sind der definierte Ausgangsstand von Boot 2, und
  dazwischen kann niemand schreiben.

## 4 Nicht gemessen

Kein Boot, kein HDCP-Paar, kein Lauf des Treiber-Watchdogs am Gerät; ob EL3s Lesen und Zurückschreiben der Ablage
(statt nur Spülen) für die Engine gleich ist, ist erwartet, nicht gemessen. Andere Boards und Rollen nicht gebaut.
Integration: TF-A und U-Boot nur zusammen (einzeln fehlt HDCP 1.4), Reihenfolge in `BERICHT.md` §7.
