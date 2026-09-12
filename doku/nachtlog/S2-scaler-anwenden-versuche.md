# S2 — Den Scaler anwenden: was wirkt, was nicht, und wo es klemmt

07.09.2026, 19:40–20:40 · Board-Sitzung · Fortsetzung von [`S1`](S1-scaler-gefunden.md)

## Die wichtigste Messung: nur AFBD folgt der Quelle

Alle Displayblöcke (`0x05000000`, `0x05140000`, `0x05180000`, `0x051C0000`, `0x05600000`, je 4 KB)
wortweise abgetastet und jedes Register gemeldet, das Panel- oder Quellgeometrie trägt — einmal bei
1080p, einmal bei 720p. **84 Register tragen Geometrie. Der Unterschied sind genau vier:**

```
0x05600020  1087x1919 -> 719x1279     VIDEO_SIZE_M1
0x05600040  Stride 1920 -> 1280       VIDEO_Y_STRIDE
0x05600048  1080x1920 -> 720x1280     VIDEO_CROP_Y
0x0560004C   540x1920 -> 360x1280     VIDEO_CROP_C
```

Alle vier sind AFBD — **unser eigener Treiber**, der dank `0107` korrekt der Quelle folgt. Alles
dahinter (PROC, Composition, Panel) steht unverändert auf 1920×1080. Das ist die ganze Krankheit in
vier Zeilen: wir stellen den Erzeuger um und niemand stellt den Abnehmer um.

## M6 beantwortet: der Quellwechsel weckt die Firmware nicht

Die **vollständige Stock-Quellwechselfolge** abgesetzt —
`Wce_SetWindow(src 1280x720, dst 1920x1080)` → `SetSource(1)` → `SetSource(3)` →
`DisableBlackScreen`. Alle vier Rufe gelingen (0,5–30 ms). **PROC bleibt danach auf 1920×1080.**
Vorher von Hand sauber auf den Ausgangswert gesetzt, damit der Kontrollversuch etwas beweist.

Damit ist M6 mit *nein* beantwortet und die Begründung aus
[`re/notes/DEAD-ENDS.md`](../../re/notes/DEAD-ENDS.md) §81 bestätigt: `UpdateWce` hängt an einer
Zustandsmaschine, die nur per Hardware-IRQ (`Vdd_TriggerInterruptTop`) taktet. Von außen ist der
Fensterneubau nicht auslösbar — über inzwischen sieben Sitzungen.

## Was der PROC-Scaler tut: nichts, er ist umgangen

Gegenprobe bei **1080p** (also im laufenden, korrekten Bild): Zielfenster `0x05140124/128` auf
960×540 gesetzt. **Das Bild blieb vollflächig und korrekt.** Wäre die Skalierstufe im Pfad, hätte es
auf ein Viertel schrumpfen müssen. Passend dazu lesen ihre Gates `0x05140114`/`0x05140134` beide 0.
Der Block selbst ist live — der Chroma-Gain `0x05140508` im selben Block wirkt sofort (Punkt 3).

Gates versuchsweise auf Bit 31 gesetzt: das Bild ändert sich *etwas* (Zahl der Wiederholungen
rechts), wird aber nicht richtig. Ohne die volle Folge aus `ProcWinNode__WriteReg` (Gates löschen,
Fenster schreiben, `0x0514011C` Bit 15, dazu `sub_8B1A5DF0` mit `0x05180040` Bit 31 und
`sub_8B1A604C` mit `0x05140514/518/524/528/148/14C/160/164`) ist das Stückwerk.

## Der Durchbruch, der noch nicht reicht: die DE-Lesegeometrie

Zehn Register des Composition-Blocks geschlossen von Panel- auf Quellgeometrie gesetzt
(`0x05000224/444/544/804/80C/844/858/85C/88C/890`, Werte aus dem 1080p-Abzug mit ersetzter
Geometrie — kein Raten, eine konsistente Substitution):

**Das Bild wurde deutlich richtiger** — Inhalt lesbar, Taskleiste sichtbar, Wandstreuung von
std 50 auf 62. **Die DE-Lesegeometrie ist also der Abnehmer.** Es bleibt ein Umbruch bei 2/3 der
Breite, also trägt genau noch ein Register die Zeilenbreite 1920. Im `0x05000xxx`-Block ist keins
mehr übrig (`0x05000AA8/AAC` stellen sich selbst nach — sie standen schon auf 720/1280 und ließen
sich nicht überschreiben). `0x05180040` (`0xC0000780`, unteres Halbwort 1920) auf 1280 gesetzt:
keine Wirkung.

## Was ich daraus mitnehme — und die Grenze, die ich gezogen habe

Ab hier war es Einzelregister-Raten, und das ist in diesem Projekt nicht erlaubt. Abgebrochen,
alle Register aus der vorher angelegten Sicherung zurückgeschrieben.

**Nebenbefund mit Kosten:** das Herumschreiben hat die Firmware-Zustandsmaschine hängen lassen —
INCAP meldete weiter 1920×1080, aber der Signalsatz kam leer zurück und die RPCs brauchten
plötzlich 537 ms statt weniger als 10. Kein Zurücksetzen der Register half; erst ein Netboot-Neustart
hat das Gerät wieder in Ordnung gebracht (danach sofort wieder Bild, `0 ohne Antwort`).
**Lehre: diese Register lassen sich nicht im laufenden Betrieb durchprobieren.** Die nächste Runde
gehört ins Disassemblat und dann in *einen* vollständigen, begründeten Schreibvorgang — nicht in
weitere devmem-Schüsse.

## Der nächste Schritt, präzise

`ProcWinNode__WriteReg` samt `sub_8B1A5DF0` und `sub_8B1A604C` vollständig dekompilieren und die
**komplette** Registerfolge samt Reihenfolge und Gates ableiten; parallel klären, welches Register
außerhalb von `0x05000xxx` noch die Zeilenbreite 1920 trägt (Kandidaten aus dem Abzug:
`0x05140208`, `0x0514020C`, `0x05140E44`, alle mit 1920 in Breitenposition). Erst wenn die Folge
vollständig hergeleitet ist, ein einziger Treiberpatch — und der Test dann direkt nach einem
Neustart, nicht auf einem gewachsenen Zustand.
