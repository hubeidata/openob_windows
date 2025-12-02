#!/usr/bin/env python3
"""
OBBroadcast Controller UI - Modern visual interface inspired by mockup design.

Usage: run from repo root (or double-click):
    python ui/main.py

Features:
 - Visual VU meters with circular input indicator and horizontal receiver bar
 - Start/Stop Redis and OBBroadcast with status cards
 - Settings dialog for launch parameters
 - System tray support for background operation
 - Logs panel (toggle visibility)
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import subprocess
import shlex
import shutil
import sys
import time
import re
import logging
import math
import random
import os
from pathlib import Path

try:
    import redis
    HAS_REDIS_LIB = True
except Exception:
    redis = None
    HAS_REDIS_LIB = False

# PIL for image handling
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# Hide PowerShell windows on Windows
creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0


REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_PY = REPO_ROOT / '.venv' / 'Scripts' / 'python.exe'
OPENOB_SCRIPT = REPO_ROOT / '.venv' / 'Scripts' / 'openob'
SCRIPT_START_OPENOB = REPO_ROOT / 'scripts' / 'start_openob.ps1'
GSTREAMER_BIN = Path(r'C:\Program Files\gstreamer\1.0\msvc_x86_64\bin')
GSTREAMER_GIR = Path(r'C:\Program Files\gstreamer\1.0\msvc_x86_64\lib\girepository-1.0')
LOG_DIR = REPO_ROOT / 'logs'
LOG_DIR.mkdir(exist_ok=True)
UI_LOG_FILE = LOG_DIR / 'ui.log'
ICON_PATH = REPO_ROOT / 'ui' / 'input_line.png'

# UI Dimensions
WIDTH, HEIGHT = 960, 700
CENTER_X = WIDTH // 2

DEFAULT_OPENOB_ARGS = '127.0.0.1 emetteur transmission tx 192.168.1.17 -e pcm -r 48000 -j 60 -a auto'

# Optional system tray support
try:
    import pystray
    from PIL import Image as PILImage
    HAS_TRAY = True
except Exception:
    HAS_TRAY = False


class OpenOBGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger('openob.ui')
        self.logger.setLevel(logging.INFO)
        self._ensure_log_handler()

        self.title('OBBroadcast Controller')
        self.geometry(f'{WIDTH}x{HEIGHT}')
        self.configure(bg='#ffffff')
        self.resizable(False, False)
        
        # Set application icon
        try:
            img_png = REPO_ROOT / 'ui' / 'images' / 'ob-logo.png'
            img_ico = REPO_ROOT / 'ui' / 'images' / 'ob-logo.ico'
            if img_png.exists():
                self._icon_img = tk.PhotoImage(file=str(img_png))
                try:
                    self.iconphoto(False, self._icon_img)
                except Exception:
                    pass
            if img_ico.exists():
                try:
                    self.iconbitmap(str(img_ico))
                except Exception:
                    pass
        except Exception:
            pass

        # State variables
        self.redis_proc = None
        self.openob_proc = None
        self.openob_thread = None
        self.redis_running = False
        self.redis_client = None
        self.redis_host = None
        self.redis_port = 6379
        self.vu_diag_state = {'local': None, 'remote': None}
        self.auto_start_var = tk.BooleanVar(value=True)
        self._auto_started = False
        self.config_host = None
        self.link_name = None
        self.node_id = None
        self.link_mode = None
        
        # VU levels (0..1 normalized) - separate for input and receiver
        self.vu_left = 0.0          # Audio Input left channel
        self.vu_right = 0.0         # Audio Input right channel
        self.receiver_left = 0.0    # Receiver Audio left channel
        self.receiver_right = 0.0   # Receiver Audio right channel
        self.receiver_level = 0.0   # Receiver combined level for bar display
        
        # Flag to know if we have real Redis data
        self._has_real_vu_data = {'local': False, 'remote': False}
        
        # Visual parameters
        self.outer_radius = 130
        self.red_center_radius = 95
        
        # Tray icon state
        self.tray_icon = None
        self.tray_thread = None
        
        # Logs visibility
        self._logs_visible = False

        # Handle window close
        self.protocol('WM_DELETE_WINDOW', self.on_close)

        # Create the modern UI
        self.create_widgets()
        
        # Load icon image for central display
        self._load_center_icon()
        
        # Initial checks and loops
        self.check_requirements()
        self.after(1500, self._auto_start_if_enabled)
        self.update_status_loop()
        self.update_vu_loop()
        self._animate_vu()

    def _load_center_icon(self):
        """Load the input_line.png icon for the center of the VU circle."""
        self.center_icon_img = None
        if ICON_PATH.exists():
            try:
                if PIL_AVAILABLE:
                    img = Image.open(str(ICON_PATH)).convert("RGBA")
                    icon_size = 130
                    img = img.resize((icon_size, icon_size), Image.LANCZOS)
                    self.center_icon_img = ImageTk.PhotoImage(img)
                else:
                    self.center_icon_img = tk.PhotoImage(file=str(ICON_PATH))
            except Exception as e:
                self.logger.warning(f"Error loading center icon: {e}")
        
        # Place the icon on the canvas if loaded
        if self.center_icon_img and hasattr(self, 'main_canvas'):
            center_y = 290
            self.main_canvas.create_image(CENTER_X, center_y, image=self.center_icon_img, tags='center_icon')

    def create_widgets(self):
        """Create the modern visual UI based on mockup design."""
        # Configure styles
        self._configure_styles()
        
        # Main canvas for visual elements
        self.main_canvas = tk.Canvas(self, width=WIDTH, height=HEIGHT, bg='#ffffff', highlightthickness=0)
        self.main_canvas.pack(fill='both', expand=True)
        
        # Draw static visual elements
        self._draw_header()
        self._draw_vu_circle()
        self._draw_receiver_bar()
        self._draw_status_cards()
        self._draw_control_buttons()
        self._create_logs_panel()
        
        # Args variable (hidden, for functionality)
        self.args_var = tk.StringVar(value=DEFAULT_OPENOB_ARGS)
        self.args_var.trace_add('write', lambda *_: self._on_args_change())
        self._update_link_details_from_args()
        
        # Status variables
        self.redis_status = tk.StringVar(value='Redis: unknown')
        self.openob_status = tk.StringVar(value='OBBroadcast: stopped')
        
        # Compatibility aliases for tests
        self.local_vu_canvas = self.main_canvas
        self.remote_vu_canvas = self.main_canvas
        self.redis_canvas = self.main_canvas
        self.openob_canvas = self.main_canvas
        self.redis_card = self._redis_card_bg
        self.openob_card = self._openob_card_bg

    def _configure_styles(self):
        """Configure ttk styles for the modern look."""
        style = ttk.Style(self)
        
        # Primary action button (Start All)
        style.configure('Primary.TButton',
                       font=('Segoe UI', 14, 'bold'),
                       padding=(16, 8))
        
        # Secondary button (Stop All)
        style.configure('Secondary.TButton',
                       font=('Segoe UI', 14),
                       padding=(16, 8))
        
        # Settings button
        style.configure('Settings.TButton',
                       font=('Segoe UI', 12),
                       padding=(8, 4))
        
        # Toggle logs button
        style.configure('Toggle.TButton',
                       font=('Segoe UI', 10),
                       padding=(6, 3))

    def _draw_header(self):
        """Draw the header with title and subtitle."""
        # Main title
        self.main_canvas.create_text(
            CENTER_X, 45,
            text="OBBroadcast",
            font=("Segoe UI", 32, "bold"),
            fill="#111111",
            tags='header'
        )
        
        # Subtitle / status
        self._status_text_id = self.main_canvas.create_text(
            CENTER_X, 90,
            text="Transmitting",
            font=("Segoe UI", 48, "bold"),
            fill="#111111",
            tags='header'
        )

    def _draw_vu_circle(self):
        """Draw the circular VU meter with input icon."""
        center_y = 290
        ox, oy = CENTER_X, center_y
        
        # Gray outer ring (background)
        r_outer = self.outer_radius
        self.main_canvas.create_oval(
            ox - r_outer, oy - r_outer, ox + r_outer, oy + r_outer,
            fill="#d0d3d6", outline="", tags='vu_bg'
        )
        
        # Red center circle
        r_red = self.red_center_radius
        self.main_canvas.create_oval(
            ox - r_red, oy - r_red, ox + r_red, oy + r_red,
            fill="#d9534f", outline="", tags='vu_center'
        )
        
        # Audio Input label
        self.main_canvas.create_text(
            CENTER_X, oy - r_red - 22,
            text="Audio Input",
            font=("Segoe UI", 11, "bold"),
            fill="#333333",
            anchor='s',
            tags='label'
        )
        
        # VU arc segments (stereo waves (((o))))
        self.segment_ids = []
        rings = 6
        ring_spacing = 12
        base_outer = r_red + 8
        inactive_color = "#cfcfcf"
        arc_extent = 50
        
        for ring in range(rings):
            r = base_outer + ring * ring_spacing
            width_val = max(4, 10 - ring)
            
            # Left arc
            left_start = 180 - arc_extent / 2
            cid_l = self.main_canvas.create_arc(
                ox - r, oy - r, ox + r, oy + r,
                start=left_start, extent=arc_extent,
                style=tk.ARC, width=width_val, outline=inactive_color,
                tags='vu_arc'
            )
            self.segment_ids.append({'id': cid_l, 'side': 'left', 'ring': ring})
            
            # Right arc
            right_start = (360 - arc_extent / 2) % 360
            cid_r = self.main_canvas.create_arc(
                ox - r, oy - r, ox + r, oy + r,
                start=right_start, extent=arc_extent,
                style=tk.ARC, width=width_val, outline=inactive_color,
                tags='vu_arc'
            )
            self.segment_ids.append({'id': cid_r, 'side': 'right', 'ring': ring})

    def _draw_receiver_bar(self):
        """Draw the horizontal receiver audio bar."""
        center_y = 290
        bar_y = center_y + self.outer_radius + 50
        bar_w = 500
        bar_h = 20
        bx1 = CENTER_X - bar_w // 2
        bx2 = CENTER_X + bar_w // 2
        
        # Store bar position for updates
        self._bar_y = bar_y
        self._bar_w = bar_w
        self._bar_h = bar_h
        self._bar_x1 = bx1
        self._bar_x2 = bx2
        
        # Label
        self.main_canvas.create_text(
            CENTER_X, bar_y - 12,
            text="Receiver Audio",
            font=("Segoe UI", 11, "bold"),
            fill="#333333",
            anchor='center',
            tags='label'
        )
        
        # Background bar
        self.main_canvas.create_rectangle(
            bx1, bar_y, bx2, bar_y + bar_h,
            fill="#dbe0e3", outline="#c9cfd3", width=1,
            tags='bar_bg'
        )
        
        # Center line
        self.main_canvas.create_line(
            CENTER_X, bar_y - 6, CENTER_X, bar_y + bar_h + 6,
            fill="#b9b9b9", tags='bar_center'
        )
        
        # Tick marks
        ticks = 8
        for i in range(ticks + 1):
            tx = bx1 + bar_w * (i / ticks)
            self.main_canvas.create_line(
                tx, bar_y - 4, tx, bar_y + bar_h + 4,
                fill="#e0e0e0", tags='bar_tick'
            )
        
        # Extremes
        self.main_canvas.create_line(bx1, bar_y - 6, bx1, bar_y + bar_h + 6, fill="#b9b9b9")
        self.main_canvas.create_line(bx2, bar_y - 6, bx2, bar_y + bar_h + 6, fill="#b9b9b9")
        
        # Dynamic bars (left and right from center)
        self.receiver_left = self.main_canvas.create_rectangle(
            CENTER_X, bar_y, CENTER_X, bar_y + bar_h,
            fill="#3fbf5f", outline="", tags='bar_level'
        )
        self.receiver_right = self.main_canvas.create_rectangle(
            CENTER_X, bar_y, CENTER_X, bar_y + bar_h,
            fill="#3fbf5f", outline="", tags='bar_level'
        )
        
        # Rounded caps
        cap_pad = bar_h // 2
        self.receiver_left_cap = self.main_canvas.create_oval(
            CENTER_X - cap_pad, bar_y, CENTER_X + cap_pad, bar_y + bar_h,
            fill="#3fbf5f", outline="", tags='bar_cap'
        )
        self.receiver_right_cap = self.main_canvas.create_oval(
            CENTER_X - cap_pad, bar_y, CENTER_X + cap_pad, bar_y + bar_h,
            fill="#3fbf5f", outline="", tags='bar_cap'
        )

    def _draw_status_cards(self):
        """Draw status indicator cards for Redis and OpenOB."""
        card_y = 520
        card_w = 180
        card_h = 40
        spacing = 20
        
        # Redis card
        redis_x = CENTER_X - card_w - spacing // 2
        self._redis_card_bg = self.main_canvas.create_rectangle(
            redis_x, card_y, redis_x + card_w, card_y + card_h,
            fill="#e0e0e0", outline="#c0c0c0", width=1,
            tags='status_card'
        )
        
        # Redis indicator dot
        dot_x = redis_x + 20
        dot_y = card_y + card_h // 2
        self.redis_canvas_dot = self.main_canvas.create_oval(
            dot_x - 8, dot_y - 8, dot_x + 8, dot_y + 8,
            fill="grey", outline="#888888", tags='redis_dot'
        )
        
        # Redis text
        self._redis_text_id = self.main_canvas.create_text(
            redis_x + 45, card_y + card_h // 2,
            text="Redis: Unknown",
            font=("Segoe UI", 10),
            fill="#333333",
            anchor='w',
            tags='status_text'
        )
        
        # OpenOB card
        openob_x = CENTER_X + spacing // 2
        self._openob_card_bg = self.main_canvas.create_rectangle(
            openob_x, card_y, openob_x + card_w, card_y + card_h,
            fill="#e0e0e0", outline="#c0c0c0", width=1,
            tags='status_card'
        )
        
        # OpenOB indicator dot
        dot_x2 = openob_x + 20
        self.openob_canvas_dot = self.main_canvas.create_oval(
            dot_x2 - 8, dot_y - 8, dot_x2 + 8, dot_y + 8,
            fill="grey", outline="#888888", tags='openob_dot'
        )
        
        # OpenOB text
        self._openob_text_id = self.main_canvas.create_text(
            openob_x + 45, card_y + card_h // 2,
            text="OpenOB: Stopped",
            font=("Segoe UI", 10),
            fill="#333333",
            anchor='w',
            tags='status_text'
        )
        
        # Link info text (below cards)
        self._link_info_id = self.main_canvas.create_text(
            CENTER_X, card_y + card_h + 18,
            text="",
            font=("Segoe UI", 9),
            fill="#666666",
            anchor='center',
            tags='link_info'
        )

    def _draw_control_buttons(self):
        """Draw control buttons on the canvas."""
        btn_y = 580
        
        # Stop button (main action when running)
        style = ttk.Style(self)
        style.configure('Stop.TButton', font=("Segoe UI", 16), padding=(12, 8))
        self.stop_btn = ttk.Button(self, text="Stop", command=self.stop_all, style='Stop.TButton')
        self.main_canvas.create_window(CENTER_X, btn_y, window=self.stop_btn, width=140, height=50)
        
        # Start All button (left side)
        style.configure('Start.TButton', font=("Segoe UI", 12), padding=(8, 4))
        self.start_btn = ttk.Button(self, text="▶ Start All", command=self.start_all, style='Start.TButton')
        self.main_canvas.create_window(CENTER_X - 180, btn_y, window=self.start_btn, width=120, height=40)
        
        # Settings button (right side)
        self.settings_btn = ttk.Button(self, text="⚙ Settings", command=self._open_settings_dialog, style='Settings.TButton')
        self.main_canvas.create_window(CENTER_X + 180, btn_y, window=self.settings_btn, width=120, height=40)
        
        # Toggle logs button (bottom right)
        self.btn_toggle_logs = ttk.Button(self, text="📋 Logs", command=self._toggle_logs, style='Toggle.TButton')
        self.main_canvas.create_window(WIDTH - 60, HEIGHT - 40, window=self.btn_toggle_logs, width=80, height=30)
        
        # Auto-start checkbox (bottom left)
        self.auto_chk = ttk.Checkbutton(
            self, text='Auto iniciar OBBroadcast al abrir',
            variable=self.auto_start_var
        )
        self.main_canvas.create_window(140, HEIGHT - 40, window=self.auto_chk, anchor='w')
        
        # Requirements status label (bottom center)
        self.req_label = ttk.Label(self, text='Checking requirements...', font=('Segoe UI', 8))
        self.main_canvas.create_window(CENTER_X, HEIGHT - 20, window=self.req_label)

    def _create_logs_panel(self):
        """Create the logs panel (hidden by default)."""
        # Log frame that will overlay when visible
        self.log_frame = tk.Frame(self, bg='#f0f0f0', bd=2, relief='groove')
        
        # Header for log panel
        log_header = tk.Frame(self.log_frame, bg='#e0e0e0')
        log_header.pack(fill='x')
        
        tk.Label(log_header, text="📋 Logs", font=('Segoe UI', 10, 'bold'), bg='#e0e0e0').pack(side='left', padx=8, pady=4)
        ttk.Button(log_header, text="✕", width=3, command=self._toggle_logs).pack(side='right', padx=4, pady=2)
        
        # Log text widget with syntax highlighting tags
        self.log_widget = scrolledtext.ScrolledText(
            self.log_frame, state='disabled', wrap='word',
            font=('Consolas', 9), bg='#1e1e1e', fg='#d4d4d4',
            insertbackground='white'
        )
        self.log_widget.pack(fill='both', expand=True, padx=4, pady=4)
        
        # Configure tags for log levels
        self.log_widget.tag_configure('INFO', foreground='#4fc3f7')
        self.log_widget.tag_configure('WARN', foreground='#ffb74d')
        self.log_widget.tag_configure('WARNING', foreground='#ffb74d')
        self.log_widget.tag_configure('ERROR', foreground='#ef5350')
        self.log_widget.tag_configure('OBBROADCAST', foreground='#81c784')

    def _animate_vu(self):
        """Animate VU meters with smooth transitions. Uses Redis data when available."""
        openob_running = bool(self.openob_proc and self.openob_proc.poll() is None)
        
        # Audio Input VU (circular arcs) - from local Redis tx data
        if self._has_real_vu_data.get('local'):
            # Real data is being updated by update_vu_loop, just smooth it
            pass
        elif openob_running:
            # Simulate when no Redis data but OpenOB is running
            target_left = abs(math.sin(time.time() * 2.5 + random.random() * 0.5)) * 0.85 + random.random() * 0.15
            target_right = abs(math.cos(time.time() * 2.3 + random.random() * 0.5)) * 0.85 + random.random() * 0.15
            self.vu_left = 0.75 * self.vu_left + 0.25 * target_left
            self.vu_right = 0.75 * self.vu_right + 0.25 * target_right
        else:
            # Decay to zero when stopped
            self.vu_left *= 0.85
            self.vu_right *= 0.85
            if self.vu_left < 0.01:
                self.vu_left = 0
            if self.vu_right < 0.01:
                self.vu_right = 0
        
        # Receiver Audio VU (horizontal bar) - from remote Redis rx data
        if self._has_real_vu_data.get('remote'):
            # Real data - compute combined level from receiver channels
            self.receiver_level = (self.receiver_left + self.receiver_right) / 2
        elif openob_running:
            # Simulate when no Redis data but OpenOB is running
            target_recv = abs(math.sin(time.time() * 1.8 + 0.5)) * 0.8 + random.random() * 0.15
            self.receiver_level = 0.80 * self.receiver_level + 0.20 * target_recv
        else:
            # Decay to zero when stopped
            self.receiver_level *= 0.85
            self.receiver_left *= 0.85
            self.receiver_right *= 0.85
            if self.receiver_level < 0.01:
                self.receiver_level = 0
            if self.receiver_left < 0.01:
                self.receiver_left = 0
            if self.receiver_right < 0.01:
                self.receiver_right = 0
        
        # Update the visual VU arcs and bar
        self._update_vu_arcs()
        self._update_receiver_bar_visual()
        
        # Schedule next frame
        self.after(80, self._animate_vu)

    def _update_vu_arcs(self):
        """Update the arc segments based on current VU levels."""
        thresholds = [0.06, 0.18, 0.32, 0.46, 0.6, 0.74]
        active_color = "#3fbf5f"
        inactive_color = "#cfcfcf"
        
        for seg in self.segment_ids:
            ring = seg['ring']
            side = seg['side']
            cid = seg['id']
            thr = thresholds[ring]
            
            if side == 'left':
                col = active_color if self.vu_left >= thr else inactive_color
            else:
                col = active_color if self.vu_right >= thr else inactive_color
            
            self.main_canvas.itemconfigure(cid, outline=col)

    def _update_receiver_bar_visual(self):
        """Update the receiver bar based on current level."""
        bar_y = self._bar_y
        bar_h = self._bar_h
        bx1 = self._bar_x1
        bx2 = self._bar_x2
        half_len = (bx2 - bx1) // 2
        
        if self.receiver_level <= 0:
            cur = 0
        else:
            cur = int(max(0, min(1.0, self.receiver_level)) * half_len)
        
        # Update bar positions
        self.main_canvas.coords(self.receiver_left, CENTER_X - cur, bar_y, CENTER_X, bar_y + bar_h)
        self.main_canvas.coords(self.receiver_right, CENTER_X, bar_y, CENTER_X + cur, bar_y + bar_h)
        
        # Update caps
        cap_pad = bar_h // 2
        if cur <= 0:
            self.main_canvas.coords(self.receiver_left_cap, -10, -10, -5, -5)
            self.main_canvas.coords(self.receiver_right_cap, -10, -10, -5, -5)
        else:
            left_cap_x = max(CENTER_X - cur, bx1 + cap_pad)
            right_cap_x = min(CENTER_X + cur, bx2 - cap_pad)
            self.main_canvas.coords(self.receiver_left_cap, left_cap_x - cap_pad, bar_y, left_cap_x + cap_pad, bar_y + bar_h)
            self.main_canvas.coords(self.receiver_right_cap, right_cap_x - cap_pad, bar_y, right_cap_x + cap_pad, bar_y + bar_h)
        
        # Color based on level
        level_norm = cur / float(half_len) if half_len else 0
        if level_norm >= 0.9:
            color = "#e04b4b"  # red
        elif level_norm >= 0.65:
            color = "#f2c94c"  # yellow
        else:
            color = "#3fbf5f"  # green
        
        self.main_canvas.itemconfigure(self.receiver_left, fill=color)
        self.main_canvas.itemconfigure(self.receiver_right, fill=color)
        self.main_canvas.itemconfigure(self.receiver_left_cap, fill=color)
        self.main_canvas.itemconfigure(self.receiver_right_cap, fill=color)

    def _update_indicators(self, redis_running: bool, openob_running: bool):
        """Update status card colors and text."""
        r_color = '#4caf50' if redis_running else '#f44336'
        o_color = '#4caf50' if openob_running else '#f44336'
        card_running = '#e8f5e9'
        card_stopped = '#ffebee'
        
        # Update dots
        self.main_canvas.itemconfigure(self.redis_canvas_dot, fill=r_color)
        self.main_canvas.itemconfigure(self.openob_canvas_dot, fill=o_color)
        
        # Update card backgrounds
        self.main_canvas.itemconfigure(self._redis_card_bg, fill=card_running if redis_running else card_stopped)
        self.main_canvas.itemconfigure(self._openob_card_bg, fill=card_running if openob_running else card_stopped)
        
        # Update text
        redis_txt = "Redis: Running" if redis_running else "Redis: Stopped"
        openob_txt = "OpenOB: Running" if openob_running else "OpenOB: Stopped"
        self.main_canvas.itemconfigure(self._redis_text_id, text=redis_txt)
        self.main_canvas.itemconfigure(self._openob_text_id, text=openob_txt)
        
        # Update header status text
        if openob_running:
            self.main_canvas.itemconfigure(self._status_text_id, text="Transmitting", fill="#2e7d32")
        else:
            self.main_canvas.itemconfigure(self._status_text_id, text="Stopped", fill="#c62828")
        
        # Update link info
        info_parts = []
        if self.config_host:
            info_parts.append(f"Host: {self.config_host}")
        if self.link_mode:
            info_parts.append(f"Mode: {self.link_mode.upper()}")
        if self.link_name:
            info_parts.append(f"Link: {self.link_name}")
        
        link_info = " | ".join(info_parts) if info_parts else ""
        self.main_canvas.itemconfigure(self._link_info_id, text=link_info)

    def append_log(self, text):
        """Append text to the log widget with level highlighting."""
        self.log_widget.configure(state='normal')
        
        # Determine tag based on content
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

    # Logging helpers
    _log_handler_set = False

    def _ensure_log_handler(self):
        if OpenOBGUI._log_handler_set:
            return
        handler = logging.FileHandler(UI_LOG_FILE, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
        self.logger.addHandler(handler)
        self.logger.propagate = False
        OpenOBGUI._log_handler_set = True

    def _log_status(self, message, level='info', to_ui=False):
        log_fn = getattr(self.logger, level, self.logger.info)
        log_fn(message)
        if to_ui:
            self.append_log(message + '\n')

    def check_requirements(self):
        msgs = []
        self._update_link_details_from_args()
        # python module redis
        if HAS_REDIS_LIB:
            msgs.append('redis: OK')
        else:
            msgs.append('redis: MISSING')

        # gi/Gst
        try:
            import gi
            gi.require_version('Gst', '1.0')
            from gi.repository import Gst  # noqa
            msgs.append('gi/Gst: OK')
        except Exception:
            msgs.append('gi/Gst: MISSING')

        # GStreamer bins
        if GSTREAMER_BIN.exists():
            msgs.append('GStreamer bins: OK')
        else:
            msgs.append(f'GStreamer bins not found at {GSTREAMER_BIN}')

        # Redis service status (Windows)
        redis_running = False
        try:
            res = subprocess.run([
                'powershell', '-NoProfile', '-Command',
                "(Get-Service -Name Redis -ErrorAction SilentlyContinue).Status -join ''"
            ], capture_output=True, text=True, cwd=str(REPO_ROOT), creationflags=creationflags)
            svc = res.stdout.strip()
            if svc:
                msgs.append(f'Redis service: {svc}')
                self.redis_status.set(f'Redis: {svc.lower()}')
                redis_running = (svc == 'Running')
            else:
                msgs.append('Redis service: NOT INSTALLED')
                self.redis_status.set('Redis: not installed')
                redis_running = False
        except Exception:
            msgs.append('Redis service: UNKNOWN')
            self.redis_status.set('Redis: unknown')
            redis_running = False

        self.req_label.config(text=' | '.join(msgs))

        # Store redis running flag for other callers
        self.redis_running = bool(redis_running)

        # Also update OpenOB status and visual indicators
        openob_running = bool(self.openob_proc and self.openob_proc.poll() is None)
        self.openob_status.set('OBBroadcast: running' if openob_running else 'OBBroadcast: stopped')
        # Update colored indicators
        try:
            self._update_indicators(self.redis_running, openob_running)
        except Exception:
            pass

    def start_redis(self):
        # Start the Redis Windows service (requires service to be installed)
        try:
            res = subprocess.run(['powershell', '-NoProfile', '-Command', 'Start-Service -Name Redis'], capture_output=True, text=True, cwd=str(REPO_ROOT), creationflags=creationflags)
            if res.returncode == 0:
                self.append_log('Requested Start-Service Redis\n')
                # refresh known status and indicators
                try:
                    self.check_requirements()
                except Exception:
                    pass
            else:
                self.append_log(f'Start-Service exit: {res.returncode} stderr={res.stderr}\n')
                messagebox.showerror('Error', f'Failed to start Redis service: {res.stderr}')
        except Exception as e:
            messagebox.showerror('Error', f'Failed to start Redis service: {e}')

    def stop_redis(self):
        try:
            res = subprocess.run(['powershell', '-NoProfile', '-Command', 'Stop-Service -Name Redis -Force'], capture_output=True, text=True, cwd=str(REPO_ROOT), creationflags=creationflags)
            if res.returncode == 0:
                self.append_log('Requested Stop-Service Redis\n')
                try:
                    self.check_requirements()
                except Exception:
                    pass
            else:
                self.append_log(f'Stop-Service exit: {res.returncode} stderr={res.stderr}\n')
                messagebox.showerror('Error', f'Failed to stop Redis service: {res.stderr}')
        except Exception as e:
            messagebox.showerror('Error', f'Failed to stop Redis service: {e}')

    def start_openob(self):
        if self.openob_proc and self.openob_proc.poll() is None:
            messagebox.showinfo('Info', 'OBBroadcast already running')
            return
        if not VENV_PY.exists():
            messagebox.showerror('Error', f'Venv python not found at {VENV_PY}')
            return

        args = self.args_var.get().strip()
        if not args:
            messagebox.showerror('Error', 'Empty OBBroadcast args')
            return

        # Ensure Redis service is running (best-effort)
        try:
            res = subprocess.run([
                'powershell', '-NoProfile', '-Command',
                "(Get-Service -Name Redis -ErrorAction SilentlyContinue).Status -join ''"
            ], capture_output=True, text=True, cwd=str(REPO_ROOT), creationflags=creationflags)
            svc = res.stdout.strip()
            if svc != 'Running':
                if messagebox.askyesno('Redis not running', 'Redis service is not running. Start it now?'):
                    self.start_redis()
                    time.sleep(0.5)
                else:
                    return
        except Exception:
            # cannot determine service state; ask user
            if not messagebox.askyesno('Redis unknown', 'Could not determine Redis service state. Continue?'):
                return

        # Prefer launching OpenOB directly with the venv python so the UI keeps
        # the real process handle. This makes stop_openob() reliable.
        if not VENV_PY.exists():
            messagebox.showerror('Error', f'Venv python not found at {VENV_PY}')
            return

        if not OPENOB_SCRIPT.exists():
            # Fallback: if the helper script exists, warn but still allow user to continue
            if SCRIPT_START_OPENOB.exists():
                if not messagebox.askyesno('Warning', f'OBBroadcast entry script not found at {OPENOB_SCRIPT}. Use helper script instead?'):
                    return
            else:
                messagebox.showerror('Error', f'OBBroadcast entry script not found at {OPENOB_SCRIPT} and helper missing at {SCRIPT_START_OPENOB}')
                return

        # Build direct command: <venv_python> <openob_script> <args...>
        try:
            split_args = shlex.split(args)
        except Exception:
            split_args = args.split()

        cmd = [str(VENV_PY), str(OPENOB_SCRIPT)] + split_args
        try:
            # Start the real OBBroadcast process and stream output into the UI
            self.openob_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(REPO_ROOT), creationflags=creationflags)
            threading.Thread(target=self._stream_process_output, args=(self.openob_proc, 'OBBROADCAST'), daemon=True).start()
            self.append_log('Started OBBroadcast (direct venv python)\n')
            self.openob_status.set('OBBroadcast: running')
            # update indicator immediately
            try:
                self._update_indicators(self.redis_running, True)
            except Exception:
                pass
        except Exception as e:
            # As a last resort, offer to run the helper script if present
            if SCRIPT_START_OPENOB.exists():
                if messagebox.askyesno('Start fallback', f'Failed to start directly: {e}\nTry helper script instead?'):
                    try:
                        cmd2 = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(SCRIPT_START_OPENOB), '-OpenobArgs', args]
                        self.openob_proc = subprocess.Popen(cmd2, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(REPO_ROOT), creationflags=creationflags)
                        threading.Thread(target=self._stream_process_output, args=(self.openob_proc, 'OBBROADCAST'), daemon=True).start()
                        self.append_log('Started OBBroadcast (via start_openob.ps1 fallback)\n')
                        self.openob_status.set('OBBroadcast: running')
                        try:
                            self._update_indicators(self.redis_running, True)
                        except Exception:
                            pass
                        return
                    except Exception as e2:
                        messagebox.showerror('Error', f'Fallback also failed: {e2}')
                        return
            messagebox.showerror('Error', f'Failed to start OBBroadcast: {e}')

    def stop_openob(self):
        if self.openob_proc and self.openob_proc.poll() is None:
            try:
                # Ask the process to terminate gracefully
                self.openob_proc.terminate()
                self.append_log('Sent terminate to OpenOB process\n')
                # wait shortly for graceful exit
                try:
                    self.openob_proc.wait(timeout=3)
                except Exception:
                    # still running: force kill
                    try:
                        self.openob_proc.kill()
                        self.append_log('Killed OpenOB process\n')
                    except Exception:
                        self.append_log('Failed to kill OpenOB process\n')
            except Exception as e:
                self.append_log(f'Error stopping OpenOB: {e}\n')
            finally:
                self.openob_proc = None
                self.openob_status.set('OpenOB: stopped')
                try:
                    self._update_indicators(self.redis_running, False)
                except Exception:
                    pass
        else:
            messagebox.showinfo('Info', 'OpenOB not running')

    def start_all(self):
        self.start_redis()
        # small delay to let redis start
        time.sleep(0.5)
        self.start_openob()

    def stop_all(self):
        self.stop_openob()
        self.stop_redis()

    def _stream_process_output(self, proc, tag):
        try:
            for line in proc.stdout:
                if not line:
                    continue
                ts = time.strftime('%Y-%m-%d %H:%M:%S')
                self.append_log(f'[{tag} {ts}] {line}')
        except Exception:
            pass

    def _auto_start_if_enabled(self):
        if self._auto_started:
            return
        try:
            if self.auto_start_var.get():
                if not (self.openob_proc and self.openob_proc.poll() is None):
                    self._log_status('Auto-starting OBBroadcast (auto option enabled)', 'info', to_ui=True)
                    try:
                        self.start_openob()
                    except Exception as exc:
                        self._log_status(f'Auto-start attempt failed: {exc}', 'error', to_ui=True)
                else:
                    self._log_status('Auto-start skipped: OBBroadcast already running', 'info')
            else:
                self._log_status('Auto-start disabled by user; skipping automatic launch', 'info')
        finally:
            # Only run once per app launch; user can manually start later
            self._auto_started = True

    def _record_vu_status(self, target, status, detail=None):
        prev = self.vu_diag_state.get(target)
        if prev == status:
            return
        self.vu_diag_state[target] = status
        msg = f'{target.upper()} VU status: {status}'
        if detail:
            msg = f'{msg} ({detail})'
        level = 'info' if status == 'ok' else 'warning'
        self._log_status(msg, level=level, to_ui=(status != 'ok'))

    def _on_args_change(self, *args):
        self._update_link_details_from_args()

    def _open_settings_dialog(self):
        """Open a modal dialog to edit OBBroadcast launch parameters in fields."""
        # Parse current args into parts
        raw = self.args_var.get() if hasattr(self, 'args_var') else ''
        try:
            parts = shlex.split(raw)
        except Exception:
            parts = raw.split()

        # Defaults
        cfg_host = parts[0] if len(parts) >= 1 else ''
        node_name = parts[1] if len(parts) >= 2 else ''
        link_name = parts[2] if len(parts) >= 3 else ''
        mode = parts[3] if len(parts) >= 4 else 'tx'
        peer = parts[4] if len(parts) >= 5 else ''

        # options parsing: simple scan
        opts = {'-e': 'pcm', '-r': '', '-j': '', '-a': ''}
        i = 5
        while i < len(parts):
            p = parts[i]
            if p in opts and i + 1 < len(parts):
                opts[p] = parts[i+1]
                i += 2
            else:
                i += 1

        dlg = tk.Toplevel(self)
        dlg.title('Configuraciones de OBBroadcast')
        dlg.transient(self)
        dlg.grab_set()
        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill='both', expand=True)

        # Helper to create labeled entry
        def labeled(parent, label, value=''):
            row = ttk.Frame(parent)
            row.pack(fill='x', pady=2)
            ttk.Label(row, text=label, width=28).pack(side='left')
            ent = ttk.Entry(row)
            ent.insert(0, value)
            ent.pack(side='left', fill='x', expand=True)
            return ent

        e_cfg = labeled(frm, 'Host del servidor de configuración (config-host):', cfg_host)
        e_node = labeled(frm, 'Nombre del nodo (node-name):', node_name)
        e_link = labeled(frm, 'Nombre del enlace (link-name):', link_name)

        # mode combobox
        rowm = ttk.Frame(frm)
        rowm.pack(fill='x', pady=2)
        ttk.Label(rowm, text='Rol / modo:', width=28).pack(side='left')
        cb_mode = ttk.Combobox(rowm, values=['tx', 'rx'], width=8)
        cb_mode.set(mode if mode in ('tx', 'rx') else 'tx')
        cb_mode.pack(side='left')

        e_peer = labeled(frm, 'IP destino (peer) - para tx:', peer)

        # encoding, samplerate, jitter, audio backend
        row_e = ttk.Frame(frm)
        row_e.pack(fill='x', pady=2)
        ttk.Label(row_e, text='Encoding (-e):', width=28).pack(side='left')
        cb_enc = ttk.Combobox(row_e, values=['pcm', 'opus'], width=10)
        cb_enc.set(opts.get('-e') or 'pcm')
        cb_enc.pack(side='left')

        row_r = ttk.Frame(frm)
        row_r.pack(fill='x', pady=2)
        ttk.Label(row_r, text='Frecuencia muestreo (-r):', width=28).pack(side='left')
        e_rate = ttk.Entry(row_r)
        e_rate.insert(0, opts.get('-r') or '')
        e_rate.pack(side='left', fill='x', expand=True)

        row_j = ttk.Frame(frm)
        row_j.pack(fill='x', pady=2)
        ttk.Label(row_j, text='Jitter buffer (-j) ms:', width=28).pack(side='left')
        e_jit = ttk.Entry(row_j)
        e_jit.insert(0, opts.get('-j') or '')
        e_jit.pack(side='left', fill='x', expand=True)

        row_a = ttk.Frame(frm)
        row_a.pack(fill='x', pady=2)
        ttk.Label(row_a, text='Backend audio (-a):', width=28).pack(side='left')
        cb_audio = ttk.Combobox(row_a, values=['auto', 'alsa', 'jack', 'test', 'pulse'], width=12)
        cb_audio.set(opts.get('-a') or 'auto')
        cb_audio.pack(side='left')

        # Buttons
        btns = ttk.Frame(frm)
        btns.pack(fill='x', pady=(8, 0))

        def do_ok():
            cfg = e_cfg.get().strip()
            nodev = e_node.get().strip()
            linkv = e_link.get().strip()
            modev = cb_mode.get().strip()
            peerv = e_peer.get().strip()
            encv = cb_enc.get().strip()
            ratev = e_rate.get().strip()
            jv = e_jit.get().strip()
            av = cb_audio.get().strip()

            if not cfg or not nodev or not linkv or not modev:
                messagebox.showerror('Error', 'Rellenar: config-host, node-name, link-name y modo')
                return

            parts = [cfg, nodev, linkv, modev]
            if modev == 'tx' and peerv:
                parts.append(peerv)
            # options
            if encv:
                parts += ['-e', encv]
            if ratev:
                parts += ['-r', ratev]
            if jv:
                parts += ['-j', jv]
            if av:
                parts += ['-a', av]

            # Update args_var
            self.args_var.set(' '.join(parts))
            dlg.destroy()

        def do_cancel():
            dlg.destroy()

        ttk.Button(btns, text='Guardar', command=do_ok).pack(side='right', padx=4)
        ttk.Button(btns, text='Cancelar', command=do_cancel).pack(side='right')

        # Center dialog
        self.update_idletasks()
        dlg.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() // 2) - (dlg.winfo_width() // 2)
        y = self.winfo_rooty() + (self.winfo_height() // 2) - (dlg.winfo_height() // 2)
        dlg.geometry(f'+{x}+{y}')
        dlg.wait_window()

    def _toggle_logs(self):
        """Show or hide the logs panel."""
        if self._logs_visible:
            self.log_frame.place_forget()
            self._logs_visible = False
            self.btn_toggle_logs.config(text='📋 Logs')
        else:
            # Place logs panel as overlay at bottom
            self.log_frame.place(x=20, y=HEIGHT - 220, width=WIDTH - 40, height=200)
            self.log_frame.lift()
            self._logs_visible = True
            self.btn_toggle_logs.config(text='✕ Hide Logs')

    def _update_link_details_from_args(self):
        raw = self.args_var.get() if hasattr(self, 'args_var') else ''
        try:
            parts = shlex.split(raw)
        except Exception:
            parts = raw.split()

        prev_host = self.config_host
        self.config_host = parts[0] if len(parts) >= 1 else None
        self.node_id = parts[1] if len(parts) >= 2 else None
        self.link_name = parts[2] if len(parts) >= 3 else None
        self.link_mode = parts[3] if len(parts) >= 4 else None

        if prev_host != self.config_host:
            self._reset_redis_connection()

    def _reset_redis_connection(self):
        self.redis_client = None
        self.redis_host = None
        self.redis_port = 6379

    def _split_host_port(self, raw_host):
        if not raw_host:
            return None, None
        if ':' in raw_host:
            host, port = raw_host.split(':', 1)
            try:
                return host, int(port)
            except ValueError:
                return host, 6379
        return raw_host, 6379

    def _get_redis_client(self):
        if not HAS_REDIS_LIB:
            return None
        host = self.config_host
        if not host:
            return None
        host_only, port = self._split_host_port(host)
        if not host_only:
            return None
        if self.redis_client and host_only == self.redis_host and port == self.redis_port:
            return self.redis_client
        try:
            client = redis.StrictRedis(host=host_only, port=port, db=0, charset='utf-8', decode_responses=True)
            client.ping()
            self.redis_client = client
            self.redis_host = host_only
            self.redis_port = port
        except Exception:
            self.redis_client = None
        return self.redis_client

    def _fetch_and_apply_vu(self, client, role, target):
        """Fetch VU data from Redis and apply to the correct meter.
        
        Args:
            client: Redis client
            role: 'tx' for transmitter (local input) or 'rx' for receiver (remote)
            target: 'local' for Audio Input meter, 'remote' for Receiver Audio meter
        """
        link = self.link_name
        if not link:
            self._set_vu_silence_target(target)
            self._record_vu_status(target, 'no-link', 'Link name missing in args')
            return
        
        key = f'openob:{link}:vu:{role}'
        try:
            data = client.hgetall(key)
        except Exception:
            data = {}
        
        if not data:
            self._set_vu_silence_target(target)
            self._record_vu_status(target, 'no-data', f'Sin datos para clave {key}')
            return
        
        left = data.get('left_db') or data.get('left') or data.get('l')
        right = data.get('right_db') or data.get('right') or data.get('r')
        
        if left is None and right is None:
            combined = data.get('audio_level_db') or data.get('audio_level') or data.get('level')
            if combined:
                nums = re.findall(r'-?\d+(?:\.\d+)?', str(combined))
                if len(nums) >= 2:
                    left, right = nums[-2], nums[-1]
                elif len(nums) == 1:
                    left = right = nums[0]
        
        try:
            left_val = float(left) if left is not None else None
            right_val = float(right) if right is not None else left_val
        except Exception:
            left_val = right_val = None
        
        if left_val is None or right_val is None:
            self._set_vu_silence_target(target)
            self._record_vu_status(target, 'invalid-data', f'Datos sin valores numéricos en {key}')
            return
        
        updated = data.get('updated_ts') or data.get('ts')
        if updated is not None:
            try:
                updated = float(updated)
            except Exception:
                updated = None
            if updated is not None and (time.time() - updated) > 5:
                self._set_vu_silence_target(target)
                self._record_vu_status(target, 'stale', f'Datos viejos ({time.time()-updated:.1f}s) en {key}')
                return
        
        # Apply VU values to the correct target
        self._set_vu_levels_from_db(target, left_val, right_val)
        self._record_vu_status(target, 'ok', None)

    def _set_vu_silence_target(self, target):
        """Set specific VU meter to silence."""
        self._has_real_vu_data[target] = False
        if target == 'local':
            # Don't force to zero - let animation handle decay
            pass
        else:  # remote
            # Don't force to zero - let animation handle decay
            pass

    def _set_vu_silence(self):
        """Set all VU meters to silence (no signal)."""
        self._has_real_vu_data['local'] = False
        self._has_real_vu_data['remote'] = False

    def _set_vu_levels_from_db(self, target, left_db, right_db):
        """Convert dB values to normalized 0..1 levels for VU display.
        
        Args:
            target: 'local' for Audio Input, 'remote' for Receiver Audio
            left_db: Left channel level in dB
            right_db: Right channel level in dB
        """
        min_db = -65.0
        
        def db_to_normalized(db_val):
            if db_val is None:
                return 0.0
            try:
                db = float(db_val)
                db = max(min_db, min(0.0, db))
                return (db - min_db) / (0.0 - min_db)
            except Exception:
                return 0.0
        
        left_norm = db_to_normalized(left_db)
        right_norm = db_to_normalized(right_db)
        
        if target == 'local':
            # Audio Input meter (circular arcs)
            self.vu_left = 0.7 * self.vu_left + 0.3 * left_norm
            self.vu_right = 0.7 * self.vu_right + 0.3 * right_norm
            self._has_real_vu_data['local'] = True
        else:  # remote
            # Receiver Audio meter (horizontal bar)
            self.receiver_left = 0.7 * self.receiver_left + 0.3 * left_norm
            self.receiver_right = 0.7 * self.receiver_right + 0.3 * right_norm
            self._has_real_vu_data['remote'] = True

    def update_vu_loop(self):
        try:
            self._update_link_details_from_args()
            client = self._get_redis_client()
            if client and self.link_name:
                self._fetch_and_apply_vu(client, 'tx', 'local')
                # Also fetch remote for receiver display
                self._fetch_and_apply_vu(client, 'rx', 'remote')
            else:
                reason = 'Sin Redis' if not client else 'Link no definido'
                self._set_vu_silence()
                self._record_vu_status('local', 'blocked', reason)
                self._record_vu_status('remote', 'blocked', reason)
        except Exception:
            pass
        try:
            self.after(1000, self.update_vu_loop)
        except Exception:
            pass

    # ---------------------------
    # Close / tray behavior
    # ---------------------------
    def on_close(self):
        """Handle window close (X): prompt user to stop OpenOB, run in background, or cancel."""
        # If OpenOB not running, just close
        if not (self.openob_proc and self.openob_proc.poll() is None):
            self.destroy()
            return

        # OpenOB is running: show choice dialog
        choice = self._show_close_dialog()
        if choice == 'stop':
            # stop OpenOB then exit
            try:
                self.stop_openob()
            except Exception:
                pass
            self.destroy()
        elif choice == 'background':
            # Minimize to tray and keep OpenOB running
            if not HAS_TRAY:
                messagebox.showerror('Error', 'Tray support not available. Install: pip install pystray pillow')
                return
            self.withdraw()
            self._start_tray()
        else:
            # cancel -> do nothing
            return

    def _show_close_dialog(self):
        """Show a modal dialog with three options:
        'Detener OpenOB antes de cerrar' -> returns 'stop'
        'Continuar ejecutando en segundo plano' -> returns 'background'
        'Cancelar' -> returns 'cancel'
        """
        dlg = tk.Toplevel(self)
        dlg.title('Cerrar')
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)

        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill='both', expand=True)
        ttk.Label(frm, text='OBBroadcast está en ejecución. ¿Qué desea hacer al cerrar la interfaz?').pack(padx=6, pady=(0,10))

        result = {'choice': 'cancel'}

        def do_stop():
            result['choice'] = 'stop'
            dlg.destroy()

        def do_background():
            result['choice'] = 'background'
            dlg.destroy()

        def do_cancel():
            result['choice'] = 'cancel'
            dlg.destroy()

        btns = ttk.Frame(frm)
        btns.pack(fill='x')
        ttk.Button(btns, text='Detener OBBroadcast antes de cerrar', command=do_stop).pack(side='left', padx=4)
        ttk.Button(btns, text='Continuar ejecutando en segundo plano', command=do_background).pack(side='left', padx=4)
        ttk.Button(btns, text='Cancelar', command=do_cancel).pack(side='right', padx=4)

        # center dialog over parent
        self.update_idletasks()
        dlg.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() // 2) - (dlg.winfo_width() // 2)
        y = self.winfo_rooty() + (self.winfo_height() // 2) - (dlg.winfo_height() // 2)
        dlg.geometry(f'+{x}+{y}')

        self.wait_window(dlg)
        return result['choice']

    def _create_tray_image(self):
        # Prefer app PNG icon if present
        img_path = REPO_ROOT / 'ui' / 'images' / 'ob-logo.png'
        try:
            if img_path.exists():
                img = PILImage.open(str(img_path)).convert('RGBA')
                return img
        except Exception:
            pass
        # fallback: create a simple blank image
        try:
            img = PILImage.new('RGBA', (64, 64), (50, 50, 50, 255))
            return img
        except Exception:
            return None

    def _start_tray(self):
        """Create and run the pystray icon in a background thread."""
        if not HAS_TRAY:
            return
        if self.tray_icon is not None:
            return

        image = self._create_tray_image()
        if image is None:
            messagebox.showerror('Error', 'No tray icon image available')
            return

        menu = pystray.Menu(
            pystray.MenuItem('Restaurar', lambda _: self.after(0, self._tray_restore)),
            pystray.MenuItem('Detener OBBroadcast', lambda _: self.after(0, self.stop_openob)),
            pystray.MenuItem('Salir', lambda _: self.after(0, self._tray_exit))
        )

        self.tray_icon = pystray.Icon('openob', image, 'OBBroadcast', menu)

        def run_icon():
            try:
                self.tray_icon.run()
            except Exception:
                pass

        self.tray_thread = threading.Thread(target=run_icon, daemon=True)
        self.tray_thread.start()

    def _stop_tray(self):
        try:
            if self.tray_icon:
                self.tray_icon.stop()
                self.tray_icon = None
        except Exception:
            pass

    def _tray_restore(self):
        # Restore window from tray
        try:
            self.deiconify()
            self.after(100, lambda: self.lift())
        except Exception:
            pass
        self._stop_tray()

    def _tray_exit(self):
        # Stop OpenOB if running, then stop tray and exit
        try:
            if self.openob_proc and self.openob_proc.poll() is None:
                # Attempt graceful stop, then force
                try:
                    self.stop_openob()
                except Exception:
                    pass
        finally:
            try:
                self._stop_tray()
            except Exception:
                pass
            try:
                self.destroy()
            except Exception:
                sys.exit(0)

    def update_status_loop(self):
        # Update statuses (called once at startup)
        # Check Redis service state
        redis_running = False
        try:
            res = subprocess.run([
                'powershell', '-NoProfile', '-Command',
                "(Get-Service -Name Redis -ErrorAction SilentlyContinue).Status -join ''"
            ], capture_output=True, text=True, cwd=str(REPO_ROOT), creationflags=creationflags)
            svc = res.stdout.strip()
            redis_running = (svc == 'Running')
        except Exception:
            redis_running = False
        openob_running = bool(self.openob_proc and self.openob_proc.poll() is None)
        self.redis_status.set('Redis: running' if redis_running else 'Redis: stopped')
        self.openob_status.set('OpenOB: running' if openob_running else 'OpenOB: stopped')
        try:
            self._update_indicators(redis_running, openob_running)
        except Exception:
            pass
        # Schedule next status check (poll every 2 seconds)
        try:
            self.after(2000, self.update_status_loop)
        except Exception:
            pass


def main():
    app = OpenOBGUI()
    app.mainloop()


if __name__ == '__main__':
    main()
