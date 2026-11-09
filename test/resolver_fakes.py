# -*- coding: utf-8 -*-
"""Shared fakes for the resolver tests (not a test module itself)."""

import json

from resolver.cache import Cache
from resolver.http import HttpResponse
from resolver.log import Logger
from resolver.settings import Settings

PUBLIC_IP = "93.184.216.34"


def fake_dns(_host, _port):
    return [PUBLIC_IP]


class FakeAddon(object):
    def __init__(self, values=None):
        self.values = dict(values or {})

    def getSetting(self, key):
        return self.values.get(key, "")


def make_settings(**overrides):
    values = {
        "resolver_service_url": "",
        "resolver_service_token": "",
        "resolver_enable_mega": "false",
        "resolver_http_timeout": "20",
        "resolver_service_timeout": "25",
        "resolver_cache_dir": "",
        "resolver_cache_ttl": "0",
    }
    values.update(overrides)
    return Settings(addon=FakeAddon(values))


def temp_cache(directory, ttl=300, clock=None):
    return Cache(directory, ttl=ttl, clock=clock)


class FakeHTTP(object):
    """Queued fake with ``fetch`` and ``request`` entry points."""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    def _next(self, kind, args, kwargs):
        self.calls.append((kind, args, kwargs))
        if not self.responses:
            raise AssertionError("unexpected HTTP %s" % kind)
        response = self.responses.pop(0)
        if callable(response):
            return response(*args, **kwargs)
        if isinstance(response, Exception):
            raise response
        return response

    def fetch(self, *args, **kwargs):
        return self._next("fetch", args, kwargs)

    def request(self, *args, **kwargs):
        return self._next("request", args, kwargs)

    def count(self, kind=None):
        if kind is None:
            return len(self.calls)
        return sum(1 for call in self.calls if call[0] == kind)


def response(body="", status=200, url="https://example.invalid/", headers=None):
    if isinstance(body, dict):
        body = json.dumps(body)
    if isinstance(body, str):
        body = body.encode("utf-8")
    return HttpResponse(status, headers or {}, body, url)


class RecordingLogger(Logger):
    def __init__(self, secrets=None):
        self.messages = []
        Logger.__init__(self, sink=self._record, secrets=secrets)

    def _record(self, message, level):
        self.messages.append((level, message))

    def text(self):
        return "\n".join(message for _level, message in self.messages)
