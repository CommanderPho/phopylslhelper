"""Reliability and retry logic for cloud streaming."""

import logging
import time
import threading
from typing import Callable, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class RetryStrategy(Enum):
    """Retry strategies for failed operations."""
    
    NONE = "none"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"


class ReliabilityManager:
    """Manages retry logic and connection reliability."""
    
    def __init__(
        self,
        max_retries: int = 5,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
    ):
        """Initialize reliability manager.
        
        Args:
            max_retries: Maximum number of retry attempts.
            initial_delay: Initial delay between retries in seconds.
            max_delay: Maximum delay between retries in seconds.
            strategy: Retry strategy to use.
        """
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.strategy = strategy
        self._lock = threading.Lock()
    
    def execute_with_retry(
        self,
        func: Callable,
        *args,
        on_retry: Optional[Callable[[int, Exception], None]] = None,
        **kwargs,
    ):
        """Execute a function with retry logic.
        
        Args:
            func: Function to execute.
            *args: Positional arguments for function.
            on_retry: Optional callback called on each retry attempt.
            **kwargs: Keyword arguments for function.
        
        Returns:
            Result of function execution.
        
        Raises:
            Exception: If all retries fail, raises the last exception.
        """
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            
            except Exception as e:
                last_exception = e
                
                if attempt < self.max_retries:
                    # Calculate delay
                    delay = self._calculate_delay(attempt)
                    
                    logger.warning(
                        f"Attempt {attempt + 1}/{self.max_retries + 1} failed: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    
                    # Call retry callback
                    if on_retry:
                        try:
                            on_retry(attempt + 1, e)
                        except Exception as callback_error:
                            logger.error(f"Error in retry callback: {callback_error}", exc_info=True)
                    
                    time.sleep(delay)
                else:
                    logger.error(f"All {self.max_retries + 1} attempts failed. Last error: {e}")
        
        # All retries exhausted
        raise last_exception
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for retry attempt.
        
        Args:
            attempt: Current attempt number (0-indexed).
        
        Returns:
            Delay in seconds.
        """
        if self.strategy == RetryStrategy.NONE:
            return self.initial_delay
        
        elif self.strategy == RetryStrategy.LINEAR:
            delay = self.initial_delay * (attempt + 1)
        
        elif self.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.initial_delay * (2 ** attempt)
        
        else:
            delay = self.initial_delay
        
        return min(delay, self.max_delay)

