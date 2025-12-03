# -*- coding: utf-8 -*-
"""
main_window.py - Main application window.

Design decisions:
- MainWindow only handles UI layout and event binding
- All business logic delegated to AppController
- Uses component widgets (VUMeterCircle, ReceiverBar)
- Clean separation of concerns
"""

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
from typing import Optional, Callable
import os

from .core.models import AppConfig, AppState, VUState, LinkConfig
from .core.controller import AppController
from .components.widgets import VUCircle, ReceiverBar
from .components.dialogs import SettingsDialog, CloseDialog
from .services.utils import get_logger, configure_logging

# Alias for compatibility
VUMeterCircle = VUCircle


logger = get_logger(__name__)


class MainWindow:
    """
    Main application window for OpenOB broadcast control.
    
    Responsibilities:
    - UI layout and widget creation
    - Event binding and delegation to controller
    - Periodic UI updates from controller state
    """
    
    def __init__(self, root: tk.Tk, config: AppConfig):
        self.root = root
        self.config = config
        
        # Initialize controller
        self.controller = AppController(config)
        self.controller.set_root(root)
        
        # Window configuration
        self._setup_window()
        
        # Create UI
        self._create_canvas()
        self._create_widgets()
        self._load_logo()
        
        # Bind events
        self._bind_events()
        
        # Start update loops
        self._start_update_loops()
        
        logger.info("MainWindow initialized")
    
    def _setup_window(self) -> None:
        """Configure main window properties."""
        self.root.title('OBBroadcast Control')
        self.root.geometry(f'{self.config.width}x{self.config.height}')
        self.root.resizable(False, False)
        
        # Background color
        self.root.configure(bg='#1a1a2e')
        
        # Protocol handlers
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
    
    def _create_canvas(self) -> None:
        """Create main canvas."""
        self.canvas = tk.Canvas(
            self.root,
            width=self.config.width,
            height=self.config.height,
            bg='#1a1a2e',
            highlightthickness=0
        )
        self.canvas.pack(fill='both', expand=True)
    
    def _create_widgets(self) -> None:
        """Create all UI widgets."""
        cx = self.config.center_x
        
        # Title
        self.canvas.create_text(
            cx, 40,
            text='OBBroadcast',
            font=('Segoe UI', 28, 'bold'),
            fill='white'
        )
        
        # VU Meters
        self._create_vu_meters()
        
        # Receiver bar
        self._create_receiver_bar()
        
        # Control buttons
        self._create_buttons()
        
        # Status label
        self._create_status_label()
    
    def _create_vu_meters(self) -> None:
        """Create left and right VU meter components."""
        cx = self.config.center_x
        vu_y = 280
        vu_offset = 240
        
        # Left VU (local/input)
        self.vu_left = VUMeterCircle(
            self.canvas,
            cx - vu_offset,
            vu_y
        )
        
        # Right VU (remote/receiver)
        self.vu_right = VUMeterCircle(
            self.canvas,
            cx + vu_offset,
            vu_y
        )
    
    def _create_receiver_bar(self) -> None:
        """Create horizontal receiver level bar."""
        cx = self.config.center_x
        bar_y = 480
        
        self.receiver_bar = ReceiverBar(
            self.canvas,
            cx,
            bar_y,
            width=500,
            height=20
        )
    
    def _create_buttons(self) -> None:
        """Create control buttons."""
        cx = self.config.center_x
        btn_y = 580
        
        # Toggle button (Start/Stop)
        self.btn_toggle = tk.Button(
            self.root,
            text='Stop',
            command=self._on_toggle_click,
            font=('Segoe UI', 14, 'bold'),
            bg='#e74c3c',
            fg='white',
            activebackground='#c0392b',
            activeforeground='white',
            width=10,
            height=1
        )
        self.canvas.create_window(cx, btn_y, window=self.btn_toggle)
        
        # Settings button (bottom-right corner)
        self.btn_settings = tk.Button(
            self.root,
            text='⚙ Settings',
            command=self._on_settings_click,
            font=('Segoe UI', 10),
            bg='#555555',
            fg='white',
            activebackground='#666666',
            activeforeground='white'
        )
        self.canvas.create_window(
            self.config.width - 70,
            self.config.height - 40,
            window=self.btn_settings
        )
    
    def _create_status_label(self) -> None:
        """Create status text label."""
        cx = self.config.center_x
        
        self.status_id = self.canvas.create_text(
            cx, 640,
            text='Iniciando...',
            font=('Segoe UI', 11),
            fill='#aaaaaa'
        )
    
    def _load_logo(self) -> None:
        """Load and display center logo."""
        # Placeholder for center logos in VU meters
        logo_size = 90
        
        if self.config.icon_path.exists():
            try:
                img = Image.open(self.config.icon_path)
                img = img.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
                
                # Store references to prevent garbage collection
                self._logo_left = ImageTk.PhotoImage(img)
                self._logo_right = ImageTk.PhotoImage(img)
                
                # Update VU meter centers
                self.vu_left.set_center_image(self._logo_left)
                self.vu_right.set_center_image(self._logo_right)
                
            except Exception as e:
                logger.warning(f"Failed to load logo: {e}")
    
    def _bind_events(self) -> None:
        """Bind keyboard and window events."""
        self.root.bind('<Escape>', lambda e: self._on_close())
        self.root.bind('<Control-q>', lambda e: self._on_close())
    
    def _start_update_loops(self) -> None:
        """Start periodic update loops."""
        # VU meter update (100ms for smooth animation)
        self._vu_update_id = self.root.after(100, self._update_vu_loop)
        
        # Status update (500ms)
        self._status_update_id = self.root.after(500, self._update_status_loop)
        
        # Cooldown update (1000ms)
        self._cooldown_update_id = self.root.after(1000, self._update_cooldown_loop)
    
    def _update_vu_loop(self) -> None:
        """Update VU meters from controller state."""
        state = self.controller.state
        
        # Update circular VU meters (left/right channels)
        self.vu_left.update(
            state.local_vu.left,
            state.local_vu.right
        )
        self.vu_right.update(
            state.remote_vu.left,
            state.remote_vu.right
        )
        
        # Update receiver bar
        self.receiver_bar.update(state.receiver_level)
        
        # Schedule next update
        self._vu_update_id = self.root.after(100, self._update_vu_loop)
    
    def _update_status_loop(self) -> None:
        """Update status display from controller state."""
        state = self.controller.state
        
        # Update button appearance
        self._update_toggle_button(state)
        
        # Update status text
        self._update_status_text(state)
        
        # Schedule next update
        self._status_update_id = self.root.after(500, self._update_status_loop)
    
    def _update_cooldown_loop(self) -> None:
        """Update cooldown state."""
        state = self.controller.state
        
        if state.cooldown_active and state.cooldown_remaining > 0:
            self.controller.tick_cooldown()
            
            if state.cooldown_remaining <= 0:
                # Cooldown finished
                self._update_toggle_button(state)
        
        self._cooldown_update_id = self.root.after(1000, self._update_cooldown_loop)
    
    def _update_toggle_button(self, state: AppState) -> None:
        """Update toggle button based on state."""
        if state.cooldown_active:
            # Cooldown state
            self.btn_toggle.config(
                text=f'Espere ({state.cooldown_remaining}s)',
                bg='#7f8c8d',
                state='disabled'
            )
        elif state.openob_running:
            # Running state - show Stop
            self.btn_toggle.config(
                text='Stop',
                bg='#e74c3c',
                state='normal'
            )
        else:
            # Stopped state - show Start
            self.btn_toggle.config(
                text='Start',
                bg='#27ae60',
                state='normal'
            )
    
    def _update_status_text(self, state: AppState) -> None:
        """Update status label text."""
        if state.cooldown_active:
            text = f"Esperando {state.cooldown_remaining}s..."
            color = '#f39c12'
        elif state.openob_running:
            text = "OpenOB en ejecución"
            color = '#2ecc71'
        else:
            text = "OpenOB detenido"
            color = '#e74c3c'
        
        self.canvas.itemconfig(self.status_id, text=text, fill=color)
    
    def _on_toggle_click(self) -> None:
        """Handle toggle button click."""
        state = self.controller.state
        
        if state.cooldown_active:
            return  # Ignore during cooldown
        
        if state.openob_running:
            # Stop OpenOB
            self.controller.stop_openob()
            self.controller.start_cooldown(5)  # 5 second cooldown
        else:
            # Start OpenOB
            self.controller.start_openob()
    
    def _on_settings_click(self) -> None:
        """Handle settings button click."""
        config = LinkConfig.from_args(self.controller.current_args)
        
        dialog = SettingsDialog(
            self.root,
            config,
            on_logs_click=self._show_logs
        )
        self.root.wait_window(dialog)
        
        if dialog.result and dialog.result.saved:
            self.controller.update_args(dialog.result.args)
            logger.info(f"Settings updated: {dialog.result.args}")
    
    def _show_logs(self) -> None:
        """Show logs window or file."""
        log_file = self.config.ui_log_file
        if log_file.exists():
            os.startfile(str(log_file))
        else:
            messagebox.showinfo("Logs", "No hay archivo de logs disponible.")
    
    def _on_close(self) -> None:
        """Handle window close request."""
        state = self.controller.state
        
        if state.openob_running:
            # Show close dialog
            dialog = CloseDialog(self.root, has_tray_support=False)
            choice = dialog.show()
            
            if choice == CloseDialog.CHOICE_STOP:
                self.controller.stop_openob()
                self._cleanup_and_close()
            elif choice == CloseDialog.CHOICE_BACKGROUND:
                self._minimize_to_tray()
            # CANCEL: do nothing
        else:
            self._cleanup_and_close()
    
    def _cleanup_and_close(self) -> None:
        """Clean up resources and close application."""
        logger.info("Closing application")
        
        # Cancel scheduled updates
        if hasattr(self, '_vu_update_id'):
            self.root.after_cancel(self._vu_update_id)
        if hasattr(self, '_status_update_id'):
            self.root.after_cancel(self._status_update_id)
        if hasattr(self, '_cooldown_update_id'):
            self.root.after_cancel(self._cooldown_update_id)
        
        # Cleanup controller
        self.controller.cleanup()
        
        # Destroy window
        self.root.destroy()
    
    def _minimize_to_tray(self) -> None:
        """Minimize to system tray (if supported)."""
        # TODO: Implement tray icon support
        self.root.withdraw()
        logger.info("Minimized to tray (placeholder)")
    
    def run(self) -> None:
        """Start the application main loop."""
        # Start VU loop in controller
        self.controller.start_vu_loop()
        
        # Run Tkinter mainloop
        self.root.mainloop()
