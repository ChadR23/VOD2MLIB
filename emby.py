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
