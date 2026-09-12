# 74 — Ursache des SetSource(HDMI)-Absturzes: `sgp_hal_signal_info` ist NULL

**Stand 07.09.2026, 10:55. Status: Ursache bewiesen (A/B am Gerät), Fix noch nicht eingebaut.**

## Ergebnis in einem Satz

Der MIPS kopiert bei jedem HDMI-Signalwechsel 44 Byte nach `sgp_hal_signal_info` — **ohne
Nullprüfung**. Dieser Zeiger ist bei uns NULL, weil der SMM-Heap beim Firmware-Start noch nicht
angelegt ist und `smmMalloc` 0 liefert. Der Store nach Adresse 0 löst eine MIPS-Exception aus,
deren defekter Handler (doku/73) anschließend den DRAM zerlegt und den SoC mitnimmt.
Gibt man dem Zeiger einen gültigen Puffer, **überlebt `SetSource(HDMI)`**.

## Beweiskette

### 1. Statik (nachgelesen in `re/ida/IDA_hy310/display.bin.bak`)

| Adresse | Instruktion | Bedeutung |
|---|---|---|
| `0x8b10aedc/e0` | `jal 0x8b12365c` / `li a0,0x2c` | `hal_adapter_init` fordert **44 Byte** an (→ `smmMalloc`) |
| `0x8b10af08` | `lui v1,0x8b25` | |
| `0x8b10af20` | `sw v0,0x3628(v1)` | Ergebnis **ungeprüft** nach `sgp_hal_signal_info` = `0x8b253628` |
| `0x8b109fb8` | `lui s1,0x8b25` | SignalChange-Adapter `0x8b109fb0` |
| `0x8b109fc4` | `lw a0,0x3628(s1)` | Ziel = der Zeiger |
| `0x8b109fcc/d0` | `jal 0x8b1bc654` / `li a2,0x2c` | `memcpy(ziel, quelle, 44)` |
| `0x8b109fe0` | `beq v0,zero,…` | Nullprüfung — **erst danach** |
| `0x8b1bc7ac` | `sw s0,0x0(t0)` | die faultende Instruktion im memcpy |

`THal_Vp_Init` (`0x8b109f04`) registriert diesen Adapter am Ende selbst (`j 0x8b14b894`,
Kennung 11). Deshalb half `--no-callbacks` nie: die Kopie passiert MIPS-seitig **vor** dem
Versand an den ARM, unabhängig davon, ob der ARM einen Empfänger registriert hat.

### 2. Messung am Gerät (frischer Boot, nur lesend)

```
sgp_hal_signal_info (phys 0x4b253628) = 0x00000000
SMM-Heap-Kopf      (phys 0x4e32d000) = 0x00000000
SMM-Slot           (phys 0x4e304d00) = 0x00000000
```

Der MIPS liest den Slot bei **jedem** `smmMalloc` (`0x8b123040`) und gibt bei null nach
„ERROR: heap[%d] is not initialized!" 0 zurück. Der Allokator ist also komplett tot, nicht nur
für diesen einen Puffer.

### 3. Passung zum Crash-Record aus Lauf 77

`a0 = 0` (memcpy-Ziel), `t0 = 0` (Store-Basis), `a2 = 1` (44 ≫ 5 = ein 32-Byte-Block),
`t2 = 3` (Rest 12 Byte = 3 Wörter), `s1 = 0x8b250000` (callee-saved, exakt das `lui s1,0x8b25`
des Adapters), `EPC = 0x8b1bc7ac`, `Cause = 0x0080040c` → ExcCode 3 = TLB-Store.
Fünf unabhängige Übereinstimmungen auf genau diese Aufrufstelle.

### 4. A/B am Gerät — eine Variable

