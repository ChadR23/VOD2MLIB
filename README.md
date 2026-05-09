# VOD2MLIB — Dispatcharr VOD → media library bridge

A Dispatcharr plugin that converts your VOD catalogue into a folder of `.strm` files (with optional NFO metadata) that media servers like Jellyfin, Emby, Kodi, or ChannelsDVR can index and play.

## Credits

- **Original author:** [shedunraid](https://github.com/shedunraid) — created v0.x–v1.3 ([upstream repo](https://github.com/shedunraid/VOD2MLIB)).
- **Fork maintainer:** [R3XCHRIS](https://github.com/R3XCHRIS) — v1.4+ adds scheduling, bug fixes, packaging for the [official Dispatcharr Plugins catalogue](https://github.com/Dispatcharr/Plugins). Upstream has been dormant since early 2026; this fork continues maintenance.
- MIT License.

> **Plex users:** Plex does *not* play `.strm` files. Jellyfin and ChannelsDVR do. See [Plex compatibility](#plex-compatibility) below.

---

## Install

1. **Map a host folder to `/VODS` in your Dispatcharr container.** Example Compose snippet:
   ```yaml
   volumes:
     - /opt/dispatcharr-vods:/VODS
   ```
2. **Zip the plugin files** (`plugin.py`, `plugin.json`, `__init__.py`, `LICENSE`, `README.md`).
3. **Dispatcharr → Plugins → Import** → upload the zip → enable the plugin.

Requires Dispatcharr **v0.24.0** or later. The auto-rescan feature additionally needs `django-celery-beat` (Dispatcharr ships with it).

## Settings

The Settings tab is grouped into four sections:

| Section | Field | What it does |
|---|---|---|
| **Paths & hosts** | Root Folder for Movies / Series | Paths inside the container (defaults `/VODS/Movies`, `/VODS/Series`) |
|  | Dispatcharr URL | Externally-reachable URL of Dispatcharr (NOT `localhost`). Baked into every `.strm`. |
| **Movies** | Batch Size | How many movies to process per click |
|  | Generate Movie NFO Files | Toggle Kodi/Jellyfin metadata generation |
| **Series** | Batch Size (Series) | How many series to process per click |
|  | Generate Series NFO Files | Toggle `tvshow.nfo` and per-episode `.nfo` |
|  | Refresh Existing Series | Re-evaluate already-processed series for new episodes (cron-friendly) |
| **Auto-rescan schedule** | Schedule (cron) | Standard 5-field expression. Default `0 3 * * *` (daily 03:00) |
|  | Scheduled Action | What the cron fires (full rescan recommended) |

## Workflow

**First run.** Configure paths → click `[LIBRARY] Catalogue snapshot` to verify the plugin can see your VODs → click `[GENERATE] Movies` with Batch Size 10 → spot-check the output → scale up.

**Scaling up.** Increase Batch Size, click again. Existing files are skipped, so each click only processes new ones.

**Auto-rescan.**
1. Turn ON **Refresh Existing Series**.
2. Set **Scheduled Action** to **Full rescan**.
3. Click `[SCHEDULE] Apply / Update`.
4. Verify with `[SCHEDULE] Show status` — last run / total runs populate after the first cron tick.
5. Optional: click `[SCHEDULE] Test fire now` to immediately replay the scheduled action without waiting for the next cron tick.

The cron snapshots your settings at click-time. Re-click Apply after changing any setting to refresh the snapshot.

## Plex compatibility

Plex does **not** play `.strm` files (it can index them but the URL inside doesn't play). This is a long-standing Plex limitation, not a plugin bug. Workable paths:

- **Jellyfin alongside Plex** — Jellyfin plays `.strm` natively. Run it in a container next to Plex, point both at the same library folder.
- **ChannelsDVR's Personal Media** — works perfectly with our output (point CDVR at the Movies/Series root).
- **Kodi** — works.
- **Emby** — works.

See [the Plex investigation in this repo's issues](https://github.com/R3XCHRIS/VOD2MLIB/issues) (TBD) for a longer write-up.

## Troubleshooting

**"Unknown action" error in the toast.** Dispatcharr cached an old version of the plugin module. `docker restart dispatcharr` clears it. Toggling enable/disable on the plugin also forces a reload.

**The Run button drops below the action title instead of right-aligning.** That's Dispatcharr's UI flex-wrap when the description spans 2+ lines. We keep descriptions single-line to avoid this; if it happens again, the description is too long for your viewport.

**Cron task registered but didn't fire.** Check `[SCHEDULE] Show status` — `last_run` should populate after the first scheduled tick. If still `never` after the expected time:
- Verify Celery beat is running in your Dispatcharr deployment.
- Check container logs for `core.scheduling Updated periodic task 'vod2mlib.auto_rescan'`.
- Click `[SCHEDULE] Test fire now` to confirm the task itself works (proves it's a scheduling-layer issue, not a plugin issue).

**Schedule fires but no new files appear.** Most likely: `Refresh Existing Series` is OFF and your existing series already have folders, so the cron only adds *new* series. Toggle Refresh Existing ON, click Apply Schedule again to update the snapshot.

**Folders named `Aladdin (2026) (2026)` (duplicate year).** This was a bug in v1.4 and earlier. Fixed in v1.5+ but pre-existing duplicate-year folders aren't auto-renamed. Run `[⚠ DANGER] Clean up Movies` once to remove them, then re-run `[GENERATE] Movies` to regenerate cleanly. (Cleanup deletes only `.strm`/`.nfo` — user-added subtitles/posters survive.)

**Generate Series fails for some series.** The summary lists the failed series names with their errors. Common causes: M3U upstream timeout, malformed episode metadata. The plugin continues with the rest of the batch.

**`localhost`/`127.0.0.1` in Dispatcharr URL.** The plugin refuses to write `.strm` with a localhost URL — your media server can't resolve it. Use the container's reachable IP/hostname.

## Tests

Pure-helper unit tests live in `tests/`. From the repo root:

```bash
python3 -m pytest tests/ -v
```

The tests don't need Django or a running Dispatcharr — they exercise `_clean_title`, `_strip_trailing_year`, `_sanitize_filename`, `_parse_cron`, `_extract_genres`, `_mask_url`, and the path-building helpers in isolation. 45 tests, ~50ms.

## Changelog

**v1.9.0** — NFO titles no longer include the year (Kodi/Jellyfin scrapers prefer just the title). Shared language-prefix regex between `_clean_title` and `_extract_genres` (the AC-130 fix now covers categories too). `_generate_movies` now uses `query.iterator()` so the batch limit is honoured even when most candidates are already-done. Magic numbers promoted to class constants (`MAX_WORKERS`, `LOG_EVERY`, `MAX_FILENAME_LEN`). Class constants grouped at the top of the class. New `[SCHEDULE] Test fire now` action to replay the registered task synchronously. Failed series names now surface in the rescan summary. Cleaner toast on Rescan All. Logged Dispatcharr URL has its host masked. Schedule target validation derived from the manifest field options. New tests/ directory with 45 unit tests.

**v1.8.x** — Section dividers on Settings tab, action labels match the design's renaming map, full-rescan confirm dialog, `[BRACKET]` style headers.

**v1.7.x** — UI clarity: button colors, confirm dialogs in Python class (manifest confirms were ignored by Dispatcharr's runtime), accurate descriptions, `Rescan all` forces refresh-existing.

**v1.6** — Rescan-friendly: per-episode skip, optional M3U re-fetch, `Refresh Existing Series` toggle. Schedule rescans now actually pick up new episodes.

**v1.5** — Submission-ready: `plugin.json` manifest, MIT/attribution, `__init__.py`. Bug fixes: duplicate-year folders, AC-130 over-strip, batch-limit unreachable for series, episode query at DB level, `checkbox` → `boolean`, scan counts unique not relations. Cleanup is now non-destructive (only deletes plugin-created files; user files preserved).

**v1.4** — Cron-driven auto-rescan via `django-celery-beat`. New `Rescan All` action.

**v1.3 and earlier** — see [shedunraid's upstream](https://github.com/shedunraid/VOD2MLIB) for the original v0.x–v1.3 history.

## Architecture (for contributors)

- The plugin is a single `plugin.py` declaring a `Plugin` class with `fields`, `actions`, and `run()` per Dispatcharr's plugin contract.
- `plugin.json` is the manifest the [Dispatcharr/Plugins catalogue](https://github.com/Dispatcharr/Plugins) reads. Dispatcharr's runtime reads action metadata from the Python class — the JSON is for the catalogue and pre-enable preview.
- Schedule registration uses `django-celery-beat`'s `PeriodicTask` + `CrontabSchedule`. The cron-fired task is a module-level `@shared_task` named `vod2mlib.scheduled_rescan` that constructs a fresh `Plugin()` and dispatches.
- Settings are snapshotted into the PeriodicTask's `kwargs` at Apply-time so the cron runs with deterministic config. Re-click Apply to refresh.
