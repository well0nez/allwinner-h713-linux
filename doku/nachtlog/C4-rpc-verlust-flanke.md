# C4 - Der RPC-Verlust: was widerlegt ist, was bleibt, und wo die Grenze der ARM-Seite liegt

07.09.2026, 14:45-17:30 · Board-Sitzung · Paket C · Fortsetzung von C3

## Ausgangspunkt

C3 hatte den Verlust reproduziert (Konsole stumm → ~30 % der dichten Rufe ohne RETURN) und die
Slot-Kette geschlossen. Marcos Auftrag: die Messung, ob der Slot zurückkommt, und den Mechanismus
**vollständig** aufbrechen. Das hier ist das Ergebnis - und es endet ehrlich an der Grenze dessen,
was von der ARM-Seite aus messbar ist.

## 1. Kommt der Slot zurück? Nein.

Beide Ringe direkt gelesen (`/dev/mem`, Köpfe bei `share_seq+120`: `+0` rd, `+4` wr, `+8` peak,
`+0xc` sem, `+0x10` cap):

| | ausgehend `getShareSeqW(1,0)` = `0x4E3026B8` | eingehend `getShareSeqR(1,1)` = `0x4E301D30` |
|---|---|---|
| Start | Abstand **4** | Abstand 1 |
| nach 4 Fehlern | Abstand **8** | Abstand 1 |
| nach 5 / 20 / 40 s Ruhe | 8 · 8 · 8 | 1 · 1 · 1 |

