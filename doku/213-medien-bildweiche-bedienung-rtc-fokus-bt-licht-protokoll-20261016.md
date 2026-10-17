# 213 - Das Nebenprojekt Medien, dritter Teil: die Bildweiche, die Bedienung beim Start, die RTC am 24-MHz-Quarz (Patch `0320`), Fokus und Bluetooth, das Licht des HY310 (16. und 17.10.2026)

**Kurz:** Fortsetzung von `doku/212`. Der Eintrag ist der Beleg für das, was am 16.10.2026 nach dem ersten Endabbild des Zweigs
`medien` dazukam: die Pakete anzeige-fix (§1), die Korrektur der Panel-Seite (§2), die Lichtbefunde der Pakete mythos-anzeige und
mythos-licht (§3), H Bedienung (§4), standby-wecker mit dem Kernel-Patch `0320` (§5), fokus-bt (§6) und der Endbau rend4 (§7).
Die Rohlogs liegen in den lokalen Arbeitsordnern der Pakete und sind nicht veröffentlicht; die Zahlen unten sind daraus übernommen,
die Quelle steht je Absatz. **Gemessen wurde nur am HY310** (Kernel 6.18.38, Zweig `medien` 693e9ec bis a70bd6f); der HY300PRO-G-EU ist in
keinem Punkt nachgemessen (`TODO.md` 2.84 ff.). Was nicht gemessen wurde, steht in §8.

## 1 Die Bildweiche: Konsole über dem Client, weißer Blitz, Stumm, die Seite ohne Signal (anzeige-fix, 16.10.)

**Ausgangslage** (Abnahme "wie ein Nutzer" am installierten Endabbild rend3, 16.10. vormittags, Kamera der Box): nach jedem direkten
Wechsel zwischen zwei Clients (Kodi, Desktop, Browser, alle sechs Richtungen) stand an der Wand die Konsole oder Schwarz statt des neuen
Clients - **19 von 19**; auf dem Rückweg zu HDMI 3 von 8; bei jeder Übergabe zwischen Ring und Client ein weißer Blitz von ein bis zwei
Kamerabildern (**8 von 8**); Stumm war nach jedem Standby weg (h713-tv startet im Aufwachen neu); der Ring nach einer Rückkehr zu HDMI
20 bis 30 s unruhig. Mechanismus, in vier Gegenproben gemessen: beim Ende eines Sitz-Clients setzt seatd tty1 auf `KD_TEXT`; der
Übergang GRAPHICS nach TEXT ruft im Kernel `drm_fb_helper_set_par()` mit `FB_ACTIVATE_KD_TEXT` und erzwingt einen fbdev-Commit am
DRM-Master vorbei, der die Primärebene mit dem Konsolenpuffer belegt und ihre z-Lage lässt; stand in dem Augenblick eine Einblendung
(z-Lage 2, über dem Video), blieb die Konsole über dem Bild, bis h713-osd neu zeichnete. Ohne gezeigte Einblendung trat es nicht auf
(Gegenprobe E1); mit `KDSETMODE KD_TEXT` von Hand unter laufendem Kodi direkt ausgelöst. (Paket abnahme, Befunde §1, §1a, §2.)

**Korrektur an der Wurzel** (Serie 3984556, fünf Commits): seatd verwaltet keinen VT mehr (`SEATD_VTBOUND=0`, Drop-in
`seatd.service.d/10-h713-no-vt.conf` im Profil `desktop`; tty1 bleibt dauerhaft im Textmodus, jedes spätere `KD_TEXT` ist ein No-op);
h713-tv schaltet die Konsolentastatur (`K_OFF`) ab, solange etwas anderes als die Konsole auf dem Panel steht, und gibt sie mit der
Konsole zurück (ohne seatds VT landete sonst jede Taste im versteckten Login von tty1); jeder Commit von h713-tv trägt die Primärebene
im gewollten Zustand; die Übergabe Ring <-> Client läuft auf demselben Claim (`warp switch`, dieselben drei NV12-Puffer, kein
Abschalten der Ebene); Stumm liegt in `/run/h713-tv-state/mute` und übersteht den eigenen Neustart (nicht den Kaltstart,
Entscheidung); eine deckende Seite öffnet auch ohne HDMI-Signal über Schwarz (`osd show N cover`). (Paket anzeige-fix, Bericht §2.)

