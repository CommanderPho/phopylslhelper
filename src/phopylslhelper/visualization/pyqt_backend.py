"""PyQt5 visualization backend."""

import logging
from typing import Optional
from collections import deque

from phopylslhelper.visualization.base import VisualizationBackend
from phopylslhelper.core.types import StreamInfo, DataSample

logger = logging.getLogger(__name__)

# Try to import PyQt5, but allow graceful degradation if not available
try:
    from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout
    from PyQt5.QtCore import QTimer, pyqtSignal, QObject
    import pyqtgraph as pg
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    logger.warning("PyQt5 not available. Install with: pip install PyQt5 pyqtgraph")


class PyQt5Backend(VisualizationBackend):
    """PyQt5-based visualization backend for lightweight custom displays."""
    
    def __init__(self, stream_info: Optional[StreamInfo] = None, buffer_size: int = 1000):
        """Initialize PyQt5 backend.
        
        Args:
            stream_info: Information about the stream to visualize.
            buffer_size: Number of samples to display in scrolling plot.
        """
        super().__init__(stream_info)
        
        if not PYQT5_AVAILABLE:
            raise RuntimeError(
                "PyQt5 is not available. Install with: pip install PyQt5 pyqtgraph"
            )
        
        self.buffer_size = buffer_size
        self._app: Optional[QApplication] = None
        self._window: Optional[QMainWindow] = None
        self._plot_widget: Optional[pg.PlotWidget] = None
        self._curves: list = []
        self._data_buffer: deque = deque(maxlen=buffer_size)
        self._timer: Optional[QTimer] = None
    
    def start(self) -> bool:
        """Start PyQt5 visualization.
        
        Returns:
            True if started successfully, False otherwise.
        """
        if self._running:
            logger.warning("PyQt5 backend already running")
            return True
        
        if not self.stream_info:
            logger.error("No stream info available")
            return False
        
        try:
            # Create QApplication if it doesn't exist
            if QApplication.instance() is None:
                self._app = QApplication([])
            else:
                self._app = QApplication.instance()
            
            # Create main window
            self._window = QMainWindow()
            self._window.setWindowTitle(f"LSL Stream: {self.stream_info.name}")
            self._window.resize(800, 600)
            
            # Create central widget with plot
            central_widget = QWidget()
            layout = QVBoxLayout()
            central_widget.setLayout(layout)
            
            # Create plot widget
            self._plot_widget = pg.PlotWidget()
            self._plot_widget.setLabel('left', 'Amplitude')
            self._plot_widget.setLabel('bottom', 'Time (samples)')
            self._plot_widget.showGrid(x=True, y=True)
            
            layout.addWidget(self._plot_widget)
            self._window.setCentralWidget(central_widget)
            
            # Create curves for each channel
            self._curves = []
            for i in range(self.stream_info.channel_count):
                curve = self._plot_widget.plot(pen=(i, self.stream_info.channel_count))
                self._curves.append(curve)
            
            # Set up update timer
            self._timer = QTimer()
            self._timer.timeout.connect(self._update_plot)
            self._timer.start(int(1000 / 30))  # 30 FPS
            
            # Show window
            self._window.show()
            
            self._running = True
            
            logger.info(f"PyQt5 backend started for stream: {self.stream_info.name}")
            
            # Process events to show window
            self._app.processEvents()
            
            return True
        
        except Exception as e:
            logger.error(f"Error starting PyQt5 backend: {e}", exc_info=True)
            return False
    
    def stop(self):
        """Stop PyQt5 visualization."""
        if not self._running:
            return
        
        try:
            if self._timer:
                self._timer.stop()
                self._timer = None
            
            if self._window:
                self._window.close()
                self._window = None
            
            self._curves = []
            self._data_buffer.clear()
            self._running = False
            
            logger.info("PyQt5 backend stopped")
        
        except Exception as e:
            logger.error(f"Error stopping PyQt5 backend: {e}", exc_info=True)
    
    def update(self, sample: DataSample):
        """Update visualization with new sample data.
        
        Args:
            sample: Data sample to display.
        """
        if not self._running:
            return
        
        # Add to buffer
        self._data_buffer.append(sample.data)
        
        # Process events to update display
        if self._app:
            self._app.processEvents()
    
    def _update_plot(self):
        """Update the plot display."""
        if not self._running or not self._data_buffer:
            return
        
        # Prepare data for plotting
        data = list(self._data_buffer)
        if not data:
            return
        
        # Transpose to get channels as columns
        try:
            import numpy as np
            data_array = np.array(data)
            if len(data_array.shape) == 1:
                # Single channel
                data_array = data_array.reshape(-1, 1)
            
            # Update each curve
            for i, curve in enumerate(self._curves):
                if i < data_array.shape[1]:
                    y_data = data_array[:, i]
                    x_data = np.arange(len(y_data))
                    curve.setData(x_data, y_data)
        except Exception as e:
            logger.debug(f"Error updating plot: {e}")
    
    def set_stream(self, stream_info: StreamInfo):
        """Set or update the stream information.
        
        Args:
            stream_info: New stream information.
        """
        was_running = self._running
        if was_running:
            self.stop()
        
        self.stream_info = stream_info
        
        if was_running:
            self.start()