Eingriff: `analyse/hdmi-seq/signal_info_buf.py --do` setzt `0x4b253628` auf `0xAE3FF000`
(ungecachter Shmem-Block, 44 Byte, mit `0x5A11B0BB` markiert). Keine Handler-Patches,
keine sonstigen Änderungen. Jeder Lauf mit Kaltstart über die Steckdose.

| Lauf | Quelle | Zeiger | Ergebnis |
|---|---|---|---|
| **80** | HDMI_2 (4) | `0xAE3FF000` | **lebt** — 60 s beobachtet, alle GetSource-RPCs RETURN, Uptime 147 s |
| **81** | HDMI_1 (3) | `0xAE3FF000` | **lebt** — 120 s beobachtet, alle RPCs RETURN, Uptime 181 s |
| **82** | HDMI_2 (4) | NULL (Gegenprobe) | **tot** — kein ssh, Log endet an derselben Stelle wie immer |

In den Läufen 80/81 waren nach dem Lauf **11 von 11 markierten Wörtern überschrieben**:

```
00000000 00001770 00000000 0000000d 00000001 00000000 00000000 00000000 00000001 00000000 8b89df5c
```

`+0x0c = 0x0d = 13` ist genau der `signal_format:13`, den die Firmware in Lauf 17 geloggt hat.
Das ist die Signal-Info-Struktur — sie ging bisher nach Adresse 0.

Und die Firmware läuft jetzt durch die Stelle, an der sie bisher starb:

```
I/app (./app_top_projector.cpp 919) CallbackOfSignalChange
I/app (./app_callback.cpp 66)       NotifySignalChange   ×2
I/app (./app_callback.cpp 84)       NotifyLatencyChange
```

## Warum es bei Stock und im alten arm32-Aufbau funktioniert

Reihenfolge. Im Legacy-Aufbau lud `sunxi-mipsloader` den MIPS **aus Linux**, also nach der
vollständigen Shmem-Initialisierung inklusive `Trid_SMM_Init`. Bei uns startet **U-Boot** die
Firmware, bevor irgendjemand den Heap angelegt hat; der Adoptionspfad unseres arm64-Treibers
legt ihn nie an. `hal_adapter_init` läuft damit gegen einen toten Allokator.

## Der richtige Fix (ARM-/Umgebungsseite, kein MIPS-Patch)

Der SMM-Heap muss im Shmem stehen, **bevor U-Boot den MIPS freigibt**. Die Stelle dafür ist
`mainline/external/u-boot/arch/arm/mach-sunxi/h713_mips.c`: U-Boot flusht dort ohnehin schon den
gesamten Shmem (`flush_cache(H713_MIPS_SHMEM_ADDR, H713_MIPS_SHMEM_SIZE)`, Zeile 3127), die
Sichtbarkeit für den MIPS ist also gegeben. Zu schreiben sind die Felder aus `Trid_SMM_Init`
(Vorlage: `analyse/cpu-comm-arm64/cpu_comm_mem.c`, ausgeführt in `analyse/hdmi-seq/smm_init.py`):

* Kopf `0x4E32D000`: `[0]=[1]=PT_PHY`, `[2]=PAGES`, `+0xB4=DATA_START`, `+0xB8=SIZE`, `+0xBC=HEAP`
* Deskriptor-Slot `0x4E304D00`: `(HEAP, SIZE)` — **zuletzt**, das Wort schaltet den Heap scharf

Eine Nachrüstung aus Linux (`smm_init.py`) reicht **nicht**: `hal_adapter_init` ist dann längst
gelaufen und hat NULL gespeichert. Genau das war der Fehler in Lauf 24.

## Was das zusätzlich erklärt

Ein toter Allokator trifft jede Allokation der Firmware, nicht nur diese. Das ist die
naheliegende Erklärung dafür, dass in der Stub-Bisektion **beide** Funktionen gestubbt werden
mussten (`0x8b10711c` und `0x8b108170`) und dass das Fenster-Handle `*(0x8b4a9da8)` bis heute 0
ist — vermutlich ebenfalls eine fehlgeschlagene Allokation. **Vorhersage, nicht gemessen.**

