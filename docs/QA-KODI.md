# Rave Player — Shield/Kodi QA checklist (3.9.36)

Repeat this on the Nvidia Shield before a release. It is deliberately short:
one pass through every user-visible surface, with a hard check that the add-on
never leaves Kodi. Record the result and any Kodi log line in the table at the
bottom.

## Preconditions

- Kodi 20 (Nexus) through Kodi 22 (Piers), Estuary skin, 1080p.
- Rave Player **3.9.36** installed from `repository.raveplayer-1.0.0`
  (or the release zip) and Kodi restarted once so the theme texture cache is
  refreshed.
- Network available; a small Archive.org or Moxser direct MP3 available for the
  download checks. Do not download a large pack just for QA.
- Optional: `RAVE_DOWNLOAD_DIR` is not needed on the Shield; downloads go to
  `special://userdata/downloads/raveplayer/`.
- Full suite on the build machine: `python3 -m unittest discover -s test`
  → **524 tests OK**.

## 1. Install / update

- [ ] Add-ons → Rave Player shows **3.9.36**; About & Sources shows the same
  version.
- [ ] Updating from 3.9.20 keeps favourites/downloads and does not reset the
  spinner setting.
- [ ] `Kodi.log` has no traceback during startup or the first root render.

## 2. Root and hubs

- [ ] Root has exactly nine rows, in this order:
  **Latest · Surprise Me · Tape Packs · Mixes & Shows · Live Radio ·
  Curated Gems · Favourites · Search the Archive · About & Sources**.
- [ ] Each row has its own sticker icon; focus fanart changes per row.
- [ ] Tape Packs: Rave Tape Packs · Jungle / Drum & Bass · Hardcore · House ·
  UK Garage · Pirate Stations · All Tape Packs · By Year · Classic Pack Series ·
  By Rave & Venue · Back.
- [ ] Mixes & Shows: Podcasts & Mixes · DNB Radio · Moxser Mixes · Hardscore.com
  · GetDarker only when the Mixcloud add-on is installed · Back.
- [ ] Live Radio: Kool FM · Rinse FM · Oldskool & Rave · Jungle · Drum & Bass ·
  Hardcore · House · UK Garage · Breakbeat · Back.
- [ ] Curated Gems: Pirate Radio Archives · Rave Archive UK (only with Mixcloud)
  · Legacy Archives (2014) · Back.
- [ ] Back returns to the root; no browser, Downloader or Android chooser opens.

Reference renders: `docs/theme-2026/root-after.png`,
`docs/theme-2026/hubs-after.png`.

## 3. Kool FM and Rinse FM live

- [ ] Live Radio → Kool FM starts the live stream; the Kool on-air row on
  Latest also starts it when available.
- [ ] Live Radio → Rinse FM starts the live stream.
- [ ] Both streams show the station name/art; stop works; no browser opens.
- [ ] If a stream is down, the row fails soft (no crash, no fallback to a web
  page); note the time and retry later.

Expected endpoints are the Rinse streaming proxy:
`https://admin.stream.rinse.fm/proxy/kool/stream` and
`https://admin.stream.rinse.fm/proxy/rinse_uk/stream`.

## 4. Pack playback

- [ ] Latest or Tape Packs → open a pack; tracks list with sensible titles.
- [ ] Play a track; artwork/plot appear; stop returns cleanly.
- [ ] Context menu → **Play all from here** (or **Shuffle pack**) starts a
  playlist and does not auto-advance into an unrelated folder.
- [ ] Back returns to the pack and then the hub/root without a reload loop.
- [ ] No raw platform page URL is sent to Kodi as a playable item.

## 5. Downloads and Downloads view

Use one small direct MP3/M4A from Archive.org, Moxser, Hardscore or Pirate
Radio Archives.

- [ ] Context menu on the direct item shows **Download**; the confirmation
  shows filename, size and free space.
- [ ] Start it; the progress dialog (or opt-in spinner, §6) updates and the
  download completes; the success notification appears.
- [ ] Favourites → **Downloads** lists the file with its size and date; playing
  it uses the local copy (test with Wi-Fi briefly off if practical).
- [ ] Delete from the Downloads context menu removes both the local file and
  its metadata row.
- [ ] A file removed externally is marked **missing** and can be deleted.
- [ ] No Download row appears on podcast/RSS, Legacy, GetDarker,
  Mixcloud/SoundCloud/YouTube or live/HLS rows.

Reference render: `docs/theme-2026/downloads-after.png`.

## 6. Spinner toggle (opt-in)

- [ ] Settings → General → **Spinning-head download window (prototype)** is
  **off** by default; downloads use the ordinary progress dialog.
- [ ] Turn it **on**, start a small download: the overlay shows rotating head,
  filename, percent, size/remaining and “Back / Stop to cancel”; Kodi does not
  block.
- [ ] Cancel once and confirm the `.part` file is gone and no final file or
  metadata row is left.
- [ ] Complete once; the overlay closes and the success notification appears.
- [ ] Turn the setting **off** again after testing (or leave as the owner
  prefers) and confirm the dialog fallback.

Reference: `docs/SPINNER-3.9.19.md` and `docs/spinner-preview.png`.

## 7. Hand-off absence (no browser / Downloader)

- [ ] Every root/hub/detail action stays inside Kodi; no browser, Android
  intent chooser, Downloader app or external player opens.
- [ ] Mixcloud content only appears when `plugin.audio.mixcloud` is installed;
  it opens that add-on. If missing, the row is hidden — no dead link.
- [ ] YouTube links (if a source exposes one) open `plugin.video.youtube`;
  otherwise they are ignored.
- [ ] **SoundCloud has no row and no hand-off** in the Kodi build. Any
  SoundCloud link is ignored; About says “Web version only”.
- [ ] Saved/deep-linked Mixcloud/YouTube/SoundCloud pages never appear as raw
  item URLs (3.9.17 gate).
- [ ] `Kodi.log` shows no `android.intent`, `StartActivity`, browser package,
  `plugin.audio.soundcloud` or raw `mixcloud.com`/`youtube.com` playback URL
  from a list item.

## 8. About & Sources

- [ ] Version/licence row: **Rave Player 3.9.36 — GPL-3.0**.
- [ ] Source rows are present for Internet Archive, Mixcloud, SoundCloud,
  radio-browser.info, Moxser, Hardscore, DNB Radio, GetDarker, podcast/RSS
  feeds, Pirate Radio Archives, Kool/Rinse, RaveTapePacks, JungleTapes and
  Toronto Rave Mixtape Archive.
- [ ] SoundCloud plot reads **“Web version only — SoundCloud is not part of the
  Kodi build; there is no Kodi source row or hand-off.”**
- [ ] The README **Sources & credits** table links resolve (checked 2026-11-01).
- [ ] About is read-only: every row stays in Kodi; Back returns to root.

## 9. Local smoke commands (build machine)

```sh
python3 -m unittest discover -s test          # 524 tests
python3 test/run.py root
python3 test/run.py packs_menu
python3 test/run.py shows_menu
python3 test/run.py radio_menu
python3 test/run.py downloads_menu
python3 test/run.py about
```

## Result record

| Field | Value |
|---|---|
| Date / tester | |
| Shield Kodi version | |
| Add-on version | 3.9.36 |
| Root / hubs | Pass / Fail |
| Kool / Rinse live | Pass / Fail |
| Pack playback | Pass / Fail |
| Download + Downloads view | Pass / Fail |
| Spinner toggle | Pass / Fail |
| Hand-off absence | Pass / Fail |
| About & Sources | Pass / Fail |
| Kodi log notes | |