Ein Slot je verlorener Antwort, dauerhaft. **Nur der ausgehende Ring.** `unmatched` blieb 0 - die
Antwort kommt auch nicht verspätet. Der ausgehende Ring hat `local_cpu = 1`: er gehört dem MIPS,
`Comm_ReleaseFreeCall` weist ihn ab („cpu mismatch"), und zwar zu Recht. Eine Rückholung von
unserer Seite wurde gebaut, vom Wächter abgewiesen und **wieder entfernt** - ein Index in eine
FIFO zu schieben, die der andere Prozessor auch beschreibt, tauscht ein Leck gegen einen doppelt
vergebenen Slot.

## 2. Wo die Antwort verlorengeht: beim MIPS, nicht bei uns

- Mit dynamischem Debug (nur kmsg, keine Konsole): **6 RETURN-Worte für 8 Rufe.** Die beiden
  gescheiterten haben kein Wort im Msgbox.
- Direkt nach einem Fehlfall: `RX-FIFO-Zähler (0x03003164) = 0`, IRQ-Status frei, IRQ an, unser
  CALL aus dem TX-FIFO abgeholt. **Es liegt nichts im FIFO.**
- Ein dauerhafter **1-ms-Poll-Backstop** neben dem IRQ (Patch, gebaut, gefahren): unverändert
  20 von 101. Ein verpasstes Wort hätte er geholt. Es gibt keines.

→ Der MIPS quittiert (`CALL_ACK`) und schreibt den RETURN nicht.

## 3. Der einzige Hebel: Zeit auf dem Aufrufer **nach** dem Türklopfer

Zwei Messknöpfe (`tx_delay_pre_us` vor dem SENT-Flag, `tx_delay_post_us` nach `SendCommLow`),
je 20-40 dichte Rufe bei stummer Konsole, frischer Pool:

| `post_us` | 0 | 100 | 200 | 500 | 1000 |
|---|---|---|---|---|---|
| Verlust | ~30 % (12/20) | **7/8** | 4/40 | 2/40 | **0/40** |

| `pre_us` | 200 | 1000 |
|---|---|---|
| Verlust | 11/20 | 15/20 |

Der CALL_ACK trifft ~134 µs nach dem Türklopfer ein. Klippe zwischen 100 und 200 µs: schlafen
wir schon in der ACK-Semaphore, wenn er kommt, geht die Antwort verloren; sind wir noch wach,
kommt sie. Genau das haben die drei Konsolenzeilen (~8 ms je) im Sendepfad monatelang geleistet,
und genau das war `CALL_GAP_MS = 500` im Legacy-Daemon.

## 4. Widerlegt - jeder Punkt eine Messung, die hätte gelingen können

| These | Test | Ergebnis |
|---|---|---|
| Barrieren zu schwach (`dmb(ish)` statt `dsb(sy)`) | Sendepfad auf `dsb(sy)` | Schritt 1 scheitert weiter |
| Nachricht braucht Zeit bis sie sichtbar ist | `pre_us` 200/1000 | 11/20, 15/20 |
| Abstand zwischen Rufen zu klein | 120 ms `sleep` zwischen Rufen | 15/20 |
| Kanalschlüssel wechselt | `TX chan=` je Ruf geloggt | immer `0xb8f31600`, auch bei Fehlfällen |
| Unser Schreib in `+105` stört den MIPS | Löschen **entfernt** | `-62`: das Bit ist ein Handshake, der MIPS quittiert dann nicht mehr |
| dasselbe, Löschen **verschoben** hinter den RETURN | gebaut, gefahren | 20/100, unverändert |
| Listenlauf `FindWaitBySessionId` kollidiert | Code gelesen | nur lesend, Linux-Semaphore, `-110` beweist Fund |
| IRQ-Kern schläft (WFI-Latenz) | Spinner **nur** auf CPU 0, Aufrufer auf CPU 3 | 13/14 |
| Aufrufer-Kern | Aufrufer auf CPU 0 / 1 / 3 | 13/18 · 2/7 · 11/20 - kein Muster |
| Flankengetriggerter Msgbox verpasst das Wort | 1-ms-Poll neben dem IRQ | 20/101, FIFO leer |
| Spinner auf allen Kernen (kein WFI) | | 15/21 - **schlechter** |

## 5. Der MIPS schweigt

Pegel 5 gesetzt (`0x4b48bd9c := 5`, `0x4b48be98 := 0`, per Wort-RMW wie in doku/63), Mitleser
läuft, Init-Sequenz per `bind` neu gefahren, 128 Rufe: **Ring-Schreibzeiger `0x4B48C2A8` bewegt sich
nicht** (`0x757 → 0x757`). Am 06.09. schrieb dieselbe Firmware auf derselben Stufe 40 KiB. Warum
sie heute nichts schreibt, ist offen - und es ist derselbe Zustand, in dem sie den RETURN nicht
schreibt.

## 6. Was das heißt

Die ARM-Seite ist ausgeschöpft: nichts, was wir schreiben, lesen, sperren, pollen oder barrieren,
ändert den Verlust. Was ihn ändert, ist ausschließlich, **ob der Aufrufer-Kern in den ~200 µs nach
dem Türklopfer wach ist**. Die Ursache liegt im Anwendungs-Thread des MIPS. Das Warum steht in
`display.bin` - im Weg vom `CALL_ACK` zum `SEND_RETURN` des BG-Threads - und nirgends sonst.

## 7. Zustand der Serie danach

- `0102` ist jetzt **reine Instrumentierung**: `calls_out`/`ohne Antwort`, der ausgehende Ring als
  `freecall … belegt N` im `watch`, die beiden Knöpfe. **Die Konsolenzeilen bleiben, wie sie waren**
- sie sind heute der Settle, der den Hochlauf am Leben hält. Das ist keine Lösung, das ist der
  bekannte Zustand mit Messgerät.
- `0104` (Löschen verschoben) und `0105` (Poll-Backstop) sind **entfernt**: ihre Begründungen sind
  widerlegt, und ein Patch mit falscher Begründung ist schlimmer als keiner.
- `0103` ist in `0102` aufgegangen.

## 8. Die Entscheidung, die jetzt Marco gehört

Zwei Wege, keiner ist Wunschzustand:

**(A) Der Stand wie vor heute Mittag.** Konsolenzeilen als unbeabsichtigter Settle, ~120 ms je
RPC, Probe ~2,6 s länger, funktioniert. Das ist der Stand dieser Serie jetzt.

**(B) Settle als Wert statt als Nebenwirkung.** `post_us = 1000` als Vorgabe: 1 ms je RPC statt
120, 0/40 gemessen, das Legacy-Vorbild tat dasselbe mit 500 ms. Gemessen, nicht erfunden - aber
ein Umgehen einer MIPS-Eigenheit, deren Grund wir nicht kennen.

**(C) Die Ursache im MIPS.** Disassemblat des BG-Threads von `CALL_ACK` bis `SEND_RETURN`
(`display.bin` liegt roh vor, `mips-objdump` braucht keine IDA-Brücke), mit der Frage: welche
Bedingung lässt ihn den RETURN auslassen, und warum hängt sie am Schlaf des ARM-Kerns. Erst danach
gibt es einen Fix, der den Namen verdient.

Mein Vorschlag: (A) jetzt, damit das Gerät läuft; (C) als nächster Arbeitsschritt; (B) nur, wenn
(C) nichts liefert.
