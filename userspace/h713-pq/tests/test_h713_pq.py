#!/usr/bin/env python3
"""Tests gegen die echten Vendor-Dateien.

Die Vendor-Dateien werden zur Laufzeit gelesen und nie kopiert. Fehlt das
tvconfig-Verzeichnis (oder der Legacy-Baum), wird der jeweilige Test sauber
uebersprungen statt zu scheitern.

Aufruf:  python3 -m unittest discover -s tests -v
     oder python3 tests/test_h713_pq.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]          # userspace/h713-pq
sys.path.insert(0, str(WURZEL))

from h713_pq import ausgabe, modell, quellen  # noqa: E402

PROJEKT = WURZEL.parents[1]                            # /opt/Projekte/h713
PQD = PROJEKT / "legacy/userspace/hy310-pqd"


def _daten() -> quellen.Datenbestand | None:
    try:
        return quellen.lade(None)
    except FileNotFoundError:
        return None


DATEN = _daten()
braucht_daten = unittest.skipIf(DATEN is None,
                                "tvconfig-Verzeichnis nicht gefunden")


# ---------------------------------------------------------------------------
# Quellen
# ---------------------------------------------------------------------------

@braucht_daten
class TestQuellen(unittest.TestCase):
    def test_tvpq_db_zeilenzahlen(self):
        # Nachtplan Abschnitt 3 G: Picture_Mode 25, White_Balance_Mode 20,
        # Gamma_Point 33.
        self.assertEqual(len(DATEN.db_picture_mode), 25)
        self.assertEqual(len(DATEN.db_weissabgleich), 20)
        self.assertEqual(len(DATEN.db_gamma_punkte), 33)

    def test_gamma_punkte_sind_leer(self):
        # Die ausgelieferte Tabelle ist durchgaengig 0 -- als Kurve unbrauchbar.
        # Stock rechnet die Punkte zur Laufzeit (BACKGROUND.md 6.2).
        self.assertEqual(set(DATEN.db_gamma_punkte), {0})

    def test_weissabgleich_neutral(self):
        for z in DATEN.db_weissabgleich:
            self.assertEqual((z.rgain, z.ggain, z.bgain), (512, 512, 512))
            self.assertEqual((z.roffset, z.goffset, z.boffset), (0, 0, 0))

    def test_werkskurve_hdmi(self):
        k = DATEN.werkskurven["HDMI"]
        self.assertEqual(k["saturation"], [0, 48, 96, 145, 192])
        self.assertEqual(k["brightness"], [0, 256, 512, 775, 1023])
        self.assertEqual(k["contrast"], [1196, 1794, 2392, 3010, 3588])
        self.assertEqual(k["hue"], [0, 256, 512, 775, 1023])
        self.assertEqual(k["sharpness"], [0, 64, 128, 193, 255])

    def test_gamma_stufen_aus_xml(self):
        # pqcontrol_config_setting.xml <transform name="gamma">
        self.assertEqual(DATEN.gamma_stufen, [1.8, 2.0, 2.1, 2.2, 2.4])

    def test_presets_hdmi1(self):
        vivid = DATEN.presets["HDMI1"]["vivid"].werte
        self.assertEqual(vivid["saturation"], 60)
        self.assertEqual(vivid["contrast"], 55)
        self.assertEqual(vivid["gamma"], 3)
        cinema = DATEN.presets["HDMI1"]["cinema"].werte
        self.assertEqual(cinema["saturation"], 45)

    def test_portmap(self):
        self.assertIn((1, 1, "HDMI1"), DATEN.portmap)
        self.assertEqual(len(DATEN.portmap), 6)

    def test_colortemp_neutral(self):
        for name in modell.FARBTEMP_NAMEN:
            ft = DATEN.farbtemperaturen["HDMI"][name]
            self.assertEqual((ft.rgain, ft.ggain, ft.bgain), (512, 512, 512))


# ---------------------------------------------------------------------------
# Modell: Saettigung
#
# Korrektur 07.09.2026 (doku/nachtlog/G-korrektur-saettigung.md). Die
# Erwartungswerte dieses Abschnitts sind geaendert worden, nicht die Rechnung:
# die Messung am Geraet (doku/nachtlog/K5-board-verifikation.md Abschnitt f)
# hat die alte Annahme "Gain 0x4C gehoert zu Benutzerwert 50" widerlegt.
# Belegt ist statt dessen: SetSaturation(N) -> 0x05001238[15:0] = N und
# 0x05140508[23:16] = floor(N * 1,28), gemessen bei N = 0/50/59/60/100.
# ---------------------------------------------------------------------------

@braucht_daten
class TestSaettigung(unittest.TestCase):
    def _kette(self, eingang: str, modus: str):
        return modell.kette(DATEN, eingang, modus)

    def test_gemessene_tabelle_k5_abschnitt_f(self):
        """Die fuenf am Geraet gemessenen Punkte, ohne jede Zwischenrechnung.

        Frueher stand hier die Tabelle aus doku/77 Abschnitt 4 (cinema 0x44,
        standard 0x4C, vivid 0x5C). Sie stammte aus der Kurvenrechnung, nicht
        aus einer Messung des RPC, und ist widerlegt: 0x4C gehoert zu
        SetSaturation 60, nicht zu 50.
        """
        gemessen = {0: 0x00, 50: 0x40, 59: 0x4B, 60: 0x4C, 100: 0x80}
        for argument, gain in gemessen.items():
            self.assertEqual(modell.chroma_gain(argument), gain,
                             f"SetSaturation {argument}")

    def test_floor_nicht_round(self):
        """59 und 60 sind die beiden Punkte, die die Rundungsart entscheiden.

        59 * 1,28 = 75,52. Kaufmaennisch gerundet waere das 76 (0x4C);
        gemessen wurde 75 (0x4B). Also abrunden.
        """
        self.assertEqual(modell.chroma_gain(59), 0x4B)
        self.assertEqual(modell.chroma_gain(60), 0x4C)
        self.assertNotEqual(modell.chroma_gain(59), round(59 * 1.28))

    def test_firmware_vorgabe_entspricht_argument_60(self):
        # Die Firmware startet mit 0x144C0000, ohne dass prep_after_boot.sh
        # SetSaturation aufruft (K5-Abnahme f).
        gain = (modell.REG_CHROMA_GAIN_STOCK & modell.CHROMA_GAIN_MASKE) >> \
            modell.CHROMA_GAIN_SHIFT
        self.assertEqual(gain, 0x4C)
        self.assertEqual(modell.chroma_gain(modell.ARGUMENT_DER_FIRMWARE_VORGABE),
                         gain)

    def test_bildmodi_liefern_rpc_argumente(self):
        """Ergebnis von h713-pq ist jetzt das RPC-Argument.

        Erwartet wird der Benutzerwert der Vendor-Presets (cinema 45,
        standard 50, vivid 60) -- frueher standen hier Registerwerte.
        """
        self.assertEqual(self._kette("HDMI1", "cinema").saettigung_argument, 45)
        self.assertEqual(self._kette("HDMI1", "standard").saettigung_argument, 50)
        self.assertEqual(self._kette("HDMI1", "vivid").saettigung_argument, 60)

    def test_kontrollwerte_gain_und_registerwort(self):
        """Der Gain bleibt als Kontrollausgabe, aber als floor(Argument*1,28).

        Frueher: standard -> 0x4C / 0x144C0000, vivid -> 0x5C / 0x145C0000.
        Jetzt: standard -> 0x40 / 0x14400000, vivid -> 0x4C / 0x144C0000 --
        vivid trifft damit genau die Firmware-Vorgabe.
        """
        standard = self._kette("HDMI1", "standard")
        self.assertEqual(standard.gain, 0x40)
        self.assertEqual(standard.gain_register, 0x14400000)
        vivid = self._kette("HDMI1", "vivid")
        self.assertEqual(vivid.gain, 0x4C)
        self.assertEqual(vivid.gain_register, modell.REG_CHROMA_GAIN_STOCK)
        self.assertEqual(self._kette("HDMI1", "cinema").gain, 0x39)
        # Reine Bitfunktion, von der Korrektur unberuehrt.
        self.assertEqual(modell.chroma_gain_register(0x5C), 0x145C0000)

    def test_gain_nur_aus_dem_argument_nicht_aus_der_kurve(self):
        # Fuer jedes Argument 0..100 gilt die Firmware-Formel, unabhaengig
        # davon, ob es fuer den Eingang ueberhaupt eine Werkskurve gibt.
        for a in range(0, 101):
            self.assertEqual(modell.chroma_gain(a), (a * 128) // 100)
        self.assertEqual(modell.chroma_gain(-5), 0)
        self.assertEqual(modell.chroma_gain(500), 128)

    def test_rpc_argument_ist_durchgereicht_und_begrenzt(self):
        for u in (0, 45, 50, 60, 100):
            self.assertEqual(modell.rpc_argument(u), u)
        self.assertEqual(modell.rpc_argument(-1), 0)
        self.assertEqual(modell.rpc_argument(101), 100)

    def test_offene_stufe_aendert_heute_nichts(self):
        """Belegt die Begruendung, warum die ungemessene Stufe offen bleiben darf.

        Saesse die Werkskurve doch zwischen Benutzerwert und RPC-Argument
        (auf 0..100 normiert), waere das Ergebnis fuer alle in den Vendor-Daten
        vorkommenden Saettigungswerte identisch. Abweichung ueberhaupt: genau
        bei Benutzerwert 75, und dort um 1.
        """
        kurve = DATEN.werkskurven["HDMI"]["saturation"]
        abweichend = {u: modell.kurve_als_argument(kurve, u)
                      for u in range(0, 101)
                      if modell.kurve_als_argument(kurve, u) != u}
        self.assertEqual(abweichend, {75: 76})
        vorkommend = {bm.werte["saturation"]
                      for modi in DATEN.presets.values() for bm in modi.values()}
        self.assertEqual(vorkommend, {45, 50, 60})
        self.assertNotIn(75, vorkommend)

    def test_kurve_stuetzstellen(self):
        # Die Werkskurve selbst ist unveraendert -- sie bleibt als Vendor-Datum
        # in der Ausgabe, nur nicht mehr als Rechenweg.
        kurve = DATEN.werkskurven["HDMI"]["saturation"]
        for u, y in ((0, 0), (25, 48), (50, 96), (75, 145), (100, 192)):
            self.assertAlmostEqual(modell.kurvenwert(kurve, u), y)
        self.assertAlmostEqual(modell.kurvenwert(kurve, 45), 86.4)
        self.assertAlmostEqual(modell.kurvenwert(kurve, 60), 115.6)

    def test_kurve_ist_keine_rpc_skala(self):
        # Das Argument der PQ-RPCs laeuft nachweislich bis 100 (SetContrast 100
        # -> 0x64). Die Kurvenwerte laufen weit darueber hinaus -- deshalb kann
        # die Kurve die Stufe Benutzerwert -> Argument nicht sein.
        k = DATEN.werkskurven["HDMI"]
        self.assertGreater(k["saturation"][-1], modell.BENUTZERWERT_MAX)
        self.assertGreater(k["contrast"][-1], modell.BENUTZERWERT_MAX)


# ---------------------------------------------------------------------------
# Modell: Kette und Datenlage
# ---------------------------------------------------------------------------

@braucht_daten
class TestKette(unittest.TestCase):
    def test_db_kreuzprobe_stimmt(self):
        k = modell.kette(DATEN, "HDMI1", "vivid")
        self.assertIn("stimmt Wert fuer Wert ueberein", k.db_abgleich)

    def test_gamma_index_zu_exponent(self):
        k = modell.kette(DATEN, "HDMI1", "standard")
        self.assertEqual(k.gamma_index, 3)
        self.assertEqual(k.gamma_exponent, 2.2)

    def test_alle_kurvengroessen_haben_jetzt_ein_register(self):
        """Stand 11.09.2026 -- alle fuenf Groessen sind am Geraet gemessen.

        Frueher stand hier: brightness/contrast/hue/sharpness -> Ziel "-",
        Stand "offen (K5)"; danach "RE belegt, ungemessen" fuer Farbton und
        Schaerfe. Beides ist ueberholt. doku/85 Abschnitt A.1 hat die
        UIMapping-Tabelle statisch aufgeloest, die Board-Abnahme K5 c/e hat
        Kontrast und Helligkeit nachgemessen, und am 11.09.2026 sind Farbton
        und Schaerfe ueber /dev/mem zurueckgelesen worden -- 1:1 bei
        0/25/50/75/100 (doku/81 Abschnitt 7.3, Plan 113 Abschnitt A.6).
        """
        k = modell.kette(DATEN, "HDMI1", "vivid")
        nach_groesse = {z.groesse: z for z in k.zielwerte}
        erwartet = {
            "brightness": (0x05001234, "[15:0]", "gemessen, wirkt"),
            "contrast": (0x05001234, "[31:16]", "gemessen, wirkt"),
            "saturation": (0x05001238, "[15:0]", "gemessen, wirkt"),
            "hue": (0x05001238, "[31:16]", "gemessen, wirkt"),
            "sharpness": (0x05001228, "[23:8]", "gemessen (Register)"),
        }
        for groesse, (reg, feld, stand) in erwartet.items():
            z = nach_groesse[groesse]
            self.assertIn(f"0x{reg:08X}", z.ziel, groesse)
            self.assertIn(feld, z.ziel, groesse)
            self.assertEqual(z.stand, stand, groesse)
            # Das Ergebnis ist das RPC-Argument, nicht ein Registerwert.
            self.assertEqual(z.argument, z.benutzerwert, groesse)

    def test_kein_feld_mehr_ungemessen(self):
        """Die Kehrseite: seit dem 11.09. traegt keine der fuenf Groessen mehr
        den Vermerk "(Wert ungemessen)" in der Zielspalte, weil jede von ihnen
        am Geraet mit ihrem Argument im Register angetroffen wurde."""
        k = modell.kette(DATEN, "HDMI1", "vivid")
        for z in k.zielwerte:
            if z.groesse in modell.KURVENGROESSEN:
                self.assertNotIn("ungemessen", z.ziel, z.groesse)
                self.assertTrue(modell.PQ_ZIELE[z.groesse].argument_1zu1,
                                z.groesse)

    def test_indexgroessen_ohne_registerschreiben(self):
        # doku/85 A.1/A.5: SetTNR und SetBlackExtension haben eine Item-ID,
        # aber Adresse 0 -- sie schreiben nachweislich kein Register.
        k = modell.kette(DATEN, "HDMI1", "vivid")
        nach_groesse = {z.groesse: z for z in k.zielwerte}
        for groesse in ("tnr", "blackextension"):
            self.assertEqual(nach_groesse[groesse].ziel, "kein Register")
        # DCI und SNR dagegen sind am Geraet belegt (K5-Abnahme b).
        self.assertIn("0x0500123C", nach_groesse["dci"].ziel)
        self.assertIn("0x05001248", nach_groesse["snr"].ziel)

    def test_custom_kommt_aus_der_datenbank(self):
        bm = modell.preset(DATEN, "HDMI1", "custom")
        self.assertIn("tvpq.db", bm.herkunft)

    def test_vga_hat_keine_werkskurve_aber_ein_rpc_argument(self):
        """Frueher: ohne Werkskurve kein Gain (assertIsNone).

        Das war eine Folge des alten Rechenwegs. Seit der Korrektur haengt das
        RPC-Argument nicht mehr an der Kurve, sondern am Benutzerwert -- also
        liefert auch ein Eingang ohne Kurvengruppe ein gueltiges Argument.
        Dass VGA1..3 keine Gruppe in pq_factory_extern.ini haben, bleibt wahr
        und wird weiterhin ausgewiesen.
        """
        self.assertIsNone(modell.EINGANG_GRUPPE["VGA1"])
        self.assertNotIn("VGA1", DATEN.werkskurven)
        k = modell.kette(DATEN, "VGA1", "standard")
        self.assertEqual(k.saettigung_argument, 50)
        self.assertEqual(k.gain, 0x40)
        sat = [z for z in k.zielwerte if z.groesse == "saturation"][0]
        self.assertIsNone(sat.kurvenwert)
        self.assertIn("keine Kurvengruppe", sat.hinweis)

    def test_tvin_zuordnung_bleibt_mehrdeutig(self):
        z = dict((tvin, kand) for tvin, _, kand in modell.tvin_zuordnung(DATEN))
        self.assertEqual(set(z), {0, 1, 2, 3, 4})
        self.assertIn("HDMI1", z[0])          # tvin 0 fuehrt computer + hdr
        self.assertNotIn("CVBS", z[0])
        self.assertGreater(len(z[0]), 1)      # nicht eindeutig -- wird nicht geraten
        self.assertEqual(set(z[1]), {"ATV", "CVBS"})
        self.assertEqual(set(z[3]), {"DTV", "VIDEODEC"})


# ---------------------------------------------------------------------------
# Modell: der maschinenlesbare Satz (Plan 113 Abschnitt A.3)
# ---------------------------------------------------------------------------

@braucht_daten
class TestSatz(unittest.TestCase):
    """Der Satz, den h713-tv beim Start liest.

    Er ist eine Schnittstelle zwischen zwei Programmen, also wird hier nicht
    nur geprueft, dass etwas herauskommt, sondern was genau: Feldnamen,
    Feldzahl und die Nummern, an denen h713-tv haengt.
    """

    def _satz(self, modus="standard"):
        return modell.satz(DATEN, "HDMI1", modus)

    def test_pflichtfelder(self):
        s = self._satz()
        for feld in ("version", "eingang", "preset", "modus", "regler",
                     "gamma_exponent", "presets"):
            self.assertIn(feld, s, feld)
        self.assertEqual(s["version"], modell.SATZ_VERSION)
        self.assertEqual(s["eingang"], "HDMI1")
        self.assertEqual(s["preset"], "standard")

    def test_neun_regler_mit_den_namen_der_vendor_datei(self):
        # Genau diese neun Namen sucht h713-tv (preset_pq_key[] in main.c).
        self.assertEqual(set(self._satz()["regler"]),
                         set(modell.PRESET_GROESSEN))
        self.assertEqual(len(modell.PRESET_GROESSEN), 9)

    def test_werte_stimmen_mit_pq_picturemode_ini(self):
        # vivid, die Zeile [HDMI1] der INI, Spalte fuer Spalte.
        r = self._satz("vivid")["regler"]
        self.assertEqual(r, {"brightness": 50, "contrast": 55, "saturation": 60,
                             "hue": 50, "sharpness": 60, "tnr": 2, "snr": 1,
                             "dci": 3, "blackextension": 1})

    def test_firmware_modusnummern(self):
        """Die Nummern der MIPS-Firmware, nicht die der Datenbank.

        doku/nachtlog/S14 Abschnitt 1.2 -- tvpq.db zaehlt anders (dort ist
        standard 0 und vivid 2), und wer die beiden verwechselt, schickt der
        Firmware den falschen Modus.
        """
        erwartet = {"standard": 1, "cinema": 7, "vivid": 0, "game": 3,
                    "computer": 6, "hdr": 12}
        for name, nummer in erwartet.items():
            with self.subTest(name):
                s = self._satz(name)
                self.assertEqual(s["modus"], nummer)
                self.assertTrue(s["modus_eigen"])

    def test_energy_saving_und_custom_ohne_eigene_nummer(self):
        # S14 Abschnitt 4: fuer beide gibt es keinen Firmware-Modus. Sie
        # laufen unter Standard und sagen das auch.
        for name in ("energy_saving", "custom"):
            with self.subTest(name):
                s = self._satz(name)
                self.assertEqual(s["modus"], modell.FIRMWARE_MODUS_ERSATZ)
                self.assertFalse(s["modus_eigen"])

    def test_energy_saving_unterscheidet_sich_nur_im_backlight(self):
        # Deshalb sind seine neun Regler die von standard -- das ist kein
        # Fehler, sondern die Vendor-Zeile.
        self.assertEqual(self._satz("energy_saving")["regler"],
                         self._satz("standard")["regler"])
        self.assertEqual(self._satz("energy_saving")["weitere"]["backlight"], 80)
        self.assertEqual(self._satz("standard")["weitere"]["backlight"], 100)

    def test_alle_bildmodi_des_eingangs_liegen_bei(self):
        # A.5: energy_saving und custom werden angeboten, sobald die Daten
        # da sind -- ohne zweiten Aufruf von h713-pq.
        namen = [p["name"] for p in self._satz()["presets"]]
        self.assertEqual(namen, ["standard", "cinema", "vivid", "game",
                                 "computer", "hdr", "energy_saving", "custom"])
        for p in self._satz()["presets"]:
            self.assertEqual(len(p["regler"]), 9, p["name"])

    def test_flache_felder_und_liste_sind_dieselben(self):
        # Der Satz nennt das angeforderte Preset zweimal: flach und in der
        # Liste. Sie kommen aus derselben Funktion und duerfen nicht
        # auseinanderlaufen.
        s = self._satz("cinema")
        aus_liste = [p for p in s["presets"] if p["name"] == "cinema"][0]
        self.assertEqual(s["regler"], aus_liste["regler"])
        self.assertEqual(s["modus"], aus_liste["modus"])
        self.assertEqual(s["gamma_exponent"], aus_liste["gamma_exponent"])

    def test_satz_ist_json_und_eine_zeile(self):
        import io as _io
        import json as _json
        from contextlib import redirect_stdout

        puffer = _io.StringIO()
        with redirect_stdout(puffer):
            ausgabe.drucke_satz(self._satz())
        text = puffer.getvalue()
        self.assertEqual(text.count("\n"), 1)
        self.assertEqual(_json.loads(text)["preset"], "standard")

    def test_nur_die_noetigen_dateien(self):
        """Der schnelle Ladeweg liefert denselben Satz wie der volle.

        h713-tv liest beim Start mit quellen.DATEIEN_FUER_SATZ, weil
        pq_factory_extern.ini allein 85 ms Bild kostet. Wenn das je einen
        Unterschied am Satz machte, waere es ein Fehler.
        """
        knapp = quellen.lade(str(DATEN.verzeichnis), quellen.DATEIEN_FUER_SATZ)
        a = modell.satz(knapp, "HDMI1", "vivid")
        b = modell.satz(DATEN, "HDMI1", "vivid")
        for feld in ("modus", "regler", "weitere", "gamma_exponent"):
            self.assertEqual(a[feld], b[feld], feld)
        self.assertEqual([p["name"] for p in a["presets"]],
                         [p["name"] for p in b["presets"]])

    def test_kaputte_datei_ist_nicht_toedlich(self):
        """Eine unlesbare tvpq.db kostet die Kreuzprobe, nicht die Presets.

        Plan 113 Abschnitt A.5: h713-tv ruft dieses Programm beim Start.
        Ein Abbruch beim Lesen waere ein Bild weniger.
        """
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            ziel = Path(tmp)
            for name in quellen.DATEIEN_FUER_SATZ:
                quelle = DATEN.verzeichnis / name
                if quelle.is_file():
                    shutil.copy2(quelle, ziel / name)
            (ziel / quellen.DATEI_DB).write_bytes(b"das ist keine Datenbank")
            best = quellen.lade(str(ziel))
            self.assertTrue(any("unlesbar" in x for x in best.fehlende_dateien))
            s = modell.satz(best, "HDMI1", "standard")
            self.assertEqual(s["regler"]["contrast"], 50)
            # ohne Datenbank faellt "custom" weg -- der Rest bleibt
            self.assertNotIn("custom", [p["name"] for p in s["presets"]])


# ---------------------------------------------------------------------------
# Modell: Gamma
# ---------------------------------------------------------------------------

class TestGamma(unittest.TestCase):
    def test_sanity_aus_re_guide_identitaet(self):
        # CALCULATEGAMMA_RE_GUIDE.md Abschnitt 11:
        #   identity -> lut[0] = 0, lut[512] ~ 2048, lut[1023] = 4095
        lut = modell.interpolieren(modell.stuetzpunkte_identitaet())
        self.assertEqual(lut[0], 0)
        self.assertEqual(lut[1023], 4095)
        self.assertAlmostEqual(lut[512], 2048, delta=8)

    def test_sanity_aus_re_guide_gamma22(self):
        #   gamma 2.2 -> lut[0] = 0, Mitte ~ 891, lut[1023] = 4095
        erg = modell.gamma_rechnen(2.2)
        self.assertEqual(erg.lut[0], 0)
        self.assertEqual(erg.lut[1023], 4095)
        # Der Guide-Wert 891 ist der Stuetzpunkt bei t = 0,5 (Punkt 16).
        self.assertEqual(erg.punkte[16], 891)
        # LUT-Index 512 liegt bei t = 512/1023 = 0,5005 -> minimal hoeher.
        self.assertAlmostEqual(erg.lut[512], 891, delta=5)
        self.assertLess(erg.lut[512], 1500)   # dunkler als Identitaet

    def test_gamma_faktor_reihenfolge(self):
        # Groesserer Exponent -> dunklere Mitteltoene.
        a = modell.gamma_rechnen(1.8).lut[512]
        b = modell.gamma_rechnen(2.4).lut[512]
        self.assertGreater(a, b)

    def test_packformat(self):
        lut = [i & modell.LUT_MAX for i in range(modell.LUT_EINTRAEGE)]
        gepackt = modell.packen(lut)
        self.assertEqual(len(gepackt), 512)
        self.assertEqual(gepackt[0], (1 << 12) | 0)
        self.assertEqual(gepackt[5], (11 << 12) | 10)

    def test_lut_datei_groessen(self):
        erg = modell.gamma_rechnen(2.2)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "lut.bin"
            self.assertEqual(ausgabe.schreibe_lut(p, erg, "r"), 2048)
            self.assertEqual(ausgabe.schreibe_lut(p, erg, "all"), 3 * 2048)
            roh = p.read_bytes()
            self.assertEqual(roh[:2048], roh[2048:4096])   # Baenke gleich (WB neutral)

    def test_kein_wert_ausserhalb_12_bit(self):
        for exp in (1.0, 1.8, 2.2, 2.4, 3.0):
            for v in modell.gamma_rechnen(exp).lut:
                self.assertGreaterEqual(v, 0)
                self.assertLessEqual(v, modell.LUT_MAX)


# ---------------------------------------------------------------------------
# Bitvergleich gegen den Legacy-Rechner
# ---------------------------------------------------------------------------

def _legacy_baubar() -> bool:
    return ((PQD / "src/pqgamma.cpp").is_file()
            and (PQD / "include/pqgamma.h").is_file()
            and subprocess.run(["which", "g++"], capture_output=True).returncode == 0)


@unittest.skipUnless(_legacy_baubar(), "Legacy-Baum oder g++ nicht vorhanden")
class TestGegenLegacy(unittest.TestCase):
    def test_bitgleich(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            bin_ = d / "legacy_ref"
            bau = subprocess.run(
                ["g++", "-O2", "-std=c++17", "-I", str(PQD / "include"),
                 str(PQD / "src/pqgamma.cpp"),
                 str(WURZEL / "tests/legacy_ref.cpp"), "-o", str(bin_)],
                capture_output=True, text=True)
            self.assertEqual(bau.returncode, 0, bau.stderr)
            for exp in ("1.8", "2.0", "2.1", "2.2", "2.4", "1.0"):
                ref = d / f"legacy-{exp}.bin"
                lauf = subprocess.run([str(bin_), exp, str(ref)],
                                      capture_output=True, text=True)
                self.assertEqual(lauf.returncode, 0, lauf.stderr)
                eigen = d / f"eigen-{exp}.bin"
                erg = modell.gamma_rechnen(float(exp))
                ausgabe.schreibe_lut(eigen, erg, "r")
                self.assertEqual(ref.read_bytes(), eigen.read_bytes(),
                                 f"Exponent {exp} nicht bitgleich")


if __name__ == "__main__":
    unittest.main(verbosity=2)
