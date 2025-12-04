# -*- coding: utf-8 -*-
"""
config_storage.py - Persistent configuration storage service.

Handles saving and loading application settings to/from JSON file.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger('openob.ui.config_storage')


@dataclass
class SavedConfig:
    """Persistent configuration that is saved to disk."""
    # Transmission mode: 'tx' or 'rx'
    transmission_mode: str = 'tx'
    
    # VPN settings (for future use)
    vpn_enabled: bool = False
    
    # TX Configuration
    tx_config_host: str = "127.0.0.1"
    tx_node_name: str = "emetteur"
    tx_link_name: str = "transmission"
    tx_peer_ip: str = "192.168.1.17"
    tx_encoding: str = "pcm"
    tx_sample_rate: str = "48000"
    tx_jitter_buffer: str = "60"
    tx_audio_backend: str = "auto"
    
    # RX Configuration
    rx_config_host: str = "192.168.1.15"
    rx_node_name: str = "recepteur"
    rx_link_name: str = "transmission"
    rx_audio_backend: str = "auto"
    rx_alsa_device: str = ""
    
    # Auto-start setting
    auto_start: bool = True
    
    def get_current_args(self) -> str:
        """Get OpenOB arguments for current mode."""
        if self.transmission_mode == 'rx':
            return self._get_rx_args()
        else:
            return self._get_tx_args()
    
    def _get_tx_args(self) -> str:
        """Build TX mode arguments."""
        parts = [
            self.tx_config_host,
            self.tx_node_name,
            self.tx_link_name,
            "tx",
            self.tx_peer_ip,
        ]
        
        if self.tx_encoding:
            parts.extend(["-e", self.tx_encoding])
        if self.tx_sample_rate:
            parts.extend(["-r", self.tx_sample_rate])
        if self.tx_jitter_buffer:
            parts.extend(["-j", self.tx_jitter_buffer])
        if self.tx_audio_backend:
            parts.extend(["-a", self.tx_audio_backend])
        
        return " ".join(parts)
    
    def _get_rx_args(self) -> str:
        """Build RX mode arguments."""
        parts = [
            self.rx_config_host,
            self.rx_node_name,
            self.rx_link_name,
            "rx",
        ]
        
        if self.rx_audio_backend:
            parts.extend(["-a", self.rx_audio_backend])
        if self.rx_alsa_device:
            parts.extend(["-d", self.rx_alsa_device])
        
        return " ".join(parts)


class ConfigStorageService:
    """
    Service for persisting application configuration.
    
    Saves/loads configuration to a JSON file in the app directory.
    """
    
    DEFAULT_FILENAME = "app_settings.json"
    
    def __init__(self, config_dir: Path):
        """
        Initialize config storage.
        
        Args:
            config_dir: Directory to store configuration file
        """
        self._config_dir = config_dir
        self._config_file = config_dir / self.DEFAULT_FILENAME
        self._config: SavedConfig = SavedConfig()
        
    @property
    def config(self) -> SavedConfig:
        """Get current configuration."""
        return self._config
    
    @property
    def config_file(self) -> Path:
        """Get config file path."""
        return self._config_file
    
    def load(self) -> SavedConfig:
        """
        Load configuration from file.
        
        Returns:
            SavedConfig: Loaded configuration, or defaults if file doesn't exist
        """
        if not self._config_file.exists():
            logger.info(f"Config file not found, using defaults: {self._config_file}")
            return self._config
        
        try:
            with open(self._config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Update config with loaded values
            self._config = SavedConfig(
                transmission_mode=data.get('transmission_mode', 'tx'),
                vpn_enabled=data.get('vpn_enabled', False),
                tx_config_host=data.get('tx_config_host', '127.0.0.1'),
                tx_node_name=data.get('tx_node_name', 'emetteur'),
                tx_link_name=data.get('tx_link_name', 'transmission'),
                tx_peer_ip=data.get('tx_peer_ip', '192.168.1.17'),
                tx_encoding=data.get('tx_encoding', 'pcm'),
                tx_sample_rate=data.get('tx_sample_rate', '48000'),
                tx_jitter_buffer=data.get('tx_jitter_buffer', '60'),
                tx_audio_backend=data.get('tx_audio_backend', 'auto'),
                rx_config_host=data.get('rx_config_host', '192.168.1.15'),
                rx_node_name=data.get('rx_node_name', 'recepteur'),
                rx_link_name=data.get('rx_link_name', 'transmission'),
                rx_audio_backend=data.get('rx_audio_backend', 'auto'),
                rx_alsa_device=data.get('rx_alsa_device', ''),
                auto_start=data.get('auto_start', True),
            )
            
            logger.info(f"Loaded config from {self._config_file}: mode={self._config.transmission_mode}")
            return self._config
            
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return self._config
    
    def save(self) -> bool:
        """
        Save current configuration to file.
        
        Returns:
            bool: True if saved successfully
        """
        try:
            # Ensure directory exists
            self._config_dir.mkdir(parents=True, exist_ok=True)
            
            # Convert to dict
            data = asdict(self._config)
            
            # Save to file
            with open(self._config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved config to {self._config_file}: mode={self._config.transmission_mode}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return False
    
    def update(self, **kwargs) -> None:
        """
        Update configuration values.
        
        Args:
            **kwargs: Configuration keys and values to update
        """
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
    
    def update_from_args(self, args: str, mode: str) -> None:
        """
        Update configuration from OpenOB argument string.
        
        Args:
            args: OpenOB command line arguments
            mode: 'tx' or 'rx'
        """
        self._config.transmission_mode = mode
        
        parts = args.split()
        if len(parts) < 4:
            return
        
        if mode == 'tx':
            self._config.tx_config_host = parts[0] if len(parts) > 0 else self._config.tx_config_host
            self._config.tx_node_name = parts[1] if len(parts) > 1 else self._config.tx_node_name
            self._config.tx_link_name = parts[2] if len(parts) > 2 else self._config.tx_link_name
            # parts[3] is 'tx'
            self._config.tx_peer_ip = parts[4] if len(parts) > 4 else self._config.tx_peer_ip
            
            # Parse options
            i = 5
            while i < len(parts):
                if parts[i] == '-e' and i + 1 < len(parts):
                    self._config.tx_encoding = parts[i + 1]
                    i += 2
                elif parts[i] == '-r' and i + 1 < len(parts):
                    self._config.tx_sample_rate = parts[i + 1]
                    i += 2
                elif parts[i] == '-j' and i + 1 < len(parts):
                    self._config.tx_jitter_buffer = parts[i + 1]
                    i += 2
                elif parts[i] == '-a' and i + 1 < len(parts):
                    self._config.tx_audio_backend = parts[i + 1]
                    i += 2
                else:
                    i += 1
        else:  # rx
            self._config.rx_config_host = parts[0] if len(parts) > 0 else self._config.rx_config_host
            self._config.rx_node_name = parts[1] if len(parts) > 1 else self._config.rx_node_name
            self._config.rx_link_name = parts[2] if len(parts) > 2 else self._config.rx_link_name
            # parts[3] is 'rx'
            
            # Parse options
            i = 4
            while i < len(parts):
                if parts[i] == '-a' and i + 1 < len(parts):
                    self._config.rx_audio_backend = parts[i + 1]
                    i += 2
                elif parts[i] == '-d' and i + 1 < len(parts):
                    self._config.rx_alsa_device = parts[i + 1]
                    i += 2
                else:
                    i += 1
