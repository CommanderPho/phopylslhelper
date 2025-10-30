"""Visualization backends for LSL streams."""

from abc import ABC, abstractmethod
from typing import Optional, List
import logging

from phopylslhelper.core.types import StreamInfo, DataSample

logger = logging.getLogger(__name__)


class VisualizationBackend(ABC):
    """Abstract base class for visualization backends."""
    
    def __init__(self, stream_info: Optional[StreamInfo] = None):
        """Initialize visualization backend.
        
        Args:
            stream_info: Information about the stream to visualize.
        """
        self.stream_info = stream_info
        self._running = False
    
    @abstractmethod
    def start(self) -> bool:
        """Start the visualization.
        
        Returns:
            True if started successfully, False otherwise.
        """
        pass
    
    @abstractmethod
    def stop(self):
        """Stop the visualization."""
        pass
    
    @abstractmethod
    def update(self, sample: DataSample):
        """Update visualization with new sample data.
        
        Args:
            sample: Data sample to display.
        """
        pass
    
    @abstractmethod
    def set_stream(self, stream_info: StreamInfo):
        """Set or update the stream information.
        
        Args:
            stream_info: New stream information.
        """
        pass
    
    def is_running(self) -> bool:
        """Check if visualization is running.
        
        Returns:
            True if running, False otherwise.
        """
        return self._running
    
    def get_stream_info(self) -> Optional[StreamInfo]:
        """Get current stream information.
        
        Returns:
            Stream information or None if not set.
        """
        return self.stream_info