## Korrekturen an früheren Befunden

* **doku/72, „SMM-Heap als Ursache ausgeschlossen" (Lauf 24) ist ungültig.** Der Heap wurde dort
  aus Linux nachträglich angelegt; der bereits gespeicherte Nullzeiger wird davon nicht gültig.
  Der Ausschluss hat die Reihenfolge nicht berücksichtigt.
* **`BadVAddr = 0x63726173` aus Lauf 76/77 war ein Artefakt meines eigenen Patches.** Die Firmware
  schreibt bei `0x8b15b3b4 sw v0,0x8c(k0)` ihre Record-Kennung nach +0x8c — genau dorthin hatte
  ich den BadVAddr-Store umgelenkt. Der echte BadVAddr ist nicht erfasst; das Ziel war 0.
* Der defekte Exception-Handler (doku/73) bleibt ein echter, unabhängiger Befund — er erklärt,
  **warum der Tod still und total ist**, nicht warum er eintritt.

## Was NICHT gezeigt ist

* Der Rücksprung `ra` des Faults ist nicht erfasst; die Aufrufstelle ist durch Registerpassung
  und das A/B sehr stark belegt, aber nicht direkt bewiesen.
* Der U-Boot-Fix ist **nicht gebaut und nicht getestet** — bisher nur der Ersatz-Zeiger aus Linux.
* Es kommt weiterhin **kein Bild**: Fenster-Handle `*(0x8b4a9da8)` und Flag `0x8b4a9afc` sind nach
  wie vor 0, `GetSource` liefert `count=0`. Der Absturz ist beseitigt, die Anzeige nicht gelöst.
* Ob nach dem Heap-Fix auch der MIPS→ARM-Callback beim ARM ankommt, ist offen.

## Werkzeuge

* `analyse/hdmi-seq/signal_info_buf.py` — Zeiger setzen / Puffer markieren / Schreibzugriffe prüfen
* `analyse/hdmi-seq/smm_init.py` — `Trid_SMM_Init`-Replik (als Vorlage für den U-Boot-Fix)
* Läufe: `analyse/hdmi-seq/{elog,kmsg}-udp-run8{0,1,2}.txt`

**Der Hinweis auf `sgp_hal_signal_info` stammt aus dem Review des geforkten Laufs; die
Firmware-Statik, die Messungen und das A/B hier sind eigenständig nachgeprüft.**

## Nachtrag 07.09.2026, 11:15 — U-Boot-Patch gebaut, Flash vorbereitet

**Patch:** `mainline/external/u-boot/arch/arm/mach-sunxi/h713_mips.c` — Defines
`H713_MIPS_SMM_HEAP_OFF` (0x2ccf0) / `H713_MIPS_SMM_SLOT_OFF` (0x4d00), Helfer `h713_mips_init_smm_heap()`
(Spiegel von `Trid_SMM_Init()`: Kopf 0x4e32d000, 1236 Seiten, `data_start` 0x5000, Größe 0x4d330f, alle
Zeiger physisch, Slot-Wort zuletzt), Aufruf in `h713_mips_prepare_ready_probe()` nach dem Record-Pool
und vor Magic/Flush. Isoliert als `analyse/hdmi-seq/uboot-smm-heap-init.patch` (3 Hunks).

**Lauf 83 (Layout-Kontrolle aus Linux):** `smm_init.py` schreibt exakt die Werte, die der Patch schreibt
(Kopf/Slot bit-identisch zur Soll-Zeile). Board lebt (Zeiger-Fix). Aber `free_list_cur` blieb 0x4e32e000 —
während `SetSource` allokiert die Firmware nichts; die Allokationen laufen beim Firmware-Init. **Der
Heap-Pfad selbst ist damit noch nicht getestet** — das geht nur mit U-Boot, das ihn vor dem Start anlegt.

