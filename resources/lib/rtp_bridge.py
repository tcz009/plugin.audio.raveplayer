# -*- coding: utf-8 -*-
"""Tiny loopback bridge for RaveTapePacks + JungleTapes playback.

Kodi's player cannot use the add-on's HTTP proxy directly, and on the Shield
its libcurl fetch of a JungleTapes MP3 host stalls (`CFileCache::Open failed`)
while the add-on's own Python fetch works.  This module starts a server on
127.0.0.1 with a random token; only allowlisted playback hosts (RTP egress
hosts plus JungleTapes) can be fetched through it, and every upstream request
uses the same SSRF guards as the rest of the add-on.  The server is bounded per
request and closed by the play route in a finally block.
"""

import base64
import http.server as http_server
import secrets
import threading
import urllib.parse

import xbmc

from . import http, kodi

BRIDGE_TIMEOUT = 20.0
READ_CHUNK = 64 * 1024
FORWARD_HEADERS = ("Range", "If-Range", "Accept", "User-Agent", "Referer")


def _b64(text):
    return base64.urlsafe_b64encode(str(text).encode("utf-8")).decode("ascii").rstrip("=")


def _unb64(text):
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding).decode("utf-8", "replace")


class _Handler(http_server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _reject(self, code=403):
        try:
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()
        except Exception:
            pass

    def do_HEAD(self):
        self._serve(head=True)

    def do_GET(self):
        self._serve(head=False)

    def _serve(self, head=False):
        bridge = getattr(self.server, "bridge", None)
        if bridge is None:
            self._reject(404)
            return
        path = urllib.parse.urlsplit(self.path).path
        parts = [part for part in path.split("/") if part]
        if len(parts) != 2 or not secrets.compare_digest(parts[0], bridge.token):
            self._reject(403)
            return
        try:
            target = _unb64(parts[1])
        except Exception:
            self._reject(400)
            return
        # The bridge is never an open proxy: only hosts on its allowlist
        # (RaveTapePacks egress + JungleTapes playback) may be bridged.
        if not http.is_bridge_host(target):
            self._reject(403)
            return
        forwarded = {}
        for name in FORWARD_HEADERS:
            value = self.headers.get(name)
            if value:
                forwarded[name] = value
        try:
            with http.open_media(target, timeout=BRIDGE_TIMEOUT,
                                 headers=forwarded,
                                 method="HEAD" if head else "GET") as upstream:
                final = getattr(upstream, "geturl", lambda: target)()
                if not http.is_bridge_host(final):
                    self._reject(502)
                    return
                status = int(getattr(upstream, "status", 200) or 200)
                self.send_response(status)
                for name in ("Content-Type", "Content-Length", "Content-Range",
                             "Accept-Ranges", "Last-Modified", "ETag", "Cache-Control"):
                    value = upstream.headers.get(name) if upstream.headers else None
                    if value:
                        self.send_header(name, value)
                self.end_headers()
                if head:
                    return
                while True:
                    chunk = upstream.read(READ_CHUNK)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:
            kodi.log("RTP bridge request failed (%s)" % exc.__class__.__name__,
                     level=xbmc.LOGDEBUG)
            if not head:
                self._reject(502)


class _Server(http_server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class RTPBridge(object):
    """Start/stop the loopback bridge; failures are quiet and non-fatal."""

    def __init__(self, port=0):
        self.token = secrets.token_urlsafe(24)
        self._httpd = None
        self._thread = None
        self.port = 0
        self._port_wanted = int(port or 0)

    def start(self):
        if self._httpd is not None:
            return True
        try:
            self._httpd = _Server(("127.0.0.1", self._port_wanted), _Handler)
            self._httpd.bridge = self
            self.port = self._httpd.server_address[1]
            self._thread = threading.Thread(target=self._httpd.serve_forever,
                                            daemon=True)
            self._thread.start()
            kodi.log("RTP bridge listening on 127.0.0.1:%d" % self.port,
                     level=xbmc.LOGDEBUG)
            return True
        except Exception as exc:
            kodi.log("RTP bridge unavailable (%s)" % exc.__class__.__name__,
                     level=xbmc.LOGDEBUG)
            self.close()
            return False

    def url_for(self, target):
        """Return a loopback URL for a bridge-eligible target, or ''.

        RaveTapePacks (egress proxy) and JungleTapes (Kodi's libcurl stalls on
        its MP3 host on the Shield) are eligible; everything else is refused.
        """
        text = str(target or "")
        if not http.is_bridge_host(text) or not self._httpd:
            return ""
        return "http://127.0.0.1:%d/%s/%s" % (self.port, self.token, _b64(text))

    def wait_for_playback(self, grace=15.0, poll=0.5):
        """Keep the loopback server alive while Kodi is playing the bridge URL."""
        player = xbmc.Player()
        waited = 0.0
        seen = False
        while waited < 6 * 60 * 60:
            try:
                playing = bool(player.isPlaying())
            except Exception:
                playing = False
            if playing:
                seen = True
            elif seen or waited >= grace:
                return
            xbmc.sleep(max(1, int(poll * 1000)))
            waited += poll

    def close(self):
        httpd = self._httpd
        self._httpd = None
        if httpd is not None:
            try:
                httpd.shutdown()
            except Exception:
                pass
            try:
                httpd.server_close()
            except Exception:
                pass
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            try:
                thread.join(0.5)
            except Exception:
                pass
