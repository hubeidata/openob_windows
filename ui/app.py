# -*- coding: utf-8 -*-
"""
app.py - Application entry point.

This is the main entry point for the OBBroadcast UI application.
It initializes configuration, sets up paths, and launches the main window.
"""

import sys
import os
import tkinter as tk
from pathlib import Path

# Ensure the ui package is importable
SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent

# Add parent to path for imports
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ui.core.models import AppConfig
from ui.main_window import MainWindow
from ui.services.utils import configure_logging, get_logger


def setup_environment() -> None:
    """
    Configure environment variables for GStreamer and GTK.
    Must be called before importing GTK-related modules.
    """
    # GStreamer paths (same as run_ui.bat)
    gst_bin = Path(r'C:\Program Files\gstreamer\1.0\msvc_x86_64\bin')
    gst_gir = Path(r'C:\Program Files\gstreamer\1.0\msvc_x86_64\lib\girepository-1.0')
    
    if gst_bin.exists():
        os.environ['PATH'] = str(gst_bin) + os.pathsep + os.environ.get('PATH', '')
        os.environ['GST_PLUGIN_PATH'] = str(gst_bin)
    
    if gst_gir.exists():
        os.environ['GI_TYPELIB_PATH'] = str(gst_gir)


def create_config() -> AppConfig:
    """
    Create application configuration with resolved paths.
    """
    log_dir = REPO_ROOT / 'logs'
    log_dir.mkdir(exist_ok=True)
    
    return AppConfig(
        repo_root=REPO_ROOT,
        venv_python=REPO_ROOT / '.venv' / 'Scripts' / 'python.exe',
        openob_script=REPO_ROOT / '.venv' / 'Scripts' / 'openob',  # Script sin extensión, usar con python.exe
        start_script=REPO_ROOT / 'scripts' / 'start_openob.ps1',
        gstreamer_bin=Path(r'C:\Program Files\gstreamer\1.0\msvc_x86_64\bin'),
        gstreamer_gir=Path(r'C:\Program Files\gstreamer\1.0\msvc_x86_64\lib\girepository-1.0'),
        log_dir=log_dir,
        ui_log_file=log_dir / 'ui.log',
        icon_path=REPO_ROOT / 'ui' / 'images' / 'input_line.png',
        width=960,
        height=700,
        default_args='127.0.0.1 emetteur transmission tx 192.168.1.17 -e pcm -r 48000 -j 60 -a auto'
    )


def main() -> int:
    """
    Main entry point.
    
    Returns:
        Exit code (0 for success)
    """
    # Setup environment first
    setup_environment()
    
    # Create configuration
    config = create_config()
    
    # Configure logging
    configure_logging(config.ui_log_file)
    logger = get_logger(__name__)
    
    logger.info("=" * 60)
    logger.info("OBBroadcast UI starting")
    logger.info(f"Python: {sys.version}")
    logger.info(f"Repo root: {config.repo_root}")
    logger.info("=" * 60)
    
    try:
        # Create Tk root
        root = tk.Tk()
        
        # Create and run main window
        app = MainWindow(root, config)
        app.run()
        
        logger.info("Application closed normally")
        return 0
        
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
