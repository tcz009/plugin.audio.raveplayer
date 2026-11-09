# -*- coding: utf-8 -*-
"""Explicit offline downloads (phase 1).

Only direct audio files from the approved sources can be downloaded:
Archive.org tracks, Moxser mix MP3s, Hardscore MP3/M4A, Pirate Radio Archives
direct files and RaveTapePacks.com pack MP3s (fetched through the RTP egress
route, like playback).  Platform pages, RSS enclosures, GetDarker rows, live
streams and HLS are never eligible.  All file work goes through
``xbmcvfs``; downloads are explicit user gestures, atomic (temp + rename) and
metadata is kept in ``downloads.json`` beside the files.
"""

import hashlib
import json
import os
import re
import shutil
import time
import unicodedata
import urllib.parse

import xbmcvfs

from . import handoff, http

DIR_ENV = "RAVE_DOWNLOAD_DIR"
DIR_SPECIAL = "special://userdata/downloads/raveplayer/"
METADATA_NAME = "downloads.json"
CHUNK_BYTES = 128 * 1024
MIN_FREE_BYTES = 256 * 1024 * 1024
MAX_FILE_BYTES = 500 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
AUDIO_EXTENSIONS = (".mp3", ".m4a")

ALLOWED_SOURCES = {
    "Archive.org": ("archive.org",),
    "Moxser.com": ("moxser.com", "enceladus.feralhosting.com"),
    "Hardscore.com": ("hardscore.com", "www.hardscore.com"),
    "Pirate Radio Archives": ("hardscore.com", "www.hardscore.com"),
    "Toronto Rave Mixtape Archive": ("torontoravemixtapearchive.com",
                                     "www.torontoravemixtapearchive.com"),
    "RaveTapePacks.com": ("ravetapepacks.com", "www.ravetapepacks.com"),
    # Resolver results: Mediafire/Drive/Podomatic direct URLs and the web's
    # signed Mega stream endpoint.  The page URLs themselves are resolved in
    # routes.download_start() and never planned directly.
    "Rave Resolver": ("mediafire.com", "drive.google.com",
                      "drive.usercontent.google.com", "googleusercontent.com",
                      "podomatic.com", "mega.nz", "mega.co.nz"),
}
ALLOWED_CONTENT_TYPES = ("audio/", "application/octet-stream")


def download_dir():
    override = os.environ.get(DIR_ENV)
    path = override or xbmcvfs.translatePath(DIR_SPECIAL)
    path = str(path or "")
    if path and not path.endswith(os.sep):
        path += os.sep
    return path


def _ensure_dir():
    path = download_dir()
    if path:
        try:
            xbmcvfs.mkdirs(path)
        except Exception:
            pass
    return path


def _metadata_path():
    return os.path.join(download_dir(), METADATA_NAME)


def _file_size(path):
    try:
        handle = xbmcvfs.File(path)
        try:
            return int(handle.size() or 0)
        finally:
            handle.close()
    except Exception:
        return 0


def _exists(path):
    try:
        return bool(xbmcvfs.exists(path))
    except Exception:
        return False


def _remove(path):
    try:
        xbmcvfs.remove(path)
    except Exception:
        pass


def _safe_base(url):
    return str(url or "").split("|", 1)[0].strip()


def _url_parts(url):
    try:
        return urllib.parse.urlsplit(_safe_base(url))
    except ValueError:
        return None


def _extension(url):
    split = _url_parts(url)
    if split is None:
        return ""
    path = split.path.lower()
    for extension in AUDIO_EXTENSIONS:
        if path.endswith(extension):
            return extension
    return ""


def _source_host_ok(url, source):
    allowed = ALLOWED_SOURCES.get(str(source or ""))
    split = _url_parts(url)
    if not allowed or split is None:
        return False
    host = (split.hostname or "").lower()
    if not host:
        return False
    for domain in allowed:
        if host == domain or host.endswith("." + domain):
            return True
    return False


def _host_in(url, hosts):
    """True when ``url``'s host equals or is below one of ``hosts``."""
    split = _url_parts(url)
    if split is None:
        return False
    host = (split.hostname or "").lower().rstrip(".")
    if not host:
        return False
    for domain in hosts or ():
        domain = str(domain or "").strip().lower().rstrip(".")
        if domain and (host == domain or host.endswith("." + domain)):
            return True
    return False


