"""Type definitions for LSL stream data structures."""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from enum import Enum
import pylsl


class StreamStatus(str, Enum):
    """Status of an LSL stream connection."""

    DISCONNECTED = "disconnected"
    DISCOVERING = "discovering"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class TimestampMetadata:
    """Metadata for preserving LSL timestamp synchronization."""

    lsl_timestamp: float
    """LSL local clock timestamp (seconds since LSL epoch)."""
    
    clock_offset: Optional[float] = None
    """Clock offset for synchronization (if available)."""
    
    transmission_time: Optional[datetime] = None
    """Transmission timestamp for latency calculation."""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "lsl_timestamp": f"{self.lsl_timestamp:.9f}",  # High precision string
        }
        if self.clock_offset is not None:
            result["clock_offset"] = f"{self.clock_offset:.9f}"
        if self.transmission_time is not None:
            result["transmission_time"] = self.transmission_time.isoformat() + "Z"
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimestampMetadata":
        """Create from dictionary."""
        return cls(
            lsl_timestamp=float(data["lsl_timestamp"]),
            clock_offset=float(data["clock_offset"]) if data.get("clock_offset") else None,
            transmission_time=datetime.fromisoformat(data["transmission_time"].replace("Z", "+00:00"))
            if data.get("transmission_time")
            else None,
        )


@dataclass
class DataSample:
    """Represents a single sample from an LSL stream."""

    data: List[Union[float, int, str]]
    """Sample data values (channels)."""
    
    timestamp: float
    """LSL timestamp of the sample."""
    
    stream_id: str
    """Identifier for the stream."""
    
    metadata: Optional[TimestampMetadata] = None
    """Additional timestamp metadata for cloud streaming."""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "stream_id": self.stream_id,
            "sample_data": self.data,
            "lsl_timestamp": f"{self.timestamp:.9f}",
        }
        if self.metadata:
            result.update(self.metadata.to_dict())
        return result


@dataclass
class StreamInfo:
    """Represents information about an LSL stream."""

    name: str
    """Stream name."""
    
    type: str
    """Stream type (e.g., 'EEG', 'Markers')."""
    
    channel_count: int
    """Number of channels."""
    
    nominal_srate: float
    """Nominal sampling rate (Hz)."""
    
    channel_format: str
    """Channel format (e.g., 'float32', 'int32', 'string')."""
    
    source_id: Optional[str] = None
    """Source identifier."""
    
    uid: Optional[str] = None
    """Unique stream identifier."""
    
    hostname: Optional[str] = None
    """Hostname where stream originates."""
    
    status: StreamStatus = StreamStatus.DISCONNECTED
    """Current connection status."""
    
    pylsl_info: Optional[pylsl.StreamInfo] = None
    """Original pylsl.StreamInfo object (if available)."""
    
    @classmethod
    def from_pylsl(cls, pylsl_info: pylsl.StreamInfo) -> "StreamInfo":
        """Create StreamInfo from pylsl.StreamInfo."""
        return cls(
            name=pylsl_info.name(),
            type=pylsl_info.type(),
            channel_count=pylsl_info.channel_count(),
            nominal_srate=pylsl_info.nominal_srate(),
            channel_format=pylsl_info.channel_format_string(),
            source_id=pylsl_info.source_id(),
            uid=pylsl_info.uid(),
            hostname=pylsl_info.hostname(),
            pylsl_info=pylsl_info,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "type": self.type,
            "channel_count": self.channel_count,
            "nominal_srate": self.nominal_srate,
            "channel_format": self.channel_format,
            "source_id": self.source_id,
            "uid": self.uid,
            "hostname": self.hostname,
            "status": self.status.value,
        }

