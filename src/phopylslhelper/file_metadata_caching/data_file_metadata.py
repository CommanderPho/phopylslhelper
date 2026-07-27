import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from copy import deepcopy

import pandas as pd
from attrs import define

from phopylslhelper.file_metadata_caching.file_metadata import BaseFileMetadataParser

# Import MNE dependencies (lazy XDF import in methods to avoid circular deps)
try:
    from mne.io import read_raw
    MNE_AVAILABLE = True
except ImportError:
    MNE_AVAILABLE = False

from concurrent.futures import ThreadPoolExecutor, as_completed


_CACHE_FILENAME = "_data_file_metadata_cache.csv"


def _normalize_src_file_key(path_value: Any) -> str:
    """Resolve a path-like value to a stable cache lookup key."""
    try:
        path = Path(path_value)
        # Absolute paths are already stable; skip expensive Path.resolve() (costly on Dropbox/network).
        if path.is_absolute():
            return str(path)
        return str(path.resolve())
    except Exception:
        return str(path_value)


@define(slots=False)
class DataFileMetadataParser(BaseFileMetadataParser):
    """
    Parses data file folders (.xdf, .fif) and extracts metadata including datetime from files.
    Provides disk-persisted caching to speed up subsequent runs.
    Supports parallel processing for improved performance.
    
    Usage:
        from phopylslhelper.file_metadata_caching.data_file_metadata import DataFileMetadataParser
        
        folder_path = Path(r"E:/Dropbox (Personal)/Databases/UnparsedData/EmotivEpocX_EEGRecordings/fif")
        df = DataFileMetadataParser.build_file_comparison_df_cached(
            recording_files=list(folder_path.glob("*.fif")),
            cache_path=folder_path / "_data_file_metadata_cache.csv",
            max_workers=3
        )
        print(df)
    """
    
    @classmethod
    def extract_datetime_from_filename(cls, filename: str) -> Optional[datetime]:
        """
        Extract datetime from filename.
        
        Examples:
            '20250730-195857-Epoc X Motion-raw.fif' -> datetime(2025, 7, 30, 19, 58, 57)
            'LabRecorder_Apogee_2025-11-04T105347.435Z_eeg.xdf' -> datetime(2025, 11, 4, 10, 53, 47)
        """
        candidates = re.findall(r'\d{4}[-_]?\d{2}[-_]?\d{2}[ T_-]?\d{2}[:\-]?\d{2}[:\-]?\d{2}', filename)
        for cand in candidates:
            normalized = cand.replace("_", "T").replace(" ", "T")
            for fmt in [
                "%Y-%m-%dT%H-%M-%S",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H%M%S",
                "%Y%m%dT%H%M%S",
                "%Y%m%d_%H%M%S",
                "%Y%m%d-%H%M%S",
                "%Y%m%d%H%M%S"
            ]:
                try:
                    return datetime.strptime(normalized, fmt)
                except ValueError:
                    continue
        return None
    
    
    @classmethod
    def extract_file_metadata(cls, file_path: Path) -> Optional[Dict[str, Any]]:
        """
        Extract metadata from a data file (.xdf or .fif).
        
        Returns:
            Dictionary with basic metadata:
            - start_datetime: Recording start datetime (UTC timezone-aware)
            - file_size: File size in bytes
            - Or None if extraction fails
            
        Note: Additional metadata (duration, num_streams, etc.) can be added incrementally
        and will be cached. This method only extracts what's available on lightweight load.
        """
        if not file_path.exists():
            return None
        
        try:
            file_ext = file_path.suffix.lower()
            
            # Get file stat metadata
            file_stat = file_path.stat()
            file_size = file_stat.st_size
            
            # Extract datetime based on file type
            if file_ext == '.xdf':
                try:
                    from phopymnehelper.xdf_files import LabRecorderXDF
                except ImportError:
                    LabRecorderXDF = None

                if LabRecorderXDF is None:
                    # Fallback to filename parsing
                    start_datetime = cls.extract_datetime_from_filename(file_path.name)
                    if start_datetime is None:
                        return None
                    start_datetime = start_datetime.replace(tzinfo=timezone.utc) if start_datetime.tzinfo is None else start_datetime.astimezone(timezone.utc)
                else:
                    # Use LabRecorderXDF for lightweight datetime extraction
                    lab_recorder_xdf = LabRecorderXDF.init_basic_from_lab_recorder_xdf_file(a_xdf_file=file_path, debug_print=False)
                    start_datetime = lab_recorder_xdf.file_datetime
                    
                    # Fallback to filename parsing if file_datetime is None
                    if start_datetime is None:
                        start_datetime = cls.extract_datetime_from_filename(file_path.name)
                        if start_datetime is None:
                            return None
                        start_datetime = start_datetime.replace(tzinfo=timezone.utc) if start_datetime.tzinfo is None else start_datetime.astimezone(timezone.utc)
                    else:
                        # Ensure UTC timezone
                        if start_datetime.tzinfo is None:
                            start_datetime = start_datetime.replace(tzinfo=timezone.utc)
                        else:
                            start_datetime = start_datetime.astimezone(timezone.utc)
                            
            elif file_ext == '.fif':
                duration = 0.0
                if not MNE_AVAILABLE:
                    # Fallback to filename parsing
                    start_datetime = cls.extract_datetime_from_filename(file_path.name)
                    if start_datetime is None:
                        return None
                    start_datetime = start_datetime.replace(tzinfo=timezone.utc) if start_datetime.tzinfo is None else start_datetime.astimezone(timezone.utc)
                else:
                    # Use MNE read_raw (preload=False for lightweight load)
                    raw = read_raw(file_path, preload=False)
                    meas_datetime = raw.info.get('meas_date', None)
                    
                    # Extract duration from raw.times[-1] (last timestamp in seconds)
                    if len(raw.times) > 0:
                        duration = float(raw.times[-1])
                    
                    if meas_datetime is None:
                        # Fallback to filename parsing
                        start_datetime = cls.extract_datetime_from_filename(file_path.name)
                        if start_datetime is None:
                            return None
                        start_datetime = start_datetime.replace(tzinfo=timezone.utc) if start_datetime.tzinfo is None else start_datetime.astimezone(timezone.utc)
                    else:
                        # Handle tuple format (timestamp, microseconds) or datetime
                        if isinstance(meas_datetime, tuple):
                            start_datetime = datetime.fromtimestamp(meas_datetime[0], tz=timezone.utc)
                        elif hasattr(meas_datetime, 'timestamp'):
                            start_datetime = meas_datetime
                            if start_datetime.tzinfo is None:
                                start_datetime = start_datetime.replace(tzinfo=timezone.utc)
                            else:
                                start_datetime = start_datetime.astimezone(timezone.utc)
                        else:
                            # Fallback
                            start_datetime = cls.extract_datetime_from_filename(file_path.name)
                            if start_datetime is None:
                                return None
                            start_datetime = start_datetime.replace(tzinfo=timezone.utc) if start_datetime.tzinfo is None else start_datetime.astimezone(timezone.utc)
            else:
                # Unsupported file type
                return None
            
            # Build result dict with duration if available
            result = {
                'start_datetime': start_datetime,
                'file_size': file_size,
            }
            
            # Add duration (for .fif files: extracted from raw.times[-1], for .xdf files: 0.0 for now)
            if file_ext == '.fif':
                result['duration'] = duration
            elif file_ext == '.xdf':
                # For XDF files, duration is not easily available without full load
                # Set to 0 for now - can be added incrementally later
                result['duration'] = 0.0
            
            return result
            
        except Exception as e:
            # Silently fail - return None to skip this file
            return None
    
    
    @classmethod
    def _merge_and_save_comparison_cache(cls, result_df: pd.DataFrame, cache_path: Path) -> None:
        """Merge ``result_df`` into the on-disk cache without dropping unrelated entries."""
        if result_df.empty:
            return
        existing = cls.load_cache(cache_path, datetime_columns=['start_datetime', 'meas_datetime'])
        if existing.empty or 'src_file' not in existing.columns:
            cls.save_cache(result_df, cache_path)
            return
        current_keys = {_normalize_src_file_key(p) for p in result_df['src_file'].tolist()}
        existing = existing.copy()
        existing['_src_key'] = existing['src_file'].map(_normalize_src_file_key)
        keep = existing[~existing['_src_key'].isin(current_keys)].drop(columns=['_src_key'])
        if keep.empty:
            merged = result_df
        else:
            merged = pd.concat([keep, result_df], ignore_index=True)
        if '_src_key' in merged.columns:
            merged = merged.drop(columns=['_src_key'])
        cls.save_cache(merged, cache_path)


    @classmethod
    def _finalize_comparison_df(cls, rows: List[Dict[str, Any]]) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame.from_records(rows)
        datetime_col_names = ['start_t', 'ctime', 'mtime']
        for col_name in datetime_col_names:
            if col_name in df.columns:
                if pd.api.types.is_numeric_dtype(df[col_name]):
                    df[col_name] = pd.to_datetime(df[col_name], unit='s')
                else:
                    df[col_name] = pd.to_datetime(df[col_name])
        ## END for col_name in datetime_col_names....

        if 'start_datetime' in df.columns:
            df['start_datetime'] = pd.to_datetime(df['start_datetime'])
        if 'meas_datetime' in df.columns:
            df['meas_datetime'] = pd.to_datetime(df['meas_datetime'])
        df = df.sort_values(['meas_datetime', 'ctime', 'mtime', 'size', 'src_file'], ignore_index=True, inplace=False, ascending=False, na_position='last')
        df = df.drop_duplicates(subset=['src_file', 'meas_datetime', 'start_t'], inplace=False, ignore_index=True, keep='first')
        return df


    @classmethod
    def _build_file_comparison_df_cached_for_group(cls, recording_files: List[Path], cache_path: Path, max_workers: int = 3, use_cache: bool = True, force_rebuild: bool = False) -> pd.DataFrame:
        """Build comparison DF for files that share one cache file; merge-save without wiping unrelated rows."""
        if not recording_files:
            return pd.DataFrame()

        cached_df = pd.DataFrame()
        if use_cache and (not force_rebuild):
            cached_df = cls.load_cache(cache_path, datetime_columns=['start_datetime', 'meas_datetime'])

        cached_by_path: Dict[str, Any] = {}
        if not cached_df.empty and 'src_file' in cached_df.columns:
            for _, row in cached_df.iterrows():
                cached_by_path[_normalize_src_file_key(row['src_file'])] = row
            ## END for _, row in cached_df.iterrows()....

        metadata_key_dict = {'ctime': 'st_ctime', 'size': 'st_size', 'mtime': 'st_mtime'}

        def _process_single_file(idx_file_tuple: Tuple[int, Path]) -> Tuple[int, Optional[Dict], bool]:
            """Return (file_idx, result_dict_or_None, was_cache_hit)."""
            file_idx, a_file = idx_file_tuple
            if not a_file.exists():
                return (file_idx, None, False)

            resolved_path = _normalize_src_file_key(a_file)

            if use_cache and not force_rebuild and resolved_path in cached_by_path:
                cached_row = cached_by_path[resolved_path]
                if not cls.is_file_changed(a_file, cached_row):
                    cached_entry = cached_row.to_dict()
                    current_metadata = cls.get_file_metadata(a_file)
                    cached_entry['cache_file_size'] = current_metadata['file_size']
                    cached_entry['cache_file_mtime'] = current_metadata['file_mtime']
                    file_stat = a_file.stat()
                    for col_name, stat_key in metadata_key_dict.items():
                        cached_entry[col_name] = getattr(file_stat, stat_key)
                    ## END for col_name, stat_key in metadata_key_dict.items()....

                    if 'start_datetime' in cached_entry:
                        if 'start_t' not in cached_entry or pd.isna(cached_entry.get('start_t')):
                            start_dt = cached_entry['start_datetime']
                            if isinstance(start_dt, datetime):
                                cached_entry['start_t'] = start_dt.timestamp()
                            else:
                                cached_entry['start_t'] = pd.to_datetime(start_dt).timestamp()
                        if 'meas_datetime' not in cached_entry or pd.isna(cached_entry.get('meas_datetime')):
                            cached_entry['meas_datetime'] = cached_entry['start_datetime']
                    cached_entry['src_file_name'] = a_file.stem
                    cached_entry['src_file'] = resolved_path
                    return (file_idx, cached_entry, True)

            try:
                metadata = cls.extract_file_metadata(a_file)
                if metadata is None:
                    return (file_idx, None, False)

                start_datetime = metadata['start_datetime']
                start_time = start_datetime.timestamp() if hasattr(start_datetime, 'timestamp') else start_datetime[0]
                file_stat = a_file.stat()
                file_metadata = cls.get_file_metadata(a_file)
                file_metadata_dict = {col_name: getattr(file_stat, stat_key) for col_name, stat_key in metadata_key_dict.items()}
                result_dict = {
                    'src_file_name': a_file.stem,
                    'src_file': resolved_path,
                    'start_datetime': start_datetime,
                    'start_t': start_time,
                    'meas_datetime': start_datetime,
                    'file_size': metadata['file_size'],
                    'size': metadata['file_size'],
                    **file_metadata_dict,
                    'cache_file_size': file_metadata['file_size'],
                    'cache_file_mtime': file_metadata['file_mtime'],
                }
                return (file_idx, result_dict, False)
            except Exception as e:
                print(f'failed to load file: "{a_file}" with error: {e}. Skipping.')
                return (file_idx, None, False)

        results: List[Optional[Dict]] = [None] * len(recording_files)
        n_cache_misses = 0
        effective_workers = min(max_workers, len(recording_files)) if recording_files else 1
        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            future_to_idx = {executor.submit(_process_single_file, (idx, file)): idx for idx, file in enumerate(recording_files)}
            for future in as_completed(future_to_idx):
                try:
                    file_idx, result_dict, was_cache_hit = future.result()
                    results[file_idx] = result_dict
                    if result_dict is not None and not was_cache_hit:
                        n_cache_misses += 1
                except Exception as e:
                    idx = future_to_idx[future]
                    print(f'EXCEPTION processing file {idx}: {e}')
                    results[idx] = None
            ## END for future in as_completed(future_to_idx)....

        rows = [r for r in results if r is not None]
        # Empty results must not delete an existing cache (transient parse failures).
        if not rows:
            return pd.DataFrame()

        df = cls._finalize_comparison_df(rows)
        # Skip rewrite when every requested file was an unchanged cache hit.
        if use_cache and (n_cache_misses > 0 or force_rebuild):
            cls._merge_and_save_comparison_cache(df, cache_path)
        return df


    @classmethod
    def build_file_comparison_df_cached(cls, recording_files: List[Path], cache_path: Optional[Path] = None, max_workers: int = 3, use_cache: bool = True, force_rebuild: bool = False) -> pd.DataFrame:
        """
        Build a DataFrame with file metadata, using disk-persisted cache for speed.
        Processes files in parallel for improved performance.
        
        This is a cache-backed version of HistoricalData.build_file_comparison_df that
        persists results to disk, allowing fast subsequent runs.
        
        Args:
            recording_files: List of Path objects to recording files (.xdf or .fif)
            cache_path: Optional explicit cache CSV. If None, uses one cache per parent
                directory (``{parent}/_data_file_metadata_cache.csv``).
            max_workers: Maximum number of parallel threads (default: 3)
            use_cache: If True, use cached metadata for unchanged files (default: True)
            force_rebuild: If True, ignore cache and rebuild from scratch (default: False)
            
        Returns:
            DataFrame with columns:
            - src_file: Full path to file
            - src_file_name: Filename without extension
            - start_datetime: Recording start datetime (UTC timezone-aware)
            - start_t: Timestamp (seconds since epoch)
            - meas_datetime: Same as start_datetime (for compatibility)
            - file_size: File size in bytes
            - size: Same as file_size (for compatibility)
            - ctime: File creation time
            - mtime: File modification time
            - cache_file_size: File size used for cache validation
            - cache_file_mtime: File modification time used for cache validation
            
        DataFrame is sorted by meas_datetime (descending, most recent first).
        """
        if not recording_files:
            return pd.DataFrame()

        paths = [Path(p) for p in recording_files]
        if cache_path is not None:
            return cls._build_file_comparison_df_cached_for_group(paths, Path(cache_path), max_workers=max_workers, use_cache=use_cache, force_rebuild=force_rebuild)

        by_parent: Dict[Path, List[Path]] = defaultdict(list)
        for path in paths:
            by_parent[path.parent].append(path)
        ## END for path in paths....

        group_dfs: List[pd.DataFrame] = []
        for parent, group_files in by_parent.items():
            group_cache = parent / _CACHE_FILENAME
            group_df = cls._build_file_comparison_df_cached_for_group(group_files, group_cache, max_workers=max_workers, use_cache=use_cache, force_rebuild=force_rebuild)
            if not group_df.empty:
                group_dfs.append(group_df)
        ## END for parent, group_files in by_parent.items()....

        if not group_dfs:
            return pd.DataFrame()
        df = pd.concat(group_dfs, ignore_index=True)
        df = df.sort_values(['meas_datetime', 'ctime', 'mtime', 'size', 'src_file'], ignore_index=True, inplace=False, ascending=False, na_position='last')
        return df.drop_duplicates(subset=['src_file', 'meas_datetime', 'start_t'], inplace=False, ignore_index=True, keep='first')


    @classmethod
    def parse_folder(cls, folder_path: Path, use_cache: bool = True, force_rebuild: bool = False, **kwargs) -> pd.DataFrame:
        return cls.parse_data_folder(folder_path, use_cache=use_cache, force_rebuild=force_rebuild, **kwargs)


    @classmethod
    def parse_data_folder(cls, folder_path: Path, data_extensions: List[str] = ['.xdf', '.fif'], use_cache: bool = True, force_rebuild: bool = False) -> pd.DataFrame:
        """
        Parse all data files in a folder and return a DataFrame with metadata.
        Uses caching to speed up subsequent runs by only processing new or modified files.
        
        This method is similar to VideoMetadataParser.parse_video_folder but configured for data files.
        
        Args:
            folder_path: Path to folder containing data files
            data_extensions: List of data file extensions to process (default: ['.xdf', '.fif'])
            use_cache: If True, use cached metadata for unchanged files (default: True)
            force_rebuild: If True, ignore cache and rebuild from scratch (default: False)
            
        Returns:
            DataFrame with columns:
            - data_file_path: Full path to data file
            - start_datetime: Recording start datetime (UTC timezone-aware)
            - end_datetime: Calculated end datetime (start + duration)
            - duration: Duration in seconds (0.0 for XDF files, extracted for FIF files)
            - file_size: File size in bytes
            - cache_file_size: File size used for cache validation
            - cache_file_mtime: File modification time used for cache validation
            
        DataFrame is sorted by start_datetime.
        """
        return cls.parse_filesystem_folder(
            folder_path=folder_path,
            included_file_extensions=data_extensions,
            use_cache=use_cache,
            force_rebuild=force_rebuild,
            cache_filename="_data_file_metadata_cache.csv",
            path_column="data_file_path",
            start_datetime_column="start_datetime",
            end_datetime_column="end_datetime",
            duration_metadata_key="duration"
        )


__all__ = ['DataFileMetadataParser']
