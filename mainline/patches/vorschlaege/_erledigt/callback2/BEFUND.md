# Callback-Anmeldung, zweiter Anlauf — Befund

Unteragent, 07.09.2026, ~11:00–11:30. **Kein Board angefasst** (kein `ssh`, kein `sonoff_ctl`,
kein `scp`, nichts nach `tftp/`, kein `tio`, kein `/dev/ttyACM0`). Kein `git commit`/`push`, kein
`sudo`, **nicht** in `mainline/patches/kernel/` geschrieben, `doku/78-nachtplan-hdmi-switch.md`
nur gelesen, `memory/` nicht angefasst. **Nicht gebaut** — weder `build/build.sh` noch podman noch
ein Übersetzerlauf irgendeiner Art; der Trockenlauf unten ist reines `patch`.

Ergebnis in diesem Verzeichnis:

| Datei | |
|---|---|
| `BEFUND.md` | dies |
| `0100-soc-sunxi-cpu-comm-register-callbacks-off-the-bring-up-path.patch` | Vorschlag, `diff -ruN`, sha256 `8caa490a4df08d6f0565b07dad0a9614ad472bb5143f2ca72cf1b8f92b49fc86` |

**Nummer 0100, nicht 0099:** während dieser Sitzung hat die Hauptsitzung um 11:04/11:10
`0099-media-drm-h713-rearm-capture-after-descriptor.patch` in die Serie aufgenommen. Der Vorschlag
ist gegen **diese** Serie erzeugt und geprüft (`series` sha256
`8ea42217ac424dff7f58d922b28285e892e63cf365626e13b51c2f12a2229543`, 73 Zeilen).

---

## 0. Die Kurzfassung, und sie ist unbequem

Der Auftrag lautete: finde heraus, **warum** die Anmeldung der Routine die Init-Sequenz zum Stehen
bringt. Die ehrliche Antwort ist:

> **Dass sie das tut, ist nicht belegt.** Von den drei Fehlschlägen scheidet Lauf 2 schon aus
> (Hotplug-Rennen, `B3-hpd-rennen.md`). **Lauf 3 scheidet ebenfalls aus** — nicht nur „die
> Zeitpunkt-Erklärung ist widerlegt", sondern: in Lauf 3 lief bis zum abbrechenden Schritt 17
> *Anweisung für Anweisung derselbe Code wie im heute guten Kernel*. Es blieb **ein** Fehlschlag
> übrig, Lauf 1, und für den gibt es genau eine Messung.

Der Verdacht aus dem Auftrag — kaputte Eintragsstruktur oder falscher Ablageort, über den die
Firmware beim Durchlaufen der Liste stolpert — **hält der Prüfung nicht stand** (§3). Er scheitert
schon an einer Stelle vorher: ein falscher oder fehlender Eintrag kann gar keinen `-110` erzeugen,
sondern nur Stille.

Was übrig bleibt, ist ein **Kandidat** und drei **echte, zitierbare Konstruktionsmängel** im
zurückgenommenen Fix, die unabhängig davon weg gehören (§4/§5). Der Vorschlag (§6) behebt die
Mängel und nimmt der Anmeldung den Ort, an dem sie eine Probe kosten kann — er behauptet **nicht**,
eine diagnostizierte Ursache zu beheben.

---

## 1. Was `-110` an einem Init-Schritt wirklich heißt — **belegt**

Das ist die wichtigste Einzelfeststellung, weil sie den Suchraum halbiert, und sie ist aus dem
Quelltext ableitbar statt geraten.

`h713_hdmirx_call()` ruft `cpu_comm_call(..., strict = true)`. Dort gibt es genau **zwei** Stellen,
die eine Zeitüberschreitung melden können:

1. **CALL_ACK fehlt.** `SendComm2CPUEx()` wartet mit
   `cpu_comm_sem_down_timeout((void *)(sem_ptr + 16), SEND_TIMEOUT_JIFFIES)`
   (`cpu_comm_proto.c:570`). `cpu_comm_sem_down_timeout()` ist ein `down_timeout()`
   (`cpu_comm.h:72–77`), und `down_timeout()` liefert bei Fristablauf **`-ETIME` (−62)**, nicht
   `-ETIMEDOUT`. Der Wert wird unverändert durchgereicht (`cpu_comm_map_err()` bildet nur −1, −3,
   −512 ab), die Logzeile wäre `SendComm2CPUEx: ACK timeout` + `SendComm2CPUEx failed (-62)`.
2. **RETURN fehlt.** `cpu_comm_call_ex()` wartet danach auf das Warteobjekt der Sitzung
   (`cpu_comm_rpc.c:654–659`) und übersetzt im `strict`-Zweig **selbst** nach `-ETIMEDOUT`:
   `cpu_comm_rpc.c:764–768`, mit der Zeile
   `cpu_comm: call comp=0x… session=0x…: no RETURN (wait timed out)`.

