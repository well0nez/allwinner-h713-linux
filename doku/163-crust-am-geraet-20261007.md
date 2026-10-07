# 163 - Crust am HY310: Normalbetrieb und TF-A-Start bestanden, erstes Aufwachen aus dem Standby (07.10.2026)

**Kurz:** Das Crust-Paket aus `doku/162` lief am 07.10. zum ersten Mal am Gerät (HY310, Marco anwesend und einverstanden).
Normalbetrieb (Phase 1) und Start durch TF-A beim Boot (Phase 2) bestanden. Im Standby (Phase 4 Stufe A: Cluster ab/auf,
DRAM läuft) ist die Box **zum ersten Mal überhaupt aus dem Suspend aufgewacht**; zwei Fehler wurden am Gerät gefunden und
behoben. Offen bleibt ein Stillstand kurz nach dem Aufwachen. Nichts geflasht; Rückweg jedes Mal eMMC-Kette mit Blob.
Belege und Uhrzeiten: `arbeit/crust-20261007/BERICHT.md` §15, `belege/phase1-20261007/`, `phase2-20261007/`, `phase4-20261007/`.

## 1 Gemessen

- **Phase 1** (05:12-05:55, Testmodul aus `/root/crust-test`, nichts Installiertes ersetzt): crust startet (Notify, Herzschlag,
  AR100 24,01 MHz), ein laufender crust wird beim Neuladen behalten, EDID/HPD über crust, Bild 1080p60 mit Warp, 30 min
  Dauerlauf ohne Hänger, Quellwechsel 720p/1080p, Rückkehr zum Blob ohne Rest (GP-Wörter wie vorher). Die Display-MIPS schickt
  crust DispMips-Rahmen (`0x16` PullHotPlug), crust bedient sie.
- **Phase 2** (08:49-08:52, FEL-Abbild, RAM-Bootargs): BL31 meldet `PSCI: SCP firmware (crust) started from 0x110000`, U-Boots
  Display-Initialisierung läuft mit crust, Linux übernimmt den laufenden crust (`image kept`), Bild steht.
- **Phase 4 Stufe A** (08:56-09:31, drei Läufe mit 5-s-Weckzeitgeber): `PSCI: system suspend, cpu op req sent` -> 5,05 s ->
  `system counter restored, 5000 ms asleep added` -> `back from system suspend` -> Weckwort `0xc0000000`.

## 2 Gefunden und behoben

- **EDID-Zurücklesen bei offenem Gate** (crust 0029): bei offenem Gate (`0x07091b04` Bits 0..2) liest der DDC-RAM
  `0x07091c00..0x07091eff` als Null - vom AR100 und vom ARM, unter crust **und** unter dem Hersteller-Blob. Der Blob schließt
  das Gate vor dem Lesen (`0x1269c`). Am Gerät bestätigt.
- **Startadressen der Nebenkerne** (crust 0030): nach dem ersten Aufwachen `CPU1..3: failed to come online`. Der Cluster-Ab
  setzt das CPU-Subsystem zurück; TF-A setzt `ALT_RVBAR` nur beim Boot, crust schrieb nur Kern 0. Jetzt gesichert und
  zurückgeschrieben: `CPU1..3 is up` 45 ms nach `back`. Am Gerät bestätigt.

## 3 Ebenfalls gemessen

- Hilfsblock- und R_PRCM-Register unter crust und Blob identisch (außer dem gewollten CPUS-Takt) - crusts ResetEDIDModule ist
  registergleich mit dem Blob.
- Das Little-Endian-Fenster des Blobs überlebt den AR100-Reset (`lewin_en = 1` beim Wechsel Blob -> crust), nicht aber den
  Systemreset ins FEL.
- Physische Adresse im HDMI-VSDB: Blob 0.0.0.0 / 2.0.0.0 / 0.2.0.0 (Port 0/1/2), crust 1.0.0.0 / 2.0.0.0 / 3.0.0.0 - nur für
  CEC von Belang (ungenutzt), Port 0 ist die Buchse.

## 4 Offen

- **Stillstand nach dem Aufwachen** an wanderndem Ort: A1 (nur CPU0) ~16 s nach `back`, A2 ~75 ms, A3 ~90 ms. Spricht gegen
  einen einzelnen Treiber (nicht gemessen). `initcall_debug` druckt in diesem Kernel nichts (kein `CONFIG_PM_DEBUG`).
- Kein Hängernetz: jeder Hänger brauchte Marco (USB ziehen, Sonoff) - TODO 2.25.
- Fehler der Hauptsitzung um 05:57: `h713-fel` ohne FEL-Host am USB (`referenz/irrwege.md`); `sonoff_ctl` fand den Sonoff
  einmal per mDNS nicht (`referenz/werkzeuge.md`).
