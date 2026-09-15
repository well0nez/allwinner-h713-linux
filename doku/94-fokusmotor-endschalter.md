# Fokusmotor und der Bereichswächter auf PH14 - Stand 12.09.2026

> **Der Titel hieß bis zum 12.09. „der tote Endschalter“. Das war in zwei Punkten falsch:**
> es ist kein Endschalter, sondern ein Bereichswächter, und ob er tot ist, war nie belegt.
> Der ursprüngliche Text steht unverändert unter dem Nachtrag.

Ergebnis einer Sitzung am Gerät, gemeinsam mit Marco. Vorarbeit: der Agentenbefund in
[`../mainline/patches/vorschlaege/motor-fokus/BEFUND.md`](../mainline/patches/vorschlaege/motor-fokus/BEFUND.md).

## NACHTRAG 12.09.2026 - die Kernaussage dieses Dokuments ist widerlegt

**Der Rest dieses Dokuments ist überholt. Lies erst hier.** Belege in
[`../mainline/patches/vorschlaege/motor-limiter/README.md`](../mainline/patches/vorschlaege/motor-limiter/README.md),
Fix in den Patches `0153`/`0154`.

**Es gibt gar keinen Endschalter.** PH14 ist ein **Bereichswächter**: er liest HIGH (`active_level = <1>`),
*solange* die Mechanik im erlaubten Fahrbereich steht. Der Anschlag wird daran erkannt, dass dieser Pegel
**wegfällt**. Belegt aus dem Stock-`vmlinux` (DWARF, Quelldatei `drivers/misc/gpio-motor/motor-control.c`):

- `motor_limiter_status` (`0xc05d6930`): bei **einem** Limiter - dem HY310-Fall - wird das Richtungsargument
  **gar nicht ausgewertet**. Derselbe Pin beantwortet hoch *und* runter. Ein Anschlagkontakt kann das nicht,
  ein Fenstergeber schon.
- `check_motor_position()` nennt den 1-Zustand wörtlich `"limited normal,no need to check postion"` und sucht
  sonst: 100 msteps hoch, 250 runter - daher unsere `HOMING_UP_MAX`/`HOMING_DN_MAX`.
- `motor_run_up_control`/`motor_run_dn_control` kehren **symmetrisch** um, sobald der Wert **0** wird.
- `active_level = <1>` steht im echten Vendor-DTS (`hy310_factory.dts:2643`) und ist bindend: fehlt es, bricht
  `motor_control_fdt_parse` mit `-EINVAL` ab.

**Warum wir nichts gesehen haben - wir waren es selbst.** Patch `0111` **erzwingt einen Pull-down** auf dem Pad,
begründet mit „the defined idle level for active_level = 1". **Diese Regel gibt es im Herstellercode nicht:**
Stock setzt zwischen `gpio_request()` und dem ersten Lesen keinen einzigen Bias, und `motor_ctr` hat keine
pinctrl-Gruppe. Der Pull-down im Stock-Pinabzug ist das, was die **Bootkette** hinterlässt - hier wurde eine
Beobachtung am laufenden System für eine Absicht des Treibers gehalten. Da „im Bereich" HIGH ist, meldet ein
interner Pull-down an **jeder** Position „außerhalb", sobald der Geber nicht selbst treibt. `0153` fasst das Pad
per Vorgabe nicht mehr an (`limiter_bias = -1`, wie Stock).

**Zwei konkrete Fehler unten im Text:**

1. **`boot.log:284` belegt keinen Lesevorgang.** Die Zeile ist `dev_err` für das *fehlende* `limiter-**dn**-gpio`.
   Das Zeitargument trägt aber trotzdem, nur anders herum: 8,5 ms sind weniger als **ein** mstep (≈14,4 ms), die
   Suchschleife lief also nicht → der erste Read lieferte „limited normal" → **PH14 war beim Booten HIGH.**
2. **Die 440-mstep-Fahrt war ungeeignet.** Sie lief **ohne Bias** und quer durch die **Mitte** des 800-mstep-
   Fahrwegs; ein Rand wurde nie angefahren. „Überall HIGH" ist dort das erwartete Ergebnis, kein Befund.

Damit fällt auch die These, unser alter Treiber habe den Schalter zerstört - sie stützte sich auf ein
„hat mal funktioniert", das so nie belegt war, und auf eine Messung, die nichts zeigen konnte.

**Noch offen:** ob der Geber lebt. Der Test (`0154` zeigt den Rohpegel) bewegt in Schritt 1 **nichts**; Schritt 2
fährt abwärts, weg vom oberen Anschlag. Kippt `raw` von 1 auf 0, lebt er. Bleibt er stur, ist die Erklärung für
Marcos Beobachtung eine andere: Stock erkennt den Anschlag dann **auch nicht**, sondern *behauptet* die Kante nach
40 vergeblichen Umkehrschritten (`g_motor_edge_Up = 1` bei `k == 40`, `0xc05d7014`).

