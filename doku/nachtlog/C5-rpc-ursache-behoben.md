# C5 — Der RPC-Verlust: Ursache gefunden, behoben, abgenommen

07.09.2026, 18:30–19:15 · Board-Sitzung · Paket C · Abschluss von C3/C4

## Die Ursache

Der ARM hat dem MIPS den Ruf gestohlen, bevor dessen BG-Thread ihn lesen konnte.

`cpu_comm_proto.c:602`, unmittelbar nach dem Aufwachen aus der CALL_ACK-Semaphore:

```c
} else {
        /* Advance CMD-FIFO Rd on ARM side — MIPS's update via KSEG0 cache
         * never propagates to ARM DDR view. Without this: -EBUSY at 19. */
        fifo_ItemRdNext((u32 *)(share_seq_w + 32));
}
```

`share_seq_w + 32` ist die **NewCall-FIFO des MIPS** (ARM-phys `0x4E3026D8/DC`). Ein Ring mit
**einem** Schreiber (MIPS-ISR, `Comm_Add2NewCallFifo` @`0x8b11d418`) und **einem** Leser
(MIPS-BG-Thread, `Comm_GetCallbyChannel` @`0x8b11d81c`). Der ARM war der **zweite Leser**.

Kam unser `rd++` vor dem des BG-Threads, sah der den Ring leer (`rd == wr`, `0x8b11dae8`), gab NULL
zurück und legte sich wieder schlafen. Der Ruf war quittiert, aber nie bearbeitet:

- kein `Comm_ReleaseFreeCall` → **der Slot blieb dauerhaft belegt** (das Leck aus C4)
- kein Handler → **kein RETURN** (das fehlende Wort aus C3)
- kein elog → **die Stille aus C4 §5**

Kam der BG-Thread zuerst, war unser `rd++` Leerlauf. Der Zeitpunkt unseres `rd++` ist das Aufwachen
aus der ACK-Semaphore — **genau die Größe, die `tx_delay_post_us`, die Konsolenzeilen und der
Legacy-Settle verschoben haben**, und `pre_us` (verschiebt den Türklopfer, nicht das Aufwachen) eben
nicht. Jede Messung aus C3/C4 passt.

Die alte Begründung („KSEG0 cache … Without this: -EBUSY at 19") ist umgedreht: die gestohlenen
Rufe hinderten den MIPS am Abarbeiten, **dadurch** gab er keine FreeCall-Slots zurück und der Pool
lief bei ~19 leer. Die Zeile hat das `-EBUSY` verursacht, gegen das sie stand. In Sitzung F war sie
als wirkungslos protokolliert (`DEAD-ENDS.md:228`) und kam trotzdem in `0014`.

Gefunden im Disassemblat von `display.bin` (Agent, `mainline/patches/vorschlaege/mips-return/BEFUND.md`),
von der Hauptsitzung im Quelltext beider Seiten nachgeprüft.

## Der Fix — Patch `0105`

Die Zeile ersatzlos entfernt. Der ARM rührt den Lesezeiger der MIPS-FIFO nicht mehr an; den Ring
räumt der MIPS, wofür er da ist. An ihre Stelle tritt ein **reiner Lesezähler**: liegt beim
CALL_ACK noch ein Eintrag im Ring, hätte die alte Zeile ihn gestohlen — sichtbar in `watch` als
`newcall N mal beim CALL_ACK noch ungelesen`.

## Abnahme — Kernel `5c6cebaf`, danach `8db27f9f` mit `0106`

**100 dichte Rufe, Konsole stumm:**

| | vor dem Fix (C3) | mit `0105` |
|---|---|---|
| Fehler | 32 / 100 | **0 / 100** |
| `newcall … ungelesen` | — | **96** |
| `freecall belegt` | wuchs bis 21 → tot | **1** (stabil) |
| Median | 0,6 ms (dann `-110`) | 0,46 ms |

Der Zähler ist der falsifizierbare Zeuge: **96 von 100** Rufen hatten den Eintrag beim CALL_ACK noch
im Ring — genau die, die die alte Zeile gestohlen hätte, und genau die frühere Verlustrate. Wäre die
Erklärung falsch, wäre entweder weiter verloren worden (Fix wirkt nicht) oder der Zähler stünde bei 0
(anderer Mechanismus). Beides kam wie vorhergesagt.

**Switcher end-to-end** (`hy310-tv`, drei Zyklen Quelle aus/an): aus std 10,2 / an std 45,3, dreimal
identisch, `0 ohne Antwort`, Pool gesund, `SignalChange` feuert. Bild an der Wand farbig, Logo rot.

## `0106` — die Zyklen zurückgeholt

Der Wettlauf ist an der Wurzel weg, also brauchen die Konsolenzeilen ihn nicht mehr zu verdecken.
Alle Per-Ruf-`pr_info` (IPC-Spur, TX-Zeilen, Türklopfer, Msgbox-Worte, Return-FIFO) auf `pr_debug`.
Nachweis: 22-Rufe-Init-Sequenz ohne eine einzige Ruf-Zeile im Log, Probe 15,78 s statt ~17,5 s,
0 Fehler bei normaler Konsole. Der Treiberpfad ist still; die einzige verbliebene Zeile je Ruf ist
die **debugfs-`call`-Ausgabe**, also das Messwerkzeug, nicht der Betrieb. Dynamisches Debug holt jede
Zeile per Name zurück.

## Was das für den ganzen Tag heißt

Ein einziger Konstruktionsfehler — der ARM las eine FIFO, die ihm nicht gehörte — hat sich als
„sporadischer RPC-Verlust", „Slot-Leck", „fehlendes RETURN", „elog-Stille" und „braucht einen
Settle" gezeigt. Alle fünf sind dieselbe Zeile. Kein Workaround, kein Delay, keine Frist: die Zeile
ist weg, und die Begründung dafür steht im Disassemblat beider Prozessoren.

## Nicht belegt

Der Wettlauf selbst am Gerät (aus beiden Quelltexten + dem `newcall`-Zähler erschlossen, nicht mit
zwei synchronisierten Tracepunkten gemessen). Die Vorhersage des Zählers ist aber so scharf — 96/100
ungelesen bei 0 Verlust —, dass eine andere Erklärung sie nicht trägt.
