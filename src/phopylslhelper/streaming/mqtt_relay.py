"""MQTT relay for cloud streaming of LSL streams."""

import logging
import threading
from typing import Optional, Dict, Callable
from collections import deque

from phopylslhelper.core.types import DataSample
from phopylslhelper.streaming.message_formatter import MessageFormatter

logger = logging.getLogger(__name__)

# Try to import paho-mqtt, but allow graceful degradation if not available
try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    logger.warning("paho-mqtt not available. Install with: pip install paho-mqtt")


class MQTTRelay:
    """MQTT client for relaying LSL streams to cloud services."""
    
    def __init__(
        self,
        broker: str,
        port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None,
        tls: bool = False,
        qos: int = 1,
        keepalive: int = 60,
    ):
        """Initialize MQTT relay.
        
        Args:
            broker: MQTT broker hostname or IP address.
            port: MQTT broker port.
            username: Optional username for authentication.
            password: Optional password for authentication.
            tls: Whether to use TLS encryption.
            qos: Quality of Service level (0, 1, or 2).
            keepalive: Keepalive interval in seconds.
        """
        if not MQTT_AVAILABLE:
            raise RuntimeError(
                "paho-mqtt not available. Install with: pip install paho-mqtt"
            )
        
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.tls = tls
        self.qos = qos
        self.keepalive = keepalive
        
        self._client: Optional[mqtt.Client] = None
        self._connected = False
        self._lock = threading.Lock()
        self._message_queue: deque = deque(maxlen=1000)  # Buffer messages during disconnection
        self._formatter = MessageFormatter()
        self._connection_callbacks: list[Callable[[bool], None]] = []
    
    def connect(self) -> bool:
        """Connect to MQTT broker.
        
        Returns:
            True if connected successfully, False otherwise.
        """
        if self._connected:
            logger.warning("MQTT relay already connected")
            return True
        
        try:
            # Create client
            client_id = f"phopylslhelper_{threading.get_ident()}"
            self._client = mqtt.Client(client_id=client_id)
            
            # Set callbacks
            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect
            self._client.on_publish = self._on_publish
            
            # Set credentials if provided
            if self.username and self.password:
                self._client.username_pw_set(self.username, self.password)
            
            # Configure TLS if requested
            if self.tls:
                self._client.tls_set()
            
            # Connect
            self._client.connect(self.broker, self.port, self.keepalive)
            
            # Start loop
            self._client.loop_start()
            
            logger.info(f"Connecting to MQTT broker {self.broker}:{self.port}...")
            
            # Wait for connection (with timeout)
            import time
            timeout = 5.0
            start_time = time.time()
            while not self._connected and (time.time() - start_time) < timeout:
                time.sleep(0.1)
            
            if self._connected:
                logger.info(f"Connected to MQTT broker {self.broker}:{self.port}")
                return True
            else:
                logger.error(f"Connection timeout to MQTT broker {self.broker}:{self.port}")
                return False
        
        except Exception as e:
            logger.error(f"Error connecting to MQTT broker: {e}", exc_info=True)
            return False
    
    def disconnect(self):
        """Disconnect from MQTT broker."""
        if not self._connected or not self._client:
            return
        
        try:
            self._client.loop_stop()
            self._client.disconnect()
            self._connected = False
            logger.info("Disconnected from MQTT broker")
        
        except Exception as e:
            logger.error(f"Error disconnecting from MQTT broker: {e}", exc_info=True)
    
    def publish_sample(self, sample: DataSample, topic: str) -> bool:
        """Publish a data sample to MQTT topic.
        
        Args:
            sample: Data sample to publish.
            topic: MQTT topic name.
        
        Returns:
            True if published successfully, False otherwise.
        """
        if not self._connected:
            logger.warning("Not connected to MQTT broker, buffering message")
            with self._lock:
                self._message_queue.append((sample, topic))
            return False
        
        try:
            # Format message
            message = self._formatter.format_sample(sample)
            
            # Publish
            result = self._client.publish(topic, message, qos=self.qos)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                return True
            else:
                logger.error(f"MQTT publish failed with code: {result.rc}")
                return False
        
        except Exception as e:
            logger.error(f"Error publishing sample: {e}", exc_info=True)
            return False
    
    def add_connection_callback(self, callback: Callable[[bool], None]):
        """Add callback for connection status changes.
        
        Args:
            callback: Function called with connection status (True=connected, False=disconnected).
        """
        self._connection_callbacks.append(callback)
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback for MQTT connection."""
        if rc == 0:
            self._connected = True
            logger.info("MQTT connection established")
            
            # Notify callbacks
            for callback in self._connection_callbacks:
                try:
                    callback(True)
                except Exception as e:
                    logger.error(f"Error in connection callback: {e}", exc_info=True)
            
            # Process buffered messages
            self._process_message_queue()
        else:
            logger.error(f"MQTT connection failed with code: {rc}")
            self._connected = False
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback for MQTT disconnection."""
        self._connected = False
        logger.warning("MQTT connection lost")
        
        # Notify callbacks
        for callback in self._connection_callbacks:
            try:
                callback(False)
            except Exception as e:
                logger.error(f"Error in connection callback: {e}", exc_info=True)
    
    def _on_publish(self, client, userdata, mid):
        """Callback for MQTT publish."""
        pass  # Can be used for delivery confirmation if needed
    
    def _process_message_queue(self):
        """Process buffered messages after reconnection."""
        with self._lock:
            while self._message_queue:
                sample, topic = self._message_queue.popleft()
                self.publish_sample(sample, topic)
    
    def is_connected(self) -> bool:
        """Check if connected to MQTT broker.
        
        Returns:
            True if connected, False otherwise.
        """
        return self._connected

