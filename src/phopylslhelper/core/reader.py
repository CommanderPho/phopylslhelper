"""LSL stream data acquisition."""

import logging
import threading
import queue
from typing import Optional, Callable, List
from collections import deque
import pylsl

from phopylslhelper.core.types import DataSample, StreamInfo, TimestampMetadata
from phopylslhelper.core.lsl_manager import LSLStreamManager

logger = logging.getLogger(__name__)


class LSLStreamReader:
    """Reads data from LSL streams with buffering and callback support."""
    
    def __init__(
        self,
        stream_manager: LSLStreamManager,
        stream_id: str,
        buffer_size: int = 1000,
        sample_callback: Optional[Callable[[DataSample], None]] = None,
    ):
        """Initialize stream reader.
        
        Args:
            stream_manager: LSLStreamManager instance for stream access.
            stream_id: Identifier of the stream to read from.
            buffer_size: Maximum number of samples to buffer.
            sample_callback: Optional callback function called for each sample.
        """
        self.stream_manager = stream_manager
        self.stream_id = stream_id
        self.buffer_size = buffer_size
        self.sample_callback = sample_callback
        
        self._stream_info: Optional[StreamInfo] = None
        self._running = False
        self._read_thread: Optional[threading.Thread] = None
        self._sample_queue: queue.Queue = queue.Queue(maxsize=buffer_size)
        self._sample_buffer: deque = deque(maxlen=buffer_size)
        self._lock = threading.Lock()
    
    def start(self) -> bool:
        """Start reading from the stream.
        
        Returns:
            True if started successfully, False otherwise.
        
        Raises:
            RuntimeError: If stream cannot be started due to connection issues.
        """
        if self._running:
            logger.warning(f"Reader for {self.stream_id} already running")
            return True
        
        try:
            # Get stream info
            self._stream_info = self.stream_manager.get_stream_info(self.stream_id)
            if not self._stream_info:
                error_msg = f"Stream info not available for {self.stream_id}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            # Ensure stream is connected
            try:
                if not self.stream_manager.connect_stream(self.stream_id):
                    error_msg = f"Failed to connect to stream {self.stream_id}"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)
            except Exception as e:
                logger.error(f"Error connecting to stream {self.stream_id}: {e}", exc_info=True)
                raise RuntimeError(f"Failed to connect to stream {self.stream_id}") from e
            
            self._running = True
            
            # Start reading thread
            self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._read_thread.start()
            
            logger.info(f"Started reading from stream: {self.stream_id}")
            return True
        
        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error starting reader for {self.stream_id}: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error starting reader for {self.stream_id}") from e
    
    def stop(self):
        """Stop reading from the stream."""
        if not self._running:
            return
        
        self._running = False
        if self._read_thread:
            self._read_thread.join(timeout=2.0)
        
        logger.info(f"Stopped reading from stream: {self.stream_id}")
    
    def _read_loop(self):
        """Main reading loop running in background thread."""
        inlet = self.stream_manager.get_stream_inlet(self.stream_id)
        if not inlet:
            logger.error(f"No inlet available for stream {self.stream_id}")
            return
        
        logger.debug(f"Reading loop started for {self.stream_id}")
        
        while self._running:
            try:
                # Pull sample with timeout
                sample, timestamp = inlet.pull_sample(timeout=0.1)
                
                if sample is None:
                    continue
                
                # Create DataSample
                data_sample = DataSample(
                    data=sample,
                    timestamp=timestamp,
                    stream_id=self.stream_id,
                    metadata=TimestampMetadata(
                        lsl_timestamp=timestamp,
                        clock_offset=inlet.time_correction(),
                    ),
                )
                
                # Add to buffer
                with self._lock:
                    self._sample_buffer.append(data_sample)
                
                # Add to queue for callbacks
                try:
                    self._sample_queue.put_nowait(data_sample)
                except queue.Full:
                    # Remove oldest sample if buffer is full
                    try:
                        self._sample_queue.get_nowait()
                        self._sample_queue.put_nowait(data_sample)
                    except queue.Empty:
                        pass
                
                # Call callback if provided
                if self.sample_callback:
                    try:
                        self.sample_callback(data_sample)
                    except Exception as e:
                        logger.error(f"Error in sample callback: {e}", exc_info=True)
            
            except Exception as e:
                if self._running:
                    logger.error(f"Error reading sample from {self.stream_id}: {e}", exc_info=True)
                    # Small delay before retrying
                    import time
                    time.sleep(0.1)
        
        logger.debug(f"Reading loop stopped for {self.stream_id}")
    
    def get_samples(self, max_samples: Optional[int] = None) -> List[DataSample]:
        """Get buffered samples.
        
        Args:
            max_samples: Maximum number of samples to return (None = all).
        
        Returns:
            List of data samples.
        """
        with self._lock:
            if max_samples is None:
                return list(self._sample_buffer)
            else:
                return list(self._sample_buffer)[-max_samples:]
    
    def clear_buffer(self):
        """Clear the sample buffer."""
        with self._lock:
            self._sample_buffer.clear()
        
        # Clear queue
        while not self._sample_queue.empty():
            try:
                self._sample_queue.get_nowait()
            except queue.Empty:
                break
    
    def get_stream_info(self) -> Optional[StreamInfo]:
        """Get information about the stream being read.
        
        Returns:
            Stream information or None if not available.
        """
        return self._stream_info
    
    def is_running(self) -> bool:
        """Check if reader is currently running.
        
        Returns:
            True if running, False otherwise.
        """
        return self._running
    
    def get_buffer_size(self) -> int:
        """Get current buffer size.
        
        Returns:
            Number of samples currently buffered.
        """
        with self._lock:
            return len(self._sample_buffer)

