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
