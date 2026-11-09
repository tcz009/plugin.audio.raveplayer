# -*- coding: utf-8 -*-
"""Adapter selection and the in-process -> NAS fallback policy.

Order is deliberate:

1. Mediafire, Drive, Podomatic, Mega page adapters (provider-specific);
2. the Direct adapter for plain audio files;
3. the NAS service only when an adapter is missing/not ready and the failure
   is fallback-eligible.

Policy failures (private/loopback URL, malformed URL, disabled Mega) are never
sent to the service: a remote resolver must not become an SSRF bypass.
"""

from . import policy
from .base import (InvalidURL, ProviderError, RateLimited, Resolution,
                   ResolveError, UnsupportedURL)
from .cache import Cache
from .direct import DirectAdapter
from .drive import DriveAdapter
from .http import HttpClient
from .log import Logger
from .mediafire import MediafireAdapter
from .mega import MegaAdapter
from .podomatic import PodomaticAdapter
from .ratelimit import DomainRateLimiter
from .service import ServiceClient, ServiceResultCache
from .settings import Settings

_DEFAULT = None


class Resolver(object):
    """Resolve a URL with in-process adapters, then the optional NAS service."""

    def __init__(self, settings=None, http=None, cache=None, logger=None,
                 adapters=None, service=None, dns_resolver=None,
                 extra_hosts=None, native_mega=None, native_podomatic=None,
                 limiter=None, service_cache=None):
        self.settings = settings or Settings()
        self.logger = logger or Logger(secrets=(self.settings.service_token,
                                                self.settings.service_cookie))
        self.extra_hosts = tuple(extra_hosts or ())
        self.dns_resolver = dns_resolver
        self.http = http or HttpClient(
            timeout=self.settings.http_timeout,
            dns_resolver=dns_resolver, logger=self.logger)
        self.cache = cache or Cache(
            self.settings.cache_dir, ttl=self.settings.cache_ttl)
        # One limiter per resolver process: in-process adapters and the NAS
        # fallback share the same per-registrable-domain token bucket.
        self.limiter = limiter if limiter is not None else DomainRateLimiter()
        # Bounded in-memory result cache + single-flight for /api/resolve.
        self.service_cache = (service_cache if service_cache is not None
                              else ServiceResultCache())
        if adapters is None:
            adapters = [
                MediafireAdapter(self.http, self.cache, logger=self.logger),
                DriveAdapter(self.http, self.cache, logger=self.logger),
                PodomaticAdapter(native=native_podomatic,
                                 logger=self.logger),
                MegaAdapter(enabled=self.settings.enable_mega,
                            native=native_mega, logger=self.logger),
                DirectAdapter(allow_hosts=self.extra_hosts,
                              dns_resolver=dns_resolver, logger=self.logger),
            ]
        self.adapters = list(adapters)
        if service is False:
            self.service = None
        elif service is not None:
            self.service = service
        else:
            # A bad resolver_service_url/token must never disable the
            # in-process adapters (Mediafire/Drive keep working offline).
            # Configuration failures are logged once per construction and a
            # later settings change can build a fresh Resolver.
            try:
                self.service = ServiceClient.from_settings(
                    self.settings, self.http, logger=self.logger,
                    dns_resolver=dns_resolver, result_cache=self.service_cache)
            except Exception as exc:  # noqa: BLE001 - playback must not break
                self.service = None
                self.logger.warning(
                    "resolver service disabled (%s)" % type(exc).__name__)

    # ------------------------------------------------------------- selection
    def provider_for(self, url):
        return policy.provider_for(url, extra_hosts=self.extra_hosts)

    def needs_resolution(self, url):
        """True only for a **known** provider page (Mediafire/Drive/etc.).

        Unknown hosts are deliberately False: live-radio and other direct
        streams must not be routed through the resolver just because they are
        not on the direct-download allowlist.  Callers that want the service to
        try an unknown provider call ``resolve()`` explicitly.
        """
        return self.provider_for(url) not in ("", "direct")

    def adapter_for(self, url, provider=None):
        name = str(provider or self.provider_for(url) or "")
        if not name:
            return None
        for adapter in self.adapters:
            if adapter.name == name:
                if not adapter.matches(url):
                    raise InvalidURL(
                        "that URL does not belong to the %s provider" % name)
                return adapter
        raise UnsupportedURL("no adapter for provider %r" % name)

    def available_providers(self):
        names = [adapter.name for adapter in self.adapters]
        if self.service is not None:
            names.append("service")
        return names

    def _validated(self, result):
        """Sanitise headers and reject a non-public adapter result.

        Web's service validates every adapter result; in-process adapters hit
        the network themselves, so a provider/parser bug or a native adapter
        could otherwise hand Kodi a private URL or replay untrusted headers.
        DNS is not repeated here (the adapter already connected); syntax,
        port 80/443 and literal private/local targets are re-checked.
        """
        if not isinstance(result, Resolution):
            raise ProviderError("the resolver returned no resolution")
        result.headers = policy.sanitize_headers(result.headers)
        policy.check_url(result.url, resolve_dns=False)
        return result

    # --------------------------------------------------------------- resolve
    def resolve(self, url, provider=None, use_service=True):
        """Resolve one URL to a :class:`Resolution`.

        Raises :class:`ResolveError` subclasses.  ``use_service=False`` forces
        in-process only (useful for diagnostics/tests).
        """
        # Syntax and literal private-address check; DNS is done by the adapter
        # that actually connects (or by the direct adapter before returning).
        policy.check_url(url, resolve_dns=False)
        name = str(provider or self.provider_for(url) or "")
        primary = None
        adapter = None
        if name:
            adapter = self.adapter_for(url, name)
        # Direct audio is a local allowlist/DNS check, not provider work:
        # gating it would throttle a play-all of archive.org tracks.  Every
        # provider adapter and the service fallback share one bucket per
        # registrable domain.
        gated = False
        if adapter is not None and adapter.name != "direct":
            gated = True
            self._take_slot(url)
        if adapter is not None:
            try:
                return self._validated(adapter.resolve(url))
            except RateLimited as exc:
                # A provider's 429 applies to the domain, not just this
                # adapter: block the service fallback too.
                self.limiter.block(url, exc.retry_after or 5)
                exc.fallback = False
                raise
            except ResolveError as exc:
                primary = exc
                self.logger.debug("in-process %s failed: %s"
                                  % (adapter.name, exc.message))
                if not exc.fallback:
                    raise
        else:
            primary = UnsupportedURL("no in-process resolver for that URL")

        if (not use_service or self.service is None or primary is None
                or not primary.fallback):
            raise primary
        if not gated:
            self._take_slot(url)
        self.logger.debug("falling back to resolver service for %s"
                          % (name or "unknown"))
        try:
            return self.service.resolve(url, provider=name or None)
        except RateLimited as exc:
            self.limiter.block(url, exc.retry_after or 5)
            exc.fallback = False
            raise

    def _take_slot(self, url):
        """Consume one token for ``url``'s domain or raise ``RateLimited``."""
        retry = self.limiter.take(url)
        if retry:
            raise RateLimited(
                "too many resolver requests for this host; retry shortly",
                retry_after=retry, fallback=False)

    def resolve_url(self, url, provider=None, use_service=True):
        """Convenience returning a string, or ``""`` on any resolve failure."""
        try:
            return self.resolve(url, provider=provider,
                                use_service=use_service).url
        except ResolveError:
            return ""


def get_resolver():
    """Return the process-wide default resolver (built lazily)."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Resolver()
    return _DEFAULT


def reset_resolver():
    """Drop the process-wide resolver (tests/settings changes)."""
    global _DEFAULT
    _DEFAULT = None


def resolve(url, provider=None, **kwargs):
    """Module-level convenience: ``resolver.resolve(url)``."""
    return get_resolver().resolve(url, provider=provider, **kwargs)
