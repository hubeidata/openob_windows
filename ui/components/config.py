# -*- coding: utf-8 -*-
"""
config.py - Configuration view following AudioBridge Pro design.

Architecture:
- ConfigView: Main view (UI only)
- ConfigController: Business logic and state management
- ConfigModel: Data models for configuration

Design Pattern: MVC with clean separation of concerns.
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass, field
from enum import Enum


# =============================================================================
# MODELS
# =============================================================================

class TransmissionMode(Enum):
    """Transmission mode enum."""
    TX = "TX"
    RX = "RX"


@dataclass
class ConfigState:
    """Configuration state model."""
    # Authentication (future implementation)
    is_logged_in: bool = False
    username: str = ""
    
    # Transmission mode
    transmission_mode: TransmissionMode = TransmissionMode.TX
    
    # VPN (future implementation)
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
    rx_audio_backend: str = "auto"  # 'auto' works on Windows, 'alsa' is Linux only
    rx_alsa_device: str = ""  # Empty for Windows (auto will pick default device)
    
    def get_current_args(self) -> str:
        """Get OpenOB arguments for current mode."""
        if self.transmission_mode == TransmissionMode.TX:
            return self._get_tx_args()
        else:
            return self._get_rx_args()
    
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


@dataclass
class ConfigResult:
    """Result from config view."""
    saved: bool = False
    args: str = ""
    mode: TransmissionMode = TransmissionMode.TX


# =============================================================================
# CONTROLLER
# =============================================================================

class ConfigController:
    """
    Controller for configuration logic.
    
    Responsibilities:
    - Manage configuration state
    - Validate input
    - Provide callbacks for UI events
    """
    
    def __init__(self, initial_state: Optional[ConfigState] = None):
        self._state = initial_state or ConfigState()
        self._on_state_change: Optional[Callable[[ConfigState], None]] = None
    
    @property
    def state(self) -> ConfigState:
        return self._state
    
    def set_on_state_change(self, callback: Callable[[ConfigState], None]) -> None:
        """Set callback for state changes."""
        self._on_state_change = callback
    
    def set_transmission_mode(self, mode: TransmissionMode) -> None:
        """Change transmission mode."""
        self._state.transmission_mode = mode
        self._notify_change()
    
    def set_vpn_enabled(self, enabled: bool) -> None:
        """Toggle VPN (placeholder for future)."""
        self._state.vpn_enabled = enabled
        self._notify_change()
    
    def login(self, username: str, password: str) -> bool:
        """Login (placeholder for future implementation)."""
        # TODO: Implement actual authentication
        self._state.is_logged_in = True
        self._state.username = username
        self._notify_change()
        return True
    
    def logout(self) -> None:
        """Logout (placeholder for future implementation)."""
        self._state.is_logged_in = False
        self._state.username = ""
        self._notify_change()
    
    def update_tx_config(self, **kwargs) -> None:
        """Update TX configuration fields."""
        for key, value in kwargs.items():
            attr_name = f"tx_{key}"
            if hasattr(self._state, attr_name):
                setattr(self._state, attr_name, value)
        self._notify_change()
    
    def update_rx_config(self, **kwargs) -> None:
        """Update RX configuration fields."""
        for key, value in kwargs.items():
            attr_name = f"rx_{key}"
            if hasattr(self._state, attr_name):
                setattr(self._state, attr_name, value)
        self._notify_change()
    
    def get_result(self) -> ConfigResult:
        """Get configuration result."""
        return ConfigResult(
            saved=True,
            args=self._state.get_current_args(),
            mode=self._state.transmission_mode
        )
    
    def _notify_change(self) -> None:
        """Notify UI of state change."""
        if self._on_state_change:
            self._on_state_change(self._state)


# =============================================================================
# VIEW
# =============================================================================

class ConfigView(tk.Toplevel):
    """
    Configuration view following AudioBridge Pro design.
    
    Layout:
    - Header with back button and title
    - Login section (future)
    - Transmission Mode selector
    - VPN toggle (future)
    - Bottom navigation (Home / Settings)
    """
    
    # Colors matching the design
    BG_COLOR = "#f5f5f5"
    HEADER_BG = "#ffffff"
    CARD_BG = "#ffffff"
    TEXT_COLOR = "#333333"
    SECONDARY_TEXT = "#666666"
    ACCENT_COLOR = "#4CAF50"
    DIVIDER_COLOR = "#e0e0e0"
    
    def __init__(
        self,
        parent: tk.Widget,
        controller: Optional[ConfigController] = None,
        on_close: Optional[Callable[[ConfigResult], None]] = None,
        on_home: Optional[Callable[[], None]] = None
    ):
        super().__init__(parent)
        
        self._controller = controller or ConfigController()
        self._on_close_callback = on_close
        self._on_home_callback = on_home
        self._result: Optional[ConfigResult] = None
        
        # Connect controller callbacks
        self._controller.set_on_state_change(self._on_state_changed)
        
        # Window setup
        self._setup_window()
        
        # Create UI
        self._create_widgets()
        
        # Center on parent
        self._center_on_parent(parent)
    
    @property
    def result(self) -> Optional[ConfigResult]:
        return self._result
    
    def _setup_window(self) -> None:
        """Configure window properties."""
        self.title("AudioBridge Pro")
        self.configure(bg=self.BG_COLOR)
        self.resizable(False, False)
        
        # Handle close
        self.protocol("WM_DELETE_WINDOW", self._on_back)
    
    def _create_widgets(self) -> None:
        """Create all UI widgets."""
        # Main container
        main_frame = tk.Frame(self, bg=self.BG_COLOR)
        main_frame.pack(fill="both", expand=True)
        
        # Header
        self._create_header(main_frame)
        
        # Content area
        content = tk.Frame(main_frame, bg=self.BG_COLOR)
        content.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Login section
        self._create_login_section(content)
        
        # Separator
        self._create_separator(content)
        
        # Transmission Mode section
        self._create_transmission_section(content)
        
        # Separator
        self._create_separator(content)
        
        # VPN section
        self._create_vpn_section(content)
        
        # Spacer
        tk.Frame(content, bg=self.BG_COLOR, height=20).pack(fill="x")
        
        # Bottom navigation
        self._create_bottom_nav(main_frame)
    
    def _create_header(self, parent: tk.Frame) -> None:
        """Create header with back button and title."""
        header = tk.Frame(parent, bg=self.HEADER_BG, height=60)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        # Back button
        back_btn = tk.Button(
            header,
            text="<",
            font=("Segoe UI", 18),
            bg=self.HEADER_BG,
            fg=self.TEXT_COLOR,
            bd=0,
            cursor="hand2",
            command=self._on_back
        )
        back_btn.pack(side="left", padx=15, pady=10)
        
        # Title
        title = tk.Label(
            header,
            text="AudioBridge Pro",
            font=("Segoe UI", 18, "bold"),
            bg=self.HEADER_BG,
            fg=self.TEXT_COLOR
        )
        title.pack(side="left", padx=10, pady=10)
    
    def _create_login_section(self, parent: tk.Frame) -> None:
        """Create login/logout section."""
        section = tk.Frame(parent, bg=self.BG_COLOR)
        section.pack(fill="x", pady=(10, 5))
        
        # Login label
        login_label = tk.Label(
            section,
            text="Login",
            font=("Segoe UI", 14, "bold"),
            bg=self.BG_COLOR,
            fg=self.TEXT_COLOR
        )
        login_label.pack(anchor="w")
        
        # Logout button (placeholder)
        logout_frame = tk.Frame(section, bg=self.BG_COLOR)
        logout_frame.pack(fill="x", pady=(5, 0))
        
        logout_label = tk.Label(
            logout_frame,
            text="Logout",
            font=("Segoe UI", 12),
            bg=self.BG_COLOR,
            fg=self.SECONDARY_TEXT,
            cursor="hand2"
        )
        logout_label.pack(anchor="w", padx=10)
        logout_label.bind("<Button-1>", lambda e: self._on_logout())
    
    def _create_separator(self, parent: tk.Frame) -> None:
        """Create a visual separator."""
        sep = tk.Frame(parent, bg=self.DIVIDER_COLOR, height=1)
        sep.pack(fill="x", pady=15)
    
    def _create_transmission_section(self, parent: tk.Frame) -> None:
        """Create transmission mode section."""
        section = tk.Frame(parent, bg=self.BG_COLOR)
        section.pack(fill="x", pady=5)
        
        # Title
        title = tk.Label(
            section,
            text="Transmission Mode",
            font=("Segoe UI", 14, "bold"),
            bg=self.BG_COLOR,
            fg=self.TEXT_COLOR
        )
        title.pack(anchor="w")
        
        # Mode selector frame
        mode_frame = tk.Frame(section, bg=self.BG_COLOR)
        mode_frame.pack(fill="x", pady=(10, 0))
        
        # Current mode variable
        self._mode_var = tk.StringVar(value=self._controller.state.transmission_mode.value)
        
        # Mode dropdown
        mode_row = tk.Frame(mode_frame, bg=self.BG_COLOR)
        mode_row.pack(fill="x", padx=10)
        
        mode_label = tk.Label(
            mode_row,
            textvariable=self._mode_var,
            font=("Segoe UI", 14),
            bg=self.BG_COLOR,
            fg=self.TEXT_COLOR
        )
        mode_label.pack(side="left")
        
        # Dropdown arrow button
        dropdown_btn = tk.Label(
            mode_row,
            text="∨",
            font=("Segoe UI", 12),
            bg=self.BG_COLOR,
            fg=self.SECONDARY_TEXT,
            cursor="hand2"
        )
        dropdown_btn.pack(side="right")
        
        # Bind click to toggle mode
        mode_row.bind("<Button-1>", lambda e: self._toggle_mode())
        mode_label.bind("<Button-1>", lambda e: self._toggle_mode())
        dropdown_btn.bind("<Button-1>", lambda e: self._toggle_mode())
    
    def _create_vpn_section(self, parent: tk.Frame) -> None:
        """Create VPN toggle section."""
        section = tk.Frame(parent, bg=self.BG_COLOR)
        section.pack(fill="x", pady=5)
        
        # VPN row
        vpn_row = tk.Frame(section, bg=self.BG_COLOR)
        vpn_row.pack(fill="x")
        
        vpn_label = tk.Label(
            vpn_row,
            text="VPN",
            font=("Segoe UI", 14),
            bg=self.BG_COLOR,
            fg=self.TEXT_COLOR
        )
        vpn_label.pack(side="left")
        
        # Toggle switch (custom widget)
        self._vpn_var = tk.BooleanVar(value=False)
        self._vpn_toggle = ToggleSwitch(
            vpn_row,
            variable=self._vpn_var,
            command=self._on_vpn_toggle
        )
        self._vpn_toggle.pack(side="right")
    
    def _create_bottom_nav(self, parent: tk.Frame) -> None:
        """Create bottom navigation bar."""
        nav = tk.Frame(parent, bg=self.HEADER_BG, height=70)
        nav.pack(fill="x", side="bottom")
        nav.pack_propagate(False)
        
        # Separator line
        sep = tk.Frame(nav, bg=self.DIVIDER_COLOR, height=1)
        sep.pack(fill="x")
        
        # Navigation buttons frame
        btn_frame = tk.Frame(nav, bg=self.HEADER_BG)
        btn_frame.pack(fill="both", expand=True)
        
        # Home button
        home_frame = tk.Frame(btn_frame, bg=self.HEADER_BG)
        home_frame.pack(side="left", expand=True, fill="both")
        
        home_icon = tk.Label(
            home_frame,
            text="🏠",
            font=("Segoe UI", 20),
            bg=self.HEADER_BG,
            fg=self.TEXT_COLOR,
            cursor="hand2"
        )
        home_icon.pack(pady=(8, 0))
        
        home_label = tk.Label(
            home_frame,
            text="Home",
            font=("Segoe UI", 10),
            bg=self.HEADER_BG,
            fg=self.TEXT_COLOR
        )
        home_label.pack()
        
        # Bind home click
        home_frame.bind("<Button-1>", lambda e: self._on_home())
        home_icon.bind("<Button-1>", lambda e: self._on_home())
        home_label.bind("<Button-1>", lambda e: self._on_home())
        
        # Settings button (Config)
        settings_frame = tk.Frame(btn_frame, bg=self.HEADER_BG)
        settings_frame.pack(side="right", expand=True, fill="both")
        
        settings_icon = tk.Label(
            settings_frame,
            text="⚙",
            font=("Segoe UI", 20),
            bg=self.HEADER_BG,
            fg=self.TEXT_COLOR,
            cursor="hand2"
        )
        settings_icon.pack(pady=(8, 0))
        
        settings_label = tk.Label(
            settings_frame,
            text="Config",
            font=("Segoe UI", 10),
            bg=self.HEADER_BG,
            fg=self.TEXT_COLOR
        )
        settings_label.pack()
        
        # Bind settings click to open detailed config
        settings_frame.bind("<Button-1>", lambda e: self._on_open_detailed_config())
        settings_icon.bind("<Button-1>", lambda e: self._on_open_detailed_config())
        settings_label.bind("<Button-1>", lambda e: self._on_open_detailed_config())
    
    def _center_on_parent(self, parent: tk.Widget) -> None:
        """Center window on parent and make modal."""
        # Set size
        self.geometry("400x550")
        self.minsize(380, 500)
        
        # Update geometry
        self.update_idletasks()
        parent.update_idletasks()
        
        # Calculate center position
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        
        self.geometry(f"400x550+{x}+{y}")
        
        # Make modal
        self.transient(parent)
        self.grab_set()
        self.focus_set()
    
    # Event handlers
    
    def _on_back(self) -> None:
        """Handle back button click."""
        self._result = self._controller.get_result()
        if self._on_close_callback:
            self._on_close_callback(self._result)
        self.destroy()
    
    def _on_home(self) -> None:
        """Handle home button click."""
        self._result = self._controller.get_result()
        if self._on_home_callback:
            self._on_home_callback()
        if self._on_close_callback:
            self._on_close_callback(self._result)
        self.destroy()
    
    def _on_logout(self) -> None:
        """Handle logout click (placeholder)."""
        self._controller.logout()
        # TODO: Implement logout UI feedback
    
    def _toggle_mode(self) -> None:
        """Toggle between TX and RX modes."""
        current = self._controller.state.transmission_mode
        new_mode = TransmissionMode.RX if current == TransmissionMode.TX else TransmissionMode.TX
        self._controller.set_transmission_mode(new_mode)
        self._mode_var.set(new_mode.value)
    
    def _on_vpn_toggle(self) -> None:
        """Handle VPN toggle (placeholder)."""
        self._controller.set_vpn_enabled(self._vpn_var.get())
        # TODO: Implement VPN functionality
    
    def _on_open_detailed_config(self) -> None:
        """Open detailed configuration dialog."""
        from .dialogs import SettingsDialog
        from ..core.models import LinkConfig
        
        # Create LinkConfig from current state
        state = self._controller.state
        
        if state.transmission_mode == TransmissionMode.TX:
            config = LinkConfig(
                config_host=state.tx_config_host,
                node_id=state.tx_node_name,
                link_name=state.tx_link_name,
                link_mode="tx",
                peer_ip=state.tx_peer_ip,
                encoding=state.tx_encoding,
                sample_rate=state.tx_sample_rate,
                jitter_buffer=state.tx_jitter_buffer,
                audio_backend=state.tx_audio_backend
            )
        else:
            config = LinkConfig(
                config_host=state.rx_config_host,
                node_id=state.rx_node_name,
                link_name=state.rx_link_name,
                link_mode="rx",
                audio_backend=state.rx_audio_backend
            )
        
        dialog = SettingsDialog(self, config)
        self.wait_window(dialog)
        
        if dialog.result and dialog.result.saved:
            # Update controller state from dialog result
            self._update_from_args(dialog.result.args)
    
    def _update_from_args(self, args: str) -> None:
        """Update controller state from args string."""
        from ..core.models import LinkConfig
        
        config = LinkConfig.from_args(args)
        
        if config.link_mode == "tx":
            self._controller.set_transmission_mode(TransmissionMode.TX)
            self._controller.update_tx_config(
                config_host=config.config_host or "",
                node_name=config.node_id or "",
                link_name=config.link_name or "",
                peer_ip=config.peer_ip or "",
                encoding=config.encoding or "",
                sample_rate=config.sample_rate or "",
                jitter_buffer=config.jitter_buffer or "",
                audio_backend=config.audio_backend or ""
            )
        else:
            self._controller.set_transmission_mode(TransmissionMode.RX)
            self._controller.update_rx_config(
                config_host=config.config_host or "",
                node_name=config.node_id or "",
                link_name=config.link_name or "",
                audio_backend=config.audio_backend or ""
            )
        
        self._mode_var.set(self._controller.state.transmission_mode.value)
    
    def _on_state_changed(self, state: ConfigState) -> None:
        """Handle controller state changes."""
        self._mode_var.set(state.transmission_mode.value)
        self._vpn_var.set(state.vpn_enabled)


# =============================================================================
# CUSTOM WIDGETS
# =============================================================================

class ToggleSwitch(tk.Canvas):
    """
    Custom toggle switch widget.
    
    Matches iOS/Android style toggle design.
    """
    
    WIDTH = 50
    HEIGHT = 26
    
    OFF_BG = "#cccccc"
    ON_BG = "#4CAF50"
    KNOB_COLOR = "#ffffff"
    
    def __init__(
        self,
        parent: tk.Widget,
        variable: Optional[tk.BooleanVar] = None,
        command: Optional[Callable[[], None]] = None,
        **kwargs
    ):
        super().__init__(
            parent,
            width=self.WIDTH,
            height=self.HEIGHT,
            highlightthickness=0,
            **kwargs
        )
        
        self._variable = variable or tk.BooleanVar(value=False)
        self._command = command
        
        # Draw initial state
        self._draw()
        
        # Bind click
        self.bind("<Button-1>", self._on_click)
        
        # Watch variable changes
        self._variable.trace_add("write", lambda *_: self._draw())
    
    def _draw(self) -> None:
        """Draw the toggle switch."""
        self.delete("all")
        
        is_on = self._variable.get()
        
        # Background pill shape
        bg_color = self.ON_BG if is_on else self.OFF_BG
        radius = self.HEIGHT // 2
        
        # Draw rounded rectangle
        self.create_oval(0, 0, self.HEIGHT, self.HEIGHT, fill=bg_color, outline="")
        self.create_oval(self.WIDTH - self.HEIGHT, 0, self.WIDTH, self.HEIGHT, fill=bg_color, outline="")
        self.create_rectangle(radius, 0, self.WIDTH - radius, self.HEIGHT, fill=bg_color, outline="")
        
        # Draw knob
        knob_x = self.WIDTH - radius - 2 if is_on else radius + 2
        knob_radius = radius - 3
        
        self.create_oval(
            knob_x - knob_radius,
            (self.HEIGHT // 2) - knob_radius,
            knob_x + knob_radius,
            (self.HEIGHT // 2) + knob_radius,
            fill=self.KNOB_COLOR,
            outline=""
        )
    
    def _on_click(self, event: tk.Event) -> None:
        """Handle click to toggle state."""
        self._variable.set(not self._variable.get())
        if self._command:
            self._command()


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def open_config_view(
    parent: tk.Widget,
    current_mode: str = "tx",
    on_save: Optional[Callable[[str], None]] = None
) -> ConfigResult:
    """
    Factory function to open config view.
    
    Args:
        parent: Parent window
        current_mode: Current transmission mode ('tx' or 'rx')
        on_save: Callback when configuration is saved
        
    Returns:
        ConfigResult with saved configuration
    """
    # Create initial state
    state = ConfigState(
        transmission_mode=TransmissionMode.TX if current_mode == "tx" else TransmissionMode.RX
    )
    
    controller = ConfigController(state)
    result_holder = [None]
    
    def on_close(result: ConfigResult):
        result_holder[0] = result
        if result.saved and on_save:
            on_save(result.args)
    
    view = ConfigView(parent, controller, on_close=on_close)
    parent.wait_window(view)
    
    return result_holder[0] or ConfigResult(saved=False)
