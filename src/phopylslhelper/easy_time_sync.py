from typing import Dict, List, Tuple, Optional, Callable, Union, Any
from datetime import datetime, timedelta
import pytz
import pylsl
from pylsl.pylsl import StreamInfo


def readable_dt_str(a_dt: datetime, tz: pytz.timezone = pytz.timezone("US/Eastern")) -> str:
    """ returns the datetime in a readible string format """
    return str(a_dt.astimezone(tz).strftime("%Y-%m-%d %I:%M:%S %p"))


def from_readable_dt_str(a_dt_str: str, tz: pytz.timezone = pytz.timezone("US/Eastern")) -> datetime:
    """ Inverse of `readable_dt_str(...)` """
    return datetime.strptime(a_dt_str, "%Y-%m-%d %I:%M:%S %p").replace(tzinfo=tz)


class EasyTimeSyncParsingMixin:
    """
    self.stream_start_lsl_local_offset = None
    self.stream_start_datetime = None
    
    Usage:
    
            from phopylslhelper.easy_time_sync import EasyTimeSyncParsingMixin, readable_dt_str, from_readable_dt_str
                        
            
            ## In class __init__:
                self.common_capture_stream_start_timestamps() ## `EasyTimeSyncParsingMixin`: capture timestamps for use in LSL streams

                                        
    """

    @property
    def stream_start_datetime(self) -> datetime:
        return self.arbitrary_time_sync_points["stream_start"][0]

    @property
    def stream_start_lsl_local_offset(self) -> float:
        return self.arbitrary_time_sync_points["stream_start"][1]


    @property
    def recording_start_datetime(self) -> datetime:
        return self.arbitrary_time_sync_points["recording_start"][0]

    @property
    def recording_start_lsl_local_offset(self) -> float:
        return self.arbitrary_time_sync_points["recording_start"][1]
        
    @property
    def arbitrary_time_sync_points(self) -> Dict[str, Tuple[datetime, float]]:
        return self._arbitrary_time_sync_points        


    def init_EasyTimeSyncParsingMixin(self):
        # self._stream_start_lsl_local_offset = None
        # self._stream_start_datetime = None
        # self._recording_start_lsl_local_offset = None
        # self._recording_start_datetime = None
        self._arbitrary_time_sync_points = {}

        self.capture_stream_start_timestamps()


    def add_arbitrary_time_sync_point(self, label: str, dt: datetime, lsl_local_offset: float):
        """ Add an arbitrary time sync point for later reference """
        self._arbitrary_time_sync_points[label] = (dt, lsl_local_offset)


    def capture_current_arbitrary_time_sync_point(self, label: str):
        """ Capture the current time as an arbitrary time sync point """
        current_lsl_local_offset = pylsl.local_clock()
        current_datetime = datetime.now(datetime.timezone.utc)
        self.add_arbitrary_time_sync_point(label, current_datetime, current_lsl_local_offset)
    


    def capture_stream_start_timestamps(self):
        """ Capture recording start timestamps for use in LSL streams """
        # Capture the local time offset between LSL and system clock
        # self._stream_start_lsl_local_offset = pylsl.local_clock()
        # Capture the current datetime with timezone info
        # self._stream_start_datetime = datetime.now(datetime.timezone.utc)
        self.capture_current_arbitrary_time_sync_point("stream_start")


    def capture_recording_start_timestamps(self):
        """ Capture recording start timestamps for use in LSL streams """
        self.capture_current_arbitrary_time_sync_point("recording_start")



    ## LSL methods
    def EasyTimeSyncParsingMixin_add_lsl_outlet_info(self, info: StreamInfo) -> StreamInfo:
        """Add the current metadata
        """
        phopylslhelper_element = info.desc().append_child('phopylslhelper')
        phopylslhelper_element.append_child_value("version", "0.1.2")
        
        ## add a custom timestamp field to the stream info:
        assert (self._arbitrary_time_sync_points is not None), f"_arbitrary_time_sync_points is None"
        for label_name, (dt, lsl_offset_sec) in self._arbitrary_time_sync_points.items():
            if dt is not None:
                phopylslhelper_element.append_child_value(f"{label_name}_datetime", readable_dt_str(dt))
            if lsl_offset_sec is not None:
                phopylslhelper_element.append_child_value(f"{label_name}_lsl_local_offset_seconds", str(lsl_offset_sec))

        return info
    


