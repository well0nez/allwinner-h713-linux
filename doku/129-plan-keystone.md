# 129 - Plan Keystone-Kette (GPU-Pfad, manuell + automatisch) - Stand 22.09.2026 abends

Anlass: Marco (22.09.): Autofokus geparkt; Keystone manuell und automatisch plus alle Geometriefunktionen des
Herstellers vollstaendig reversen, den GPU-Pfad "auf 100 %" bringen (IOMMU/DMA/Takt sauber) und alles samt Tests planen.
Quellen: `umbau/plan/keystone/PLAN.md` (englisch, 10 Stufen, 34 Tests in `tests.csv`, Review `umbau/reviews/KS0.md`),
`umbau/re-apps/AP2i` (Inventar, Review dort). Alles Weitere aus re-apps AP2, AP2b-h, AP3d, AP3n.

## 1 Reverse Engineering: abgeschlossen
- Hersteller-UI hat genau zwei Backends: **SurfaceFlinger transact 1050** (manuelle vier Ecken, Reset, Auto-Keystone,
  "Digital scaling" 0..20 = dieselbe Homographie gleichmaessig eingezogen, Kamera-Varianten) und **einen** tvserver-Aufruf,
  "Installation mode" = RPC 09ffc6eb `THal_Vp_Wce_SetMirrorMode`, ein Wort (Bit 0 H, Bit 1 V) XOR MirrorMode des Panels
  (HY310: 0). Die Firmware haelt ihn in window_manager+48, wendet ihn bei jeder Fensterberechnung neu an (ueberlebt
  Moduswechsel), kippt V in 0x05600010 [3:2] und H in 0x051C00A0 Bit 0. Boot-Saat aus der Panel-ini ueber die MIPS-XML.
- Kein Warp in display.bin; Keystone geht nur ueber die GPU. Auto = Beschleunigungssensor (SC7A20/STK83xx, twi1 @0x18)
  + 3D-Optikmodell, Python-Referenzen mit 87 Tests (AP2c/f/g/h). Kamera-Pfad auf Marcos Geraet unmoeglich (AP2e).
- Nicht reversed und nicht noetig: android.os.PrjScreen (Winkel-Offset), PxScale, Schreiber von zoom_scale. Noetig und auf
  der Wand zu klaeren: Zuordnung physische Ecke <-> Slot je Projektionsmodus (T21).
- Gefahr in unserem Treiber: afbd.c:1092 schreibt AFBD_VIDEO_CTRL als ganzes Wort und wuerde die Spiegelbits [3:2]
  loeschen, sobald ein Modus != 0 aktiv ist - beim Einbau ODER-verknuepfen.

## 2 Die Kette (10 Stufen, 10 Slots, 0 geplante Stromzyklen, Budget 3)
S0 mesa nur Panfrost cross-gebaut (Debian-mesa = 187,6 MiB wegen LLVM; eigener Build 8-12 MiB geschaetzt, keine harte Grenze) ->
S1 GPU-Fundament A: Rendertest, Thermik, Steckdosen-Watt (nur lesen) -> S2 GPU-Fundament B: IOMMU aus (tot, GPU hat
eigene MMU), LIMA raus, OPP-Tabelle 288/432/600/696 MHz + devfreq + Thermik-Trips (heute 864 MHz gegen 700 beim
Hersteller), 10 min Last, 0055-Fall neu geprueft -> S3 importierter Puffer auf dem RGB-Kanal, NV16-Probe, 60 s
Registerwache -> S4 hdmirx dma-buf-Exporter (0136y) + Primary-Plane-Check (0133g), erster GPU-Durchlauf live ->
S5 h713-warp + h713-tv (Identitaet byteexakt, Matrix gegen AP2f, Ecke auf der Wand, 1 h Dauerlauf) -> S6 Write-back-
Selbsttest (optional, Debug-Kernel) -> S7 Screen-Zoom ueber Einzuege + Projektionsmodus ueber den RPC (Plane-Property
"mirror", `ctl mirror`) -> S8 Auto-Keystone: twi1 + Sensorknoten, drei Lagen, h713-keystone (Python), `ctl keystone
auto` -> S9 Doku. Neu ca. 4000-4700 Zeilen plus 1091 verschobene (AP2h-Modelle).

## 3 Entscheidungen
mesa selbst bauen; IOMMU fuer niemanden; Panfrost bleibt Modul; 0053 bleibt, 0036/0049 nach S3 raus; NV16 als zwei
Ebenen (R8 + GR88) mit eigenem Shader; Projektionsmodus per RPC, nicht per Shader (muss auch ohne Warp gehen);
h713-tv bleibt DRM-Master, h713-warp ist reiner Renderer; Auto-Keystone in Python (Suche existiert getestet).

## 4 Marcos Anteil
Fotos mit Testbild (S3/S5/S7, kleine Flaeche reicht). Kein Wattmeter (Marco hat keins; Leistung aus Runtime-PM, devfreq,
Luefter). Erst bei S8, nach dem Coden: etwas zum Kippen (Buch unter den Vorderfuessen), Massband nur wenn die Trapezgroesse
nicht zum Modell passt. Die 15-MiB-Grenze fuer mesa ist gestrichen: Groesse wird protokolliert, nicht gedeckelt.

## 5 Naechster Schritt
S0 (mesa-Build im Container, kein Geraet), parallel h713-gpu-probe (probe.c <= 200 Zeilen) fuer S1. Offene Folgeaufgaben:
Muster-Generator + Foto-Metrik aus dem Scratchpad nach umbau/tools; Hersteller-GPU-Takt per idalib (Schreibtisch);
android.os.PrjScreen nur bei Bedarf.