**Also: `-110` an einem Init-Schritt bedeutet zwingend — der Ruf ging raus, der MIPS hat ihn per
CALL_ACK quittiert, und danach kam die Antwort nicht.** Msgbox-ISR des MIPS lebt, sein
Bearbeitungs-Thread nicht (oder nicht rechtzeitig).

`CALLBACK-regression.md` §3.2 behauptet dasselbe, aber ohne Herleitung und ohne Logzitat. Jetzt ist
es hergeleitet. **Offen bleibt** die Gegenprobe am Mitschnitt: in den dmesg der Läufe 1 und 3 muss
die Zeile `no RETURN (wait timed out)` stehen und **darf** `ACK timeout` nicht stehen. Ich habe
diese dmesg im Repo nicht gefunden (`analyse/hdmi-seq/` endet am 06.09.); wer sie noch hat, sollte
das nachsehen — es ist eine Prüfung, die scheitern kann.

---

## 2. Lauf 3 fällt vollständig aus der Beweisführung — **belegt**

Nicht nur „die Anmeldung wurde nicht erreicht", sondern: **der ausgeführte Code bis Schritt 17 war
derselbe wie im guten Kernel.**

Bäume (nur gelesen):

| Baum | was |
|---|---|
| `mainline/build/linux-6.18.38-e39777bf…` | guter Stand, A–H grün |
| `mainline/build/linux-6.18.38-c78adf61…` (09:51) | Fix v1, Anmeldung am Probe-Anfang → **Lauf 1/2** |
| `mainline/build/linux-6.18.38-aadd1f1b…` (10:24) | Fix v2, Anmeldung am Probe-Ende → **Lauf 3** |
| `mainline/build/linux-6.18.38-80693e8e…` (10:41) | nach `0098` + Hotplug-Fix, probt durch, 60/60 Bilder |

`diff -rq` zwischen `aadd1f1b` und `80693e8e` liefert genau vier abweichende Quelldateien:
`sun50i-h713-hdmirx.c`, `cpu_comm_api.c`, `sun50i-h713-arisc.c`, `h713-cpu-comm.h`. Jede einzeln:

* **`h713-cpu-comm.h`** — nur Kommentar und Signaturen (id → Name). Kein Laufzeitverhalten.
* **`sun50i-h713-arisc.c`** — die einzige Änderung ist `arisc_wait_hpd_idle()`, und deren einziger
  Aufrufer ist `arisc_hdmi_set_portmap()` (`sun50i-h713-arisc.c:1161`, Aufruf `:1220`). Das läuft in
  Stufe 4, **nach** der Init-Sequenz. Kann Schritt 17 nicht erreichen.
* **`sun50i-h713-hdmirx.c`** — v2 hat `h713_hdmirx_register_callbacks()` aus dem Kopf der Probe
  **entfernt** und hinter `video_register_device()` gesetzt. Bis Schritt 17 tut die Probe damit
  *weniger* als in Lauf 1 und **exakt dasselbe** wie der gute Kernel.
* **`cpu_comm_api.c`** — die einzige Änderung auf einem Laufzeitpfad ist der Wegfall der
  Kurzschluss-Prüfung in `cpu_comm_kernel_deliver()` (`if (!msg || !atomic_read(&cpu_comm_kcb_count))`,
  Grundstand `cpu_comm_api.c:263`). Diese Funktion wird ausschließlich aus `command_action()` für
  **eingehende** CALLs aufgerufen (`cpu_comm_proto.c:950`), und `rx_calls` zählt jeden Eintritt
  *vor* jeder Zuordnung. Der Messwert `rx_calls 0` besagt also: die Funktion ist in diesem Boot nie
  gelaufen. Alles Übrige in `cpu_comm_api.c` (Deskriptor-Einbau, Kanal, debugfs-Erweiterung) hängt
  an der nie erreichten Anmeldung bzw. an einem debugfs-Lesezugriff.

**Folge:** Lauf 3 ist ein **eigenständiger, sporadischer** Ausfall der Init-Sequenz, der genauso im
guten Kernel möglich ist. Er gehört nicht in die Beweiskette des Callback-Fixes. Damit steht die
These „die Anmeldung zerlegt die Init-Sequenz" auf **einer** Messung (Lauf 1) — und wir wissen jetzt,
dass dieselbe Fehlersignatur ohne Anmeldung vorkommt.

Das ist wieder derselbe Fehlertyp, den diese Sitzung zweimal teuer bezahlt hat, nur andersherum:
**drei Fehlschläge sahen nach einem Muster aus, waren aber drei verschiedene Ereignisse.**

---

## 3. Der Verdacht aus dem Auftrag: geprüft, hält nicht

### 3.1 „Die Eintragsstruktur stimmt nicht" — **widerlegt, soweit prüfbar**

Der Deskriptor, den `0092` gebaut hat, ist **feldgleich** mit dem, den der funktionierende
Userspace-Weg schickt, und geht durch **dieselbe** Funktion:

