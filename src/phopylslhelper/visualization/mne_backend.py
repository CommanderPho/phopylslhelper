"""MNE-LSL visualization backend."""

import logging
from typing import Optional

from phopylslhelper.visualization.base import VisualizationBackend
from phopylslhelper.core.types import StreamInfo, DataSample

logger = logging.getLogger(__name__)

# Try to import MNE-LSL, but allow graceful degradation if not available
try:
    from mne_lsl import StreamInfo, StreamPlayer, StreamClient
    import mne
    MNE_AVAILABLE = True
except ImportError:
    MNE_AVAILABLE = False
    logger.warning("MNE-LSL not available. Install with: pip install mne-lsl")


class MNEBackend(VisualizationBackend):
    """MNE-LSL-based visualization backend for advanced neuroscience features."""
    
    def __init__(self, stream_info: Optional[StreamInfo] = None):
        """Initialize MNE backend.
        
        Args:
            stream_info: Information about the stream to visualize.
        """
        super().__init__(stream_info)
        
        if not MNE_AVAILABLE:
            raise RuntimeError(
                "MNE-LSL is not available. Install with: pip install mne-lsl"
            )
        
        self._client: Optional[StreamClient] = None
        self._raw: Optional[mne.io.Raw] = None
    
    def start(self) -> bool:
        """Start MNE-LSL visualization.
        
        Returns:
            True if started successfully, False otherwise.
        """
        if self._running:
            logger.warning("MNE backend already running")
            return True
        
        if not self.stream_info:
            logger.error("No stream info available")
            return False
        
        try:
            # Create stream client
            self._client = StreamClient()
            
            # Connect to stream
            self._client.connect(
                bufsize=360,
                name=self.stream_info.name,
            )
            
            # Get raw data object
            self._raw = self._client.get_data()
            
            # Start visualization loop (this would typically launch MNE's viewer)
            # For now, we'll just mark as running
            self._running = True
            
            logger.info(f"MNE backend started for stream: {self.stream_info.name}")
            return True
        
        except Exception as e:
            logger.error(f"Error starting MNE backend: {e}", exc_info=True)
            return False
    
    def stop(self):
        """Stop MNE-LSL visualization."""
        if not self._running:
            return
        
        try:
            if self._client:
                self._client.disconnect()
                self._client = None
            
            self._raw = None
            self._running = False
            
            logger.info("MNE backend stopped")
        
        except Exception as e:
            logger.error(f"Error stopping MNE backend: {e}", exc_info=True)
    
    def update(self, sample: DataSample):
        """Update visualization with new sample data.
        
        Note: MNE-LSL handles updates internally through its stream client.
        
        Args:
            sample: Data sample to display.
        """
        # MNE-LSL handles updates internally, but we can trigger refresh if needed
        if self._raw and self._running:
            # Update would happen automatically through MNE's internal mechanisms
            pass
    
    def set_stream(self, stream_info: StreamInfo):
        """Set or update the stream information.
        
        Args:
            stream_info: New stream information.
        """
        was_running = self._running
        if was_running:
            self.stop()
        
        self.stream_info = stream_info
        
        if was_running:
            self.start()