**Gemessen** (HY310, 16.10. 12:12 bis 13:29 UTC, Gate `abnahme.sh` ganz, nachbewertet mit den Rohbildern dieses Laufs):

| Prüfung | vorher | nachher |
|---|---|---|
| Client -> Client, sechs Richtungen, drei Runden | 19 von 19 schwarz | **18 von 18 mit Bild** |
| Client -> HDMI | 3 von 8 schwarz | **12 von 12 mit Bild** |
| HDMI -> Client | 8 von 8 gut | 12 von 12 gut |
| Blitz bei der Übergabe Ring <-> Client (Kamera, Faktor 1,25, höchstens 3 Bilder) | 8 von 8 | **0** |
| Einstellungsseite über jedem Modus, Home/Back | 4 von 4, 2 von 2 | 12 von 12, 3 von 3 |
| Standby aus jedem Modus und Powertaste | 5 von 5 | 10 von 10 Zellen (5 Standbys) |
| Stumm über den Standby | weg nach 1 von 1 | **gehalten in 5 von 5** (`kept from the run before`) |
| Launcher ohne HDMI-Signal | öffnet nicht (`ok unseen`) | an der Wand (Struktur 6,0 gegen Schwarz 2,4), Tastatur `K_OFF`, nach Back Konsole zurück |

Gate insgesamt **74 von 75**; die eine Zelle war der Selbsttest selbst: der Ring nach der Rückkehr zu HDMI ist ohne `ctl check` ruhig
(0 bis 1 spätes Bild in 44 s), mit laufendem `check 300` 145 und 97 späte Bilder je 10 s - die "Unruhe nach dem Wechsel" war das
Messwerkzeug der Ruhe-Zelle, kein Betriebsfehler; die Zelle zählt den Check seitdem getrennt. Einschwingen nach einem Wechsel: am Ring
ab dem ersten 5-s-Fenster 59,4 Bilder/s ohne Verlust; im Client-Weg ist die Bildfolge die des Clients (Kodis Menü gleichmäßig 21,6
Bilder/s mit ein bis drei Vsync Abstand bei 150 MHz GPU-Takt, Firefox nur beim Laden, danach 0 Commits). Flackern bei Einblendungen
über einem ruhenden Client: mit der Kamera nicht reproduziert (Adresswechsel der Videoebene nur je Commit, Gesamthelligkeit je
Einblendung unter 1 %) - die Antwort kam aus §3. (Paket anzeige-fix, Bericht §8.)

**Rest, dokumentiert:** ein fremder erzwungener Commit (ein Programm, das selbst GRAPHICS und dann TEXT setzt; im Abbild keines)
würde erst mit dem nächsten Commit von h713-tv geheilt. Nicht gemessen: der Bypass-Fall der Übergabe (Keystone gleich Identität), die
157 plus 55 späten Warp-Bilder in den ersten 100 s eines Boots (sie fallen zeitlich mit dem Bluetooth-Verbindungsaufbau der
Fernbedienung zusammen, §3).

## 2 Die Panel-Seite als Lastreiz (h713-panel, mythos-anzeige, 16.10.)

Die offene Einstellungsseite der Weboberfläche fragt alle 3 s den Status ab; dafür startete `h713-panel` jedes Mal ein Python-Programm
(`h713-keystone status`, 0,27 s CPU-Zeit). Das war der 3,0-s-Puls im Licht (§3): mit offener Seite in jeder Messung, auch unter Firefox
(Autokorrelation 3,02 s, r 0,77 bis 0,90). Korrektur (Commit 1b9ccbd): die Keystone-Fakten entstehen im Prozess des Panels. Gemessen am
HY310 (Grau-Client stehend, eigener Abruf alle 3 s): altes h713-panel Spitze je Abruf **+1,44 % / +1,57 %** (Mittel/Median), 0,27 s, 274
Kamerabilder über 0,7 % in 45 s; neues h713-panel **+0,71 % / +0,70 %**, 0,08 s, 6 Bilder. Die Reste sind die zwei C-Statusprogramme
(`h713-tv ctl status brief`, `h713-warp ctl status`, je etwa +0,45 % für ein Bild). Hosttests h713-panel 74. (Paket mythos-anzeige,
Bericht §3c.4.)

