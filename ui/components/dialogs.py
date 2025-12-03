# -*- coding: utf-8 -*-
"""
dialogs.py - Dialog windows for settings and confirmations.

Design decisions:
- Each dialog is a class inheriting from tk.Toplevel
- Dialogs are modal and return results via result property
- Clean separation from main window logic
- Callbacks for communication with controller
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable
from dataclasses import dataclass

from ..core.models import LinkConfig


@dataclass
class SettingsResult:
    """Result from settings dialog."""
    saved: bool
    args: str = ""


class SettingsDialog(tk.Toplevel):
    """
    Settings dialog for editing OBBroadcast launch parameters.
    """
    
    def __init__(
        self,
        parent: tk.Widget,
        current_config: LinkConfig,
        on_logs_click: Optional[Callable[[], None]] = None
    ):
        super().__init__(parent)
        
        self.title('Configuraciones de OBBroadcast')
        self.transient(parent)
        self.grab_set()
        
        self._config = current_config
        self._on_logs_click = on_logs_click
        self._result: Optional[SettingsResult] = None
        
        self._create_widgets()
        self._center_on_parent(parent)
    
    @property
    def result(self) -> Optional[SettingsResult]:
        """Get dialog result after close."""
        return self._result
    
    def _create_widgets(self) -> None:
        """Create dialog widgets."""
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill='both', expand=True)
        
        # Config host
        self.e_cfg = self._labeled_entry(
            frame,
            'Host del servidor de configuración (config-host):',
            self._config.config_host or ''
        )
        
        # Node name
        self.e_node = self._labeled_entry(
            frame,
            'Nombre del nodo (node-name):',
            self._config.node_id or ''
        )
        
        # Link name
        self.e_link = self._labeled_entry(
            frame,
            'Nombre del enlace (link-name):',
            self._config.link_name or ''
        )
        
        # Mode combobox
        row_mode = ttk.Frame(frame)
        row_mode.pack(fill='x', pady=2)
        ttk.Label(row_mode, text='Rol / modo:', width=28).pack(side='left')
        self.cb_mode = ttk.Combobox(row_mode, values=['tx', 'rx'], width=8)
        self.cb_mode.set(self._config.link_mode or 'tx')
        self.cb_mode.pack(side='left')
        
        # Peer IP
        self.e_peer = self._labeled_entry(
            frame,
            'IP destino (peer) - para tx:',
            self._config.peer_ip or ''
        )
        
        # Encoding
        row_enc = ttk.Frame(frame)
        row_enc.pack(fill='x', pady=2)
        ttk.Label(row_enc, text='Encoding (-e):', width=28).pack(side='left')
        self.cb_enc = ttk.Combobox(row_enc, values=['pcm', 'opus'], width=10)
        self.cb_enc.set(self._config.encoding or 'pcm')
        self.cb_enc.pack(side='left')
        
        # Sample rate
        self.e_rate = self._labeled_entry(
            frame,
            'Frecuencia muestreo (-r):',
            self._config.sample_rate or ''
        )
        
        # Jitter buffer
        self.e_jit = self._labeled_entry(
            frame,
            'Jitter buffer (-j) ms:',
            self._config.jitter_buffer or ''
        )
        
        # Audio backend
        row_audio = ttk.Frame(frame)
        row_audio.pack(fill='x', pady=2)
        ttk.Label(row_audio, text='Backend audio (-a):', width=28).pack(side='left')
        self.cb_audio = ttk.Combobox(
            row_audio,
            values=['auto', 'alsa', 'jack', 'test', 'pulse'],
            width=12
        )
        self.cb_audio.set(self._config.audio_backend or 'auto')
        self.cb_audio.pack(side='left')
        
        # Separator
        ttk.Separator(frame, orient='horizontal').pack(fill='x', pady=(12, 8))
        
        # Logs button
        logs_frame = ttk.Frame(frame)
        logs_frame.pack(fill='x', pady=(0, 8))
        ttk.Button(
            logs_frame, text="📋 Ver Logs",
            command=self._on_logs
        ).pack(side='left')
        ttk.Label(
            logs_frame,
            text="Ver registro de actividad",
            font=('Segoe UI', 8),
            foreground='#666666'
        ).pack(side='left', padx=(8, 0))
        
        # Buttons
        btns = ttk.Frame(frame)
        btns.pack(fill='x', pady=(8, 0))
        ttk.Button(btns, text='Guardar', command=self._on_save).pack(side='right', padx=4)
        ttk.Button(btns, text='Cancelar', command=self._on_cancel).pack(side='right')
    
    def _labeled_entry(
        self,
        parent: ttk.Frame,
        label: str,
        value: str
    ) -> ttk.Entry:
        """Create labeled entry row."""
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=2)
        ttk.Label(row, text=label, width=28).pack(side='left')
        entry = ttk.Entry(row)
        entry.insert(0, value)
        entry.pack(side='left', fill='x', expand=True)
        return entry
    
    def _center_on_parent(self, parent: tk.Widget) -> None:
        """Center dialog on parent window."""
        self.update_idletasks()
        parent.update_idletasks()
        
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        
        self.geometry(f'+{x}+{y}')
    
    def _on_save(self) -> None:
        """Handle save button."""
        cfg = self.e_cfg.get().strip()
        node = self.e_node.get().strip()
        link = self.e_link.get().strip()
        mode = self.cb_mode.get().strip()
        
        if not cfg or not node or not link or not mode:
            messagebox.showerror(
                'Error',
                'Rellenar: config-host, node-name, link-name y modo'
            )
            return
        
        # Build new config
        config = LinkConfig(
            config_host=cfg,
            node_id=node,
            link_name=link,
            link_mode=mode,
            peer_ip=self.e_peer.get().strip() if mode == 'tx' else None,
            encoding=self.cb_enc.get().strip(),
            sample_rate=self.e_rate.get().strip(),
            jitter_buffer=self.e_jit.get().strip(),
            audio_backend=self.cb_audio.get().strip()
        )
        
        self._result = SettingsResult(saved=True, args=config.to_args())
        self.destroy()
    
    def _on_cancel(self) -> None:
        """Handle cancel button."""
        self._result = SettingsResult(saved=False)
        self.destroy()
    
    def _on_logs(self) -> None:
        """Handle logs button."""
        if self._on_logs_click:
            self._on_logs_click()
        self.destroy()


class CloseDialog(tk.Toplevel):
    """
    Dialog shown when closing with OpenOB running.
    
    Options:
    - Stop OpenOB and close
    - Continue in background (tray)
    - Cancel
    """
    
    CHOICE_STOP = 'stop'
    CHOICE_BACKGROUND = 'background'
    CHOICE_CANCEL = 'cancel'
    
    def __init__(self, parent: tk.Widget, has_tray_support: bool = True):
        super().__init__(parent)
        
        self.title('Cerrar')
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        
        self._has_tray = has_tray_support
        self._result = self.CHOICE_CANCEL
        
        self._create_widgets()
        self._center_on_parent(parent)
    
    @property
    def result(self) -> str:
        """Get dialog result after close."""
        return self._result
    
    def _create_widgets(self) -> None:
        """Create dialog widgets."""
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill='both', expand=True)
        
        ttk.Label(
            frame,
            text='OBBroadcast está en ejecución. ¿Qué desea hacer al cerrar la interfaz?'
        ).pack(padx=6, pady=(0, 10))
        
        btns = ttk.Frame(frame)
        btns.pack(fill='x')
        
        ttk.Button(
            btns,
            text='Detener OBBroadcast antes de cerrar',
            command=self._on_stop
        ).pack(side='left', padx=4)
        
        if self._has_tray:
            ttk.Button(
                btns,
                text='Continuar ejecutando en segundo plano',
                command=self._on_background
            ).pack(side='left', padx=4)
        
        ttk.Button(
            btns,
            text='Cancelar',
            command=self._on_cancel
        ).pack(side='right', padx=4)
    
    def _center_on_parent(self, parent: tk.Widget) -> None:
        """Center dialog on parent window."""
        self.update_idletasks()
        parent.update_idletasks()
        
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        
        self.geometry(f'+{x}+{y}')
    
    def _on_stop(self) -> None:
        self._result = self.CHOICE_STOP
        self.destroy()
    
    def _on_background(self) -> None:
        self._result = self.CHOICE_BACKGROUND
        self.destroy()
    
    def _on_cancel(self) -> None:
        self._result = self.CHOICE_CANCEL
        self.destroy()
    
    def show(self) -> str:
        """Show dialog and return result."""
        self.wait_window()
        return self._result
