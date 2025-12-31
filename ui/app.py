# --- PATH debug dump ---
try:
    import os
    path_debug_file = os.path.join(os.path.dirname(__file__), '..', 'logs', 'ui_path_debug.txt')
    os.makedirs(os.path.dirname(path_debug_file), exist_ok=True)
    with open(path_debug_file, 'w', encoding='utf-8') as f:
        f.write(os.environ.get('PATH', ''))
except Exception as e:
    pass
# -*- coding: utf-8 -*-
"""
app.py - Application entry point.

This is the main entry point for the OBBroadcast UI application.
It initializes configuration, sets up paths, and launches the main window.
"""

import sys
import os
import logging
# --- Logging setup ---
log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'ui_runtime.log')
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8', mode='a'),
        logging.StreamHandler(sys.stdout)
    ]
)

def excepthook(type, value, tb):
    import traceback
    logging.error('Uncaught exception:', exc_info=(type, value, tb))
    sys.__excepthook__(type, value, tb)

sys.excepthook = excepthook

class StreamToLogger:
    def __init__(self, logger, level, is_stderr: bool = False):
        self.logger = logger
        self.level = level
        self.linebuf = ''
        self.is_stderr = is_stderr
        self._in_write = False
        # Save original stream to avoid recursion when logging subsystem writes to stderr
        self._orig_stream = sys.__stderr__ if is_stderr else sys.__stdout__
    def write(self, buf):
        try:
            # Ensure we have a str
            if not isinstance(buf, str):
                try:
                    buf = buf.decode('utf-8', errors='replace')
                except Exception:
                    buf = str(buf)

            # If we're already inside write, fallback to original stream to avoid recursion
            if self._in_write:
                try:
                    self._orig_stream.write(buf)
                except Exception:
                    pass
                return

            self._in_write = True
            for line in buf.rstrip('\n').splitlines():
                # If the logging system itself emits a 'Logging error', write it directly
                # to the original stderr to avoid infinite recursion.
                if 'Logging error' in line:
                    try:
                        sys.__stderr__.write(line + os.linesep)
                    except Exception:
                        pass
                else:
                    self.logger.log(self.level, line.rstrip())
        finally:
            self._in_write = False
    def flush(self):
        try:
            self._orig_stream.flush()
        except Exception:
            pass

sys.stdout = StreamToLogger(logging.getLogger('STDOUT'), logging.INFO, is_stderr=False)
sys.stderr = StreamToLogger(logging.getLogger('STDERR'), logging.ERROR, is_stderr=True)
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


def _load_env_file(env_path: Path) -> dict:
    """Load simple KEY=VALUE env file (ignores empty lines and # comments)."""
    values: dict[str, str] = {}
    try:
        for raw in env_path.read_text(encoding='utf-8').splitlines():
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip()
            v = v.strip()
            if k:
                values[k] = v
    except Exception:
        return {}
    return values


def setup_environment() -> None:
    """
    Configure environment variables for GStreamer and GTK.
    Must be called before importing GTK-related modules.
    """
    # Prefer installed app config when available: {repo_root}\config\gstreamer.env
    env_file = REPO_ROOT / 'config' / 'gstreamer.env'
    if env_file.exists():
        values = _load_env_file(env_file)
        for k, v in values.items():
            os.environ[k] = v

    # Resolve and set derived GStreamer env variables
    gst_bin = _resolve_env_path(os.environ.get('GstBin', r'C:\Program Files\gstreamer\1.0\msvc_x86_64\bin'))
    gst_gir = _resolve_env_path(os.environ.get('GI_TYPELIB_PATH', r'C:\Program Files\gstreamer\1.0\msvc_x86_64\lib\girepository-1.0'))
    gst_py_site = os.environ.get('GstPySitePackages', '')

    # Derive GstPySitePackages from GstBin if not provided
    if not gst_py_site and str(gst_bin).lower().endswith('\\bin'):
        gst_root = str(gst_bin.parent)
        gst_py_site = str(Path(gst_root) / 'lib' / 'site-packages')
        os.environ['GstPySitePackages'] = gst_py_site

    if gst_bin.exists():
        os.environ['PATH'] = str(gst_bin) + os.pathsep + os.environ.get('PATH', '')
        os.environ['GST_PLUGIN_PATH'] = str(gst_bin)

    if gst_gir.exists():
        os.environ['GI_TYPELIB_PATH'] = str(gst_gir)

    # Ensure Python can import gi (PyGObject) from GStreamer runtime
    if gst_py_site:
        gst_py_site_path = Path(gst_py_site)
        if gst_py_site_path.exists():
            existing = os.environ.get('PYTHONPATH', '')
            if existing:
                os.environ['PYTHONPATH'] = str(gst_py_site_path) + os.pathsep + existing
            else:
                os.environ['PYTHONPATH'] = str(gst_py_site_path)


def _resolve_env_path(val: str) -> Path:
    if not val:
        return Path()
    p = Path(val)
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p


def create_config() -> AppConfig:
    """
    Create application configuration with resolved paths.
    """
    log_dir = REPO_ROOT / 'logs'
    log_dir.mkdir(exist_ok=True)

    # Dev mode (repo) uses .venv; installed mode uses embedded runtime under {app}\python
    venv_python = REPO_ROOT / '.venv' / 'Scripts' / 'python.exe'
    openob_script = REPO_ROOT / '.venv' / 'Scripts' / 'openob.exe'
    start_script = REPO_ROOT / 'scripts' / 'start_openob.ps1'

    embedded_python = REPO_ROOT / 'python' / 'python.exe'
    embedded_openob = REPO_ROOT / 'python' / 'Scripts' / 'openob.exe'
    if embedded_python.exists():
        venv_python = embedded_python
    if embedded_openob.exists():
        openob_script = embedded_openob
    if not start_script.exists():
        # Not required for normal operation; only used if UI chooses fallback mode.
        start_script = REPO_ROOT / 'scripts' / 'start_openob.ps1'

    gst_bin = Path(os.environ.get('GstBin', r'C:\Program Files\gstreamer\1.0\msvc_x86_64\bin'))
    gst_gir = Path(os.environ.get('GI_TYPELIB_PATH', r'C:\Program Files\gstreamer\1.0\msvc_x86_64\lib\girepository-1.0'))
    
    return AppConfig(
        repo_root=REPO_ROOT,
        venv_python=venv_python,
        openob_script=openob_script,
        start_script=start_script,
        gstreamer_bin=gst_bin,
        gstreamer_gir=gst_gir,
        log_dir=log_dir,
        ui_log_file=log_dir / 'ui.log',
        icon_path=REPO_ROOT / 'ui' / 'images' / 'input_line.png',
        width=960,
        height=700,
        default_args='127.0.0.1 emetteur transmission tx 192.168.1.17 -e opus -b 48 -r 48000 -j 60 -a auto'
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