**Build:** auf dem dokumentierten Weg (Container `h713-build`, `build/uboot-build.sh … hy310_netboot_defconfig`,
doku/50). rc=0; Warnungen nur in bestehendem Code (Zeilen 8679 ff.). Image enthält „SMM heap prepared".
Ein Host-seitiger Versuch mit Umgehungen (`YACC=true`) wurde auf Marcos Einspruch verworfen — zu Recht.

**Ist-Zustand eMMC (nur gelesen):** LBA 16 (SPL) sha256 `3585a720…` und Proper @0x49ac00 (886137 Byte)
sha256 `4bbf4bd0…` sind **byte-identisch** mit dem Build vom 01.09. (`u-boot-sunxi-with-spl.bin.bak-vor-smmheap-20260907`,
Split in `build/flash-netboot-smmheap/alt/`). Rückweg damit zertifiziert.

**Flash-Plan (doku/20 Weg 3, aus dem laufenden Linux):** nur **U-Boot proper** (886137 Byte = 1731 Sektoren,
sha256 `cec9f54f…`) nach `seek=4828160`; **SPL bleibt** — er unterscheidet sich nur im Zeitstempel, und der
Patch liegt ausschließlich in proper. Vorher Sicherung des eMMC-Bereichs nach `/root/uboot-proper.vorher.bin`,
danach Rücklesung mit sha256-Vergleich. Rückweg: `alt/uboot-proper.bin` an dieselbe Stelle; FEL laut doku/20 getestet.

**Nachweis nach dem Flash:** (1) U-Boot-Banner zeigt „SMM heap prepared"; (2) unter Linux auf frischem Boot,
**ohne** jeden Eingriff: Slot 0x4e304d00 ≠ 0, `sgp_hal_signal_info` (0x4b253628) ≠ 0 und im Heap-Datenbereich
(≥ 0x4e332000); (3) `SetSource(4)` ohne `signal_info_buf.py` → muss leben; (4) Fenster-Handle 0x8b4a9da8 prüfen.

## Nachtrag 07.09.2026, 11:15 — Fix geflasht und am Gerät bestätigt (Lauf 84)

**Flash:** nur U-Boot proper (886137 Byte, 1731 Sektoren, sha256 `cec9f54f…`) nach LBA 0x49ac00, Rücklesung
identisch. SPL an LBA 16 unverändert. Sicherung des vorherigen eMMC-Bereichs: `/root/uboot-proper.vorher.bin`
am Board und `build/flash-netboot-smmheap/alt/uboot-proper.bin` (sha256 `4bbf4bd0…`, identisch zum alten eMMC-Stand).

**Lauf 84 — Kaltstart, neues U-Boot, KEIN Eingriff aus Linux:**

| Messgröße | vorher (alle Läufe bis 82) | jetzt |
|---|---|---|
| Slot `0x4e304d00` | 0 | `0x4e32d000` (von U-Boot) |
| `sgp_hal_signal_info` (`0x4b253628`) | **0** | **`0xae332000`** — von der Firmware selbst allokiert |
| `SetSource(4)` | Tod nach ~100 ms | **RETURN, 60 s lebendig, alle GetSource-RPCs RETURN** |

`0xAE332000` ist die kseg1-Sicht von ARM-phys `0x4E332000` = Heap-Basis `0x4e32d000` + `data_start` `0x5000`:
die **erste Allokation der Firmware liegt exakt am Datenanfang des von U-Boot angelegten Heaps**. Damit ist
nicht nur der Nullzeiger weg, sondern der Allokator selbst nachweislich in Betrieb — ohne `signal_info_buf.py`,
ohne `smm_init.py`, ohne Firmware-Patch. Der TFD meldet nach dem Umschalten `Signal_Channel ==> HDMI1`.

