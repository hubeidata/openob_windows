# -*- coding: utf-8 -*-
"""
controller.py - Main application controller.

Design decisions:
- Acts as mediator between UI and services
- Manages application state
- Handles all business logic (VU processing, service coordination)
- UI only calls controller methods, never services directly
- Uses callbacks for UI updates (loose coupling)
"""

from __future__ import annotations

import time
import logging
from pathlib import Path
from typing import Optional, Callable, List, Any, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    import tkinter as tk

from .models import AppConfig, AppState, VUState, LinkConfig, VUVisualConfig
from ..services.redis_service import RedisService, VUData
from ..services.process_service import (
    RedisServiceManager, 
    OpenOBProcessManager, 
    RequirementsChecker,
    ServiceStatus,
    ProcessResult
)
from ..services.config_storage import ConfigStorageService, SavedConfig
from ..services.utils import (
    db_to_normalized, 
    apply_vu_jitter, 
    smooth_value,
    get_refresh_rate_ms,
    simulate_vu_level,
    setup_logging
)


logger = logging.getLogger('openob.ui.controller')


@dataclass
class UICallbacks:
    """Callbacks for UI updates from controller."""
    on_log: Optional[Callable[[str], None]] = None
    on_status_change: Optional[Callable[[bool, bool], None]] = None  # (redis_running, openob_running)
    on_requirements_check: Optional[Callable[[List[str]], None]] = None
    on_cooldown_tick: Optional[Callable[[int], None]] = None
    on_cooldown_end: Optional[Callable[[], None]] = None