## 3 Das Licht des HY310 folgt dem Strom des SoC (mythos-anzeige, mythos-licht, 16.10.)

**Beobachtung** (Marco, 16.10.): leichtes Flackern über Firefox und Kodi, bei jedem Update einer Einblendung, nach dem Umschalten
mehr, zwischendurch auch ohne Einblendung; über HDMI "quasi nicht"; ein weißer Client, der jedes Bild committet, nicht.

**Messweg:** die Kamera der Box als Rolling-Shutter-Lichtschreiber - je Kamerabild die 480 Zeilenmittel (eine Zeile je 83 µs), ein helleres
Panelbild von 16,8 ms ist ein Band über etwa 240 Zeilen; Eichung mit einem Client, der jedes Bild zwischen Grau 200 und 60 wechselt
(29,7 Hz): Bänder von je 16 ms, abwechselnd -11 % und +11 % (bestanden). Dazu eine Registerspur über AFBD, TCON, LVDS, Komposition und
INCAP (alle 2 ms) und Lastreize **ohne Bildkette** (Rechenstoß 150 ms auf vier Kernen alle 2 s; reiner Taktwechsel 480 <-> 1296 MHz ohne
Last; GPU-Last ohne Anzeige). Kontrolle der Kamera mit schwarzer Projektion: bei denselben Rechenstößen innen +0,13 %, am Rand +0,04
Zähler - ein additiver Versorgungsfehler der Kamera ist ausgeschlossen; einen multiplikativen (Verstärkung folgt der Last) kann nur das
Auge ausschließen. (Paket mythos-anzeige, Bericht §3, §3a, §3c.1.)

**Gemessen** (HY310, Grau 200 über die ganze Wand, Belichtung 20 ms, innere Zeilen, Spitze gegen gleitenden Median):

| Reiz über dem stehenden Client | Licht |
|---|---|
| Rechenstoß 150 ms, vier Kerne, fester Takt 1296 MHz / 1,06 V | **+1,20 %** über 4 bis 11 Kamerabilder (0,24 s), 40 bis 90 ms nach dem Stoß |
| derselbe Stoß bei festem 480 MHz / 0,90 V | **+0,48 %**, ein Kamerabild |
| nur Taktwechsel 480 <-> 1296 MHz ohne Last | nichts (5 von 34 Marken mit Ereignis, Zufallsniveau) |
| GPU-Last 300 ms ohne Anzeige | +1,23 %, 8 bis 9 Bilder - wie CPU-Last |
| Einblendung (`h713-osd ctl volume`) alle 0,7 s, Höchsttakt 1296 MHz | +0,73 % / +0,85 %, 0,15 s |
| dieselben Einblendungen mit `scaling_max_freq` 1008 MHz / 792 MHz | +0,33 % / +0,22 %, ein Bild (skaliert mit f mal V^2 des Stoßes) |
| ein Commit nach einer Pause (alle 2 s derselbe Inhalt) | ein helleres Einzelbild +0,75 %, 41 bis 55 ms nach dem Commit |
| jedes Bild derselbe Inhalt committet (60/s, wie der Ring) | Grundhelligkeit +1,8 %, keine Pulse |
| Backlight-Stufe aus Linux 0 / 25 / 75 / 100 (PWM2 an PB4, Duty folgt) | **178,0 / 178,2 / 178,2 / 178,4** - dasselbe Licht |
| Firmware-Regler `dci`, `black`, `tnr`, `snr` auf 0 (Firefox ruhend) | unverändert (sd 1,10 -> 1,06 -> 0,98 %, Periode 3,02 s bleibt) |
| Registerspur je Reiz | keine Änderung außer den bekannten Zählern des Treibers und der Firmware |

**Mit Marcos Auge** (Ansage, dann Urteil): dasselbe Grau, einmal jedes Bild vom Warp neu gezeichnet und committet (Variante 1), einmal
einmal committet und dann ruhend (Variante 2): "kaum wahrgenommen" gegen "immer kurz, einmal, wie ein Mini-Mini-Flash"; die Kamera
sieht in Variante 2 die Pulse und 11 Teilbild-Bänder, in Variante 1 0 Bänder. Ein Kernelversuch, der das stehende Speicherbild je Vsync
neu in die Warteschlange legt (Adresspaar und DIRTY wie ein Flip), änderte nichts (Pulse +0,90 % mit, +1,03 % ohne; Stöße +1,52 %) und
wurde verworfen: ruhig macht die gleichmäßige Last des Zeichnens, nicht das Latch. Blindtest der Taktdeckelung (Firefox frisch
gestartet, A `scaling_max_freq` 1008 MHz, B 1296 MHz): A "stark", B "genauso stark" - Deckeln hilft dem Auge nicht, der Takt bleibt.
(Paket mythos-anzeige, Bericht §3b bis §3f; Aufsicht 16.10. 22:10 bis 22:15.)

