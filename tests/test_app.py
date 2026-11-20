import re
from html.parser import HTMLParser
import threading
import time
import unittest
from unittest.mock import patch

from app import create_app

PORTS = [{"port": "/dev/ttyACM0", "name": "Test Pro Micro", "vid": 0x2341, "pid": 0x8036, "serial": "test", "location": "1-1"}]
CONFIG = {"port": "/dev/ttyACM0", "password": "unit-test-secret", "layout": "fr", "delay_ms": 5000, "interval_ms": 30, "press_enter": False}


class AppTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app("test-instance")
        self.client = self.app.test_client()
        self.app.testing = True
        self.port_patch = patch("device.ports", return_value=PORTS)
        self.port_patch.start()
        html = self.client.get("/").get_data(as_text=True)
        token = re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)
        self.headers = {"X-CSRF-Token": token}

    def tearDown(self):
        self.app.extensions["worker"].shutdown(wait=True)
        self.port_patch.stop()

    def wait_job(self):
        for _ in range(100):
            job = self.client.get("/api/state").json["job"]
            if job["status"] != "running":
                return job
            time.sleep(0.01)
        self.fail("Job never completed")

    def test_local_page_and_security_headers(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn("3,3 V / 8 MHz", response.get_data(as_text=True))

    def test_generator_and_reset_guide_are_available_with_javascript_module(self):
        html = self.client.get("/").get_data(as_text=True)
        for identifier in ("generate-password", "generator-length", "generator-symbols", "toggle-reset-guide", "reset-guide"):
            self.assertIn(f'id="{identifier}"', html)
        self.assertIn('type="module"', html)
        with self.client.get("/static/password-generator.mjs") as module:
            self.assertEqual(module.status_code, 200)
            self.assertIn("javascript", module.content_type)

    def test_both_board_options_exist_as_selectable_html_options(self):
        class Options(HTMLParser):
            inside = False
            values = None

            def handle_starttag(self, tag, attributes):
                attributes = dict(attributes)
                if tag == "select":
                    self.inside = attributes.get("id") == "board"
                if tag == "option" and self.inside:
                    self.values.append(attributes.get("value"))

            def handle_endtag(self, tag):
                if tag == "select":
                    self.inside = False

        parser = Options()
        parser.values = []
        parser.feed(self.client.get("/").get_data(as_text=True))
        self.assertEqual(parser.values, ["", "5v16", "3v8"])

    @patch("device.recover", return_value={"port": "/dev/ttyACM0", "device": {"protocol": 1}})
    def test_recovery_starts_even_when_normal_usb_port_has_disappeared(self, recover):
        with patch("device.ports", return_value=[]):
            result = self.client.post("/api/recover", json={"board": "5v16"}, headers=self.headers)
            self.assertEqual(result.status_code, 202)
            self.assertEqual(self.wait_job()["status"], "success")
            self.assertEqual(recover.call_args.args[0], "5v16")

    def test_external_hosts_and_origins_are_rejected(self):
        for headers in ({"Host": "evil.example"}, {"Origin": "https://evil.example"}, {"Sec-Fetch-Site": "cross-site"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.client.get("/api/state", headers=headers).status_code, 403)

    def test_write_requires_csrf_token_and_json_object(self):
        self.assertEqual(self.client.post("/api/configure", json=CONFIG).status_code, 403)
        self.assertEqual(self.client.post("/api/tools", data="x", headers=self.headers).status_code, 415)
        self.assertEqual(self.client.post("/api/tools", json=[], headers=self.headers).status_code, 400)

    def test_input_validation_precedes_async_task(self):
        self.assertEqual(self.client.post("/api/configure", json={**CONFIG, "password": "bad\n"}, headers=self.headers).status_code, 400)
        self.assertEqual(self.client.post("/api/flash", json={"port": "/dev/ttyACM0", "board": []}, headers=self.headers).status_code, 400)

    @patch("device.configure", return_value={"protocol": 1, "configured": True, "length": 16})
    def test_secret_does_not_appear_in_job_state_or_log(self, configure):
        response = self.client.post("/api/configure", json=CONFIG, headers=self.headers)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.wait_job()["status"], "success")
        self.assertNotIn(CONFIG["password"], self.client.get("/api/state").get_data(as_text=True))
        self.assertNotIn(CONFIG["password"].encode().hex(), self.client.get("/api/state").get_data(as_text=True))

    def test_concurrent_usb_operations_are_refused(self):
        started, release = threading.Event(), threading.Event()

        def wait(*_):
            started.set()
            release.wait(3)
            return {"protocol": 1}

        with patch("device.info", side_effect=wait):
            try:
                self.client.post("/api/device", json={"port": "/dev/ttyACM0"}, headers=self.headers)
                self.assertTrue(started.wait(1))
                response = self.client.post("/api/clear", json={"port": "/dev/ttyACM0"}, headers=self.headers)
                self.assertEqual(response.status_code, 409)
            finally:
                release.set()
            self.assertEqual(self.wait_job()["status"], "success")

    @patch("device.info", side_effect=RuntimeError("unexpected sensitive data"))
    def test_unexpected_exceptions_are_sanitized(self, _):
        self.client.post("/api/device", json={"port": "/dev/ttyACM0"}, headers=self.headers)
        job = self.wait_job()
        self.assertEqual(job["status"], "error")
        self.assertNotIn("sensitive", str(job))