class AppController:
    """
    Main application controller.
    
    Coordinates between UI, services, and manages application state.
    """
    
    COOLDOWN_SECONDS = 5
    VU_POLL_INTERVAL_MS = 100
    STATUS_POLL_INTERVAL_MS = 2000
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.state = AppState()
        self.vu_config = VUVisualConfig()
        self.callbacks = UICallbacks()
        
        # Initialize config storage service (for persistent settings)
        self._config_storage = ConfigStorageService(config.repo_root / 'ui')
        self._config_storage.load()
        
        # Initialize services
        self._redis_service = RedisService()
        self._redis_manager = RedisServiceManager(config.repo_root)
        self._openob_manager = OpenOBProcessManager(
            venv_python=config.venv_python,
            openob_script=config.openob_script,
            fallback_script=config.start_script,
            working_dir=config.repo_root
        )
        self._requirements_checker = RequirementsChecker(
            gstreamer_bin=config.gstreamer_bin,
            working_dir=config.repo_root
        )
        
        # Setup logging
        self._logger = setup_logging(config.ui_log_file)
        
        # Current link configuration
        self._link_config: Optional[LinkConfig] = None
        # Use saved args if available, otherwise use default
        self._args_string: str = self._config_storage.config.get_current_args()
        
        # VU loop state
        self._vu_loop_running = False
        self._vu_after_id: Optional[str] = None
        self._root: Optional[Any] = None  # tk.Tk
    
    # -------------------------
    # Properties
    # -------------------------
    
    @property
    def current_args(self) -> str:
        """Get current OpenOB arguments string."""
        return self._args_string
    
    @property
    def saved_config(self) -> SavedConfig:
        """Get saved configuration."""
        return self._config_storage.config
    
    @property
    def auto_start_enabled(self) -> bool:
        """Get auto-start setting from saved config."""
        return self._config_storage.config.auto_start
    
    # -------------------------
    # Initialization
    # -------------------------
    
    def initialize(self) -> None:
        """Initialize controller and check requirements."""
        self._update_link_config()
        self.check_requirements()
    
    def check_requirements(self) -> List[str]:
        """Check system requirements and return status messages."""
        messages = self._requirements_checker.check_all()
        
        # Update state
        self.state.redis_running = self._requirements_checker.is_redis_running()
        self.state.openob_running = self._openob_manager.is_running
        
        # Notify UI
        if self.callbacks.on_requirements_check:
            self.callbacks.on_requirements_check(messages)
        
        self._notify_status_change()
        return messages
    
    # -------------------------
    # OpenOB Arguments
    # -------------------------
    
    def get_args(self) -> str:
        """Get current OpenOB arguments string."""
        return self._args_string
    
    def set_args(self, args: str) -> None:
        """Set OpenOB arguments and update link config."""
        self._args_string = args
        self._update_link_config()
        
        # Save to persistent storage
        mode = 'rx' if ' rx ' in args or args.endswith(' rx') else 'tx'
        self._config_storage.update_from_args(args, mode)
        self._config_storage.save()
    
    def set_auto_start(self, enabled: bool) -> None:
        """Set and save auto-start preference."""
        self._config_storage.update(auto_start=enabled)
        self._config_storage.save()
    
    def update_args(self, args: str) -> None:
        """Alias for set_args - update OpenOB arguments."""
        self.set_args(args)
    
    def get_link_config(self) -> Optional[LinkConfig]:
        """Get current link configuration."""
        return self._link_config
    
    def _update_link_config(self) -> None:
        """Parse and update link configuration from args."""
        old_host = self._link_config.config_host if self._link_config else None
        self._link_config = LinkConfig.from_args(self._args_string)
        
        # Reset Redis connection if host changed
        if old_host != self._link_config.config_host:
            self._redis_service.disconnect()
    
    # -------------------------
    # Redis Service Control
    # -------------------------
    
    def start_redis(self) -> ProcessResult:
        """Start Redis service."""
        result = self._redis_manager.start()
        
        if result.success:
            self._log("Requested Start-Service Redis")
            time.sleep(0.3)  # Brief delay for service to start
            self.state.redis_running = self._requirements_checker.is_redis_running()
            self._notify_status_change()
        else:
            self._log(f"Start-Service failed: {result.message}", level='error')
        
        return result
    
    def stop_redis(self) -> ProcessResult:
        """Stop Redis service."""
        result = self._redis_manager.stop()
        
        if result.success:
            self._log("Requested Stop-Service Redis")
            self.state.redis_running = False
            self._notify_status_change()
        else:
            self._log(f"Stop-Service failed: {result.message}", level='error')
        
        return result
    
    def is_redis_running(self) -> bool:
        """Check if Redis is running."""
        status = self._redis_manager.get_status()
        self.state.redis_running = (status == ServiceStatus.RUNNING)
        return self.state.redis_running
    
    # -------------------------
    # OpenOB Process Control
    # -------------------------
    
    def start_openob(self, use_fallback: bool = False) -> ProcessResult:
        """Start OpenOB process."""
        # Check if can start
        can_start, error = self._openob_manager.can_start()
        if not can_start and not use_fallback:
            return ProcessResult(success=False, message=error)
        
        # Check Redis
        if not self.is_redis_running():
            return ProcessResult(
                success=False, 
                message="Redis not running",
                return_code=-1  # Special code to indicate Redis check
            )
        
        # Log the command that will be executed
        self._log(f"Executing OpenOB with args: {self._args_string}")
        
        # Start process
        result = self._openob_manager.start(
            args=self._args_string,
            output_callback=self._handle_openob_output,
            use_fallback=use_fallback
        )
        
        if result.success:
            self._log(f"Started OBBroadcast ({result.message})")
            self.state.openob_running = True
            self._notify_status_change()
        else:
            self._log(f"Failed to start OBBroadcast: {result.message}", level='error')
        
        return result
    
    def stop_openob(self) -> ProcessResult:
        """Stop OpenOB process."""
        if not self._openob_manager.is_running:
            return ProcessResult(success=False, message="OpenOB not running")
        
        result = self._openob_manager.stop()
        
        if result.success:
            self._log("Stopped OBBroadcast")
        else:
            self._log(f"Error stopping OBBroadcast: {result.message}", level='error')
        
        self.state.openob_running = False
        self._notify_status_change()
        
        return result
    
    def is_openob_running(self) -> bool:
        """Check if OpenOB is running."""
        self.state.openob_running = self._openob_manager.is_running
        return self.state.openob_running
    
    def toggle_openob(self) -> ProcessResult:
        """Toggle OpenOB: stop if running, start if stopped."""
        if self.state.cooldown_active:
            return ProcessResult(success=False, message="Cooldown active")
        
        if self.is_openob_running():
            result = self.stop_openob()
            if result.success:
                self._start_cooldown()
            return result
        else:
            return self.start_openob()
    
    def _handle_openob_output(self, line: str) -> None:
        """Handle output line from OpenOB process."""
        from ..services.utils import format_timestamp
        ts = format_timestamp()
        self._log(f"[OBBROADCAST {ts}] {line.rstrip()}", to_ui_only=True)
    
    # -------------------------
    # Cooldown Management
    # -------------------------
    
    def start_cooldown(self, seconds: int = None) -> None:
        """
        Start cooldown period.
        
        Args:
            seconds: Cooldown duration (default: COOLDOWN_SECONDS)
        """
        self.state.cooldown_active = True
        self.state.cooldown_remaining = seconds if seconds else self.COOLDOWN_SECONDS
    
    def _start_cooldown(self) -> None:
        """Start cooldown period after stopping OpenOB."""
        self.start_cooldown(self.COOLDOWN_SECONDS)
    
    def tick_cooldown(self) -> bool:
        """
        Process one second of cooldown.
        
        Returns:
            True if cooldown still active, False if finished
        """
        if not self.state.cooldown_active:
            return False
        
        self.state.cooldown_remaining -= 1
        
        if self.state.cooldown_remaining <= 0:
            self.state.cooldown_active = False
            self.state.cooldown_remaining = 0
            if self.callbacks.on_cooldown_end:
                self.callbacks.on_cooldown_end()
            return False
        
        if self.callbacks.on_cooldown_tick:
            self.callbacks.on_cooldown_tick(self.state.cooldown_remaining)
        
        return True
    
    # -------------------------
    # VU Meter Processing
    # -------------------------
    
    def update_vu_from_redis(self) -> None:
        """Fetch VU data from Redis and update state."""
        if not self._link_config or not self._link_config.link_name:
            self._set_vu_silence('local', 'no-link', 'Link name missing')
            self._set_vu_silence('remote', 'no-link', 'Link name missing')
            return
        
        # Connect to Redis if needed
        if not self._redis_service.is_connected:
            host, port = RedisService.parse_host_port(self._link_config.config_host)
            if not host or not self._redis_service.connect(host, port):
                self._set_vu_silence('local', 'blocked', 'Cannot connect to Redis')
                self._set_vu_silence('remote', 'blocked', 'Cannot connect to Redis')
                return
        
        # Fetch and apply VU data
        link = self._link_config.link_name
        self._fetch_and_apply_vu(link, 'tx', 'local')
        self._fetch_and_apply_vu(link, 'rx', 'remote')
    
    def _fetch_and_apply_vu(self, link: str, role: str, target: str) -> None:
        """Fetch VU data for a specific role and apply to target."""
        vu_data = self._redis_service.fetch_vu_data(link, role)
        
        if vu_data is None:
            self._set_vu_silence(target, 'no-data', f'No data for {role}')
            return
        
        if vu_data.is_stale:
            self._set_vu_silence(target, 'stale', f'Stale data for {role}')
            return
        
        # Convert dB to normalized and apply
        self._apply_vu_data(target, vu_data.left_db, vu_data.right_db)
        self._record_vu_status(target, 'ok')
    
    def _apply_vu_data(self, target: str, left_db: float, right_db: float) -> None:
        """Apply VU dB values to state with jitter and smoothing."""
        left_norm = db_to_normalized(left_db)
        right_norm = db_to_normalized(right_db)
        
        avg = (left_norm + right_norm) / 2
        left_norm, right_norm, smooth = apply_vu_jitter(left_norm, right_norm, avg)
        
        if target == 'local':
            vu = self.state.local_vu
            vu.left = smooth_value(vu.left, left_norm, smooth)
            vu.right = smooth_value(vu.right, right_norm, smooth)
            vu.has_real_data = True
        else:
            vu = self.state.remote_vu
            vu.left = smooth_value(vu.left, left_norm, smooth)
            vu.right = smooth_value(vu.right, right_norm, smooth)
            vu.has_real_data = True
    
    def _set_vu_silence(self, target: str, status: str, detail: str) -> None:
        """Set VU to silence mode (let animation handle decay)."""
        if target == 'local':
            self.state.local_vu.has_real_data = False
        else:
            self.state.remote_vu.has_real_data = False
        
        self._record_vu_status(target, status, detail)
    
    def _record_vu_status(self, target: str, status: str, detail: str = None) -> None:
        """Record VU diagnostic status change."""
        prev = self.state.vu_diag_state.get(target)
        if prev == status:
            return
        
        self.state.vu_diag_state[target] = status
        
        msg = f'{target.upper()} VU status: {status}'
        if detail:
            msg = f'{msg} ({detail})'
        
        level = 'info' if status == 'ok' else 'warning'
        to_ui = status != 'ok'
        self._log(msg, level=level, to_ui_only=to_ui)
    
    def animate_vu(self) -> int:
        """
        Process VU animation frame.
        
        Returns:
            Next frame delay in milliseconds
        """
        # Local VU (Audio Input)
        if not self.state.local_vu.has_real_data:
            if self.state.openob_running:
                # Simulate VU
                self.state.local_vu.left = smooth_value(
                    self.state.local_vu.left,
                    simulate_vu_level(0.0),
                    0.75
                )
                self.state.local_vu.right = smooth_value(
                    self.state.local_vu.right,
                    simulate_vu_level(0.5),
                    0.75
                )
            else:
                self.state.local_vu.decay()
        
        # Remote VU (Receiver)
        if not self.state.remote_vu.has_real_data:
            if self.state.openob_running:
                level = simulate_vu_level(1.0, 0.8)
                self.state.receiver_level = smooth_value(
                    self.state.receiver_level,
                    level,
                    0.8
                )
            else:
                self.state.remote_vu.decay()
                self.state.receiver_level *= 0.85
                if self.state.receiver_level < 0.01:
                    self.state.receiver_level = 0.0
        else:
            # Use real data
            self.state.receiver_level = self.state.remote_vu.average
        
        # Calculate refresh rate
        max_level = max(
            self.state.local_vu.max_level,
            self.state.receiver_level
        )
        return get_refresh_rate_ms(max_level)
    
    # -------------------------
    # Status Updates
    # -------------------------
    
    def refresh_status(self) -> None:
        """Refresh all status values."""
        self.state.redis_running = self._requirements_checker.is_redis_running()
        self.state.openob_running = self._openob_manager.is_running
        self._notify_status_change()
    
    def _notify_status_change(self) -> None:
        """Notify UI of status change."""
        if self.callbacks.on_status_change:
            self.callbacks.on_status_change(
                self.state.redis_running,
                self.state.openob_running
            )
    
    # -------------------------
    # Logging
    # -------------------------
    
    def _log(
        self, 
        message: str, 
        level: str = 'info', 
        to_ui_only: bool = False
    ) -> None:
        """Log message to file and optionally to UI."""
        if not to_ui_only:
            log_fn = getattr(self._logger, level, self._logger.info)
            log_fn(message)
        
        if self.callbacks.on_log and (to_ui_only or level != 'debug'):
            self.callbacks.on_log(message + '\n')
    
    # -------------------------
    # Cleanup
    # -------------------------
    
    def cleanup(self) -> None:
        """Clean shutdown of controller."""
        self.stop_vu_loop()
        if self._openob_manager.is_running:
            self._openob_manager.stop()
        self._redis_service.disconnect()
    
    def shutdown(self) -> None:
        """Alias for cleanup - clean shutdown of controller."""
        self.cleanup()
    
    # -------------------------
    # VU Loop Control
    # -------------------------
    
    def set_root(self, root: Any) -> None:
        """Set Tk root for scheduled callbacks."""
        self._root = root
    
    def start_vu_loop(self) -> None:
        """Start the VU meter update loop."""
        self._vu_loop_running = True
        self._vu_loop_tick()
    
    def stop_vu_loop(self) -> None:
        """Stop the VU meter update loop."""
        self._vu_loop_running = False
        if self._vu_after_id and self._root:
            try:
                self._root.after_cancel(self._vu_after_id)
            except Exception:
                pass
            self._vu_after_id = None
    
    def _vu_loop_tick(self) -> None:
        """Single tick of VU loop."""
        if not self._vu_loop_running:
            return
        
        try:
            # Fetch VU data from Redis
            self.update_vu_from_redis()
            
            # Process animation frame
            next_delay = self.animate_vu()
            
            # Schedule next tick
            if self._root:
                self._vu_after_id = self._root.after(next_delay, self._vu_loop_tick)
            
        except Exception as e:
            self._log(f"VU loop error: {e}", level='error')
            # Continue loop even on error
            if self._root:
                self._vu_after_id = self._root.after(100, self._vu_loop_tick)
