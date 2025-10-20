from typing import Dict, List, Tuple, Optional, Callable, Union, Any
from datetime import datetime, timedelta
import pytz
import pylsl
from pylsl import StreamInfo
from phopylslhelper.general_helpers import unwrap_single_element_listlike_if_needed, readable_dt_str, from_readable_dt_str, localize_datetime_to_timezone, tz_UTC, tz_Eastern, _default_tz


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
        current_datetime = datetime.now(pytz.timezone('UTC')) # datetime.now(datetime.timezone.utc)
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
    


    @classmethod
    def parse_and_add_lsl_outlet_info_from_desc(cls, desc_info_dict: Dict, stream_info_dict: Dict) -> dict:
        """Parse the LSL outlet info from the description dictionary
        
        'stream_start_lsl_local_offset_seconds', 'stream_start_datetime'
        'recording_start_lsl_local_offset_seconds', 'recording_start_datetime'

                desc_info_dict = dict(stream['info'].get('desc', [{}])[0])
                stream_info_dict = EasyTimeSyncParsingMixin.parse_and_add_lsl_outlet_info_from_desc(desc_info_dict=desc_info_dict, stream_info_dict=stream_info_dict) ## Returns the updated `stream_info_dict`

        """
        assert len(desc_info_dict) > 0
        # label_names = ('recording_start', 'stream_start')
        # custom_timestamp_keys = {'recording_start_lsl_local_offset_seconds': (lambda v: float(v)), 'recording_start_datetime': (lambda v: from_readable_dt_str(v))}
        ## try to get the special marker timestamp helpers:
        phopylslhelper_dict = unwrap_single_element_listlike_if_needed((desc_info_dict.get('phopylslhelper', {})))
        assert len(phopylslhelper_dict) > 0

        for a_key, a_value in phopylslhelper_dict.items():
            if a_key.endswith('_datetime') and (a_value is not None):
                a_ts_value = from_readable_dt_str(unwrap_single_element_listlike_if_needed(a_value))
                stream_info_dict[a_key] = a_ts_value
                print(f'\t FOUND CUSTOM TIMESTAMP SYNC KEY: "{a_key}": {a_ts_value}')
            elif a_key.endswith('_lsl_local_offset_seconds') and (a_value is not None):
                a_ts_value = float(unwrap_single_element_listlike_if_needed(a_value))
                stream_info_dict[a_key] = a_ts_value
                print(f'\t FOUND CUSTOM TIMESTAMP SYNC KEY: "{a_key}": {a_ts_value}')

        # assert 'recording_start_lsl_local_offset_seconds' in desc_info_dict

        # for a_key, a_value_type_convert_fn in custom_timestamp_keys.items():
        #     ## NOTE IMPORTANT: this operates on `desc_info_dict` dict, not the same `stream_info_dict` as above
        #     if desc_info_dict.get(a_key, None) is not None:
        #         a_ts_value = a_value_type_convert_fn(unwrap_single_element_listlike_if_needed(desc_info_dict[a_key])) # ['169993.1081304000']
        #         # a_ts_value_dt: datetime = file_datetime + pd.Timedelta(nanoseconds=a_ts_value)
        #         stream_info_dict[a_key] = a_ts_value ## In-contrast to what we get the data from, we SET the data to `stream_info_dict` just as above (flattening)
        #         print(f'\t FOUND CUSTOM TIMESTAMP SYNC KEY: "{a_key}": {a_ts_value}')


        return stream_info_dict
