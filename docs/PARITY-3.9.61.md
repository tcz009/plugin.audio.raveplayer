# Rave Player 3.9.61 — classic-menu parity matrix

Release 3.9.61 makes the full-screen **Rave Screen** (`script.raveplayer.ui`)
reach every destination in the plugin's classic directory (`mode=classic_root`
in `resources/lib/routes.py`). This is the audit trail and the regression
contract; `test/test_parity_3_9_61.py` asserts it.

Method: read `routes.py`'s `classic_root`, `packs_menu`, `pirate_radio`,
`shows_menu`, `radio_menu`, `fav_list`, `search`, `surprise`, `about` and every
mode they emit; then walk the screen's `RaveData` rooms, `LiveRadio` rows,
library rooms and controller actions. No device, network or ADB was used.

Legend: **old** = plugin mode (the classic path is shown where it is not the
root); **new** = screen room → row/action.

| # | Destination | Old classic path | New screen room → row/action | Status |
|---|-------------|------------------|------------------------------|--------|
| 1 | Latest | `latest` | Home → Latest | present (existing) |
| 2 | Tape Packs hub | `packs_menu` | Home → Tape Packs | **added** |
| 3 | Toronto Rave Mixtape Archive | Tape Packs → `toronto` | Tape Packs → Toronto | present (existing room) |
| 4 | Toronto genre | `toronto_genre` | Tape Packs → Toronto → genre | present (existing) |
| 5 | JungleTapes.com | Tape Packs → `legacy_jt` | Tape Packs → JungleTapes | present (existing room) |
| 6 | JungleTapes show | `legacy_jt_show` | Tape Packs → JungleTapes → show | present (existing) |
| 7 | RaveTapePacks.com | Tape Packs → `legacy_menu` | Tape Packs → RaveTapePacks | present (existing room) |
| 8 | RaveTapePacks index (Event/DJ/MC/Year) | `legacy_index` | RaveTapePacks → index | present (existing) |
| 9 | RaveTapePacks category | `legacy_category` | RaveTapePacks → index → category | present (existing) |
| 10 | RaveTapePacks pack | `legacy_post` / `legacy_pack` | RaveTapePacks → pack / Favourites saved pack | present (existing) |
| 11 | RaveTapePacks All Packs | `legacy_packs` | RaveTapePacks → All Packs | present (existing) |
| 12 | Classic Pack Series | Tape Packs → `filters_menu` | Tape Packs → Classic Pack Series | **added** |
| 13 | Individual classic series | `filter_list` | Classic Pack Series → series | **added** |
| 14 | "Live now" filter door | `filter_live` | Classic Pack Series → series → live now | **added** |
| 15 | By Rave, Venue & Promoter | Tape Packs → `rave_nights` | Tape Packs → By Rave, Venue & Promoter | **added** |
| 16 | One rave's packs/sets | `rave_list` | By Rave → rave (Archive packs + Mixcloud hand-off) | **added** |
| 17 | By Year | Tape Packs → `years` | Tape Packs → By Year | **added** |
| 18 | One year's packs | `year_list` | By Year → year | **added** |
| 19 | Every Pack | Tape Packs → `archive_list(key=tapepacks)` | Tape Packs → Every Pack | **added** |
| 20 | Archive pack detail | `archive_item` | Every Pack / Latest → pack | present (existing pack rows) |
| 21 | Pirate Radio hub | `pirate_radio` | Home → Pirate Radio | **added** |
| 22 | Hardscore | Pirate Radio → `hardscore` | Pirate Radio → Hardscore | present in Mixes; **added hub door** |
| 23 | Hardscore event/post | `hardscore_event` | Pirate Radio → Hardscore → post | present in Mixes; **added hub door** |
| 24 | Pirate Radio Archives | Pirate Radio → `pirate_menu` | Pirate Radio → Pirate Radio Archives | present in Mixes; **added hub door** |
| 25 | One pirate station | `pirate_station` | Pirate Radio → Archives → station | present in Mixes; **added hub door** |
| 26 | Kool FM Sets | Pirate Radio → `filter_list(key=kool)` | Pirate Radio → Kool FM Sets | **added** |
| 27 | Mixes & Shows hub | `shows_menu` | Home → Mixes & Shows | present (existing) |
| 28 | Podcasts & Mixes | `media_menu` | Mixes & Shows → Podcasts & Mixes | present (existing) |
| 29 | One podcast feed | `feed` | Mixes & Shows → Podcasts & Mixes → feed | present (existing) |
| 30 | DNBRADIO | `dnb_list` | Mixes & Shows → DNBRADIO Shows | present (existing) |
| 31 | One DNBRADIO show | `dnb_play` | Mixes & Shows → DNBRADIO → show | present (existing) |
| 32 | GetDarker | `getdarker` | Mixes & Shows → GetDarker | present (existing) |
| 33 | One GetDarker set | `getdarker_page` | Mixes & Shows → GetDarker → set | present (existing) |
| 34 | Moxser | `moxser` | Mixes & Shows → Moxser | present (existing) |
| 35 | One Moxser mix | `moxser_mix` | Mixes & Shows → Moxser → mix | present (existing) |
| 36 | Mikus Musik | *(2014 menu; was absent from 3.9.60 classic)* | Mixes & Shows → Mikus Musik | **restored** |
| 37 | One Mikus post | *legacy `GetLinks9a/9b/9c`* | Mikus Musik → post (MP3 / Mixcloud) | **restored** |
| 38 | Demodulated Mixtapes | *(2014 menu; was absent from 3.9.60 classic)* | Mixes & Shows → Demodulated Mixtapes | **restored** |
| 39 | One Demodulated post | *legacy `GetLinks11/11a/11b`* | Demodulated Mixtapes → post (preview MP3 / Mixcloud) | **restored** |
| 40 | Live Radio | `radio_menu` | Home → Live Radio | present (existing) |
| 41 | Curated station | `station_live` | Live Radio → Kool FM / Rinse FM / Centreforce | present (existing) |
| 42 | Live genre doors | `radio_tag` | Live Radio → Hardcore/Jungle/Drum & Bass/House/UK Garage/Dubstep & Grime | **added** |
| 43 | Favourites | `fav_list` | Home → Favourites | present (existing) |
| 44 | Downloads | `downloads_menu` (via Favourites) | Home → Downloads | present (existing) |
| 45 | Search the Archive | `search` | Home → Search | present (existing) |
| 46 | Surprise Me | `surprise` | Home → Spinning Surprise | present (existing) |
| 47 | About & Sources | `about` | Home → About | present (existing) |
| 48 | Classic directory UI | `classic_root` | About → **Classic lists** (and plugin root fallback) | **added action** |

