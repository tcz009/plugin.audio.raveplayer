# Rave Player — Verified Content Sources

Research date: **2026-10-29** · Method: `curl` + Python `urllib`/`json` only, normal UA (`RavePlayerResearch/1.0`), 1–2 requests per host endpoint, no browsers.
Every row below was confirmed by a live HTTP call made during this session. Counts are `numFound` as returned at the time of writing and **drift by a few items between calls** — treat them as order-of-magnitude, not constants.

---

## 1. Internet Archive — verified search queries

Endpoint used:

```
https://archive.org/advancedsearch.php?q=<QUERY>&fl[]=identifier&fl[]=title&fl[]=year&fl[]=downloads&rows=10&output=json
```

| # | Section name | Query string | numFound | Example identifier | Audio formats found |
|---|---|---|---|---|---|
| 1 | The Rave Tapes (curated collection) | `collection:ravetapes AND mediatype:audio` | **724** | `Dreamscape_3_-_Absolutely_No_Compromise_10.3.92` | 10 × `.mp3`, 10 × `.ogg` |
| 2 | Rave tape packs (phrase) | `"rave tape pack"` | **67** | `dreamscape-19-toil-and-trouble-jungle-8-tape-pack-1995` | 9 × `.mp3` |
| 3 | Tape packs by title | `title:("tape pack" OR "tape packs") AND mediatype:audio` | **50** | `helter-skelter-tape-packs` | 1,645 × `.mp3` |
| 4 | Tape pack + genre (broad sweep) | `"tape pack" AND (jungle OR hardcore OR rave OR "drum and bass" OR "old skool")` | **164** | `helter-skelter-tape-packs` | 1,645 × `.mp3` |
| 5 | Dreamscape | `title:(dreamscape) AND mediatype:audio AND subject:(rave OR jungle OR hardcore OR "drum and bass")` | **51** | `dreamscape-19-toil-and-trouble-jungle-8-tape-pack-1995` | 9 × `.mp3` |
| 6 | Helter Skelter | `title:("helter skelter") AND mediatype:audio AND subject:(rave OR jungle OR hardcore OR "drum and bass" OR house)` | **7** | `helter-skelter-tape-packs` | 1,645 × `.mp3` |
| 7 | Fantazia | `title:(fantazia) AND mediatype:audio` | **22** | `Fantazia_The_Big_Bang_27th_Nov_1993` | 4 × `.mp3`, 4 × `.ogg` |
| 8 | One Nation | `title:("one nation") AND mediatype:audio AND subject:(rave OR jungle OR hardcore OR "drum and bass")` | **57** | `photek-one-nation-say-it-1996` | 2 × `.mp3` |
| 9 | World Dance | `title:("world dance") AND mediatype:audio` | **25** | `World_Dance_94` | 7 × `.mp3`, 7 × `.ogg` |
| 10 | Pirate radio (Kool FM / Don FM / Centreforce) | `title:("kool fm" OR "don fm" OR "rush fm" OR "centreforce" OR "centerforce" OR "fantasy fm" OR "sunrise fm")` | **35** | `brockie-kool_fm-30th_october_1993` | 1 × `.mp3`, 1 × `.ogg` |
| 11 | Happy Hardcore | `title:("happy hardcore") AND mediatype:audio` | **107** | `happy-hardcore-1-9` | 263 × `.mp3` |
| 12 | Golden Era Jungle mixes | `title:(jungle) AND mediatype:audio AND subject:(rave OR "tape pack" OR "old skool" OR hardcore)` | **46** | `golden_era_jungle_mixes_archive` | 1,634 × `.mp3` |

**Additional verified queries (kept out of the main table to stay at 12):**

