# Plan 119 — Fremde Geräte (HY300 Pro) und die Installer-Fehler aus Issue #1

Ausgelöst durch den ersten fremden Nutzer (Issue #1, HY300 Pro). Zwei getrennte Dinge, hier zusammen, weil das
eine das andere aufgedeckt hat: **(A)** wie man ein Gerät unterstützt, das wir nicht haben, und **(B)** vier
Installer-Fehler, die der Lauf belegt hat. B ist heute machbar, A ist die grundsätzliche Frage.

## A. Wie unterstützt man ein Gerät, das man nicht besitzt?

Ehrlich: **gar nicht bis zur Auslieferung**, ohne dass am Ende jemand mit dem Gerät testet. Der Weg dazwischen
ist trotzdem klar, in drei Stufen mit fallendem Sicherheitsniveau:

1. **Statisch, aus seinem Vollabzug — kostet ihn nichts, uns kein Risiko.**
   - `h713-extract` bekommt ein Profil `hy300pro`: die Referenz-Hashes aus *seiner* Extraktion (Vendor-Datei-Hashes
     sind nicht geheim — der Nutzer darf sie posten, den Abzug selbst nie). Damit erkennt das Werkzeug das Gerät
     beim nächsten Mal und meldet nicht mehr „unbekannt".
   - `hy310-install` bekommt einen Erkennungseintrag für den Fingerprint `ADT-3/…/6245789` (Android 10), damit die
     Firmware nicht mehr „unbekannt" heißt.
   - **Das allein gibt noch keinen Schreibweg frei.** Erkennen ≠ dürfen.
2. **Ein Abbild bauen — aus seinen eigenen Bausteinen.**
   - Board-Unterschiede aus seinem Log: DDR3 **636 MHz** (wir 792), Projekt-ID **0x34** (wir 0x30), andere
     `display.bin`-Revision, anderes Partitionslayout, Android 10. Ein HY300-Pro-Abbild braucht: ein U-Boot mit
     636-MHz-DRAM (oder Beleg, dass 792 auf seinem RAM hält — riskant), `h713_project=0x34`, einen DTS-Abgleich
     (Lüfter, Motor `phase-num 4 step-num 8`, Taste; das Panel kommt über die TSE aus seinem Abzug).
   - `hy310-mkimage` müsste das Layout aus **seiner** GPT nehmen, nicht aus unseren Konstanten (hängt an Fix B2).
3. **Testen — nur er kann das, und nur mit Rückweg.**
   - Vollabzug hat er (verifiziert). Erst FEL-Boot des neuen U-Boot beobachten (kein Schreiben), dann `--dry-run`,
     dann echtes Schreiben, jederzeit `--restore` auf seinen Abzug.

**Vorschlag zur Politik:** Fremde Geräte laufen als **community-getragene Profile**. Wir liefern das Gerüst
(Extraktor-Profil, Erkennung, `mkimage` aus GPT) und die Anleitung; das Board-Bring-up und der Hardware-Test
gehören dem, der das Gerät hat. Ein Gerät kommt erst dann in die „unterstützt"-Liste, wenn sein Besitzer einen
grünen Durchlauf gemeldet hat. Alles andere wäre Raten auf fremder Hardware — genau das, was die Erkennung
verhindern soll.

Für Issue #1 heißt das konkret: die Antwort (Entwurf in `analyse/issues/issue-1-antwort-entwurf.md`) sagt heute
nur „geht nicht". Besser: „geht nicht mit v0.5-beta, aber so könnten **wir gemeinsam** ein HY300-Pro-Profil
machen — Extraktor-Profil aus deinen Hashes, dann ein Test-Abbild, das nur du flashst." Siehe §C.

## B. Die vier Installer-Fehler aus dem Log

| # | Fehler | Sicher offline zu fixen? |
|---|---|---|
| B1 | FEL-Prüfung vergleicht den SoC-**Namen** `(H713)` statt der ID `0x1860`; distro-`sunxi-fel` schreibt `(unknown)` → falsches „kein H713" | **ja** |
| B2 | kleiner Abzug nimmt **HY310-Konstanten** für `private`/`reserve0` statt der GPT-Offsets; auf dem HY300 Pro wurde die falsche Region gelesen und als `reserve0` beschriftet | teilweise — die Logik ja, die Richtigkeit braucht ein Gerät zum Gegenprüfen |
| B3 | `--nur-abzug`/`--dry-run` bei unbekannter Firmware meldet „FEHLER … kein Weiter" und macht dann weiter | **ja** |
| B4 | On-Screen-Hash von `secure-storage`/`private` — der Nutzer hat ihn öffentlich gepostet | **ja** |

**Heute gefixt: B1, B3, B4** (kein Gerät nötig, offline gegen die Logzeilen prüfbar).
**B2 als eigener Schritt**, weil ein falsch beschrifteter Abzug ein trügerisches Sicherheitsgefühl gibt und die
Korrektheit gegen ein echtes Gerät geprüft werden muss; hängt ohnehin an A2 (`mkimage` aus GPT).

### B1 — FEL an der SoC-ID prüfen
`fel_da()` liefert die AWUSBFEX-Zeile; `soc=00001860(<name>)`. Der Name kommt aus der `sunxi-fel`-Tabelle und
fehlt bei alten Ständen. Prüfen auf **`00001860`** (H713-SoC-ID), nicht auf den Namen. Bei fehlendem Namen ein
Hinweis: „nimm das `sunxi-fel` aus dem Release". Ein echter Fremd-SoC (andere ID) wird weiter abgelehnt.

### B3 — bei „nur lesen" ist unbekannt kein Abbruch
`geraet_melden()` gibt „darf geschrieben werden?" zurück, und `_arbeiten()` bricht nur ab, wenn `schreiben`.
Das ist logisch schon richtig — falsch ist die **Wortwahl**: „FEHLER … kein Weiter" bei einem Lauf, der gar
nicht schreibt. Bei `nur_abzug`/`dry_run` stattdessen: „Unbekannte Firmware — es wird nur gelesen, nichts
geschrieben. Bitte die Kennungszeile melden." Kein `fehler()`, kein Widerspruch.

### B4 — kein Secure-Storage-Hash auf den Schirm
`abzug_klein()` druckt je Region `h[:16]+"…"`. Für die geheimen Regionen (`secure-storage`, `private`) auf dem
Bildschirm **keinen Hash** — nur Größe und „gesichert". Im Manifest (auf der Platte des Nutzers) bleibt der Hash
für die Verifikation; posten wird ihn dann niemand versehentlich.

## C. Reihenfolge

- ☑ B1, B3, B4 gefixt in `analyse/release/arbeit/r0-fel/hy310-install.py`, offline geprüft: B1 akzeptiert
  distro-`(unknown)` (ID 0x1860) mit Hinweis und lehnt fremde SoC ab; B3 meldet bei `--nur-abzug` eine Warnung
  statt „FEHLER … kein Weiter"; B4 zeigt für `secure-storage`/`private` „gesichert (Hash im Manifest)" statt des
  Hashes. Gepusht nach `main` als `96e2188`.
- ☑ Antwort an #1 gepostet (13.09.): Kooperationsangebot in drei Stufen, ausdrückliches „nicht flashen", Bitte,
  den Abzug nie hochzuladen. https://github.com/well0nez/allwinner-h713-linux/issues/1#issuecomment-5655638816
- ☐ B2 + A2: `mkimage`/`abzug_klein` lesen Layout aus der GPT. Braucht Gegenprobe an unserem Gerät (unser Abzug
  muss byteidentisch bleiben) und danach an seinem Abzug (nur lesen).
- ☐ `h713-extract`-Profil `hy300pro` aus seinen Hashes.
- ☑ Fixes nach `main` gepusht (kein neues Release nötig; der Installer wird geklont).
