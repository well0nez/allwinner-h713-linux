"""Test of the polkit rule for Kodi's own power menu (rootfs/overlay-desktop/etc/polkit-1/rules.d/50-h713-kodi.rules): the rule is run
by node against a stand-in for polkit's JavaScript object. polkitd's engine (duktape) is ES5; the rule uses nothing newer.
What the rule must do: YES for the user h713-kodi and the six logind actions, and no answer (the next rule decides) for anything else."""
import json
import os
import shutil
import subprocess
import unittest

RULE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "rootfs", "overlay-desktop",
                    "etc", "polkit-1", "rules.d", "50-h713-kodi.rules")
ALLOWED = ["suspend", "suspend-multiple-sessions", "power-off", "power-off-multiple-sessions", "reboot", "reboot-multiple-sessions"]
SHIM = """
var rule = null;
var polkit = {addRule: function (f) { rule = f; }, Result: {YES: "yes", NO: "no", AUTH_ADMIN: "auth_admin"}};
eval(require("fs").readFileSync(process.argv[1], "utf8"));
var cases = JSON.parse(process.argv[2]);
console.log(JSON.stringify(cases.map(function (c) { return [c[0], c[1], String(rule({id: c[1]}, {user: c[0]}))]; })));
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class TestRule(unittest.TestCase):
    def answers(self, cases):
        out = subprocess.run(["node", "-e", SHIM, RULE, json.dumps(cases)], capture_output=True, text=True, timeout=30, check=True)
        return {(u, a): r for u, a, r in json.loads(out.stdout)}

    def test_the_kodi_user_gets_the_six_actions(self):
        got = self.answers([["h713-kodi", "org.freedesktop.login1." + a] for a in ALLOWED])
        self.assertEqual(set(got.values()), {"yes"})
        self.assertEqual(len(got), 6)

    def test_nothing_else_for_the_kodi_user(self):
        others = ["hibernate", "suspend-ignore-inhibit", "power-off-ignore-inhibit", "reboot-ignore-inhibit", "set-wall-message",
                  "halt", "manage-units", "lock-sessions", "inhibit-block-shutdown"]
        got = self.answers([["h713-kodi", "org.freedesktop.login1." + a] for a in others] +
                           [["h713-kodi", "org.freedesktop.systemd1.manage-units"], ["h713-kodi", "org.freedesktop.NetworkManager.settings.modify.system"]])
        self.assertEqual(set(got.values()), {"undefined"}, got)

    def test_nothing_for_other_users(self):
        got = self.answers([[u, "org.freedesktop.login1.suspend"] for u in ["root", "h713-desktop", "h713-kodi2", "xh713-kodi", "nobody"]])
        self.assertEqual(set(got.values()), {"undefined"}, got)


if __name__ == "__main__":
    unittest.main()
