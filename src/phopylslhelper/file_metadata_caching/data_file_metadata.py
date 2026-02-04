import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from copy import deepcopy

import pandas as pd
from attrs import define

from phopylslhelper.file_metadata_caching.file_metadata import BaseFileMetadataParser

# Import MNE and XDF dependencies (lazy import in methods to avoid circular deps)
try:
    from mne.io import read_raw
    MNE_AVAILABLE = True
except ImportError:
    MNE_AVAILABLE = False

try:
    from phoofflineeeganalysis.analysis.xdf_files import LabRecorderXDF
    XDF_AVAILABLE = True
except ImportError:
    XDF_AVAILABLE = False

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed


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
                if not XDF_AVAILABLE:
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
            
            return {
                'start_datetime': start_datetime,
                'file_size': file_size,
            }
            
        except Exception as e:
            # Silently fail - return None to skip this file
            return None
    
    
    @classmethod
    def build_file_comparison_df_cached(cls, recording_files: List[Path], cache_path: Optional[Path] = None, max_workers: int = 3, use_cache: bool = True, force_rebuild: bool = False) -> pd.DataFrame:
        """
        Build a DataFrame with file metadata, using disk-persisted cache for speed.
        Processes files in parallel for improved performance.
        
        This is a cache-backed version of HistoricalData.build_file_comparison_df that
        persists results to disk, allowing fast subsequent runs.
        
        Args:
            recording_files: List of Path objects to recording files (.xdf or .fif)
            cache_path: Path to cache CSV file. If None, uses first file's parent / "_data_file_metadata_cache.csv"
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
        
        # Determine cache path
        if cache_path is None:
            # Use first file's parent directory
            cache_path = recording_files[0].parent / "_data_file_metadata_cache.csv"
        cache_path = Path(cache_path)
        
        # Load existing cache if enabled and not forcing rebuild
        cached_df = pd.DataFrame()
        if use_cache and not force_rebuild:
            cached_df = cls.load_cache(cache_path, datetime_columns=['start_datetime'])
        
        # Build dictionary of cached entries by file path
        cached_by_path = {}
        if not cached_df.empty and 'src_file' in cached_df.columns:
            for idx, row in cached_df.iterrows():
                file_path_str = row['src_file']
                cached_by_path[file_path_str] = row
        
        metadata_key_dict = {'ctime': 'st_ctime', 'size': 'st_size', 'mtime': 'st_mtime'}
        
        def _process_single_file(idx_file_tuple: Tuple[int, Path]) -> Tuple[int, Optional[Dict]]:
            """Process a single file and return its metadata. Thread-safe worker function."""
            file_idx, a_file = idx_file_tuple
            if not a_file.exists():
                return (file_idx, None)
            
            resolved_path = str(a_file.resolve())
            
            # Check if we can use cached entry
            use_cached = False
            if use_cache and not force_rebuild and resolved_path in cached_by_path:
                cached_row = cached_by_path[resolved_path]
                if not cls.is_file_changed(a_file, cached_row):
                    # Use cached entry, but update cache metadata and file stat
                    cached_entry = cached_row.to_dict()
                    current_metadata = cls.get_file_metadata(a_file)
                    cached_entry['cache_file_size'] = current_metadata['file_size']
                    cached_entry['cache_file_mtime'] = current_metadata['file_mtime']
                    
                    # Update file stat columns
                    file_stat = a_file.stat()
                    for col_name, stat_key in metadata_key_dict.items():
                        cached_entry[col_name] = getattr(file_stat, stat_key)
                    
                    # Ensure datetime columns are present
                    if 'start_datetime' in cached_entry:
                        if 'start_t' not in cached_entry:
                            start_dt = cached_entry['start_datetime']
                            if isinstance(start_dt, datetime):
                                cached_entry['start_t'] = start_dt.timestamp()
                            else:
                                cached_entry['start_t'] = pd.to_datetime(start_dt).timestamp()
                        if 'meas_datetime' not in cached_entry:
                            cached_entry['meas_datetime'] = cached_entry['start_datetime']
                    
                    cached_entry['src_file_name'] = a_file.stem
                    cached_entry['src_file'] = resolved_path
                    return (file_idx, cached_entry)
            
            # Cache miss or file changed - extract metadata
            try:
                metadata = cls.extract_file_metadata(a_file)
                if metadata is None:
                    return (file_idx, None)
                
                start_datetime = metadata['start_datetime']
                start_time = start_datetime.timestamp() if hasattr(start_datetime, 'timestamp') else start_datetime[0]
                
                # Get file stat metadata
                file_stat = a_file.stat()
                file_metadata = cls.get_file_metadata(a_file)
                file_metadata_dict = {col_name: getattr(file_stat, stat_key) for col_name, stat_key in metadata_key_dict.items()}
                
                result_dict = {
                    'src_file_name': a_file.stem,
                    'src_file': resolved_path,
                    'start_datetime': start_datetime,
                    'start_t': start_time,
                    'meas_datetime': start_datetime,  # For compatibility
                    'file_size': metadata['file_size'],
                    'size': metadata['file_size'],  # For compatibility
                    **file_metadata_dict,
                    'cache_file_size': file_metadata['file_size'],
                    'cache_file_mtime': file_metadata['file_mtime'],
                }
                return (file_idx, result_dict)
                
            except Exception as e:
                print(f'failed to load file: "{a_file}" with error: {e}. Skipping.')
                return (file_idx, None)
        
        # Parallel processing using ThreadPoolExecutor
        results = [None] * len(recording_files)
        effective_workers = min(max_workers, len(recording_files)) if recording_files else 1
        
        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            future_to_idx = {executor.submit(_process_single_file, (idx, file)): idx for idx, file in enumerate(recording_files)}
            for future in as_completed(future_to_idx):
                try:
                    file_idx, result_dict = future.result()
                    results[file_idx] = result_dict
                except Exception as e:
                    idx = future_to_idx[future]
                    print(f'EXCEPTION processing file {idx}: {e}')
                    results[idx] = None
        
        # Filter out failed files (None results)
        _out_df = [r for r in results if r is not None]
        
        if not _out_df:
            # No valid files found - clear cache if it exists
            if cache_path.exists() and use_cache:
                try:
                    cache_path.unlink()
                except Exception:
                    pass
            return pd.DataFrame()
        
        # Create DataFrame
        df = pd.DataFrame.from_records(_out_df)
        
        # Convert datetime columns
        datetime_col_names = ['start_t', 'ctime', 'mtime']
        for col_name in datetime_col_names:
            if col_name in df.columns:
                df[col_name] = pd.to_datetime(df[col_name], unit='s')
        
        # Ensure start_datetime and meas_datetime are datetime objects
        if 'start_datetime' in df.columns:
            df['start_datetime'] = pd.to_datetime(df['start_datetime'])
        if 'meas_datetime' in df.columns:
            df['meas_datetime'] = pd.to_datetime(df['meas_datetime'])
        
        # Sort by meas_datetime (descending, most recent first)
        df = df.sort_values(['meas_datetime', 'ctime', 'mtime', 'size', 'src_file'], ignore_index=True, inplace=False, ascending=False, na_position='last')
        
        # Remove duplicates
        df = df.drop_duplicates(subset=['src_file', 'meas_datetime', 'start_t'], inplace=False, ignore_index=True, keep='first')
        
        # Save updated cache
        if use_cache:
            cls.save_cache(df, cache_path)
        
        return df


__all__ = ['DataFileMetadataParser']
