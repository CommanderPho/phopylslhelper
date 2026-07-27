"""Unit tests for DataFileMetadataParser disk cache behavior."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
import pytest

from phopylslhelper.file_metadata_caching.data_file_metadata import DataFileMetadataParser, _CACHE_FILENAME


def _touch_file(path: Path, content: bytes = b"x") -> Path:
    path.write_bytes(content)
    return path


def _stub_extract(file_path: Path) -> Optional[Dict[str, Any]]:
    return {
        'start_datetime': datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        'file_size': file_path.stat().st_size,
        'duration': 0.0,
    }


@pytest.fixture
def stub_extract(monkeypatch):
    calls = {'n': 0, 'paths': []}

    def _counting_extract(file_path: Path) -> Optional[Dict[str, Any]]:
        calls['n'] += 1
        calls['paths'].append(Path(file_path).resolve())
        return _stub_extract(file_path)

    monkeypatch.setattr(DataFileMetadataParser, 'extract_file_metadata', classmethod(lambda cls, p: _counting_extract(p)))
    return calls


def test_cache_hit_skips_extract_on_second_call(tmp_path: Path, stub_extract):
    files = [_touch_file(tmp_path / f"rec_{i}.xdf", content=b"abc") for i in range(3)]
    df1 = DataFileMetadataParser.build_file_comparison_df_cached(files, use_cache=True, force_rebuild=False, max_workers=1)
    assert len(df1) == 3
    assert stub_extract['n'] == 3

    stub_extract['n'] = 0
    stub_extract['paths'].clear()
    df2 = DataFileMetadataParser.build_file_comparison_df_cached(files, use_cache=True, force_rebuild=False, max_workers=1)
    assert len(df2) == 3
    assert stub_extract['n'] == 0
    assert (tmp_path / _CACHE_FILENAME).is_file()


def test_mtime_change_forces_reextract(tmp_path: Path, stub_extract):
    f0 = _touch_file(tmp_path / "a.xdf", content=b"aaa")
    f1 = _touch_file(tmp_path / "b.xdf", content=b"bbb")
    DataFileMetadataParser.build_file_comparison_df_cached([f0, f1], use_cache=True, max_workers=1)
    assert stub_extract['n'] == 2

    stub_extract['n'] = 0
    stub_extract['paths'].clear()
    f0.write_bytes(b"aaaa")  # size change invalidates cache
    DataFileMetadataParser.build_file_comparison_df_cached([f0, f1], use_cache=True, max_workers=1)
    assert stub_extract['n'] == 1
    assert stub_extract['paths'][0] == f0.resolve()


def test_subset_call_preserves_other_cache_rows(tmp_path: Path, stub_extract):
    files = [_touch_file(tmp_path / f"rec_{i}.xdf", content=bytes([i]) * 4) for i in range(5)]
    DataFileMetadataParser.build_file_comparison_df_cached(files, use_cache=True, max_workers=1)
    stub_extract['n'] = 0

    subset = files[:2]
    df_subset = DataFileMetadataParser.build_file_comparison_df_cached(subset, use_cache=True, max_workers=1)
    assert len(df_subset) == 2
    assert stub_extract['n'] == 0

    cached = DataFileMetadataParser.load_cache(tmp_path / _CACHE_FILENAME, datetime_columns=['start_datetime'])
    assert len(cached) == 5


def test_full_cache_hit_skips_cache_rewrite(tmp_path: Path, stub_extract, monkeypatch):
    files = [_touch_file(tmp_path / f"rec_{i}.xdf", content=b"abc") for i in range(3)]
    DataFileMetadataParser.build_file_comparison_df_cached(files, use_cache=True, max_workers=1)
    cache_path = tmp_path / _CACHE_FILENAME
    mtime_before = cache_path.stat().st_mtime
    save_calls = {'n': 0}
    original_merge = DataFileMetadataParser._merge_and_save_comparison_cache

    def _counting_merge(cls, result_df, path):
        save_calls['n'] += 1
        return original_merge(result_df, path)

    monkeypatch.setattr(DataFileMetadataParser, '_merge_and_save_comparison_cache', classmethod(_counting_merge))
    stub_extract['n'] = 0
    df2 = DataFileMetadataParser.build_file_comparison_df_cached(files, use_cache=True, max_workers=1)
    assert len(df2) == 3
    assert stub_extract['n'] == 0
    assert save_calls['n'] == 0
    assert cache_path.stat().st_mtime == mtime_before


def test_empty_extract_does_not_delete_cache(tmp_path: Path, monkeypatch):
    files = [_touch_file(tmp_path / f"rec_{i}.xdf", content=b"zz") for i in range(2)]
    monkeypatch.setattr(DataFileMetadataParser, 'extract_file_metadata', classmethod(lambda cls, p: _stub_extract(p)))
    DataFileMetadataParser.build_file_comparison_df_cached(files, use_cache=True, max_workers=1)
    cache_path = tmp_path / _CACHE_FILENAME
    assert cache_path.is_file()

    monkeypatch.setattr(DataFileMetadataParser, 'extract_file_metadata', classmethod(lambda cls, p: None))
    # Force rebuild so extract is called and returns None for all
    df = DataFileMetadataParser.build_file_comparison_df_cached(files, use_cache=True, force_rebuild=True, max_workers=1)
    assert df.empty
    assert cache_path.is_file()
    cached = DataFileMetadataParser.load_cache(cache_path, datetime_columns=['start_datetime'])
    assert len(cached) == 2


def test_force_rebuild_reextracts_unchanged_files(tmp_path: Path, stub_extract):
    files = [_touch_file(tmp_path / f"rec_{i}.xdf", content=b"ok") for i in range(2)]
    DataFileMetadataParser.build_file_comparison_df_cached(files, use_cache=True, max_workers=1)
    stub_extract['n'] = 0
    DataFileMetadataParser.build_file_comparison_df_cached(files, use_cache=True, force_rebuild=True, max_workers=1)
    assert stub_extract['n'] == 2


def test_per_parent_cache_files(tmp_path: Path, stub_extract):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    files = [
        _touch_file(dir_a / "one.xdf", content=b"1"),
        _touch_file(dir_b / "two.xdf", content=b"2"),
    ]
    df = DataFileMetadataParser.build_file_comparison_df_cached(files, use_cache=True, max_workers=1)
    assert len(df) == 2
    assert (dir_a / _CACHE_FILENAME).is_file()
    assert (dir_b / _CACHE_FILENAME).is_file()


def test_is_file_changed_treats_nan_as_changed(tmp_path: Path):
    path = _touch_file(tmp_path / "z.xdf", content=b"data")
    row = pd.Series({'cache_file_size': float('nan'), 'cache_file_mtime': 1.0})
    assert DataFileMetadataParser.is_file_changed(path, row) is True
    row_ok = pd.Series({'cache_file_size': path.stat().st_size, 'cache_file_mtime': path.stat().st_mtime})
    assert DataFileMetadataParser.is_file_changed(path, row_ok) is False
