"""Message formatting for cloud streaming."""

import json
import logging
from typing import Dict, Any

from phopylslhelper.core.types import DataSample

logger = logging.getLogger(__name__)


class MessageFormatter:
    """Formats LSL data samples into JSON messages for cloud transmission."""
    
    def format_sample(self, sample: DataSample) -> str:
        """Format a data sample as JSON string.
        
        Args:
            sample: Data sample to format.
        
        Returns:
            JSON string representation of the sample.
        """
        try:
            message_dict = sample.to_dict()
            return json.dumps(message_dict, ensure_ascii=False)
        
        except Exception as e:
            logger.error(f"Error formatting sample: {e}", exc_info=True)
            raise ValueError(f"Failed to format sample: {e}") from e
    
    def format_batch(self, samples: list[DataSample]) -> str:
        """Format multiple samples as a batch JSON array.
        
        Args:
            samples: List of data samples to format.
        
        Returns:
            JSON string representation of the batch.
        """
        try:
            batch = [sample.to_dict() for sample in samples]
            return json.dumps(batch, ensure_ascii=False)
        
        except Exception as e:
            logger.error(f"Error formatting batch: {e}", exc_info=True)
            raise ValueError(f"Failed to format batch: {e}") from e
    
    def parse_sample(self, json_str: str) -> Dict[str, Any]:
        """Parse a JSON string back into a dictionary.
        
        Args:
            json_str: JSON string to parse.
        
        Returns:
            Dictionary representation of the sample.
        """
        try:
            return json.loads(json_str)
        
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON: {e}", exc_info=True)
            raise ValueError(f"Invalid JSON: {e}") from e

