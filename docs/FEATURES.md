# Ideas for what to add next

Ranked by value-for-effort, with the constraint that everything must stay a
thin layer over public sources (no accounts, no keys, no scraping that rots).

> **Status:** items 1–9 below are implemented. Item 10 (downloads) is deferred
> pending a Kodi device: Kodi 20–22 has no Python download hook for resolved
> plugin streams (see the note under item 10).

## Ready to build (low risk, high value)

### 1. Latest — one screen, everything new
A section that merges the newest items from every source and sorts by date:

- newest podcast episodes (`pubDate` from the RSS feeds)
- newest tape packs (`addeddate desc` on the ravetapes collection)
- newest DNBRADIO shows (the recordings page is already dated)
- newest pirate radio uploads from the Archive

Why: the add-on currently opens with genres, not with "what's new". For a
library that runs 1988 → today, "Latest" is the most-used screen in practice.
Effort: small — every provider already returns dates or can expose them.

### 2. Surprise me
One menu entry that picks a random pack from `collection:ravetapes` and opens
it. Trivial to implement, and it is the feature people actually use on a TV
remote when they do not know what they want.

### 3. Tape packs by year
A year submenu (1988 … 2026) filtering `collection:ravetapes` by date range
(`date:[1993-01-01 TO 1993-12-31]`). The collection has dates on most items,
so this is a query change rather than new code, and it makes the tape-pack
backbone browsable the way the old add-on's menus were.

### 4. Quick filters / DJ search
Shortcuts to the names that matter: Dreamscape, Helter Skelter, Fantazia,
One Nation, Kool FM, Centreforce, Don FM. Each is an Archive query against
the collection — data, not code, so they can live in a JSON file next to
`feeds.json` and be edited without touching Python.

### 5. Favourites
A context-menu "Add to favourites" on any tape pack or episode, stored as JSON
in the add-on profile directory, plus a Favourites section. Survives Kodi
restarts; no account needed. Medium effort because of the context menu and
storage, but it is the single biggest gap for repeat use.

## Worth doing when there is time

### 6. Cache (already in progress)
Network responses cached on disk with a TTL. Makes menus feel instant on a
Shield and halves the requests the sources see. Already being implemented as
part of the code-quality pass.

### 7. Settings that matter
Currently only page size and station limit. Worth exposing: episodes per feed,
cache TTL, which sections to show, and default sort order. Low effort, but
avoid turning it into a wall of toggles.

### 8. Discovery scanner
A standalone script (`scripts/discover.py`) that takes a list of candidate
sites, probes each for audio links, RSS feeds and platform fingerprints
(WordPress, Drupal, RSS.com, Internet Archive), checks one sample stream with
the right headers, and writes a shortlist. This is how new sources get added
without guessing — and it can be re-run later to find dead links.

### 9. "Now playing" polish
**Implemented in 3.9.5.** Show the pack cover (Archive item thumbnail) as
full-screen fanart while a tape plays, and surface the DJ/venue/date parsed from
the item title in the plot. Kodi shows whatever the resolved list item carries,
so this is mostly metadata work: `resources/lib/nowplaying.py` parses the title
(best-effort, using the researched catalogue/filter names as vocabulary) and
`routes.archive_item` / `_play_tracks` / `play` carry the fanart, plot and
parsed details through to the resolved item. Existing base plots like
"From archive.org item <id>" are kept and only prefixed, and unknown titles are
left untouched.

### 10. Downloads
**Deferred in 3.9.5 — needs a Kodi device and a product decision.** The
investigation found no Python or context-menu download hook to use:

- Kodi 20–22 has no `Download` action in the media context menus
  (`xbmc/video/ContextMenus.cpp`, `xbmc/music/ContextMenus.cpp` in the Omega
  branch); no `Download` builtin exists in `xbmc/interfaces/Builtins.cpp`.
- The only built-in download path is JSON-RPC `Files.Download` /
  `Files.PrepareDownload` (`xbmc/interfaces/json-rpc/JSONServiceDescription.cpp`),
  which is for remote clients (Kore etc.); a Python add-on cannot invoke it as a
  context-menu action on its own list item.
- Add-on rows are `plugin://...` URLs resolved with `setResolvedUrl`, which is
  playback-only. Kodi's own download would save the plugin URL, not the stream;
  making it work means either exposing the raw stream as the item path (losing
  the resolver, favourites and `|Referer=` handling) or writing an add-on-owned
  Download action (`xbmcvfs`/urllib + destination dialog) — neither is testable
  here, and RaveTapePacks streams cannot work without stream headers anyway.

So: no guessing and no untested download UI in this release. Revisit with a
Kodi device to see what the context menu actually offers on 20–22, then decide
between an add-on-owned download action and a documented "use the web build"
answer.

## Deliberately not planned

- **YouTube / Spotify / SoundCloud embedding** — needs yt-dlp or client
  credentials, both of which break constantly and pull in licences the add-on
  does not want.
- **Accounts, sync, favourites in the cloud** — no benefit for a single-user
  home-lab add-on and a privacy cost.
- **Scraping sites behind Cloudflare challenges** — unverifiable and fragile;
  the two pirate-archive domains cannot be tested without a browser, so they
  stay out.
