# -*- coding: utf-8 -*-
"""Source discovery: probe candidate sites and score them for the add-on.

    python3 scripts/discover.py            # writes docs/DISCOVERED.md
    python3 scripts/discover.py --json     # machine-readable output

This is how new sources get added without guessing: it fingerprints the
platform, counts real audio links, finds RSS feeds (and counts enclosures),
then checks that one sample stream actually responds. Nothing is added to the
add-on automatically — the report is a shortlist to approve.

Standalone by design: stdlib only, no Kodi imports, safe to run anywhere.
"""

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "RavePlayer-Discovery/1.0 (+https://github.com/tcz009/plugin.audio.raveplayer)"
TIMEOUT = 20

CANDIDATES = [
    # Old-school sites
    "https://www.ravetapepacks.com/",
    "https://jungletapes.com/",
    "https://www.torontoravemixtapearchive.com/",
    "https://rave-archive.com/",
    "https://oldskoolanthems.com/",
    "https://mixes.vuiz.net/",
    # Present-day
    "https://dnbradio.com/recordings",
    "https://rss.com/podcasts/jungle-lab/",
    "https://rss.com/podcasts/the-m-pathe-test/",
    "https://rss.com/podcasts/viper-classic-rave/",
    "https://rss.com/podcasts/toro-in-the-mix/",
    "https://hearthis.at/categories/drumandbass/",
    "https://www.mixcloud.com/discover/jungle/",
    "https://bandcamp.com/tag/jungle",
    # Archives
    "https://archive.org/details/ravetapes",
]

AUDIO_RE = re.compile(r"""https?://[^"'\s>]+\.(?:mp3|m4a|ogg|flac|wav)(?:\?[^"'\s>]*)?|/[^"'\s>]+\.(?:mp3|m4a|ogg)(?:\?[^"'\s>]*)?""", re.I)
FEED_RE = re.compile(r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*>', re.I)


def fetch(url, method="GET", headers=None):
    request = urllib.request.Request(url, method=method, headers={"User-Agent": UA, "Accept": "*/*"})
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read(400000)
            return {
                "status": response.status,
                "url": response.geturl(),
                "type": response.headers.get_content_type(),
                "body": raw.decode("utf-8", "replace"),
            }
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "url": url, "type": "", "body": ""}
    except Exception as exc:  # network, DNS, TLS
        return {"status": 0, "url": url, "type": "", "body": "", "error": str(exc)}


def title_of(body):
    match = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
    return " ".join(html.unescape(match.group(1)).split())[:90] if match else ""


def platform_of(body, url):
    lowered = body.lower()
    if "wp-content" in lowered or "wp-json" in lowered:
        return "wordpress"
    if "/sites/default/" in lowered or "drupal" in lowered:
        return "drupal"
    if "rss.com" in url or "content.rss.com" in lowered:
        return "rss.com"
    if "archive.org" in url:
        return "internet-archive"
    if "hearthis" in url:
        return "hearthis"
    if "mixcloud" in url:
        return "mixcloud"
    if "bandcamp" in url:
        return "bandcamp"
    return "generic"


def feed_url(body, base):
    match = FEED_RE.search(body or "")
    if match:
        href = re.search(r'href=["\']([^"\']+)', match.group(0))
        if href:
            return urllib.parse.urljoin(base, html.unescape(href.group(1)))
    guess = urllib.parse.urljoin(base, "/feed/")
    probe = fetch(guess)
    if probe["status"] == 200 and "xml" in (probe["type"] or ""):
        return guess
    return ""


def enclosure_count(feed_text):
    return len(re.findall(r"<enclosure\b", feed_text or "", re.I))


def check_sample(url):
    result = fetch(url, headers={"Range": "bytes=0-2048", "Referer": urllib.parse.urlparse(url).scheme + "://" + urllib.parse.urlparse(url).netloc + "/"})
    return {"status": result["status"], "type": result["type"]}


def probe(url):
    page = fetch(url)
    body = page["body"]
    entry = {
        "url": url,
        "status": page["status"],
        "final_url": page["url"],
        "title": title_of(body),
        "platform": platform_of(body, page["url"]) if body else "unreachable",
        "audio_links": len(AUDIO_RE.findall(body)),
        "feed": "",
        "episodes": 0,
        "sample": None,
        "score": 0,
    }
    if page["status"] >= 400 or not body:
        entry["score"] = -5
        return entry

    feed = feed_url(body, page["url"])
    if feed:
        entry["feed"] = feed
        feed_page = fetch(feed)
        if feed_page["status"] == 200:
            entry["episodes"] = enclosure_count(feed_page["body"])
            entry["score"] += 3 if entry["episodes"] else 0

    if entry["audio_links"]:
        entry["score"] += 2
        sample = AUDIO_RE.search(body)
        if sample:
            sample_url = urllib.parse.urljoin(page["url"], html.unescape(sample.group(0)))
            entry["sample"] = check_sample(sample_url)

    if entry["platform"] not in ("generic", "unreachable"):
        entry["score"] += 1
    if entry["platform"] == "wordpress" and not entry["feed"]:
        entry["score"] -= 1
    return entry


def main():
    parser = argparse.ArgumentParser(description="Score candidate sources for Rave Player")
    parser.add_argument("--json", action="store_true", help="print JSON instead of markdown")
    parser.add_argument("--out", default=os.path.join(ROOT, "docs", "DISCOVERED.md"))
    args = parser.parse_args()

    results = [probe(url) for url in CANDIDATES]
    results.sort(key=lambda item: item["score"], reverse=True)

    if args.json:
        print(json.dumps(results, indent=2))
        return 0

    lines = [
        "# Discovered sources",
        "",
        "Generated by `scripts/discover.py`. Score: +3 feed with audio enclosures,",
        "+2 direct audio links, +1 recognisable platform, -5 unreachable.",
        "",
        "| Score | Source | Platform | Audio | Feed | Episodes |",
        "|---|---|---|---|---|---|",
    ]
    for item in results:
        lines.append("| %d | %s | %s | %d | %s | %d |" % (
            item["score"],
            (item["title"] or item["url"])[:60].replace("|", "/"),
            item["platform"],
            item["audio_links"],
            (item["feed"] or "-")[:50],
            item["episodes"],
        ))

    details = ["", "## Detail", ""]
    for item in results:
        if not item["audio_links"] and not item["feed"]:
            continue
        details.append("### %s" % (item["title"] or item["url"]))
        details.append("- URL: %s" % item["final_url"])
        details.append("- Platform: %s" % item["platform"])
        if item["feed"]:
            details.append("- Feed: %s (%d episodes)" % (item["feed"], item["episodes"]))
        if item["sample"]:
            details.append("- Sample stream: %s %s" % (item["sample"]["status"], item["sample"]["type"]))
        details.append("")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines + details) + "\n")
    print("wrote %s (%d sources)" % (args.out, len(results)))
    for item in results[:6]:
        print("  %2d  %-40s %s" % (item["score"], (item["title"] or item["url"])[:40], item["platform"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