* `IOCTL_INSTALL_RT` kopiert 96 Byte aus dem Userspace und ruft `AddInRoutine(buf)`
  (`cpu_comm_dev.c:264–271`), danach `Comm_AddNewChannel()`. Genau diese zwei Schritte macht der
  Fix.
* Das Feldbild (`+0` chan, `+2` target_cpu, `+4` owner, `+8` comp_id, `+12` Name 64 B, `+92` next)
  ist von drei Seiten festgenagelt: von `FindRoutineEx()` (`cpu_comm_rpc.c:348ff`, kopiert +0, +2,
  +4, +8, +12…75, +80), von `SendComm2CPUEx()` (`cpu_comm_proto.c:447`, legt `routine_find_buf+4`
  in jede Nachricht auf `+0x10`) und von der RE-Seite
  (`re/notes/HANDOFF-IPC-SESSION-20260420-H.md:296–306`, `re/notes/WORKLOG.md:265–271`).
* Die einzige Abweichung zum Userspace ist `owner = 0` statt der pid. Sie ist konsistent
  durchgerechnet: der MIPS spiegelt sie nach `+0x10` zurück, `Comm_Add2NewCallFifo()` baut daraus
  `channel_id = (comp_id & 0xF) | (owner << 4) = 1`, und alle drei Feldvergleiche dort
  (`cpu_comm_channel.c:188–197`) gehen mit dem Kanal auf, den der Fix anlegt
  (`Comm_AddNewChannel(pool, 1, 0)`, `cpu_comm_channel.c:76ff`).

### 3.2 „Der Ablageort stimmt nicht" — **widerlegt**

