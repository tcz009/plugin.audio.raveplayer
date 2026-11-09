# -*- coding: utf-8 -*-
"""Per-registrable-domain token bucket for resolver network work.

The Kodi SDK used to have no shared request budget: Mediafire had its own
courtesy gap, Drive had none, and a 429 from one provider was forgotten before
the service fallback ran.  This module mirrors the web resolver's
:class:`TokenBucket` policy so both sides of the system slow down the same
way:

* one bucket per **registrable domain** (``n1``/``n2.mediafire.com`` share a
  bucket; ``drive.google.com`` and ``docs.google.com`` share ``google.com``);
* a bounded LRU of buckets, so a caller cannot mint state per random
  subdomain forever;
* ``block()`` records a provider's ``Retry-After`` and refuses further work
  until it elapses;
* the clock is injectable and defaults to ``time.monotonic`` so wall-clock
  changes cannot mint tokens.

The limiter is deliberately transport-agnostic: the manager calls :meth:`take`
once per resolution attempt and :meth:`block` when an adapter or the service
answers 429.  Direct audio files (no provider page and no network fetch) are
not gated, so a play-all of archive.org tracks is unaffected.
"""

import collections
import ipaddress
import math
import threading
import time

from . import policy

DEFAULT_RATE_PER_MINUTE = 60.0
DEFAULT_BURST = 10.0
MAX_KEYS = 256
MAX_BACKOFF = 120

# A deliberately small public-suffix subset, matching the web resolver.  It
# covers the providers this SDK knows about (``mega.co.nz``) without pulling
# in an optional public-suffix package.  Anything else falls back to the last
# two labels.
_MULTI_LABEL_SUFFIXES = frozenset((
    "ac.uk", "co.uk", "gov.uk", "ltd.uk", "me.uk", "net.uk", "nhs.uk",
    "org.uk", "plc.uk", "police.uk", "sch.uk",
    "ac.nz", "co.nz", "geek.nz", "govt.nz", "net.nz", "org.nz", "school.nz",
    "com.au", "edu.au", "gov.au", "net.au", "org.au",
    "com.br", "com.mx", "com.sg", "com.tr", "com.tw", "com.hk",
    "co.il", "co.in", "co.jp", "co.kr", "co.za", "ne.jp", "or.jp",
))


def registrable_domain(host):
    """Return the registrable domain used for per-provider rate limiting.

    ``n12.mediafire.com``, ``download1.mediafire.com`` and ``mediafire.com``
    share one bucket.  IP literals and single-label hosts are returned
    unchanged.  This is the same deliberately small suffix list the web
    resolver uses, so Kodi and the NAS agree on bucket keys.
    """
    host = str(host or "").strip().lower().rstrip(".")
    if not host:
        return ""
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    last_two = ".".join(labels[-2:])
    if last_two in _MULTI_LABEL_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return last_two


def domain_for(url):
    """Return the bucket key for a URL, or ``""`` when it has no host."""
    parts = policy.split_url(url)
    if parts is None:
        return ""
    return registrable_domain(parts.hostname)


def _ceil_seconds(value):
    try:
        return max(1, int(math.ceil(float(value))))
    except (TypeError, ValueError, OverflowError):
        return 1


class DomainRateLimiter(object):
    """Bounded per-domain token bucket with 429 back-off state."""

    def __init__(self, rate_per_minute=DEFAULT_RATE_PER_MINUTE,
                 burst=DEFAULT_BURST, clock=None, max_keys=MAX_KEYS):
        self.rate_per_minute = _non_negative(rate_per_minute,
                                             DEFAULT_RATE_PER_MINUTE)
        self.rate_per_second = self.rate_per_minute / 60.0
        self.burst = max(1.0, _non_negative(burst, DEFAULT_BURST))
        self.clock = clock or time.monotonic
        self.max_keys = max(1, int(max_keys))
        self._lock = threading.Lock()
        # key -> [tokens, last_refill, blocked_until]
        self._state = collections.OrderedDict()

    def take(self, url=None, key=None):
        """Consume one token for the URL's domain.

        Returns ``0`` when the caller may proceed, or a positive ``Retry-After``
        in seconds.  A blocked domain never consumes a token.
        """
        bucket = str(key or domain_for(url) or "").lower()
        if self.rate_per_second <= 0:
            return 0
        if not bucket:
            return 0
        now = self.clock()
        with self._lock:
            tokens, last, blocked = self._state.get(
                bucket, (self.burst, now, 0.0))
            if blocked > now:
                self._touch(bucket, tokens, last, blocked)
                return _ceil_seconds(blocked - now)
            elapsed = max(0.0, now - last)
            tokens = min(self.burst, tokens + elapsed * self.rate_per_second)
            if tokens >= 1.0:
                self._touch(bucket, tokens - 1.0, now, 0.0)
                return 0
            wait = (1.0 - tokens) / self.rate_per_second
            self._touch(bucket, tokens, now, 0.0)
            return _ceil_seconds(wait)

    def block(self, url=None, seconds=5, key=None):
        """Record a 429 ``Retry-After`` for the URL's domain.

        ``seconds`` is clamped to 1..:data:`MAX_BACKOFF`; the later of an
        existing block and the new one wins, so two adapters cannot shorten a
        provider's back-off.
        """
        bucket = str(key or domain_for(url) or "").lower()
        if not bucket:
            return 0
        try:
            wait = int(seconds)
        except (TypeError, ValueError, OverflowError):
            wait = 5
        wait = max(1, min(wait, MAX_BACKOFF))
        now = self.clock()
        with self._lock:
            tokens, last, blocked = self._state.get(
                bucket, (self.burst, now, 0.0))
            until = max(blocked, now + wait)
            self._touch(bucket, tokens, last, until)
        return wait

    def reset(self, key=None):
        """Drop one domain (or all state).  Tests and settings reload only."""
        with self._lock:
            if key is None:
                self._state.clear()
            else:
                self._state.pop(str(key or "").lower(), None)

    def __len__(self):
        with self._lock:
            return len(self._state)

    def _touch(self, bucket, tokens, last, blocked):
        self._state[bucket] = (tokens, last, blocked)
        self._state.move_to_end(bucket)
        while len(self._state) > self.max_keys:
            self._state.popitem(last=False)


def _non_negative(value, default):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    if not math.isfinite(number):
        return float(default)
    return max(0.0, number)