| Section | Query | numFound | Example |
|---|---|---|---|
| UK Garage / speed garage | `title:("uk garage" OR "speed garage" OR "2step" OR "2 step" OR "ukg") AND mediatype:audio` | **124** | `oldskoolgaragemixukg1` (6 × `.mp3`) |
| Slammin' Vinyl | `title:("slammin vinyl")` | **12** | `BadCompany-LiveAtSlamminVinylBagleysLondon-07.04.2000` (1 × `.mp3`, 1 × `.ogg`) |
| Cassette-tape collection by subject | `collection:cassettetapes AND subject:("rave" OR "jungle" OR "hardcore" OR "tape pack")` | **173** | `helter-skelter-tape-packs` |
| Acid house / Detroit techno | `title:("acid house" OR "chicago house" OR "detroit techno") AND mediatype:audio` | **115** | `DarrenRiain-AcidHouseDetroitTechnoOldskoolMix` |

### Playback URL pattern (verified)

```
https://archive.org/download/<identifier>/<url-encoded filename>
```

`GET` on `https://archive.org/download/Dreamscape_3_-_Absolutely_No_Compromise_10.3.92/Dreamscape%203%20Carl%20Cox%20A.mp3`
→ **HTTP/2 302**, `location: https://dn710802.ca.archive.org/0/items/...` (range request followed to a storage node).

### Gotchas that matter for the add-on

- **Never list files by `format` alone.** Tape-pack items are full of non-audio derivatives: `.afpk` (Columbia Peaks), `.png` (spectrograms/waveforms), `.xml`, `.sqlite`, `.torrent`, `.sfv`, `.nfo`. Filter by **extension** `.mp3` / `.ogg` / `.flac` / `.m4a`.
- **Formats actually present:** `VBR MP3` dominates, `Ogg Vorbis` on many items. **FLAC was not found** in any of the rave tape-pack items sampled (only 1,645 mp3 vs 0 flac in the largest item).
- `format` strings are inconsistent (`VBR MP3`, `128Kbps MP3`, `Ogg Vorbis`) — the `files[].name` extension is the reliable discriminator.
- Items can disappear or return an empty `files` array — `dreamscape-14-halloween-ball-sanctuary-milton-keynes` returned 60 files / 16 mp3 on the first check and **0 files** on a re-check ~10 minutes later. Always handle empty metadata gracefully.
- Queries using bare `subject:` or `title:` terms are heavily polluted: `subject:(jungle)` returns *The Jungle Book* (Librivox), `title:(dreamscape)` returns a 528 Hz meditation track, `title:(one nation)` returns political books, `title:(telepathy)` returns parapsychology scans. **Always pair scene terms with `mediatype:audio` and a scene-specific `subject:` filter**, or use exact scene names (Dreamscape, Fantazia, Helter Skelter) — those are clean.

---

## 2. radio-browser.info — verified tags

Endpoint used:

```
https://de1.api.radio-browser.info/json/stations/search?tag=<TAG>&limit=300&hidebroken=true&order=clickcount&reverse=true
```

Counts are the number of stations returned (capped at the `limit` of 300). "GB" = stations with `countrycode == "GB"`.

| Tag | Count | GB | Verdict |
|---|---|---|---|
| `oldskool` | 8 | 5 | **Excellent precision**, small pool — every GB station is on-genre |
| `jungle` | 55 | 24 | **Best overall** — most UK stations, includes Kool FM, Rinse, UK Bass Radio |
| `drum and bass` | 121 | 28 | **Strong** — good breadth, some EU/US filler |
| `hardcore` | 115 | 15 | **Good** — happy-hardcore/rave stations present |
| `garage` | 83 | 26 | **Useful** — overlaps heavily with `jungle` (same UK stations) |
| `breakbeat` | 30 | 7 | **Useful** — small, high hit-rate |
| `rave` | 57 | 5 | **Mixed** — top results are German commercial dance/chat radio; needs manual allow-listing |
| `house` | 300+ (API cap) | 22 | **Too broad** — global house radio, not oldskool-specific |
| `pirate` | 60 | 3 | **Reject** — Dutch pirate-schlager/volksmuziek, not UK pirate radio |
| `oldschool` | 28 | 4 | **Reject** — hip-hop/RnB/goldies, wrong genre |

