"""Timestamp management for preserving LSL synchronization in cloud streaming."""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import pylsl

from phopylslhelper.core.types import TimestampMetadata, DataSample

logger = logging.getLogger(__name__)


class TimestampManager:
    """Manages LSL timestamp preservation and synchronization metadata."""
    
    def __init__(self):
        """Initialize timestamp manager."""
        self._clock_offset: Optional[float] = None
        self._last_correction_time: Optional[float] = None
    
    def get_timestamp_metadata(
        self,
        lsl_timestamp: float,
        inlet: Optional[Any] = None,
    ) -> TimestampMetadata:
        """Generate timestamp metadata for a sample.
        
        Args:
            lsl_timestamp: LSL timestamp from sample.
            inlet: Optional StreamInlet for clock correction.
        
        Returns:
            TimestampMetadata with synchronization information.
        """
        clock_offset = None
        
        # Get clock offset if inlet provided
        if inlet:
            try:
                clock_offset = inlet.time_correction()
                self._clock_offset = clock_offset
                self._last_correction_time = pylsl.local_clock()
            except Exception as e:
                logger.debug(f"Could not get clock correction: {e}")
                # Use cached offset if available
                if self._clock_offset is not None:
                    clock_offset = self._clock_offset
        
        # Get transmission time
        transmission_time = datetime.now(timezone.utc)
        
        return TimestampMetadata(
            lsl_timestamp=lsl_timestamp,
            clock_offset=clock_offset,
            transmission_time=transmission_time,
        )
    
    def enrich_sample(self, sample: DataSample, inlet: Optional[Any] = None) -> DataSample:
        """Enrich a data sample with timestamp metadata.
        
        Args:
            sample: Data sample to enrich.
            inlet: Optional StreamInlet for clock correction.
        
        Returns:
            Sample with metadata added.
        """
        if sample.metadata is None:
            sample.metadata = self.get_timestamp_metadata(sample.timestamp, inlet)
        
        return sample
    
    def get_clock_offset(self) -> Optional[float]:
        """Get current clock offset estimate.
        
        Returns:
            Clock offset in seconds, or None if not available.
        """
        return self._clock_offset
    
    def reset(self):
        """Reset timestamp manager state."""
        self._clock_offset = None
        self._last_correction_time = None

