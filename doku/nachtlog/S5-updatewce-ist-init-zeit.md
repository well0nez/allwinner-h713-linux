# S5 — `UpdateWce` ist Init-Zeit, und der Sentinel allein reicht nicht

07.09.2026, 20:50–21:20 · Auswertung des Stock-Mitschnitts + Gegenprobe am Gerät

## Der Stock-Mitschnitt sagt etwas, das ich zuerst überlesen hatte

`re/ida/IDA_hy310/elog_after_hdmird.txt` deckt **über sechs Minuten Laufzeit** ab. Darin kommt
`UpdateWce` **genau zweimal** vor — und beide Male bei Zeitstempel `[0]`:

```
 786  win_mgr [0]  UpdateWce : ENTER     -> SetWindow -> 720x480 -> 1920x1080, ratio [24576 x 29127]
1440  win_mgr [0]  UpdateWce : ENTER     -> SetWindow -> 1920x1080 -> 1920x1080, ratio [65536 x 65536]
```

Danach nichts mehr, obwohl später `AppTopSetSource` (`[17]`), `THal_Vp_SetSource()` (`[34251]`)
und `NotifySignalChange` (`[34253]`) auftreten. **Stock konfiguriert die Fensterkette bei der
Initialisierung und danach nie wieder** — jedenfalls nicht in diesem Mitschnitt.

Das erklärt rückblickend `M6` (`S2`): dass unsere vollständige Stock-Quellwechselfolge nichts
bewirkt, ist kein Fehler unserer Umsetzung — **auch bei Stock bewirkt ein Quellwechsel keinen
Fensterneubau.**

## Die daraus folgende Gegenprobe — und ihr Ergebnis

Wenn die Konfiguration Init-Zeit ist, dann muss die Quelle **beim Probe** schon anliegen. Genau
diese Kombination war nie getestet: bisher habe ich immer geprobt und *danach* die Quelle
gewechselt.

Ablauf: Zuspieler sauber auf 1280x720 gespiegelt, dann `unbind`/`bind` des hdmirx-Treibers, dann
HDMI-Verbindung neu aufgebaut, damit die Erkennung frisch läuft.

| | Ergebnis |
|---|---|
| Sentinel aus `0108` gesendet? | **ja** — Shared Memory trägt `0x1E00` = 7680 und `0x10E0` = 4320 |
| Quelle erkannt? | **ja** — INCAP `0x050002D0` = 1280x720, `incap: aktiv 1280x720, total 1650x750` |
| Scaler? | **unverändert 1:1** — `0x05180008 = 0x43010000`, Bit 27 in `0x05180014` gesetzt |
| PROC-Fenster? | **unverändert** 1920x1080 in Quelle *und* Ziel |

Also: richtiger Wert, richtige Reihenfolge, erkannte Quelle — und trotzdem kein Neubau.

## Was `0108` damit ist

Der Patch tut nachweislich, was er soll (der Sentinel steht im Shared Memory), und er korrigiert
einen Wert, der aus eigenem Recht falsch war. Er **löst das Problem aber nicht**. Das steht seit
dieser Messung auch so in seiner Begründung.

## Wo der Blocker jetzt steht

Der Fensterneubau läuft in Stock innerhalb der Anwendung: `window_manager.cpp` ruft `UpdateWce`,
das ruft `WCETop::SetWindow`, das die Knotenkette `Cap → NR → DETN → Proc → Panel` durchrechnet
und schreibt. Ausgelöst wird das bei Stock von der Projektor-App während ihres Hochlaufs — und auf
unserer Seite gibt es niemanden, der diese Rolle spielt.

Nebenbefund derselben Messung: `signal-info: noch kein SignalChange in diesem Boot`, obwohl die
Firmware die Quelle sichtbar neu erkannt hat (INCAP wurde umgestellt). Das ist erklärbar — die
Callback-Registrierung hängt seit `0100` am ersten `open()` von `/dev/video1`, und der Player lief
für diesen Versuch nicht. Für die Frage nach dem Neubau ändert es nichts, für die Bewertung
künftiger Messungen aber schon: **ohne laufenden Player kommen keine Firmware-Ereignisse an.**

## Was als Nächstes zu klären ist

Nicht mehr „welches Register", sondern **„wer ruft `UpdateWce`, und ist dieser Weg von außen
erreichbar"**. Konkret zu dekompilieren: `window_manager.cpp:255` (der Aufrufer), und ob eine der
91 bekannten FunIDs oder eine Nachricht an den Window-Manager (`WinMgr_OnMsg8_VideoDec`
0x8B1ABC60, `WinMgr_OnMsg35_HDMI` 0x8B1ABC80, `WindowManager__Refresh` 0x8B1AB9E8) dort hinführt.
`re/notes/DEAD-ENDS.md` §81 hält fest, dass der STM-Takt per Hardware-IRQ kommt — das betrifft
aber die *Progression* der Zustandsmaschine, nicht notwendig den Einstieg in `UpdateWce`.