## What changed, and what deliberately did not

- **Added:** two home rooms (Tape Packs, Pirate Radio), their archive-backed
  child rooms, six Live Radio genre doors, `About → Classic lists`, and the
  Mikus/Demodulated source (`resources/lib/legacyblog.py` plus classic routes).
- **No removals:** the original 11 rooms keep their keys, labels, art, facts,
  codes and Back semantics; Search/Favourites/Downloads/About/Surprise are
  untouched. The home subtitle now counts 13 rooms at runtime.
- **One implementation per concern:** the classic menus and the screen read
  the same `filters.json`, `rave-catalog.json`, `RADIO_SECTIONS` and
  `ARCHIVE_SECTIONS` through the public
  `routes.classic_filters/classic_raves/classic_radio_sections/classic_archive_sections/classic_years`
  helpers. The screen does not carry a second copy of those taxonomies.
- **Orphan route:** `mixcloud_account` is registered but no classic menu emits
  it; it is listed explicitly in the parity test as an orphan so it can never
  be mistaken for a destination.

## Verification

```sh
python3 -m unittest test.test_parity_3_9_61 -v
python3 -m unittest discover -s test
```

The parity test fails when a new page mode is registered in
`routes.HANDLERS` without a matrix entry, or when a matrix destination is not
reachable by walking the screen data graph.
