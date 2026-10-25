"""Host tests of h713-mic: no device, no voice recording. `make test`."""
import importlib.machinery
import importlib.util
import os
import random
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_loader = importlib.machinery.SourceFileLoader("h713mic", os.path.join(HERE, "..", "h713-mic"))
_spec = importlib.util.spec_from_loader("h713mic", _loader)
mic = importlib.util.module_from_spec(_spec)
_loader.exec_module(mic)

# The packet both remotes (HY310, HY300PRO-G-EU) send ~10 times at the start of a press (11.10.2026 captures).
STARTUP = bytes.fromhex("70cc57a899bb974016a847fbd489f456518fc08e9d4c08a74638104551fa48a6a7a04149a7a63d1183f0a4"
                        "64dcee5ab399a49fa465e2f15fe963ebf7")


def read(path):
    with open(path, "rb") as f:
        return f.read()


def scramble(plain):
    """The remote's side: the inverse of mic.unscramble."""
    b = bytearray(plain)
    b[0] = ((b[0] ^ mic.KEY) + 62) & 0xFF
    for i in range(1, len(mic.ORDER)):
        b[mic.ORDER[i]] = ((b[mic.ORDER[i]] ^ (i ^ mic.KEY)) - b[mic.ORDER[i - 1]]) & 0xFF
    return bytes(b)


class Mic(unittest.TestCase):
    def test_unscramble_inverts_the_scrambling(self):
        rnd = random.Random(7)
        for _ in range(500):
            piece = bytes(rnd.randrange(256) for _ in range(20))
            self.assertEqual(mic.unscramble(scramble(piece)), piece)
            self.assertEqual(scramble(mic.unscramble(piece)), piece)

    def test_the_startup_packet_is_sbc_silence(self):
        frame = mic.sbc_frame(STARTUP)
        self.assertEqual(len(frame), 64)
        self.assertEqual(frame[:3], bytes([0x9C, 0x31, 0x1C]))
        self.assertEqual(frame[4:8], bytes(4))                # all scale factors 0
        self.assertEqual(frame[8:12], bytes.fromhex("77776db7"))   # mid values

    def test_only_voice_reports_are_taken(self):
        self.assertEqual(mic.voice_payload(bytes([0x1E]) + STARTUP), STARTUP)
        self.assertIsNone(mic.voice_payload(bytes([0x03, 0xCF, 0x00])))
        self.assertIsNone(mic.voice_payload(bytes([0x1E]) + STARTUP[:59]))
        with self.assertRaises(ValueError):
            mic.sbc_frame(STARTUP[:59])

    def test_report_sizes_from_a_descriptor(self):
        rdesc = bytes([0x05, 0x0C, 0x09, 0x01, 0xA1, 0x01, 0x85, 0x03, 0x19, 0x00, 0x2A, 0x9C, 0x02,
                       0x15, 0x00, 0x26, 0x9C, 0x02, 0x95, 0x02, 0x75, 0x10, 0x81, 0x00, 0xC0,
                       0x06, 0x00, 0xFF, 0x09, 0x01, 0xA1, 0x01, 0x85, 0x1E, 0x75, 0x08, 0x95, 0x3C,
                       0x81, 0x02, 0xC0])
        sizes = mic.report_sizes(rdesc)
        self.assertEqual(sizes[0x03], 32)
        self.assertEqual(sizes[0x1E], 480)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is not installed")
    def test_round_trip_through_a_reference_encoder(self):
        """ffmpeg's SBC encoder at 64 kbit/s makes exactly the remote's frames (9c 31 1c); stripped and scrambled
        like the remote does it, convert must give the encoder's stream back bit for bit, header and CRC too."""
        with tempfile.TemporaryDirectory() as tmp:
            ref = os.path.join(tmp, "ref.sbc")
            subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                            "sine=frequency=440:sample_rate=16000:duration=0.5", "-ac", "1", "-c:a", "sbc",
                            "-b:a", "64k", "-f", "sbc", ref], check=True)
            data = read(ref)
            frames = [data[i:i + 64] for i in range(0, len(data), 64)]
            self.assertTrue(frames and all(f[:3] == bytes([0x9C, 0x31, 0x1C]) for f in frames))
            cap = os.path.join(tmp, "capture.txt")
            with open(cap, "w") as f:
                for n, fr in enumerate(frames):
                    body = fr[4:]
                    report = b"".join(scramble(body[i:i + 20]) for i in (0, 20, 40))
                    f.write("00:00:%09.6f %s\n" % (n * 0.008, (bytes([0x1E]) + report if n % 2 else report).hex()))
            out = os.path.join(tmp, "out.sbc")
            self.assertEqual(mic.main(["convert", cap, out]), 0)
            self.assertEqual(read(out), data)


if __name__ == "__main__":
    unittest.main()
