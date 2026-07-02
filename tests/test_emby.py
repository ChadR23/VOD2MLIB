"""Unit tests for emby.py — Emby-aware dedup helpers.

Pure logic only (no HTTP, no Django, no filesystem). Run with `pytest`
from the repo root, same as test_helpers.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from emby import normalize_title, parse_movie_folder, parse_episode_strm


class TestNormalizeTitle:
    def test_lowercases_and_strips(self):
        assert normalize_title("  The Matrix ") == "the matrix"

    def test_strips_trailing_year_parens(self):
        assert normalize_title("BEEF (2023)") == "beef"

    def test_punctuation_becomes_space(self):
        # 'Spider-Man' must match 'Spider Man'
        assert normalize_title("Spider-Man") == normalize_title("Spider Man")

    def test_apostrophes_removed(self):
        assert normalize_title("Shrimp's Odyssey") == normalize_title("Shrimps Odyssey")

    def test_whitespace_collapsed(self):
        assert normalize_title("The   Hour  of   Separation") == "the hour of separation"

    def test_empty_and_none(self):
        assert normalize_title("") == ""
        assert normalize_title(None) == ""

    def test_year_in_middle_not_stripped(self):
        assert normalize_title("Blade Runner 2049") == "blade runner 2049"


class TestParseMovieFolder:
    def test_title_year(self):
        assert parse_movie_folder("The Matrix (1999)") == ("The Matrix", 1999, None)

    def test_title_year_tmdb(self):
        assert parse_movie_folder("The Matrix (1999) {tmdb-603}") == ("The Matrix", 1999, "603")

    def test_title_only(self):
        assert parse_movie_folder("Avatar") == ("Avatar", None, None)

    def test_tmdb_without_year(self):
        assert parse_movie_folder("Avatar {tmdb-19995}") == ("Avatar", None, "19995")

    def test_year_is_whole_title(self):
        # Folder for the movie "1984" with no (year) suffix
        assert parse_movie_folder("1984") == ("1984", None, None)


class TestParseEpisodeStrm:
    def test_standard(self):
        assert parse_episode_strm("BEEF - S02E07 - Episode 7.strm") == ("BEEF", 2, 7)

    def test_no_episode_title(self):
        assert parse_episode_strm("BEEF - S02E07.strm") == ("BEEF", 2, 7)

    def test_dash_in_series_name(self):
        assert parse_episode_strm("Obi-Wan Kenobi - S01E03 - Part III.strm") == ("Obi-Wan Kenobi", 1, 3)

    def test_dash_in_episode_title(self):
        got = parse_episode_strm("BEEF - S01E01 - The Birds Don't Sing - They Screech.strm")
        assert got == ("BEEF", 1, 1)

    def test_not_an_episode_returns_none(self):
        assert parse_episode_strm("tvshow.nfo") is None
        assert parse_episode_strm("Random File.strm") is None


from emby import EmbyIndex


@pytest.fixture
def idx():
    i = EmbyIndex()
    i.add_movie("The Matrix", 1999, tmdb_id="603", imdb_id="tt0133093")
    i.add_movie("Heat", 1995)                       # no provider ids
    i.add_episode("BEEF", 2, 7, series_tmdb_id="223333")
    i.add_episode("Smiling Friends", 1, 3)          # no tmdb
    return i


class TestEmbyIndexMovies:
    def test_match_by_tmdb_id_alone(self, idx):
        # Wildly different title/year — the forced id match wins
        assert idx.has_movie("Wrong Title", 2020, tmdb_id="603")

    def test_match_by_imdb_id_alone(self, idx):
        assert idx.has_movie("Wrong Title", None, imdb_id="tt0133093")

    def test_match_by_title_year(self, idx):
        assert idx.has_movie("Heat", 1995)

    def test_title_year_normalized(self, idx):
        assert idx.has_movie("HEAT", 1995)

    def test_year_off_by_one_matches(self, idx):
        # Metadata sources commonly disagree by one year
        assert idx.has_movie("Heat", 1996)
        assert idx.has_movie("Heat", 1994)

    def test_year_off_by_two_no_match(self, idx):
        assert not idx.has_movie("Heat", 1997)

    def test_no_year_never_title_only_matches(self, idx):
        # Spec: no title-only matching (remake false positives)
        assert not idx.has_movie("Heat", None)

    def test_unowned_movie(self, idx):
        assert not idx.has_movie("Barbie", 2023)


class TestEmbyIndexEpisodes:
    def test_match_by_series_and_numbers(self, idx):
        assert idx.has_episode("BEEF", 2, 7)

    def test_episode_title_irrelevant(self, idx):
        # We only ever key on numbers; series name normalized
        assert idx.has_episode("beef", 2, 7)

    def test_match_by_series_tmdb(self, idx):
        assert idx.has_episode("Totally Different Name", 2, 7, series_tmdb_id="223333")

    def test_series_year_suffix_normalized(self, idx):
        assert idx.has_episode("Smiling Friends (2020)", 1, 3)

    def test_unowned_episode_of_owned_series(self, idx):
        assert not idx.has_episode("BEEF", 2, 8)

    def test_unowned_series(self, idx):
        assert not idx.has_episode("Severance", 1, 1)


class TestEmbyIndexMisc:
    def test_is_empty(self, idx):
        assert not idx.is_empty
        assert EmbyIndex().is_empty

    def test_summary_mentions_counts(self, idx):
        s = idx.summary()
        assert "2 movies" in s and "2 episodes" in s

    def test_roundtrip_through_dict(self, idx):
        clone = EmbyIndex.from_dict(idx.to_dict())
        assert clone.has_movie("Heat", 1995)
        assert clone.has_movie("x", None, tmdb_id="603")
        assert clone.has_episode("BEEF", 2, 7)
        assert clone.has_episode("x", 2, 7, series_tmdb_id="223333")
        assert not clone.has_episode("BEEF", 2, 8)

    def test_from_dict_garbage_raises(self):
        with pytest.raises(Exception):
            EmbyIndex.from_dict({"movies": "nope"})


import emby
from emby import EmbyError, fetch_index, resolve_library_ids


class FakeLogger:
    def __init__(self):
        self.warnings, self.errors, self.infos = [], [], []
    def warning(self, msg, *a): self.warnings.append(msg % a if a else msg)
    def error(self, msg, *a): self.errors.append(msg % a if a else msg)
    def info(self, msg, *a): self.infos.append(msg % a if a else msg)


VIRTUAL_FOLDERS = [
    {"Name": "Movies", "ItemId": "lib1", "CollectionType": "movies"},
    {"Name": "TV Shows", "ItemId": "lib2", "CollectionType": "tvshows"},
    {"Name": "Dispatcharr VODs", "ItemId": "lib3", "CollectionType": "tvshows"},
]


def make_fake_http(items_by_type, virtual_folders=VIRTUAL_FOLDERS, page_size_cap=None):
    """items_by_type: {'Movie': [...], 'Series': [...], 'Episode': [...]}"""
    def fake(base_url, path, params, api_key, timeout=30):
        if path == "/emby/Library/VirtualFolders":
            return virtual_folders
        assert path == "/emby/Items"
        typ = params["IncludeItemTypes"]
        all_items = items_by_type.get(typ, [])
        start = int(params.get("StartIndex", 0))
        limit = int(params.get("Limit", 1000))
        if page_size_cap:
            limit = min(limit, page_size_cap)
        return {"Items": all_items[start:start + limit],
                "TotalRecordCount": len(all_items)}
    return fake


MOVIE_ITEMS = [
    {"Name": "The Matrix", "ProductionYear": 1999, "Path": "/jbod/movies/The Matrix (1999)/matrix.mkv",
     "ProviderIds": {"Tmdb": "603", "Imdb": "tt0133093"}},
    {"Name": "Heat", "ProductionYear": 1995, "Path": "/jbod/movies/Heat (1995)/heat.mkv",
     "ProviderIds": {}},
    # A .strm inside a "real" library must be excluded from the index
    {"Name": "Sneaky VOD", "ProductionYear": 2024, "Path": "/VODS/Movies/Sneaky VOD (2024)/Sneaky VOD (2024).strm",
     "ProviderIds": {"Tmdb": "999"}},
]

SERIES_ITEMS = [
    {"Id": "ser1", "Name": "BEEF", "Path": "/jbod/tv/BEEF", "ProviderIds": {"Tmdb": "223333"}},
    {"Id": "ser2", "Name": "Smiling Friends", "Path": "/jbod/tv/Smiling Friends", "ProviderIds": {}},
]

EPISODE_ITEMS = [
    {"SeriesId": "ser1", "SeriesName": "BEEF", "ParentIndexNumber": 2, "IndexNumber": 7,
     "Path": "/jbod/tv/BEEF/S02/BEEF - S02E07 - The Hour of Separation.mkv"},
    {"SeriesId": "ser2", "SeriesName": "Smiling Friends", "ParentIndexNumber": 1, "IndexNumber": 3,
     "Path": "/jbod/tv/Smiling Friends/S01/ep.mkv"},
    # .strm episode must be excluded
    {"SeriesId": "ser1", "SeriesName": "BEEF", "ParentIndexNumber": 2, "IndexNumber": 8,
     "Path": "/VODS/Series/BEEF/Season 02/BEEF - S02E08.strm"},
    # Missing numbers must be skipped, not crash
    {"SeriesId": "ser2", "SeriesName": "Smiling Friends", "ParentIndexNumber": None, "IndexNumber": 4,
     "Path": "/jbod/tv/x.mkv"},
]


class TestResolveLibraryIds:
    def test_resolves_case_insensitive(self, monkeypatch):
        monkeypatch.setattr(emby, "_http_get_json", make_fake_http({}))
        ids = resolve_library_ids("http://emby:8096", "k", ["movies", "TV SHOWS"])
        assert ids == {"Movies": "lib1", "TV Shows": "lib2"}

    def test_missing_library_raises_with_available_names(self, monkeypatch):
        monkeypatch.setattr(emby, "_http_get_json", make_fake_http({}))
        with pytest.raises(EmbyError) as exc:
            resolve_library_ids("http://emby:8096", "k", ["Moviez"])
        assert "Moviez" in str(exc.value)
        assert "Movies" in str(exc.value)  # lists what IS available


class TestFetchIndex:
    def fetch(self, monkeypatch, **kw):
        monkeypatch.setattr(emby, "_http_get_json", make_fake_http(
            {"Movie": MOVIE_ITEMS, "Series": SERIES_ITEMS, "Episode": EPISODE_ITEMS}, **kw))
        return fetch_index("http://emby:8096", "k", ["Movies", "TV Shows"], FakeLogger())

    def test_movies_indexed(self, monkeypatch):
        idx = self.fetch(monkeypatch)
        assert idx.has_movie("The Matrix", 1999)
        assert idx.has_movie("x", None, tmdb_id="603")
        assert idx.has_movie("Heat", 1995)

    def test_strm_items_excluded(self, monkeypatch):
        idx = self.fetch(monkeypatch)
        assert not idx.has_movie("Sneaky VOD", 2024)
        assert not idx.has_movie("x", None, tmdb_id="999")
        assert not idx.has_episode("BEEF", 2, 8)

    def test_episodes_indexed_by_name_and_series_tmdb(self, monkeypatch):
        idx = self.fetch(monkeypatch)
        assert idx.has_episode("BEEF", 2, 7)
        assert idx.has_episode("anything", 2, 7, series_tmdb_id="223333")
        assert idx.has_episode("Smiling Friends", 1, 3)

    def test_episode_missing_numbers_skipped(self, monkeypatch):
        idx = self.fetch(monkeypatch)
        assert not idx.has_episode("Smiling Friends", 0, 4)

    def test_pagination(self, monkeypatch):
        idx = self.fetch(monkeypatch, page_size_cap=1)  # force many pages
        assert idx.has_movie("Heat", 1995)
        assert idx.has_episode("Smiling Friends", 1, 3)

    def test_empty_index_raises(self, monkeypatch):
        monkeypatch.setattr(emby, "_http_get_json", make_fake_http(
            {"Movie": [], "Series": [], "Episode": []}))
        with pytest.raises(EmbyError):
            fetch_index("http://emby:8096", "k", ["Movies"], FakeLogger())

    def test_http_error_propagates_as_emby_error(self, monkeypatch):
        def boom(*a, **kw):
            raise EmbyError("connection refused")
        monkeypatch.setattr(emby, "_http_get_json", boom)
        with pytest.raises(EmbyError):
            fetch_index("http://emby:8096", "k", ["Movies"], FakeLogger())


from emby import build_emby_index

GOOD_SETTINGS = {
    "emby_enabled": True,
    "emby_url": "http://emby:8096/",   # trailing slash on purpose
    "emby_api_key": "k",
    "emby_libraries": "Movies, TV Shows",
}


class TestBuildEmbyIndex:
    def test_disabled_returns_none(self, tmp_path):
        idx, source = build_emby_index({"emby_enabled": False}, FakeLogger(), str(tmp_path / "c.json"))
        assert idx is None and source == "disabled"

    def test_enabled_but_unconfigured_is_disabled_with_warning(self, tmp_path):
        log = FakeLogger()
        idx, source = build_emby_index({"emby_enabled": True}, log, str(tmp_path / "c.json"))
        assert idx is None and source == "disabled"
        assert log.warnings  # tells the user what's missing

    def test_live_fetch_writes_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(emby, "_http_get_json", make_fake_http(
            {"Movie": MOVIE_ITEMS, "Series": SERIES_ITEMS, "Episode": EPISODE_ITEMS}))
        cache = tmp_path / "c.json"
        idx, source = build_emby_index(GOOD_SETTINGS, FakeLogger(), str(cache))
        assert source == "live"
        assert idx.has_movie("Heat", 1995)
        assert cache.exists()

    def test_fetch_failure_falls_back_to_cache(self, tmp_path, monkeypatch):
        # First: a good run to populate the cache
        monkeypatch.setattr(emby, "_http_get_json", make_fake_http(
            {"Movie": MOVIE_ITEMS, "Series": SERIES_ITEMS, "Episode": EPISODE_ITEMS}))
        cache = tmp_path / "c.json"
        build_emby_index(GOOD_SETTINGS, FakeLogger(), str(cache))
        # Then: Emby goes down
        def boom(*a, **kw):
            raise EmbyError("down")
        monkeypatch.setattr(emby, "_http_get_json", boom)
        log = FakeLogger()
        idx, source = build_emby_index(GOOD_SETTINGS, log, str(cache))
        assert source == "cache"
        assert idx.has_movie("Heat", 1995)
        assert log.warnings

    def test_fetch_failure_no_cache_returns_unavailable(self, tmp_path, monkeypatch):
        def boom(*a, **kw):
            raise EmbyError("down")
        monkeypatch.setattr(emby, "_http_get_json", boom)
        idx, source = build_emby_index(GOOD_SETTINGS, FakeLogger(), str(tmp_path / "nope.json"))
        assert idx is None and source == "unavailable"

    def test_corrupt_cache_returns_unavailable(self, tmp_path, monkeypatch):
        def boom(*a, **kw):
            raise EmbyError("down")
        monkeypatch.setattr(emby, "_http_get_json", boom)
        cache = tmp_path / "c.json"
        cache.write_text("{not json", encoding="utf-8")
        idx, source = build_emby_index(GOOD_SETTINGS, FakeLogger(), str(cache))
        assert idx is None and source == "unavailable"
