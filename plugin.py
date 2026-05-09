"""
VOD2MLIB — VOD .strm Generator Plugin for Dispatcharr
v1.8.1 — full-rescan confirm dialog + tighter description

MIT License
Copyright (c) 2025-2026 shedunraid (original author)
Copyright (c) 2026 R3XCHRIS (downstream maintainer, fork)
Upstream:   https://github.com/shedunraid/VOD2MLIB
This fork:  https://github.com/R3XCHRIS/VOD2MLIB
"""
import os
import re
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed


class Plugin:
    """Generate .strm files for VOD movies from Dispatcharr."""
    
    name = "VOD2MLIB"
    version = "1.8.1"
    description = (
        "Convert Dispatcharr VODs into media-server-friendly .strm files. "
        "Map a host folder to /VODS in your Dispatcharr container, then click "
        "'Scan for VODs' to see totals and 'Generate Movie/Series .strm Files' "
        "to process them in batches. Series episodes are auto-fetched per series "
        "with 3 parallel workers. Use 'Apply Schedule' to enable a cron-driven "
        "auto-rescan. If you hit a UI glitch, hard-refresh the browser (Cmd/Ctrl+Shift+R)."
    )
    
    fields = [
        {
            "id": "_about",
            "label": "About",
            "type": "info",
            "description": "Workflow:\n  1. Configure paths below.\n  2. Actions → Scan → see catalogue totals.\n  3. Actions → Generate Movies / Generate Series (start with Batch Size 10).\n  4. (Optional) Turn ON Refresh Existing Series, set cron, click Apply Schedule for nightly auto-rescan.\n\nDocs: https://github.com/R3XCHRIS/VOD2MLIB",
        },
        {
            "id": "_section_paths",
            "label": "── Paths & host ──",
            "type": "info",
            "description": "Where to write .strm files and how media servers reach Dispatcharr.",
        },
        {
            "id": "root_folder",
            "label": "Root Folder for Movies",
            "type": "string",
            "default": "/VODS/Movies",
            "help_text": "Path inside the Dispatcharr container where movie folders will be created."
        },
        {
            "id": "series_root_folder",
            "label": "Root Folder for Series",
            "type": "string",
            "default": "/VODS/Series",
            "help_text": "Path inside the Dispatcharr container where series folders will be created."
        },
        {
            "id": "dispatcharr_url",
            "label": "Dispatcharr URL (IMPORTANT!)",
            "type": "string",
            "default": "http://192.168.99.11:9191",
            "help_text": "⚠️ MUST be your actual IP address (not localhost)! This URL goes into .strm files and must be accessible from your media server."
        },
        {
            "id": "_section_movies",
            "label": "── Movies ──",
            "type": "info",
            "description": "Settings for the Generate Movies action.",
        },
        {
            "id": "batch_size",
            "label": "Batch Size (Movies)",
            "type": "select",
            "default": "250",
            "options": [
                {"value": "10", "label": "10 movies"},
                {"value": "100", "label": "100 movies"},
                {"value": "200", "label": "200 movies"},
                {"value": "500", "label": "500 movies"},
                {"value": "1000", "label": "1000 movies"},
                {"value": "all", "label": "All movies"}
            ],
            "help_text": "Number of movies to process in this run"
        },
        {
            "id": "generate_nfo",
            "label": "Generate Movie NFO Files",
            "type": "boolean",
            "default": True,
            "help_text": "Create .nfo metadata files for movies"
        },
        {
            "id": "_section_series",
            "label": "── Series ──",
            "type": "info",
            "description": "Settings for the Generate Series action.",
        },
        {
            "id": "series_batch_size",
            "label": "Batch Size (Series)",
            "type": "select",
            "default": "10",
            "options": [
                {"value": "1", "label": "1 series (testing)"},
                {"value": "5", "label": "5 series"},
                {"value": "10", "label": "10 series"},
                {"value": "25", "label": "25 series"},
                {"value": "all", "label": "All series (slow!)"}
            ],
            "help_text": "Series to process (episodes auto-fetched for each)"
        },
        {
            "id": "generate_series_nfo",
            "label": "Generate Series NFO Files",
            "type": "boolean",
            "default": True,
            "help_text": "Create .nfo metadata files for series and episodes"
        },
        {
            "id": "refresh_existing",
            "label": "Refresh Existing Series (rescan-friendly)",
            "type": "boolean",
            "default": False,
            "help_text": "Re-evaluate series that already have folders, picking up new episodes added upstream. Turn ON for cron rescans."
        },
        {
            "id": "_section_schedule",
            "label": "── Auto-rescan schedule ──",
            "type": "info",
            "description": "Configure the cron job. Click Apply in the Actions tab to register or update.",
        },
        {
            "id": "schedule_cron",
            "label": "Auto-Rescan Schedule (cron)",
            "type": "string",
            "default": "0 3 * * *",
            "help_text": "Standard 5-field cron: 'minute hour day-of-month month day-of-week'. Default '0 3 * * *' = every day at 03:00. Used by 'Apply Schedule'."
        },
        {
            "id": "schedule_target",
            "label": "Scheduled Action",
            "type": "select",
            "default": "rescan_all",
            "options": [
                {"value": "scan_all_vods", "label": "Scan only (totals)"},
                {"value": "generate_movies", "label": "Movies only"},
                {"value": "generate_series", "label": "Series only"},
                {"value": "rescan_all", "label": "Full rescan (movies + series)"}
            ],
            "help_text": "Which action the scheduler should run on each tick."
        }
    ]

    SCHEDULE_TASK_NAME = "vod2mlib.auto_rescan"
    
    actions = [
        {
            "id": "scan_all_vods",
            "label": "[LIBRARY] Catalogue snapshot",
            "description": "Count unique Movies and Series in the Dispatcharr database. Read-only.",
            "button_label": "Scan",
            "button_variant": "outline",
            "button_color": "blue",
        },
        {
            "id": "generate_movies",
            "label": "[GENERATE] Movies",
            "description": "Process movies per Batch Size. Existing .strm files are skipped.",
            "button_label": "Generate",
            "button_variant": "filled",
            "button_color": "green",
        },
        {
            "id": "generate_series",
            "label": "[GENERATE] Series",
            "description": "Create episode .strm files. See 'Refresh Existing Series' setting.",
            "button_label": "Generate",
            "button_variant": "filled",
            "button_color": "green",
        },
        {
            "id": "rescan_all",
            "label": "[GENERATE] Full rescan",
            "description": "Rescan then force regenerate Movies + Series. What cron fires.",
            "button_label": "Rescan all",
            "button_variant": "filled",
            "button_color": "teal",
            "confirm": {
                "required": True,
                "title": "Run full rescan now?",
                "message": "Full rescan walks every Movie and every Series, re-fetching episode lists from the M3U source and writing any missing files. On large catalogues this can take many minutes. The cron schedule already runs this action nightly — only click here for an immediate refresh.",
            },
        },
        {
            "id": "schedule_status",
            "label": "[SCHEDULE] Show status",
            "description": "Show registered cron, last run, and total runs.",
            "button_label": "Status",
            "button_variant": "outline",
            "button_color": "blue",
        },
        {
            "id": "apply_schedule",
            "label": "[SCHEDULE] Apply / Update",
            "description": "Register or update the cron task. Re-click after changing any setting.",
            "button_label": "Apply",
            "button_variant": "outline",
            "button_color": "blue",
        },
        {
            "id": "remove_schedule",
            "label": "[SCHEDULE] Unschedule",
            "description": "Remove the periodic auto-rescan task.",
            "button_label": "Remove",
            "button_variant": "outline",
            "button_color": "orange",
            "confirm": {
                "required": True,
                "title": "Remove auto-rescan schedule?",
                "message": "This unregisters the periodic task. You can re-create it any time with Apply.",
            },
        },
        {
            "id": "cleanup_movies",
            "label": "[⚠ DANGER] Clean up Movies",
            "description": "Delete plugin .strm/.nfo from Movies root. User files preserved.",
            "button_label": "Clean up",
            "button_variant": "filled",
            "button_color": "red",
            "confirm": {
                "required": True,
                "title": "Delete generated movie files?",
                "message": "This deletes every .strm and .nfo file this plugin created under your Movies root. User-added files (subtitles, posters, custom .nfo) in those folders are preserved. Continue?",
            },
        },
        {
            "id": "cleanup_series",
            "label": "[⚠ DANGER] Clean up Series",
            "description": "Delete plugin .strm/.nfo from Series root. User files preserved.",
            "button_label": "Clean up",
            "button_variant": "filled",
            "button_color": "red",
            "confirm": {
                "required": True,
                "title": "Delete generated series files?",
                "message": "This deletes every .strm and .nfo file this plugin created under your Series root. User-added files in those folders are preserved. Continue?",
            },
        },
    ]
    
    def run(self, action: str, params: dict, context: dict):
        """Execute plugin action."""
        logger = context.get("logger")
        settings = context.get("settings", {})
        
        logger.info("=" * 60)
        logger.info("VOD .strm Generator v%s", self.version)
        logger.info("Action: %s", action)
        logger.info("=" * 60)
        
        if action == "scan_all_vods":
            return self._scan_all_vods(settings, logger)
        elif action == "generate_movies":
            return self._generate_movies(settings, logger)
        elif action == "generate_series":
            return self._generate_series(settings, logger)
        elif action == "cleanup_movies":
            return self._cleanup_movies(settings, logger)
        elif action == "cleanup_series":
            return self._cleanup_series(settings, logger)
        elif action == "rescan_all":
            return self._rescan_all(settings, logger)
        elif action == "apply_schedule":
            return self._apply_schedule(settings, logger)
        elif action == "remove_schedule":
            return self._remove_schedule(settings, logger)
        elif action == "schedule_status":
            return self._schedule_status(settings, logger)

        return {"status": "error", "message": f"Unknown action: {action}"}
    
    def _scan_all_vods(self, settings: Dict[str, Any], logger):
        """Scan and show total movies and series available."""
        logger.info("Scanning VODs in Dispatcharr...")
        logger.info("")
        
        try:
            from apps.vod.models import Movie, Series, M3UMovieRelation, M3USeriesRelation
        except ImportError as e:
            logger.error("Failed to import models: %s", e)
            return {"status": "error", "message": f"Import error: {e}"}

        try:
            movie_count = Movie.objects.count()
            series_count = Series.objects.count()
            movie_relations = M3UMovieRelation.objects.count()
            series_relations = M3USeriesRelation.objects.count()

            logger.info("=" * 60)
            logger.info("MOVIES: %d unique  (%d M3U relations)", movie_count, movie_relations)
            logger.info("SERIES: %d unique  (%d M3U relations)", series_count, series_relations)
            logger.info("=" * 60)
            logger.info("")
            logger.info("Use 'Generate Movie .strm Files' for movies")
            logger.info("Use 'Generate Series .strm Files' for series")
            
            return {
                "status": "ok",
                "message": f"Found {movie_count} movies and {series_count} series",
                "movies": movie_count,
                "series": series_count
            }
        except Exception as e:
            logger.error("Scan failed: %s", e)
            return {"status": "error", "message": f"Scan error: {e}"}
    
    def _generate_movies(self, settings: Dict[str, Any], logger):
        """Generate movie .strm files according to batch size."""
        root_folder = settings.get("root_folder", "/VODS/Movies")
        dispatcharr_url = settings.get("dispatcharr_url", "http://192.168.99.11:9191").rstrip("/")
        batch_size = settings.get("batch_size") or "250"
        generate_nfo = settings.get("generate_nfo", True)
        
        # Validate URL is not localhost
        if "localhost" in dispatcharr_url.lower() or "127.0.0.1" in dispatcharr_url:
            logger.error("=" * 60)
            logger.error("CONFIGURATION ERROR!")
            logger.error("Dispatcharr URL is set to localhost/127.0.0.1")
            logger.error("This will NOT work in media servers!")
            logger.error("")
            logger.error("Current setting: %s", dispatcharr_url)
            logger.error("Change to: http://192.168.99.11:9191 (or your actual IP)")
            logger.error("=" * 60)
            return {
                "status": "error",
                "message": "Dispatcharr URL must be an actual IP address, not localhost! Update settings and try again."
            }
        
        logger.info("")
        logger.info("Configuration:")
        logger.info("  Root Folder: %s", root_folder)
        logger.info("  Dispatcharr URL: %s", dispatcharr_url)
        logger.info("  Batch Size: %s", batch_size)
        logger.info("  Generate NFO: %s", "Yes" if generate_nfo else "No")
        logger.info("")
        
        # Import Django models
        try:
            from apps.vod.models import Movie, M3UMovieRelation
            from apps.m3u.models import M3UAccount
        except ImportError as e:
            logger.error("Failed to import models: %s", e)
            return {"status": "error", "message": f"Import error: {e}"}
        
        # Get total count first
        logger.info("Scanning database...")
        try:
            total_count = M3UMovieRelation.objects.count()
            logger.info("Total VODs in database: %d", total_count)
            logger.info("")
        except Exception as e:
            logger.error("Failed to count VODs: %s", e)
            return {"status": "error", "message": f"Database error: {e}"}
        
        # Get movies based on batch size
        logger.info("Querying movies for this batch...")
        try:
            # Get movies with their M3U relations
            query = M3UMovieRelation.objects.select_related('movie', 'm3u_account', 'category')
            filtered_count = query.count()
            
            if batch_size == "all":
                movie_relations = list(query)
                logger.info("Processing ALL %d movies", filtered_count)
                target_batch = filtered_count
            else:
                target_batch = int(batch_size)
                # Fetch 3x batch size to account for skips
                fetch_size = min(target_batch * 3, filtered_count)
                movie_relations = list(query[:fetch_size])
                logger.info("Fetching %d movies to process batch of %d", fetch_size, target_batch)
            
            if not movie_relations:
                logger.warning("No movies found in database!")
                return {
                    "status": "ok",
                    "message": "No movies found to process",
                    "processed": 0
                }
            
            logger.info("Found %d movies to process", len(movie_relations))
            logger.info("")
            
        except Exception as e:
            logger.error("Database query failed: %s", e)
            return {"status": "error", "message": f"Database error: {e}"}
        
        # Ensure root folder exists
        try:
            os.makedirs(root_folder, exist_ok=True)
            logger.info("Root folder ready: %s", root_folder)
            logger.info("")
        except Exception as e:
            logger.error("Failed to create root folder: %s", e)
            return {"status": "error", "message": f"Folder creation error: {e}"}
        
        # Process movies until we've created the target batch
        created_strm = 0
        created_nfo = 0
        skipped = 0
        errors = 0
        processed = 0
        
        logger.info("Processing movies:")
        logger.info("-" * 60)
        
        for idx, relation in enumerate(movie_relations, 1):
            processed += 1
            movie = relation.movie
            stream_id = relation.stream_id
            
            raw_name = movie.name or f"Unknown Movie {movie.id}"
            movie_name = self._clean_title(raw_name)
            movie_name, title_year = self._strip_trailing_year(movie_name)
            year = movie.year or title_year

            safe_name = self._sanitize_filename(movie_name)
            if year:
                folder_name = f"{safe_name} ({year})"
                strm_filename = f"{safe_name} ({year}).strm"
            else:
                folder_name = safe_name
                strm_filename = f"{safe_name}.strm"
            
            # Create movie folder and paths
            movie_folder = os.path.join(root_folder, folder_name)
            strm_path = os.path.join(movie_folder, strm_filename)
            
            # Check if already processed
            if os.path.exists(strm_path):
                skipped += 1
                if idx % 50 == 1 or idx <= 10:
                    logger.info("")
                    logger.info("[%d/%d] %s - Already exists, skipping", idx, len(movie_relations), movie_name)
                continue
            
            # Stop if we've created enough for this batch (unless processing all)
            if batch_size != "all" and created_strm >= target_batch:
                logger.info("")
                logger.info("Batch complete! Created %d movies.", target_batch)
                break
            
            # Build proxy URL
            proxy_url = f"{dispatcharr_url}/proxy/vod/movie/{movie.uuid}?stream_id={stream_id}"
            
            # Log every 50th movie to avoid spam
            if idx % 50 == 1 or idx <= 10:
                logger.info("")
                logger.info("[%d/%d] %s", idx, len(movie_relations), movie_name)
                logger.info("  Year: %s", year if year else "Unknown")
                logger.info("  Folder: %s", folder_name)
                logger.info("  UUID: %s", movie.uuid)
                logger.info("  Stream ID: %s", stream_id)
            
            try:
                # Create folder
                os.makedirs(movie_folder, exist_ok=True)
                
                # Write .strm file
                with open(strm_path, 'w', encoding='utf-8') as f:
                    f.write(proxy_url)
                created_strm += 1
                
                # Write .nfo file if enabled
                if generate_nfo:
                    nfo_filename = strm_filename.replace('.strm', '.nfo')
                    nfo_path = os.path.join(movie_folder, nfo_filename)
                    
                    category_name = relation.category.name if relation.category else ""
                    nfo_content = self._generate_nfo(movie, category_name)
                    
                    with open(nfo_path, 'w', encoding='utf-8') as f:
                        f.write(nfo_content)
                    created_nfo += 1
                
                if idx % 50 == 1 or idx <= 10:
                    logger.info("  ✓ Created: .strm%s", " + .nfo" if generate_nfo else "")
                
            except Exception as e:
                logger.error("  ✗ Error: %s", e)
                errors += 1
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("SUMMARY:")
        logger.info("  Total in DB:    %d", total_count)
        logger.info("  Examined:       %d", processed)
        logger.info("  .strm created:  %d", created_strm)
        if generate_nfo:
            logger.info("  .nfo created:   %d", created_nfo)
        logger.info("  Skipped:        %d", skipped)
        logger.info("  Errors:         %d", errors)
        logger.info("=" * 60)
        logger.info("")
        logger.info("Complete! Check your media server to verify playback.")
        
        summary_msg = f"Created {created_strm} .strm files"
        if generate_nfo:
            summary_msg += f" + {created_nfo} .nfo files"
        
        return {
            "status": "ok",
            "message": summary_msg,
            "total_in_db": total_count,
            "processed": processed,
            "created_strm": created_strm,
            "created_nfo": created_nfo if generate_nfo else 0,
            "skipped": skipped,
            "errors": errors
        }
    
    def _series_target_folder(self, series, series_root: str):
        """Compute the target folder for a series. Returns (folder_path, clean_name, year)."""
        raw_name = series.name or f"Unknown Series {series.id}"
        clean_name = self._clean_title(raw_name)
        clean_name, title_year = self._strip_trailing_year(clean_name)
        year = series.year or title_year
        safe = self._sanitize_filename(clean_name)
        folder_name = f"{safe} ({year})" if year else safe
        return os.path.join(series_root, folder_name), clean_name, year

    def _series_already_processed(self, series_folder: str) -> bool:
        """A series is considered processed if its folder contains any 'Season ...' subdir."""
        if not os.path.isdir(series_folder):
            return False
        try:
            return any(
                item.startswith("Season") and os.path.isdir(os.path.join(series_folder, item))
                for item in os.listdir(series_folder)
            )
        except OSError:
            return False

    def _generate_series(self, settings: Dict[str, Any], logger):
        """Generate series .strm files with episodes using parallel processing."""
        series_root = settings.get("series_root_folder", "/VODS/Series")
        dispatcharr_url = settings.get("dispatcharr_url", "http://192.168.99.11:9191").rstrip("/")
        batch_size = settings.get("series_batch_size") or "10"
        generate_nfo = settings.get("generate_series_nfo", True)
        refresh_existing = bool(settings.get("refresh_existing", False))

        if "localhost" in dispatcharr_url.lower() or "127.0.0.1" in dispatcharr_url:
            return {"status": "error", "message": "Dispatcharr URL must be an actual IP address!"}

        logger.info("")
        logger.info("Configuration:")
        logger.info("  Series Root: %s", series_root)
        logger.info("  Dispatcharr URL: %s", dispatcharr_url)
        logger.info("  Batch Size: %s", batch_size)
        logger.info("  Generate NFO: %s", "Yes" if generate_nfo else "No")
        logger.info("  Refresh Existing: %s", "Yes" if refresh_existing else "No")
        logger.info("  Threading: ENABLED (3 workers)")
        logger.info("")

        try:
            from apps.vod.models import M3USeriesRelation
        except ImportError as e:
            logger.error("Failed to import models: %s", e)
            return {"status": "error", "message": f"Import error: {e}"}

        try:
            query = M3USeriesRelation.objects.select_related('series', 'm3u_account', 'category')
            total_count = query.count()

            if batch_size == "all":
                target_batch = total_count
                logger.info("Mode: process ALL %d series", total_count)
            else:
                target_batch = int(batch_size)
                logger.info("Target batch size: %d (of %d total)", target_batch, total_count)

            if total_count == 0:
                return {"status": "ok", "message": "No series found"}
        except Exception as e:
            logger.error("Query failed: %s", e)
            return {"status": "error", "message": f"Database error: {e}"}

        try:
            os.makedirs(series_root, exist_ok=True)
        except OSError as e:
            return {"status": "error", "message": f"Folder creation error: {e}"}

        if refresh_existing:
            logger.info("Refresh-existing mode: scanning all series for new episodes...")
        else:
            logger.info("Filtering already-processed series...")
        to_process = []
        scanned = 0
        for series_rel in query.iterator():
            scanned += 1
            if not refresh_existing:
                folder, _, _ = self._series_target_folder(series_rel.series, series_root)
                if self._series_already_processed(folder):
                    continue
            to_process.append(series_rel)
            if batch_size != "all" and len(to_process) >= target_batch:
                break

        skipped_pre = scanned - len(to_process)
        if refresh_existing:
            logger.info("Scanned %d series; %d to evaluate this run", scanned, len(to_process))
        else:
            logger.info("Scanned %d series; %d already processed (skipped); %d to process this run", scanned, skipped_pre, len(to_process))
        logger.info("")

        if not to_process:
            logger.info("Nothing to process.")
            return {
                "status": "ok",
                "message": f"Nothing to process; {skipped_pre} series already done.",
                "series_processed": 0,
                "episodes_created": 0,
                "nfo_created": 0,
                "errors": 0,
            }

        created_strm = 0
        created_nfo = 0
        errors = 0
        series_created = 0
        series_uptodate = 0

        logger.info("Processing %d series with 3 parallel workers:", len(to_process))
        logger.info("-" * 60)

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(
                    self._process_single_series,
                    series_rel,
                    dispatcharr_url,
                    generate_nfo,
                    series_root,
                    logger,
                    refresh_existing,
                ): series_rel
                for series_rel in to_process
            }

            for idx, future in enumerate(as_completed(futures), 1):
                try:
                    result = future.result()
                except Exception as e:
                    logger.error("[%d/%d] Worker raised: %s", idx, len(futures), e)
                    errors += 1
                    continue

                if result.get("uptodate"):
                    series_uptodate += 1
                elif result.get("created"):
                    series_created += 1
                    created_strm += result["episodes"]
                    created_nfo += result["nfo_files"]
                if "error" in result:
                    errors += 1
                logger.info("[%d/%d] %s", idx, len(futures), result["message"])
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("SUMMARY:")
        logger.info("  Series with new content: %d", series_created)
        logger.info("  Series up-to-date:       %d", series_uptodate)
        logger.info("  New episode .strm files: %d", created_strm)
        if generate_nfo:
            logger.info("  New NFO files:           %d", created_nfo)
        logger.info("  Errors:                  %d", errors)
        logger.info("=" * 60)

        if series_created == 0 and series_uptodate > 0:
            summary_msg = f"All {series_uptodate} evaluated series already up-to-date — no new episodes."
        else:
            summary_msg = f"Wrote {created_strm} new episodes across {series_created} series"
            if series_uptodate:
                summary_msg += f" ({series_uptodate} already up-to-date)"
            if generate_nfo and created_nfo:
                summary_msg += f" + {created_nfo} NFO"

        return {
            "status": "ok",
            "message": summary_msg,
            "series_processed": series_created,
            "series_uptodate": series_uptodate,
            "episodes_created": created_strm,
            "nfo_created": created_nfo if generate_nfo else 0,
            "errors": errors,
        }
    
    def _process_single_series(self, series_rel, dispatcharr_url, generate_nfo, series_root, logger, refresh_existing=False):
        """Process a single series. Idempotent: writes only missing episode files.

        With refresh_existing=False, callers should pre-filter already-done
        series for performance. With refresh_existing=True, every series is
        re-evaluated and the M3U source is re-fetched so newly-aired episodes
        are picked up.
        """
        from apps.vod.models import M3UEpisodeRelation
        from apps.vod.tasks import refresh_series_episodes

        series = series_rel.series
        series_folder, series_name, _year = self._series_target_folder(series, series_root)

        try:
            custom_props = series_rel.custom_properties or {}
            should_refetch = refresh_existing or not custom_props.get('episodes_fetched', False)
            if should_refetch:
                try:
                    refresh_series_episodes(
                        account=series_rel.m3u_account,
                        series=series_rel.series,
                        external_series_id=series_rel.external_series_id,
                    )
                except Exception as fetch_err:
                    logger.warning("refresh_series_episodes failed for %s: %s", series_name, fetch_err)

            episodes = list(
                M3UEpisodeRelation.objects.filter(
                    m3u_account=series_rel.m3u_account,
                    episode__series=series,
                )
                .select_related('episode')
                .order_by('episode__season_number', 'episode__episode_number')
            )
            episode_count = len(episodes)
            
            if episode_count == 0:
                return {
                    "created": False,
                    "uptodate": False,
                    "series_name": series_name,
                    "episodes": 0,
                    "nfo_files": 0,
                    "message": f"{series_name} - No episodes found",
                }

            os.makedirs(series_folder, exist_ok=True)

            new_episodes = 0
            new_nfo = 0

            if generate_nfo:
                tvshow_nfo_path = os.path.join(series_folder, "tvshow.nfo")
                if refresh_existing or not os.path.isfile(tvshow_nfo_path):
                    category_name = series_rel.category.name if series_rel.category else ""
                    tvshow_content = self._generate_tvshow_nfo(series, category_name)
                    with open(tvshow_nfo_path, 'w', encoding='utf-8') as f:
                        f.write(tvshow_content)
                    new_nfo += 1

            for episode_rel in episodes:
                episode = episode_rel.episode
                season_num = episode.season_number or 0
                episode_num = episode.episode_number or 0

                season_folder_name = f"Season {season_num:02d}"
                season_folder = os.path.join(series_folder, season_folder_name)

                episode_title = episode.name or ""
                if episode_title:
                    clean_title = self._clean_title(episode_title)
                    filename = f"{series_name} - S{season_num:02d}E{episode_num:02d} - {clean_title}"
                else:
                    filename = f"{series_name} - S{season_num:02d}E{episode_num:02d}"
                filename = self._sanitize_filename(filename)

                strm_path = os.path.join(season_folder, f"{filename}.strm")
                if os.path.isfile(strm_path):
                    continue

                os.makedirs(season_folder, exist_ok=True)
                proxy_url = f"{dispatcharr_url}/proxy/vod/episode/{episode.uuid}?stream_id={episode_rel.stream_id}"
                with open(strm_path, 'w', encoding='utf-8') as f:
                    f.write(proxy_url)
                new_episodes += 1

                if generate_nfo:
                    nfo_path = os.path.join(season_folder, f"{filename}.nfo")
                    if not os.path.isfile(nfo_path):
                        with open(nfo_path, 'w', encoding='utf-8') as f:
                            f.write(self._generate_episode_nfo(episode))
                        new_nfo += 1

            if new_episodes == 0:
                return {
                    "created": False,
                    "uptodate": True,
                    "series_name": series_name,
                    "episodes": 0,
                    "nfo_files": new_nfo,
                    "message": f"{series_name} - up-to-date ({episode_count} episodes on disk)",
                }

            return {
                "created": True,
                "uptodate": False,
                "series_name": series_name,
                "episodes": new_episodes,
                "nfo_files": new_nfo,
                "message": f"{series_name} - +{new_episodes} new episode{'s' if new_episodes != 1 else ''}",
            }

        except Exception as e:
            return {
                "created": False,
                "uptodate": False,
                "series_name": series_name,
                "episodes": 0,
                "nfo_files": 0,
                "error": str(e),
                "message": f"{series_name} - ✗ Error: {e}",
            }
    
    _PLUGIN_FILE_SUFFIXES = ('.strm', '.nfo')

    def _delete_plugin_files_in_dir(self, dir_path: str, logger):
        """Delete only .strm and .nfo files in dir_path. Returns (strm_deleted, nfo_deleted, errors)."""
        strm = nfo = errors = 0
        try:
            entries = os.listdir(dir_path)
        except OSError as e:
            logger.error("Cannot list %s: %s", dir_path, e)
            return 0, 0, 1

        for name in entries:
            if not name.endswith(self._PLUGIN_FILE_SUFFIXES):
                continue
            path = os.path.join(dir_path, name)
            if not os.path.isfile(path):
                continue
            try:
                os.remove(path)
                if name.endswith('.strm'):
                    strm += 1
                else:
                    nfo += 1
            except OSError as e:
                logger.error("Failed to delete %s: %s", path, e)
                errors += 1
        return strm, nfo, errors

    def _try_rmdir(self, path: str) -> bool:
        """Remove path if it's an empty directory. Returns True if removed."""
        try:
            os.rmdir(path)
            return True
        except OSError:
            return False

    def _cleanup_movies(self, settings: Dict[str, Any], logger):
        """Delete plugin-generated .strm and .nfo files under the movies root.

        Folders that still contain user-added files (subtitles, posters, etc.)
        are preserved; folders that become empty are removed.
        """
        root_folder = settings.get("root_folder", "/VODS/Movies")

        logger.info("=" * 60)
        logger.info("VOD2MLIB v%s — cleanup_movies", self.version)
        logger.info("Root: %s", root_folder)
        logger.info("=" * 60)
        logger.info("")

        if not os.path.exists(root_folder):
            logger.info("Root folder doesn't exist. Nothing to clean up.")
            return {"status": "ok", "message": "Root folder doesn't exist", "deleted_folders": 0, "deleted_strm": 0, "deleted_nfo": 0}

        try:
            entries = sorted(os.listdir(root_folder))
        except OSError as e:
            return {"status": "error", "message": f"Cannot list {root_folder}: {e}"}

        deleted_folders = deleted_strm = deleted_nfo = preserved = errors = 0
        scanned = 0
        for item in entries:
            item_path = os.path.join(root_folder, item)
            if not os.path.isdir(item_path):
                continue
            scanned += 1
            strm, nfo, err = self._delete_plugin_files_in_dir(item_path, logger)
            deleted_strm += strm
            deleted_nfo += nfo
            errors += err
            if (strm + nfo) > 0:
                if self._try_rmdir(item_path):
                    deleted_folders += 1
                else:
                    preserved += 1
                    logger.info("Preserved (user files remain): %s", item)

        logger.info("")
        logger.info("=" * 60)
        logger.info("CLEANUP SUMMARY")
        logger.info("  Folders scanned:   %d", scanned)
        logger.info("  Folders removed:   %d", deleted_folders)
        logger.info("  Folders preserved: %d  (user-added files inside)", preserved)
        logger.info("  .strm deleted:     %d", deleted_strm)
        logger.info("  .nfo deleted:      %d", deleted_nfo)
        logger.info("  Errors:            %d", errors)
        logger.info("=" * 60)

        msg = f"Deleted {deleted_strm} .strm + {deleted_nfo} .nfo, removed {deleted_folders} folders"
        if preserved:
            msg += f", preserved {preserved} (user files)"
        return {
            "status": "ok",
            "message": msg,
            "deleted_folders": deleted_folders,
            "deleted_strm": deleted_strm,
            "deleted_nfo": deleted_nfo,
            "preserved_folders": preserved,
            "errors": errors,
        }

    def _cleanup_series(self, settings: Dict[str, Any], logger):
        """Delete plugin-generated .strm and .nfo files under the series root.

        Walks Season/* subfolders. Season folders that become empty are removed,
        then series folders that become empty (no Season subdirs and no other
        files) are removed too. Folders with user-added files are preserved.
        """
        series_root = settings.get("series_root_folder", "/VODS/Series")

        logger.info("=" * 60)
        logger.info("VOD2MLIB v%s — cleanup_series", self.version)
        logger.info("Root: %s", series_root)
        logger.info("=" * 60)
        logger.info("")

        if not os.path.exists(series_root):
            logger.info("Series root doesn't exist. Nothing to clean up.")
            return {"status": "ok", "message": "Series root doesn't exist", "deleted": 0}

        try:
            entries = sorted(os.listdir(series_root))
        except OSError as e:
            return {"status": "error", "message": f"Cannot list {series_root}: {e}"}

        deleted_strm = deleted_nfo = errors = 0
        seasons_removed = series_removed = preserved = 0

        for series_name in entries:
            series_path = os.path.join(series_root, series_name)
            if not os.path.isdir(series_path):
                continue

            try:
                sub_entries = os.listdir(series_path)
            except OSError as e:
                logger.error("Cannot list %s: %s", series_path, e)
                errors += 1
                continue

            for sub in sub_entries:
                sub_path = os.path.join(series_path, sub)
                if os.path.isdir(sub_path) and sub.startswith("Season"):
                    strm, nfo, err = self._delete_plugin_files_in_dir(sub_path, logger)
                    deleted_strm += strm
                    deleted_nfo += nfo
                    errors += err
                    if self._try_rmdir(sub_path):
                        seasons_removed += 1

            tvshow_path = os.path.join(series_path, "tvshow.nfo")
            if os.path.isfile(tvshow_path):
                try:
                    os.remove(tvshow_path)
                    deleted_nfo += 1
                except OSError as e:
                    logger.error("Failed to delete %s: %s", tvshow_path, e)
                    errors += 1

            if self._try_rmdir(series_path):
                series_removed += 1
            else:
                preserved += 1

        logger.info("")
        logger.info("=" * 60)
        logger.info("CLEANUP SUMMARY")
        logger.info("  Series removed:      %d", series_removed)
        logger.info("  Series preserved:    %d  (user-added files inside)", preserved)
        logger.info("  Season dirs removed: %d", seasons_removed)
        logger.info("  .strm deleted:       %d", deleted_strm)
        logger.info("  .nfo deleted:        %d", deleted_nfo)
        logger.info("  Errors:              %d", errors)
        logger.info("=" * 60)

        msg = (
            f"Deleted {deleted_strm} .strm + {deleted_nfo} .nfo, "
            f"removed {series_removed} series ({seasons_removed} season dirs)"
        )
        if preserved:
            msg += f", preserved {preserved}"
        return {
            "status": "ok",
            "message": msg,
            "series_removed": series_removed,
            "seasons_removed": seasons_removed,
            "preserved_series": preserved,
            "deleted_strm": deleted_strm,
            "deleted_nfo": deleted_nfo,
            "errors": errors,
        }
    
    _LANGUAGE_PREFIX_RE = re.compile(r'^[A-Z]{2,3}\s+-\s*')
    _TRAILING_YEAR_RE = re.compile(r'\s*\((\d{4})\)\s*$')

    def _clean_title(self, title: str) -> str:
        """Remove language prefixes like 'EN - ', 'FR - ' from titles.

        Requires whitespace before the dash so real titles like 'AC-130' or
        'MI-5' are not stripped.
        """
        if not title:
            return title
        return self._LANGUAGE_PREFIX_RE.sub('', title).strip()

    def _strip_trailing_year(self, title: str):
        """Strip a trailing ' (YYYY)' from a title.

        Returns (cleaned_title, year) where year is an int if found, else None.
        Used to avoid double-year folder names when the source title already
        contains the year.
        """
        if not title:
            return title or "", None
        match = self._TRAILING_YEAR_RE.search(title)
        if not match:
            return title, None
        return self._TRAILING_YEAR_RE.sub('', title).rstrip(), int(match.group(1))
    
    def _extract_genres(self, category_name: str) -> list:
        """Extract genre names from category name."""
        if not category_name:
            return []
        
        # Remove common prefixes (EN -, FR -, US -, etc.)
        genre_text = re.sub(r'^[A-Z]{2,3}\s*-\s*', '', category_name)
        
        # Remove (movie) or (series) suffix
        genre_text = re.sub(r'\s*\((movie|series)\)\s*$', '', genre_text, flags=re.IGNORECASE)
        
        # Split on common separators
        genres = re.split(r'[/&,]', genre_text)
        
        # Clean up each genre
        cleaned_genres = []
        for genre in genres:
            genre = genre.strip()
            # Capitalize first letter of each word
            genre = ' '.join(word.capitalize() for word in genre.split())
            if genre:
                cleaned_genres.append(genre)
        
        return cleaned_genres or ["Unknown"]
    
    def _generate_tvshow_nfo(self, series, category_name: str) -> str:
        """Generate tvshow.nfo XML content for a series."""
        # Extract basic info (clean language prefix)
        raw_title = series.name or "Unknown"
        title = self._clean_title(raw_title)
        year = series.year or ""
        plot = series.description or ""
        
        # Extract genres from category
        genres = self._extract_genres(category_name)
        
        # Build XML
        xml_lines = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>']
        xml_lines.append('<tvshow>')
        xml_lines.append(f'    <title>{self._xml_escape(title)}</title>')
        
        if year:
            xml_lines.append(f'    <year>{year}</year>')
        
        for genre in genres:
            xml_lines.append(f'    <genre>{self._xml_escape(genre)}</genre>')
        
        if plot:
            xml_lines.append(f'    <plot>{self._xml_escape(plot)}</plot>')
        
        xml_lines.append('</tvshow>')
        
        return '\n'.join(xml_lines)
    
    def _generate_episode_nfo(self, episode) -> str:
        """Generate episode.nfo XML content for an episode."""
        # Extract episode info (clean language prefix)
        raw_title = episode.name or ""
        title = self._clean_title(raw_title) if raw_title else "Episode"
        season_num = episode.season_number or 0
        episode_num = episode.episode_number or 0
        plot = episode.description or ""
        
        # Build XML
        xml_lines = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>']
        xml_lines.append('<episodedetails>')
        xml_lines.append(f'    <title>{self._xml_escape(title)}</title>')
        xml_lines.append(f'    <season>{season_num}</season>')
        xml_lines.append(f'    <episode>{episode_num}</episode>')
        
        if plot:
            xml_lines.append(f'    <plot>{self._xml_escape(plot)}</plot>')
        
        xml_lines.append('</episodedetails>')
        
        return '\n'.join(xml_lines)
    
    def _generate_nfo(self, movie, category_name: str) -> str:
        """Generate NFO XML content for a movie."""
        # Extract basic info (clean language prefix)
        raw_title = movie.name or "Unknown"
        title = self._clean_title(raw_title)
        year = movie.year or ""
        plot = movie.description or ""
        rating = movie.rating or ""
        tmdb_id = movie.tmdb_id or ""
        imdb_id = movie.imdb_id or ""
        
        # Extract genres from category
        genres = self._extract_genres(category_name)
        
        # Build XML
        xml_lines = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>']
        xml_lines.append('<movie>')
        xml_lines.append(f'    <title>{self._xml_escape(title)}</title>')
        
        if year:
            xml_lines.append(f'    <year>{year}</year>')
        
        for genre in genres:
            xml_lines.append(f'    <genre>{self._xml_escape(genre)}</genre>')
        
        if plot:
            xml_lines.append(f'    <plot>{self._xml_escape(plot)}</plot>')
        
        if rating:
            xml_lines.append(f'    <rating>{rating}</rating>')
        
        if tmdb_id:
            xml_lines.append(f'    <tmdbid>{tmdb_id}</tmdbid>')
        
        if imdb_id:
            xml_lines.append(f'    <imdbid>{imdb_id}</imdbid>')
        
        xml_lines.append('</movie>')
        
        return '\n'.join(xml_lines)
    
    def _xml_escape(self, text: str) -> str:
        """Escape special XML characters."""
        if not text:
            return ""
        text = str(text)
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        text = text.replace('"', '&quot;')
        text = text.replace("'", '&apos;')
        return text
    
    def _sanitize_filename(self, name: str) -> str:
        """Sanitize filename by removing invalid characters."""
        if not name:
            return "Unknown"
        
        # Remove invalid characters for Windows/Linux filesystems
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name)
        
        # Replace multiple spaces with single space
        name = re.sub(r'\s+', ' ', name)
        
        # Trim and limit length
        name = name.strip()[:200]
        
        # Remove trailing dots/spaces (Windows issue)
        name = name.rstrip('. ')

        return name or "Unknown"

    def _rescan_all(self, settings: Dict[str, Any], logger):
        """Combined scan + generate movies + generate series. Used by the cron schedule.

        Always runs the series step with refresh_existing forced ON regardless of
        the saved setting, so cron rescans (and manual Rescan All clicks) reliably
        pick up new episodes for already-processed series. Movies are unaffected
        (they're idempotent at the .strm-file level already).
        """
        logger.info("Combined rescan: scan + movies + series (Refresh Existing forced ON for series)")
        logger.info("")

        scan = self._scan_all_vods(settings, logger)
        if scan.get("status") != "ok":
            return scan

        logger.info("")
        logger.info("=" * 60)
        logger.info("Rescan: movies")
        logger.info("=" * 60)
        movies = self._generate_movies(settings, logger)

        logger.info("")
        logger.info("=" * 60)
        logger.info("Rescan: series  (refresh_existing=True)")
        logger.info("=" * 60)
        series_settings = {**settings, "refresh_existing": True}
        series = self._generate_series(series_settings, logger)

        movie_msg = movies.get("message", "movies skipped")
        series_msg = series.get("message", "series skipped")

        return {
            "status": "ok",
            "message": f"Rescan complete — {movie_msg}; {series_msg}",
            "scan": scan,
            "movies": movies,
            "series": series,
        }

    def _parse_cron(self, cron_expr: str):
        """Validate and split a 5-field cron expression. Returns tuple or raises ValueError."""
        if not cron_expr:
            raise ValueError("Cron expression is empty")
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            raise ValueError(
                f"Cron expression must have 5 fields (minute hour dom month dow), got {len(parts)}: {cron_expr!r}"
            )
        return tuple(parts)

    def _apply_schedule(self, settings: Dict[str, Any], logger):
        """Register or update a periodic auto-rescan task via django-celery-beat."""
        cron_expr = settings.get("schedule_cron") or "0 3 * * *"
        target = settings.get("schedule_target") or "rescan_all"

        valid_targets = {"scan_all_vods", "generate_movies", "generate_series", "rescan_all"}
        if target not in valid_targets:
            return {"status": "error", "message": f"Invalid schedule_target: {target}"}

        try:
            minute, hour, dom, month, dow = self._parse_cron(cron_expr)
        except ValueError as e:
            logger.error("Invalid cron expression: %s", e)
            return {"status": "error", "message": str(e)}

        try:
            from django_celery_beat.models import PeriodicTask, CrontabSchedule
        except ImportError as e:
            logger.error("django-celery-beat is not installed: %s", e)
            logger.error("")
            logger.error("Fallback: add a host-side cron entry that POSTs to Dispatcharr's plugin")
            logger.error("action endpoint to trigger '%s' on plugin '%s'.", target, self.name)
            return {
                "status": "error",
                "message": "django-celery-beat not available. Use host cron to call the plugin action instead.",
            }

        import json
        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute=minute,
            hour=hour,
            day_of_month=dom,
            month_of_year=month,
            day_of_week=dow,
        )

        snapshot = {k: v for k, v in (settings or {}).items() if not k.startswith("schedule_")}

        task, created = PeriodicTask.objects.update_or_create(
            name=self.SCHEDULE_TASK_NAME,
            defaults={
                "crontab": schedule,
                "task": "vod2mlib.scheduled_rescan",
                "kwargs": json.dumps({"action": target, "settings": snapshot}),
                "enabled": True,
                "description": f"Auto-rescan for {self.name} v{self.version}",
            },
        )

        verb = "Created" if created else "Updated"
        logger.info("%s schedule: %s @ '%s' → action '%s'", verb, self.SCHEDULE_TASK_NAME, cron_expr, target)
        logger.info("Settings snapshot keys: %s", sorted(snapshot.keys()))
        logger.info("")
        logger.info("Note: re-run 'Apply Schedule' after changing settings to refresh the snapshot.")

        warning = ""
        refresh_on = bool(snapshot.get("refresh_existing", False))
        if target == "generate_series" and not refresh_on:
            warning = (
                " ⚠️ 'Refresh Existing Series' is OFF — cron will only ADD new series, "
                "not pick up new episodes for already-processed series. "
                "Turn it ON and re-Apply for true auto-rescans, or use target 'rescan_all' which forces it ON."
            )
            logger.warning(warning.strip())

        return {
            "status": "ok",
            "message": f"{verb} periodic task '{self.SCHEDULE_TASK_NAME}' for cron '{cron_expr}' → {target}.{warning}",
            "created": created,
            "cron": cron_expr,
            "target": target,
            "refresh_existing_in_snapshot": refresh_on,
        }

    def _remove_schedule(self, settings: Dict[str, Any], logger):
        """Unregister the periodic auto-rescan task."""
        try:
            from django_celery_beat.models import PeriodicTask
        except ImportError:
            return {"status": "ok", "message": "django-celery-beat not installed; nothing to remove."}

        deleted, _ = PeriodicTask.objects.filter(name=self.SCHEDULE_TASK_NAME).delete()
        if deleted:
            logger.info("Removed periodic task '%s'", self.SCHEDULE_TASK_NAME)
        else:
            logger.info("No periodic task named '%s' was registered.", self.SCHEDULE_TASK_NAME)
        return {"status": "ok", "message": f"Removed {deleted} scheduled task(s).", "deleted": deleted}

    def _schedule_status(self, settings: Dict[str, Any], logger):
        """Show current schedule registration."""
        try:
            from django_celery_beat.models import PeriodicTask
        except ImportError:
            msg = "django-celery-beat is not installed — scheduling disabled."
            logger.info(msg)
            return {"status": "ok", "message": msg, "scheduled": False, "reason": "django-celery-beat not installed"}

        task = PeriodicTask.objects.filter(name=self.SCHEDULE_TASK_NAME).first()
        if not task:
            msg = "No schedule registered. Click 'Apply Schedule' to enable auto-rescan."
            logger.info(msg)
            return {"status": "ok", "message": msg, "scheduled": False}

        cron = task.crontab
        cron_str = (
            f"{cron.minute} {cron.hour} {cron.day_of_month} {cron.month_of_year} {cron.day_of_week}"
            if cron else "<none>"
        )
        last_run = str(task.last_run_at) if task.last_run_at else "never"
        state = "enabled" if task.enabled else "disabled"

        logger.info("Schedule: %s", task.name)
        logger.info("  Enabled:    %s", task.enabled)
        logger.info("  Cron:       %s", cron_str)
        logger.info("  Task:       %s", task.task)
        logger.info("  Kwargs:     %s", task.kwargs)
        logger.info("  Last run:   %s", last_run)
        logger.info("  Total runs: %s", task.total_run_count)

        message = (
            f"Schedule {state} — cron '{cron_str}', "
            f"last run {last_run}, total runs {task.total_run_count}"
        )
        return {
            "status": "ok",
            "message": message,
            "scheduled": True,
            "enabled": task.enabled,
            "cron": cron_str,
            "task": task.task,
            "last_run_at": str(task.last_run_at) if task.last_run_at else None,
            "total_run_count": task.total_run_count,
        }


try:
    from celery import shared_task as _vod2mlib_shared_task

    @_vod2mlib_shared_task(name="vod2mlib.scheduled_rescan")
    def _vod2mlib_scheduled_rescan(action="rescan_all", settings=None):
        """Celery entry point invoked by the periodic task registered via _apply_schedule."""
        import logging
        logger = logging.getLogger("vod2mlib.schedule")
        return Plugin().run(action, {}, {"logger": logger, "settings": settings or {}})
except Exception:
    pass
