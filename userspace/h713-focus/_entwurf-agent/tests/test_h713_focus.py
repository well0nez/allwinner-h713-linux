#!/usr/bin/env python3
"""Tests fuer h713-focus -- ohne Gerät, ohne Mechanik, ohne Stromzyklus.

Zwei Ebenen:

* **rein**: zustand.py (Auslegen der Zeile, Sicherheitsregeln) und geraet.py
  (Suche, Schreibsperre, Wortformat) werden direkt geprueft.
* **durchgehend**: ``cli.main(["--sysfs", PFAD, ...])`` laeuft gegen ein echtes
  Verzeichnis, das ``tests/attrappe.py`` mit einem Modell des Treibers fuellt.
  Derselbe Code wie am Gerät, nur ohne Motor.

Aufruf:  python3 tests/test_h713_focus.py
     oder python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]          # userspace/h713-focus
sys.path.insert(0, str(WURZEL))
sys.path.insert(0, str(WURZEL / "tests"))

import attrappe                                        # noqa: E402
from h713_focus import cli, fahren, geraet, zustand  # noqa: E402
from h713_focus.zustand import AB, AUF                 # noqa: E402

#: Die Zeile, die am 12.09.2026 am Gerät stand -- Ruhezustand nach dem
#: Randereignis (analyse/boot/motor-bereichswaechter-20260912.txt).
ZEILE_AM_RAND = "1 up=1 dn=1 num=1 raw=1 act=1 edge_up=0 edge_dn=1 step=-207"
#: Und die Zeile ohne jede Bewegung, direkt nach dem Laden.
ZEILE_RUHE = "1 up=1 dn=1 num=1 raw=1 act=1 edge_up=0 edge_dn=0 step=0"


def _flach(text: str) -> str:
    """Alle Zeilenumbrueche und Einzuege zu einfachen Leerzeichen.

    Die Ausgabe bricht lange Begruendungen um; ein Test soll auf den Wortlaut
    pruefen koennen, ohne die Umbruchbreite mitzupflegen.
    """
    return " ".join(text.split())


def _lauf(argv: list[str]) -> tuple[int, str]:
    """cli.main() aufrufen und stdout einsammeln."""
    puffer = io.StringIO()
    with contextlib.redirect_stdout(puffer):
        rueck = cli.main(argv)
    return rueck, puffer.getvalue()


@contextlib.contextmanager
def _stand(**kwargs):
    """Ein laufendes Attrappen-Verzeichnis mit dem gewuenschten Modell."""
    modell = attrappe.Treibermodell(**kwargs)
    with tempfile.TemporaryDirectory() as d:
        pfad = Path(d) / "motor-ctr"
        with attrappe.Verzeichnis(pfad, modell) as v:
            yield str(pfad), modell, v


# ---------------------------------------------------------------------------
# zustand: die Zeile auslegen
# ---------------------------------------------------------------------------

class TestZeile(unittest.TestCase):
    def test_gemessene_zeile(self):
        g = zustand.lies_grenze(ZEILE_AM_RAND)
        self.assertTrue(g.im_bereich)
        self.assertEqual((g.num, g.raw, g.act), (1, 1, 1))
        self.assertFalse(g.edge_up)
        self.assertTrue(g.edge_dn)
        self.assertEqual(g.step, -207)
        self.assertTrue(g.rohpegel_passt)
        self.assertEqual(g.roh, ZEILE_AM_RAND)

    def test_kante_je_richtung(self):
        g = zustand.lies_grenze(ZEILE_AM_RAND)
        self.assertTrue(g.kante(AB))
        self.assertFalse(g.kante(AUF))

    def test_rohpegel_weg(self):
        g = zustand.lies_grenze(
            "0 up=0 dn=0 num=1 raw=0 act=1 edge_up=0 edge_dn=0 step=-206")
        self.assertFalse(g.im_bereich)
        self.assertIs(g.rohpegel_passt, False)

    def test_ohne_pin(self):
        # Ohne Limiter liefert der Treiber raw=-1, meldet aber "im Bereich".
        g = zustand.lies_grenze(
            "1 up=1 dn=1 num=0 raw=-1 act=1 edge_up=0 edge_dn=0 step=0")
        self.assertTrue(g.im_bereich)
        self.assertIsNone(g.rohpegel_passt)

    def test_unbekannte_felder_bleiben_erhalten(self):
        g = zustand.lies_grenze(ZEILE_RUHE + " neu=42")
        self.assertEqual(g.unbekannt, {"neu": "42"})

    def test_altes_format_ohne_raw_wird_angenommen(self):
        # raw= fehlt (Treiber vor 0154) -- auslegbar, aber nicht fahrbar.
        g = zustand.lies_grenze(
            "1 up=1 dn=1 num=1 act=1 edge_up=0 edge_dn=0 step=0")
        self.assertIsNone(g.raw)
        self.assertIsNone(g.rohpegel_passt)

    def test_stock_zeile_ist_unlesbar(self):
        # Stock gibt nur das erste Feld aus. Daraus laesst sich nichts
        # ableiten, also wird geraten -- nein: es wird abgelehnt.
        with self.assertRaises(zustand.ZeileUnlesbar):
            zustand.lies_grenze("1")

    def test_zeile_vor_0154_ist_unlesbar(self):
        # So sah motor_limit vor Patch 0154 aus: "%d up=%d dn=%d num=%d".
        # Kein Pegel, keine Position, keine Kanten -- unlesbar, nicht halb
        # lesbar.
        with self.assertRaises(zustand.ZeileUnlesbar) as e:
            zustand.lies_grenze("1 up=1 dn=1 num=1")
        self.assertIn("0154", str(e.exception))

    def test_leer_und_muell(self):
        for text in ("", "   ", "nanu up=1"):
            with self.assertRaises(zustand.ZeileUnlesbar):
                zustand.lies_grenze(text)


# ---------------------------------------------------------------------------
# zustand: die Sicherheitsregeln
# ---------------------------------------------------------------------------

class TestRegeln(unittest.TestCase):
    def test_ruhe_erlaubt_beides(self):
        g = zustand.lies_grenze(ZEILE_RUHE)
        self.assertIsNone(zustand.pruefe(g, AUF, 0))
        self.assertIsNone(zustand.pruefe(g, AB, 0))

    def test_kante_sperrt_nur_ihre_richtung(self):
        g = zustand.lies_grenze(ZEILE_AM_RAND)
        self.assertIsNone(zustand.pruefe(g, AUF, 0))       # weg vom Rand: ja
        self.assertIn("edge_dn=1", zustand.pruefe(g, AB, 0))

    def test_ohne_limiter_gesperrt(self):
        # Das erste Feld sagt "im Bereich" -- und ist wertlos, weil der Treiber
        # ohne Pin bedingungslos 1 liefert.
        g = zustand.lies_grenze(
            "1 up=1 dn=1 num=0 raw=-1 act=1 edge_up=0 edge_dn=0 step=0")
        for r in (AUF, AB):
            self.assertIn("num=0", zustand.pruefe(g, r, 0))

    def test_no_limit_gesperrt(self):
        g = zustand.lies_grenze(ZEILE_RUHE)
        for r in (AUF, AB):
            self.assertIn("no_limit", zustand.pruefe(g, r, 1))

    def test_ohne_rohpegel_gesperrt(self):
        g = zustand.lies_grenze(
            "1 up=1 dn=1 num=1 act=1 edge_up=0 edge_dn=0 step=0")
        self.assertIn("0154", zustand.pruefe(g, AB, 0))

    def test_rohpegel_minus_eins_gesperrt(self):
        g = zustand.lies_grenze(
            "1 up=1 dn=1 num=1 raw=-1 act=1 edge_up=0 edge_dn=0 step=0")
        self.assertIn("raw=-1", zustand.pruefe(g, AB, 0))

    def test_ausserhalb_gesperrt(self):
        g = zustand.lies_grenze(
            "0 up=0 dn=0 num=1 raw=0 act=1 edge_up=0 edge_dn=0 step=-206")
        for r in (AUF, AB):
            self.assertIn("ausserhalb", zustand.pruefe(g, r, 0))

    def test_widerspruch_gesperrt(self):
        # Rohpegel passt, erstes Feld sagt trotzdem "ausserhalb".
        g = zustand.lies_grenze(
            "0 up=0 dn=0 num=1 raw=1 act=1 edge_up=0 edge_dn=0 step=0")
        self.assertIn("widerspr", zustand.pruefe(g, AB, 0))

    def test_active_level_null_wird_geachtet(self):
        # act=0 hiesse: LOW ist "im Bereich". Dann ist raw=0 richtig und raw=1
        # der Rand. Die Vendor-Angabe ist bindend, nicht die Gewohnheit.
        drin = zustand.lies_grenze(
            "1 up=1 dn=1 num=1 raw=0 act=0 edge_up=0 edge_dn=0 step=0")
        self.assertIsNone(zustand.pruefe(drin, AB, 0))
        draussen = zustand.lies_grenze(
            "0 up=0 dn=0 num=1 raw=1 act=0 edge_up=0 edge_dn=0 step=0")
        self.assertIsNotNone(zustand.pruefe(draussen, AB, 0))

    def test_unbekannte_richtung(self):
        g = zustand.lies_grenze(ZEILE_RUHE)
        with self.assertRaises(ValueError):
            zustand.pruefe(g, "seitwaerts", 0)

    def test_zaehler_versatz(self):
        typisch, hoechstens = zustand.zaehler_versatz(5)
        self.assertEqual(typisch, 6)                     # 1 + back_step
        self.assertEqual(hoechstens, 46)                 # 1 + 40 + back_step


# ---------------------------------------------------------------------------
# geraet: Suche, Sperre, Wortformat
# ---------------------------------------------------------------------------

class TestGeraet(unittest.TestCase):
    def test_findet_vorgegebenes_verzeichnis(self):
        with _stand() as (pfad, _m, _v):
            basis, herkunft = geraet.finde_basis(pfad)
            self.assertEqual(str(basis), pfad)
            self.assertIn("--sysfs", herkunft)

    def test_verzeichnis_ohne_attribute_wird_abgelehnt(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(geraet.KnotenFehlt) as e:
                geraet.finde_basis(d)
            self.assertIn("motor_ctrl", str(e.exception))

    def test_fehlender_pfad(self):
        with self.assertRaises(geraet.KnotenFehlt):
            geraet.finde_basis("/gibt/es/nicht")

    @unittest.skipIf(geraet.treiber_registriert(),
                     "auf diesem Rechner ist der Treiber registriert")
    def test_ohne_treiber_kommt_der_ladehinweis(self):
        with self.assertRaises(geraet.ModulFehlt) as e:
            geraet.finde_basis(None)
        text = str(e.exception)
        self.assertIn("homing=0", text)
        self.assertIn(geraet.MODUL, text)

    def test_no_limit_wird_nie_geschrieben(self):
        with _stand() as (pfad, modell, _v):
            g = geraet.Geraet(Path(pfad))
            with self.assertRaises(geraet.Verboten):
                g.schreibe(geraet.ATTR_NO_LIMIT, 1)
            self.assertEqual(modell.no_limit, 0)
            self.assertEqual(
                (Path(pfad) / geraet.ATTR_NO_LIMIT).read_text().strip(), "0")

    def test_wortformat(self):
        # 8 = aufwaerts, 9 = abwaerts; Bit 0x80 (full_limit) bleibt aus.
        with _stand() as (pfad, _m, v):
            g = geraet.Geraet(Path(pfad))
            self.assertEqual(g.befehl(geraet.CMD_AUF, 2), (8 << 8) | 2)
            self.assertEqual(g.befehl(geraet.CMD_AB, 2), (9 << 8) | 2)
            self.assertEqual(g.leeren(), 3 << 8)
            for wort in ((8 << 8) | 2, (9 << 8) | 2, 3 << 8):
                self.assertEqual(wort & 0x80, 0, "full_limit darf nicht gesetzt sein")
            del v

    def test_parameter_aus_sysfs(self):
        with _stand(step_num=8, cycle=2, ctrl_time=1, back_step=5) as (p, _m, _v):
            par = geraet.Geraet(Path(p)).parameter()
            self.assertEqual((par.step_num, par.cycle, par.ctrl_time_ms), (8, 2, 1))
            self.assertEqual(par.back_step, 5)
            self.assertEqual(par.geraten, ())
            self.assertAlmostEqual(par.mstep_ms, 16.0)   # 2 x 8 x 1 ms

    def test_fehlende_parameter_werden_als_vorgabe_gekennzeichnet(self):
        with _stand() as (pfad, _m, _v):
            (Path(pfad) / geraet.ATTR_BACK_STEP).unlink()
            par = geraet.Geraet(Path(pfad)).parameter()
            self.assertEqual(par.back_step, geraet.VORGABEN[geraet.ATTR_BACK_STEP])
            self.assertIn(geraet.ATTR_BACK_STEP, par.geraten)


# ---------------------------------------------------------------------------
# Das Treibermodell selbst -- damit die Tests darunter etwas wert sind
# ---------------------------------------------------------------------------

class TestModell(unittest.TestCase):
    def test_rand_wie_am_geraet(self):
        """Die Form der Messung vom 12.09.: raw faellt weg, der Treiber kehrt
        um, merkt die Kante und steht danach EINEN Zaehlerschritt weiter."""
        m = attrappe.Treibermodell(pos=-204, step=-204, rand_unten=-205)
        m.ctrl_write(str((9 << 8) | 2))
        m.ein_mstep()                                    # -> pos/step -205
        self.assertEqual((m.pos, m.step, m.raw()), (-205, -205, 1))
        m.ein_mstep()                                    # -> pos -206, raus
        self.assertEqual((m.pos, m.raw(), m.step), (-206, 0, -205))
        self.assertFalse(m.edge_dn)                      # Kante noch offen
        m.ein_mstep()                                    # Erholung
        self.assertEqual(m.step, -206)
        self.assertTrue(m.edge_dn)
        self.assertEqual(m.raw(), 1)
        self.assertEqual(m.pos, -200)                    # zurueck + back_step

    def test_weiter_abwaerts_wird_verworfen(self):
        m = attrappe.Treibermodell(pos=0, step=0, rand_unten=-1)
        m.ctrl_write(str((9 << 8) | 4))
        m.abarbeiten()
        stand = m.step
        m.ctrl_write(str((9 << 8) | 4))
        m.abarbeiten()
        self.assertEqual(m.step, stand)                  # nichts passiert

    def test_aufwaerts_loescht_die_untere_kante(self):
        m = attrappe.Treibermodell(pos=0, step=0, rand_unten=-1)
        m.ctrl_write(str((9 << 8) | 4))
        m.abarbeiten()
        self.assertTrue(m.edge_dn)
        m.ctrl_write(str((8 << 8) | 1))
        m.abarbeiten()
        self.assertFalse(m.edge_dn)

    def test_clamp_auf_18(self):
        m = attrappe.Treibermodell()
        m.ctrl_write(str((8 << 8) | 40))
        self.assertEqual(len(m.warteschlange), attrappe.MOVE_CLAMP_MAX)

    def test_autofokus_befehle_werden_abgewiesen(self):
        m = attrappe.Treibermodell()
        with self.assertRaises(OSError):
            m.ctrl_write(str((1 << 8) | 2))


# ---------------------------------------------------------------------------
# Durchgehend: cli.main() gegen die Attrappe
# ---------------------------------------------------------------------------

class TestStatus(unittest.TestCase):
    def test_status_menschenlesbar(self):
        # Ruhezustand nach dem Randereignis vom 12.09.: Zaehler -207,
        # Mechanik aber back_step+1 msteps INNERHALB des Randes.
        with _stand(pos=-200, step=-207, rand_unten=-206,
                    edge_dn=True) as (p, _m, _v):
            rueck, text = _lauf(["--sysfs", p, "status"])
        self.assertEqual(rueck, 0)
        self.assertIn("Bereichswaechter", text)
        self.assertIn("im Fahrbereich", text)
        self.assertIn("GEMERKT", text)                   # die untere Kante
        self.assertIn("step=-207", text)                 # die rohe Zeile steht da
        self.assertNotIn("Traceback", text)

    def test_status_json(self):
        # Ruhezustand nach dem Randereignis vom 12.09.: Zaehler -207,
        # Mechanik aber back_step+1 msteps INNERHALB des Randes.
        with _stand(pos=-200, step=-207, rand_unten=-206,
                    edge_dn=True) as (p, _m, _v):
            rueck, text = _lauf(["--sysfs", p, "status", "--json"])
        self.assertEqual(rueck, 0)
        satz = json.loads(text)
        self.assertEqual(satz["version"], 1)
        self.assertEqual(satz["step"], -207)
        self.assertTrue(satz["edge_dn"])
        self.assertTrue(satz["darf_auf"])
        self.assertFalse(satz["darf_ab"])
        self.assertIn("edge_dn=1", satz["grund_ab"])

    def test_status_bewegt_nichts(self):
        with _stand() as (p, modell, v):
            _lauf(["--sysfs", p, "status"])
            self.assertEqual(modell.pos, 0)
            self.assertEqual(v.geschrieben, [])


class TestFahren(unittest.TestCase):
    def test_abwaerts_im_freien_bereich(self):
        with _stand(rand_unten=-500, rand_oben=500) as (p, modell, v):
            rueck, text = _lauf(["--sysfs", p, "down", "20"])
        self.assertEqual(rueck, 0)
        self.assertEqual(modell.step, -20)
        self.assertEqual(modell.pos, -20)
        self.assertIn("fertig", text)
        # 10 Haeppchen zu 2, alle mit cmd 9 und ohne full_limit
        self.assertEqual(len(v.geschrieben), 10)
        for wort in v.geschrieben:
            self.assertEqual(wort >> 8, geraet.CMD_AB)
            self.assertEqual(wort & 0x7F, 2)
            self.assertEqual(wort & 0x80, 0)

    def test_aufwaerts_mit_eigener_schrittweite(self):
        with _stand(rand_unten=-500, rand_oben=500) as (p, modell, v):
            rueck, _t = _lauf(["--sysfs", p, "up", "6", "--schritt", "3"])
        self.assertEqual(rueck, 0)
        self.assertEqual(modell.step, 6)
        self.assertEqual([w >> 8 for w in v.geschrieben], [geraet.CMD_AUF] * 2)

    def test_haelt_am_rand_und_meldet_ihn(self):
        with _stand(rand_unten=-10, rand_oben=500) as (p, modell, v):
            rueck, text = _lauf(["--sysfs", p, "down", "100", "--max", "60"])
        self.assertEqual(rueck, 0)                       # Rand ist kein Fehler
        self.assertIn("RAND ERREICHT", text)
        self.assertTrue(modell.edge_dn)
        # Nach dem Rand wurde nicht weitergeschrieben.
        self.assertLess(len(v.geschrieben), 30)
        self.assertIn("Rand bei", text)

    def test_sieht_den_weggefallenen_rohpegel(self):
        # rand_pause_ms haelt den Zustand "raw=0, Zaehler noch alt" fest --
        # genau den, der am 12.09. abgelesen wurde.
        with _stand(rand_unten=-6, rand_oben=500,
                    rand_pause_ms=250) as (p, modell, _v):
            rueck, text = _lauf(["--sysfs", p, "down", "40", "--max", "40"])
        self.assertEqual(rueck, 0)
        self.assertIn("RAND ERREICHT", text)
        self.assertIn("Rohpegel", text)
        # Und danach wird die RUHELAGE abgewartet, nicht die Momentaufnahme
        # gemeldet: der Treiber ist zurueckgefahren und hat die Kante gesetzt.
        self.assertIn("Ruhelage danach", _flach(text))
        self.assertIn("edge_dn=1", text)
        self.assertTrue(modell.edge_dn)
        self.assertTrue(modell.im_fahrbereich)

    def test_nach_dem_rand_steht_die_mechanik_wieder_im_bereich(self):
        # Der Zaehler ist danach EINEN mstep hinter dem Rand, die Mechanik aber
        # back_step+1 msteps davor -- der Versatz aus zustand.zaehler_versatz.
        with _stand(rand_unten=-10, rand_oben=500) as (p, modell, _v):
            _lauf(["--sysfs", p, "down", "40", "--max", "40"])
        self.assertEqual(modell.step, -11)
        self.assertEqual(modell.pos, -10 + modell.back_step)
        typisch, _h = zustand.zaehler_versatz(modell.back_step)
        self.assertEqual(modell.pos - modell.step, typisch)

    def test_gemerkte_kante_sperrt_und_schreibt_nichts(self):
        with _stand(edge_dn=True) as (p, modell, v):
            rueck, text = _lauf(["--sysfs", p, "down", "10"])
        self.assertEqual(rueck, 1)
        self.assertIn("nicht gefahren", text)
        self.assertIn("edge_dn=1", text)
        self.assertEqual(v.geschrieben, [])
        self.assertEqual(modell.pos, 0)

    def test_gegenrichtung_bleibt_erlaubt(self):
        with _stand(edge_dn=True, rand_oben=500) as (p, modell, _v):
            rueck, _t = _lauf(["--sysfs", p, "up", "4"])
        self.assertEqual(rueck, 0)
        self.assertEqual(modell.step, 4)
        self.assertFalse(modell.edge_dn)                 # der Treiber loescht sie

    def test_ohne_limiter_wird_nicht_gefahren(self):
        with _stand(num=0) as (p, modell, v):
            rueck, text = _lauf(["--sysfs", p, "down", "4"])
        self.assertEqual(rueck, 1)
        self.assertIn("num=0", text)
        self.assertEqual(v.geschrieben, [])
        self.assertEqual(modell.pos, 0)

    def test_no_limit_gesetzt_wird_nicht_gefahren(self):
        with _stand(no_limit=1) as (p, modell, v):
            rueck, text = _lauf(["--sysfs", p, "down", "4"])
        self.assertEqual(rueck, 1)
        self.assertIn("no_limit", text)
        self.assertEqual(v.geschrieben, [])
        self.assertEqual(modell.pos, 0)

    def test_alte_zeile_ohne_raw_sperrt_das_fahren(self):
        with _stand() as (p, modell, v):
            (Path(p) / "motor_limit").write_text(
                "1 up=1 dn=1 num=1 act=1 edge_up=0 edge_dn=0 step=0\n")
            rueck, text = _lauf(["--sysfs", p, "down", "4"])
        self.assertEqual(rueck, 1)
        self.assertIn("0154", text)
        self.assertEqual(v.geschrieben, [])

    def test_harte_obergrenze(self):
        with _stand(rand_unten=-9999, rand_oben=9999) as (p, modell, _v):
            rueck, text = _lauf(["--sysfs", p, "down", "1000", "--schritt", "18"])
        self.assertEqual(rueck, 0)
        self.assertIn("gekuerzt", text)
        self.assertEqual(abs(modell.step), fahren.LAUF_MAX_HART)

    def test_schrittweite_ueber_dem_clamp_wird_abgelehnt(self):
        with _stand() as (p, _m, v):
            rueck, _t = _lauf(["--sysfs", p, "down", "4", "--schritt", "30"])
        self.assertEqual(rueck, 2)
        self.assertEqual(v.geschrieben, [])

    def test_trockenlauf_schreibt_nichts(self):
        with _stand(rand_unten=-500) as (p, modell, v):
            rueck, text = _lauf(["--sysfs", p, "--trocken", "down", "20"])
        self.assertEqual(rueck, 0)
        self.assertIn("Trockenlauf", text)
        self.assertIn(f"{(9 << 8) | 2}", text)
        self.assertEqual(v.geschrieben, [])
        self.assertEqual(modell.pos, 0)

    def test_null_msteps_ist_ein_bedienfehler(self):
        with _stand() as (p, _m, v):
            rueck, _t = _lauf(["--sysfs", p, "down", "0"])
        self.assertEqual(rueck, 2)
        self.assertEqual(v.geschrieben, [])


class TestGoto(unittest.TestCase):
    def test_faehrt_auf_den_zaehlerstand(self):
        with _stand(pos=-100, step=-100,
                    rand_unten=-500, rand_oben=500) as (p, modell, _v):
            rueck, text = _lauf(["--sysfs", p, "goto", "-90"])
        self.assertEqual(rueck, 0)
        self.assertEqual(modell.step, -90)
        self.assertIn("10 msteps", text)

    def test_gleicher_stand_tut_nichts(self):
        with _stand(pos=-100, step=-100) as (p, _m, v):
            rueck, text = _lauf(["--sysfs", p, "goto", "-100"])
        self.assertEqual(rueck, 0)
        self.assertIn("Nichts zu tun", text)
        self.assertEqual(v.geschrieben, [])

    def test_richtung_nach_unten(self):
        with _stand(rand_unten=-500, rand_oben=500) as (p, modell, v):
            rueck, _t = _lauf(["--sysfs", p, "goto", "-8"])
        self.assertEqual(rueck, 0)
        self.assertEqual(modell.step, -8)
        self.assertTrue(all(w >> 8 == geraet.CMD_AB for w in v.geschrieben))


class TestStopp(unittest.TestCase):
    def test_leert_die_warteschlange(self):
        with _stand() as (p, _m, v):
            rueck, text = _lauf(["--sysfs", p, "stop"])
        self.assertEqual(rueck, 0)
        self.assertEqual(v.geschrieben, [geraet.CMD_LEEREN << 8])
        self.assertIn("Warteschlange geleert", text)
        self.assertIn("laeuft noch zu Ende", _flach(text))


    def test_flush_ist_derselbe_befehl(self):
        # "flush" hiess er im Vorlaeufer legacy/tools/focus.
        with _stand() as (p, _m, v):
            rueck, text = _lauf(["--sysfs", p, "flush"])
        self.assertEqual(rueck, 0)
        self.assertEqual(v.geschrieben, [geraet.CMD_LEEREN << 8])
        self.assertIn("Warteschlange geleert", text)


class TestRange(unittest.TestCase):
    def test_findet_den_unteren_rand(self):
        with _stand(rand_unten=-40, rand_oben=500) as (p, modell, _v):
            rueck, text = _lauf(["--sysfs", p, "range", "--ja", "--max", "120"])
        self.assertEqual(rueck, 0)
        self.assertIn("unterer Rand", text)
        self.assertIn("oberer Rand nicht angefahren", _flach(text))
        self.assertTrue(modell.edge_dn)
        # Der Rand liegt beim Zaehlerstand des Randereignisses.
        self.assertIn("step=-41", text)

    def test_faehrt_nicht_nach_oben_ohne_schalter(self):
        with _stand(rand_unten=-10, rand_oben=10) as (p, modell, _v):
            _lauf(["--sysfs", p, "range", "--ja", "--max", "60"])
        self.assertFalse(modell.edge_up)
        self.assertLess(modell.pos, 5)

    def test_beide_raender(self):
        with _stand(rand_unten=-30, rand_oben=30) as (p, modell, _v):
            rueck, text = _lauf(["--sysfs", p, "range", "--ja",
                                 "--auch-oben", "--max", "150"])
        self.assertEqual(rueck, 0)
        self.assertTrue(modell.edge_up)
        self.assertIn("Fahrweg", text)
        self.assertIn("nie geprueft", text)             # Ehrlichkeit zu den 800

    def test_kein_rand_in_reichweite_ist_ein_befund(self):
        with _stand(rand_unten=-9999, rand_oben=9999) as (p, _m, _v):
            rueck, text = _lauf(["--sysfs", p, "range", "--ja", "--max", "20"])
        self.assertEqual(rueck, 1)
        self.assertIn("NICHT gefunden", text)
        self.assertIn("kein Grund weiterzufahren", _flach(text))

    def test_faengt_nicht_an_wenn_abwaerts_gesperrt(self):
        with _stand(edge_dn=True) as (p, _m, v):
            rueck, _t = _lauf(["--sysfs", p, "range", "--ja"])
        self.assertEqual(rueck, 2)
        self.assertEqual(v.geschrieben, [])

    def test_ohne_ja_und_ohne_terminal_passiert_nichts(self):
        with _stand(rand_unten=-40) as (p, _m, v):
            rueck, _t = _lauf(["--sysfs", p, "range"])
        self.assertEqual(rueck, 2)
        self.assertEqual(v.geschrieben, [])


class TestKeineVerboteneBefehle(unittest.TestCase):
    """Quer ueber alle Laeufe: nur 8, 9 und 3 duerfen geschrieben werden."""

    def test_nur_erlaubte_kommandos(self):
        erlaubt = {geraet.CMD_AUF, geraet.CMD_AB, geraet.CMD_LEEREN}
        with _stand(rand_unten=-40, rand_oben=40) as (p, _m, v):
            _lauf(["--sysfs", p, "down", "6"])
            _lauf(["--sysfs", p, "up", "4"])
            _lauf(["--sysfs", p, "goto", "0"])
            _lauf(["--sysfs", p, "stop"])
            _lauf(["--sysfs", p, "range", "--ja", "--max", "80"])
        self.assertTrue(v.geschrieben)
        for wort in v.geschrieben:
            self.assertIn(wort >> 8, erlaubt, f"unerlaubtes Kommando in {wort}")
            self.assertEqual(wort & 0x80, 0)


class TestAusfuehrbar(unittest.TestCase):
    """Das mitgelieferte Startskript muss auch als Programm laufen."""

    START = WURZEL / "h713-focus"

    def test_hilfe(self):
        lauf = subprocess.run([sys.executable, str(self.START), "--help"],
                              capture_output=True, text=True)
        self.assertEqual(lauf.returncode, 0, lauf.stderr)
        self.assertIn("BEREICHSWAECHTER", lauf.stdout)
        self.assertIn("range", lauf.stdout)

    def test_status_als_unterprozess(self):
        with _stand(pos=-3, step=-3, rand_unten=-206) as (p, _m, v):
            lauf = subprocess.run(
                [sys.executable, str(self.START), "--sysfs", p,
                 "status", "--json"],
                capture_output=True, text=True)
        self.assertEqual(lauf.returncode, 0, lauf.stderr)
        satz = json.loads(lauf.stdout)
        self.assertEqual(satz["step"], -3)
        self.assertEqual(v.geschrieben, [])

    def test_ausfuehrbar_gesetzt(self):
        self.assertTrue(os.access(self.START, os.X_OK),
                        "h713-focus muss ausfuehrbar sein")


if __name__ == "__main__":
    unittest.main(verbosity=2)