**Die Lichtsteuerung** (Paket mythos-licht, 19:23 bis 19:51 UTC): der HY310-Baum gibt der Display-Firmware keine PWM-Wörter
(`allwinner,backlight-pwm-info`), Linux' pwm-backlight treibt PWM2 an PB4 mit 25 kHz, Stufe 75; der Hersteller gibt der Firmware
`2 1 25000 1 1 100` (`panel_config.ini`). Ein Test-FIT (Kernel und Baum aus dem FIT der Box, nur die sechs Wörter am `hdmi-rx`-Knoten
und pwm-backlight `disabled`): die Firmware nimmt die Wörter (Journal `backlight PWM: channel 2 polarity 1 freq 25000 vs_lock 1 min 1
max 100`, auch nach dem Aufwachen erneut), **lässt den PWM-Block aber aus** (PER, PCGR, PCCR, PWM2 alle 0) und **PB4 abgeschaltet**
(mux 15), vor und nach `Thal_Vp_SetBacklightLevel` 100/50/100; Stufe 50 und 100 geben dasselbe Licht (Kamera 188,6 / 188,6); die Lampe
ist ohne jede PWM so hell wie mit 75 % (Ring 105,6 gegen 104,5); die Rechenstöße heben das Licht weiter um +1,14 % (vorher +0,93 % am
Ring, +1,20 % am Client); nach einem RTC-Standby (`wake rtc`, 74,8 s) alles identisch (188,6 / 188,8; +1,17 %; Ring 0 Ereignisse). Marco
nach einem Kaltstart auf dem Test-FIT: "selbst kalt flackert es auf dem Grau minimal". Rückbau auf das FIT davor, kein Patch.

**Was das heißt:** eine elektrische Kopplung zwischen dem Strom des SoC und dem LED-Licht (mehr Strom = heller, etwa 1 % je Rechenstoß,
Zeitkonstante 0,1 bis 0,3 s), in der Hardware (Versorgung oder Masse des LED-Boosts gegen den VDD_CPU-Wandler); die Bildkette (DIRTY,
RGB-Kanal, Selektor, Firmware-Zeiger, Regler) ist Schritt für Schritt ausgeschlossen. **Am HY310 erreicht keine PWM die Lampe**: weder
die von Linux noch die der Firmware; PB4 ist nicht mit dem LED-Treiber verdrahtet, die LED läuft mit festem Strom aus dem Boost an PB5.
Was hilft: unnötige Lastsprünge weg (§2), gleichmäßige Last ist unsichtbar; eine Lichtsteuerung, die das kompensieren könnte, gibt es an
diesem Gerät nicht. **Nicht gemessen:** Spannung und LED-Strom mit dem Oszilloskop bei einem Rechenstoß; Marcos "HDMI flackert erst
nach dem Wechsel von einem Client zurück"; die Boot-Spätbilder mit der echten Fernbedienung im Verbindungsaufbau; dasselbe am G-EU
(LCD mit Lampen-PWM der Firmware).

## 4 Die Bedienung beim Start: Launcher, "Starting X...", Firefox, Kodis Ende, Schriftgröße (H Bedienung, 16.10. 17:42 bis 18:46 UTC)

