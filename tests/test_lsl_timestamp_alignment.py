"""Unit tests for lsl_stream_timestamps_to_unix_seconds (XDF timestamp alignment)."""

import unittest
from datetime import datetime, timezone

import numpy as np

from phopylslhelper.general_helpers import GeneralHelpers
from phopylslhelper.easy_time_sync import EasyTimeSyncParsingMixin


def _make_stream_with_sync(stream_start_datetime: datetime, lsl_offset_seconds: float) -> dict:
    """Build a minimal pyxdf-style stream dict carrying phopylslhelper sync metadata in its desc."""
    return {
        'info': {
            'desc': [{
                'phopylslhelper': [{
                    'stream_start_datetime': [GeneralHelpers.readable_dt_str(stream_start_datetime)],
                    'stream_start_lsl_local_offset_seconds': [str(lsl_offset_seconds)],
                }]
            }]
        },
    }


class TestLslTimestampAlignment(unittest.TestCase):
    def test_metadata_path_uses_stream_start_and_offset(self):
        # whole-second datetime so readable_dt_str round-trips exactly
        sdt = datetime(2026, 4, 27, 23, 42, 28, tzinfo=timezone.utc)
        offset = 169993.0  # raw LSL local_clock offset at stream start (machine-uptime scale)
        ts = np.array([offset + 0.0, offset + 1.5, offset + 10.0])

        out = EasyTimeSyncParsingMixin.lsl_stream_timestamps_to_unix_seconds(_make_stream_with_sync(sdt, offset), ts)

        parsed_sdt = GeneralHelpers.from_readable_dt_str(GeneralHelpers.readable_dt_str(sdt))
        expected = parsed_sdt.timestamp() + (ts - offset)
        np.testing.assert_allclose(out, expected)
        # first sample lands exactly on the stream start wall-clock
        np.testing.assert_allclose(out[0], parsed_sdt.timestamp())


    def test_fallback_anchors_to_reference_datetime_and_first_sample(self):
        ref = datetime(2026, 4, 27, 23, 0, 0, tzinfo=timezone.utc)
        ts = np.array([1000.0, 1001.0, 1005.5])  # raw values, no sync metadata
        stream = {'info': {'desc': [{}]}}  # empty desc -> no phopylslhelper metadata

        out = EasyTimeSyncParsingMixin.lsl_stream_timestamps_to_unix_seconds(stream, ts, fallback_reference_datetime=ref)

        np.testing.assert_allclose(out, ref.timestamp() + (ts - ts[0]))
        np.testing.assert_allclose(out[0], ref.timestamp())


    def test_no_metadata_no_fallback_returns_raw(self):
        ts = np.array([1.0, 2.0, 3.0])
        out = EasyTimeSyncParsingMixin.lsl_stream_timestamps_to_unix_seconds({'info': {'desc': [{}]}}, ts)
        np.testing.assert_allclose(out, ts)


    def test_empty_timestamps_returns_empty(self):
        out = EasyTimeSyncParsingMixin.lsl_stream_timestamps_to_unix_seconds({'info': {}}, [])
        self.assertEqual(len(out), 0)


if __name__ == '__main__':
    unittest.main()
