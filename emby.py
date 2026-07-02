"""Emby-aware dedup support for VOD2MLIB.

Builds an in-memory index of content the user already owns as REAL files
in Emby (never .strm), so plugin.py can skip writing duplicate .strm
files and clean up ones the user has since acquired.

Matching rules (see docs/superpowers/specs/2026-07-02-vod2mlib-emby-dedup-design.md
in the parent project):
  * Movies: TMDB id, IMDB id, or normalized title + year (±1). Never title-only.
  * Episodes: (normalized series title, season#, episode#) or
    (series TMDB id, season#, episode#). NEVER episode titles — IPTV
    providers ship placeholder names like "Episode 7".

Stdlib only — no new dependencies.

MIT License, part of the VOD2MLIB fork.
"""
import json
import os
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class EmbyError(Exception):
    """Raised when the Emby API can't be reached or returns unusable data."""


# ---------- name normalization & path parsing (pure) ----------

_YEAR_SUFFIX_RE = re.compile(r'\s*\(\d{4}\)\s*$')
_APOSTROPHE_RE = re.compile(r"['’]")
_NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r'\s+')
_TMDB_SUFFIX_RE = re.compile(r'\s*\{tmdb-(\d+)\}\s*$')
_FOLDER_YEAR_RE = re.compile(r'\s*\((\d{4})\)\s*$')
_EPISODE_RE = re.compile(
    r'^(?P<series>.+?)\s+-\s+S(?P<s>\d{1,4})E(?P<e>\d{1,4})(?:\s+-\s+.*)?$',
    re.IGNORECASE,
)


def normalize_title(title):
    """Case/punctuation/year-insensitive form used as a match key.

    Most punctuation is replaced by a space (not removed) so 'Spider-Man'
    matches 'Spider Man'. Apostrophes are the exception: they are deleted
    with no space so "Shrimp's" matches 'Shrimps'. A trailing '(YYYY)' is
    stripped; a year that is part of the title proper ('Blade Runner 2049')
    is kept.
    """
    if not title:
        return ""
    t = _YEAR_SUFFIX_RE.sub('', title.casefold())
    t = _APOSTROPHE_RE.sub('', t)
    t = _NON_WORD_RE.sub(' ', t)
    return _WS_RE.sub(' ', t).strip()


def parse_movie_folder(folder_name):
    """Parse a plugin-written movie folder name back to identity.

    'The Matrix (1999) {tmdb-603}' -> ('The Matrix', 1999, '603')
    Returns (title, year|None, tmdb_id|None).
    """
    tmdb_id = None
    m = _TMDB_SUFFIX_RE.search(folder_name)
    if m:
        tmdb_id = m.group(1)
        folder_name = folder_name[:m.start()]
    year = None
    m = _FOLDER_YEAR_RE.search(folder_name)
    if m:
        year = int(m.group(1))
        folder_name = folder_name[:m.start()]
    return folder_name.strip(), year, tmdb_id


def parse_episode_strm(filename):
    """Parse a plugin-written episode filename back to identity.

    'BEEF - S02E07 - Episode 7.strm' -> ('BEEF', 2, 7)
    Returns None for files that don't look like plugin episode files.
    """
    if filename.lower().endswith('.strm'):
        stem = filename[:-5]
    else:
        return None
    m = _EPISODE_RE.match(stem)
    if not m:
        return None
    return m.group('series').strip(), int(m.group('s')), int(m.group('e'))


# ---------- owned-content index ----------

