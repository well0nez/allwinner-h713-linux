# C2 - Der RPC-Verlust ist im Ruhezustand nicht messbar

07.09.2026, 13:40 · Board-Sitzung · Paket C, Vorarbeit zum neuen Plan

## Was gemessen wurde

500 aufeinanderfolgende RPCs `THal_Vp_GetSource` über `/sys/kernel/debug/cpu_comm/call`, am
eingeschwungenen System (Kaltstart 13:10 abgeschlossen, `hy310-tv` läuft, Bild steht):

```
500 Rufe im Ruhezustand: 500 ok, 0 Fehler
```

Kein `no RETURN`, kein `ACK timeout` im dmesg. Davor bereits gemessen: 40 Rufe zwischen 20
Anmelde-/Abmeldezyklen der Callback-Routine, ebenfalls fehlerfrei.

`GetSource` ist ein reiner Lesevorgang und hat keine Nebenwirkung - deshalb sind 500 Rufe hier
möglich, ohne das Bild anzufassen.

## Was das heißt

**Der Transportweg verliert im Ruhezustand keine Antworten.** Das ist ein Kriterium, das hätte
scheitern können, und es ist nicht gescheitert.

Damit verengt sich der Suchraum: alle drei bisher beobachteten `-110` lagen im **Hochlauffenster**
oder unmittelbar danach -

| Vorfall | Zeitpunkt |
|---|---|
| Init-Sequenz Schritt 15 `SetPortMap` | mitten in der Bring-up-Sequenz |
| Init-Sequenz Schritt 17 `THal_Vp_DisableBlackScreen` | mitten in der Bring-up-Sequenz |
| `SetSource(HDMI-1)` am Ende der Probe | ~0,2 s nach der EDID/HPD-Stufe |

- und in genau diesem Fenster tut auch der **MIPS** noch seine eigene Arbeit, während ARISC die
EDID/HPD-Folge fährt und der Anzeigetreiber den Descriptor veröffentlicht.

## Was daraus folgt, und was nicht

**Folgt:** eine Messung im Ruhezustand kann das Problem nicht finden, egal wie viele Rufe man
macht. Wer es reproduzieren will, muss es im Hochlauf messen - also über viele Kaltstarts, oder
indem er die Nebenläufigkeit des Hochlaufs künstlich herstellt.

**Folgt nicht:** dass die Nebenläufigkeit die Ursache ist. 500 Rufe schließen eine Rate von etwa
1:500 nach oben aus, mehr nicht; drei Vorfälle in einer Sitzung mit geschätzt einigen hundert
Bring-up-RPCs sind damit vereinbar, ohne dass der Hochlauf etwas Besonderes wäre. Der Unterschied
zwischen „im Hochlauf häufiger" und „im Hochlauf zufällig aufgefallen" ist **nicht** gemessen.

Genau das ist die erste Messung, die der Plan braucht: eine Zählung, die beide Fälle
unterscheiden kann.
