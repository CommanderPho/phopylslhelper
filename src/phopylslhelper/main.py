"""Main CLI entry point for LSL stream tools."""

import argparse
import sys
import signal
import logging
from pathlib import Path
from typing import Optional, List

from phopylslhelper.core import (
    LSLStreamManager,
    LSLStreamReader,
    load_config,
    setup_logging,
    StreamInfo,
)
from phopylslhelper.visualization import create_backend, list_available_backends
from phopylslhelper.streaming import (
    MQTTRelay,
    TimestampManager,
    MetricsCollector,
    ReliabilityManager,
)

logger = logging.getLogger(__name__)


class LSLStreamApplication:
    """Main application for LSL stream visualization and cloud streaming."""
    
    def __init__(self, config_path: Optional[Path] = None):
        """Initialize application.
        
        Args:
            config_path: Path to configuration file.
        """
        # Load configuration
        try:
            self.config = load_config(config_path)
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            sys.exit(1)
        
        # Setup logging
        setup_logging(self.config.log_level)
        
        # Initialize components
        self.stream_manager = LSLStreamManager()
        self.readers: List[LSLStreamReader] = []
        self.visualization_backends = []
        self.mqtt_relays: dict[str, MQTTRelay] = {}
        self.timestamp_manager = TimestampManager()
        self.metrics_collector = MetricsCollector()
        self.reliability_manager = ReliabilityManager()
        
        # Shutdown flag
        self._shutdown_requested = False
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info("Shutdown signal received")
        self._shutdown_requested = True
    
    def list_streams(self):
        """List available LSL streams."""
        print("Discovering LSL streams...")
        streams = self.stream_manager.discover_streams()
        
        if not streams:
            print("No streams found.")
            return
        
        print(f"\nFound {len(streams)} stream(s):\n")
        for i, stream in enumerate(streams, 1):
            print(f"{i}. {stream.name}")
            print(f"   Type: {stream.type}")
            print(f"   Channels: {stream.channel_count}")
            print(f"   Sampling Rate: {stream.nominal_srate} Hz")
            print(f"   Format: {stream.channel_format}")
            print(f"   Status: {stream.status.value}")
            if stream.uid:
                print(f"   UID: {stream.uid}")
            print()
    
    def visualize_streams(self, stream_names: Optional[List[str]] = None):
        """Start visualization for specified streams.
        
        Args:
            stream_names: List of stream names to visualize. If None, uses config.
        """
        if stream_names is None:
            stream_names = self.config.visualization.streams
        
        if not stream_names:
            print("No streams specified for visualization.")
            print("Available backends:", ", ".join(list_available_backends()))
            return
        
        # Discover streams
        print("Discovering streams...")
        discovered = self.stream_manager.discover_streams()
        
        # Find requested streams
        streams_to_visualize = []
        for name in stream_names:
            found = [s for s in discovered if s.name == name or (s.uid and s.uid == name)]
            if found:
                streams_to_visualize.append(found[0])
            else:
                logger.warning(f"Stream '{name}' not found")
        
        if not streams_to_visualize:
            print("No matching streams found.")
            return
        
        # Create visualization backend
        backend_type = self.config.visualization.backend
        try:
            backend = create_backend(backend_type)
        except Exception as e:
            logger.error(f"Failed to create visualization backend: {e}")
            return
        
        # Setup visualization for each stream
        for stream_info in streams_to_visualize:
            print(f"Setting up visualization for {stream_info.name}...")
            
            # Create reader
            reader = LSLStreamReader(
                self.stream_manager,
                stream_info.uid or stream_info.name,
                buffer_size=self.config.visualization.buffer_size,
            )
            
            # Setup visualization callback
            backend.set_stream(stream_info)
            if not backend.start():
                logger.error(f"Failed to start visualization backend")
                continue
            
            # Start reader with visualization callback
            def update_callback(sample):
                backend.update(sample)
            
            reader.sample_callback = update_callback
            
            if not reader.start():
                logger.error(f"Failed to start reader for {stream_info.name}")
                continue
            
            self.readers.append(reader)
            self.visualization_backends.append(backend)
        
        print("\nVisualization started. Press Ctrl+C to stop.")
        
        # Run until shutdown
        try:
            import time
            while not self._shutdown_requested:
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        
        # Cleanup
        self._cleanup()
    
    def stream_to_cloud(self, stream_names: Optional[List[str]] = None):
        """Stream LSL data to cloud via MQTT.
        
        Args:
            stream_names: List of stream names to stream. If None, uses config.
        """
        if not self.config.cloud_streaming.enabled:
            print("Cloud streaming is disabled in configuration.")
            return
        
        if not self.config.cloud_streaming.mqtt:
            print("MQTT configuration missing.")
            return
        
        mqtt_config = self.config.cloud_streaming.mqtt
        
        # Setup MQTT relay
        mqtt_relay = MQTTRelay(
            broker=mqtt_config.broker,
            port=mqtt_config.port,
            username=mqtt_config.username,
            password=mqtt_config.password,
            tls=mqtt_config.tls,
            qos=mqtt_config.qos,
            keepalive=mqtt_config.keepalive,
        )
        
        # Connect with retry
        if not self.reliability_manager.execute_with_retry(
            mqtt_relay.connect,
            on_retry=lambda attempt, error: print(f"Connection attempt {attempt} failed, retrying..."),
        ):
            logger.error("Failed to connect to MQTT broker")
            return
        
        # Start metrics collection
        self.metrics_collector.start()
        
        # Setup stream-to-topic mapping
        topic_map = {item["stream"]: item["topic"] for item in mqtt_config.topics}
        
        if stream_names is None:
            stream_names = list(topic_map.keys())
        
        # Discover and connect to streams
        print("Discovering streams...")
        discovered = self.stream_manager.discover_streams()
        
        streams_to_stream = []
        for name in stream_names:
            found = [s for s in discovered if s.name == name or (s.uid and s.uid == name)]
            if found:
                streams_to_stream.append(found[0])
            else:
                logger.warning(f"Stream '{name}' not found")
        
        if not streams_to_stream:
            print("No matching streams found.")
            return
        
        # Create readers and publish data
        for stream_info in streams_to_stream:
            stream_id = stream_info.uid or stream_info.name
            topic = topic_map.get(stream_info.name, f"lsl/{stream_info.type}/{stream_id}")
            
            print(f"Streaming {stream_info.name} to {topic}...")
            
            # Create reader
            reader = LSLStreamReader(
                self.stream_manager,
                stream_id,
            )
            
            # Setup publishing callback
            inlet = self.stream_manager.get_stream_inlet(stream_id)
            
            def publish_callback(sample):
                # Enrich with timestamp metadata
                enriched = self.timestamp_manager.enrich_sample(sample, inlet)
                
                # Publish
                if mqtt_relay.publish_sample(enriched, topic):
                    self.metrics_collector.record_sample_sent(len(str(enriched.to_dict())))
                else:
                    self.metrics_collector.record_sample_dropped()
            
            reader.sample_callback = publish_callback
            
            if not reader.start():
                logger.error(f"Failed to start reader for {stream_info.name}")
                continue
            
            self.readers.append(reader)
            self.mqtt_relays[stream_id] = mqtt_relay
        
        print("\nStreaming to cloud. Press Ctrl+C to stop.")
        
        # Run until shutdown
        try:
            import time
            while not self._shutdown_requested:
                time.sleep(1.0)
                # Print metrics periodically
                if self.metrics_collector.metrics.samples_sent % 100 == 0:
                    print(self.metrics_collector.get_summary())
        except KeyboardInterrupt:
            pass
        
        # Cleanup
        self._cleanup()
        print("\nFinal metrics:")
        print(self.metrics_collector.get_summary())
    
    def _cleanup(self):
        """Clean up resources."""
        logger.info("Cleaning up...")
        
        # Stop readers
        for reader in self.readers:
            reader.stop()
        
        # Stop visualization backends
        for backend in self.visualization_backends:
            backend.stop()
        
        # Disconnect MQTT relays
        for relay in self.mqtt_relays.values():
            relay.disconnect()
        
        # Cleanup stream manager
        self.stream_manager.cleanup()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="LSL Stream Tools - Visualization and Cloud Streaming"
    )
    
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # List streams command
    subparsers.add_parser("list", help="List available LSL streams")
    
    # Visualize command
    viz_parser = subparsers.add_parser("visualize", help="Visualize LSL streams")
    viz_parser.add_argument(
        "--streams",
        nargs="+",
        help="Stream names to visualize",
    )
    
    # Stream command
    stream_parser = subparsers.add_parser("stream", help="Stream LSL data to cloud")
    stream_parser.add_argument(
        "--streams",
        nargs="+",
        help="Stream names to stream",
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Create application
    app = LSLStreamApplication(config_path=args.config)
    
    # Execute command
    if args.command == "list":
        app.list_streams()
    
    elif args.command == "visualize":
        app.visualize_streams(stream_names=args.streams)
    
    elif args.command == "stream":
        app.stream_to_cloud(stream_names=args.streams)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

