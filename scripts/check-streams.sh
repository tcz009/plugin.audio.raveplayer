#!/bin/sh
# Fail if the curated live streams or a known archive item stop serving.
# Used by .github/workflows/streams.yml (daily) and safe to run locally.
set -eu
UA="RavePlayerStreamCheck/1.0 (+https://github.com/tcz009/plugin.audio.raveplayer)"
fail=0

check_stream() {
  name="$1"; url="$2"
  code=$(curl -sL -m 20 -A "$UA" -r 0-2000 -o /tmp/rp-stream.bin -w '%{http_code}' "$url" || true)
  type=$(file -b --mime-type /tmp/rp-stream.bin 2>/dev/null || echo unknown)
  case "$code" in
    200|206) echo "OK   $name ($code, $type)";;
    *) echo "FAIL $name (HTTP $code)"; fail=1;;
  esac
}

check_json() {
  name="$1"; url="$2"
  code=$(curl -sL -m 20 -A "$UA" -o /dev/null -w '%{http_code}' "$url" || true)
  case "$code" in
    200) echo "OK   $name ($code)";;
    *) echo "FAIL $name (HTTP $code)"; fail=1;;
  esac
}

check_stream "Kool London" "https://admin.stream.rinse.fm/proxy/kool/stream"
check_stream "Rinse FM" "https://admin.stream.rinse.fm/proxy/rinse_uk/stream"
check_json "Archive metadata (Rinse)" "https://archive.org/metadata/SpyroRinseFM20130606"
check_json "Archive repo index" "https://raw.githubusercontent.com/tcz009/plugin.audio.raveplayer/main/repo/addons.xml"

exit "$fail"
