#!/usr/bin/env python3
"""installer-fahren.py -- hy310-install unter einem Pseudo-TTY fahren.

WARUM: hy310-install verlangt vor dem Schreiben ein getipptes JA (Befund S46
B15) und verweigert ohne TTY -- Absicht. Wer den Installer aus einer Sitzung
ohne Terminal startet (Claude, Skript, ssh -T), braucht ein Pseudo-TTY und
jemanden, der das JA an genau dieser Stelle tippt. Das hier ist dieser jemand.
Alles, was der Installer ausgibt, landet im LOG -- die Zusage ist damit
dokumentiert, nicht umgangen.

    setsid nohup sudo python3 installer-fahren.py LOG \
        python3 hy310-install.py --abbild out/h713-hy310-vX.Y.tabelle.json \
        --vendor PFAD/zur/h713-extract-Ausgabe \
        --authorized-key ~/.ssh/id_ed25519.pub \
        --uboot ../mainline/build/out/u-boot-installer.bin \
        --sunxi-fel ../mainline/build/out/sunxi-fel \
        --abzug klein --sicherung ../../hy310-sicherung-DATUM \
        > fahrer.out 2>&1 < /dev/null &

    Die Pfade gelten fuer das Repo-Layout (installer/ neben mainline/); beide
    Bausteine legt release/build-all.sh ab (Schritte 2b und 2c). Im alten
    Arbeitsverzeichnis (analyse/release/arbeit/r0-fel) sind es vier Ebenen
    (../../../../mainline/build/out/...).

    ACHTUNG --sunxi-fel: nur ein sunxi-fel MIT S44-Falltuer (Fork-Commit
    269dfa2, Kennung "FEL trap door" in strings) startet U-Boot proper.
    mainline/build/fel/sunxi-fel war das UNGEPATCHTE vom 31.08. (12.09.,
    doku/60 §Abbild v0.8).

Dann in kurzen Schritten ins LOG sehen -- nicht auf das Ende warten
(Geraetebefehle in kurzen Schritten). Der Lauf dauert ~3 min.

AUFNAHME: Ist H713_AUFNAHME=PFAD gesetzt, entstehen zusaetzlich PFAD.typescript
und PFAD.timing im Format von script(1). Abspielen mit
    scriptreplay --timing PFAD.timing PFAD.typescript
und daraus laesst sich ein Video machen (asciinema/agg), ohne den Lauf zu wiederholen.
"""
import os, pty, select, sys, time
log = open(sys.argv[1], "ab", buffering=0); cmd = sys.argv[2:]
pid, fd = pty.fork()
if pid == 0:
    os.execvp(cmd[0], cmd)
puffer = b""; geantwortet = False; t0 = time.time(); st = None
aufn = os.environ.get("H713_AUFNAHME")
ts = open(aufn + ".typescript", "wb", buffering=0) if aufn else None
tm = open(aufn + ".timing", "w", buffering=1) if aufn else None
t_letzt = t0
def mitschnitt(daten):
    global t_letzt
    if not ts: return
    jetzt = time.time(); tm.write("%.6f %d\n" % (jetzt - t_letzt, len(daten))); t_letzt = jetzt
    ts.write(daten)
while True:
    r, _, _ = select.select([fd], [], [], 1.0)
    if r:
        try: d = os.read(fd, 4096)
        except OSError: break
        if not d: break
        log.write(d); mitschnitt(d); puffer = (puffer + d)[-2000:]
        if not geantwortet and b"JA eintippen" in puffer:
            time.sleep(0.5); os.write(fd, b"ja\n"); geantwortet = True; mitschnitt(b"ja\r\n")
            log.write(b"\n[fahrer] JA gesendet nach %.0f s\n" % (time.time() - t0))
    else:
        wpid, st = os.waitpid(pid, os.WNOHANG)
        if wpid: break
if st is None:
    _, st = os.waitpid(pid, 0)
rc = os.waitstatus_to_exitcode(st)
log.write(b"\n[fahrer] Ende rc=%d nach %.0f s\n" % (rc, time.time() - t0)); log.close()
if ts: ts.close(); tm.close()
sys.exit(rc if rc >= 0 else 1)
