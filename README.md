# Rave Player 3.0

Oldskool rave, jungle, hardcore, house & garage and pirate radio for Kodi —
rebuilt in 2026 from the 2014 original.

![Rave Player](icon.png)

## What it does

- **Rave tape packs, jungle, hardcore, house & garage** — pulled from the
  Internet Archive's public collections, streamed straight to Kodi.
- **Pirate radio archive and drum & bass sets** — Archive audio collections.
- **Live radio** — oldskool, jungle, drum & bass, hardcore, house/garage and
  pirate stations from [radio-browser.info](https://www.radio-browser.info/).
- **Search** — full-text search across the whole Archive from inside Kodi.

## Why it was rebuilt rather than patched

The 2014 add-on was Python 2, ran on `xbmc.python` 2.1.0 (Kodi 13), and
depended on three modules that no longer exist in any current repository. It
also scraped ~30 fan sites with 70 bespoke regex functions, and most of those
sites are gone. Rewriting it as a thin layer over two maintained, public APIs
means a dead source can't take the whole add-on down with it.

## Requirements

- Kodi 21 (Omega) or Kodi 22 (Piers)
- Nothing else. No module dependencies, no external binaries.

## Install

1. Download `plugin.audio.raveplayer-3.0.0.zip` from `dist/`.
2. Kodi → Add-ons → Install from zip file.
3. Enable "Unknown sources" first if Kodi asks.

## Development

Everything is standard library plus Kodi's own modules.

```
raveplayer/
├── addon.xml
├── default.py              # entry point
├── resources/
│   ├── settings.xml
│   └── lib/
│       ├── routes.py       # menu + routing (sections are data, not code)
│       ├── archive.py      # Internet Archive provider
│       ├── radio.py        # radio-browser.info provider
│       ├── ui.py           # list items and artwork
│       ├── http.py         # tiny JSON transport
│       └── kodi.py         # Kodi wrappers
└── test/
    ├── stubs/              # fake xbmc* modules
    └── run.py              # runs the routes outside Kodi
```

Smoke-test any route without Kodi:

```sh
python3 test/run.py root
python3 test/run.py archive_list key=rave page=1
python3 test/run.py archive_item id=dreamscape-19-toil-and-trouble-jungle-8-tape-pack-1995
python3 test/run.py radio_tag key=oldskool
```

Build the installable zip and the Kodi repository layout:

```sh
./scripts/build.sh        # dist/plugin.audio.raveplayer-<version>.zip
./scripts/build-repo.sh   # repo/addons.xml + zip, for install-from-repo
```

Install straight onto a Shield or any Android Kodi box over ADB (needs one
`Allow debugging` tap on the device):

```sh
./scripts/install-shield.sh
```

Publish (creates the repository if missing):

```sh
GITHUB_TOKEN=ghp_xxx ./scripts/publish.sh
```

## Licence

GPL-3.0-or-later, same as the original. The add-on hosts nothing: everything
is streamed from third-party archives and radio directories.
