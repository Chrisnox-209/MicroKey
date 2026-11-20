from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import device

BOOT = {"port": "/dev/ttyACM0", "vid": 0x2341, "pid": 0x0036, "location": "1-1", "serial": None}


class RecoveryTests(unittest.TestCase):
    def test_wrong_frequency_is_rejected_before_compilation_or_upload(self):
        with patch("device.ports", return_value=[{**BOOT, "pid": 0x8036}]), patch("device.compile_firmware") as compile:
            with self.assertRaisesRegex(device.DeviceError, "16 MHz"):
                device.flash("/dev/ttyACM0", "3v8", Mock())
            compile.assert_not_called()

    def test_known_8mhz_board_profile_is_supported(self):
        device.check_board_profile({"vid": 0x1B4F, "pid": 0x9204}, "3v8")
        with self.assertRaises(device.DeviceError):
            device.check_board_profile({"vid": 0x1B4F, "pid": 0x9204}, "5v16")

    def environment(self, stack, candidates):
        temporary = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="promicro-recovery-")))
        binary = temporary / "data/packages/arduino/tools/avrdude/test/bin/avrdude"
        binary.parent.mkdir(parents=True)
        binary.touch()
        config = binary.parent.parent / "etc/avrdude.conf"
        config.parent.mkdir()
        config.touch()
        build = temporary / "build"
        build.mkdir()
        (build / "promicro_key.ino.hex").touch()
        stack.enter_context(patch("device.TOOL_DIR", temporary))
        stack.enter_context(patch("device.compile_firmware", return_value=build))
        stack.enter_context(patch("device.ports", return_value=candidates))
        run = stack.enter_context(patch("device.run_command"))
        verify = stack.enter_context(patch("device.verify_after_flash", return_value={"port": BOOT["port"]}))
        return run, verify

    def test_recovery_preserves_eeprom_verifies_flash_and_skips_serial_reset(self):
        with ExitStack() as stack:
            run, verify = self.environment(stack, [BOOT])
            device.recover("5v16", Mock())
            command = run.call_args.args[0]
            self.assertIn("avr109", command)
            self.assertIn("-D", command)
            self.assertNotIn("-V", command)
            self.assertNotIn("-e", command)
            self.assertNotIn("1200", command)
            self.assertEqual(command[command.index("-P") + 1], BOOT["port"])
            verify.assert_called_once()

    def test_recovery_refuses_incompatible_bootloader(self):
        with ExitStack() as stack:
            run, verify = self.environment(stack, [BOOT])
            with self.assertRaises(device.DeviceError):
                device.recover("3v8", Mock())
            run.assert_not_called()

    def test_recovery_refuses_ambiguous_devices(self):
        with ExitStack() as stack:
            run, verify = self.environment(stack, [BOOT, {**BOOT, "port": "/dev/ttyACM1"}])
            with self.assertRaisesRegex(device.DeviceError, "Plusieurs"):
                device.recover("5v16", Mock())
            run.assert_not_called()

    def test_recovery_timeout_is_actionable_and_never_uploads(self):
        with ExitStack() as stack:
            run, verify = self.environment(stack, [])
            with self.assertRaisesRegex(device.DeviceError, "RST"):
                device.recover("5v16", Mock(), timeout=0)
            run.assert_not_called()

    def test_fresh_recovery_waits_for_disconnection_before_upload(self):
        with ExitStack() as stack:
            run, verify = self.environment(stack, [])
            ports = stack.enter_context(patch("device.ports", side_effect=[[BOOT], [], [BOOT]]))
            stack.enter_context(patch("device.time.sleep"))
            device.recover("5v16", Mock(), require_disconnect=True)
            self.assertEqual(ports.call_count, 3)
            run.assert_called_once()
