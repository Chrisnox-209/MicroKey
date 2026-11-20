from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("g++"), "g++ absent : simulation native du firmware ignorée")
class FirmwareTests(unittest.TestCase):
    def test_firmware_lifecycle_and_eeprom(self):
        with tempfile.TemporaryDirectory(prefix="promicro-firmware-") as temporary:
            binary = str(Path(temporary) / "firmware_test")
            subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-I", str(ROOT / "tests" / "firmware"),
                            str(ROOT / "tests" / "firmware" / "firmware_test.cpp"), "-o", binary], check=True, capture_output=True, text=True)
            result = subprocess.run([binary], check=True, capture_output=True, text=True)
            self.assertIn("Firmware scenarios passed", result.stdout)
