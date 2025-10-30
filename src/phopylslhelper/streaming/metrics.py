"""Performance metrics and statistics for streaming."""

import logging
import time
from typing import Dict, Optional
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class StreamingMetrics:
    """Metrics for streaming performance."""
    
    samples_sent: int = 0
    samples_dropped: int = 0
    bytes_sent: int = 0
    connection_errors: int = 0
    publish_errors: int = 0
    latency_samples: deque = field(default_factory=lambda: deque(maxlen=1000))
    throughput_samples: deque = field(default_factory=lambda: deque(maxlen=100))
    
    def to_dict(self) -> Dict:
        """Convert metrics to dictionary."""
        avg_latency = (
            sum(self.latency_samples) / len(self.latency_samples)
            if self.latency_samples else 0.0
        )
        avg_throughput = (
            sum(self.throughput_samples) / len(self.throughput_samples)
            if self.throughput_samples else 0.0
        )
        
        return {
            "samples_sent": self.samples_sent,
            "samples_dropped": self.samples_dropped,
            "bytes_sent": self.bytes_sent,
            "connection_errors": self.connection_errors,
            "publish_errors": self.publish_errors,
            "average_latency_ms": avg_latency * 1000,
            "average_throughput_samples_per_sec": avg_throughput,
        }


class MetricsCollector:
    """Collects and tracks streaming performance metrics."""
    
    def __init__(self):
        """Initialize metrics collector."""
        self.metrics = StreamingMetrics()
        self._start_time: Optional[float] = None
        self._last_sample_time: Optional[float] = None
    
    def start(self):
        """Start metrics collection."""
        self._start_time = time.time()
        self._last_sample_time = None
    
    def record_sample_sent(self, bytes_sent: int = 0):
        """Record a successfully sent sample.
        
        Args:
            bytes_sent: Number of bytes sent.
        """
        self.metrics.samples_sent += 1
        self.metrics.bytes_sent += bytes_sent
        
        # Update throughput
        current_time = time.time()
        if self._last_sample_time:
            time_delta = current_time - self._last_sample_time
            if time_delta > 0:
                throughput = 1.0 / time_delta
                self.metrics.throughput_samples.append(throughput)
        
        self._last_sample_time = current_time
    
    def record_sample_dropped(self):
        """Record a dropped sample."""
        self.metrics.samples_dropped += 1
    
    def record_connection_error(self):
        """Record a connection error."""
        self.metrics.connection_errors += 1
    
    def record_publish_error(self):
        """Record a publish error."""
        self.metrics.publish_errors += 1
    
    def record_latency(self, latency_seconds: float):
        """Record latency measurement.
        
        Args:
            latency_seconds: Latency in seconds.
        """
        self.metrics.latency_samples.append(latency_seconds)
    
    def get_metrics(self) -> Dict:
        """Get current metrics as dictionary.
        
        Returns:
            Dictionary of metrics.
        """
        return self.metrics.to_dict()
    
    def reset(self):
        """Reset all metrics."""
        self.metrics = StreamingMetrics()
        self._start_time = None
        self._last_sample_time = None
    
    def get_summary(self) -> str:
        """Get human-readable metrics summary.
        
        Returns:
            Formatted string summary.
        """
        metrics_dict = self.get_metrics()
        
        uptime = (
            time.time() - self._start_time
            if self._start_time else 0.0
        )
        
        summary = f"""
Streaming Metrics Summary:
-------------------------
Uptime: {uptime:.1f}s
Samples sent: {metrics_dict['samples_sent']}
Samples dropped: {metrics_dict['samples_dropped']}
Bytes sent: {metrics_dict['bytes_sent']}
Connection errors: {metrics_dict['connection_errors']}
Publish errors: {metrics_dict['publish_errors']}
Average latency: {metrics_dict['average_latency_ms']:.2f}ms
Average throughput: {metrics_dict['average_throughput_samples_per_sec']:.2f} samples/sec
"""
        return summary.strip()

