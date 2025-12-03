# -*- coding: utf-8 -*-
"""
models.py - Data models and application state.

Design decisions:
- Dataclasses for immutable configuration and state objects
- Separate VU state for local (input) and remote (receiver) meters
- Clear separation between configuration and runtime state
"""

from dataclasses import dataclass, field
from typing import Optional, Dict
from pathlib import Path


@dataclass
class AppConfig:
    """Application configuration paths and constants."""
    repo_root: Path
    venv_python: Path
    openob_script: Path
    start_script: Path
    gstreamer_bin: Path
    gstreamer_gir: Path
    log_dir: Path
    ui_log_file: Path
    icon_path: Path
    
    # UI dimensions
    width: int = 960
    height: int = 700
    
    # Default OpenOB arguments
    # Formato: <config-host> <node-name> <link-name> <mode> [peer-ip] -e <encoding> -r <sample-rate> -j <jitter> -a <audio>
    default_args: str = '127.0.0.1 emetteur transmission tx 192.168.1.17 -e pcm -r 48000 -j 60 -a auto'
    
    @property
    def center_x(self) -> int:
        return self.width // 2


@dataclass
class VUState:
    """VU meter state for a single channel pair (stereo)."""
    left: float = 0.0
    right: float = 0.0
    has_real_data: bool = False
    
    def decay(self, factor: float = 0.85, threshold: float = 0.01) -> None:
        """Apply decay to levels."""
        self.left *= factor
        self.right *= factor
        if self.left < threshold:
            self.left = 0.0
        if self.right < threshold:
            self.right = 0.0
    
    @property
    def average(self) -> float:
        """Get average level."""
        return (self.left + self.right) / 2.0
    
    @property
    def max_level(self) -> float:
        """Get maximum of both channels."""
        return max(self.left, self.right)


@dataclass
class LinkConfig:
    """OpenOB link configuration parsed from arguments."""
    config_host: Optional[str] = None
    node_id: Optional[str] = None
    link_name: Optional[str] = None
    link_mode: Optional[str] = None  # 'tx' or 'rx'
    peer_ip: Optional[str] = None
    encoding: str = 'pcm'
    sample_rate: str = ''
    jitter_buffer: str = ''
    audio_backend: str = 'auto'
    
    @classmethod
    def from_args(cls, args_string: str) -> 'LinkConfig':
        """Parse LinkConfig from command line arguments string."""
        import shlex
        try:
            parts = shlex.split(args_string)
        except Exception:
            parts = args_string.split()
        
        config = cls()
        if len(parts) >= 1:
            config.config_host = parts[0]
        if len(parts) >= 2:
            config.node_id = parts[1]
        if len(parts) >= 3:
            config.link_name = parts[2]
        if len(parts) >= 4:
            config.link_mode = parts[3]
        if len(parts) >= 5 and not parts[4].startswith('-'):
            config.peer_ip = parts[4]
        
        # Parse options
        i = 5 if config.peer_ip else 4
        while i < len(parts):
            opt = parts[i]
            if opt == '-e' and i + 1 < len(parts):
                config.encoding = parts[i + 1]
                i += 2
            elif opt == '-r' and i + 1 < len(parts):
                config.sample_rate = parts[i + 1]
                i += 2
            elif opt == '-j' and i + 1 < len(parts):
                config.jitter_buffer = parts[i + 1]
                i += 2
            elif opt == '-a' and i + 1 < len(parts):
                config.audio_backend = parts[i + 1]
                i += 2
            else:
                i += 1
        
        return config
    
    def to_args(self) -> str:
        """Convert back to command line arguments string."""
        parts = []
        if self.config_host:
            parts.append(self.config_host)
        if self.node_id:
            parts.append(self.node_id)
        if self.link_name:
            parts.append(self.link_name)
        if self.link_mode:
            parts.append(self.link_mode)
        if self.link_mode == 'tx' and self.peer_ip:
            parts.append(self.peer_ip)
        
        if self.encoding:
            parts.extend(['-e', self.encoding])
        if self.sample_rate:
            parts.extend(['-r', self.sample_rate])
        if self.jitter_buffer:
            parts.extend(['-j', self.jitter_buffer])
        if self.audio_backend:
            parts.extend(['-a', self.audio_backend])
        
        return ' '.join(parts)


@dataclass
class AppState:
    """Runtime application state."""
    # VU meter states
    local_vu: VUState = field(default_factory=VUState)
    remote_vu: VUState = field(default_factory=VUState)
    receiver_level: float = 0.0
    
    # Service states
    redis_running: bool = False
    openob_running: bool = False
    
    # UI states
    logs_visible: bool = False
    auto_start_enabled: bool = True
    auto_started: bool = False
    cooldown_active: bool = False
    cooldown_remaining: int = 0
    
    # Diagnostic state
    vu_diag_state: Dict[str, Optional[str]] = field(default_factory=lambda: {'local': None, 'remote': None})


# VU meter visual configuration
@dataclass
class VUVisualConfig:
    """Configuration for VU meter visual appearance."""
    # Circular VU
    outer_radius: int = 130
    center_radius: int = 95
    num_rings: int = 9
    ring_spacing: int = 10
    arc_extent: int = 50
    
    # Thresholds for each ring (9 rings)
    ring_thresholds: tuple = (0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.78, 0.90)
    
    # Colors for each ring (green -> yellow -> red gradient)
    ring_colors: tuple = (
        "#3fbf5f",  # Ring 0 - green
        "#3fbf5f",  # Ring 1 - green  
        "#3fbf5f",  # Ring 2 - green
        "#5fcf5f",  # Ring 3 - light green
        "#7fdf5f",  # Ring 4 - yellow-green
        "#bfef3f",  # Ring 5 - lime
        "#f2c94c",  # Ring 6 - yellow
        "#f0a030",  # Ring 7 - orange
        "#e04b4b",  # Ring 8 - red
    )
    
    inactive_color: str = "#cfcfcf"
    
    # Receiver bar
    bar_width: int = 500
    bar_height: int = 20
    bar_green: str = "#3fbf5f"
    bar_yellow: str = "#f2c94c"
    bar_red: str = "#e04b4b"
