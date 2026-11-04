# -*- coding: utf-8 -*-
"""Per-host RaveTapePacks egress for the Kodi add-on.

Offline: a local mock proxy and a local target server stand in for the VPN
host and for the rest of the internet.
"""

import http.server as httpserver
import os
import socket
import sys
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

from resources.lib import http  # noqa: E402


def _closed_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class _Server(object):
    def __init__(self, handler):
        self.requests = []
        self._httpd = httpserver.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._httpd.requests = self.requests
        self.url = "http://127.0.0.1:%d" % self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def close(self):
        self._httpd.shutdown()
        self._httpd.server_close()


class _ProxyHandler(httpserver.BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.requests.append({
            "path": self.path,
            "headers": {key.lower(): value for key, value in self.headers.items()},
        })
        if "redirect-private" in self.path:
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1/private")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if "redirect-rtp" in self.path:
            self.send_response(302)
            self.send_header("Location", "http://www.ravetapepacks.com/final")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = b"proxy-body"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_CONNECT = do_GET

    def log_message(self, *args):
        pass


class _TargetHandler(httpserver.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"direct-body"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class _Base(unittest.TestCase):
    def setUp(self):
        self._saved = {}
        for key in ("RTP_EGRESS_PROXY", "RTP_EGRESS_HOSTS", "RTP_EGRESS_FALLBACK"):
            self._saved[key] = os.environ.pop(key, None)
        proxy_httpd = _Server(_ProxyHandler)
        self.proxy = proxy_httpd
        self.target = _Server(_TargetHandler)

    def tearDown(self):
        self.proxy.close()
        self.target.close()
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class EgressRoutingTest(_Base):
    def test_proxy_only_for_rtp_hosts(self):
        os.environ["RTP_EGRESS_PROXY"] = self.proxy.url
        self.assertEqual(http.fetch("http://www.ravetapepacks.com/page"), "proxy-body")
        self.assertEqual(len(self.proxy.requests), 1)
        self.assertTrue(self.proxy.requests[0]["path"].startswith(
            "http://www.ravetapepacks.com/"))

        self.proxy.requests.clear()
        self.assertEqual(http.fetch(self.target.url + "/other.mp3"), "direct-body")
        self.assertEqual(self.proxy.requests, [])

    def test_headers_survive_the_proxy(self):
        os.environ["RTP_EGRESS_PROXY"] = self.proxy.url
        body = http.fetch(
            "http://www.ravetapepacks.com/",
            headers={"User-Agent": "Mozilla/5.0",
                     "Referer": "https://www.ravetapepacks.com/",
                     "Accept": "text/html"},
        )
        self.assertEqual(body, "proxy-body")
        sent = self.proxy.requests[0]["headers"]
        self.assertEqual(sent["user-agent"], "Mozilla/5.0")
        self.assertEqual(sent["referer"], "https://www.ravetapepacks.com/")
        self.assertEqual(sent["accept"], "text/html")

    def test_proxy_down_falls_back_direct(self):
        os.environ["RTP_EGRESS_PROXY"] = "http://127.0.0.1:%d" % _closed_port()
        os.environ["RTP_EGRESS_HOSTS"] = "127.0.0.1"
        self.assertEqual(http.fetch(self.target.url + "/page"), "direct-body")
        self.assertEqual(self.proxy.requests, [])

    def test_redirect_to_private_still_refused(self):
        os.environ["RTP_EGRESS_PROXY"] = self.proxy.url
        self.assertIsNone(http.fetch(
            "http://www.ravetapepacks.com/redirect-private"))
        self.assertEqual(len(self.proxy.requests), 1)

    def test_redirect_inside_rtp_stays_proxied(self):
        os.environ["RTP_EGRESS_PROXY"] = self.proxy.url
        self.assertEqual(
            http.fetch("http://www.ravetapepacks.com/redirect-rtp"),
            "proxy-body")
        self.assertEqual(len(self.proxy.requests), 2)

    def test_egress_host_boundaries(self):
        os.environ.pop("RTP_EGRESS_HOSTS", None)
        self.assertTrue(http.is_egress_host("www.ravetapepacks.com"))
        self.assertTrue(http.is_egress_host("https://ravetapepacks.com/x"))
        self.assertFalse(http.is_egress_host("notravetapepacks.com"))
        self.assertFalse(http.is_egress_host("example.com"))

    def test_proxy_config_normalisation(self):
        os.environ["RTP_EGRESS_PROXY"] = "192.0.2.10:8888"
        self.assertEqual(http.egress_proxy(), "http://192.0.2.10:8888")
        os.environ["RTP_EGRESS_PROXY"] = "http://user:pass@proxy.example:3128"
        self.assertEqual(http.egress_proxy(),
                         "http://user:pass@proxy.example:3128")
        os.environ["RTP_EGRESS_PROXY"] = "http://proxy.example:3128/path"
        self.assertEqual(http.egress_proxy(), "")

    def test_setting_is_used_when_env_is_empty(self):
        from resources.lib import kodi

        original = kodi.setting

        def fake_setting(name, default=""):
            if name == http.EGRESS_PROXY_SETTING:
                return "http://192.0.2.10:8888"
            return original(name, default)

        kodi.setting = fake_setting
        try:
            self.assertEqual(http.egress_proxy(), "http://192.0.2.10:8888")
        finally:
            kodi.setting = original


if __name__ == "__main__":
    unittest.main()