### Example stations per useful tag

**`oldskool` (8 results)**
| Station | Country | `url_resolved` |
|---|---|---|
| Underground Bass | GB | `https://listen.undergroundbass.com:8804/stream` |
| Energy 1058 | GB | `http://tachyon.shoutca.st:8590/stream` |
| Happy Hardcore | GB | `https://audio-edge-3mayu.fra.h.radiomast.io/73055724-1141-41e2-a69b-24a6ca96c8e7` |

**`jungle` (55 results)**
| Station | Country | `url_resolved` |
|---|---|---|
| Rinse UK | GB | `https://admin.stream.rinse.fm/proxy/rinse_uk/stream` |
| Kool FM | GB | `https://admin.stream.rinse.fm/proxy/kool/stream` |
| UK Bass Radio | GB | `https://www.ukbassradio.com/stream` |
| *Old Skool Rave Tapes* | GB | `https://azuracast.oldskoolravetapes.co.uk/listen/old_skool_rave_tapes/listen` |

**`drum and bass` (121 results)**
| Station | Country | `url_resolved` |
|---|---|---|
| Bassdrive | US | `http://chi.bassdrive.co/` |
| Intamixx 80s 90s Radio UK | GB | `https://radio.intamixx.uk:8443/radio2` |
| NR1 Drum and Bass Radio | GB | `https://radio.listen-nr1dnb.com/listen/nr1_dnb_radio/radio.mp3` |

**`hardcore` (115 results)**
| Station | Country | `url_resolved` |
|---|---|---|
| Kool FM | GB | `https://admin.stream.rinse.fm/proxy/kool/stream` |
| Happy Rave Radio [90s Happy Hardcore] | US | `https://happyrave-rex.radioca.st/stream` |
| I Like It Oldskool | GB | `https://ilikeitoldskool.radioca.st/stream` |

**`garage` (83 results)**
| Station | Country | `url_resolved` |
|---|---|---|
| Intamixx 80s 90s Radio UK | GB | `https://radio.intamixx.uk:8443/radio2` |
| Rinse UK | GB | `https://admin.stream.rinse.fm/proxy/rinse_uk/stream` |
| UK Bass Radio | GB | `https://www.ukbassradio.com/stream` |

**`breakbeat` (30 results)**
| Station | Country | `url_resolved` |
|---|---|---|
| UK Bass Radio | GB | `https://www.ukbassradio.com/stream` |
| Underground Bass | GB | `https://listen.undergroundbass.com:8804/stream` |
| Eruption Radio | GB | `http://streaming04.liveboxstream.uk:8116/stream` |

### Stream endpoint verification (actual 6-second GET, ICY headers captured)

| Station | Result | Evidence |
|---|---|---|
| Kool FM | ✅ | `HTTP/1.1 200`, `Content-Type: audio/aacp`, `icy-genre: Drum & Bass`, `icy-br: 128` |
| Rinse UK | ✅ | `HTTP/1.1 200`, `audio/aacp`, `icy-name: Rinse FM`, 343 KB received in 6 s |
| Old Skool Rave Tapes | ✅ | `HTTP/2 200`, `content-type: audio/aac`, `icy-genre: Old Skool Rave, Hardcore, Jungle, Drum and Bass` |
| Happy Rave Radio | ✅ | `HTTP/1.1 200`, `audio/mpeg`, `icy-br: 320`, 457 KB in 6 s |
| Underground Bass | ✅ | `HTTP/1.1 200`, `audio/mpeg`, `icy-br:256`, `icy-genre:DnB` |
| Intamixx 80s 90s | ✅ | `HTTP/1.1 200`, `audio/mpeg`, `icy-br: 128` |
| Energy 1058 | ✅ | `HTTP/1.0 200`, `audio/mpeg`, `icy-br:320`, `icy-genre:DnB Old Skool Jungle Nu Skool` |
| Bassdrive | ✅ | `HTTP/1.0 200`, `audio/mpeg`, `icy-br:192` |
| I Like It Oldskool | ✅ | `HTTP/1.1 200`, `audio/mpeg`, `icy-name: I Like It Oldskool`, `icy-genre: Oldskool` |
| UK Bass Radio | ✅ (after redirect) | `301 → 302 → HTTP/2 200`, `icy-name: UK Bass Radio` — **must follow redirects** |
| Happy Hardcore (radiomast) | ❌ | `HTTP/1.1 401 Unauthorized` — tokenised URL, expired/geo-locked |
| Fresh Soundz Radio | ⚠️ | Stream answers `200 audio/mpeg` but advertises `icy-name: This is my server name`, `icy-genre: Rock` — misconfigured, exclude |

