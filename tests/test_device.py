import unittest
from unittest.mock import Mock, patch

import device


def settings(**changes):
    return {"password": "  Demo_123!  ", "layout": "fr", "delay_ms": 5000,
            "interval_ms": 30, "press_enter": False, **changes}


class SettingsTests(unittest.TestCase):
    def test_spaces_and_every_printable_ascii_are_preserved(self):
        password = "".join(chr(c) for c in range(32, 127))
        self.assertEqual(device.validate_settings(settings(password=password))["password"], password)
        self.assertEqual(device.validate_settings(settings())["password"], "  Demo_123!  ")

    def test_rejects_invalid_passwords_and_types(self):
        for value in ("", "a" * 129, "café", "x\ny", "x\ty", "a\0b", "🔑", None, 12):
            with self.subTest(value=value), self.assertRaises(device.DeviceError):
                device.validate_settings(settings(password=value))

    def test_timing_layout_and_enter_validation(self):
        for changes in ({"layout": "be"}, {"delay_ms": True}, {"delay_ms": 999},
                        {"delay_ms": 30001}, {"interval_ms": 9}, {"interval_ms": 201},
                        {"interval_ms": 30.0}, {"press_enter": "false"}):
            with self.subTest(changes=changes), self.assertRaises(device.DeviceError):
                device.validate_settings(settings(**changes))

    def test_maximum_length_and_boundaries(self):
        device.validate_settings(settings(password="x" * 128, layout="us", delay_ms=30000, interval_ms=200, press_enter=True))

    def test_button_modes_and_exposed_pins(self):
        for mode in ("usb", "button", "both"):
            for pin in (0, 1, 2, 4, 10, 14, 15, 16, 18, 19, 20, 21):
                validated = device.validate_settings(settings(trigger_mode=mode, trigger_pin=pin))
                self.assertEqual(validated["trigger_pin"], pin)
        for changes in ({"trigger_mode": "automatic"}, {"trigger_pin": 13}, {"trigger_pin": 17},
                        {"trigger_pin": 22}, {"trigger_pin": True}, {"trigger_pin": "4"}):
            with self.subTest(changes=changes), self.assertRaises(device.DeviceError):
                device.validate_settings(settings(**changes))

    def test_empty_password_only_allowed_for_parameter_update(self):
        with self.assertRaises(device.DeviceError):
            device.validate_settings(settings(password=""))
        self.assertEqual(device.validate_settings(settings(password=""), allow_keep=True)["password"], "")


class ProtocolTests(unittest.TestCase):
    def test_ignores_other_protocols_and_reads_firmware_reply(self):
        connection = Mock()
        connection.readline.side_effect = [b"unrelated\n", b"PMK1 invalid json\n", b"PMK1 []\n", b'PMK1 {"protocol":1,"configured":false}\n']
        reply = device.exchange(connection, "INFO")
        self.assertFalse(reply["configured"])
        connection.write.assert_called_once_with(b"PMK1 INFO\n")

    def test_firmware_error_is_reported(self):
        connection = Mock()
        connection.readline.return_value = b'PMK1 {"protocol":1,"error":"invalid_command"}\n'
        with self.assertRaises(device.DeviceError):
            device.exchange(connection, "INFO")

    def test_timeout_does_not_expose_secret_command(self):
        connection = Mock()
        with self.assertRaises(device.DeviceError) as error:
            device.exchange(connection, "SET secret-text", timeout=0)
        self.assertNotIn("secret-text", str(error.exception))

    @patch("device.connect")
    @patch("device.exchange")
    def test_secret_only_sent_after_protocol_handshake(self, exchange, connect):
        exchange.side_effect = device.DeviceError("Unknown firmware")
        with self.assertRaises(device.DeviceError):
            device.configure("/dev/test", settings())
        self.assertEqual(exchange.call_count, 1)
        self.assertEqual(exchange.call_args.args[1], "INFO")

    @patch("device.connect")
    @patch("device.exchange")
    def test_configuration_serializes_hex_without_stripping(self, exchange, connect):
        exchange.side_effect = [{"protocol": 1}, {"protocol": 1, "configured": True, "length": len(settings()["password"])}]
        device.configure("/dev/test", settings())
        command = exchange.call_args.args[1]
        self.assertEqual(command, "SET fr 5000 30 0 " + "  Demo_123!  ".encode().hex())

    @patch("device.connect")
    @patch("device.exchange")
    def test_extended_configuration_includes_mode_and_pin(self, exchange, connect):
        exchange.side_effect = [{"protocol": 2}, {"protocol": 2, "configured": True, "length": len(settings()["password"])}]
        device.configure("/dev/test", settings(trigger_mode="button", trigger_pin=18))
        self.assertEqual(exchange.call_args.args[1], "SET2 fr 5000 30 0 button 18 " + settings()["password"].encode().hex())

    @patch("device.connect")
    @patch("device.exchange")
    def test_parameter_only_update_never_sends_the_existing_password(self, exchange, connect):
        exchange.side_effect = [{"protocol": 2, "configured": True, "length": 20}, {"protocol": 2, "configured": True, "length": 20}]
        device.configure("/dev/test", settings(password="", trigger_mode="both", trigger_pin=4))
        self.assertEqual(exchange.call_args.args[1].strip(), "PARAMS fr 5000 30 0 both 4")

    @patch("device.connect")
    @patch("device.exchange")
    def test_button_requires_firmware_upgrade_before_any_secret_is_sent(self, exchange, connect):
        exchange.return_value = {"protocol": 1, "configured": True, "length": 10}
        with self.assertRaisesRegex(device.DeviceError, "nouveau firmware"):
            device.configure("/dev/test", settings(trigger_mode="button"))
        self.assertEqual(exchange.call_count, 1)

    @patch("device.ports", return_value=[{"port": "/dev/ttyACM0"}])
    def test_rejects_unlisted_paths(self, _):
        for port in ("/etc/passwd", "/dev/ttyS0", None, ["/dev/ttyACM0"]):
            with self.assertRaises(device.DeviceError):
                device.check_port(port)

    def test_both_board_definitions_are_distinct(self):
        self.assertTrue(device.BOARDS["5v16"].endswith("cpu=16MHzatmega32U4"))
        self.assertTrue(device.BOARDS["3v8"].endswith("cpu=8MHzatmega32U4"))