class EmbyIndex:
    """Fast lookup of content owned as real files in Emby.

    Built once per run, then read-only — safe to share across the
    ThreadPoolExecutor workers in _generate_series.
    """

    def __init__(self):
        self.movie_tmdb = set()        # str tmdb ids
        self.movie_imdb = set()        # str imdb ids, lowercased
        self.movie_title_year = set()  # (normalized_title, int_year)
        # ALL owned episodes by name — used as the loose fallback when the VOD
        # side has no known year (or the cache predates year-awareness).
        self.episode_by_name = set()   # (normalized_series, season, episode)
        # Owned episodes whose SERIES has no known year — matches any queried
        # year loosely (we can't disambiguate a remake without a year on our end).
        self.episode_by_name_yearless = set()  # (normalized_series, season, episode)
        # Owned episodes whose series year IS known — the year-scoped path, so
        # The Office (2005) doesn't false-positive against The Office (2001).
        self.episode_by_name_year = set()  # (normalized_series, int_year, season, episode)
        self.episode_by_tmdb = set()   # (str series_tmdb, season, episode)

    def add_movie(self, name, year, tmdb_id=None, imdb_id=None):
        if tmdb_id:
            self.movie_tmdb.add(str(tmdb_id))
        if imdb_id:
            self.movie_imdb.add(str(imdb_id).lower())
        key = normalize_title(name)
        if key and year:
            self.movie_title_year.add((key, int(year)))

    def add_episode(self, series_name, season, episode, series_tmdb_id=None, series_year=None):
        s, e = int(season), int(episode)
        key = normalize_title(series_name)
        if key:
            self.episode_by_name.add((key, s, e))  # always — loose fallback
            if series_year:
                self.episode_by_name_year.add((key, int(series_year), s, e))
            else:
                self.episode_by_name_yearless.add((key, s, e))
        if series_tmdb_id:
            self.episode_by_tmdb.add((str(series_tmdb_id), s, e))

    def has_movie(self, title, year, tmdb_id=None, imdb_id=None):
        if tmdb_id and str(tmdb_id) in self.movie_tmdb:
            return True
        if imdb_id and str(imdb_id).lower() in self.movie_imdb:
            return True
        if not year:
            return False  # never title-only — remakes would false-positive
        key = normalize_title(title)
        if not key:
            return False
        y = int(year)
        return any((key, cand) in self.movie_title_year for cand in (y, y - 1, y + 1))

    def has_episode(self, series_title, season, episode, series_tmdb_id=None, series_year=None):
        s, e = int(season), int(episode)
        if series_tmdb_id and (str(series_tmdb_id), s, e) in self.episode_by_tmdb:
            return True
        key = normalize_title(series_title)
        if not key:
            return False
        if not series_year:
            # No year on the VOD side — loose match (original behavior).
            return (key, s, e) in self.episode_by_name
        # Year known on both sides: match a yearless-owned series (can't
        # disambiguate) OR an owned series whose year is within ±1 (metadata
        # sources routinely disagree by a year).
        if (key, s, e) in self.episode_by_name_yearless:
            return True
        y = int(series_year)
        return any((key, cand, s, e) in self.episode_by_name_year for cand in (y - 1, y, y + 1))

    @property
    def is_empty(self):
        return not (self.movie_tmdb or self.movie_imdb or self.movie_title_year
                    or self.episode_by_name or self.episode_by_tmdb)

    def summary(self):
        # movie_title_year and movie_tmdb overlap for well-tagged items, so a
        # precise count isn't possible from sets alone — report the larger.
        movies = max(len(self.movie_title_year), len(self.movie_tmdb))
        episodes = max(len(self.episode_by_name), len(self.episode_by_tmdb))
        return f"{movies} movies, {episodes} episodes owned"

    def to_dict(self):
        return {
            "version": 1,
            "movie_tmdb": sorted(self.movie_tmdb),
            "movie_imdb": sorted(self.movie_imdb),
            "movie_title_year": sorted(self.movie_title_year),
            "episode_by_name": sorted(self.episode_by_name),
            "episode_by_name_yearless": sorted(self.episode_by_name_yearless),
            "episode_by_name_year": sorted(self.episode_by_name_year),
            "episode_by_tmdb": sorted(self.episode_by_tmdb),
        }

    @classmethod
    def from_dict(cls, data):
        idx = cls()
        idx.movie_tmdb = {str(x) for x in data["movie_tmdb"]}
        idx.movie_imdb = {str(x) for x in data["movie_imdb"]}
        idx.movie_title_year = {(t, int(y)) for t, y in data["movie_title_year"]}
        idx.episode_by_name = {(n, int(s), int(e)) for n, s, e in data["episode_by_name"]}
        idx.episode_by_tmdb = {(str(i), int(s), int(e)) for i, s, e in data["episode_by_tmdb"]}
        # NEW keys default sensibly so an old cache file (v1 without them) still
        # loads: yearless defaults to the full name set (loose = old behavior),
        # year-scoped defaults to empty.
        idx.episode_by_name_yearless = {
            (n, int(s), int(e))
            for n, s, e in data.get("episode_by_name_yearless", data["episode_by_name"])
        }
        idx.episode_by_name_year = {
            (n, int(y), int(s), int(e))
            for n, y, s, e in data.get("episode_by_name_year", [])
        }
        return idx


