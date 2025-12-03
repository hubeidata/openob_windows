# -*- coding: utf-8 -*-
"""
components.py - Reusable UI components/widgets.

Design decisions:
- Each visual component is a class encapsulating its drawing logic
- Components only handle rendering, no business logic
- State is passed in via update() methods
- Canvas-based drawing for performance
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
from typing import List, Dict, Optional, Tuple
from pathlib import Path

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class VUCircle:
    """
    Circular VU meter component with stereo arc segments.
    
    Draws concentric arc segments that light up based on audio level.
    Left channel on left side, right channel on right side.
    """
    
    def __init__(
        self,
        canvas: tk.Canvas,
        center_x: int,
        center_y: int,
        outer_radius: int = 130,
        center_radius: int = 95,
        num_rings: int = 9,
        ring_spacing: int = 10,
        arc_extent: int = 50
    ):
        self.canvas = canvas
        self.center_x = center_x
        self.center_y = center_y
        self.outer_radius = outer_radius
        self.center_radius = center_radius
        self.num_rings = num_rings
        self.ring_spacing = ring_spacing
        self.arc_extent = arc_extent
        
        # Colors
        self.inactive_color = "#cfcfcf"
        self.ring_colors = (
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
        self.thresholds = (0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.78, 0.90)
        
        # Segment IDs storage
        self.segments: List[Dict] = []
        
        # Draw static elements
        self._draw_background()
        self._draw_arcs()
    
    def _draw_background(self) -> None:
        """Draw background circles."""
        ox, oy = self.center_x, self.center_y
        
        # Gray outer ring
        self.canvas.create_oval(
            ox - self.outer_radius, oy - self.outer_radius,
            ox + self.outer_radius, oy + self.outer_radius,
            fill="#d0d3d6", outline="", tags='vu_bg'
        )
        
        # Red center circle
        self.canvas.create_oval(
            ox - self.center_radius, oy - self.center_radius,
            ox + self.center_radius, oy + self.center_radius,
            fill="#d9534f", outline="", tags='vu_center'
        )
        
        # Label
        self.canvas.create_text(
            self.center_x, oy - self.center_radius - 22,
            text="Audio Input",
            font=("Segoe UI", 11, "bold"),
            fill="#333333",
            anchor='s',
            tags='label'
        )
    
    def _draw_arcs(self) -> None:
        """Draw VU arc segments."""
        ox, oy = self.center_x, self.center_y
        base_outer = self.center_radius + 8
        
        for ring in range(self.num_rings):
            r = base_outer + ring * self.ring_spacing
            width = max(3, 10 - ring)
            
            # Left arc
            left_start = 180 - self.arc_extent / 2
            cid_l = self.canvas.create_arc(
                ox - r, oy - r, ox + r, oy + r,
                start=left_start, extent=self.arc_extent,
                style=tk.ARC, width=width, outline=self.inactive_color,
                tags='vu_arc'
            )
            self.segments.append({'id': cid_l, 'side': 'left', 'ring': ring})
            
            # Right arc
            right_start = (360 - self.arc_extent / 2) % 360
            cid_r = self.canvas.create_arc(
                ox - r, oy - r, ox + r, oy + r,
                start=right_start, extent=self.arc_extent,
                style=tk.ARC, width=width, outline=self.inactive_color,
                tags='vu_arc'
            )
            self.segments.append({'id': cid_r, 'side': 'right', 'ring': ring})
    
    def update(self, left_level: float, right_level: float) -> None:
        """
        Update VU display based on levels.
        
        Args:
            left_level: Left channel level (0.0 to 1.0)
            right_level: Right channel level (0.0 to 1.0)
        """
        for seg in self.segments:
            ring = seg['ring']
            side = seg['side']
            cid = seg['id']
            threshold = self.thresholds[ring]
            
            level = left_level if side == 'left' else right_level
            
            if level >= threshold:
                color = self.ring_colors[ring]
            else:
                color = self.inactive_color
            
            self.canvas.itemconfigure(cid, outline=color)
    
    def set_center_image(self, image: tk.PhotoImage) -> None:
        """Set center icon image."""
        self.canvas.create_image(
            self.center_x, self.center_y,
            image=image,
            tags='center_icon'
        )


class ReceiverBar:
    """
    Horizontal receiver audio bar component.
    
    Displays audio level as a bar expanding from center to both sides.
    Color changes based on level (green -> yellow -> red).
    """
    
    def __init__(
        self,
        canvas: tk.Canvas,
        center_x: int,
        y: int,
        width: int = 500,
        height: int = 20
    ):
        self.canvas = canvas
        self.center_x = center_x
        self.y = y
        self.width = width
        self.height = height
        
        self.x1 = center_x - width // 2
        self.x2 = center_x + width // 2
        self.half_len = width // 2
        
        # Colors
        self.color_green = "#3fbf5f"
        self.color_yellow = "#f2c94c"
        self.color_red = "#e04b4b"
        
        # Draw static elements
        self._draw_background()
        
        # Create dynamic elements
        self._create_bars()
    
    def _draw_background(self) -> None:
        """Draw background and static elements."""
        # Label
        self.canvas.create_text(
            self.center_x, self.y - 12,
            text="Receiver Audio",
            font=("Segoe UI", 11, "bold"),
            fill="#333333",
            anchor='center',
            tags='label'
        )
        
        # Background bar
        self.canvas.create_rectangle(
            self.x1, self.y, self.x2, self.y + self.height,
            fill="#dbe0e3", outline="#c9cfd3", width=1,
            tags='bar_bg'
        )
        
        # Center line
        self.canvas.create_line(
            self.center_x, self.y - 6,
            self.center_x, self.y + self.height + 6,
            fill="#b9b9b9", tags='bar_center'
        )
        
        # Tick marks
        ticks = 8
        for i in range(ticks + 1):
            tx = self.x1 + self.width * (i / ticks)
            self.canvas.create_line(
                tx, self.y - 4, tx, self.y + self.height + 4,
                fill="#e0e0e0", tags='bar_tick'
            )
        
        # Extremes
        self.canvas.create_line(
            self.x1, self.y - 6, self.x1, self.y + self.height + 6,
            fill="#b9b9b9"
        )
        self.canvas.create_line(
            self.x2, self.y - 6, self.x2, self.y + self.height + 6,
            fill="#b9b9b9"
        )
    
    def _create_bars(self) -> None:
        """Create dynamic bar elements."""
        # Left and right bars from center
        self.bar_left = self.canvas.create_rectangle(
            self.center_x, self.y, self.center_x, self.y + self.height,
            fill=self.color_green, outline="", tags='bar_level'
        )
        self.bar_right = self.canvas.create_rectangle(
            self.center_x, self.y, self.center_x, self.y + self.height,
            fill=self.color_green, outline="", tags='bar_level'
        )
        
        # Rounded caps
        cap_pad = self.height // 2
        self.cap_left = self.canvas.create_oval(
            self.center_x - cap_pad, self.y,
            self.center_x + cap_pad, self.y + self.height,
            fill=self.color_green, outline="", tags='bar_cap'
        )
        self.cap_right = self.canvas.create_oval(
            self.center_x - cap_pad, self.y,
            self.center_x + cap_pad, self.y + self.height,
            fill=self.color_green, outline="", tags='bar_cap'
        )
    
    def update(self, level: float) -> None:
        """
        Update bar display based on level.
        
        Args:
            level: Audio level (0.0 to 1.0)
        """
        level = max(0.0, min(1.0, level))
        cur = int(level * self.half_len)
        
        # Update bar positions
        self.canvas.coords(
            self.bar_left,
            self.center_x - cur, self.y,
            self.center_x, self.y + self.height
        )
        self.canvas.coords(
            self.bar_right,
            self.center_x, self.y,
            self.center_x + cur, self.y + self.height
        )
        
        # Update caps
        cap_pad = self.height // 2
        if cur <= 0:
            # Hide caps
            self.canvas.coords(self.cap_left, -10, -10, -5, -5)
            self.canvas.coords(self.cap_right, -10, -10, -5, -5)
        else:
            left_cap_x = max(self.center_x - cur, self.x1 + cap_pad)
            right_cap_x = min(self.center_x + cur, self.x2 - cap_pad)
            self.canvas.coords(
                self.cap_left,
                left_cap_x - cap_pad, self.y,
                left_cap_x + cap_pad, self.y + self.height
            )
            self.canvas.coords(
                self.cap_right,
                right_cap_x - cap_pad, self.y,
                right_cap_x + cap_pad, self.y + self.height
            )
        
        # Color based on level
        level_norm = cur / float(self.half_len) if self.half_len else 0
        if level_norm >= 0.9:
            color = self.color_red
        elif level_norm >= 0.65:
            color = self.color_yellow
        else:
            color = self.color_green
        
        self.canvas.itemconfigure(self.bar_left, fill=color)
        self.canvas.itemconfigure(self.bar_right, fill=color)
        self.canvas.itemconfigure(self.cap_left, fill=color)
        self.canvas.itemconfigure(self.cap_right, fill=color)


class LogPanel:
    """
    Collapsible log panel component.
    
    Displays log messages with syntax highlighting by level.
    """
    
    def __init__(self, parent: tk.Widget, width: int, height: int):
        self.parent = parent
        self.width = width
        self.height = height
        self.visible = False
        
        self._create_frame()
    
    def _create_frame(self) -> None:
        """Create log frame and widgets."""
        self.frame = tk.Frame(self.parent, bg='#f0f0f0', bd=2, relief='groove')
        
        # Header
        header = tk.Frame(self.frame, bg='#e0e0e0')
        header.pack(fill='x')
        
        tk.Label(
            header, text="📋 Logs",
            font=('Segoe UI', 10, 'bold'),
            bg='#e0e0e0'
        ).pack(side='left', padx=8, pady=4)
        
        ttk.Button(
            header, text="✕", width=3,
            command=self.hide
        ).pack(side='right', padx=4, pady=2)
        
        # Log text widget
        self.text = scrolledtext.ScrolledText(
            self.frame, state='disabled', wrap='word',
            font=('Consolas', 9), bg='#1e1e1e', fg='#d4d4d4',
            insertbackground='white'
        )
        self.text.pack(fill='both', expand=True, padx=4, pady=4)
        
        # Configure tags
        self.text.tag_configure('INFO', foreground='#4fc3f7')
        self.text.tag_configure('WARN', foreground='#ffb74d')
        self.text.tag_configure('WARNING', foreground='#ffb74d')
        self.text.tag_configure('ERROR', foreground='#ef5350')
        self.text.tag_configure('OBBROADCAST', foreground='#81c784')
    
    def show(self, x: int, y: int) -> None:
        """Show log panel at position."""
        self.frame.place(x=x, y=y, width=self.width, height=self.height)
        self.frame.lift()
        self.visible = True
    
    def hide(self) -> None:
        """Hide log panel."""
        self.frame.place_forget()
        self.visible = False
    
    def toggle(self, x: int, y: int) -> None:
        """Toggle log panel visibility."""
        if self.visible:
            self.hide()
        else:
            self.show(x, y)
    
    def append(self, text: str) -> None:
        """Append text with level highlighting."""
        self.text.configure(state='normal')
        
        # Determine tag
        tag = None
        text_upper = text.upper()
        if 'ERROR' in text_upper:
            tag = 'ERROR'
        elif 'WARN' in text_upper:
            tag = 'WARN'
        elif 'INFO' in text_upper:
            tag = 'INFO'
        elif 'OBBROADCAST' in text_upper:
            tag = 'OBBROADCAST'
        
        if tag:
            self.text.insert('end', text, tag)
        else:
            self.text.insert('end', text)
        
        self.text.see('end')
        self.text.configure(state='disabled')


class IconLoader:
    """Helper for loading and caching icons."""
    
    def __init__(self):
        self._cache: Dict[str, tk.PhotoImage] = {}
    
    def load(self, path: Path, size: Optional[Tuple[int, int]] = None) -> Optional[tk.PhotoImage]:
        """Load icon from path, optionally resizing."""
        cache_key = f"{path}:{size}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        if not path.exists():
            return None
        
        try:
            if PIL_AVAILABLE and size:
                img = Image.open(str(path)).convert("RGBA")
                img = img.resize(size, Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
            else:
                photo = tk.PhotoImage(file=str(path))
            
            self._cache[cache_key] = photo
            return photo
            
        except Exception:
            return None