**Notes:** most are SHOUTcast/Icecast and **do not answer `HEAD`** — use a 1–2 s `GET` and read the `icy-*` headers. `url_resolved` is the field to cache, but re-resolve occasionally: Rinse-hosted streams (`admin.stream.rinse.fm`) are stable, radiomast/zeno/radioca.st URLs churn.

---

## 3. Legacy domains from the 2014 add-on

Checked with a browser UA (`Mozilla/5.0 ... Chrome/124.0`), following redirects, reading status + `<title>` + body.

| Domain | Verdict | Evidence |
|---|---|---|
| **ravetapepacks.com** | **LIVE — real content, directly scrapeable** | `200` → `https://www.ravetapepacks.com/`, title `Rave Tape Packs \| Jungle, Hardcore, Drum & Bass, UK Garage tapepacks`. WordPress, taxonomy `?cat=NN` (67 `<audio>` tags on `?cat=10`). Direct MP3s: `https://www.ravetapepacks.com/music/AmazonVol10/Tape_1_-_Fabio.mp3`. **Hotlink-protected:** bare `HEAD` → `403`; `GET` with `Referer: https://www.ravetapepacks.com/` → `206 audio/mpeg`. No sitemap (`/sitemap.xml` 404, `/wp-sitemap.xml` 404) — crawl `?cat=` IDs. |
| **thepiratearchive.net** | **UNVERIFIABLE — Cloudflare challenge** | `403`, `cf-mitigated: challenge`, `server: cloudflare`, title `Just a moment...`. Cannot confirm content without a browser (out of scope). Likely alive but bot-gated. |
| **piratearchive.co.uk** | **UNVERIFIABLE — Cloudflare challenge** | Identical: `403`, `cf-mitigated: challenge`, title `Just a moment...`. |
| **oldskoolanthemz.com** | **LIVE (redirects)** | `200` → `https://www.oldskoolanthems.com/`, title `Old Skool Anthems`. XenForo forum (109 KB page): forums, "OSA Radio", Tunes, Mixes, Events, Flyers. Content is behind forum navigation — scrapeable as HTML, but not a flat media index. Note the `.com` → `.com` (spelling change: anthe**mz** → anthe**ms**). |
| **twiceasnice.co.uk** | **LIVE but repurposed — NOT the tape archive** | `200`, title `TwiceasNice – Sexy & Stylish`. Body is an events/DJ-booking agency ("HOME ABOUT US What we do Services Contact Us ENTERTAINMENT Music / DJ Playlist ... EVENTS UK Events International Events PHOTOS"). No tape-pack archive. |
| **jungletapes.com** | **LIVE — excellent, directly scrapeable** | `200`, title `Jungle Tapes \| An audio library of Toronto jungle/drum n' bass radio shows digitized from our cassette tape collection`. Drupal. Show pages `/show/<slug>` embed direct files, e.g. `https://jungletapes.com/sites/default/files/jungle_tapes_uploaded_audio_files/2000.07.21-Mystical-Influence-Thru-the-Mirror-Side-A-Dan_0.mp3` → `200`. |
| **torontoravemixtapearchive.com** | **LIVE — excellent, flat MP3 index** | `200`, title `Home Page - Toronto Rave Mixtape Archive`. Listing pages `/jungle.html`, `/updates.html` expose raw `/files/mixtape/<name>.mp3` hrefs. Verified `GET`/`HEAD` on `Brockie Mc Fearless - Live at Syrous - Spellbound - July 6 1996.mp3` → `HTTP/2 200`, `content-type: audio/mpeg`, `content-length: 205751901`. |
| **systemslibrarian.co.za** | **LIVE but wrong site — dead as a rave source** | `200`, title `Systems Librarian`. Body: "Africa's leading website on Systems / Technical Librarianship & Integrated Library Systems (ILS)". Domain now hosts an unrelated LIS academic site. |
| **artmeetsscience.co.uk** | **PARKED** | `200`, title `artmeetsscience.co.uk is almost here!`, body "Upload your website to get started. Need help? Admin Panel DreamHost". 776-byte placeholder. |
| **braindamageradio.com** | **LIVE — streaming radio + mixes** | `200`, title `BrainDamageRadio.com`, `<h1>Latest Mixes</h1>`. Joomla + JReviews. Playlist files present: `/stream/bdr-winamp.pls` → `[playlist] File1=http://69.64.36.195:8010 Title1=BDR Stream`; also `/stream/bdr-real.ram`, `/stream/bdr-mediaplayer.asx`. Mix metadata rendered server-side (scrapeable). |