| Prüfung | Ergebnis |
|---|---|
| Launcher beim Start (`on_start = launcher`), vier Warmstarts | öffnet **10,6 bis 10,9 s** nach dem Boot, "HDMI input" gewählt, Kamera sieht ihn; ohne Signal nur im Rennen gemessen (Signal kam 0,2 s nach der Seite: die Seite blieb, deckend über Schwarz) |
| "Starting X..." (die Seite bleibt bis zum ersten Bild des Clients) | Kodi aus HDMI 4,74 bis 4,85 s; Desktop aus HDMI 1,20 bis 1,23 s; Browser aus HDMI 6,34 bis 6,38 s; aus Kodi je plus etwa 3 s (Kodis Ende); die Wand in keiner Zelle schwarz |
| Firefox-Start | die 9 bis 13 s der Abnahme waren Firefox' Notweg: nach jeder kurzen Sitzung (ein Moduswechsel beendet es nach Sekunden) stand die Marke `.startup-incomplete`, und Firefox baute seine Startcaches neu (Hauptthread 8 s bei 85 bis 100 % eines Kerns, keine Platte, kein Speicher). Vier Pref-Varianten änderten nichts (8,91 bis 8,97 s). Mit `ExecStopPost`, das die Marke nach einem gewollten Stopp entfernt: Fenster nach **5,59 bis 5,60 s** statt 8,24 bis 8,68 s. Die erste Sitzung nach einer Installation muss einmal etwa 35 s laufen (Firefox entfernt die Marke erst dann); der erste Start dauert etwa 11 s |
| Kodis Ende | `Application.Quit` bis Prozess weg 3,09 / 2,79 s; davon Event-Server 0,81 s, WS-Discovery-Listener 0,86 s, Skin 0,49 s. Mit `services.wsdiscovery = false` in den Start-Einstellungen **1,88 / 2,29 s** (Preis: Kodi listet SMB-Rechner nicht mehr von selbst); der Event-Server trägt den JSON-RPC-Server und bleibt |
| Schriftgröße an der Wand (Kamera) | Firefox-Faktor 1,5: 16-px-Text klein und weich; **2,0**: 16 px gut lesbar, 24 px klar (die Seite wird für 960 x 540 CSS-Pixel gesetzt); 2,5: 768 x 432, viele Seiten im Handy-Layout. Gewählt 2,0, foot 24 pt, labwc 20 pt |
| Desktop endet mit seinem Terminal (`labwc -S foot`, Autostart leer) | Shell beendet -> Unit inaktiv nach 0,2 und 0,5 s, der HDMI-Ring nach 2,25 und 2,26 s (zwei Läufe) |
| Gate `abnahme.sh -n 2 -S hdmi,kodi` mit direkten Wechseln (`systemctl start --no-block`, ohne Launcher) | **61 von 62**: 30 Launcher-Wechsel, 7 von 8 direkte (die sechs Client-Client-Richtungen alle mit Bild - die Korrektur aus §1 hält ohne das Neuzeichnen der Seite), 12 Settings, 2 Standbys (`wecker OK`, `wake rtc`), 4 Ruhe-Zellen; die eine Zelle Kodi -> Desktop direkt 5,32 s gegen die Grenze 5 s (Kodis Ende), Bild gut |

(Paket H Bedienung, Bericht §1 bis §7.) Nicht gemessen: ein Start ohne Signal über längere Zeit, ein Kaltstart, die echte
Fernbedienung, ob Firefox' Caches von einem Abbild aufs nächste gelten, Kodis Ende unter 5 s mit der Einstellung (die Box trug Marcos
guisettings).

## 5 Die RTC am 24-MHz-Quarz (standby-wecker, Patch `0320`, 16.10. 16:53 bis 19:21 UTC)

**Anlass:** in der Abnahme des Vormittags schlief die Box aus Kodi ohne Wecker (Kernel: `standby 2: net none, no RTC alarm`), obwohl
`rtcwake -m no -s 90` zehn Sekunden vorher Erfolg gemeldet hatte, und kam erst mit der Powertaste zurück. **Gemessen (nur lesend):** die
RTC des HY310 lief auf dem internen RC-Oszillator **26 % zu langsam** - 190 s Systemzeit waren 140 RTC-Sekunden, eine RTC-Sekunde =
1,357 s (08.10. unter dem crust-Testabbild 1,071 s, `doku/170`; nicht geklärt, ob Kernel oder Messaufbau). Der Kernel (CONFIG_RTC_SYSTOHC)
stellt die RTC alle elf Minuten auf die Systemzeit, solange NTP synchron ist, hier ein Sprung von etwa 174 s nach vorn (beobachtet +132 s
zwischen zwei Lesungen); beim Stellen löst der RTC-Kern jeden Wecker auf, dessen Zeit damit vergangen ist (`rtc_set_time` ->
`rtc_timer_do_work`), also jeden unter 174 s. Am Gerät gezeigt: Wecker 60 s gesetzt, RTC um 70 s vorgestellt -> `wakealarm` leer;
um 5 s -> der Wecker bleibt. **Wurzel** (Stock-Vergleich am HY350, derselben SoC, Hersteller-Kernel 5.4.99, adb nur lesend): dort läuft
die RTC exakt (122 s = 122 RTC-Sekunden), ihr 32-kHz-Takt kommt aus dem 24-MHz-Quarz (`dcxo24M-div32k`, LOSC_CTRL 0x4002), der RC-Pfad
ist ungenutzt; unser Treiber (H6-Taktpfad, Patch `0031`) ließ sie am 16-MHz-RC ohne Kalibrierung.

