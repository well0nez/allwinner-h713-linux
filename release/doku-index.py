#!/usr/bin/env python3
"""doku-index.py -- den Index des Arbeitsjournals erzeugen (doku/INDEX.md).

    release/doku-index.py [--pruefen]

Warum generiert und nicht gepflegt: ein handgeschriebener Index ueber 200 Dateien ist
nach zwei Wochen falsch, und ein falscher Index ist schlimmer als keiner. Hier steht
nichts, was nicht aus den Dateien selbst kommt.

Drei Abschnitte, und der erste ist der eigentliche Zweck:

  1. Worauf die Leserdokumentation ruht. `docs/` und die Wurzeldateien zitieren das
     Journal 400-mal; das wird umgedreht. Wer wissen will, woher eine Aussage in
     `docs/subsystems/arisc.md` kommt, findet hier die Eintraege dazu - und umgekehrt
     sieht man einem Journaleintrag an, ob eine Doku auf ihm aufbaut.
  2. Alle Eintraege: Nummer, Art, Datum, Titel.
  3. Eintraege, die niemand zitiert. Kein Vorwurf - ein Journal darf Material enthalten,
     das nie in eine Doku geflossen ist. Aber es ist die Liste, auf der man nachsieht,
     wenn man etwas konsolidieren oder als ueberholt markieren will.

--pruefen schreibt nichts und endet mit 1, wenn INDEX.md nicht dem Stand entspricht
(fuer eine Pruefung vor dem Push).
"""

import os
import re
import sys

WURZEL = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
JOURNAL = "doku"
# Wo nach Zitaten gesucht wird: die Leserdokumentation und die Wurzeltexte, nicht das
# Journal selbst - Querverweise im Journal sind seine eigene Sache.
ZITIERER = ["docs", "boards", "installer", "release", "rootfs", "userspace", "mainline/docs"]
WURZELTEXTE = ["README.md", "STATUS.md", "ROADMAP.md", "BUILDING.md", "FLASHING.md",
               "RELEASES.md", "PROVENANCE.md"]

ART = [
    (re.compile(r"handoff"), "Handoff"),
    (re.compile(r"^nachtlog/"), "Nachtlog"),
    (re.compile(r"plan"), "Plan"),
    (re.compile(r"abgleich"), "Abgleich"),
    (re.compile(r"protokoll|verifikation|grosstest"), "Protokoll"),
]
RX_DATUM = re.compile(r"(20\d{2})(\d{2})(\d{2})")
# "doku/128", "doku/nachtlog/S49-...", "doku/128a"
RX_ZITAT = re.compile(r"doku/(nachtlog/[A-Za-z0-9-]+|[0-9]+[a-z]?)")


def art_von(rel):
    for rx, name in ART:
        if rx.search(rel):
            return name
    return "Analyse"


def titel_von(pfad):
    try:
        with open(pfad, encoding="utf-8") as f:
            for zeile in f:
                z = zeile.strip()
                if z.startswith("#"):
                    return z.lstrip("#").strip()
                if z and not z.startswith(">"):
                    return z[:90]
    except OSError:
        pass
    return "(ohne Titel)"


def datum_von(rel, pfad):
    m = RX_DATUM.search(rel)
    if m:
        return "%s-%s-%s" % m.groups()
    return ""


def schluessel(rel):
    """Der Name, unter dem andere Dateien diesen Eintrag zitieren."""
    base = os.path.basename(rel)
    if rel.startswith("nachtlog/"):
        return "nachtlog/" + re.split(r"\.md$", base)[0]
    m = re.match(r"([0-9]+[a-z]?)-", base)
    return m.group(1) if m else None


def journal_dateien():
    out = []
    for d, _, files in os.walk(os.path.join(WURZEL, JOURNAL)):
        for f in sorted(files):
            if not f.endswith(".md") or f in ("INDEX.md", "README.md"):
                continue
            p = os.path.join(d, f)
            out.append((os.path.relpath(p, os.path.join(WURZEL, JOURNAL)), p))
    return sorted(out)


