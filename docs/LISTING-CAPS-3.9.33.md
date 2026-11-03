# Listing caps audit — 3.9.33

No listing source may silently drop rows. Large sources are shown in full;
Archive/rave and year/filter pages keep their existing **Next page** pagination.
No playback/auto-play route was changed.

| Source | Old cap | New behaviour |
|---|---|---|
| Moxser Mixes | `MAX_MIXES=120`, `MAX_SITEMAPS=4`, route limit 60; upstream audit: **1000** sitemap URLs across 2 sitemaps | `MAX_MIXES=5000`, `MAX_SITEMAPS=20`, route requests the full sitemap catalogue (fixture 150 rows across 5 sitemaps) |
| Hardscore.com | `MAX_ITEMS=100`, route limit 60 | `MAX_ITEMS=5000`, route full feed (fixture 150 posts) |
| GetDarker RSS | 60 via Hardscore | full Hardscore feed |
| Toronto Rave Mixtape Archive | `MAX_TRACKS=600`; upstream audit: jungle **678**, house **546**, studio **1174**, xstatic **241** | `MAX_TRACKS=5000`; 678-row fixture fully rendered |
| Podcast/mix RSS feeds | `EPISODES_PER_FEED=60`, max 500 | default/max **5000**; settings default changed to 5000; 120-episode fixture fully parsed |
| Mixcloud curated accounts | `MAX_CLOUDS=80`, route 60 | `MAX_CLOUDS=1000`, route full response |
| Live radio tags / live-name lookup | 100 / 20 | 500 / 200 (setting default 500) |
| Archive.org / Rave Tape Packs / year / filters | paginated | unchanged: 50/page (setting up to 200), total + “Next page” |
| Pirate Radio Archives | data file, no cap | unchanged |
| DNB Radio | no cap | unchanged |
| Latest | curated “newest 60” view | unchanged; it is a recent-items view, not the Archive listing |

Cache TTLs and request throttles remain in place for Moxser/Toronto; raising a
cap does not add requests. Tests: `test/test_listing_caps.py` asserts the
fixture counts and route rendering, and the full suite is 444 OK.
