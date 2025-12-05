# -*- coding: utf-8 -*-
"""
main_window.py - Main application window.

Design decisions:
- MainWindow only handles UI layout and event binding
- All business logic delegated to AppController
- Matches original main.py design exactly:
  * White background (#ffffff)
  * Single central VU meter with input_line.png icon
  * Horizontal receiver bar below
  * Start/Stop toggle button
  * Settings button bottom-right
  * Auto-start checkbox bottom-left
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from PIL import Image, ImageTk
from typing import Optional
import math
import random
import time

from .core.models import AppConfig, AppState, LinkConfig
from .core.controller import AppController
from .services.utils import get_logger

logger = get_logger(__name__)


class MainWindow:
    """
    Main application window for OpenOB broadcast control.
    Matches the original main.py design exactly.
    """
    
    def __init__(self, root: tk.Tk, config: AppConfig):
        self.root = root
        self.config = config
        
        # Initialize controller
        self.controller = AppController(config)
        self.controller.set_root(root)
        self.controller.initialize()  # Parse default args and check requirements
        
        # Connect controller callbacks
        self.controller.callbacks.on_log = self._on_log_message
        
        # VU state
        self.vu_left = 0.0
        self.vu_right = 0.0
        self.receiver_level = 0.0
        self._has_real_vu_data = {'local': False, 'remote': False}
        
        # Visual parameters
        self.outer_radius = 130
        self.red_center_radius = 95
        
        # Logs visibility
        self._logs_visible = False
        self._auto_started = False
        
        # Window configuration
        self._setup_window()
        
        # Create UI
        self._configure_styles()
        self._create_canvas()
        self._draw_header()
        self._draw_vu_circle()
        self._draw_receiver_bar()
        self._draw_status_cards()
        self._draw_control_buttons()
        self._create_logs_panel()
        self._load_center_icon()
        
        # Bind events
        self._bind_events()
        
        # Start update loops
        self._start_update_loops()
        
        logger.info("MainWindow initialized")
    
    def _setup_window(self) -> None:
        """Configure main window properties."""
        self.root.title('OBBroadcast Controller')
        self.root.geometry(f'{self.config.width}x{self.config.height}')
        self.root.configure(bg='#ffffff')
        self.root.resizable(False, False)
        
        # Set application icon
        self._set_app_icon()
        
        # Protocol handlers
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
    
    def _set_app_icon(self) -> None:
        """Set application window icon."""
        try:
            img_png = self.config.repo_root / 'ui' / 'images' / 'ob-logo.png'
            img_ico = self.config.repo_root / 'ui' / 'images' / 'ob-logo.ico'
            if img_png.exists():
                self._icon_img = tk.PhotoImage(file=str(img_png))
                try:
                    self.root.iconphoto(False, self._icon_img)
                except Exception:
                    pass
            if img_ico.exists():
                try:
                    self.root.iconbitmap(str(img_ico))
                except Exception:
                    pass
        except Exception:
            pass
    
    def _configure_styles(self) -> None:
        """Configure ttk styles."""
        style = ttk.Style(self.root)
        style.configure('Primary.TButton', font=('Segoe UI', 14, 'bold'), padding=(16, 8))
        style.configure('Secondary.TButton', font=('Segoe UI', 14), padding=(16, 8))
        style.configure('Settings.TButton', font=('Segoe UI', 12), padding=(8, 4))
        style.configure('Stop.TButton', font=('Segoe UI', 16), padding=(12, 8))
        style.configure('Start.TButton', font=('Segoe UI', 16), padding=(12, 8))
    
    def _create_canvas(self) -> None:
        """Create main canvas with white background."""
        self.canvas = tk.Canvas(
            self.root,
            width=self.config.width,
            height=self.config.height,
            bg='#ffffff',
            highlightthickness=0
        )
        self.canvas.pack(fill='both', expand=True)
    
    def _draw_header(self) -> None:
        """Draw the header with title and dynamic status."""
        cx = self.config.center_x
        
        # Main title (changes based on mode: TX/RX)
        self._title_text_id = self.canvas.create_text(
            cx, 45,
            text="OBBroadcast TX",
            font=("Segoe UI", 32, "bold"),
            fill="#111111",
            tags='header'
        )
        
        # Dynamic status text (Transmitting / Stopped / Receiving)
        self._status_text_id = self.canvas.create_text(
            cx, 90,
            text="Stopped",
            font=("Segoe UI", 48, "bold"),
            fill="#c62828",
            tags='header'
        )
    
    def _draw_vu_circle(self) -> None:
        """Draw the single central circular VU meter."""
        cx = self.config.center_x
        center_y = 290
        
        # Gray outer ring (background)
        r_outer = self.outer_radius
        self.canvas.create_oval(
            cx - r_outer, center_y - r_outer,
            cx + r_outer, center_y + r_outer,
            fill="#d0d3d6", outline="", tags='vu_bg'
        )
        
        # Red center circle
        r_red = self.red_center_radius
        self.canvas.create_oval(
            cx - r_red, center_y - r_red,
            cx + r_red, center_y + r_red,
            fill="#d9534f", outline="", tags='vu_center'
        )
        
        # Audio Input/Output label (changes based on mode)
        self._vu_label_id = self.canvas.create_text(
            cx, center_y - r_red - 22,
            text="Audio Input",
            font=("Segoe UI", 11, "bold"),
            fill="#333333",
            anchor='s',
            tags='label'
        )
        
        # VU arc segments
        self.segment_ids = []
        rings = 9
        ring_spacing = 10
        base_outer = r_red + 8
        inactive_color = "#cfcfcf"
        arc_extent = 50
        
        for ring in range(rings):
            r = base_outer + ring * ring_spacing
            width_val = max(3, 10 - ring)
            
            # Left arc
            left_start = 180 - arc_extent / 2
            cid_l = self.canvas.create_arc(
                cx - r, center_y - r, cx + r, center_y + r,
                start=left_start, extent=arc_extent,
                style=tk.ARC, width=width_val, outline=inactive_color,
                tags='vu_arc'
            )
            self.segment_ids.append({'id': cid_l, 'side': 'left', 'ring': ring})
            
            # Right arc
            right_start = (360 - arc_extent / 2) % 360
            cid_r = self.canvas.create_arc(
                cx - r, center_y - r, cx + r, center_y + r,
                start=right_start, extent=arc_extent,
                style=tk.ARC, width=width_val, outline=inactive_color,
                tags='vu_arc'
            )
            self.segment_ids.append({'id': cid_r, 'side': 'right', 'ring': ring})
        
        # Store center position for icon
        self._vu_center_y = center_y
    
    def _draw_receiver_bar(self) -> None:
        """Draw the horizontal receiver audio bar."""
        cx = self.config.center_x
        center_y = 290
        bar_y = center_y + self.outer_radius + 50
        bar_w = 500
        bar_h = 20
        bx1 = cx - bar_w // 2
        bx2 = cx + bar_w // 2
        
        # Store bar position
        self._bar_y = bar_y
        self._bar_w = bar_w
        self._bar_h = bar_h
        self._bar_x1 = bx1
        self._bar_x2 = bx2
        
        # Label (changes based on mode)
        self._bar_label_id = self.canvas.create_text(
            cx, bar_y - 12,
            text="Receiver Audio",
            font=("Segoe UI", 11, "bold"),
            fill="#333333",
            anchor='center',
            tags='label'
        )
        
        # Background bar
        self.canvas.create_rectangle(
            bx1, bar_y, bx2, bar_y + bar_h,
            fill="#dbe0e3", outline="#c9cfd3", width=1,
            tags='bar_bg'
        )
        
        # Center line
        self.canvas.create_line(
            cx, bar_y - 6, cx, bar_y + bar_h + 6,
            fill="#b9b9b9", tags='bar_center'
        )
        
        # Tick marks
        ticks = 8
        for i in range(ticks + 1):
            tx = bx1 + bar_w * (i / ticks)
            self.canvas.create_line(
                tx, bar_y - 4, tx, bar_y + bar_h + 4,
                fill="#e0e0e0", tags='bar_tick'
            )
        
        # Extremes
        self.canvas.create_line(bx1, bar_y - 6, bx1, bar_y + bar_h + 6, fill="#b9b9b9")
        self.canvas.create_line(bx2, bar_y - 6, bx2, bar_y + bar_h + 6, fill="#b9b9b9")
        
        # Dynamic bars
        self.receiver_bar_left = self.canvas.create_rectangle(
            cx, bar_y, cx, bar_y + bar_h,
            fill="#3fbf5f", outline="", tags='bar_level'
        )
        self.receiver_bar_right = self.canvas.create_rectangle(
            cx, bar_y, cx, bar_y + bar_h,
            fill="#3fbf5f", outline="", tags='bar_level'
        )
        
        # Rounded caps
        cap_pad = bar_h // 2
        self.receiver_cap_left = self.canvas.create_oval(
            cx - cap_pad, bar_y, cx + cap_pad, bar_y + bar_h,
            fill="#3fbf5f", outline="", tags='bar_cap'
        )
        self.receiver_cap_right = self.canvas.create_oval(
            cx - cap_pad, bar_y, cx + cap_pad, bar_y + bar_h,
            fill="#3fbf5f", outline="", tags='bar_cap'
        )
    
    def _draw_status_cards(self) -> None:
        """Draw link info text."""
        cx = self.config.center_x
        card_y = 520
        
        self._link_info_id = self.canvas.create_text(
            cx, card_y + 20,
            text="",
            font=("Segoe UI", 10),
            fill="#666666",
            anchor='center',
            tags='link_info'
        )
    
    def _draw_control_buttons(self) -> None:
        """Draw control buttons."""
        cx = self.config.center_x
        btn_y = 580
        
        # Main action button (Start/Stop toggle)
        self.main_action_btn = ttk.Button(
            self.root,
            text="Start",
            command=self._on_toggle_click,
            style='Start.TButton'
        )
        self.canvas.create_window(cx, btn_y, window=self.main_action_btn, width=140, height=50)
        
        # Auto-start checkbox (bottom left)
        # Auto-start checkbox (bottom left) - load from saved config
        self.auto_start_var = tk.BooleanVar(value=self.controller.auto_start_enabled)
        self.auto_chk = ttk.Checkbutton(
            self.root,
            text='Auto iniciar OBBroadcast al abrir',
            variable=self.auto_start_var,
            command=self._on_auto_start_changed
        )
        self.canvas.create_window(140, self.config.height - 40, window=self.auto_chk, anchor='w')
        
        # Settings button (bottom right)
        self.settings_btn = ttk.Button(
            self.root,
            text="⚙ Settings",
            command=self._on_settings_click,
            style='Settings.TButton'
        )
        self.canvas.create_window(
            self.config.width - 140,
            self.config.height - 40,
            window=self.settings_btn,
            anchor='e',
            width=120,
            height=32
        )
        
        # Logs button (next to Settings)
        self.logs_btn = ttk.Button(
            self.root,
            text="📋 Logs",
            command=self._toggle_logs,
            style='Settings.TButton'
        )
        self.canvas.create_window(
            self.config.width - 270,
            self.config.height - 40,
            window=self.logs_btn,
            anchor='e',
            width=100,
            height=32
        )
        
        # Requirements status label (bottom center)
        self.req_label = ttk.Label(self.root, text='Checking requirements...', font=('Segoe UI', 8))
        self.canvas.create_window(cx, self.config.height - 20, window=self.req_label)
    
    def _create_logs_panel(self) -> None:
        """Create the logs panel (hidden by default)."""
        self.log_frame = tk.Frame(self.root, bg='#f0f0f0', bd=2, relief='groove')
        
        log_header = tk.Frame(self.log_frame, bg='#e0e0e0')
        log_header.pack(fill='x')
        
        tk.Label(log_header, text="📋 Logs", font=('Segoe UI', 10, 'bold'), bg='#e0e0e0').pack(side='left', padx=8, pady=4)
        ttk.Button(log_header, text="✕", width=3, command=self._toggle_logs).pack(side='right', padx=4, pady=2)
        
        self.log_widget = scrolledtext.ScrolledText(
            self.log_frame, state='disabled', wrap='word',
            font=('Consolas', 9), bg='#1e1e1e', fg='#d4d4d4',
            insertbackground='white'
        )
        self.log_widget.pack(fill='both', expand=True, padx=4, pady=4)
        
        self.log_widget.tag_configure('INFO', foreground='#4fc3f7')
        self.log_widget.tag_configure('WARN', foreground='#ffb74d')
        self.log_widget.tag_configure('WARNING', foreground='#ffb74d')
        self.log_widget.tag_configure('ERROR', foreground='#ef5350')
        self.log_widget.tag_configure('OBBROADCAST', foreground='#81c784')
    
    def _load_center_icon(self) -> None:
        """Load the input_line.png icon for the center of the VU circle."""
        self.center_icon_img = None
        icon_path = self.config.repo_root / 'ui' / 'images' / 'input_line.png'
        
        if icon_path.exists():
            try:
                img = Image.open(str(icon_path)).convert("RGBA")
                icon_size = 130
                img = img.resize((icon_size, icon_size), Image.LANCZOS)
                self.center_icon_img = ImageTk.PhotoImage(img)
            except Exception as e:
                logger.warning(f"Error loading center icon: {e}")
        
        if self.center_icon_img:
            cx = self.config.center_x
            self.canvas.create_image(
                cx, self._vu_center_y,
                image=self.center_icon_img,
                tags='center_icon'
            )
    
    def _bind_events(self) -> None:
        """Bind keyboard and window events."""
        self.root.bind('<Escape>', lambda e: self._on_close())
        self.root.bind('<Control-q>', lambda e: self._on_close())
    
    def _start_update_loops(self) -> None:
        """Start periodic update loops."""
        # VU animation (fast)
        self._animate_vu()
        
        # VU data from Redis (100ms)
        self._update_vu_from_redis()
        
        # Status update (2000ms)
        self._update_status_loop()
        
        # Auto-start check (1500ms delay)
        self.root.after(1500, self._auto_start_if_enabled)
    
    def _animate_vu(self) -> None:
        """Animate VU meters with smooth transitions."""
        openob_running = self.controller.is_openob_running()
        
        # Determine current mode
        link_config = self.controller.get_link_config()
        is_rx_mode = link_config and link_config.link_mode == 'rx'
        
        # Circular VU (vu_left/vu_right)
        # In TX mode: simulate if no real data
        # In RX mode: never simulate, only show real data or silence
        if self._has_real_vu_data.get('local'):
            pass  # Real data updated by _update_vu_from_redis
        elif openob_running and not is_rx_mode:
            # TX mode only: Simulate when no Redis data
            target_left = abs(math.sin(time.time() * 2.5 + random.random() * 0.5)) * 0.85 + random.random() * 0.15
            target_right = abs(math.cos(time.time() * 2.3 + random.random() * 0.5)) * 0.85 + random.random() * 0.15
            self.vu_left = 0.75 * self.vu_left + 0.25 * target_left
            self.vu_right = 0.75 * self.vu_right + 0.25 * target_right
        else:
            # Decay to zero (RX mode without data, or not running)
            self.vu_left *= 0.85
            self.vu_right *= 0.85
            if self.vu_left < 0.01:
                self.vu_left = 0
            if self.vu_right < 0.01:
                self.vu_right = 0
        
        # Horizontal bar (receiver_level) - never simulate, only real data
        if self._has_real_vu_data.get('remote'):
            pass  # Real data updated by _update_vu_from_redis
        else:
            # No real data - decay to silence
            self.receiver_level *= 0.85
            if self.receiver_level < 0.01:
                self.receiver_level = 0
        
        # Update visuals
        self._update_vu_arcs()
        self._update_receiver_bar_visual()
        
        # Schedule next frame
        avg_level = max(self.vu_left, self.vu_right, self.receiver_level)
        if avg_level > 0.7:
            refresh_ms = 40
        elif avg_level > 0.4:
            refresh_ms = 60
        else:
            refresh_ms = 80
        
        self.root.after(refresh_ms, self._animate_vu)
    
    def _update_vu_arcs(self) -> None:
        """Update the arc segments based on current VU levels."""
        thresholds = [0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.78, 0.90]
        inactive_color = "#cfcfcf"
        ring_colors = [
            "#3fbf5f", "#3fbf5f", "#3fbf5f",  # green
            "#5fcf5f", "#7fdf5f", "#bfef3f",  # yellow-green
            "#f2c94c", "#f0a030", "#e04b4b",  # yellow to red
        ]
        
        for seg in self.segment_ids:
            ring = seg['ring']
            side = seg['side']
            cid = seg['id']
            thr = thresholds[ring]
            
            level = self.vu_left if side == 'left' else self.vu_right
            
            if level >= thr:
                col = ring_colors[ring]
            else:
                col = inactive_color
            
            self.canvas.itemconfigure(cid, outline=col)
    
    def _update_receiver_bar_visual(self) -> None:
        """Update the receiver bar based on current level."""
        cx = self.config.center_x
        bar_y = self._bar_y
        bar_h = self._bar_h
        bx1 = self._bar_x1
        bx2 = self._bar_x2
        half_len = (bx2 - bx1) // 2
        
        cur = int(max(0, min(1.0, self.receiver_level)) * half_len) if self.receiver_level > 0 else 0
        
        # Update bar positions
        self.canvas.coords(self.receiver_bar_left, cx - cur, bar_y, cx, bar_y + bar_h)
        self.canvas.coords(self.receiver_bar_right, cx, bar_y, cx + cur, bar_y + bar_h)
        
        # Update caps
        cap_pad = bar_h // 2
        if cur <= 0:
            self.canvas.coords(self.receiver_cap_left, -10, -10, -5, -5)
            self.canvas.coords(self.receiver_cap_right, -10, -10, -5, -5)
        else:
            left_cap_x = max(cx - cur, bx1 + cap_pad)
            right_cap_x = min(cx + cur, bx2 - cap_pad)
            self.canvas.coords(self.receiver_cap_left, left_cap_x - cap_pad, bar_y, left_cap_x + cap_pad, bar_y + bar_h)
            self.canvas.coords(self.receiver_cap_right, right_cap_x - cap_pad, bar_y, right_cap_x + cap_pad, bar_y + bar_h)
        
        # Color based on level
        level_norm = cur / float(half_len) if half_len else 0
        if level_norm >= 0.9:
            color = "#e04b4b"
        elif level_norm >= 0.65:
            color = "#f2c94c"
        else:
            color = "#3fbf5f"
        
        self.canvas.itemconfigure(self.receiver_bar_left, fill=color)
        self.canvas.itemconfigure(self.receiver_bar_right, fill=color)
        self.canvas.itemconfigure(self.receiver_cap_left, fill=color)
        self.canvas.itemconfigure(self.receiver_cap_right, fill=color)
    
    def _update_vu_from_redis(self) -> None:
        """Fetch VU data from Redis via controller."""
        try:
            # First trigger controller to fetch from Redis
            self.controller.update_vu_from_redis()
            
            # Then get the updated state
            state = self.controller.state
            
            # Determine current mode
            link_config = self.controller.get_link_config()
            is_rx_mode = link_config and link_config.link_mode == 'rx'
            
            # In TX mode:
            #   - Circular VU (vu_left/vu_right) shows local_vu (audio being transmitted)
            #   - Bar shows remote_vu (what receiver is getting)
            # In RX mode:
            #   - Circular VU shows remote_vu (audio being received/output)
            #   - Bar shows local_vu (what transmitter sent - if available)
            
            if is_rx_mode:
                # RX Mode: Circular VU shows received audio (remote_vu from rx)
                if state.remote_vu.has_real_data:
                    avg_remote = state.remote_vu.average
                    if avg_remote >= 0.02:
                        self._has_real_vu_data['local'] = True
                        self.vu_left = state.remote_vu.left
                        self.vu_right = state.remote_vu.right
                    else:
                        self._has_real_vu_data['local'] = False
                else:
                    self._has_real_vu_data['local'] = False
                
                # Bar shows transmitted audio (local_vu from tx)
                if state.local_vu.has_real_data:
                    self._has_real_vu_data['remote'] = True
                    avg_local = state.local_vu.average
                    self.receiver_level = 0.7 * self.receiver_level + 0.3 * avg_local
                else:
                    self._has_real_vu_data['remote'] = False
            else:
                # TX Mode: Normal behavior
                # Circular VU shows audio being transmitted (local_vu)
                if state.local_vu.has_real_data:
                    avg_local = state.local_vu.average
                    if avg_local >= 0.02:
                        self._has_real_vu_data['local'] = True
                        self.vu_left = state.local_vu.left
                        self.vu_right = state.local_vu.right
                    else:
                        self._has_real_vu_data['local'] = False
                else:
                    self._has_real_vu_data['local'] = False
                
                # Bar shows what receiver is getting (remote_vu from rx)
                if state.remote_vu.has_real_data:
                    self._has_real_vu_data['remote'] = True
                    avg_remote = state.remote_vu.average
                    self.receiver_level = 0.7 * self.receiver_level + 0.3 * avg_remote
                else:
                    self._has_real_vu_data['remote'] = False
            
        except Exception:
            pass
        
        self.root.after(100, self._update_vu_from_redis)
    
    def _update_status_loop(self) -> None:
        """Update status display."""
        self.controller.refresh_status()
        state = self.controller.state
        
        # Determine current mode (TX or RX)
        link_config = self.controller.get_link_config()
        is_rx_mode = link_config and link_config.link_mode == 'rx'
        
        # Update labels based on mode
        if is_rx_mode:
            self.canvas.itemconfigure(self._title_text_id, text="OBBroadcast RX")
            self.canvas.itemconfigure(self._vu_label_id, text="Audio Output")
            self.canvas.itemconfigure(self._bar_label_id, text="Audio Transmitted")
        else:
            self.canvas.itemconfigure(self._title_text_id, text="OBBroadcast TX")
            self.canvas.itemconfigure(self._vu_label_id, text="Audio Input")
            self.canvas.itemconfigure(self._bar_label_id, text="Receiver Audio")
        
        # Update header status text based on mode and running state
        if state.openob_running:
            if is_rx_mode:
                self.canvas.itemconfigure(self._status_text_id, text="Receiving", fill="#2e7d32")
            else:
                self.canvas.itemconfigure(self._status_text_id, text="Transmitting", fill="#2e7d32")
        else:
            self.canvas.itemconfigure(self._status_text_id, text="Stopped", fill="#c62828")
        
        # Update button
        if state.cooldown_active:
            self.main_action_btn.configure(
                state='disabled',
                text=f'Espera {state.cooldown_remaining}s'
            )
        elif state.openob_running:
            self.main_action_btn.configure(text="Stop", style='Stop.TButton', state='normal')
        else:
            self.main_action_btn.configure(text="Start", style='Start.TButton', state='normal')
        
        # Update link info
        link_config = self.controller.get_link_config()
        if link_config:
            info_parts = []
            if link_config.config_host:
                info_parts.append(f"Host: {link_config.config_host}")
            if link_config.link_mode:
                info_parts.append(f"Mode: {link_config.link_mode.upper()}")
            if link_config.link_name:
                info_parts.append(f"Link: {link_config.link_name}")
            link_info = " | ".join(info_parts)
            self.canvas.itemconfigure(self._link_info_id, text=link_info)
        
        # Update requirements
        self._update_requirements_label()
        
        self.root.after(2000, self._update_status_loop)
    
    def _update_requirements_label(self) -> None:
        """Update requirements status label."""
        msgs = self.controller.check_requirements()
        self.req_label.config(text=' | '.join(msgs))
    
    def _auto_start_if_enabled(self) -> None:
        """Auto-start OpenOB if enabled."""
        if self._auto_started:
            return
        
        try:
            if self.auto_start_var.get():
                if not self.controller.is_openob_running():
                    logger.info('Auto-starting OBBroadcast')
                    self.controller.start_openob()
        finally:
            self._auto_started = True
    
    def _on_auto_start_changed(self) -> None:
        """Handle auto-start checkbox change."""
        enabled = self.auto_start_var.get()
        self.controller.set_auto_start(enabled)
        logger.info(f"Auto-start {'enabled' if enabled else 'disabled'}")
    
    def _on_toggle_click(self) -> None:
        """Handle toggle button click."""
        state = self.controller.state
        
        if state.cooldown_active:
            return
        
        if state.openob_running:
            self.controller.stop_openob()
            self._start_cooldown()
        else:
            self.controller.start_openob()
    
    def _start_cooldown(self) -> None:
        """Start cooldown period."""
        self.controller.start_cooldown(5)
        self._cooldown_tick()
    
    def _cooldown_tick(self) -> None:
        """Update cooldown countdown."""
        state = self.controller.state
        
        if state.cooldown_remaining > 0:
            self.controller.tick_cooldown()
            self.main_action_btn.configure(text=f'Espera {state.cooldown_remaining}s')
            self.root.after(1000, self._cooldown_tick)
        else:
            self.main_action_btn.configure(text='Start', state='normal')
    
    def _on_settings_click(self) -> None:
        """Open configuration view (AudioBridge Pro style)."""
        # Check if OpenOB is running - must stop before editing config
        if self.controller.is_openob_running():
            messagebox.showwarning(
                "OBBroadcast en ejecución",
                "Debe detener OBBroadcast antes de modificar las configuraciones.\n\n"
                "Haga clic en 'Stop' primero y luego intente nuevamente."
            )
            return
        
        try:
            logger.info("Opening ConfigView...")
            from .components.config import ConfigView, ConfigController, ConfigState, TransmissionMode
            
            # Get current args from controller to determine mode
            current_args = self.controller.current_args
            is_rx_mode = " rx " in current_args or current_args.endswith(" rx")
            
            # Create initial state from current settings
            initial_state = ConfigState(
                transmission_mode=TransmissionMode.RX if is_rx_mode else TransmissionMode.TX
            )
            
            # Parse current args into state
            link_config = self.controller.get_link_config()
            if link_config:
                if is_rx_mode:
                    initial_state.rx_config_host = link_config.config_host or initial_state.rx_config_host
                    initial_state.rx_node_name = link_config.node_id or initial_state.rx_node_name
                    initial_state.rx_link_name = link_config.link_name or initial_state.rx_link_name
                    initial_state.rx_audio_backend = link_config.audio_backend or initial_state.rx_audio_backend
                else:
                    initial_state.tx_config_host = link_config.config_host or initial_state.tx_config_host
                    initial_state.tx_node_name = link_config.node_id or initial_state.tx_node_name
                    initial_state.tx_link_name = link_config.link_name or initial_state.tx_link_name
                    initial_state.tx_peer_ip = link_config.peer_ip or initial_state.tx_peer_ip
                    initial_state.tx_encoding = link_config.encoding or initial_state.tx_encoding
                    initial_state.tx_sample_rate = link_config.sample_rate or initial_state.tx_sample_rate
                    initial_state.tx_jitter_buffer = link_config.jitter_buffer or initial_state.tx_jitter_buffer
                    initial_state.tx_audio_backend = link_config.audio_backend or initial_state.tx_audio_backend
            
            controller = ConfigController(initial_state)
            
            def on_config_close(result):
                if result and result.saved:
                    self.controller.set_args(result.args)
                    logger.info(f"Configuration updated: {result.args}")
            
            dialog = ConfigView(
                self.root,
                controller,
                on_close=on_config_close,
                on_home=lambda: None  # Just close when Home is clicked
            )
            logger.info(f"ConfigView created: {dialog}")
            self.root.wait_window(dialog)
            logger.info("ConfigView closed")
            
        except Exception as e:
            logger.error(f"Error opening ConfigView: {e}", exc_info=True)
    
    def _toggle_logs(self) -> None:
        """Toggle logs panel visibility."""
        if self._logs_visible:
            self.log_frame.place_forget()
            self._logs_visible = False
        else:
            self.log_frame.place(
                x=20,
                y=self.config.height - 220,
                width=self.config.width - 40,
                height=200
            )
            self.log_frame.lift()
            self._logs_visible = True
    
    def _on_log_message(self, text: str) -> None:
        """Handle log message from controller - thread-safe."""
        # Schedule on main thread to avoid Tkinter threading issues
        self.root.after(0, lambda: self.append_log(text))
    
    def append_log(self, text: str) -> None:
        """Append text to log widget."""
        self.log_widget.configure(state='normal')
        
        tag = None
        if 'ERROR' in text.upper():
            tag = 'ERROR'
        elif 'WARN' in text.upper():
            tag = 'WARN'
        elif 'INFO' in text.upper():
            tag = 'INFO'
        elif 'OBBROADCAST' in text.upper():
            tag = 'OBBROADCAST'
        
        if tag:
            self.log_widget.insert('end', text, tag)
        else:
            self.log_widget.insert('end', text)
        
        self.log_widget.see('end')
        self.log_widget.configure(state='disabled')
    
    def _on_close(self) -> None:
        """Handle window close request."""
        from .components.dialogs import CloseDialog
        
        if self.controller.is_openob_running():
            dialog = CloseDialog(self.root, has_tray_support=False)
            choice = dialog.show()
            
            if choice == CloseDialog.CHOICE_STOP:
                self.controller.stop_openob()
                self._cleanup_and_close()
            elif choice == CloseDialog.CHOICE_BACKGROUND:
                self.root.withdraw()
            # CANCEL: do nothing
        else:
            self._cleanup_and_close()
    
    def _cleanup_and_close(self) -> None:
        """Clean up and close."""
        logger.info("Closing application")
        self.controller.cleanup()
        self.root.destroy()
    
    def run(self) -> None:
        """Start the application main loop."""
        self.root.mainloop()
