# Regel-1-Durchsicht des Kernelpfads 0091-0097

> **Korrektur 07.09., 09:16 - ein Satz dieser Durchsicht ist falsch, und sie widerspricht sich selbst.**
> Die Aussage „alle Wartezeiten außer A2 enden in einem Fehler statt in einem Weiterlaufen" trifft
> nicht zu: **alle sechs** Wartestellen im Display-Treiber liefen weiter. Die eigenen Abschnitte B4
> und B5 beschreiben zwei davon - der Satz in Abschnitt E widerspricht also dem eigenen Text.
> Außerdem waren `0093` und `0095` gar nicht Gegenstand dieser Durchsicht.
> Nachgeholt und richtiggestellt in [REGEL1-0093-0095.md](REGEL1-0093-0095.md): 3 Fristen an
> 6 Aufrufstellen, davon 2 Verstöße, einer behoben, einer (`0078`, fremder Patch) gemessen und
> als heute folgenlos belegt.


Stand 07.09.2026, 08:1x. Auftrag: Nachtplan `doku/78` Abschnitt 0 Regel 1 (kein Workaround, kein
Quirk) und Abschnitt 0a (was am Gerät wirkt, steht in `patches/kernel/` **und** in `series`) einmal
vollständig gegen die Patches 0091-0097 halten.

**Gelesen wurde der erzeugte Baum, nicht die Patches** - frischer Tarball
`mainline/build/cache/linux-6.18.38.tar.xz`, danach alle 71 Zeilen der `series` mit `patch -p1`,
genau wie `build/build.sh` Z. 143-155. Zeilennummern unten beziehen sich auf diesen Baum.

Das Board wurde nicht angefasst. Wo eine Entscheidung ohne Messung nicht fällt, steht unten eine
Messvorschrift statt eines geratenen Werts.

---

## 0. Prüfbau

| Schritt | Ergebnis |
|---|---|
| 71/71 Serienzeilen mit `patch -p1` | sauber, **kein `.rej`** |
| `hy200_qz713df_a1_defconfig`, `ARCH=arm64 LLVM=1` | konfiguriert |
| `make drivers/soc/sunxi/ drivers/gpu/drm/tiny/ drivers/media/platform/sunxi/` | **grün** |
| `make dtbs` (u. a. `sun50i-h713-hy200-qz713df-a1.dtb`) | **grün** |
| dieselben fünf Übersetzungseinheiten mit `W=1` | eine Warnung, **nicht neu**: `cpu_comm_rpc.c:256 'prev_idx' set but not used` (aus 0014) |

Das gilt für den Stand **nach** der unter A1 beschriebenen Änderung an 0092/0097.
Der Prüfbau lief in einer Kopie unter `/tmp/claude-1000/wf-rest/regel1/`; der Baubaum der
Hauptsitzung wurde nicht angefasst, `series` nicht verändert (71 Zeilen, md5 unverändert).

---

## A. Muss vor der nächsten Abnahme weg

### A1 - toter Modulparameter `callwq_kernel_cb` - **erledigt, Patches geändert**

*Wo:* `drivers/soc/sunxi/cpu_comm/cpu_comm_rpc.c:23-35` im fertigen Baum - angelegt von `0097`,
ausgewertet nirgends, weil `0092` den ganzen Block entfernt, der ihn las.

