# -*- coding: utf-8 -*-
"""
process_service.py - Process management for Redis and OpenOB services.

Design decisions:
- Encapsulates all subprocess operations
- Separates Windows service management from process management
- Uses callbacks for output streaming
- Handles process lifecycle (start, stop, status check)
"""

import subprocess
import threading
import shlex
import time
import logging
from pathlib import Path
from typing import Optional, Callable, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger('openob.ui.process')

# Hide PowerShell windows on Windows
CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0


class ServiceStatus(Enum):
    """Windows service status."""
    RUNNING = "Running"
    STOPPED = "Stopped"
    NOT_INSTALLED = "NotInstalled"
    UNKNOWN = "Unknown"


@dataclass
class ProcessResult:
    """Result of a process operation."""
    success: bool
    message: str = ""
    return_code: int = 0


class RedisServiceManager:
    """
    Manages the Redis Windows service.
    
    Uses PowerShell to start/stop/check Redis service status.
    """
    
    SERVICE_NAME = "Redis"
    
    def __init__(self, working_dir: Optional[Path] = None):
        self._working_dir = working_dir
    
    def get_status(self) -> ServiceStatus:
        """Get current Redis service status."""
        try:
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 f"(Get-Service -Name {self.SERVICE_NAME} -ErrorAction SilentlyContinue).Status -join ''"],
                capture_output=True,
                text=True,
                cwd=str(self._working_dir) if self._working_dir else None,
                creationflags=CREATION_FLAGS
            )
            status = result.stdout.strip()
            
            if status == "Running":
                return ServiceStatus.RUNNING
            elif status == "Stopped":
                return ServiceStatus.STOPPED
            elif not status:
                return ServiceStatus.NOT_INSTALLED
            else:
                return ServiceStatus.UNKNOWN
                
        except Exception as e:
            logger.warning(f"Failed to check Redis service status: {e}")
            return ServiceStatus.UNKNOWN
    
    def start(self) -> ProcessResult:
        """Start the Redis service."""
        try:
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command', 
                 f'Start-Service -Name {self.SERVICE_NAME}'],
                capture_output=True,
                text=True,
                cwd=str(self._working_dir) if self._working_dir else None,
                creationflags=CREATION_FLAGS
            )
            
            if result.returncode == 0:
                logger.info("Redis service started successfully")
                return ProcessResult(success=True, message="Redis service started")
            else:
                logger.error(f"Failed to start Redis: {result.stderr}")
                return ProcessResult(
                    success=False, 
                    message=f"Failed to start Redis: {result.stderr}",
                    return_code=result.returncode
                )
                
        except Exception as e:
            logger.error(f"Exception starting Redis: {e}")
            return ProcessResult(success=False, message=str(e))
    
    def stop(self) -> ProcessResult:
        """Stop the Redis service."""
        try:
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command', 
                 f'Stop-Service -Name {self.SERVICE_NAME} -Force'],
                capture_output=True,
                text=True,
                cwd=str(self._working_dir) if self._working_dir else None,
                creationflags=CREATION_FLAGS
            )
            
            if result.returncode == 0:
                logger.info("Redis service stopped successfully")
                return ProcessResult(success=True, message="Redis service stopped")
            else:
                logger.error(f"Failed to stop Redis: {result.stderr}")
                return ProcessResult(
                    success=False,
                    message=f"Failed to stop Redis: {result.stderr}",
                    return_code=result.returncode
                )
                
        except Exception as e:
            logger.error(f"Exception stopping Redis: {e}")
            return ProcessResult(success=False, message=str(e))


