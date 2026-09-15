# H713 / HY260 - Arbeitsbereich

> **Hinweis (12.09.2026):** Diese Seite beschreibt das **Arbeitsverzeichnis**
> `/opt/Projekte/h713` - also auch das, was nie ins Repo geht (`re/`, `tftp/`,
> `patches-snapshots/`, `legacy/`). Die Wurzel-`README.md` ist seit P5 die
> **englische Seite des Repos**; das Layout des Repos steht in
> [`116-plan-release-repo.md`](116-plan-release-repo.md) §3.

Angelegt 2026-08-31.

```
/opt/Projekte/h713/
├── doku/               Projektdokumentation - Einstieg doku/00-STATUS.md
├── mainline/           cstenger/allwinner-h713-mainline - der aktive Hauptbaum;
│                       patches/kernel/series = unsere Kernel-Serie, build/ = Bäume und Ausgaben
├── userspace/          h713-tv (HDMI-Eingang als Dienst + Steuerkanal), h713-pq (PQ-Rechner)
├── analyse/            Messwerkzeuge und Rohdaten je Thema (analyse/README.md)
├── tools/              UART-, Disassembler- und Parser-Skripte (tools/README.md)
├── tftp/               Netboot-Kernelabbild + die zwei guten Stände; alt/ = abgelöste
├── patches-snapshots/  Sicherungen der Patch-Serie vor jeder Änderung
├── re/                 das gesamte RE-Material, dedupliziert und verifiziert
├── legacy/             well0nez/allwinner-h713-linux - unser altes Repo, nur Referenz
├── uboot-h713/         unsere U-Boot-Änderungen als Patch, außerhalb des Submoduls
└── agenten/            abgegrenzte Nebenprojekte (Fokusmotor)
```

**Stand 08.09.2026:** der HDMI-Eingang läuft vollständig aus Kernel und Userspace (Bild, Umschalten,
Auflösungen, Bildregler, Presets, Einpassung, Gamma). Bedienung: `doku/50-befehle.md`, Abschnitt Betrieb.

**Einstieg: [doku/00-STATUS.md](00-STATUS.md)** - aktueller Stand, was
läuft, was offen ist. Die Datei hier beschreibt nur die Bäume und die
Submodul-Fallen.

## `mainline/` - der Hauptbaum

Klon von <https://github.com/cstenger/allwinner-h713-mainline>. Offene
Boot-Chain (U-Boot SPL → TF-A BL31 → U-Boot → Linux) plus arm64 Debian 13 auf
Mainline 6.18.38 LTS. Seine Kernel-Patches **0001-0022 sind unsere**, von ihm
mit Namensnennung übernommen (siehe sein `PROVENANCE.md`).

Bauen: `build/build.sh all`. Board-Vorgabe `BOARD=ddr3` (Bench) oder `lpddr3`.

### ⚠️ Ein Submodul-Pin ist tot: `sunxi-tools`

`git clone --recurse-submodules` bricht ab mit:

```
upload-pack: not our ref 72b4001954a38aa5e3d566dfd4b71e337e5c96b0
fatal: "fetch" in Submodul-Pfad 'external/sunxi-tools' ausgeführt, aber
       enthielt nicht 72b4001954a3…
```

| Submodul | gepinnt | Zustand |
|---|---|---|
| `external/u-boot` | `7b178056c329` | ✓ Vorfahr von `origin/h713`, 07.08. |
| `external/arm-trusted-firmware` | `47ee829f745f` | ✓ = `refs/heads/sun50i-h713`, 14.07. |
| `external/sunxi-tools` | `72b4001954a3` | ✗ **existiert im Fork nicht** → hier auf `origin/h713` = `5d56b77` (18.07.) |

Der Abbruch an sunxi-tools verhindert, dass die übrigen Submodule ausgecheckt
werden - es sieht dadurch so aus, als wären mehrere kaputt. Sind sie nicht.
Nach `git submodule update --checkout external/u-boot external/arm-trusted-firmware`
stehen beide auf ihrem Pin.

