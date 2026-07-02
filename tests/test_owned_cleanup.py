"""Filesystem tests for the Emby owned-content cleanup pass.

Uses tmp_path and a hand-built EmbyIndex — no Django, no HTTP.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from emby import EmbyIndex
from plugin import Plugin


class CapturingLogger:
    def __init__(self):
        self.warnings, self.errors, self.infos = [], [], []
    def warning(self, *a, **kw): self.warnings.append(a[0] if a else "")
    def error(self, *a, **kw): self.errors.append(a[0] if a else "")
    def info(self, *a, **kw): self.infos.append(a[0] if a else "")


@pytest.fixture
def p():
    return Plugin()


@pytest.fixture
def log():
    return CapturingLogger()


@pytest.fixture
def idx():
    i = EmbyIndex()
    i.add_movie("Heat", 1995)
    i.add_movie("The Matrix", 1999, tmdb_id="603")
    i.add_episode("BEEF", 2, 7)
    return i


def write(path, content="http://d/proxy"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


class TestCleanupOwnedMovies:
    def test_owned_movie_deleted_with_nfo_and_folder(self, p, idx, log, tmp_path):
        root = str(tmp_path)
        write(os.path.join(root, "Heat (1995)", "Heat (1995).strm"))
        write(os.path.join(root, "Heat (1995)", "Heat (1995).nfo"))
        res = p._cleanup_owned_movies(root, idx, False, log)
        assert res["deleted_strm"] == 1
        assert res["deleted_nfo"] == 1
        assert not os.path.exists(os.path.join(root, "Heat (1995)"))

    def test_owned_by_tmdb_suffix(self, p, idx, log, tmp_path):
        root = str(tmp_path)
        write(os.path.join(root, "Wrong Title (2003) {tmdb-603}", "Wrong Title (2003).strm"))
        res = p._cleanup_owned_movies(root, idx, False, log)
        assert res["deleted_strm"] == 1

    def test_unowned_movie_kept(self, p, idx, log, tmp_path):
        root = str(tmp_path)
        strm = os.path.join(root, "Barbie (2023)", "Barbie (2023).strm")
        write(strm)
        res = p._cleanup_owned_movies(root, idx, False, log)
        assert res["deleted_strm"] == 0
        assert os.path.exists(strm)

    def test_nested_category_layout(self, p, idx, log, tmp_path):
        root = str(tmp_path)
        write(os.path.join(root, "Action", "Heat (1995)", "Heat (1995).strm"))
        res = p._cleanup_owned_movies(root, idx, False, log)
        assert res["deleted_strm"] == 1
        assert not os.path.exists(os.path.join(root, "Action"))  # empty category pruned

    def test_user_files_preserve_folder(self, p, idx, log, tmp_path):
        root = str(tmp_path)
        write(os.path.join(root, "Heat (1995)", "Heat (1995).strm"))
        write(os.path.join(root, "Heat (1995)", "poster.jpg"), "img")
        p._cleanup_owned_movies(root, idx, False, log)
        assert os.path.exists(os.path.join(root, "Heat (1995)", "poster.jpg"))

    def test_dry_run_deletes_nothing(self, p, idx, log, tmp_path):
        root = str(tmp_path)
        strm = os.path.join(root, "Heat (1995)", "Heat (1995).strm")
        write(strm)
        res = p._cleanup_owned_movies(root, idx, True, log)
        assert res["deleted_strm"] == 1  # counted as would-delete
        assert os.path.exists(strm)

    def test_missing_root_ok(self, p, idx, log, tmp_path):
        res = p._cleanup_owned_movies(str(tmp_path / "nope"), idx, False, log)
        assert res["deleted_strm"] == 0 and res["errors"] == 0


class TestCleanupOwnedSeries:
    def seed_beef(self, root):
        write(os.path.join(root, "BEEF (2023)", "Season 02", "BEEF - S02E07 - Episode 7.strm"))
        write(os.path.join(root, "BEEF (2023)", "Season 02", "BEEF - S02E07 - Episode 7.nfo"))
        write(os.path.join(root, "BEEF (2023)", "Season 02", "BEEF - S02E08 - Episode 8.strm"))
        write(os.path.join(root, "BEEF (2023)", "tvshow.nfo"), "<tvshow/>")

    def test_owned_episode_deleted_others_kept(self, p, idx, log, tmp_path):
        root = str(tmp_path)
        self.seed_beef(root)
        res = p._cleanup_owned_series(root, idx, False, log)
        assert res["deleted_strm"] == 1
        assert res["deleted_nfo"] == 1
        assert not os.path.exists(os.path.join(root, "BEEF (2023)", "Season 02", "BEEF - S02E07 - Episode 7.strm"))
        assert os.path.exists(os.path.join(root, "BEEF (2023)", "Season 02", "BEEF - S02E08 - Episode 8.strm"))
        assert os.path.exists(os.path.join(root, "BEEF (2023)", "tvshow.nfo"))  # episodes remain

    def test_last_episode_removes_show_folder_and_tvshow_nfo(self, p, log, tmp_path):
        root = str(tmp_path)
        i = EmbyIndex()
        i.add_episode("BEEF", 2, 7)
        i.add_episode("BEEF", 2, 8)
        self.seed_beef(root)
        res = p._cleanup_owned_series(root, i, False, log)
        assert res["deleted_strm"] == 2
        assert not os.path.exists(os.path.join(root, "BEEF (2023)"))

    def test_series_matched_via_folder_year_suffix(self, p, idx, log, tmp_path):
        # Folder says 'BEEF (2023)', index says 'BEEF' — must match
        root = str(tmp_path)
        write(os.path.join(root, "BEEF (2023)", "Season 02", "BEEF - S02E07.strm"))
        res = p._cleanup_owned_series(root, idx, False, log)
        assert res["deleted_strm"] == 1

    def test_dry_run_deletes_nothing(self, p, idx, log, tmp_path):
        root = str(tmp_path)
        self.seed_beef(root)
        res = p._cleanup_owned_series(root, idx, True, log)
        assert res["deleted_strm"] == 1
        assert os.path.exists(os.path.join(root, "BEEF (2023)", "Season 02", "BEEF - S02E07 - Episode 7.strm"))

    def test_wrong_year_folder_not_deleted(self, p, log, tmp_path):
        # Index owns The Office (2005) S01E01; a folder for The Office (2001)
        # must NOT be deleted — the year on the folder disambiguates the remake.
        root = str(tmp_path)
        i = EmbyIndex()
        i.add_episode("The Office", 1, 1, series_year=2005)
        strm = os.path.join(root, "The Office (2001)", "Season 01",
                            "The Office - S01E01 - Downsize.strm")
        write(strm)
        res = p._cleanup_owned_series(root, i, False, log)
        assert res["deleted_strm"] == 0
        assert os.path.exists(strm)

    def test_matching_year_folder_deleted(self, p, log, tmp_path):
        # Companion: same index, but the folder year matches → deleted.
        root = str(tmp_path)
        i = EmbyIndex()
        i.add_episode("The Office", 1, 1, series_year=2005)
        strm = os.path.join(root, "The Office (2005)", "Season 01",
                            "The Office - S01E01 - Pilot.strm")
        write(strm)
        res = p._cleanup_owned_series(root, i, False, log)
        assert res["deleted_strm"] == 1
        assert not os.path.exists(strm)


class TestCleanupOwnedAction:
    def test_none_index_refuses(self, p, log, tmp_path):
        settings = {"root_folder": str(tmp_path), "series_root_folder": str(tmp_path)}
        res = p._cleanup_owned(settings, log, emby_index=None)
        assert res["status"] == "error"

    def test_happy_path(self, p, idx, log, tmp_path):
        movies = tmp_path / "Movies"
        series = tmp_path / "Series"
        write(str(movies / "Heat (1995)" / "Heat (1995).strm"))
        write(str(series / "BEEF (2023)" / "Season 02" / "BEEF - S02E07.strm"))
        settings = {
            "root_folder": str(movies),
            "series_root_folder": str(series),
            "emby_remove_owned": True,
        }
        res = p._cleanup_owned(settings, log, emby_index=idx)
        assert res["status"] == "ok"
        assert res["deleted_strm"] == 2

    def test_remove_owned_off_is_noop(self, p, idx, log, tmp_path):
        movies = tmp_path / "Movies"
        strm = movies / "Heat (1995)" / "Heat (1995).strm"
        write(str(strm))
        settings = {
            "root_folder": str(movies),
            "series_root_folder": str(tmp_path / "Series"),
            "emby_remove_owned": False,
        }
        res = p._cleanup_owned(settings, log, emby_index=idx)
        assert res["status"] == "ok"
        assert strm.exists()
