# userspace/ — was auf dem Board läuft

| Verzeichnis | Was | Stand |
|---|---|---|
| [`h713-tv/`](h713-tv/README.md) | **Der HDMI-Eingang als Dienst.** C, ein Prozess: zeigt den Capture-Ring auf der KMS-Plane, bei Signalverlust die Konsole; sendet beim Start Preset und Gammakurve; Steuerkanal `h713-tv ctl …` (Regler, Presets, Einpassung, Bild an/aus, roher RPC). Läuft als Template-Unit `h713-tv@video1` (udev, `BindsTo`). | in Betrieb (08.09.2026) |
| [`h713-pq/`](h713-pq/README.md) | **PQ-Rechner.** Python, liest die Stock-PQ-Daten (`pq_picturemode.ini`, `tvpq.db`, …) und rechnet RPC-Argumente und DE2-Gamma-LUTs. Schreibt nichts ans Gerät; `gamma-standard.bin` in `h713-tv/` stammt von hier. | fertig, Werkzeug |
| [`h713-focus/`](h713-focus/README.md) | **Fokusmotor von Hand fahren.** Ein Python-Skript, ohne Abhängigkeiten. `status` / `up` / `down` / `flush` / `unlatch`; liest den Bereichswächter vor und nach jeder Bewegung, harte Obergrenze je Lauf, schreibt `motor_ctrl_no_limit` nie. Ersetzt `legacy/tools/focus`. | fertig (12.09.2026) |
| [`h713-cam/`](h713-cam/README.md) | **Interne Kamera.** Ein Python-Skript, ohne Abhängigkeiten. `probe` / `controls` / `get` / `set` / `grab` (PNG); sucht den Knoten über den Namen statt `/dev/video2` zu raten; schreibt vor dem Bild einmal die Belichtung zurück (die Kamera liefert sonst schwarz). Aus `analyse/beamer-cam/`. | fertig (12.09.2026), am Gerät ungeprüft |

Bauen und Einspielen: `doku/50-befehle.md`, Abschnitt Betrieb. Die alten Stock-Nachbauten `hy310-hdmird` und
`hy310-pqd` (C++-Daemons mit eigener RPC-Schicht) liegen nur noch als Referenz in `legacy/`; ihr Wissen steckt in
den Kernel-Treibern (`doku/77` §3).