# ---------- Emby HTTP API ----------

def _http_get_json(base_url, path, params, api_key, timeout=30):
    """GET an Emby endpoint, return parsed JSON. API key goes in the
    X-Emby-Token header so it never shows up in logged URLs."""
    url = f"{base_url}{path}"
    if params:
        url += "?" + urlencode(params)
    req = Request(url, headers={"X-Emby-Token": api_key, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise EmbyError(f"GET {path} failed: {e}") from e


def resolve_library_ids(base_url, api_key, library_names):
    """Map configured library names -> Emby ItemIds (case-insensitive).

    Raises EmbyError naming both the missing and the available libraries,
    so a typo in settings produces an actionable message.
    """
    folders = _http_get_json(base_url, "/emby/Library/VirtualFolders", {}, api_key)
    if isinstance(folders, dict):
        folders = folders.get("Items") or []
    by_lower = {(f.get("Name") or "").lower(): f for f in folders}
    resolved, missing = {}, []
    for want in library_names:
        f = by_lower.get(want.strip().lower())
        if f is None:
            missing.append(want.strip())
        else:
            lib_id = str(f.get("ItemId") or f.get("Id") or "")
            if not lib_id:
                # An empty ParentId makes /emby/Items query the WHOLE server,
                # counting items outside the chosen libraries as "owned" — refuse.
                raise EmbyError(
                    f"Emby library '{f.get('Name') or want.strip()}' has no ItemId "
                    "— cannot scope the query"
                )
            resolved[f["Name"]] = lib_id
    if missing:
        available = ", ".join(sorted(f.get("Name", "?") for f in folders))
        raise EmbyError(
            f"Emby libraries not found: {', '.join(missing)}. Available: {available}"
        )
    return resolved


def _iter_items(base_url, api_key, parent_id, item_type, fields, page_size=1000):
    """Yield all items of item_type under parent_id, following pagination."""
    start = 0
    while True:
        data = _http_get_json(base_url, "/emby/Items", {
            "ParentId": parent_id,
            "IncludeItemTypes": item_type,
            "Recursive": "true",
            "Fields": fields,
            "EnableImages": "false",
            "StartIndex": start,
            "Limit": page_size,
        }, api_key)
        items = data.get("Items") or []
        for item in items:
            yield item
        start += len(items)
        total = int(data.get("TotalRecordCount") or 0)
        if not items or start >= total:
            return


def _provider_ids(item):
    """Case-tolerant ProviderIds lookup: returns (tmdb, imdb) or Nones."""
    prov = {k.lower(): v for k, v in (item.get("ProviderIds") or {}).items()}
    return prov.get("tmdb"), prov.get("imdb")


def _is_strm(item):
    return (item.get("Path") or "").lower().endswith(".strm")


def fetch_index(base_url, api_key, library_names, logger, page_size=1000):
    """Build an EmbyIndex of REAL files across the given libraries.

    Items whose Path ends in .strm are excluded — second line of defense
    so the plugin's own VOD library can never count as "owned" even if a
    user lists it in emby_libraries by mistake.

    Raises EmbyError on any HTTP failure or if the result is empty
    (an empty index would authorize mass-deleting nothing-is-owned state,
    which is far more likely a misconfiguration than reality).
    """
    idx = EmbyIndex()
    lib_ids = resolve_library_ids(base_url, api_key, library_names)
    for lib_name, lib_id in lib_ids.items():
        movies = episodes = 0
        for item in _iter_items(base_url, api_key, lib_id, "Movie",
                                "ProviderIds,ProductionYear,Path", page_size):
            if _is_strm(item):
                continue
            tmdb, imdb = _provider_ids(item)
            idx.add_movie(item.get("Name") or "", item.get("ProductionYear"),
                          tmdb_id=tmdb, imdb_id=imdb)
            movies += 1
        series_tmdb_by_id = {}
        series_year_by_id = {}
        for item in _iter_items(base_url, api_key, lib_id, "Series",
                                "ProviderIds,ProductionYear,Path", page_size):
            tmdb, _ = _provider_ids(item)
            if tmdb:
                series_tmdb_by_id[item.get("Id")] = str(tmdb)
            series_year_by_id[item.get("Id")] = item.get("ProductionYear")
        for item in _iter_items(base_url, api_key, lib_id, "Episode",
                                "Path,ParentIndexNumber,IndexNumber,SeriesName,SeriesId",
                                page_size):
            if _is_strm(item):
                continue
            season, ep = item.get("ParentIndexNumber"), item.get("IndexNumber")
            if season is None or ep is None:
                continue
            idx.add_episode(item.get("SeriesName") or "", season, ep,
                            series_tmdb_id=series_tmdb_by_id.get(item.get("SeriesId")),
                            series_year=series_year_by_id.get(item.get("SeriesId")))
            episodes += 1
        logger.info("Emby library '%s': %d movies, %d episodes indexed", lib_name, movies, episodes)
    if idx.is_empty:
        raise EmbyError(
            "Emby returned no owned items across the configured libraries — "
            "refusing to dedup against an empty index (likely a misconfiguration)."
        )
    return idx


def trigger_library_refresh(base_url, api_key, logger):
    """Ask Emby to rescan its libraries so deletions disappear promptly.
    Best-effort: failures are logged, never raised."""
    url = f"{base_url}/emby/Library/Refresh"
    req = Request(url, data=b"", headers={"X-Emby-Token": api_key}, method="POST")
    try:
        with urlopen(req, timeout=30):
            pass
        logger.info("Triggered Emby library refresh.")
        return True
    except Exception as e:
        logger.warning("Emby library refresh trigger failed (non-fatal): %s", e)
        return False


# ---------- orchestration: settings -> index (with cache fallback) ----------

def _parse_libraries(raw):
    return [name.strip() for name in (raw or "").split(",") if name.strip()]


def save_cache(index, cache_path, logger):
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(index.to_dict(), f)
    except OSError as e:
        logger.warning("Could not write Emby index cache %s: %s", cache_path, e)


def load_cache(cache_path, logger):
    """Returns an EmbyIndex from the cache file, or None if absent/corrupt."""
    if not os.path.isfile(cache_path):
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return EmbyIndex.from_dict(json.load(f))
    except (OSError, ValueError, KeyError, TypeError) as e:
        logger.warning("Emby index cache %s unreadable (%s) — ignoring it.", cache_path, e)
        return None


def build_emby_index(settings, logger, cache_path):
    """Resolve settings into an owned-content index.

    Returns (index_or_None, source) with source in:
      "live"        — fresh from the Emby API (cache updated)
      "cache"       — Emby unreachable, last good index used (stale-but-safe)
      "disabled"    — feature off or not configured; dedup is a no-op
      "unavailable" — Emby unreachable AND no cache; caller MUST NOT skip
                      or delete anything this run
    """
    if not settings.get("emby_enabled", False):
        return None, "disabled"
    base_url = (settings.get("emby_url") or "").strip().rstrip("/")
    api_key = (settings.get("emby_api_key") or "").strip()
    libraries = _parse_libraries(settings.get("emby_libraries"))
    problems = []
    if not base_url.startswith(("http://", "https://")):
        problems.append("Emby URL missing or not http(s)")
    if not api_key:
        problems.append("Emby API key missing")
    if not libraries:
        problems.append("Emby libraries list empty")
    if problems:
        logger.warning("Emby dedup is ON but not usable: %s. Dedup disabled this run.",
                       "; ".join(problems))
        return None, "disabled"
    try:
        idx = fetch_index(base_url, api_key, libraries, logger)
        save_cache(idx, cache_path, logger)
        return idx, "live"
    except Exception as e:
        # Catch broadly (not just EmbyError): mis-shaped Emby data can escape
        # the fetch path as AttributeError/TypeError/ValueError, and those must
        # take the same cache/unavailable fallback instead of crashing the action.
        logger.warning("Emby fetch failed: %s: %s", type(e).__name__, e)
        cached = load_cache(cache_path, logger)
        if cached is not None and not cached.is_empty:
            logger.warning("Using last good Emby index from cache (stale-but-safe).")
            return cached, "cache"
        logger.warning("No usable Emby index cache — dedup fully disabled this run "
                       "(nothing will be skipped or deleted).")
        return None, "unavailable"
