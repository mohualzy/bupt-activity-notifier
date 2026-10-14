"""Loopback HTTP integration test: exercise real requests without real QQ or tokens."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bupt_activity_notifier.filtering import Activity
from bupt_activity_notifier.notifications import Notifier


class StubOneBot(BaseHTTPRequestHandler):
    received = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        StubOneBot.received.append((self.path, json.loads(raw.decode("utf-8"))))
        reply = json.dumps({"status": "ok", "retcode": 0, "data": {"message_id": 1}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, *args):
        pass


class LocalHTTPIntegrationTests(unittest.TestCase):
    def test_onebot_real_loopback_request(self):
        StubOneBot.received = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), StubOneBot)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            activity = Activity.from_raw({
                "id": 123, "name": "完全虚构的测试活动", "area": 1,
                "demands": 2, "location": "模拟场地",
            })
            channel = Notifier(
                onebot_url=f"http://127.0.0.1:{server.server_port}",
                onebot_user_id="12345",
            )
            channel.send_channel("onebot_private", activity)
            self.assertEqual(len(StubOneBot.received), 1)
            path, payload = StubOneBot.received[0]
            self.assertEqual(path, "/send_private_msg")
            self.assertTrue(payload["auto_escape"])
            self.assertIn("完全虚构", payload["message"])
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