def zitate():
    """{Journalschluessel: {zitierende Datei, ...}}"""
    treffer = {}
    pfade = [os.path.join(WURZEL, x) for x in ZITIERER]
    pfade += [os.path.join(WURZEL, x) for x in WURZELTEXTE]
    for pfad in pfade:
        dateien = []
        if os.path.isfile(pfad):
            dateien = [pfad]
        else:
            for d, dirs, files in os.walk(pfad):
                dirs[:] = [x for x in dirs if x not in (".git", "__pycache__", "external")]
                dateien += [os.path.join(d, f) for f in files
                            if os.path.splitext(f)[1] in (".md", ".py", ".sh", ".c", ".h", ".txt")]
        for f in dateien:
            try:
                s = open(f, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for m in RX_ZITAT.finditer(s):
                treffer.setdefault(m.group(1), set()).add(os.path.relpath(f, WURZEL))
    return treffer


def bauen():
    dateien = journal_dateien()
    zit = zitate()
    zeilen = []
    zeilen.append("# Index des Arbeitsjournals")
    zeilen.append("")
    zeilen.append("**Erzeugt von `release/doku-index.py` - nicht von Hand aendern.**")
    zeilen.append("")
    zeilen.append("Das Journal ist die Beweisgrundlage der Dokumentation, kein Handbuch; "
                  "was es ist und wie man es liest, steht in [README.md](README.md). "
                  "Dieser Index macht es auffindbar, ohne es umzuschreiben.")
    zeilen.append("")

    # 1. Worauf die Leserdokumentation ruht
    zeilen.append("## 1 Worauf die Leserdokumentation ruht")
    zeilen.append("")
    zeilen.append("Umgedreht aus den Zitaten in `docs/` und den Wurzeltexten: wer wissen will, "
                  "woher eine Aussage kommt, findet hier den Eintrag dazu.")
    zeilen.append("")
    nach_doku = {}
    for key, wer in zit.items():
        for w in wer:
            nach_doku.setdefault(w, set()).add(key)
    zeilen.append("| Dokument | ruht auf |")
    zeilen.append("|---|---|")
    for w in sorted(nach_doku):
        keys = sorted(nach_doku[w], key=lambda k: (not k[0].isdigit(), k))
        zeilen.append("| `%s` | %s |" % (w, ", ".join("`doku/%s`" % k for k in keys)))
    zeilen.append("")

    # 2. Alle Eintraege
    zeilen.append("## 2 Alle Eintraege")
    zeilen.append("")
    zeilen.append("| Eintrag | Art | Datum | Titel | zitiert von |")
    zeilen.append("|---|---|---|---|---|")
    ohne = []
    for rel, pfad in dateien:
        k = schluessel(rel)
        wer = sorted(zit.get(k, ())) if k else []
        if not wer:
            ohne.append((rel, k))
        zeilen.append("| [`%s`](%s) | %s | %s | %s | %s |" % (
            rel, rel.replace(" ", "%20"), art_von(rel), datum_von(rel, pfad),
            titel_von(pfad).replace("|", "\\|"),
            ("%d" % len(wer)) if wer else "-"))
    zeilen.append("")

    # 3. Nicht zitiert
    zeilen.append("## 3 Eintraege, die niemand zitiert")
    zeilen.append("")
    zeilen.append("%d von %d. Das ist kein Vorwurf - ein Journal darf Material tragen, das "
                  "nie in eine Doku geflossen ist. Es ist die Liste, auf die man schaut, wenn "
                  "man etwas als ueberholt markieren will." % (len(ohne), len(dateien)))
    zeilen.append("")
    for rel, _ in ohne:
        zeilen.append("* `%s`" % rel)
    zeilen.append("")
    return "\n".join(zeilen) + "\n"


def main(argv):
    ziel = os.path.join(WURZEL, JOURNAL, "INDEX.md")
    neu = bauen()
    if "--pruefen" in argv:
        alt = open(ziel, encoding="utf-8").read() if os.path.exists(ziel) else ""
        if alt != neu:
            print("doku/INDEX.md ist nicht auf dem Stand -- release/doku-index.py laufen lassen")
            return 1
        print("doku/INDEX.md ist auf dem Stand")
        return 0
    open(ziel, "w", encoding="utf-8").write(neu)
    print("doku/INDEX.md geschrieben (%d Zeilen)" % len(neu.splitlines()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
