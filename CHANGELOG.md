# Changelog

## v1.13.0 — URL refresh & user-edit preservation

Fix stale `.strm` URLs after changing `Dispatcharr URL`. Previously, once a movie or episode `.strm` was on disk, the plugin would never rewrite it — so editing the URL setting left every existing file pointing at the old address. The only workaround was `[⚠ DANGER] Clean up` followed by regenerate, which also wiped user-added `.nfo` edits.

New `Refresh Existing Movies (URL refresh)` setting (default OFF, mirrors the existing `Refresh Existing Series` toggle) — when ON, `[GENERATE] Movies` rewrites existing `.strm` files with the current Dispatcharr URL while preserving `.nfo` edits (only writes `.nfo` when missing). In refresh mode, `Batch Size` caps total writes (new + refreshed) so large URL-refresh runs can be paced over multiple ticks.

`Refresh Existing Series` now also rewrites existing episode `.strm` URLs (previously it only picked up *new* episodes — existing episodes silently kept the old URL). `tvshow.nfo` is no longer overwritten in refresh mode, preserving user metadata edits. Episode `.nfo` was already preserved.

`[GENERATE] Full rescan` and the cron schedule (`rescan_all`) force both refresh flags ON, so URL changes propagate automatically on the next scheduled tick — no manual intervention or cleanup-then-regenerate dance required.

## v1.12.0

New `Schedule Timezone` setting (IANA name like `Europe/London`, `America/New_York`; default empty = UTC). The cron expression is now interpreted in that timezone, so `0 3 * * *` in `Europe/London` fires at 03:00 local time year-round — DST handled automatically. `[SCHEDULE] Show status` now reports the timezone alongside the cron. New `help_url` manifest field pointing at the README — Dispatcharr's plugin tile renders this as a link next to the author name, so users can find the docs without leaving the UI. Validator (`_validate_timezone`) rejects invalid IANA names at Apply time with a helpful error pointing at the timezone list. 7 new unit tests (113 total).

## v1.11.0

Optional category-nested folder layout. Two new boolean settings (both default OFF): `Nest Movies by Category` and `Nest Series by Category`. When ON, each item's folder is wrapped in a subfolder named by its raw M3U category — useful when your provider organises content by genre. Items without a category land under `Unassigned/`. Items present under multiple categories (e.g. 4K vs HD) get separate folders intentionally. Cleanup actions refactored to walk recursively (`os.walk`) so they handle both flat and nested layouts in one pass — empty Season / series / category folders are removed bottom-up, user-added files (subtitles, posters, extras) are still preserved. **Layout-change warning:** flipping a `Nest by Category` setting after generation does NOT migrate existing folders — the new layout coexists alongside the old. Run `[⚠ DANGER] Clean up Movies` / `Series` followed by `[GENERATE]` to fully switch layouts. 17 new unit tests (106 total).

## v1.10.1

Year-bucket category names like `2026 Movies` / `1990s Series` / `2026 TV Shows` are no longer emitted as fake genres. These come from IPTV providers that organize their VOD catalogue by year rather than by genre — passing them through to media servers actively confuses genre browsing in Plex/Jellyfin/Kodi. Now: when the only category-derived genre would be a year-bucket, no `<genre>` tag is emitted at all. Plex/Jellyfin/CDVR will fetch real genres from TMDB themselves via the `<tmdbid>` we already emit. Real categorical genres (`Action`, `Drama, Crime`, `Action / Adventure`) pass through unchanged. Mixed cases (`Action / 2026 Movies`) keep the real part and drop the bucket. 13 new unit tests (89 total).

## v1.10.0

NFO files now emit external IDs and richer metadata, dramatically improving identification by ChannelsDVR / Jellyfin / Plex / Kodi / Emby. `tvshow.nfo` and `episode.nfo` get `<tmdbid>`, `<imdbid>`, and Kodi-style `<uniqueid type="tmdb"|"imdb">` (movie NFO already had IDs; gets `<uniqueid>` now too). Series and episode NFOs additionally get `<rating>`. Episode NFO gets `<aired>` (from `air_date`) and `<runtime>` (from `duration_secs`). Genre selection now prefers Dispatcharr's DB-stored `Series.genre` / `Movie.genre` (TMDB-grade values like "Sci-Fi & Fantasy") over the M3U-category-derived genre (which often produced unhelpful values like "Australian Tv"). Falls back to the category when the DB field is empty. 22 new unit tests (76 total). Existing folders need a regenerate to pick up the richer NFOs — `[⚠ DANGER] Clean up Movies` / `Series` then `[GENERATE]` will refresh them.

## v1.9.4

Closes a real footgun reported on the Dispatcharr Discord against the legacy v1.3 plugin: a user edited the Dispatcharr URL field but never clicked Save, so every `.strm` file silently shipped the placeholder URL `http://192.168.99.11:9191` and nothing played. Now: the Python class default is empty, the placeholder `http://192.168.99.11:9191` is rejected on action with a clear error, and a fresh installer is forced to set the URL before anything generates. As a separate concession to host-network setups, the localhost reject is downgraded to a warning — a setup with Dispatcharr and the consumer on the same host with shared network namespace can legitimately use `localhost`/`127.0.0.1`. Validation is centralised in `_validate_dispatcharr_url`, with 9 new unit tests (54 total).

## v1.9.3

Replaced the auto-generated V-on-gradient `logo.png` with custom pixel-art artwork (a CRT showing "VOD" with a download arrow into a `.STRM` file). Source kept at `tools/source_logo.png`; `tools/build_logo.py` resizes to 512×512 with NEAREST resampling.

## v1.9.2

Display name changed from `VOD2MLIB` to `VOD to Media Library`. Slug, repo URL, install folder name, and Celery task identifiers all unchanged.

## v1.9.1

Trimmed `[GENERATE] Full rescan` and `[SCHEDULE] Test fire now` descriptions to keep their Run buttons right-aligned.

## v1.9.0

NFO titles no longer include the year (Kodi/Jellyfin scrapers prefer just the title). Shared language-prefix regex between `_clean_title` and `_extract_genres`. `_generate_movies` now uses `query.iterator()` so the batch limit is honoured even when most candidates are already-done. Magic numbers promoted to class constants. New `[SCHEDULE] Test fire now` action. Failed series names surface in the rescan summary. New `tests/` directory with 45 unit tests.

## v1.8.x

Section dividers on Settings tab, action labels match the design's renaming map, full-rescan confirm dialog, `[BRACKET]` style headers.

## v1.7.x

UI clarity: button colors, confirm dialogs in Python class, accurate descriptions, `Rescan all` forces refresh-existing.

## v1.6

Rescan-friendly: per-episode skip, optional M3U re-fetch, `Refresh Existing Series` toggle. Schedule rescans now actually pick up new episodes.

## v1.5

Submission-ready: `plugin.json` manifest, MIT/attribution, `__init__.py`. Bug fixes: duplicate-year folders, AC-130 over-strip, batch-limit unreachable for series, episode query at DB level, `checkbox` → `boolean`, scan counts unique not relations. Cleanup is now non-destructive.

## v1.4

Cron-driven auto-rescan via `django-celery-beat`. New `Rescan All` action.

## v1.3 and earlier

See [shedunraid's upstream](https://github.com/shedunraid/VOD2MLIB) for the original v0.x–v1.3 history.