Nur `external/sunxi-tools` weicht bewusst ab (`git submodule status` zeigt `+`).
Sein Pin lässt sich nicht wiederherstellen; `.gitmodules` nennt `branch = h713`,
also ist dessen Kopf die naheliegende Ersatzwahl.

Befund für ihn: sein Repo ist derzeit von Dritten nicht klonbar, wegen genau
eines Commits.

**Blockiert nichts.** `build/build.sh` referenziert sunxi-tools nirgends; der
Bau von BL31, U-Boot, Kernel und Images läuft ohne. Gebraucht wird es nur für
FEL, also in `tools/boot-switch.sh`, `docs/flash.md` und
`docs/reference/h713-fel-notes.md` - und damit erst, wenn Hardware im Spiel ist.
Dann allerdings zwingend, denn FEL ist der Rettungsanker: bevor irgendwas auf
den HY310 geflasht wird, muss FEL-Recovery auf genau diesem Board nachgewiesen
sein. Zu dem Zeitpunkt gehört der Stand von `external/sunxi-tools` verifiziert.

**Prüfmethode, falls das wieder auftritt:** `git ls-remote` listet nur
Ref-*Köpfe*. Ein gepinnter Commit muss keiner sein, sondern nur von einem Ref
aus erreichbar. Richtig ist: alle Refs holen, dann `git cat-file -e <sha>` und
`git branch -r --contains <sha>`.

### Falls je geforkt wird

Die Submodul-URLs sind **relativ** (`url = ../u-boot.git`) und lösen gegen die
Origin-URL des Superprojekts auf. Ein Fork nach `well0nez/` würde folglich
`well0nez/u-boot.git` suchen und nichts finden. Dann entweder alle vier Repos
forken oder die URLs lokal überschreiben:

```
git config submodule.external/u-boot.url https://github.com/cstenger/u-boot.git
```

## `legacy/` - unser Repo

Klon von <https://github.com/well0nez/allwinner-h713-linux>. 32-bit-ARM-Port
auf 6.16.7, Stock-U-Boot mit gepatchtem Env. Entwicklung pausiert (siehe
README dort). Enthält, was `mainline/` nicht hat: `sunxi-mipsloader`,
`msgbox-amp`, den HDMI-RX-DRM-Treiber mit `hy310-hdmird` und den EDID-Notizen,
den funktionierenden Audio-Stack und den `sunxi_ge2d`-Port.

## `re/` - das Material

25.277 Dateien, dedupliziert aus vier Quellen, doppelt verifiziert. Einstieg:
`re/INDEX.md`, Datenbank-Zuordnung in
`re/ida/PAIRING.md`. Die Originale liegen unangetastet
unter `/opt/archive/`.

Wichtig: der aktuelle Wissensstand steht in `re/notes/` (u.a.
`CURRENT-TRUTH.md`, `DEAD-ENDS.md`, `OPEN-LEADS.md`), **nicht** in der
`STATUS.md` von `legacy/` - die ist auf dem Stand vom Mai, die Notizen reichen
bis zum 4. Juli.

## Der nächste sinnvolle Schritt

`cpu-comm` auf arm64. In `mainline/` ist es deaktiviert, weil der Treiber
Host-Kernel-VAs in `u32`-Felder in Shared Memory schreibt - auf arm32 ein
No-op, auf arm64 fällt die obere Hälfte weg. Die Lösung ist die
`Vir2Mid`/`Mid2Vir`-Schicht, die in `legacy/drivers/cpu_comm/cpu_comm_mem.c`
(Zeilen 502-531) bereits implementiert ist: eine „Mid" ist ein 32-bit-Token
relativ zum Shared-Window, kein Host-Zeiger.

Erste Aufgabe ist aber nicht Code, sondern eine Entscheidung pro Fundstelle:
schreibt MIPS das Feld mit, oder läuft nur ARM darüber? Im ersten Fall muss
`Vir2Mid` hin, im zweiten reicht ein breiterer lokaler Typ. Dafür braucht es
die Kenntnis der Stock-`.ko` aus IDA - siehe `re/ida/PAIRING.md`.

`cpu-comm` ist das Tor zu allem, was `mainline/` fehlt: MIPS-Steuerung,
HDMI-RX, PQ, Keystone.
