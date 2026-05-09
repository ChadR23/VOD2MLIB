"""Unit tests for VOD2MLIB's pure helper methods.

These methods don't touch Django/DB/filesystem and are safe to test in
isolation. Run with `pytest` from the repo root.
"""
import os
import sys

# Make the repo root importable so `import plugin` resolves to plugin.py.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from plugin import Plugin


@pytest.fixture
def p():
    return Plugin()


# ---------- _clean_title ----------

class TestCleanTitle:
    def test_strips_two_letter_language_prefix(self, p):
        assert p._clean_title("EN - Inception") == "Inception"

    def test_strips_three_letter_language_prefix(self, p):
        assert p._clean_title("ENG - Inception") == "Inception"

    def test_preserves_AC_130_style_titles(self, p):
        # The whole point of the v1.5 regex tightening
        assert p._clean_title("AC-130") == "AC-130"
        assert p._clean_title("MI-5") == "MI-5"

    def test_no_prefix_unchanged(self, p):
        assert p._clean_title("The Matrix") == "The Matrix"

    def test_empty_input(self, p):
        assert p._clean_title("") == ""
        assert p._clean_title(None) is None

    def test_whitespace_trimmed_after_strip(self, p):
        assert p._clean_title("FR -   Amélie") == "Amélie"


# ---------- _strip_trailing_year ----------

class TestStripTrailingYear:
    def test_strips_year(self, p):
        assert p._strip_trailing_year("Aladdin (2026)") == ("Aladdin", 2026)

    def test_no_year_returns_none(self, p):
        cleaned, year = p._strip_trailing_year("Aladdin")
        assert cleaned == "Aladdin"
        assert year is None

    def test_year_in_middle_not_stripped(self, p):
        # "(2026)" not trailing
        cleaned, year = p._strip_trailing_year("The Year (2026) Movie")
        assert cleaned == "The Year (2026) Movie"
        assert year is None

    def test_extra_trailing_whitespace(self, p):
        assert p._strip_trailing_year("Aladdin (2026)  ") == ("Aladdin", 2026)

    def test_empty_input(self, p):
        cleaned, year = p._strip_trailing_year("")
        assert cleaned == ""
        assert year is None
        cleaned, year = p._strip_trailing_year(None)
        assert cleaned == ""
        assert year is None

    def test_three_digit_year_not_matched(self, p):
        # Regex requires exactly 4 digits
        cleaned, year = p._strip_trailing_year("Old Film (123)")
        assert cleaned == "Old Film (123)"
        assert year is None

    def test_double_year_strips_only_outermost(self, p):
        # A pre-v1.5 folder name that somehow makes it back into a title
        cleaned, year = p._strip_trailing_year("Aladdin (2026) (2026)")
        assert cleaned == "Aladdin (2026)"
        assert year == 2026


# ---------- _sanitize_filename ----------

class TestSanitizeFilename:
    def test_strips_invalid_chars(self, p):
        assert p._sanitize_filename('a<b>c:"d/e\\f|g?h*i') == "abcdefghi"

    def test_strips_control_chars(self, p):
        assert p._sanitize_filename("a\x00b\x1fc") == "abc"

    def test_collapses_runs_of_spaces(self, p):
        assert p._sanitize_filename("a   b   c") == "a b c"

    def test_tabs_stripped_as_control_chars(self, p):
        # Tabs and other \x00-\x1f bytes are stripped BEFORE whitespace collapse.
        # Documenting current behaviour: "a\t\tb" loses its separator.
        assert p._sanitize_filename("a\t\tb") == "ab"

    def test_trims_to_max_length(self, p):
        long = "x" * 500
        result = p._sanitize_filename(long)
        assert len(result) == p.MAX_FILENAME_LEN

    def test_strips_trailing_dots_and_spaces(self, p):
        assert p._sanitize_filename("name. . .") == "name"

    def test_dotdot_becomes_unknown(self, p):
        # Path traversal defense: '..' rstrips to empty, falls back to Unknown
        assert p._sanitize_filename("..") == "Unknown"

    def test_empty_input(self, p):
        assert p._sanitize_filename("") == "Unknown"
        assert p._sanitize_filename(None) == "Unknown"

    def test_normal_movie_name(self, p):
        assert p._sanitize_filename("Aladdin (2026)") == "Aladdin (2026)"


# ---------- _parse_cron ----------