Ein Muster, das an diesem Tag zum vierten Mal auftrat: die Antwort lag jedes Mal in Material, das längst vorlag -
Vendor-Gerätebaum, Stock-`vmlinux`, ein Patchkopf. Vgl. `analyse/boot/ntc-gpadc-messung-20260911.txt` (Temperatur),
`doku/60-offen.md` (pinctrl-IRQ) und `analyse/boot/wlan-aic8800-messung-20260912.txt` (WLAN-GPIO).

## Kurzfassung

Der Motor ist in Ordnung, der SoC-Pin ist in Ordnung, **der Endschalter liefert kein Signal**.
Ohne ihn gibt es keinen absoluten Bezugspunkt, und damit keinen sicheren automatischen Betrieb.
Der Motorknoten steht deshalb wieder auf `status = "disabled"`; der Treiber ist gebaut, aber nichts
lädt oder probt ihn.

## Was das Gerät ist - eine Namenskorrektur

Es gibt auf der HY310 **genau einen** Schrittmotor, und das ist der **Fokusantrieb**. Belegt aus
drei unabhängigen Quellen: die Stock-DTB hat einen einzigen Knoten `motor_ctr` (vier Phasen
PH4-PH7, ein Limiter PH14), der Stock-Kernel genau einen Satz Motor-Globals, der laufende
GPIO-Abzug genau fünf Motorleitungen. Das Wort „keystone" kommt in der **gesamten
Herstellerfirmware nicht ein einziges Mal vor** - nicht in kallsyms, nicht in `display.bin`. Es
stammt aus dem HY300-Baum und war unsere Erfindung. Treiber, Kconfig-Symbol und Kompatible heißen
seit dieser Sitzung `hy310-focus-motor` / `HY310_FOCUS_MOTOR` / `allwinner,hy310-focus-motor`.

## Was gemessen wurde

**Der Motor läuft.** Hörbar, und die Mechanik reagiert: bei Handfahrt wurde das Bild scharf. Der
Positionszähler läuft gleichmäßig mit (−18 je 40 msteps).

**Der SoC-Pin ist gesund.** Mit dem Diagnoseschalter `limiter_bias` (Patch `0115`) durchgemessen,
ohne die Mechanik zu bewegen:

| Bias | GPIO-Abzug |
|---|---|
| Pull-down (wie Stock) | `in lo` |
| Pull-up | `in hi` |
| ohne Bias | `in hi` |

Der Pin folgt dem Bias sauber. Ein nach Masse kurzgeschlossenes oder zerstörtes Pad bliebe unter
Pull-up LOW. **Die Schadenshypothese am Pad ist damit widerlegt.**

**Die Pin-Konfiguration entspricht Stock, byte für byte.** Nach dem Fix des Agenten:

```
Stock  pin 238 (PH14): input bias pull down, output drive strength (20 mA)
wir    pin 238 (PH14): input bias pull down (1 ohms), drive strength (20 mA)
Mux    GPIO 2000000.pinctrl:238   (beide)
```

Die Konfiguration ist also **nicht** mehr der Unterschied.

**Die Leitung trägt keine Positionsinformation.** Ohne Bias (der Pin liest dann die Außenwelt
direkt) wurde über **440 msteps** gefahren - mehr als die Hälfte des in der DTS hinterlegten
Fahrwegs von 800, quer durch den Bereich, in dem das Bild scharf ist. Der Pin blieb an **jeder**
Position unverändert HIGH. Ebenso beim Homing (100 hoch + 150 zurück, Prüfung nach jedem
einzelnen mstep) und bei einer durchgehend abtastenden Handfahrt.

## Was das heißt

Der Schalter ist nicht angeschlossen, seine Leitung ist unterbrochen, oder ihm fehlt die
Versorgung. Welches davon, sagt nur eine Messung im offenen Gerät - die Strecke hinter dem
SoC-Pin ist von Software aus nicht weiter auflösbar.