def eligible(url, source, check_host=True, resolved=False, extra_hosts=None):
    """The single direct-file/source predicate shared with the web build.

    ``check_host=False`` is used for building context menus (cheap, no DNS);
    the start route always re-validates with the public-host guard.

    ``resolved=True`` is for a URL returned by the resolver: Drive and the
    signed Mega endpoint do not end in an audio extension, so the extension
    requirement is replaced by the source host allowlist plus the probe's
    Content-Type check in :func:`plan`.  ``extra_hosts`` names the exact
    operator-configured resolver-service host for a signed Mega stream; that
    URL is intentionally on the LAN/Tailscale and skips the public-host guard.
    """
    if str(source or "") not in ALLOWED_SOURCES:
        return False
    text = str(url or "").strip()
    if not text or handoff.platform_kind(text):
        return False
    split = _url_parts(text)
    if split is None or split.scheme not in ("http", "https"):
        return False
    if split.username or split.password:
        return False
    if not _extension(text) and not resolved:
        return False
    service_host = _host_in(text, extra_hosts)
    if not (_source_host_ok(text, source) or service_host):
        return False
    if not check_host:
        return True
    if service_host:
        # Only download_start() passes this, after checking the URL is the
        # configured service's /api/mega/stream endpoint.
        return True
    # Public-host/DNS guard reuses the same helper as playback.
    return bool(http.safe_stream_url(text))


def sanitize_filename(title, url, extension=".mp3"):
    """Return ``<safe-title>-<8hex><ext>``; never the URL itself."""
    extension = extension if extension in AUDIO_EXTENSIONS else _extension(url) or ".mp3"
    text = unicodedata.normalize("NFKD", str(title or ""))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"\.(?:mp3|m4a)$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    if not text:
        text = "rave-player"
    text = text[:80].strip("-")
    if text.upper() in ("CON", "PRN", "AUX", "NUL") or re.match(r"^COM\d$|^LPT\d$", text.upper()):
        text = "rave-" + text
    digest = hashlib.sha1(str(url).encode("utf-8")).hexdigest()[:8]
    return "%s-%s%s" % (text or "rave-player", digest, extension)


def _key(url):
    return hashlib.sha1(str(url).encode("utf-8")).hexdigest()[:16]


def free_bytes():
    path = download_dir()
    if not path:
        return None
    try:
        return int(shutil.disk_usage(path).free)
    except (OSError, ValueError):
        try:
            stats = os.statvfs(path)
            return int(stats.f_bavail * stats.f_frsize)
        except (OSError, ValueError, AttributeError):
            return None


def _load_index():
    path = _metadata_path()
    if not _exists(path):
        return []
    try:
        handle = xbmcvfs.File(path)
        try:
            data = handle.read()
        finally:
            handle.close()
        if isinstance(data, (bytes, bytearray)):
            data = data.decode("utf-8", "replace")
        package = json.loads(data)
    except (OSError, ValueError, TypeError, UnicodeError):
        return []
    rows = []
    for raw in package if isinstance(package, list) else []:
        if not isinstance(raw, dict):
            continue
        filename = raw.get("filename")
        key = raw.get("key")
        if not isinstance(filename, str) or not filename or "/" in filename or "\\" in filename:
            continue
        if not isinstance(key, str) or not key:
            continue
        rows.append({
            "key": key,
            "filename": filename,
            "title": str(raw.get("title") or filename),
            "source": str(raw.get("source") or ""),
            "url": str(raw.get("url") or ""),
            "size": max(0, int(raw.get("size") or 0)) if str(raw.get("size") or "0").isdigit() else 0,
            "added": raw.get("added") or "",
        })
    return rows


def _save_index(rows):
    path = _metadata_path()
    directory = download_dir()
    if not directory:
        return False
    temporary = path + ".tmp"
    try:
        _ensure_dir()
        handle = xbmcvfs.File(temporary, "w")
        try:
            handle.write(json.dumps(rows, ensure_ascii=False, indent=0))
        finally:
            handle.close()
        if _exists(path):
            _remove(path)
        if not xbmcvfs.rename(temporary, path):
            _remove(temporary)
            return False
        return True
    except Exception:
        _remove(temporary)
        return False


def total_saved_bytes():
    return sum(row["size"] for row in list_downloads())


def list_downloads():
    rows = _load_index()
    result = []
    for row in rows:
        path = os.path.join(download_dir(), row["filename"])
        exists = _exists(path)
        size = _file_size(path) if exists else 0
        result.append(dict(row, path=path, exists=exists, size=size, missing=not exists))
    result.sort(key=lambda row: row.get("added") or "", reverse=True)
    return result


def path_for(row):
    return os.path.join(download_dir(), row["filename"])