*Warum Verstoß:* ein Schalter, der nichts tut, dessen `MODULE_PARM_DESC` aber Verhalten beschreibt
(„Kernel-seitigen Routine-Callback … aufrufen, Vorgabe 0: nur protokollieren"), das der Code nicht
mehr hat. Das ist genau die Sorte Quirk, die Regel 1 meint: eine Stellschraube als Ersatz für eine
Entscheidung. `grep -rn callwq_kernel_cb drivers/soc/sunxi/cpu_comm/` findet im fertigen Baum nur
noch die Deklaration und den Kommentar darüber.

*Gemacht* (Variante (b) aus `INTEGRATION-hauptsitzung.md`, geprüft und aufgegangen):

* `0097` auf seine drei bleibenden Korrekturen eingedampft - tgid-ABI (`+0x34` ist Parameter 3),
  `memset(routine_info, 0, …)`, RX-CALL-Druckoffsets. Die beiden `cpu_comm_rpc.c`-Hunks
  `@@ -19 @@` (Deklarationsblock) und `@@ -1011 @@` (`pr_warn` + Sperre) sind raus. Betreff und
  Dateiname bleiben gültig: der `memset` **ist** der callwq-Zeiger-Fix.
* `0092` gegen den so entstandenen Stand neu erzeugt (nur der `cpu_comm_rpc.c`-Abschnitt; die
  anderen sieben Dateien unverändert).
* Sicherung der Originale: `/tmp/claude-1000/wf-rest/regel1/backup/`.

*Warum der Zwischenzustand trägt* (wichtig fürs Bisektieren): nach dem neuen `0097` und **vor**
`0092` steht in `comm_CallWorkAction` wieder der Block aus 0014 - aber `routine_info` ist jetzt
genullt, also ist `callback == NULL`, der Sprung findet nicht statt und der `else`-Zweig schickt
das ACK. Der `memset` allein ist die vollständige Ursachenbehebung; der Modulparameter war nur
Gürtel zum Hosenträger. Genau diese Reihenfolge stand am 06.09. auf dem Tisch.

*Nachweis:* frischer Tarball + alle 71 Serienzeilen mit den geänderten Patches → 71/71 sauber,
kein `.rej`; der erzeugte Baum unterscheidet sich vom vorherigen **ausschließlich** um den
gelöschten Parameterblock (`diff -ru`, sonst nichts); Prüfbau siehe Abschnitt 0.

### A2 - `msleep(10 s)` als HPD-Low-Dauer, ohne Beleg für genau diese Dauer

*Wo:* `drivers/soc/sunxi/sun50i-h713-arisc.c:191` (`#define HPD_DOWN_MS 10000`) und `:1269`
(`msleep(HPD_DOWN_MS)` in `arisc_hdmi_edid_init()`), aus `0091`.

*Warum Verstoß:* Regel 1 verbietet künstliche Verzögerungen ohne Beleg, **warum genau diese Dauer**.
Der Kommentar darüber sagt selbst nur: HDMI verlangt ≥ 100 ms, und „die auf diesem Board bewiesene
Sequenz hält 10 s". Das ist die Herkunft des Werts - er stammt aus `analyse/hdmi-seq/arisc_edid_init.sh:30`
(`sleep 10`) und ist dort in `doku/nachtlog/J-pflichtliste.md` bereits als **Fund W8** verzeichnet:
*kein Stock-Beleg*. Stock stellt das HPD-Intervall auf 200 - `HDMI_SetHPDTimeInterval(0xC8)`, im
Stock-elog als `SetHPDTimeInterval from 200 to 200` (`re/captures/weltneuheit/elog-stock-LIVE.bin`,
tick 28823, `./THDMIRx.cpp 603`). Zwischen 200 ms und 10 s liegt Faktor 50, und der Wert steht jetzt
nicht mehr in einem Diagnoseskript, sondern im **Betriebspfad des Kernels**: `arisc_hdmi_edid_init()`
läuft in `h713_hdmirx_probe()`, macht die Anbindung des Aufnahmegeräts über zehn Sekunden lang und
ist der einzige Grund für `PROBE_PREFER_ASYNCHRONOUS` an diesem Treiber.

*Was fehlt:* eine Messung. Ohne sie ist jeder Ersatzwert geraten - deshalb hier **kein** Fix,
sondern die Messvorschrift in Abschnitt D.

*Sauber danach:* kleinste gemessene Dauer, die die Quelle wieder `connected` melden lässt, als
`HPD_DOWN_MS` mit Messdatum und Quelle im Kommentar; falls die Stock-200 genügt, den Stock-Wert.
Falls wirklich erst Sekunden wirken, ist das ein eigener Befund und gehört so in die Pflichtliste -
dann ist die lange Wartezeit belegt und damit erlaubt.

### A3 - `0096` bringt den DT-Knoten, aber nicht den Treiber (Abschnitt 0a)

*Wo:* `0096-arm64-dts-h713-add-the-tvcap-bringup-node.patch` legt
`tvcap_bringup: tvcap@50c0000` mit `compatible = "allwinner,h713-tvcap"` an. Im erzeugten Baum
gibt es **keinen** Treiber, der darauf bindet: `grep -rn h713-tvcap drivers/` ist leer. Der Treiber
liegt außerhalb des Baums, als Out-of-tree-Modul in `analyse/tvcap/h713-tvcap.c` (+ vorgebautem
`.ko`), und steht nicht in `patches/kernel/`, also auch nicht in `series`.

*Warum Verstoß:* Abschnitt 0a, wörtlich. Und es ist derselbe Fehler, den `0096` in seiner eigenen
Beschreibung behebt: „war nur eine Handänderung in einem Baubaum … verschwand, sobald ein neuer
Baum gebaut wurde". Der Knoten ist jetzt gerettet, der Treiber noch nicht. Ohne ihn bleiben TVFE
und TVCAP stromlos, das INCAP-Fenster liest 0x00000000 und der Aufnahmering bleibt leer - das ist
exakt der Befund der Nacht (grüne Wand), den `0096` beschreibt. Ein `.ko` neben dem Baum ist kein
Stand, der einen Neubau überlebt.

*Sauber:* `analyse/tvcap/h713-tvcap.c` als eigener Patch nach `patches/kernel/` (Kconfig-Symbol +
Makefile-Zeile + Defconfig-Eintrag wie bei den anderen H713-Treibern), Serienzeile dahinter.
**Nicht von mir gemacht** - `series` ist für diese Sitzung tabu; das ist ein Handgriff für die
Hauptsitzung. Solange er offen ist, ist die Serie für sich genommen nicht abnahmefähig, auch wenn
sie grün baut.

---

## B. Benannte Punkte fürs Log (kein Abnahmeblocker)

### B1 - Takt und Reset per rohem MMIO statt über die Standard-Schnittstelle

*Wo:* `sun50i-h713-arisc.c:331-348` (`arisc_enable_cpus_clocks()`, drei R_PRCM-Gates bei
`0x07010110/114/118` per Read-Modify-Write) und `:350-359` (`arisc_set_reset()`, R_CPUCFG
`0x07000400` Bit 0). DT: `reg`-Einträge `"cpus-clk"` und `"reset"` statt `clocks`/`resets`.

*Der Vorwurf eines früheren Prüfers trifft in seiner ursprünglichen Form **nicht mehr zu**:* der
Treiber verlässt sich hier nicht auf einen Vorzustand, er setzt die drei Gates selbst und fährt
den Reset selbst (assert → Image → para → deassert). Belegt ist es auch: boot0 druckt „prcm cpus
timer clock enable", und die Reihenfolge steht als Vendor-BL31-Rezept im Dateikopf. Damit fällt es
unter Regel 1, Ausnahme „was Stock tut (mit Beleg)". Die Fenster überlappen bewusst fremde Knoten
und werden deshalb mit `devm_ioremap()` statt `devm_ioremap_resource()` abgebildet; ich habe
nachgesehen: der D1-R-CCU-Treiber beschreibt bei `0x110/0x114/0x118` **nichts** (sein niedrigstes
Gate liegt bei `0x11c`, `ccu-sun20i-d1-r.c:42`), es gibt also kein gemeinsam beschriebenes Register
und keinen Konflikt mit dem CCU-Spinlock.

*Was aber übrig bleibt* - und das ist der Punkt, den ich benenne:

1. **R_CPUCFG.** Für genau diesen Block gibt es die Standard-Schnittstelle bereits im Baum:
   `CLK_BUS_R_CPUCFG` (Gate `0x22c` Bit 0) und `RST_BUS_R_CPUCFG` (`0x22c` Bit 16),
   `ccu-sun20i-d1-r.c:65` und `:118`, geliefert vom `r_ccu`-Knoten, den dieses DTSI ohnehin hat.
   Der Treiber nimmt weder das eine noch das andere - dass der Bus-Takt an und der Reset gelöst
   ist, kommt heute allein vom Bootloader. Das ist der eine Fall, der wirklich auf einen
   Vorzustand baut, obwohl die saubere Lösung fertig danebenliegt.
   *Sauber:* `clocks = <&r_ccu CLK_BUS_R_CPUCFG>; resets = <&r_ccu RST_BUS_R_CPUCFG>;` am
   `arisc`-Knoten, im Probe `devm_clk_get_enabled()` und `reset_control_deassert()` (nur
   deassert, nie assert - der Block gehört nicht uns allein).
2. **Msgbox.** `"msgbox-rx"`/`"msgbox-tx"` liegen in `0x03003000`, dessen Takt und Reset am
   `cpu_comm`-Knoten hängen (`clocks = <&ccu CLK_BUS_MSGBOX>`, `resets = <&ccu RST_BUS_MSGBOX>`).
   Der ARISC-Treiber hält keine Referenz darauf und es gibt zwischen den beiden Knoten auch keinen
   Phandle, also keine Reihenfolge. Probt `arisc` vor `cpu_comm`, redet die Startquittung in einen
   ungetakteten Block; das Ergebnis wäre `-ETIMEDOUT` beim Notify - also B2 unten, nur mit einer
   ganz anderen Ursache als der gemeldeten.
   *Sauber:* `clocks = <&ccu CLK_BUS_MSGBOX>` zusätzlich am `arisc`-Knoten (das Gate ist
   referenzgezählt, beide Treiber dürfen es halten). **Keinen** Reset dazunehmen.
3. Die drei CPUS-Timer-Gates gehören der Vollständigkeit halber ins D1-R-CCU-Modell (drei
   `SUNXI_CCU_GATE`-Zeilen bei `0x110/0x114/0x118`); dann wäre auch das `"cpus-clk"`-Fenster los.
   Das ist Kür, kein Verstoß.

### B2 - `h713_arisc_start()` gibt nach gescheiterter Startquittung `0` zurück

*Wo:* `sun50i-h713-arisc.c:1476-1489`. Schlägt der Handschlag fehl, wird `dev_err()` gedruckt und
`return 0` - die Anbindung gilt als gelungen, `debugfs` entsteht, `->running` bleibt aber falsch und
jeder Dienst antwortet `-ENODEV`.

Das ist **nicht** der Fehlertyp aus dem Auftrag (ein Timeout, der `ret = 0` setzt und dann so tut,
als sei alles gut) - der Fehler wird laut gemeldet, der Zustand ist in `debugfs/h713-arisc/status`
ablesbar, und es wird nichts Halbgares benutzt. Es ist trotzdem eine bewusste Abweichung von der
üblichen Kernel-Konvention und gehört deshalb ins Log: `h713_hdmirx_probe()` bekommt von
`arisc_hdmi_edid_init()` dann `-ENODEV` und schreibt das in `-EPROBE_DEFER` um (`:1641`), obwohl
der ARISC-Treiber gebunden **ist** und von selbst nie wieder in die Gänge kommt. Die Rückstellung
verpufft also, statt dass jemand den ARISC neu startet.
*Sauber, wenn man es aufräumt:* entweder Probe-Fehler nach oben geben (dann verschwindet der
Knoten und die Ursache steht einmal im Log), oder `->running` als ausdrücklichen, wiederholbaren
Startversuch anbieten (`debugfs`-Kommando `restart`), damit die Rückstellung des hdmirx auf etwas
warten kann, das eintreten kann.

### B3 - Rahmenerkennung über Pausen (`NOTIFY_GAP_MS`/`REPLY_GAP_MS` = 200 ms)

*Wo:* `sun50i-h713-arisc.c:177` und `:179`, benutzt in `arisc_read_frame()` ab `:454`.

Das Protokoll trägt keine Länge, die Firmware schiebt Wort für Wort, also ist das Ende eines
Rahmens eine Pause. Das ist sauber begründet und jeder Ausgang ist ein Fehler (`-ETIMEDOUT`), kein
Weiterlaufen. Preis: jeder 0x15-Aufruf (`CheckEDIDUpdateStatus`, `RequestEDID`) kostet danach
mindestens 200 ms Wartezeit. Kein Verstoß, aber der Wert ist eine Annahme über die Firmware und
gehört benannt, damit ihn niemand für gemessen hält.

### B4 - `h713_afbd_wait_ready()` warnt und macht weiter

*Wo:* `drivers/gpu/drm/tiny/sun50i-h713-afbd.c:353-363`. 50 ms `readl_poll_timeout` auf das
READY-Bit; läuft es aus, gibt es `drm_warn()` und die Funktion kehrt zurück (`void`). Die vier
Aufrufer (`RGB disable`, `RGB enable`, `video enable`, `video disable`) können darauf nicht
reagieren, weil `atomic_update`/`atomic_disable` selbst nichts zurückgeben können.

Es verdeckt nichts - die Warnung ist laut - , aber „Umschaltung hat vielleicht nicht stattgefunden"
läuft danach weiter in den Mux. Fürs Log; ein sauberer Umbau hieße, den Fehlschlag im nächsten
`atomic_check` sichtbar zu machen oder ihn zu zählen und in `debugfs` zu führen.

### B5 - Gamma: 40 ms auf den Bildzähler warten, dann trotzdem schreiben

*Wo:* `sun50i-h713-afbd.c:1085-1092`. Ausdrücklich als Bildgrenze, nicht als Bereitschaftsflagge
beschrieben, und mit Stock-Beleg („stock gives up after the same 40 ms and writes anyway",
Herkunft `libhaldisplay.so::WriteGammaLUTByColor`). Fällt unter „was Stock tut (mit Beleg)".
Kein Handlungsbedarf, nur der Vollständigkeit halber notiert.

### B6 - hdmirx bildet `-EAGAIN` auf `-EPROBE_DEFER` ab

*Wo:* `drivers/media/platform/sunxi/sun50i-h713-hdmirx/sun50i-h713-hdmirx.c:1620-1629`.
`-EAGAIN` heißt bei `cpu_comm_call()` „der Koprozessor hat die Anwendungsbereitschaft noch nicht
erreicht" - ein **Laufzeitzustand**, keine fehlende Geräteanbindung. Die Rückstellung wird hier
also als Warteschleife benutzt, die nur dann noch einmal läuft, wenn irgendein anderer Treiber
erfolgreich bindet. Das ist die Standard-Schnittstelle und damit erlaubt, aber es ist ein
Wiederholen ohne eigenen Takt. Sauber wäre ein Phandle auf `cpu_comm` (dann ordnet der Kern die
Probes) plus Bereitschaftsabfrage in der cpu_comm-API; `-EPROBE_DEFER` bliebe dann für den Fall
„Treiber noch nicht da" (`-ENODEV`), wo es hingehört.

### B7 - HDCP-Schritt wird bei fehlender Firmware übersprungen

*Wo:* `sun50i-h713-hdmirx.c:510-519`. `dev_warn` + `continue`. Der Schlüssel ist Vendor-Material
und liegt nicht im Baum. Das ist eine benannte, begründete Auslassung, kein Quirk - aber es heißt,
dass die Init-Sequenz auf einer Maschine ohne `hy310-hdcp22.bin` **anders** ist als die, die
abgenommen wurde. Gehört ins Log, damit ein Abnahmelauf ohne die Datei nicht als derselbe Lauf
gilt.

### B8 - 20-ms-Fenster in `h713_hdmirx_signal_present()` setzt ≥ 50 Hz voraus

*Wo:* `sun50i-h713-hdmirx.c:773-785`. Zwei Abtastungen der Flip-Zeiger im Abstand von 20-25 ms;
bewegt sich `y` nicht, gilt das als „kein Signal". Bei 60 Hz (16,7 ms Bildabstand) trägt das.
Heute ist das unkritisch, weil der Treiber genau **eine** Timing-Kombination anbietet
(`h713_hdmirx_timings_cap`, `:1020-1032`: 1920×1080, Pixeltakt fest 148,5 MHz). Sobald dort eine
zweite Zeile dazukommt, wird das Fenster falsch (24 Hz = 41,7 ms → jede zweite Abfrage meldet
fälschlich „kein Signal"). Der Wert gehört dann aus `rx->timings` abgeleitet, nicht als Konstante.

---

## C. Ältere Funde im selben Pfad - nicht 0091-0097, aber 0092 baut darauf auf

Diese Stellen stammen alle aus `0014-soc-sunxi-add-cpu-comm-ipc.patch` und wurden deshalb nicht
geändert. Sie stehen hier, weil `cpu_comm_call()` aus `0092` durch **jede einzelne** davon
hindurchläuft - und weil `0092` eine davon in seinem eigenen Dateikopf beschreibt, statt sie zu
beheben (`cpu_comm_api.c:14-18`). Zwei sind bereits als J-Funde W5/W6 verzeichnet.

| # | Stelle | Was |
|---|---|---|
| C1 | `cpu_comm_proto.c:297-304` | **Der klassische Fall aus dem Auftrag.** `cpu_comm_sem_down_timeout(sem_ptr, 100 ms)`; bei Fehlschlag `pr_info_ratelimited("sem timeout, bypassing")` und **`ret = 0`**. Der Kommentar darüber sagt selbst „DEBUG". Ein Fehlschlag wird in Erfolg umgeschrieben - genau der Fall, für den die Semaphore da ist (kein MIPS-ACK). = J-Fund W6. |
| C2 | `cpu_comm_proto.c:319-329` und `:369-383` | Zwei 100-Spin-Schleifen mit `schedule()` und `-EBUSY` am Ende. Der TODO-Block `:336-367` beschreibt den sauberen Weg selbst (Semaphore `s_CommSockt[remote]+235`, Stock-RE @ `0x3c40`) und nennt sich wörtlich „a workaround". = J-Fund W5. |
| C3 | `cpu_comm_proto.c:464-470` | `do { GetFreeWaitComm(...); schedule(); } while (!wait_ptr);` - **ohne jede Schranke**. Läuft der Wait-Objekt-Vorrat leer und füllt der MIPS ihn nicht nach, hängt der Aufrufer für immer, ohne eine Zeile im Log. Von den drei Schleifen in dieser Funktion ist das die einzige ohne Ausgang. Neu benannt; steht so noch nicht in W5. |
| C4 | `cpu_comm_proto.c:555-566` | 200 × `udelay(100)` (bis 20 ms) plus ein `pr_info` **pro RPC** im Betriebspfad, nur um zu drucken, ob die Firmware das SENT-Bit gelöscht hat. Diagnose an einer Stelle, an der sie Betrieb kostet: bei der Init-Sequenz aus `0094` sind das gut 30 Zeilen und bis zu einer halben Sekunde. Gehört hinter ein `pr_debug` oder einen ausdrücklichen Diagnoseschalter. |
| C5 | `cpu_comm_rpc.c:996, 1002, 1008, 1015, 1052` | Fünf frühe `return;` in `comm_CallWorkAction()` springen am `out_free:`-Label vorbei und geben das mit `kmalloc` geholte `item` nicht frei (`kfree(item)` steht bei `:1090`). Kein Regel-1-Punkt, ein schlichtes Leck - jedes Mal 40 Byte, ausgelöst von Nachrichten des Koprozessors. |

Nichts davon habe ich angefasst: es liegt außerhalb des Auftrags und `0014` ist die Grundlage von
allem, was heute auf dem Board läuft. C1 und C3 sind die beiden, die ich vor dem nächsten längeren
Dauerlauf ansehen würde.

---

## D. Board-Anfrage: HPD-Low-Dauer (zu A2)

*Frage:* Reicht die Stock-Dauer (200 ms) oder eine andere kurze Dauer, damit die Quelle den
Stecker als neu gesteckt sieht - oder braucht es wirklich 10 s?

*Warum jetzt anders als M4 in `J-pflichtliste.md`:* die Messung braucht nicht mehr `/dev/mem` und
kein `arisc_hdmi.py`. `0091` bringt die Schnittstelle selbst mit, als
`/sys/kernel/debug/h713-arisc/cmd`. Damit misst man den Pfad, der auch im Betrieb läuft.

*Vorbedingung:* Bild steht, `/sys/kernel/debug/h713-arisc/status` zeigt `arisc: running`,
`edid_module: ready` und `edid_gate: 1`. Ist `edid_gate` 0, weigert sich `hpd … up` mit `-EIO` -
dann zuerst die volle Sequenz (`echo edid 0 > …/cmd`) und danach messen.

Für jede Dauer aus `0.2 0.5 1 3 10` (in dieser Reihenfolge, von kurz nach lang):

```
# 1. Pin runter, warten, Pin hoch - Dauer in der Variablen T
T=0.2
timeout 30 ssh root@192.168.8.141 "echo 'hpd 0 down' > /sys/kernel/debug/h713-arisc/cmd; \
                                   sleep $T; \
                                   echo 'hpd 0 up'   > /sys/kernel/debug/h713-arisc/cmd; echo rc=\$?"

# 2. Was sagt die Quelle? (der ThinkPad an HDMI-1)
timeout 20 ssh user@192.168.8.162 'cat /sys/class/drm/card0-HDMI-A-2/status'

# 3. Kommt das Bild zurück?
python3 analyse/hdmi-seq/wandcheck.py shot hpd-$T

# 4. Was hat der Treiber gesehen?
timeout 20 ssh root@192.168.8.141 'cat /sys/kernel/debug/h713-arisc/status; \
                                   cat /sys/kernel/debug/sun50i-h713-hdmirx/status'
```

*Gesucht:* die **kleinste** Dauer, bei der (2) wieder `connected` meldet **und** (3) ein Bild zeigt
**und** in (4) `SignalChange`-Zähler und `frames: … geliefert` weiterlaufen. Zwischen zwei Läufen
mindestens 5 s Pause, und jede Dauer zweimal - ein einzelner Treffer ist bei Hotplug kein Ergebnis.

*Ergebnis eintragen:* Wert + Messdatum als Kommentar an `HPD_DOWN_MS` in `0091`, Zeile in
`doku/75` und in `analyse/hdmi-seq/arisc_edid_init.sh`, Fund **W8** in `J-pflichtliste.md`
abhaken.

*Erwartung:* ≥ 100 ms genügt (HDMI-Spezifikation, und Stocks 200 passt dazu). Wenn erst Sekunden
wirken, ist das ein eigener Befund - dann ist die lange Wartezeit belegt, A2 ist erledigt, und der
Grund gehört in den Kommentar.

---

## E. Wo nichts ist

Der Vollständigkeit halber, damit niemand zweimal sucht:

* **Kein Doorbell-Puls** mehr im ARISC-Pfad. `0091` schreibt nur MSG_DATA und begründet im
  Dateikopf, warum das reicht (die Firmware pollt: `rpm_poll` @ `0xc5d0`, Poller `0x7bbc`,
  Startwarter `0x756c`). J-Fund **W1 ist damit im Kernelpfad erledigt.**
* **Keine Rettungsschleife, kein `unstick`, kein „einmal pulsen"** in 0091-0097
  (`grep -inE 'unstick|retry|nochmal|again'` über die sieben erzeugten Dateien: nichts).
* **Kein `/dev/mem`** im Betriebspfad. Alles läuft über Treiber; `debugfs` ist Diagnose und als
  solche gekennzeichnet. J-Fund **W10 ist für den Kernelpfad erledigt**, solange die fünf Skripte
  nicht mehr gebraucht werden.
* **Kein fester Ring-Slot** mehr. `0093` nimmt pro Vsync den fertigen Slot und veröffentlicht ihn
  über den Flip-Notifier; der 120-Hz-Abtasttimer, der daneben lief, ist ersatzlos weg und der
  Grund steht im Quelltext (`sun50i-h713-hdmirx.c:721-733`). J-Fund **W9 erledigt.**
* **Genau ein Modulparameter** in den sieben Dateien - der aus A1, und der ist jetzt weg.
  Kein weiterer Schalter, kein Sysfs-Knopf, keine Kconfig-Option ohne Wirkung.
* **Alle Wartezeiten außer A2 enden in einem Fehler**, nicht in einem Weiterlaufen:
  `arisc_wait_handler` → `-ETIMEDOUT`, `arisc_send` FIFO → `-EBUSY` mit Meldung,
  `arisc_hpd_locked` → `-EIO`/`-ETIMEDOUT`, `cpu_comm_call()` → `-ETIMEDOUT` statt „Erfolg ohne
  Werte" (das ist der eigentliche Gewinn von `0092`, `cpu_comm_rpc.c:764-770`).
* **`0095` (Gamma/CTM)** ist unauffällig: die CTM-Prüfung weist ab, was die Stufe nicht kann
  (Nebendiagonale, negative Verstärkung, Überlauf), statt es stillschweigend fallenzulassen, und
  sie tut das im `atomic_check`, wo KMS es erwartet.

---

## F. Was ich geändert habe

| Datei | Änderung |
|---|---|
| `mainline/patches/kernel/0097-soc-sunxi-cpu-comm-fix-the-call-argument-abi-and-the-callwq-pointer.patch` | zwei `cpu_comm_rpc.c`-Hunks entfernt (Deklarationsblock des Modulparameters, `pr_warn` + Sperre); Beschreibung Punkt 2 auf den `memset` als vollständige Ursachenbehebung umgeschrieben; Betreff und Dateiname unverändert |
| `mainline/patches/kernel/0092-soc-sunxi-h713-cpu-comm-kernel-api.patch` | `cpu_comm_rpc.c`-Abschnitt gegen den neuen 0097-Stand neu erzeugt; die anderen sieben Dateien unverändert |
| `doku/nachtlog/REGEL1-durchsicht.md` | diese Datei |

`patches/kernel/series` **nicht** angefasst (71 Zeilen, unverändert). `build/build.sh` nicht
aufgerufen. Sicherung der beiden Originalpatches:
`/tmp/claude-1000/wf-rest/regel1/backup/`.