**Weiterhin offen:** Fenster-Handle `*(0x8b4a9da8)` = 0, Flag 0 — kein Bild. Das ist die nächste Baustelle, jetzt
auf einem Board, das den Signalwechsel überlebt. `free_list_cur` (`0x4e32d004`) bleibt `0x4e32e000`; der
Allokator arbeitet offenbar über den brk (`+0xB4`), nicht über die Seitenliste — nicht weiter untersucht.

**Hinweis für die Doku-Pflege:** `tftp/h713-kernel-netboot.fit` ist noch die `fit-mipsmem`-Variante (zusätzliche
`no-map`-Reservierung 0x4d961000+0x99f000 aus H12); sie ist neutral, Original liegt als `.bak-vor-reloc-20260906`.

## Nachtrag 07.09.2026, 11:45 — Bereinigung: alle Diagnose-Zustände (Inventar)

Marco: „alle Debug-Flags deaktivieren und nichts vergessen". Vollständige Liste dessen, was während der
Untersuchung eingeführt wurde, und der Zustand nach der Bereinigung:

| Nr | Was | Art | Zustand jetzt |
|---|---|---|---|
| 1 | `tftp/h713-kernel-netboot.fit` = `fit-mipsmem` (Extra-`no-map` 0x4d961000+0x99f000, H12) | Diagnose | **zurückgesetzt** auf `.bak-vor-reloc-20260906` (sha256 `c229c830…`), mipsmem gesichert als `.bak-mipsmem-20260907` |
| 2 | `/root/hy310-cpu-comm-callwq-test.ko` (Landezone `CC_REF_LOCAL_BASE` 0xAE780000, Deref-Bereichsprüfung, `ack_action pr_info`; 37 Zeilen vs Serienstand) | Diagnose | **nicht mehr verwendet**: `prep_clean.sh` lädt das Serienmodul `/lib/modules/6.18.38/.../hy310-cpu-comm.ko` (== Backup == In-Tree-Quelle). Quellen in `analyse/cpu-comm-arm64/` bleiben als Testbuild dokumentiert; Backups `*.vor-landezone`. Lauf 86 prüft den Serienstand. |
| 3 | `prep_after_boot.sh` Schritt 4: **Firmware-RAM-Schreiben** elog-Level 5 (0x4B48BD9C/0x4B48BE98), `printk 8` | Diagnose | **weg** in `prep_clean.sh` (kein RAM-Schreiben; für Logs künftig `h713_disp init … elog=<n>` von U-Boot) |
| 4 | prep Schritte 5/6: `elog_tail`, IRQ-Affinität, `watchdog_thresh`, `softlockup_panic`, `kmsg_udp`, `wdt_ping` | Diagnose | **weg** in `prep_clean.sh`; keine Diagnose-Prozesse |
| 5 | Live-Firmware-Patches (`mips_patch.py`, `mips_stub.py`, `elog_uncached_patch.py`, `signal_info_buf.py`, `smm_init.py`) | Diagnose, nur DRAM | **weg** mit jedem Kaltstart (U-Boot lädt `display.bin` neu); `/root/mips_stub.json` existiert nicht |
| 6 | Bootargs `modprobe.blacklist=hy310_cpu_comm` (U-Boot-Env, per UART gesetzt) | Diagnose (nur nötig für das Testmodul) | **bereinigt 11:30** mit `tools/uart-fixargs.py` (Kaltstart, Strg-C bis `=>`, `setenv bootargs` ohne Blacklist, `saveenv` → „Writing to MMC(1)… OK“ — die Env liegt auf **MMC(1)**, deshalb war sie unter mmc 0 nicht zu finden). Linux-Cmdline danach ohne Blacklist verifiziert; `hy310_cpu_comm` lädt jetzt automatisch (Ready 4/4). |
| 7 | U-Boot Trace-Patches (`h713_mips_apply_trace`, Firmware-Cave 0x4b1002c4) | Projekt-Debug | **nicht aktiv** (0x4b1238d8 = Original `0ec5401a`); nur bei `probe-trace` |
| 8 | U-Boot HDCP-Key-Wait-Patch („key-load wait defeated") | Projektentscheidung (kein Key) | unverändert — **kein** Teil dieser Untersuchung, bewusst nicht angefasst |
| 9 | `display_cfg.xml` / TSE auf eMMC p1 | — | **unberührt** (md5 identisch mit Vendor) |
| 10 | U-Boot proper mit `h713_mips_init_smm_heap()` | **der Fix** | geflasht, Rückweg `build/flash-netboot-smmheap/alt/` |
| 11 | ARISC-Blob, `h713-tvcap.ko`, `hy310-arisc-hdmi.ko` aus `/root` | Bring-up-Rezept (doku/69) | bleiben (nicht Diagnose) |

**Lauf 86 — vollständig sauber (11:26):** Original-FIT, geflashtes U-Boot, `prep_clean.sh` (Serienmodul
`hy310_cpu_comm` aus `/lib/modules`, Ready 4/4, `printk` Standard `7 4 1 7`, keine Diagnose-Prozesse, kein
Firmware-RAM-Schreiben), Phase 2+3 mit Callbacks. `SetSource(4)`: RETURN 239.8 ms, 60 s alle GetSource-RPCs
RETURN, Uptime 111 s, `sgp_hal_signal_info = 0xAE332000`. **Der Fix braucht keinen einzigen Diagnose-Baustein.**

Board-Bereinigung danach: `/root/hy310-cpu-comm-callwq-test.ko` → `/root/attic/`, altes `prep_after_boot.sh` →
`/root/attic/prep_diag.sh`, `prep_clean.sh` ist jetzt das `prep_after_boot.sh`. Bootargs-Bereinigung (Zeile 6 der
Tabelle) mit dem Projektwerkzeug `tools/uart-fixargs.py` (setzt die saubere Zeile ohne Blacklist, `saveenv`).

**UART-Mitschnitt des bereinigten Boots (11:29):** U-Boot meldet vor der Freigabe des MIPS
`H713 MIPS: SMM heap prepared (base 0x4e32d000, 1236 pages, slot 0x4e304d00)` — die Zeile des Patches —
und danach die gewohnte `readiness probe shared memory prepared`. Kernel-Cmdline:
`console=ttyS0,115200 earlycon root=/dev/nfs rw nfsroot=192.168.8.104:/srv/h713-rootfs,vers=3,tcp ip=dhcp rootwait clk_ignore_unused pd_ignore_unused cma=128M`.
Mitschnitt: `re/captures/boot-clkignore.log` (vom Werkzeug geschrieben).

## Endzustand (07.09.2026, 11:35)

* **Ursache:** `sgp_hal_signal_info` NULL, weil der SMM-Heap beim Firmware-Start fehlte (Reihenfolge U-Boot vor Linux).
* **Fix:** `h713_mips_init_smm_heap()` in U-Boot (`h713_mips.c`), nur proper geflasht, Rückweg gesichert.
* **Nachweis:** Läufe 84/85/86 (HDMI_2, HDMI_1, komplett sauber) leben; Gegenprobe 82 stirbt. Firmware allokiert den
  Puffer selbst (0xAE332000 = Heap + data_start).
* **Bereinigt:** FIT original, Serienmodul (lädt automatisch), kein Firmware-RAM-Schreiben, keine Diagnose-Prozesse,
  Bootargs ohne Blacklist, Host-Listener beendet.
* **Offen:** kein Bild (Fenster-Handle 0); MIPS→ARM-Callback-Pfad noch nicht als Ziel geprüft; cstengers Befunde vom
  4./5.9. (60-Hz-Ring-Rewrite-Lock, „Unbound is not quiesced“, DECD-Handover 0x05600098) sind für die Bild-Baustelle relevant.
