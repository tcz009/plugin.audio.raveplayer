# Ideas for what to add next

Ranked by value-for-effort, with the constraint that everything must stay a
thin layer over public sources (no accounts, no keys, no scraping that rots).

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
Show the pack cover (Archive item thumbnail) as full-screen fanart while a
tape plays, and surface the DJ/venue/date parsed from the item title in the
plot. Kodi shows whatever the resolved list item carries, so this is mostly
metadata work.

### 10. Downloads
Make sure Kodi's own "Download" context-menu entry works for resolved items,
so a pack can be saved to local storage for offline listening. Needs a
resolver path that does not rely on stream headers.

## Deliberately not planned

- **YouTube / Spotify / SoundCloud embedding** — needs yt-dlp or client
  credentials, both of which break constantly and pull in licences the add-on
  does not want.
- **Accounts, sync, favourites in the cloud** — no benefit for a single-user
  home-lab add-on and a privacy cost.
- **Scraping sites behind Cloudflare challenges** — unverifiable and fragile;
  the two pirate-archive domains cannot be tested without a browser, so they
  stay out.
