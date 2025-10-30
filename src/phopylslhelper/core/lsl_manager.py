"""LSL stream discovery and connection management."""

import logging
import threading
from typing import List, Optional, Dict, Callable
from collections import defaultdict
import pylsl
from pylsl import StreamInfo, StreamInlet

from phopylslhelper.core.types import StreamInfo as StreamInfoType, StreamStatus

logger = logging.getLogger(__name__)


class LSLStreamManager:
    """Manages LSL stream discovery and connections."""
    
    def __init__(self, discovery_timeout: float = 1.0):
        """Initialize stream manager.
        
        Args:
            discovery_timeout: Timeout in seconds for stream discovery operations.
        """
        self.discovery_timeout = discovery_timeout
        self._discovered_streams: Dict[str, StreamInfoType] = {}
        self._connected_streams: Dict[str, StreamInlet] = {}
        self._stream_callbacks: Dict[str, List[Callable]] = defaultdict(list)
        self._discovery_thread: Optional[threading.Thread] = None
        self._discovery_running = False
        self._lock = threading.Lock()
    
    def discover_streams(
        self,
        name: Optional[str] = None,
        stream_type: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> List[StreamInfoType]:
        """Discover available LSL streams on the network.
        
        Args:
            name: Filter by stream name (optional).
            stream_type: Filter by stream type (optional).
            timeout: Discovery timeout in seconds (uses default if None).
        
        Returns:
            List of discovered stream information.
        """
        timeout = timeout or self.discovery_timeout
        
        try:
            logger.info(f"Discovering LSL streams (timeout: {timeout}s)...")
            
            # Resolve streams
            infos = pylsl.resolve_streams(timeout=timeout)
            
            discovered = []
            for info in infos:
                # Apply filters
                if name and info.name() != name:
                    continue
                if stream_type and info.type() != stream_type:
                    continue
                
                stream_info = StreamInfoType.from_pylsl(info)
                stream_info.status = StreamStatus.DISCONNECTED
                
                # Update discovered streams cache
                with self._lock:
                    self._discovered_streams[stream_info.uid or stream_info.name] = stream_info
                
                discovered.append(stream_info)
                logger.debug(f"Discovered stream: {stream_info.name} ({stream_info.type})")
            
            logger.info(f"Discovered {len(discovered)} stream(s)")
            return discovered
        
        except Exception as e:
            logger.error(f"Error during stream discovery: {e}", exc_info=True)
            return []
    
    def start_continuous_discovery(self, interval: float = 5.0):
        """Start continuous stream discovery in background thread.
        
        Args:
            interval: Time between discovery attempts in seconds.
        """
        if self._discovery_running:
            logger.warning("Discovery already running")
            return
        
        self._discovery_running = True
        
        def discovery_loop():
            while self._discovery_running:
                try:
                    self.discover_streams()
                except Exception as e:
                    logger.error(f"Error in discovery loop: {e}", exc_info=True)
                
                # Sleep for interval
                import time
                time.sleep(interval)
        
        self._discovery_thread = threading.Thread(target=discovery_loop, daemon=True)
        self._discovery_thread.start()
        logger.info("Started continuous stream discovery")
    
    def stop_continuous_discovery(self):
        """Stop continuous stream discovery."""
        if not self._discovery_running:
            return
        
        self._discovery_running = False
        if self._discovery_thread:
            self._discovery_thread.join(timeout=2.0)
        logger.info("Stopped continuous stream discovery")
    
    def connect_stream(
        self,
        stream_id: str,
        max_buflen: int = 360,
        max_chunklen: int = 0,
    ) -> bool:
        """Connect to an LSL stream.
        
        Args:
            stream_id: Stream identifier (UID or name).
            max_buflen: Maximum buffer length in samples.
            max_chunklen: Maximum chunk length (0 = no limit).
        
        Returns:
            True if connection successful, False otherwise.
        
        Raises:
            ValueError: If stream_id is invalid.
            RuntimeError: If connection fails after retries.
        """
        if not stream_id or not isinstance(stream_id, str):
            raise ValueError(f"Invalid stream_id: {stream_id}")
        
        try:
            with self._lock:
                # Check if already connected
                if stream_id in self._connected_streams:
                    logger.warning(f"Stream {stream_id} already connected")
                    return True
                
                # Find stream info
                stream_info = self._discovered_streams.get(stream_id)
                if not stream_info:
                    # Try to discover stream
                    try:
                        discovered = self.discover_streams(name=stream_id if stream_id not in self._discovered_streams else None)
                        if discovered:
                            stream_info = discovered[0]
                            stream_id = stream_info.uid or stream_info.name
                        else:
                            error_msg = f"Stream {stream_id} not found during discovery"
                            logger.error(error_msg)
                            raise RuntimeError(error_msg)
                    except Exception as e:
                        logger.error(f"Error during stream discovery for {stream_id}: {e}", exc_info=True)
                        raise RuntimeError(f"Failed to discover stream {stream_id}") from e
                
                # Create inlet
                pylsl_info = stream_info.pylsl_info
                if not pylsl_info:
                    # Re-resolve if pylsl_info not available
                    try:
                        resolved = pylsl.resolve_stream("name", stream_info.name, timeout=self.discovery_timeout)
                        if not resolved:
                            error_msg = f"Could not resolve stream {stream_id}"
                            logger.error(error_msg)
                            raise RuntimeError(error_msg)
                        pylsl_info = resolved[0]
                    except Exception as e:
                        logger.error(f"Error resolving stream {stream_id}: {e}", exc_info=True)
                        raise RuntimeError(f"Failed to resolve stream {stream_id}") from e
                
                try:
                    inlet = StreamInlet(pylsl_info, max_buflen=max_buflen, max_chunklen=max_chunklen)
                except Exception as e:
                    logger.error(f"Error creating StreamInlet for {stream_id}: {e}", exc_info=True)
                    stream_info.status = StreamStatus.ERROR
                    raise RuntimeError(f"Failed to create inlet for stream {stream_id}") from e
                
                # Store connection
                self._connected_streams[stream_id] = inlet
                stream_info.status = StreamStatus.CONNECTED
                self._discovered_streams[stream_id] = stream_info
                
                logger.info(f"Connected to stream: {stream_info.name} ({stream_id})")
                return True
        
        except (ValueError, RuntimeError):
            raise
        except Exception as e:
            logger.error(f"Unexpected error connecting to stream {stream_id}: {e}", exc_info=True)
            if stream_id in self._discovered_streams:
                self._discovered_streams[stream_id].status = StreamStatus.ERROR
            raise RuntimeError(f"Unexpected error connecting to stream {stream_id}") from e
    
    def disconnect_stream(self, stream_id: str) -> bool:
        """Disconnect from an LSL stream.
        
        Args:
            stream_id: Stream identifier.
        
        Returns:
            True if disconnection successful, False otherwise.
        """
        with self._lock:
            if stream_id not in self._connected_streams:
                logger.warning(f"Stream {stream_id} not connected")
                return False
            
            try:
                inlet = self._connected_streams.pop(stream_id)
                inlet.close_stream()
                
                # Update status
                if stream_id in self._discovered_streams:
                    self._discovered_streams[stream_id].status = StreamStatus.DISCONNECTED
                
                logger.info(f"Disconnected from stream: {stream_id}")
                return True
            
            except Exception as e:
                logger.error(f"Error disconnecting from stream {stream_id}: {e}", exc_info=True)
                return False
    
    def get_stream_info(self, stream_id: str) -> Optional[StreamInfoType]:
        """Get information about a stream.
        
        Args:
            stream_id: Stream identifier.
        
        Returns:
            Stream information or None if not found.
        """
        with self._lock:
            return self._discovered_streams.get(stream_id)
    
    def get_connected_streams(self) -> List[str]:
        """Get list of connected stream IDs.
        
        Returns:
            List of stream identifiers.
        """
        with self._lock:
            return list(self._connected_streams.keys())
    
    def get_stream_inlet(self, stream_id: str) -> Optional[StreamInlet]:
        """Get the StreamInlet for a connected stream.
        
        Args:
            stream_id: Stream identifier.
        
        Returns:
            StreamInlet or None if not connected.
        """
        with self._lock:
            return self._connected_streams.get(stream_id)
    
    def disconnect_all(self):
        """Disconnect from all streams."""
        stream_ids = list(self._connected_streams.keys())
        for stream_id in stream_ids:
            self.disconnect_stream(stream_id)
        
        logger.info(f"Disconnected from {len(stream_ids)} stream(s)")
    
    def cleanup(self):
        """Clean up resources."""
        self.stop_continuous_discovery()
        self.disconnect_all()
        logger.info("Stream manager cleaned up")

