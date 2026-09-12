# S7 — Der Rest des Scaler-Problems: wir zerstören selbst, was die Firmware richtig gerechnet hat

07.09.2026, 23:10–00:20 · Werkzeug: die Firmware-Shell aus [`doku/98`](../98-mips-shell.md) und das
elog auf Stufe 5

## Der Befund in einem Satz

Die Firmware baut die Fensterkette bei einem Auflösungswechsel **vollständig korrekt** — und ein
zweiter Durchlauf, den **unser eigener Wiederanlauf** auslöst, rechnet sie falsch neu und
überschreibt das Ergebnis.

## Wie man das sieht

Das elog auf Stufe 5 (`0x4b48bd9c` Byte 0 := 5, `0x4b48be98` Byte 0 := 0, siehe `doku/63`) zeigt
beide Durchläufe. Quelle 1080p → 720p, Kernel mit `0117`:

**Durchlauf 1** (t = 70107), ausgelöst von der Descriptor-Neuveröffentlichung:

```
kAFDMapTable[8][1][1]
capture_cfg  : [   0, 0, 1280,  720][   0, 0, 1280,  720]
display_cfg  : [   0, 0, 1920, 1080][   0, 0, 1920, 1080]
CapWinNode   in_win [260,25,1280,720]  out_win [0,0,1280,720]
             m_scale_ratio_h/v : 0x10000          <- Aufnahme 1:1, wie es sein soll
             m_psu_rowbyte_y: 80, line_num_y: 720
             Rowbyte/LineBufLevel/LineNumber: Y[0x50, 0x50, 0x2d0]
NRWinNode    m_in_win [0,0,1280,720]  m_out_win [104,25,1280,720]
ProcWinNode  in_win_size [1280,720]   out_win_size [1920,1080]
             ratio [43690 x 43690]                <- 0xAAAA, exakt richtig
             m_out_win [104,25,1920,1080]
PanelWinNode m_out_win [0,0,1920,1080]
CapWinNode   WriteReg : ENTER / EXIT
```

Das ist die komplette, korrekte Abbildung 1280×720 → 1920×1080. Die Firmware kann es, sie tut es,
und sie schreibt es in die Register.

**Durchlauf 2** (t = 70227), 120 Ticks später:

```
SetSignalInfo
SetCaptureCfg  m_src_cfg : [1280x720][1920x1080]
SetDisplayCfg  m_dst_cfg : [1280x720][1920x1080]
UpdateWce      capture_cfg : [ 853x480][1280x720]     <- gestaucht
               display_cfg : [1280x720][1920x1080]
WCETop         capture_cfg : [ 852x480][1280x720]
```

Die Aufnahme wird proportional um 1280/1920 = 2/3 gestaucht: 1280→853, 720→480. Danach stehen in
der Hardware `0x06940928` = …`01E0` (480 statt 720) und `0x06940924` = `0x36` (54 statt 80). Das
Bild an der Wand ist ein schmales, verschmiertes Band — genau das Muster einer Aufnahme, die zwei
Drittel zu klein konfiguriert ist.

## Was Durchlauf 2 auslöst

`SetSignalInfo` → `SetCaptureCfg` → `SetDisplayCfg` ist die Kette, die die Firmware nach einem
**Quellenwechsel** fährt. Und den fahren wir selbst: `0099` lässt den Aufnahmetreiber auf die
Descriptor-Benachrichtigung mit `SetSource` weg und zurück antworten, weil die Veröffentlichung die
Aufnahmefreigabe löscht (MemoryAgent `+8` → `memory_agent_onoff` → `0x06940928` Bit 31, `doku/86` §4).

Dieser Wiederanlauf war richtig, solange der Descriptor nie neu veröffentlicht wurde. Seit `0117`
ist er schädlich: er kommt **nach** einem korrekten Neubau und stößt einen zweiten an, der die
Geometrie verliert.

**Der Scaler war nie das Problem.** Er wird korrekt programmiert. Wir überschreiben das Ergebnis.

## Der Weg heraus

Die Aufnahme muss nach der Veröffentlichung wieder frei werden, **ohne** einen Quellenwechsel. Genau
dafür hat die Firmware ein Kommando, gefunden beim Auszählen der Shell-Tabellen:

```
memory_agent  en   enable memory agent(0-9 / all)
              dis  disable memory agent(0-9 / all)
```

Das schaltet exakt den Baustein, der die Freigabe löscht. Der nächste Schritt ist damit klar
umrissen: den `SetSource`-Wiederanlauf aus dem Descriptor-Pfad nehmen und ihn durch das Freigeben
des MemoryAgent ersetzen — ARM-seitig über einen RPC, falls es einen gibt, sonst über den
Shell-Ring, den wir jetzt bedienen können.

## Eine zurückgenommene Fehldeutung

`0118` („Ziel = Panel im Descriptor") beruhte auf einer falsch gelesenen Logzeile: `SetCaptureCfg`
druckt seine beiden Rechtecke in **umgekehrter** Reihenfolge (`[a2[4..7]][a2[0..3]]`, also
`[Quelle][Anzeige]`), was ich als `[Quelle][Ziel]` gelesen hatte. Der Patch ist zurückgenommen; die
vier Fensterwörter des Descriptors bleiben die Quellgeometrie. Zurückgenommene Patches liegen in
`mainline/patches/zurueckgenommen/`.

## Stand

Serie 87. Gerät sauber auf 1080p mit korrektem Bild. `0117` bleibt — es ist der Patch, der die
Firmware überhaupt erst zum Neubau bringt, und Durchlauf 1 beweist, dass der Neubau stimmt.
