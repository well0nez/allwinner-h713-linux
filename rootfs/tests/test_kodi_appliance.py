"""Tests for the image's Kodi defaults (rootfs/overlay-desktop/usr/share/kodi/system/settings/appliance.xml) and rootfs/check-kodi-appliance.py,
which build-rootfs.sh runs against the built tree. No Kodi, no device."""
import importlib.util
import os
import unittest
import xml.etree.ElementTree as ET

ROOTFS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
spec = importlib.util.spec_from_file_location("check_kodi_appliance", os.path.join(ROOTFS, "check-kodi-appliance.py"))
chk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chk)

OVERLAY = os.path.join(ROOTFS, "overlay-desktop")
# what the image wants of Kodi (the values the first guisettings.xml of the image used to carry)
IMAGE_DEFAULTS = {
    "audiooutput.audiodevice": "ALSA:@|Default (hy310hdmi Device sounds, mixed into HDMI)",
    "services.esenabled": "true", "services.esallinterfaces": "false", "services.webserver": "false", "services.zeroconf": "false",
    "services.wsdiscovery": "false", "screensaver.mode": "", "powermanagement.displaysoff": "0", "videoplayer.usevaapimpeg2": "true",
}


def parse(text):
    return ET.fromstring(text)


# a made-up Kodi: two settings, where settings.xml has them
KODI = parse('<settings><section id="services"><category id="smb"><group id="3"><setting id="services.wsdiscovery"/></group></category>'
             '<category id="control"><group id="2"><setting id="services.esenabled"/></group></category></section></settings>')


def appliance(smb_group="3", extra="", sid="services.wsdiscovery"):
    return parse('<settings><section id="services"><category id="smb"><group id="%s"><setting id="%s"><default>false</default>%s</setting>'
                 '</group></category></section></settings>' % (smb_group, sid, extra))


class ApplianceTest(unittest.TestCase):
    def test_the_image_names_its_defaults_to_kodi(self):
        root = ET.parse(os.path.join(OVERLAY, chk.APPLIANCE)).getroot()
        self.assertEqual({s.get("id"): (s.find("default").text or "") for s in root.iter("setting")}, IMAGE_DEFAULTS)

    def test_the_image_lays_no_guisettings_of_its_own(self):
        """Kodi writes that file at every exit: a copy of the image's values in it is the owner's choice to Kodi, and a reset or a lost file
        brings Kodi's own defaults back instead of the image's (measured on the HY300PRO-G-EU: audio device "Default", zeroconf and
        WS-Discovery on, no VA-API for MPEG-2)"""
        self.assertFalse(os.path.exists(os.path.join(OVERLAY, chk.SEED)))

    def test_what_kodi_fixes_by_its_capabilities_is_not_pinned_here(self):
        """powermanagement.shutdownstate is 0 whatever appliance.xml says when Kodi starts without CanPowerDown (measured): no default of ours holds"""
        ids = {s.get("id") for s in ET.parse(os.path.join(OVERLAY, chk.APPLIANCE)).getroot().iter("setting")}
        self.assertNotIn("powermanagement.shutdownstate", ids)

    def test_the_checker_takes_the_overlay(self):
        self.assertEqual(chk.main(), 0)

    def test_the_checker_takes_a_setting_where_kodi_has_it(self):
        self.assertEqual(chk.problems(appliance(), [KODI]), [])

    def test_the_checker_finds_a_setting_in_the_wrong_group(self):
        """Kodi would not apply it, and say nothing"""
        found = chk.problems(appliance(smb_group="1"), [KODI])
        self.assertEqual(len(found), 1)
        self.assertIn("Kodi has it in services/smb/3, appliance.xml in services/smb/1", found[0])

    def test_the_checker_finds_a_setting_that_kodi_does_not_have(self):
        self.assertIn("services.wsdiscovry: not a setting of this Kodi", chk.problems(appliance(sid="services.wsdiscovry"), [KODI]))

    def test_the_checker_finds_more_than_a_default(self):
        self.assertTrue(any("only <default>" in p for p in chk.problems(appliance(extra="<visible>false</visible>"), [KODI])))

    def test_the_checker_finds_a_guisettings_of_the_images(self):
        self.assertTrue(any("guisettings.xml" in p for p in chk.problems(appliance(), [KODI], seed_there=True)))


if __name__ == "__main__":
    unittest.main()