class TestParseCron:
    def test_valid_5_field(self, p):
        assert p._parse_cron("0 3 * * *") == ("0", "3", "*", "*", "*")

    def test_complex_expression(self, p):
        assert p._parse_cron("*/15 9-17 1,15 * 1-5") == ("*/15", "9-17", "1,15", "*", "1-5")

    def test_empty_raises(self, p):
        with pytest.raises(ValueError, match="empty"):
            p._parse_cron("")

    def test_too_few_fields_raises(self, p):
        with pytest.raises(ValueError, match="5 fields"):
            p._parse_cron("0 3 * *")

    def test_too_many_fields_raises(self, p):
        with pytest.raises(ValueError, match="5 fields"):
            p._parse_cron("0 3 * * * *")

    def test_extra_whitespace_normalised(self, p):
        assert p._parse_cron("  0   3 * * *  ") == ("0", "3", "*", "*", "*")


# ---------- _extract_genres ----------

class TestExtractGenres:
    def test_strips_language_prefix(self, p):
        # EN - prefix should be removed, NOT the AC- in AC-130 style names
        assert p._extract_genres("EN - Action") == ["Action"]

    def test_preserves_AC_130_in_category(self, p):
        # Regression: was previously stripped, leaving "130 Action"
        assert p._extract_genres("AC-130 Action") == ["Ac-130 Action"]

    def test_strips_movie_suffix(self, p):
        assert p._extract_genres("Action (movie)") == ["Action"]
        assert p._extract_genres("Drama (series)") == ["Drama"]

    def test_splits_on_separators(self, p):
        assert p._extract_genres("Action / Adventure") == ["Action", "Adventure"]
        assert p._extract_genres("Action & Adventure") == ["Action", "Adventure"]
        assert p._extract_genres("Action, Adventure") == ["Action", "Adventure"]

    def test_capitalises_each_word(self, p):
        assert p._extract_genres("science fiction") == ["Science Fiction"]

    def test_empty_returns_empty_list(self, p):
        assert p._extract_genres("") == []
        assert p._extract_genres(None) == []

    def test_unknown_fallback(self, p):
        # If everything is stripped away
        assert p._extract_genres("(movie)") == ["Unknown"]


# ---------- _mask_url ----------

class TestMaskUrl:
    def test_masks_host(self, p):
        assert p._mask_url("http://192.168.100.111:9191/path") == "http://<host>:9191/path"

    def test_masks_host_no_port(self, p):
        assert p._mask_url("http://example.com/path") == "http://<host>/path"

    def test_handles_no_path(self, p):
        assert p._mask_url("http://example.com:8080") == "http://<host>:8080"

    def test_unrecognised_url_passthrough(self, p):
        assert p._mask_url("not-a-url") == "not-a-url"

    def test_empty(self, p):
        assert p._mask_url("") == ""


# ---------- _valid_schedule_targets ----------

class TestValidScheduleTargets:
    def test_returns_action_ids_from_manifest(self, p):
        targets = p._valid_schedule_targets()
        # Should match the schedule_target field's options
        assert "rescan_all" in targets
        assert "scan_all_vods" in targets
        assert "generate_movies" in targets
        assert "generate_series" in targets
        # Should NOT contain non-target actions
        assert "cleanup_movies" not in targets
        assert "apply_schedule" not in targets


# ---------- _movie_target_paths ----------

class TestMovieTargetPaths:
    def test_uses_db_year(self, p):
        # Build a minimal stand-in with the attributes the helper reads
        class M:
            id = 1
            uuid = "abc"
            name = "Aladdin"
            year = 1992
        folder, strm, name, year = p._movie_target_paths(M(), "/VODS/Movies")
        assert folder == "/VODS/Movies/Aladdin (1992)"
        assert strm == "Aladdin (1992).strm"
        assert name == "Aladdin"
        assert year == 1992

    def test_strips_year_from_title_and_dedupes(self, p):
        class M:
            id = 1
            uuid = "abc"
            name = "Aladdin (2026)"
            year = 2026
        folder, strm, name, year = p._movie_target_paths(M(), "/VODS/Movies")
        # The fix: no double year
        assert folder == "/VODS/Movies/Aladdin (2026)"
        assert strm == "Aladdin (2026).strm"
        assert name == "Aladdin"
        assert year == 2026

    def test_recovers_year_from_title_when_db_year_missing(self, p):
        class M:
            id = 1
            uuid = "abc"
            name = "Aladdin (1992)"
            year = None
        folder, strm, name, year = p._movie_target_paths(M(), "/VODS/Movies")
        assert folder == "/VODS/Movies/Aladdin (1992)"
        assert year == 1992

    def test_no_year_anywhere(self, p):
        class M:
            id = 7
            uuid = "abc"
            name = "Mystery Title"
            year = None
        folder, strm, name, year = p._movie_target_paths(M(), "/VODS/Movies")
        assert folder == "/VODS/Movies/Mystery Title"
        assert strm == "Mystery Title.strm"
        assert year is None