**Patch `0320`:** eigene Taktdaten für den H713; `sun6i_rtc_clk_init` setzt zuerst das Gate des 24-MHz-Teilers (LOSC_OUT_GATING Bit 16,
wie mainline beim H616) und dann LOSC_CTRL auf den Stock-Wert (Auto-Switch an, Quelle DCXO). Die erste Fassung (nur der Mux) **hielt
die RTC an** - am Gerät gesehen (`since_epoch` 90 s eingefroren), sofort zurückgestellt, verworfen. Die zweite am Gerät vor dem Deploy
per Register geprobt: Rate **1,000** (60 s = 60 RTC-Sekunden). Deploy des FIT (Kernel sonst gleich), Warmstart: LOSC_CTRL 0x4002,
Rate **1,000** (90 s = 90 RTC-Sekunden), `hwclock` gleich `date`; zwei RTC-Standbys aus HDMI und aus Kodi mit dem abgesicherten
`abnahme.sh` (es stellt die RTC vor dem `rtcwake` auf die Systemzeit und liest `wakealarm` zurück): `wecker OK in 91 s`, Rückstand 0 s,
Kernel `RTC alarm in 89798 ms` und `85815 ms`, beide `wake rtc`, Bild und Kodi zurück; IR-Fernbedienung dekodiert (sunxi-ir läuft am
24-MHz-Teiler, unberührt). Nebenwirkung: die `osc32k`-Verbraucher im Baum laufen nun mit 32,8 statt 24,2 kHz, was ihr Nennwert ist.
(Paket standby-wecker, Bericht §2 bis §6a.) Nicht gemessen: der G-EU (derselbe RTC-Block, derselbe Kernel, kein 32-kHz-Quarz im Baum).

## 6 Fokus-Randbild und Bluetooth (fokus-bt, 16.10. 20:08 bis 20:50 UTC)

**Randbild:** Marco fuhr den Fokus nach unten bis zum Anschlag und sah das Symbol für den oberen Rand (Pfeil oben mit Strich darüber);
im Journal waren alle 14 Drücke als `focus up ... at the edge` angekommen (nur IR, Bluetooth war nicht verbunden). Auf seine Vorgabe
zeigt h713-keys am Anschlag das Rand-Bild der anderen Richtung; Tasten, Keymaps und die Pfeile beim Fahren sind unverändert. Gemessen:
15 Drücke am oberen Rand je `focus up 20: at the edge, shown as the down edge`, am unteren Rand `focus down 20: at the edge, shown as
the up edge`; Wandfoto der Box-Kamera: am unteren Rand der obere Pfeil rot; Host-Puffer alle vier Zeilen. **Kein Wurzelfix** - warum die
Richtung verdreht gemeldet wird, ist nicht geklärt. **Nebenbefund, offen:** am unteren Rand bleibt der Motor OUTSIDE (zweimal: Schritt
-386 und -6, `raw 0`, beide Kanten 0), der Treiber fährt nicht zurück in den Bereich, danach sind beide Richtungen bis zum Warmstart
gesperrt; am oberen Rand rastet die Kante ein. Ob IR und Bluetooth die Fokustasten gleich zuordnen, ist nicht gemessen. (Paket fokus-bt,
Bericht §1.)