**Ein Verdacht, der benannt gehört:** unser eigener Stock-Bootlog
(`re/captures/HY310-DEV/boot.log:284`) belegt, dass der Schalter an *diesem* Gerät unter Stock
einmal aktiv gelesen wurde - der Abstand von 8,5 ms zur nächsten Kernelzeile lässt keine
Suchschleife zu, der erste Lesevorgang muss erfolgreich gewesen sein. Er hat also funktioniert.
Seither hat unser **alter** Treiber die Leitung bei jedem Boot kurz als Ausgang auf LOW getrieben
(`devm_gpio_request_one(dev, gpio, 0, …)` ist `GPIOF_OUT_INIT_LOW`), während der Schalter sie auf
3,3 V zog - ein Kurzschluss gegen den Pad-Treiber, viele Male wiederholt. Das Pad hat es
überstanden; der Schalter oder seine Verdrahtung möglicherweise nicht. Bewiesen ist das nicht,
aber es ist die einzige bekannte Veränderung zwischen „hat funktioniert" und „liefert nichts".

## Warum Software-Grenzen das nicht auffangen

Naheliegend, aber falsch: den Fahrweg einfach über die Schrittzahl begrenzen. **Ein Schrittzähler
ohne Bezugspunkt schützt nichts.** Er zählt relativ zu einem Start, den wir nie kennen - nach
jedem Stromausfall, jedem Modul-Neuladen, jedem Verstellen von Hand steht die Mechanik irgendwo,
und der Zähler beginnt trotzdem bei null. Genau dafür existiert der Schalter: er ist der einzige
**absolute** Bezug im System. Stocks `motor_ctrl_no_limit` ändert daran nichts, es schaltet die
Prüfung nur ab.

## Wie es weitergehen könnte

1. **Den Schalter reparieren.** Die eigentliche Lösung. Es ist genau bekannt, wo zu messen ist:
   die Strecke von PH14 zum Schalter und dessen 3,3-V-Seite. Der SoC-Pin ist nachweislich in
   Ordnung, es geht nur um das, was dahinter hängt.
2. **Die Kamera als Bezug.** Das Gerät hat eine, und Stock benutzt genau sie für den Autofokus -
   „Bild scharf" statt „Schalter aktiv". Technisch der saubere Ersatz für einen toten Schalter,
   aber es ist das zurückgestellte große Projekt (Sensor, MIPI-CSI, Regelkreis), siehe
   [`60-offen.md`](60-offen.md).
3. **Bis dahin: kein automatischer Betrieb.** Kein Homing, keine behauptete Position, nur
   ausdrückliche relative Fahrbefehle mit dem Menschen als Bezugspunkt. Vor allem verhindert das
   genau den Vorgang, der den Motor beschädigt hat: dass der Treiber von sich aus losfährt und
   gegen den Anschlag drückt.

## Zustand jetzt (12.09.2026, nach der Messung)

- `&motor_ctr { status = "okay"; }` - `0157`. Die alte Begründung *„Endschalter liefert
  nichts"* ist widerlegt, siehe Nachtrag oben.
- `homing` ist **standardmäßig aus** - `0156`. Der Treiber wird beim Booten geladen
  (`CONFIG_HY310_FOCUS_MOTOR=m`, über modalias), richtet die Pads ein, zeigt sysfs und
  **bewegt dabei nichts**. Damit ist die Blacklist auf dem Netboot-Rootfs
  (`/etc/modprobe.d/hy310-focus-motor.conf`) nur noch Restbestand; ins Release-Rootfs
  gehört sie nicht.
- Bedient wird von Hand mit [`userspace/h713-focus`](../userspace/h713-focus/README.md):
  liest `motor_limit` vor und nach jeder Bewegung, harte Obergrenze 400 msteps je Lauf,
  schreibt `motor_ctrl_no_limit` nie, lädt das Modul nicht selbst.
- Patches in der Serie: `0009` (umbenannt), `0111` - `0114` (Endschalter-Lesepfad, Handfahrbefehle,
  Stock-Eigenschaftsnamen, Kconfig), `0115` (Bias-Diagnose), `0116` (`homing=0` als Möglichkeit),
  `0153` (Bias nicht mehr erzwingen), `0154` (Rohpegel in `motor_limit`), `0156` (`homing`
  standardmäßig aus), `0157` (Knoten aktiv).

**Offen und ungeprüft:** ob es in der *oberen* Richtung überhaupt eine Wächterkante gibt.
Gemessen wurde nur die untere (`edge_dn` bei step −206). Solange das so ist, wäre ein Homing
eine Fahrt mit unbekanntem Ende - deshalb `0156`.

## Eine Lehre für den Umgang mit dem Gerät

Das Probe des Treibers stößt ein Homing an, und Homing beginnt mit 100 msteps **aufwärts**. Steht
die Mechanik bereits am oberen Anschlag, drückt jeder Modul-Ladevorgang dagegen. Genau das wäre
beim Diagnoseversuch beinahe dreimal hintereinander passiert. Deshalb `0116`: für alles, was den
Zustand nur *ansehen* will, gilt `homing=0`.