def plan(url, title, source, resolved=False, extra_hosts=None,
         allow_private=False):
    """Validate eligibility/size/space before asking the user to start.

    ``resolved``/``extra_hosts``/``allow_private`` are set only by
    ``routes.download_start()`` for a resolver result; every other caller keeps
    the original direct-file behaviour.
    """
    result = {
        "allowed": False, "reason": "", "url": str(url or ""), "title": str(title or ""),
        "source": str(source or ""), "size": 0, "free": 0, "filename": "",
        "path": "", "existing": False, "allow_private": bool(allow_private),
    }
    if not eligible(url, source, resolved=resolved, extra_hosts=extra_hosts):
        result["reason"] = "Not a downloadable direct audio file from an approved source."
        return result
    _ensure_dir()
    probe = http.probe_media(url, timeout=20, allow_private=allow_private)
    if not probe:
        result["reason"] = "Could not verify the file size/type."
        return result
    size = int(probe.get("size") or 0)
    content_type = str(probe.get("content_type") or "").lower()
    if size <= 0 or size > MAX_FILE_BYTES:
        result["reason"] = "File size is missing or above the 500 MiB cap."
        return result
    if not any(content_type.startswith(prefix) for prefix in ALLOWED_CONTENT_TYPES):
        result["reason"] = "Upstream is not an audio file."
        return result
    total = total_saved_bytes()
    if total + size > MAX_TOTAL_BYTES:
        result["reason"] = "The 2 GiB downloads allowance would be exceeded."
        return result
    free = free_bytes()
    if free is None:
        result["reason"] = "Could not check free storage."
        return result
    if free - size < MIN_FREE_BYTES:
        result["reason"] = "Not enough free space (keep 256 MiB free)."
        return result
    # Drive and the signed Mega endpoint carry no filename extension; the
    # probe's audio Content-Type decides between the two allowed extensions so
    # an M4A is never mislabelled as MP3.
    extension = _extension(url)
    if not extension:
        extension = ".m4a" if ("mp4" in content_type or "m4a" in content_type) else ".mp3"
    filename = sanitize_filename(title, url, extension)
    path = os.path.join(download_dir(), filename)
    result.update({
        "allowed": True, "size": size, "free": free, "filename": filename,
        "path": path, "existing": _exists(path), "content_type": content_type,
        "key": _key(url),
    })
    return result


def _make_progress(progress, done, total):
    if progress is None:
        return
    try:
        progress(done, total)
    except Exception:
        pass


def download(plan_row, progress=None, cancelled=None):
    """Download one planned file atomically.  Returns ``{ok, reason}``."""
    if not plan_row.get("allowed"):
        return {"ok": False, "reason": plan_row.get("reason") or "Download not allowed."}
    if cancelled is not None and cancelled():
        return {"ok": False, "reason": "cancelled"}
    directory = _ensure_dir()
    if not directory:
        return {"ok": False, "reason": "Download folder is unavailable."}
    final_path = plan_row["path"]
    temporary = final_path + ".part"
    _remove(temporary)
    handle = None
    try:
        with http.open_media(
                plan_row["url"], timeout=30,
                allow_private=bool(plan_row.get("allow_private"))) as response:
            content_type = str((response.headers.get("Content-Type") if response.headers else "") or "").lower()
            if not any(content_type.startswith(prefix) for prefix in ALLOWED_CONTENT_TYPES):
                raise ValueError("upstream is not audio")
            total = int((response.headers.get("Content-Length") if response.headers else 0) or plan_row.get("size") or 0)
            if total and total > MAX_FILE_BYTES:
                raise ValueError("file too large")
            handle = xbmcvfs.File(temporary, "wb")
            done = 0
            while True:
                if cancelled is not None and cancelled():
                    raise RuntimeError("cancelled")
                chunk = response.read(CHUNK_BYTES)
                if not chunk:
                    break
                if not isinstance(chunk, (bytes, bytearray)):
                    raise ValueError("non-byte response")
                handle.write(bytes(chunk))
                done += len(chunk)
                if done > MAX_FILE_BYTES:
                    raise ValueError("file too large")
                _make_progress(progress, done, total)
            handle.close()
            handle = None
            if done <= 0:
                raise ValueError("empty response")
            if total and done != total:
                raise ValueError("incomplete response")
        if not _exists(temporary):
            raise OSError("temporary file missing")
        if _exists(final_path):
            _remove(final_path)
        if not xbmcvfs.rename(temporary, final_path):
            raise OSError("could not finalise download")
        rows = [row for row in _load_index()
                if row.get("key") != plan_row.get("key") and row.get("url") != plan_row.get("url")]
        rows.append({
            "key": _key(plan_row["url"]),
            "filename": plan_row["filename"],
            "title": plan_row["title"] or plan_row["filename"],
            "source": plan_row["source"],
            "url": plan_row["url"],
            "size": done,
            "added": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        if not _save_index(rows):
            _remove(final_path)
            return {"ok": False, "reason": "Could not save download metadata."}
        _make_progress(progress, done, done)
        return {"ok": True, "reason": ""}
    except Exception as exc:
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass
        _remove(temporary)
        return {"ok": False, "reason": str(exc) or "Download failed."}


def delete(key):
    key = str(key or "")
    rows = _load_index()
    row = next((item for item in rows if item["key"] == key), None)
    if row is None:
        return False
    path = path_for(row)
    _remove(path)
    _remove(path + ".part")
    rows = [item for item in rows if item["key"] != key]
    return _save_index(rows)


def format_size(size):
    try:
        size = int(size or 0)
    except (TypeError, ValueError):
        size = 0
    if size >= 1024 * 1024 * 1024:
        return "%.1f GB" % (size / float(1024 * 1024 * 1024))
    if size >= 1024 * 1024:
        return "%.1f MB" % (size / float(1024 * 1024))
    if size >= 1024:
        return "%.0f KB" % (size / float(1024))
    return "%d B" % size
