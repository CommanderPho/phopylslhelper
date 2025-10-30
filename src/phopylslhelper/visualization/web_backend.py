"""Web-based visualization backend using FastAPI and WebSockets."""

import logging
import threading
import asyncio
from typing import Optional, Dict, Any
from collections import deque
import json

from phopylslhelper.visualization.base import VisualizationBackend
from phopylslhelper.core.types import StreamInfo, DataSample

logger = logging.getLogger(__name__)

# Try to import FastAPI and WebSockets, but allow graceful degradation if not available
try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse
    import uvicorn
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    logger.warning("FastAPI/WebSockets not available. Install with: pip install fastapi uvicorn websockets")


class WebBackend(VisualizationBackend):
    """Web-based visualization backend with WebSocket support."""
    
    def __init__(
        self,
        stream_info: Optional[StreamInfo] = None,
        host: str = "localhost",
        port: int = 8000,
        buffer_size: int = 1000,
    ):
        """Initialize web backend.
        
        Args:
            stream_info: Information about the stream to visualize.
            host: Host address for web server.
            port: Port for web server.
            buffer_size: Number of samples to buffer.
        """
        super().__init__(stream_info)
        
        if not WEBSOCKET_AVAILABLE:
            raise RuntimeError(
                "FastAPI/WebSockets not available. Install with: pip install fastapi uvicorn websockets"
            )
        
        self.host = host
        self.port = port
        self.buffer_size = buffer_size
        
        self._app: Optional[FastAPI] = None
        self._server_thread: Optional[threading.Thread] = None
        self._websocket_connections: list = []
        self._data_buffer: deque = deque(maxlen=buffer_size)
        self._lock = threading.Lock()
    
    def start(self) -> bool:
        """Start web visualization server.
        
        Returns:
            True if started successfully, False otherwise.
        """
        if self._running:
            logger.warning("Web backend already running")
            return True
        
        try:
            # Create FastAPI app
            self._app = FastAPI(title="LSL Stream Visualization")
            
            # Define WebSocket endpoint
            @self._app.websocket("/ws")
            async def websocket_endpoint(websocket: WebSocket):
                await websocket.accept()
                with self._lock:
                    self._websocket_connections.append(websocket)
                
                try:
                    # Send initial stream info
                    if self.stream_info:
                        await websocket.send_json({
                            "type": "stream_info",
                            "data": self.stream_info.to_dict(),
                        })
                    
                    # Keep connection alive
                    while True:
                        await websocket.receive_text()
                
                except WebSocketDisconnect:
                    pass
                finally:
                    with self._lock:
                        if websocket in self._websocket_connections:
                            self._websocket_connections.remove(websocket)
            
            # Define HTML page endpoint
            @self._app.get("/", response_class=HTMLResponse)
            async def get_html():
                return self._get_html_content()
            
            # Start server in background thread
            def run_server():
                uvicorn.run(self._app, host=self.host, port=self.port, log_level="warning")
            
            self._server_thread = threading.Thread(target=run_server, daemon=True)
            self._server_thread.start()
            
            self._running = True
            
            logger.info(
                f"Web backend started on http://{self.host}:{self.port}"
                f" for stream: {self.stream_info.name if self.stream_info else 'unknown'}"
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Error starting web backend: {e}", exc_info=True)
            return False
    
    def stop(self):
        """Stop web visualization server."""
        if not self._running:
            return
        
        try:
            # Close WebSocket connections
            with self._lock:
                connections = list(self._websocket_connections)
                self._websocket_connections.clear()
            
            for conn in connections:
                try:
                    asyncio.run(conn.close())
                except Exception:
                    pass
            
            # Server will stop when thread exits (daemon thread)
            self._data_buffer.clear()
            self._running = False
            
            logger.info("Web backend stopped")
        
        except Exception as e:
            logger.error(f"Error stopping web backend: {e}", exc_info=True)
    
    def update(self, sample: DataSample):
        """Update visualization with new sample data.
        
        Args:
            sample: Data sample to display.
        """
        if not self._running:
            return
        
        # Add to buffer
        self._data_buffer.append(sample.to_dict())
        
        # Broadcast to WebSocket connections
        self._broadcast_sample(sample)
    
    def _broadcast_sample(self, sample: DataSample):
        """Broadcast sample to all WebSocket connections."""
        if not self._websocket_connections:
            return
        
        message = {
            "type": "sample",
            "data": sample.to_dict(),
        }
        
        async def send_to_all():
            disconnected = []
            for conn in self._websocket_connections:
                try:
                    await conn.send_json(message)
                except Exception:
                    disconnected.append(conn)
            
            # Remove disconnected connections
            if disconnected:
                with self._lock:
                    for conn in disconnected:
                        if conn in self._websocket_connections:
                            self._websocket_connections.remove(conn)
        
        # Run in event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(send_to_all())
            else:
                loop.run_until_complete(send_to_all())
        except Exception as e:
            logger.debug(f"Error broadcasting sample: {e}")
    
    def _get_html_content(self) -> str:
        """Generate HTML content for visualization page."""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>LSL Stream Visualization</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        #plot {{ width: 100%; height: 600px; }}
        #info {{ margin-bottom: 20px; }}
    </style>
</head>
<body>
    <h1>LSL Stream Visualization</h1>
    <div id="info"></div>
    <div id="plot"></div>
    
    <script>
        const ws = new WebSocket('ws://{self.host}:{self.port}/ws');
        const plotDiv = document.getElementById('plot');
        const infoDiv = document.getElementById('info');
        
        let data = {{}};
        
        ws.onmessage = function(event) {{
            const msg = JSON.parse(event.data);
            
            if (msg.type === 'stream_info') {{
                const info = msg.data;
                infoDiv.innerHTML = `
                    <h2>${{info.name}}</h2>
                    <p><strong>Type:</strong> ${{info.type}}</p>
                    <p><strong>Channels:</strong> ${{info.channel_count}}</p>
                    <p><strong>Sampling Rate:</strong> ${{info.nominal_srate}} Hz</p>
                `;
                
                // Initialize data arrays for each channel
                for (let i = 0; i < info.channel_count; i++) {{
                    data[`channel_${{i}}`] = {{ x: [], y: [] }};
                }}
            }}
            
            if (msg.type === 'sample') {{
                const sample = msg.data;
                const sampleData = sample.sample_data;
                
                // Update data arrays
                Object.keys(data).forEach((key, idx) => {{
                    if (idx < sampleData.length) {{
                        data[key].x.push(data[key].x.length);
                        data[key].y.push(sampleData[idx]);
                        
                        // Keep last 1000 points
                        if (data[key].x.length > 1000) {{
                            data[key].x.shift();
                            data[key].y.shift();
                        }}
                    }}
                }});
                
                // Update plot
                const traces = Object.keys(data).map((key, idx) => ({{
                    x: data[key].x,
                    y: data[key].y,
                    type: 'scatter',
                    mode: 'lines',
                    name: key,
                }}));
                
                Plotly.newPlot('plot', traces, {{
                    title: 'Real-time Stream Data',
                    xaxis: {{ title: 'Sample' }},
                    yaxis: {{ title: 'Amplitude' }},
                }}, {{ responsive: true }});
            }}
        }};
        
        ws.onerror = function(error) {{
            console.error('WebSocket error:', error);
        }};
    </script>
</body>
</html>
"""
    
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

