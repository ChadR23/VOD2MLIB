# VOD2MLIB — VOD → Media-Library .strm Generator (v1.8.1)

Convert Dispatcharr's VOD catalogue into media-server-friendly `.strm` files (Plex, Jellyfin, Emby, Kodi) with optional NFO metadata, batch processing, and scheduled auto-rescan.

## Credits

- **Original author:** [shedunraid](https://github.com/shedunraid) — created v0.x–v1.3 ([upstream repo](https://github.com/shedunraid/VOD2MLIB)).
- **Fork maintainer:** [R3XCHRIS](https://github.com/R3XCHRIS) — v1.4+ adds scheduling, bug fixes, and submission to the official Dispatcharr Plugins repo. The upstream has been dormant since early 2026; this fork continues maintenance.
- Distributed under the MIT License.

## What's New in v1.8.1

- **Full rescan now requires confirmation.** Clicking `[GENERATE] Full rescan` pops a dialog explaining the action walks every Movie and every Series, re-fetches episodes from the M3U source, and may take many minutes on large catalogues — and reminds you the cron does this nightly. Prevents accidental long-running clicks.
- Description tightened to: *"Rescan then force regenerate Movies + Series. What cron fires."*

## What's New in v1.8.0

Manifest-side UX pass — the most we can do without touching Dispatcharr's frontend.

- **Settings tab now grouped.** Four `info`-type section dividers (`Paths & host`, `Movies`, `Series`, `Auto-rescan schedule`) split the previously flat field list into thematic blocks. The existing `About` block at the top stays.
- **Action labels match the design's renaming map.** Sentence case throughout, with uppercase section prefixes:
  - `Scan for VODs` → `[LIBRARY] Catalogue snapshot`
  - `[Generate] Movie .strm files` → `[GENERATE] Movies`
  - `[Generate] Series .strm files` → `[GENERATE] Series`
  - `[Rescan & Generate] All` → `[GENERATE] Full rescan`
  - `[Schedule] Apply` → `[SCHEDULE] Apply / Update`
  - `[Schedule] Remove` → `[SCHEDULE] Unschedule`
  - `[⚠️ Cleanup] Movies / Series` → `[⚠ DANGER] Clean up Movies / Series`
- **Right-side button labels condensed** to single verbs: `Generate`, `Rescan all`, `Apply`, `Remove`, `Clean up`. Cleaner row visual.
- **Rescan description trimmed** to fit one row at typical viewport widths.

A full structural redesign (proper section headers as render-time UI, inline schedule status card, live-data meta chips) is out of scope for any plugin-side change — those require Dispatcharr frontend work. The current shape is the ceiling of what the plugin manifest alone can achieve.

## What's New in v1.7.1

- Action descriptions condensed to single-line so Run buttons stay right-aligned with their action title (Dispatcharr's UI drops buttons below when descriptions wrap).
- `[Rescan] All (Movies + Series)` renamed to `[Rescan & Generate] All (Movies + Series)` to better reflect its dual nature: it both refreshes existing series and adds new ones.

## What's New in v1.7

UI clarity pass — the Actions panel was confusing in v1.6 (misleading descriptions, no confirm dialogs, mixed concerns). Fixes:

- **Action labels now use `[Section]` prefixes** to visually group: `[Scan]`, `[Generate]`, `[Rescan]`, `[Schedule]`, `[⚠️ Cleanup]`. The flat list now reads top-to-bottom in workflow order.
- **Confirm dialogs actually work** for destructive actions (`Cleanup Movies`, `Cleanup Series`, `Remove Schedule`). Earlier versions declared confirms in `plugin.json` but the runtime ignores manifest actions — now they live in the Python class where Dispatcharr reads them.
- **Accurate descriptions.** Cleanup descriptions no longer claim to "remove all folders" — they correctly describe the v1.5+ selective behavior. Generate descriptions explain the skip semantics. Apply Schedule mentions the snapshot rule.
- **`Rescan All` now forces `Refresh Existing Series` ON** regardless of the saved setting. The action's name promised rescan; the implementation now matches. The global `Refresh Existing Series` setting still applies to the individual `Generate Series` action for fast manual iteration.
- **`Apply Schedule` warns** when you schedule `generate_series` with `Refresh Existing Series` OFF — the cron would silently fail to pick up new episodes. The warning appears in both the toast and the log.
- **Buttons now have colors and labels** — Generate (green filled), Rescan (teal filled), Cleanup (red filled with confirm), Schedule status/apply (blue outline), Remove Schedule (orange outline with confirm).
- **New `About` info field** at the top of Settings explaining the workflow.

## What's New in v1.6

- **Rescan-friendly series processing.** Series no longer skip wholesale once their folder exists — episodes are checked individually and only missing `.strm` files are written. New episodes added upstream are picked up on the next run.
- **New setting: `Refresh Existing Series`** (boolean, default off). When ON, the plugin re-fetches the episode list from the M3U source for every series and re-evaluates already-processed series. Turn this ON before clicking **Apply Schedule** so cron rescans actually find new content.
- **`tvshow.nfo` refresh:** with `Refresh Existing Series` ON, the plugin re-writes `tvshow.nfo` so metadata edits (plot, genre) propagate.
- **Cleaner result messages**: per-series log now shows `+3 new episodes` or `up-to-date (24 episodes on disk)`. Run summary differentiates "series with new content" vs "series up-to-date".
- **Fault tolerance**: the M3U re-fetch (which talks to your IPTV provider) is wrapped in try/except so a single failed series doesn't kill the rest of the batch.

### Recommended schedule setup

1. Turn ON **Refresh Existing Series**.
2. Set **Batch Size (Series)** to **All series** (or a high number).
3. Set **Auto-Rescan Schedule** (default `0 3 * * *` = 03:00 daily).
4. Set **Scheduled Action** to **Full rescan (movies + series)**.
5. Click **Apply Schedule**. The current settings are snapshotted into the periodic task.
6. Verify via **Show Schedule Status**.

The first scheduled run after upgrading to v1.6 may take longer than usual because every series is re-evaluated. Subsequent runs are fast — most series come back as "up-to-date" without writing files.

## What's New in v1.5

- **Bug fixes:**
  - Folder names no longer duplicate the year (e.g. `Aladdin (2026) (2026)` → `Aladdin (2026)`).
  - Series `Batch Size` now actually limits how many series are processed (previously the limit was unreachable due to a thread-pool order bug).
  - Episode lookup is now filtered at the database level rather than scanning the entire M3U episode table per series — large catalogues are dramatically faster.
  - `_clean_title` no longer over-strips short uppercase prefixes from real titles like `AC-130`.
  - `Scan for VODs` now reports unique movie/series counts, not duplicate-counted M3U relations.
  - `generate_nfo` and `generate_series_nfo` toggles are now exposed in the Dispatcharr UI (previously rejected because of an invalid field type).
- **Cleanup is now non-destructive:** `Clean Up Movies` / `Clean Up Series` only delete the `.strm` and `.nfo` files this plugin created. User-added files (subtitles, posters, extras) are preserved; folders are removed only if empty.
- **Submission-ready:** added a `plugin.json` manifest with proper field types, button styling, and confirm dialogs.

## What's New in v1.4

- **Rescan All action**: One-click full rescan that runs scan + movies + series in sequence.
- **Scheduled Auto-Rescan (cron)**: Register a periodic task using a standard 5-field cron expression (default `0 3 * * *` = daily at 3 AM). Uses `django-celery-beat`.
- **Schedule manager actions**: `Apply Schedule`, `Remove Schedule`, `Show Schedule Status`.

### Setting up the schedule

1. Set **Auto-Rescan Schedule (cron)** to your desired expression (e.g. `0 3 * * *`).
2. Set **Scheduled Action** to what you want it to run (default: full rescan).
3. Click **Apply Schedule**. The plugin snapshots your *current* settings into the periodic task — if you later change `root_folder`, `dispatcharr_url`, batch sizes, or NFO toggles, click **Apply Schedule** again to refresh the snapshot.
4. Use **Show Schedule Status** to verify the task is registered, see the cron expression, last run, and run count.
5. **Remove Schedule** unregisters the periodic task.

Requires `django-celery-beat` and a running Celery beat scheduler in your Dispatcharr deployment. If `django-celery-beat` isn't available, the manager actions log a clear message and you can fall back to a host-side cron job hitting the Dispatcharr plugin action API.

## What's New in v1.1

- **Batch Size Options**: Choose 10, 50, 100, 200, 500, or All movies
- **Total Count Display**: Shows total VODs in database before processing
- **Progress Logging**: Logs every 50th movie to avoid spam

## Installation

1. Map a host folder to `/VODS` in your Dispatcharr container (e.g. `-v /opt/dispatcharr-vods:/VODS`).
2. Zip the `plugin.py`, `plugin.json`, `__init__.py`, `LICENSE`, and `README.md` files.
3. Dispatcharr → Plugins → Import → upload the zip → enable the plugin.

## Settings

- **Root Folder for Movies / Series:** paths inside the container (default `/VODS/Movies` and `/VODS/Series`).
- **Dispatcharr URL:** the externally-reachable URL of your Dispatcharr instance (NOT `localhost`). It's baked into every `.strm`, so it must resolve from your media server.
- **Batch Size (Movies / Series):** how many to process per click. Start at 10 to verify, scale up.
- **Generate Movie / Series NFO Files:** toggle metadata file creation.
- **Auto-Rescan Schedule (cron) / Scheduled Action:** see "Setting up the schedule" below.

## Usage

### First Time
1. Set Batch Size to **10**
2. Click "Generate .strm Files"
3. Verify 10 movies created correctly
4. Test playback in media server

### Scale Up
1. Set Batch Size to **50**
2. Run again - processes next 50
3. Keep increasing as comfort grows

### Process All
1. Set Batch Size to **All**
2. Run once - processes entire catalog

## Output Example

```
============================================================
VOD .strm Generator v1.1.0
Action: generate
============================================================

Configuration:
  Root Folder: /data/movies
  Dispatcharr URL: http://192.168.99.11:9191
  Batch Size: 10

Scanning database...
Total VODs in database: 1234

Querying movies for this batch...
Processing 10 of 1234 movies
Found 10 movies to process

Root folder ready: /data/movies

Processing movies:
------------------------------------------------------------

[1/10] Avatar
  Year: 2009
  Folder: Avatar (2009)
  UUID: abc-123-def
  Stream ID: 1234567
  ✓ Created: /data/movies/Avatar (2009)/Avatar (2009).strm

... (details for other movies) ...

============================================================
SUMMARY:
  Total in DB:  1234
  Processed:    10
  Created:      10
  Skipped:      0
  Errors:       0
============================================================

Complete! Check your media server to verify playback.
```

## Folder Structure

```
/data/movies/
├── Avatar (2009)/
│   └── Avatar (2009).strm
├── Inception (2010)/
│   └── Inception (2010).strm
└── ...
```

## Differences from v0.1

| Feature | v0.1 | v1.1 |
|---------|------|------|
| Batch size | 5 only | 10, 50, 100, 200, 500, All |
| Total count | No | Yes |
| Progress | Every movie | Every 50th + first 10 |
| Action name | "Test Mode" | "Generate .strm Files" |

## Simple & Clean

Based on working v0.1 code with minimal additions:
- Same imports
- Same structure
- Same reliability
- Just adds batch size options

## Next Steps

Once this works perfectly:
- Add genre organization
- Add incremental processing (skip existing)
- Add progress notifications
- Add more features

But for now - keep it simple!


