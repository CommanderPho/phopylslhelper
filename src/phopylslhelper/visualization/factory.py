"""Factory for creating visualization backends."""

import logging
from typing import Optional

from phopylslhelper.visualization.base import VisualizationBackend
from phopylslhelper.core.types import StreamInfo

logger = logging.getLogger(__name__)


def create_backend(
    backend_type: str,
    stream_info: Optional[StreamInfo] = None,
    **kwargs,
) -> VisualizationBackend:
    """Create a visualization backend instance.
    
    Args:
        backend_type: Type of backend ("mne-lsl", "pyqt5", or "web").
        stream_info: Stream information for visualization.
        **kwargs: Additional arguments passed to backend constructor.
    
    Returns:
        Visualization backend instance.
    
    Raises:
        ValueError: If backend_type is invalid.
        RuntimeError: If backend dependencies are not available.
    """
    backend_type = backend_type.lower()
    
    if backend_type == "mne-lsl":
        try:
            from phopylslhelper.visualization.mne_backend import MNEBackend
            return MNEBackend(stream_info=stream_info, **kwargs)
        except RuntimeError as e:
            logger.error(f"Failed to create MNE backend: {e}")
            raise RuntimeError(f"MNE backend not available: {e}") from e
    
    elif backend_type == "pyqt5":
        try:
            from phopylslhelper.visualization.pyqt_backend import PyQt5Backend
            return PyQt5Backend(stream_info=stream_info, **kwargs)
        except RuntimeError as e:
            logger.error(f"Failed to create PyQt5 backend: {e}")
            raise RuntimeError(f"PyQt5 backend not available: {e}") from e
    
    elif backend_type == "web":
        try:
            from phopylslhelper.visualization.web_backend import WebBackend
            return WebBackend(stream_info=stream_info, **kwargs)
        except RuntimeError as e:
            logger.error(f"Failed to create web backend: {e}")
            raise RuntimeError(f"Web backend not available: {e}") from e
    
    else:
        raise ValueError(
            f"Invalid backend type: {backend_type}. "
            f"Must be one of: 'mne-lsl', 'pyqt5', 'web'"
        )


def list_available_backends() -> list:
    """List available visualization backends.
    
    Returns:
        List of backend type names that are available.
    """
    available = []
    
    # Check MNE-LSL
    try:
        from phopylslhelper.visualization.mne_backend import MNE_AVAILABLE
        if MNE_AVAILABLE:
            available.append("mne-lsl")
    except ImportError:
        pass
    
    # Check PyQt5
    try:
        from phopylslhelper.visualization.pyqt_backend import PYQT5_AVAILABLE
        if PYQT5_AVAILABLE:
            available.append("pyqt5")
    except ImportError:
        pass
    
    # Check Web
    try:
        from phopylslhelper.visualization.web_backend import WEBSOCKET_AVAILABLE
        if WEBSOCKET_AVAILABLE:
            available.append("web")
    except ImportError:
        pass
    
    return available