class OpenOBProcessManager:
    """
    Manages the OpenOB process.
    
    Handles starting, stopping, and monitoring the OpenOB process.
    """
    
    def __init__(
        self,
        venv_python: Path,
        openob_script: Path,
        fallback_script: Optional[Path] = None,
        working_dir: Optional[Path] = None
    ):
        self._venv_python = venv_python
        self._openob_script = openob_script
        self._fallback_script = fallback_script
        self._working_dir = working_dir
        
        self._process: Optional[subprocess.Popen] = None
        self._output_thread: Optional[threading.Thread] = None
    
    @property
    def is_running(self) -> bool:
        """Check if OpenOB process is currently running."""
        return self._process is not None and self._process.poll() is None
    
    @property
    def process(self) -> Optional[subprocess.Popen]:
        """Get the current process handle."""
        return self._process
    
    def can_start(self) -> tuple[bool, str]:
        """
        Check if OpenOB can be started.
        
        Returns:
            Tuple of (can_start, error_message)
        """
        if not self._venv_python.exists():
            return False, f"Venv python not found at {self._venv_python}"
        
        if not self._openob_script.exists():
            if self._fallback_script and self._fallback_script.exists():
                return True, ""  # Can use fallback
            return False, f"OpenOB script not found at {self._openob_script}"
        
        return True, ""
    
    def start(
        self, 
        args: str, 
        output_callback: Optional[Callable[[str], None]] = None,
        use_fallback: bool = False
    ) -> ProcessResult:
        """
        Start the OpenOB process.
        
        Args:
            args: OpenOB command line arguments
            output_callback: Optional callback for stdout lines
            use_fallback: Use fallback PowerShell script instead
            
        Returns:
            ProcessResult indicating success/failure
        """
        if self.is_running:
            return ProcessResult(success=False, message="OpenOB already running")
        
        if not args.strip():
            return ProcessResult(success=False, message="Empty OpenOB arguments")
        
        try:
            split_args = shlex.split(args)
        except Exception:
            split_args = args.split()
        
        try:
            if use_fallback and self._fallback_script and self._fallback_script.exists():
                cmd = [
                    'powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                    '-File', str(self._fallback_script),
                    '-OpenobArgs', args
                ]
            else:
                cmd = [str(self._venv_python), str(self._openob_script)] + split_args
            
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(self._working_dir) if self._working_dir else None,
                creationflags=CREATION_FLAGS
            )
            
            # Start output streaming thread
            if output_callback:
                self._output_thread = threading.Thread(
                    target=self._stream_output,
                    args=(output_callback,),
                    daemon=True
                )
                self._output_thread.start()
            
            method = "fallback script" if use_fallback else "direct venv"
            logger.info(f"Started OpenOB ({method})")
            return ProcessResult(success=True, message=f"Started OpenOB ({method})")
            
        except Exception as e:
            logger.error(f"Failed to start OpenOB: {e}")
            return ProcessResult(success=False, message=str(e))
    
    def stop(self, timeout: float = 3.0) -> ProcessResult:
        """
        Stop the OpenOB process.
        
        Args:
            timeout: Seconds to wait for graceful termination before force kill
            
        Returns:
            ProcessResult indicating success/failure
        """
        if not self.is_running:
            return ProcessResult(success=False, message="OpenOB not running")
        
        try:
            # Try graceful termination first
            self._process.terminate()
            logger.info("Sent terminate signal to OpenOB")
            
            try:
                self._process.wait(timeout=timeout)
                logger.info("OpenOB terminated gracefully")
            except subprocess.TimeoutExpired:
                # Force kill
                self._process.kill()
                logger.warning("OpenOB force killed after timeout")
            
            self._process = None
            return ProcessResult(success=True, message="OpenOB stopped")
            
        except Exception as e:
            logger.error(f"Error stopping OpenOB: {e}")
            self._process = None
            return ProcessResult(success=False, message=str(e))
    
    def _stream_output(self, callback: Callable[[str], None]) -> None:
        """Stream process output to callback."""
        try:
            if self._process and self._process.stdout:
                for line in self._process.stdout:
                    if line:
                        callback(line)
        except Exception as e:
            logger.debug(f"Output streaming ended: {e}")


class RequirementsChecker:
    """
    Checks system requirements for the application.
    """
    
    def __init__(self, gstreamer_bin: Path, working_dir: Optional[Path] = None):
        self._gstreamer_bin = gstreamer_bin
        self._working_dir = working_dir
        self._redis_manager = RedisServiceManager(working_dir)
    
    def check_all(self) -> List[str]:
        """
        Check all requirements.
        
        Returns:
            List of status messages
        """
        messages = []
        
        # Check Redis library
        try:
            import redis
            messages.append("redis: OK")
        except ImportError:
            messages.append("redis: MISSING")
        
        # Check GStreamer bindings
        try:
            import gi
            gi.require_version('Gst', '1.0')
            from gi.repository import Gst
            messages.append("gi/Gst: OK")
        except Exception:
            messages.append("gi/Gst: MISSING")
        
        # Check GStreamer binaries
        if self._gstreamer_bin.exists():
            messages.append("GStreamer bins: OK")
        else:
            messages.append(f"GStreamer bins not found at {self._gstreamer_bin}")
        
        # Check Redis service
        status = self._redis_manager.get_status()
        if status == ServiceStatus.NOT_INSTALLED:
            messages.append("Redis service: NOT INSTALLED")
        else:
            messages.append(f"Redis service: {status.value}")
        
        return messages
    
    def is_redis_running(self) -> bool:
        """Check if Redis service is running."""
        return self._redis_manager.get_status() == ServiceStatus.RUNNING
