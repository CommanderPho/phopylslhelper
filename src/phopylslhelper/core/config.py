"""Configuration loading and validation for LSL stream tools."""

import os
import re
import yaml
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


def _substitute_env_vars(text: str) -> str:
    """Substitute environment variables in format ${VAR_NAME}."""
    def replace_var(match):
        var_name = match.group(1)
        return os.getenv(var_name, match.group(0))
    
    return re.sub(r'\$\{([^}]+)\}', replace_var, text)


def _load_yaml_with_env_substitution(file_path: Path) -> Dict[str, Any]:
    """Load YAML file and substitute environment variables."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Substitute environment variables
    content = _substitute_env_vars(content)
    
    return yaml.safe_load(content)


@dataclass
class MQTTConfig:
    """MQTT broker configuration."""
    
    broker: str
    port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None
    tls: bool = False
    topics: List[Dict[str, str]] = field(default_factory=list)
    qos: int = 1
    keepalive: int = 60
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MQTTConfig":
        """Create from dictionary."""
        return cls(
            broker=data["broker"],
            port=data.get("port", 1883),
            username=data.get("username"),
            password=data.get("password"),
            tls=data.get("tls", False),
            topics=data.get("topics", []),
            qos=data.get("qos", 1),
            keepalive=data.get("keepalive", 60),
        )


@dataclass
class CloudStreamingConfig:
    """Cloud streaming configuration."""
    
    enabled: bool = False
    mqtt: Optional[MQTTConfig] = None
    
    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "CloudStreamingConfig":
        """Create from dictionary."""
        if not data:
            return cls(enabled=False)
        
        mqtt_config = None
        if data.get("mqtt"):
            mqtt_config = MQTTConfig.from_dict(data["mqtt"])
        
        return cls(
            enabled=data.get("enabled", False),
            mqtt=mqtt_config,
        )


@dataclass
class VisualizationConfig:
    """Visualization configuration."""
    
    backend: str = "mne-lsl"  # Options: "mne-lsl", "pyqt5", "web"
    streams: List[str] = field(default_factory=list)
    update_rate: float = 30.0  # FPS
    buffer_size: int = 1000  # Number of samples to buffer
    
    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "VisualizationConfig":
        """Create from dictionary."""
        if not data:
            return cls()
        
        return cls(
            backend=data.get("backend", "mne-lsl"),
            streams=data.get("streams", []),
            update_rate=data.get("update_rate", 30.0),
            buffer_size=data.get("buffer_size", 1000),
        )


@dataclass
class Config:
    """Main configuration class."""
    
    visualization: VisualizationConfig = field(default_factory=VisualizationConfig)
    cloud_streaming: CloudStreamingConfig = field(default_factory=CloudStreamingConfig)
    log_level: str = "INFO"
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        """Create Config from dictionary."""
        return cls(
            visualization=VisualizationConfig.from_dict(data.get("visualization")),
            cloud_streaming=CloudStreamingConfig.from_dict(data.get("cloud_streaming")),
            log_level=data.get("log_level", "INFO"),
        )
    
    def validate(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []
        
        # Validate visualization backend
        valid_backends = ["mne-lsl", "pyqt5", "web"]
        if self.visualization.backend not in valid_backends:
            errors.append(
                f"Invalid visualization backend: {self.visualization.backend}. "
                f"Must be one of {valid_backends}"
            )
        
        # Validate update rate
        if self.visualization.update_rate <= 0:
            errors.append("Visualization update_rate must be positive")
        
        # Validate buffer size
        if self.visualization.buffer_size <= 0:
            errors.append("Visualization buffer_size must be positive")
        
        # Validate cloud streaming if enabled
        if self.cloud_streaming.enabled:
            if not self.cloud_streaming.mqtt:
                errors.append("Cloud streaming enabled but MQTT configuration missing")
            else:
                if not self.cloud_streaming.mqtt.broker:
                    errors.append("MQTT broker address is required")
                if self.cloud_streaming.mqtt.port < 1 or self.cloud_streaming.mqtt.port > 65535:
                    errors.append("MQTT port must be between 1 and 65535")
        
        return errors


def load_config(config_path: Optional[Path] = None) -> Config:
    """Load configuration from YAML file.
    
    Args:
        config_path: Path to configuration file. If None, searches for
            config.yaml in current directory and common locations.
    
    Returns:
        Config object with loaded settings.
    
    Raises:
        FileNotFoundError: If config file not found.
        ValueError: If configuration is invalid.
    """
    if config_path is None:
        # Search for config file in common locations
        search_paths = [
            Path("config.yaml"),
            Path("config/config.yaml"),
            Path.home() / ".phopylslhelper" / "config.yaml",
        ]
        
        for path in search_paths:
            if path.exists():
                config_path = path
                break
        
        if config_path is None:
            logger.warning("No configuration file found, using defaults")
            return Config()
    
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    try:
        data = _load_yaml_with_env_substitution(config_path)
        config = Config.from_dict(data)
        
        # Validate configuration
        errors = config.validate()
        if errors:
            raise ValueError(f"Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors))
        
        logger.info(f"Configuration loaded from {config_path}")
        return config
    
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in configuration file: {e}")
    except Exception as e:
        raise ValueError(f"Error loading configuration: {e}")