Version bei `ShMem+0x75C0`, Zähler bei `+0x75C4`, 1224 Einträge à 96 Byte ab `+0x75C8`; alle Slots
werden beim Init mit `comp_id = 0` und `next = -1` vorbelegt
(`cpu_comm_mem.c:2407–2419`, „routine table initialized (1224 slots)"). Dieselben Offsets stehen in
der RE-Doku (`re/notes/HANDOFF-IPC-SESSION-20260420-H.md:300–306`) und in `cpu_comm_rpc.c:56–58`.
Der Fix legt nichts an einem anderen Ort ab; er benutzt `AddInRoutine()`.

Weil alle Slots `next = -1` tragen, nimmt `AddInRoutine()` für einen freien Eimer den
Primärzweig (`cpu_comm_rpc.c:158–164`) und kann keine Kette verbiegen. Die beiden ids liegen
zudem in verschiedenen Eimern (`0x3e7fbc46 & 0x3FF = 70`, `0x38d780e2 & 0x3FF = 226`).

### 3.3 Und der Sargnagel: ein kaputter Eintrag könnte gar keinen `-110` erzeugen

Wenn die Firmware den Empfänger nicht findet, bricht **ihr eigenes** `SendComm2CPUEx` mit `-3` ab,
**bevor** irgendetwas auf die Leitung geht (`cpu_comm_proto.c:230–231`). Die Wirkung eines falschen
Eintrags ist **Stille** — exakt der Zustand vor dem Fix, in dem A–H abgenommen wurden. Für einen
`-110` (§1: ACK ja, RETURN nein) braucht es einen *zusätzlichen* Mechanismus. Der Verdacht erklärt
das beobachtete Fehlerbild also selbst dann nicht, wenn er zuträfe.

### 3.4 Die anderen im Auftrag genannten Gegenerklärungen

| Erklärung | Stand |
|---|---|
| **zweiter Eintrag für dieselbe comp_id verwirrt die Firmware** | kann nicht entstehen: `AddInRoutine()` prüft mit `FindRoutineEx()` auf Duplikat und gibt bei Treffer 0 zurück, **ohne** einen zweiten Eintrag anzulegen (`cpu_comm_rpc.c:148–150`). Ein Fremdeintrag (z. B. Rest eines `hdmi_seq.py`) bleibt einfach stehen. |
| **ein Feld erwartet eine physische statt virtuelle Adresse** | im Deskriptor steht keine Adresse. Die einzigen Zeiger im Tabelleneintrag sind `+80` (MIPS-kseg0-Handlerzeiger, vom MIPS geschrieben) und der Name; der Fix schreibt beide nicht bzw. nur den Namen. Belegt in `doku/83-cpu-comm-api.md:240–246`. |
| **die Tabelle hat einen Zähler/Kopf, der mitgezogen werden muss** | hat sie (`version`, `count`), und `AddInRoutine()` zieht beide mit (`cpu_comm_rpc.c:153`, `:164`, `:235`). **Aber:** die Version wird vorn und hinten je einmal erhöht — ein Seqlock-Muster (ungerade = „wird gerade geändert"). Zwei Rückgabepfade in `AddInRoutine()` (`:170–175` „corrupt entry", `:181–186` „chain index > max") verlassen die Funktion **ohne** die zweite Erhöhung und lassen die Version **dauerhaft ungerade**. Ob die Firmware das als „busy" liest, ist **nicht belegt** (die RE-Notizen sagen zur Semantik nichts, `HANDOFF-…-H.md:307` nennt nur „route table version"). Wenn ja, wäre es ein Dauerschaden. Auslösbar ist es nur durch einen Eintrag mit `entry+2 > 1` in der Kette — und die gibt es laut `cpu_comm_proto.c:236–243` („HY310-fix: entry[2] … can be >1, e.g. thread_id=3") tatsächlich. **Vermutung, nicht Befund.** Der Vorschlag umgeht sie nicht, macht sie aber sichtbar (Version steht jetzt in `watch`). |
| **die Firmware liest die Tabelle nur zu bestimmten Zeitpunkten neu** | plausibel (der Kommentar an `FindRoutineEx()`, `cpu_comm_rpc.c:338–340`, sagt, die Stock-Fassung cache die Tabelle und synchronisiere bei Versionswechsel), erklärt aber wieder nur **Stille**, keinen `-110`. Nicht weiterverfolgt. |

---

## 4. Was **die Anmeldung** wirklich anfasst, das sonst niemand anfasst — **belegt**

Genau eine Sache: **SW-Spinlock 2.**

* `AddInRoutine()` nimmt `comm_SpinLock(2)` (`cpu_comm_rpc.c:152`), `RemoveRoutine()` ebenso
  (`:273`), `RemovePidRoutines()` (`:428`) und `RoutineCleanupInCPUReset()` (`:462`).
* **Auf ARM-Seite nahm diesen Lock im Kernel-Probe-Pfad vor dem Fix niemand.** Die einzigen
  ARM-Nutzer sind `IOCTL_INSTALL_RT`/`IOCTL_UNINSTALL_RT` (`cpu_comm_dev.c:264/324`) und
  `cpu_comm_release()` — alles Userspace. Die Abnahmevorschrift schreibt ausdrücklich „KEIN
  prep-Skript, KEIN `hdmi_seq.py`" vor, also lief in den fraglichen Booten kein Userspace-Nutzer.
* **Der MIPS nimmt denselben Lock in seinem eigenen `AddInRoutine` (`display.bin @0x8B11C4C4`)** —
  `re/notes/display.bin-init-chain.md:11` („Lock 2 ist ein shared ARM↔MIPS-Lock für die
  SharedMem-routing-table"), `:116`, `re/notes/MASTER-HANDOFF.md:210`.
* **Der MIPS wartet dort ohne Frist.** `re/notes/display.bin-init-chain.md`, Abschnitt
  „Spinlock-Internals": *„Kein Timeout — MIPS kann hier unendlich warten wenn der Lock nicht frei
  wird."* Dasselbe steht im Kernel-Kommentar `cpu_comm_hw.c:586–592`
  („MIPS hangs in AddInRoutine -> comm_SpinLock(2) … MIPS's enterCritical uses `__hwspin_lock`
  without our 50ms timeout fallback").
* **Eine Kollision genau dieser Art ist schon einmal gemessen worden**, mit Logzeile:
  `cpu_comm: spinLock(2, mode=2): TIMEOUT after 10001 retries (owner=2 thread_id=0x8b8f3160 refcnt=1)`
  (`re/notes/display.bin-init-chain.md:130–136`) — der ARM gab auf, weil ein MIPS-Thread Lock 2
  hielt.
* Es gab Zeiten, in denen dieser Lock in `display.bin` **weggepatcht** werden musste, damit der MIPS
  überhaupt durchlief (`re/notes/display.bin-patches.md:20`, `re/notes/DEAD-ENDS.md:225`).

Das passt zu §1: der MIPS quittiert per ISR und bleibt im Bearbeitungs-Thread stehen. Es ist **die
einzige** neue Berührungsfläche mit dem Zustand des anderen Prozessors, die die Anmeldung mitbringt.

---

## 5. Drei zitierbare Mängel im zurückgenommenen Fix — **belegt als Code-Eigenschaft**

Diese Punkte sind unabhängig davon richtig, ob sie am 07.09. etwas ausgelöst haben.

### 5.1 Ein nicht erlangter Lock ist von einem erlangten nicht zu unterscheiden

`comm_SpinLock()` verwirft den Rückgabewert von `spinLock()`:

```c
void comm_SpinLock(int lock_id)          /* cpu_comm_hw.c:935 */
{
        spinLock(lock_id, 2);            /* :938  — Rückgabe wird weggeworfen */
}
```

`spinLock()` gibt nach 10001 Runden `-EBUSY` zurück (`cpu_comm_hw.c:867–875`). `AddInRoutine()`
merkt davon nichts und ändert die geteilte Tabelle **ungeschützt**, während der MIPS drin ist.

### 5.2 Die Freigabe kann still ausfallen und den Lock dauerhaft belegt lassen

`enterCritical()` schreibt das Besitzerbyte **bedingungslos** (`cpu_comm_hw.c:784–827`, entgegen dem
eigenen Kommentar „Spin until … free / Verify still free"), und `leaveCritical()` schreibt
**bedingungslos** „frei" — ohne den HW-Lock (`cpu_comm_hw.c:832–838`). Beide Prozessoren
überschreiben also gegenseitig ihr Besitzerbyte. `comm_SpinUnLock()` bricht ab, wenn es das
Besitzerbyte gerade „frei" vorfindet:

```c
if (entry[SPINLOCK_OFF_OWNER] == SPINLOCK_FREE) {
        pr_warn("cpu_comm: SpinUnLock(%d): unlocking a free lock, skipping\n", lock_id);   /* :965 */
        leaveCritical(lock_id);
        return;                          /* ref_count und thread_id bleiben stehen */
}
```

Danach ist Lock 2 für die Algorithmik **dauerhaft belegt**: der ARM läuft in `-EBUSY` (und ignoriert
das, siehe 5.1), der MIPS wartet ohne Frist. Das ist eine **Vermutung als Mechanismus**, aber eine
**belegte Code-Eigenschaft** — und sie ist am Gerät sichtbar, siehe §7.

### 5.3 Der Fix hielt beim Anmelden die Mutex des Empfangspfads

`cpu_comm_register_callback()` in der zurückgenommenen Fassung nahm `cpu_comm_kcb_mutex` und rief
**darunter** `cpu_comm_install_routine()` → `AddInRoutine()` → `comm_SpinLock(2)`. Dieselbe Mutex
nimmt der Empfangspfad (`cpu_comm_kernel_deliver()`), und `command_action()` schickt die Quittung an
den MIPS **erst danach**:

```
cpu_comm_proto.c:942   cpu_comm_userspace_deliver(entry_base);
cpu_comm_proto.c:950   cpu_comm_kernel_deliver(entry_base);      <- nimmt cpu_comm_kcb_mutex
cpu_comm_proto.c:952   if (entry_cmd <= 4) …
cpu_comm_proto.c:1038  SendAckLow(share_seq_w, …);               <- Quittung an den MIPS
```

Der Header sagt das inzwischen selbst über Handler („it delays the acknowledgement the MIPS is
waiting for", `h713-cpu-comm.h`, `cpu_comm_cb_t`) — es gilt für **jeden** Halter dieser Mutex.
Ein Anmelder, der bis zu 10 s in `spinLock()` verbringt, blockiert damit die Quittung und über sie
den MIPS-Thread, der den Callback geschickt hat. Dasselbe gilt für das debugfs-`watch`-Lesen der
alten Fassung, das `FindRoutineEx()` — einen unbegrenzten Kettenlauf (`cpu_comm_rpc.c:397–400`,
keine Zyklusabsicherung) — unter der Mutex machte.

---

## 6. Der Vorschlag: `0100`

Er behauptet keine Ursache. Er tut drei Dinge, jedes mit eigenem Grund:

1. **Die Anmeldung verlässt die Probe.** `sun50i-h713-hdmirx` meldet beide Callbacks beim **ersten
   `open()`** von `/dev/video1` an und beim **letzten `close()`** ab (Zähler `cb_users` unter
   eigener `cb_lock`). Begründung, unabhängig von der `-110`-Frage: die Handler erzeugen
   `V4L2_EVENT_SOURCE_CHANGE`, und V4L2-Ereignisse gehen an **abonnierte Dateihandles** — vor dem
   ersten `open()` gibt es niemanden, den sie erreichen könnten. Der Preis eines Fehlschlags sinkt
   von „Kaltstart" auf „`open()` wiederholen". Die Probe ist danach aus Sicht des Coprozessors
   **byte-gleich** mit der, mit der A–H abgenommen wurden: 22 Rufe raus, kein Deskriptor rein.
2. **Kein Shared Memory unter `cpu_comm_kcb_mutex`** (behebt 5.3). Anmelden reserviert einen Slot
   unter der Mutex (comp_id gesetzt, `fn` noch NULL — die Zustellung nimmt `fn` als Gültigkeitsmarke,
   sieht einen reservierten Slot also nicht), lässt die Mutex los, baut den Deskriptor ein und nimmt
   die Mutex nur zum Veröffentlichen wieder. Abmelden und das debugfs-Lesen sind genauso getrennt.
   Die Zustellung nimmt die Mutex nur noch, wenn wirklich etwas registriert ist — der Leerlauf des
   Empfangspfads kostet wieder nur eine Kopie und zwei Atomics wie vor `0092`, die Zähler bleiben
   trotzdem vollständig.
3. **Ein nicht erlangter Lock wird sichtbar** (entschärft 5.1/5.2, ohne `0014` anzufassen): vor dem
   `AddInRoutine()` wird der Zustand von SW-Lock 2 gelesen und bei belegtem Lock mit `-EBUSY`
   abgelehnt; danach wird der Eintrag mit `FindRoutineEx()` zurückgelesen, damit „AddInRoutine gab 0
   zurück" und „der Deskriptor steht in der Tabelle" nicht mehr dieselbe Aussage sind.

Dazu zwei neue Zeilen in `/sys/kernel/debug/cpu_comm/watch`, die **scheitern können**: der
Tabellenkopf (`rtable version N count M`) und der Zustand von Lock 2
(`spinlock2 owner=… refcnt=… thread=0x… frei|BELEGT`).

Und ein Nebeneffekt, der mehr wert ist als der Patch: **Anmelden ist jetzt eine gewöhnliche
Dateioperation.** `echo MipsHalCallback_SignalChange > /sys/kernel/debug/cpu_comm/watch` legt den
Deskriptor an, `echo -MipsHal… >` nimmt ihn zurück — **ohne Treiber, ohne Kaltstart, beliebig oft.**
Damit lässt sich die offene Frage endlich messen statt vermuten (§7).

### Was der Vorschlag kostet — ausdrücklich benannt

* **Ohne offenes `/dev/video1` gibt es keine Callbacks.** `cpu_comm/watch` zeigt dann `handlers 0`.
  Die Abnahmevorschriften in `CALLBACK-luecke.md` §8 und `CALLBACK-regression.md` §7 stimmen so
  nicht mehr; §7 unten ersetzt sie.
* `hy310-tv` und `hdmirx_test` halten den Knoten offen, sind also nicht betroffen.
* `open()` kann jetzt `-EBUSY`/`-ENODEV`/`-EIO` liefern. Werkzeuge, die `open()` als unfehlbar
  behandeln, sehen einen neuen Fehler. Das ist gewollt: er ist wiederholbar.
* `sun50i-h713-hdmirx.c` gehört Paket E. Der Vorschlag fasst es an; die Aufnahme entscheidet die
  Hauptsitzung.

### Trockenlauf — **sauber**

Frischer Tarball aus `build/cache/linux-6.18.38.tar.xz` in ein eigenes Temp-Verzeichnis
(`tar -C $tmp --strip-components=1 -xf …`), dann alle 73 Zeilen aus `patches/kernel/series` mit
`patch -s -d $tmp -p1`, zuletzt der Vorschlag:

```
series: 73 applied, 0 fehlgeschlagen
.orig nach der Serie allein: 17
0100 …: applied cleanly — 0 .rej, 0 neue .orig, kein Fuzz, kein Offset
```

Zwei Kontrollen dazu:

* Der aus der Serie erzeugte Baum ist für die drei betroffenen Dateien **byte-gleich** mit
  `mainline/build/linux-6.18.38-80693e8e…` (vor der Aufnahme von `0099`) bzw. mit dem daraus
  entstehenden Stand — die Vorlage stimmt.
* Der erste Entwurf war gegen die Serie **vor** `0099` erzeugt und wandte sich mit Fuzz an; er wurde
  verworfen und gegen die aktuelle Serie neu erzeugt. Die abgelegte Fassung ist die fuzzfreie.

**Nicht geprüft: der Übersetzer.** Der Auftrag verbietet das Bauen, also ist `0100` **nicht
kompiliert**. Vor der Aufnahme gehört ein `make Image modules` + `make W=1` für
`drivers/soc/sunxi/cpu_comm/` und `.../sun50i-h713-hdmirx/` davor. Was ich statt dessen getan habe:
Deklarationsreihenfolge, Includes (`build_bug.h` für `static_assert`, `stddef.h` für `sizeof_field`),
`CONFIG_DEBUG_FS`-aus-Zweig, Stapelverbrauch (die Momentaufnahme in `watch` liegt jetzt im Heap,
nicht auf dem Stapel) und die Sperrreihenfolge (`cb_lock` ist ein Blatt; `vb2_fop_release()` und
`cb_lock` werden nacheinander, nicht geschachtelt genommen) von Hand durchgesehen.

---

## 7. Wie man das am Gerät falsifiziert

Zwei Messungen. Die erste entscheidet die eigentliche Frage und **kann scheitern**; die zweite ist
die Abnahme des Vorschlags.

### 7.1 Die Anmeldung isoliert prüfen — ohne Treiber, ohne Kaltstart

Das geht erst mit `0100`, weil erst dort `watch` den Deskriptor anlegt, ohne dass eine Probe daran
hängt. **Das ist der Test, der in drei Anläufen gefehlt hat:** bisher wurde immer Anmeldung *und*
Bring-up in einem einzigen Kaltstart gemessen, und ein Ausgang pro Nacht kann nichts entscheiden.

```bash
# Voraussetzung: Kernel mit 0100, E hat durchgeprobt, /dev/video1 NICHT geoeffnet,
# kein hdmi_seq.py.  Board-Sperre halten.

ssh root@192.168.8.141 'cat /sys/kernel/debug/cpu_comm/watch'
#  erwartet:  handlers 0
#             spinlock2 owner=2 refcnt=0 thread=0x000000ff frei
#  Steht hier schon "BELEGT", ist Lock 2 seit dem Boot verklemmt -> das allein
#  ist der Befund, alles Weitere waere sinnlos.  Nachtlog, STOPP.

# --- A) 20 Anmeldungen/Abmeldungen, dazwischen je ein RPC, der antworten MUSS ---
ssh root@192.168.8.141 'for i in $(seq 20); do
    echo MipsHalCallback_SignalChange > /sys/kernel/debug/cpu_comm/watch || echo "REG $i: $?"
    echo "Thal_Vp_SetBacklightLevel 100" > /sys/kernel/debug/cpu_comm/call
    cat /sys/kernel/debug/cpu_comm/call
    echo -MipsHalCallback_SignalChange > /sys/kernel/debug/cpu_comm/watch || echo "UNREG $i: $?"
    echo "Thal_Vp_SetBacklightLevel 100" > /sys/kernel/debug/cpu_comm/call
    cat /sys/kernel/debug/cpu_comm/call
  done; cat /sys/kernel/debug/cpu_comm/watch'
ssh root@192.168.8.141 'dmesg | grep -E "no RETURN|ACK timeout|SpinUnLock\(2\)|spinLock\(2|Routinen-Spinlock"'
```

**Auswertung — und jede Zeile davon kann eintreten:**

* **Alle 40 `call`-Zeilen sagen `ok`, `spinlock2 … frei`, dmesg leer** → *das Anmelden stört die
  RPC-Bearbeitung nicht.* Damit ist die Ursachenthese aus `CALLBACK-luecke.md`/`-regression.md`
  **erledigt**, und Lauf 1 gehört zu demselben sporadischen Ausfall wie Lauf 3 (§2). Der nächste
  Schritt ist dann *nicht* ein weiterer Treiberumbau, sondern die Frage, warum die Init-Sequenz
  gelegentlich einen RETURN verliert.
* **Irgendein `call` liefert `error -110`** und dmesg zeigt `no RETURN (wait timed out)` →
  *das Anmelden stört sie doch,* und zwar reproduzierbar in Minuten statt in Kaltstarts. Dann ist
  §4 der erste Verdächtige und der nächste Schritt die Disassembly des MIPS-Pfads um
  `0x8B11C4C4`/`0x8B125548`.
* **`error -62`** statt `-110` → es fehlt der **ACK**, nicht der RETURN (§1). Das wäre ein
  *anderes* Bild als am 07.09. und gehört ins Nachtlog.
* **`spinlock2 … BELEGT` am Ende, obwohl nichts läuft** → §5.2 ist am Gerät eingetreten. Das ist
  der Volltreffer: ein dauerhaft verklemmter Lock 2 erklärt „ACK ja, RETURN nie" für den Rest des
  Boots und ist ab jetzt sichtbar, statt nur über `/dev/mem` erratbar.
* **`REG i: 16` (`-EBUSY`) in einzelnen Runden** → der MIPS hält Lock 2 zeitweise; genau dafür ist
  die Ablehnung da. Kein Durchfall, aber notieren, wie oft.

**Gegenprobe, die den Test selbst prüft** (sonst prüft er nichts): dieselbe Schleife **ohne** die
beiden `watch`-Zeilen laufen lassen. Kommt dort ebenfalls ein `-110`, misst der Test nicht die
Anmeldung, sondern den sporadischen Ausfall aus §2 — und beantwortet die Frage trotzdem, nämlich
mit „nicht die Anmeldung".

### 7.2 Abnahme des Vorschlags

```bash
# 0. Kaltstart, kein prep-Skript, kein hdmi_seq.py
ss -ulnp | grep -w :69 || { echo "TFTP laeuft nicht -- STOPP"; exit 1; }
sonoff_ctl restart --host 192.168.8.179
for i in $(seq 30); do ssh -o BatchMode=yes -o ConnectTimeout=3 root@192.168.8.141 uptime && break; sleep 4; done
ssh root@192.168.8.141 'cut -d" " -f1 /proc/uptime'

# 1. Die Probe ist unberuehrt geblieben
ssh root@192.168.8.141 'ls -l /dev/video1; dmesg | grep -E "sun50i-h713-hdmirx" | tail -20; \
  cat /sys/kernel/debug/cpu_comm/watch'
#  BESTANDEN, wenn zugleich:
#   * "Init-Sequenz vollstaendig (22 Aufrufe)" und /dev/video1 da,
#   * watch sagt "handlers 0"  <-- DAS ist der Punkt: die Probe hat die
#     Routinentabelle nicht angefasst,
#   * "rx_calls 0", "spinlock2 ... frei".
#  "handlers 2" hier waere ein Widerspruch zum Patch -> Nachtlog, STOPP.

# 2. Erst das Oeffnen meldet an
ssh root@192.168.8.141 'exec 3</dev/video1; cat /sys/kernel/debug/cpu_comm/watch; exec 3<&-; \
  sleep 1; cat /sys/kernel/debug/cpu_comm/watch'
#  erwartet: bei offenem Knoten "handlers 2" und zweimal "rt cpu=0 owner=0",
#            nach dem Schliessen wieder "handlers 0" und zweimal "rt none".
#  "rt none" bei offenem Knoten -> Anmeldung nicht angekommen. STOPP.

# 3. Der Callback kommt an  (elog wie in CALLBACK-luecke.md §8 Schritt 2 scharfstellen)
ssh root@192.168.8.141 'nohup /root/hdmirx_test -d /dev/video1 --events > /root/ev.log 2>&1 & echo $!'
ssh root@192.168.8.141 'cat /sys/kernel/debug/cpu_comm/watch > /tmp/w.vor'
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --off';  sleep 6
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --auto'; sleep 6
ssh root@192.168.8.141 'cat /sys/kernel/debug/cpu_comm/watch; echo ---; \
  dmesg | grep -E "RX-CALL.*comp_id=0x(3e7fbc46|38d780e2)" | tail -5; echo ---; \
  grep -E "CallbackOfSignalChange|NotifySignalChange" /root/elog_tail.out | tail -6; echo ---; \
  grep -c SOURCE_CHANGE /root/ev.log'
#  BESTANDEN nur, wenn ALLE fuenf zugleich:
#   1. elog zeigt CallbackOfSignalChange/NotifySignalChange (Firmware hat gefeuert),
#   2. rx_calls um >= 1 gestiegen,
#   3. die Zeile 0x3e7fbc46 um GENAU denselben Betrag, unmatched unveraendert,
#   4. dmesg-Zeile "RX-CALL ... comp_id=0x3e7fbc46" da (zweiter, unabhaengiger Zeuge),
#   5. hdmirx_test hat >= 1 SOURCE_CHANGE gesehen -- der eigentliche Zweck.
```

---

## 8. Was ich **nicht** belegen konnte

* **Dass die Anmeldung Lauf 1 verursacht hat.** Eine Messung, und §2 zeigt, dass dieselbe
  Fehlersignatur ohne Anmeldung auftritt. Die Aussage in `STAND-JETZT.md` („Übrig bleiben Lauf 1 und
  Lauf 3") sollte nach diesem Befund auf **Lauf 1** zusammenschrumpfen.
* **Den Mechanismus in §4/§5.2.** Er ist aus dem Quelltext beider Seiten und aus einer historischen
  Messung plausibel, aber am Gerät nicht gezeigt. §7.1 ist gebaut, um ihn zu widerlegen.
* **Ob die Läufe 1 und 3 `no RETURN` oder `ACK timeout` im dmesg hatten** (§1). Die Mitschnitte
  liegen nicht im Repo; die Unterscheidung ist −110 gegen −62 und hätte die Diagnose halbiert.
* **Die Seqlock-Semantik der Tabellenversion** (§3.4). Reine Vermutung; die RE-Notizen sagen dazu
  nichts.
* **Ob der MIPS zum Senden wirklich die Entsprechung unseres `SendComm2CPUEx` fährt.** Unverändert
  offen aus `CALLBACK-luecke.md` §6 — nicht disassembliert.
* **Dass `0100` übersetzt.** Nicht gebaut, siehe §6.

## 9. Nebenbefunde, gefunden und **nicht** angefasst

* `FindRoutineEx()` (`cpu_comm_rpc.c:348–400`) hat **keine Zyklusabsicherung**: eine Kette, deren
  `next` auf einen früheren Slot zeigt, lässt die Funktion ewig laufen. Auf ARM hängt damit der
  Empfangspfad, auf MIPS (gleiche Vendor-Funktion) die RPC-Bearbeitung. Erzeugen kann eine solche
  Kette weder `AddInRoutine()` noch `RemoveRoutine()` in ihrer heutigen Form; die Schranke fehlt
  trotzdem. `0014`-Gebiet.
* `AddInRoutine()` verlässt zwei Zweige ohne die abschließende Versionserhöhung (§3.4).
  `0014`-Gebiet.
* Der Überlaufzweig von `AddInRoutine()` verkettet den neuen Eintrag nur, wenn `prev_idx >= 0`
  (`cpu_comm_rpc.c:216–218`). Ist der Primärslot belegt-aber-comp_id-0 und `next != -1`, bleibt
  `prev_idx` auf −1 und der Eintrag hängt an keiner Kette — er wäre nie auffindbar. Bei der heutigen
  Vorbelegung (`next = -1` überall) nicht erreichbar. `0014`-Gebiet.
* `RemovePidRoutines()` liest die pid bei `+28` statt `+4` — bereits in `CALLBACK-luecke.md` §9.1
  beschrieben, unverändert offen.
