from typing import Dict, List, Tuple, Optional, Callable, Union, Any
from datetime import datetime, timedelta
import pytz

""" 

from phopylslhelper.general_helpers import unwrap_single_element_listlike_if_needed, readable_dt_str, from_readable_dt_str, localize_datetime_to_timezone, tz_UTC, tz_Eastern, _default_tz

"""
# _default_tz: pytz.timezone = pytz.timezone("US/Eastern")


tz_Eastern: pytz.timezone = pytz.timezone("US/Eastern")
tz_UTC: pytz.timezone = pytz.timezone("UTC")

_default_tz: pytz.timezone = tz_UTC


class GeneralHelpers:
    """General helper utilities for timezone localization and string formatting."""

    @classmethod
    def localize_datetime_to_timezone(cls, obj: datetime, tz: pytz.timezone = _default_tz) -> datetime:
        return tz.localize(obj)


    @classmethod
    def readable_dt_str(cls, a_dt: datetime, tz: pytz.timezone = _default_tz) -> str:
        """ returns the datetime in a readible string format """
        return str(a_dt.astimezone(tz).strftime("%Y-%m-%d %I:%M:%S %p"))


    @classmethod
    def from_readable_dt_str(cls, a_dt_str: str, tz: pytz.timezone = _default_tz) -> datetime:
        """ Inverse of `readable_dt_str(...)` """
        return datetime.strptime(a_dt_str, "%Y-%m-%d %I:%M:%S %p").replace(tzinfo=tz)


    @classmethod
    def unwrap_single_element_listlike_if_needed(cls, a_list: List) -> Union[Any, List]:
        """ Unwrap a single element listlike if needed
        
        from phopylslhelper.general_helpers import unwrap_single_element_listlike_if_needed

        """
        try:
            if len(a_list) == 1:
                return a_list[0]
            else:
                return a_list
        except (TypeError, AttributeError) as e:
            return a_list ## return the original
        except Exception as e:
            raise e


# Module-level function aliases for backward compatibility
localize_datetime_to_timezone = GeneralHelpers.localize_datetime_to_timezone
readable_dt_str = GeneralHelpers.readable_dt_str
from_readable_dt_str = GeneralHelpers.from_readable_dt_str
unwrap_single_element_listlike_if_needed = GeneralHelpers.unwrap_single_element_listlike_if_needed