---

## 4. Recommended menu (7 top-level sections)

| Section | Primary source | Secondary / fallback |
|---|---|---|
| **1. Rave Tape Packs** | IA `collection:ravetapes AND mediatype:audio` (724) | ravetapepacks.com `?cat=` crawl (needs `Referer` header) |
| **2. Jungle / Drum & Bass** | IA `golden_era_jungle_mixes_archive` query (46) + `"tape pack"` genre sweep (164) | radio-browser `jungle` (55) / `drum and bass` (121) |
| **3. Happy Hardcore** | IA `title:("happy hardcore") AND mediatype:audio` (107) | radio-browser `hardcore` (115) — Happy Rave Radio, I Like It Oldskool |
| **4. Pirate Radio** | IA Kool FM / Don FM / Centreforce query (35) | Live: Kool FM, Rinse UK, Old Skool Rave Tapes streams |
| **5. UK Garage** | IA UK Garage query (124) — `oldskoolgaragemixukg1` etc. | radio-browser `garage` (83) |
| **6. Jungle Tapes Toronto** | jungletapes.com `/show/<slug>` direct MP3s | torontoravemixtapearchive.com `/files/mixtape/*.mp3` |
| **7. Live Radio** | radio-browser `oldskool` + `jungle` + `breakbeat` tags | braindamageradio.com `.pls` stream |

**Optional 8th:** *Classic Rave Events* (Dreamscape / Fantazia / Helter Skelter / One Nation / World Dance — 155 items combined) if you want event-browsable navigation rather than genre browsing.

### Ranking, if you only build three things

1. **`collection:ravetapes`** — 724 curated items, one query, on-genre, already grouped as "The Rave Tapes" (credited to Stamina MC / Will @ Sublogic). This alone is a shippable add-on.
2. **`golden_era_jungle_mixes_archive`** — a *single item* with 1,634 MP3s, enough for a whole Jungle section without pagination.
3. **radio-browser `jungle` + `oldskool`** — the live-radio tab; 63 stations, 29 UK, verified ICY audio.

### Open risks

- **ravetapepacks.com** serves full MP3s with only a `Referer` check — trivially bypassable, so likely not rights-cleared. Prefer IA as primary; treat this as a catalogue/index source rather than a hotlink target.
- **Cloudflare** blocks thepiratearchive.net / piratearchive.co.uk to non-browser clients — needs a server-side proxy or manual curation, not a direct add-on fetch.
- IA counts and item availability shift (see `dreamscape-14` above); cache identifiers, tolerate 404/empty metadata.
- radio-browser `url_resolved` values rot — re-resolve on failure and keep `stationuuid` as the stable key.