**Bluetooth:** nach jedem Neustart blieb die Fernbedienung unverbunden (`Connected: no`) und sendete IR. Gemessen ohne Taste: bluez lädt
den Bund, der Controller sucht dauernd passiv mit Accept-List, die Fernbedienung muss nur anzeigen. Die wahrscheinliche Wurzel: der Bund
der Box stammt vom 11.10. und wurde zweimal aus Sicherungen zurückgespielt, die Fernbedienung wurde am 11.10. am G-EU neu gekoppelt -
sie merkt sich eine Box; in Marcos Boot-Journal `Connection successful` und 1,5 s später `Connected: no` (ein Link, dessen
Verschlüsselung mit dem alten Schlüssel scheitert; der Code `PIN or Key Missing` selbst ist nicht mitgeschnitten). Der Fehler im
Werkzeug: `h713-remote-pair watch` koppelte nur, wenn kein Bund existiert; die Kopplungsbitte der Fernbedienung (Maus- oder
Mikrofontaste, IR-Code 0x66) blieb ohne Antwort, und auch LINKS+RECHTS allein hilft mit vorhandenem Bund nicht. **Fix gebaut, auf dem
Testgerät, nicht gemessen, nicht im Zweig:** `watch` liest den IR-Scancode 0x0266 über `/dev/lirc0`, vergisst dann den Bund der nicht
verbundenen Fernbedienung und koppelt neu (Hosttests 26 von 26; der Nachweis braucht die echte Fernbedienung). Nebenmessung: ein
LE-Suchfenster von 96/96 (bluez-Vorgabe) statt 16/96 kostet das WLAN der Box **40 % Pakete** (450 von 1135, Median 200 ms) - das schmale
Fenster bleibt; `systemctl restart bluetooth` lässt hci0 am AIC8800 aus (`Opcode 0x1003 failed`), nur ein Warmstart holt es zurück.
(Paket fokus-bt, Bericht §2.)

## 7 Das Endabbild rend4 (16.10. abends) und die Installation von rend3

rend3 (Zweig 693e9ec) wurde am 16.10. um 09:22 UTC auf dem HY310 installiert (FEL, `h713-install`, Probelauf, Schreiben 5 min, Secure
Storage unverändert, eigene Dateien zurückgespielt): FIT, uname und 622 Pakete wie gebaut, 0 gescheiterte Einheiten, Hostschlüssel
gleich, Kodi als `h713-kodi` (StateDirectory übernimmt die Home beim ersten Start), `CanSuspend` true, Firefox ESR 153.5. Die Fehler
F1 bis F6 (§1, §4) fand Marco an diesem Abbild; sie sind seitdem per Einzel-Deploy behoben und im Zweig. rend4 (Zweig a70bd6f):
`release/build-all.sh --board hy310 --version v0.0-rend4 --profile media,desktop --standby` aus leeren Bauverzeichnissen, Exit 0 nach
27 min 52 s, Stempel `reproducible: yes`, Serie 342 Patches, Rootfs aus `trixie`, `trixie-updates`, `trixie-security`, 622 Pakete, Baum
1235 MiB, System-Abbild 2177 MiB (2-GiB-Rootfs mit 795 MiB frei), alle Tore grün. Gegen den Stand der Box: 22 von 33 Zeilen gleich, 9
anders (8 gewollt - Gate, Marcos Konfiguration und guisettings, zehn neuere Sicherheitsstände, Testbestand, der ältere
`h713-remote-pair` -, 1 echt: `tv.conf` in der Abnahmefassung mit gleicher Wirkung), 2 nicht verglichen. **rend4 ist nicht gebootet.**
(Paket R-release, Bericht Nachtrag 5, Vergleich.)

## 8 Nicht gemessen

* Alles am HY300PRO-G-EU: §1 bis §6, dazu alles aus `doku/211` und `doku/212`.
* Das Abbild rend4 am Gerät (Installation, erster Start, Launcher beim Start, erste Firefox-Sitzung, Fernbedienung).
* §1: der Bypass-Fall der Übergabe, ein fremdes GRAPHICS -> TEXT, die Boot-Spätbilder. §3: Spannung und LED-Strom mit dem Oszilloskop,
  HDMI nach dem Wechsel von einem Client zurück, Boot-Spätbilder mit der echten Fernbedienung. §4: Start ohne Signal über längere Zeit,
  Kaltstart, echte Fernbedienung, Caches über Abbilder hinweg. §5: nichts offen am HY310; der Hersteller-Weg am G-EU. §6: der BT-Fix
  mit der echten Fernbedienung, der Verschlüsselungsfehler selbst, die Fokusrichtung über Bluetooth, der Motor am unteren Rand.
