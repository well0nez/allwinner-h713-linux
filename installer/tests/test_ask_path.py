"""Deep review 27.09.2026: the two new prompts keep the case of a path and expand ~ to the
invoking user's home under sudo."""
import os
import pwd
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from h713 import install as install_mod   # noqa: E402


class AskPath(unittest.TestCase):
    def test_the_case_is_kept(self):
        self.assertEqual(install_mod.ask_path("? ", "", _input=lambda t: " /media/USB/My-Dump ", _isatty=True),
                         "/media/USB/My-Dump")

    def test_empty_is_the_default(self):
        self.assertEqual(install_mod.ask_path("? ", "x", _input=lambda t: "", _isatty=True), "x")

    def test_no_terminal_is_the_default(self):
        self.assertEqual(install_mod.ask_path("? ", "d", _input=lambda t: "/z", _isatty=False), "d")

    def test_tilde_is_the_sudo_users_home(self):
        me = pwd.getpwuid(os.getuid())
        old = os.environ.get("SUDO_USER")
        os.environ["SUDO_USER"] = me.pw_name
        try:
            self.assertEqual(install_mod.ask_path("? ", "", _input=lambda t: "~/k.pub", _isatty=True),
                             me.pw_dir + "/k.pub")
        finally:
            if old is None:
                del os.environ["SUDO_USER"]
            else:
                os.environ["SUDO_USER"] = old


if __name__ == "__main__":
    unittest.main()
