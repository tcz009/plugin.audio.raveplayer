# Kodi taxonomy — 3.9.42 (navigation update 3.9.48)

Mirrors the web 1.6.44 scene taxonomy (`docs/RAVE-TAXONOMY-2026.md`): labels,
grouping and source order only. No new scraping; the 1.6.46 legacy-stream URL
fixes are included.

## Root

`Latest · Tape Packs · Pirate Radio · Mixes & Shows · Live Radio · Favourites ·
Search the Archive · Surprise Me · About & Sources`

`Curated Gems`/the 2014 bucket and the duplicate `legacy_toronto` route are
gone.

## Tape Packs

1. Toronto Rave Mixtape Archive
2. JungleTapes.com
3. RaveTapePacks.com — By Event · By DJ · By MC · By Year · All Packs.
   Each kind lists its categories (`legacy_index`), a category lists every
   `?p=<id>` pack across WordPress pages (`legacy_category`), and a pack opens
   its direct MP3s (`legacy_post`); All Packs keeps the homepage-pack view.
4. Classic Pack Series
5. By Rave, Venue & Promoter
6. By Year
7. Every Pack (archive.org, demoted; plot “Archive mixtapes”)

## Mixes & Shows

`Podcasts & Mixes · DNBRADIO · GetDarker · Moxser`

## Pirate Radio

`Hardscore · Pirate Radio Archives · Kool FM Sets`

## Live Radio

`Kool FM · Rinse FM · Centreforce 883` then
`Hardcore · Jungle · Drum & Bass · House · UK Garage · Dubstep & Grime`.

## Genre doors

Jungle and Drum & Bass are separate archive/radio doors; Hardcore and Happy
Hardcore are separate archive doors. `Oldskool & Rave` and `Breakbeat` are
removed.

## Tests

`test/test_taxonomy_2026.py` asserts exact root/Tape Packs/Pirate/Mixes/Live
order, split doors, kebab-case ids, removed legacy routes and distinct stickers.
`test/test_rtp_navigation.py` pins the 50/209/90/13 document-order categories,
paginated category packs, post tracks, and the exact legacy_index/
legacy_category/legacy_post routes, offline.
`test/test_naming.py` also rejects any `* 2.*` duplicate copy. No
playback/autoplay changes.
