# S4 - Der Stock-Mitschnitt beweist die Formel und zeigt den echten Fehler im Treiber

07.09.2026, 22:45-23:40 · Auslöser: Marcos Hinweis auf die vorhandenen Umschalt-Mitschnitte

## Der Hinweis war richtig

Ich habe aus dem Disassemblat argumentiert, während in
`re/ida/IDA_hy310/elog_after_hdmird.txt` ein **Stock-Mitschnitt eines echten Auflösungswechsels**
liegt. Stock schaltet zwischen seiner eigenen Oberfläche und dem HDMI-Eingang um, und die laufen in
verschiedenen Auflösungen - Stock *muss* dabei skalieren.

## Die Formel aus `S3` ist damit an echten Stock-Zahlen bestätigt

```
wce_proc  in_win_size : [  720,  480]
wce_proc  out_win_size: [ 1920, 1080]
wce_proc  ratio [24576 x 29127]
```

720·65536/1920 = **24576** und 480·65536/1080 = **29127** - exakt `CalcScaleRatio`
(`sub_8B1A56B8`), klein/groß in 16.16. Ein zweiter Eintrag im selben Log zeigt
1920×1080 → 1920×1080 mit `ratio [65536 x 65536]`. Die Herleitung aus `S3` steht damit doppelt:
gegen den gelesenen Registerzustand **und** gegen Stock-Zahlen.

## Der Fehler im Treiber, den der Mitschnitt aufdeckt

Was `UpdateWce` in Stock übergeben bekommt:

```
win_mgr  src_cfg     : [ 0, 0, 7680, 4320][ 0, 0, 7680, 4320]
win_mgr  dst_cfg     : [ 0, 0, 7680, 4320][ 0, 0, 7680, 4320]
win_mgr  capture_cfg : [ 0, 0,  720,  240][ 0, 0,  720,  240]
win_mgr  display_cfg : [ 0, 0, 1920, 1080][ 0, 0, 1920, 1080]
```

**7680×4320 ist keine Auflösung, sondern das „kein Ausschnitt"-Sentinel.** Stock lässt beide
konfigurierbaren Fenster offen und überlässt der Firmware die Abbildung
`capture_cfg → display_cfg` - die Firmware kennt beide, sie hat die eine gemessen und treibt die
andere.

**Wir senden dort 1920×1080.** Das ist kein „offen", sondern ein ausdrücklicher Ausschnitt, der
Quelle und Ziel aneinander nagelt - und genau 1:1 ergibt. Das war Marcos Verdacht, und er trifft zu:
der fest verdrahtete Wert **ist** Teil des Problems.

Behoben in `0108-media-h713-hdmirx-hand-wce-the-full-window-like-stock.patch`.

## Was der Patch bringt - gemessen, nicht behauptet

**Nichts, für sich genommen.** Mit dem Sentinel im Treiber (Modul getauscht, Probe neu gelaufen)
und einer 720p-Quelle: INCAP stellt sich korrekt auf `0x050002D0` = 1280×720 um, der Scaler bleibt
bei `0x05180008 = 0x43010000` und Bit 27 in `0x05180014` gesetzt. Der Rückstand ist unverändert
`UpdateWce`, das nicht läuft.

Der Patch bleibt trotzdem in der Serie: der ersetzte Wert war aus eigenem Recht falsch - eine
Geometrie, die der Treiber nicht zu wählen hat, im Widerspruch zum einzigen Mitschnitt dessen, was
Stock sendet, und er würde jeder späteren Lösung entgegenarbeiten. Die Patch-Begründung sagt das
ausdrücklich.

## Was der Mitschnitt sonst noch zeigt

Der Neubau ist **eine ganze Knotenkette** in *einem* `WCETop::SetWindow`:
`CapWinNode → NRWinNode → DETNWinNode → ProcWinNode → PanelWinNode`, jeder mit eigenem
`CalcWindow` und `WriteReg`. Einzelne PROC-Register von außen zu setzen kann das nicht ersetzen -
das erklärt, warum alle Versuche aus `S2`/`S3` folgenlos blieben.

Dazu Details, die meine Handwerte widerlegen: die Fenster tragen **Versätze**
(`m_in_win : [104, 25, 720, 480]`, nicht `[0, 0, …]`), und der Panel-Scaler ist ein *zweiter*,
separater Scaler, der auf 1:1 bleibt (`windows_manager_util.c: scaler_ratio_v: 0x10000`), während
der PROC-Scaler die Arbeit macht.

## Stand

Formel bestätigt, ein echter Treiberfehler gefunden und behoben, der Neubaupfad vollständig
verstanden. Der Blocker ist unverändert und jetzt sehr scharf umrissen: **`UpdateWce` läuft bei uns
nicht**, und ohne ihn programmiert niemand die Kette um. Serie 81, Gerät sauber auf 1080p mit Bild
und `0 ohne Antwort`.
