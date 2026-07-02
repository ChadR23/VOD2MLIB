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
