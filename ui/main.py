#!/usr/bin/env python3
"""
Simple Tkinter GUI to start/stop Redis and OBBroadcast, show status and logs, and edit launch args.

Usage: run from repo root (or double-click):
    python ui\main.py

Notes:
 - Uses the repository layout created during the session:
     .venv\Scripts\python.exe
     .venv\Scripts\openob
     redis-server\redis-server.exe
 - Checks for Python modules `redis` and `gi` (GStreamer) and presence of GStreamer bins.
 - Default OBBroadcast args: -v 127.0.0.1 emetteur transmission tx 192.168.8.17 -e pcm -r 48000 -j 60 -a test
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
from pathlib import Path

try:
    import redis
    HAS_REDIS_LIB = True
except Exception:
    redis = None
    HAS_REDIS_LIB = False


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

DEFAULT_OPENOB_ARGS = '127.0.0.1 emetteur transmission tx 192.168.1.17 -e pcm -r 48000 -j 60 -a auto'

# Optional system tray support
try:
    import pystray
    from PIL import Image
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
        self.geometry('900x600')
        # Set application icon (prefer PNG for window, ICO for taskbar/shortcut)
        try:
            img_png = REPO_ROOT / 'ui' / 'images' / 'ob-logo.png'
            img_ico = REPO_ROOT / 'ui' / 'images' / 'ob-logo.ico'
            if img_png.exists():
                # keep reference to avoid GC
                self._icon_img = tk.PhotoImage(file=str(img_png))
                try:
                    # iconphoto works for many platforms and sets the window icon
                    self.iconphoto(False, self._icon_img)
                except Exception:
                    pass
            if img_ico.exists():
                try:
                    # iconbitmap for Windows taskbar and legacy support
                    self.iconbitmap(str(img_ico))
                except Exception:
                    pass
        except Exception:
            # don't fail UI if icons can't be loaded
            pass
        # redis is managed as a Windows service now; we don't spawn redis-server.exe
        self.redis_proc = None
        self.openob_proc = None
        self.openob_thread = None
        self.redis_running = False
        self.redis_client = None
        self.redis_client = None
        self.redis_host = None
        self.redis_port = 6379
        self.vu_diag_state = {'local': None, 'remote': None}
        self.auto_start_var = tk.BooleanVar(value=True)
        self._auto_started = False
        self.redis_host = None
        self.redis_port = 6379
        self.config_host = None
        self.link_name = None
        self.node_id = None
        self.link_mode = None
        # tray icon state
        self.tray_icon = None
        self.tray_thread = None

        # Handle window close
        self.after(1500, self._auto_start_if_enabled)
        self.protocol('WM_DELETE_WINDOW', self.on_close)

        self.create_widgets()
        self.check_requirements()
        self.update_status_loop()
        self.update_vu_loop()

    def create_widgets(self):
        frm = ttk.Frame(self)
        frm.pack(fill='both', expand=True, padx=8, pady=8)

        top = ttk.Frame(frm)
        top.pack(fill='x')

        # Requirements status
        self.req_label = ttk.Label(top, text='Checking requirements...')
        self.req_label.pack(side='left')

        btn_check = ttk.Button(top, text='Re-check', command=self.check_requirements)
        btn_check.pack(side='right')

        # Args entry (hidden by default)
        args_frame = ttk.LabelFrame(frm, text='OBBroadcast launch args')
        # Do not pack the args frame so it's hidden by default; keep reference
        self.args_frame = args_frame
        self.args_var = tk.StringVar(value=DEFAULT_OPENOB_ARGS)
        self.args_var.trace_add('write', lambda *_: self._on_args_change())
        self._update_link_details_from_args()
        # Entry + Settings button
        args_row = ttk.Frame(args_frame)
        args_row.pack(fill='x', padx=6, pady=6)
        args_entry = ttk.Entry(args_row, textvariable=self.args_var)
        args_entry.pack(side='left', fill='x', expand=True)
        # Settings button with gear icon (fallback to text if image unavailable)
        try:
            gear_path = REPO_ROOT / 'ui' / 'images' / 'gear.jpg'
            if gear_path.exists():
                self._gear_img = tk.PhotoImage(file=str(gear_path))
                btn_settings = ttk.Button(args_row, image=self._gear_img, command=self._open_settings_dialog)
            else:
                btn_settings = ttk.Button(args_row, text='Settings ⚙', command=self._open_settings_dialog)
        except Exception:
            btn_settings = ttk.Button(args_row, text='Settings ⚙', command=self._open_settings_dialog)
        btn_settings.pack(side='right', padx=(6, 0))

        # Controls
        ctl = ttk.Frame(frm)
        ctl.pack(fill='x', pady=6)

        self.redis_status = tk.StringVar(value='Redis: unknown')
        self.openob_status = tk.StringVar(value='OBBroadcast: stopped')

        # Status indicators: a small colored circle and the textual status
        status_frame = ttk.Frame(ctl)
        status_frame.pack(side='left', padx=6)

        # Redis indicator
        self.redis_canvas = tk.Canvas(status_frame, width=16, height=16, highlightthickness=0)
        self.redis_canvas.create_oval(2, 2, 14, 14, fill='grey', outline='black', tags='dot')
        self.redis_canvas.pack(side='left')
        ttk.Label(status_frame, textvariable=self.redis_status).pack(side='left', padx=(4, 12))

        # OpenOB indicator
        self.openob_canvas = tk.Canvas(status_frame, width=16, height=16, highlightthickness=0)
        self.openob_canvas.create_oval(2, 2, 14, 14, fill='grey', outline='black', tags='dot')
        self.openob_canvas.pack(side='left')
        ttk.Label(status_frame, textvariable=self.openob_status).pack(side='left', padx=(4, 6))

        btn_start_all = ttk.Button(ctl, text='Start All', command=self.start_all)
        btn_start_all.pack(side='right', padx=4)
        btn_stop_all = ttk.Button(ctl, text='Stop All', command=self.stop_all)
        btn_stop_all.pack(side='right', padx=4)
        # Toggle logs button (logs hidden by default)
        self._logs_visible = False
        self.btn_toggle_logs = ttk.Button(ctl, text='Show Logs', command=self._toggle_logs)
        self.btn_toggle_logs.pack(side='right', padx=4)

        # Visible Settings button so users can open settings even if args_frame is hidden
        try:
            gear_path = REPO_ROOT / 'ui' / 'images' / 'gear.jpg'
            if gear_path.exists():
                # keep reference to avoid GC
                self._gear_img = tk.PhotoImage(file=str(gear_path))
                btn_settings_visible = ttk.Button(ctl, image=self._gear_img, command=self._open_settings_dialog)
            else:
                btn_settings_visible = ttk.Button(ctl, text='Settings ⚙', command=self._open_settings_dialog)
        except Exception:
            btn_settings_visible = ttk.Button(ctl, text='Settings ⚙', command=self._open_settings_dialog)
        btn_settings_visible.pack(side='right', padx=4)

        subctl = ttk.Frame(frm)
        subctl.pack(fill='x')
        ttk.Button(subctl, text='Start Redis', command=self.start_redis).pack(side='left', padx=4, pady=4)
        ttk.Button(subctl, text='Stop Redis', command=self.stop_redis).pack(side='left', padx=4)
        ttk.Button(subctl, text='Start OBBroadcast', command=self.start_openob).pack(side='left', padx=4)
        ttk.Button(subctl, text='Stop OBBroadcast', command=self.stop_openob).pack(side='left', padx=4)
        ttk.Checkbutton(subctl, text='Auto iniciar OBBroadcast al abrir', variable=self.auto_start_var).pack(side='left', padx=8)

        # VU Meter area (two stacked meters)
        vu_frame = ttk.LabelFrame(frm, text='Audio Levels')
        vu_frame.pack(fill='x', pady=(6, 0))
        self._vu_max_width = 360
        (self.local_vu_canvas,
         self._local_left_rect,
         self._local_right_rect) = self._create_vu_section(vu_frame, 'Audio Input (Local)')
        (self.remote_vu_canvas,
         self._remote_left_rect,
         self._remote_right_rect) = self._create_vu_section(vu_frame, 'Audio Output (Receiver)')

        # Log area (hidden by default) — use self.log_frame so toggle can show/hide
        self.log_frame = ttk.LabelFrame(frm, text='Logs')
        # do not pack now; will be packed when user requests
        self.log_widget = scrolledtext.ScrolledText(self.log_frame, state='disabled', wrap='none')
        self.log_widget.pack(fill='both', expand=True, padx=4, pady=4)

    def append_log(self, text):
        self.log_widget.configure(state='normal')
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

    def _create_vu_section(self, parent, title):
        section = ttk.Frame(parent)
        section.pack(fill='x', padx=6, pady=4)
        ttk.Label(section, text=title).pack(anchor='w')
        canvas = tk.Canvas(section, height=32)
        canvas.pack(fill='x', pady=2)
        canvas.create_text(6, 10, anchor='w', text='L', font=('TkDefaultFont', 9))
        canvas.create_text(6, 24, anchor='w', text='R', font=('TkDefaultFont', 9))
        left_rect = canvas.create_rectangle(24, 6, 24, 14, fill='grey', outline='black')
        right_rect = canvas.create_rectangle(24, 18, 24, 26, fill='grey', outline='black')
        return canvas, left_rect, right_rect

    def _update_indicators(self, redis_running: bool, openob_running: bool):
        """Update the canvas indicators: green (running) or red (stopped)."""
        try:
            r_color = 'green' if redis_running else 'red'
            o_color = 'green' if openob_running else 'red'
            if hasattr(self, 'redis_canvas'):
                try:
                    self.redis_canvas.itemconfig('dot', fill=r_color)
                except Exception:
                    pass
            if hasattr(self, 'openob_canvas'):
                try:
                    self.openob_canvas.itemconfig('dot', fill=o_color)
                except Exception:
                    pass
        except Exception:
            pass

    def _set_vu_canvas(self, canvas, left_rect, right_rect, left_val, right_val):
        """Render VU bars on the provided canvas using shared mapping logic."""
        try:
            lv_raw = float(left_val)
            rv_raw = float(right_val)

            if lv_raw < 0 or rv_raw < 0:
                min_db = -65.0
                lv = max(min_db, min(0.0, lv_raw))
                rv = max(min_db, min(0.0, rv_raw))
                lam = (lv - min_db) / (0.0 - min_db)
                ram = (rv - min_db) / (0.0 - min_db)
            else:
                lv = max(0.0, min(124.0, lv_raw))
                rv = max(0.0, min(124.0, rv_raw))
                lam = 1.0 - (lv / 124.0)
                ram = 1.0 - (rv / 124.0)

            lam = max(0.0, min(1.0, lam))
            ram = max(0.0, min(1.0, ram))

            canvas_w = max(50, canvas.winfo_width() or self._vu_max_width)
            max_w = canvas_w - 40
            lpx = int(24 + lam * max_w)
            rpx = int(24 + ram * max_w)

            def color_for(a):
                if a >= 0.75:
                    return '#33cc33'
                if a >= 0.4:
                    return '#ebd02b'
                return '#e03b3b'

            lcol = color_for(lam)
            rcol = color_for(ram)

            canvas.coords(left_rect, 24, 6, lpx, 14)
            canvas.itemconfig(left_rect, fill=lcol)
            canvas.coords(right_rect, 24, 18, rpx, 26)
            canvas.itemconfig(right_rect, fill=rcol)
        except Exception:
            pass

    def _apply_vu_values(self, target, left, right):
        if target == 'local':
            canvas = getattr(self, 'local_vu_canvas', None)
            lrect = getattr(self, '_local_left_rect', None)
            rrect = getattr(self, '_local_right_rect', None)
        else:
            canvas = getattr(self, 'remote_vu_canvas', None)
            lrect = getattr(self, '_remote_left_rect', None)
            rrect = getattr(self, '_remote_right_rect', None)
        if canvas and lrect and rrect:
            self._set_vu_canvas(canvas, lrect, rrect, left, right)

    def _set_vu_silence(self, target):
        self._apply_vu_values(target, -65.0, -65.0)

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
        """Show or hide the logs panel and update button text."""
        try:
            if getattr(self, '_logs_visible', False):
                try:
                    self.log_frame.pack_forget()
                except Exception:
                    pass
                self._logs_visible = False
                try:
                    self.btn_toggle_logs.config(text='Show Logs')
                except Exception:
                    pass
            else:
                try:
                    # pack in same place as originally intended
                    self.log_frame.pack(fill='both', expand=True, pady=6)
                except Exception:
                    pass
                self._logs_visible = True
                try:
                    self.btn_toggle_logs.config(text='Hide Logs')
                except Exception:
                    pass
        except Exception:
            pass

        # Adjust main window size to fit new content without moving window
        try:
            self.update_idletasks()
            # Keep current width, adjust to requested height
            cur_x = self.winfo_x()
            cur_y = self.winfo_y()
            cur_w = self.winfo_width() or 900
            req_h = self.winfo_reqheight() or 600
            # Avoid making the window smaller than a reasonable minimum
            min_h = 200
            new_h = max(min_h, req_h)
            try:
                self.geometry(f'{cur_w}x{new_h}+{cur_x}+{cur_y}')
            except Exception:
                # fallback: set only size without position
                try:
                    self.geometry(f'{cur_w}x{new_h}')
                except Exception:
                    pass
        except Exception:
            pass

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
        link = self.link_name
        if not link:
            self._set_vu_silence(target)
            self._record_vu_status(target, 'no-link', 'Link name missing in args')
            return
        key = f'openob:{link}:vu:{role}'
        try:
            data = client.hgetall(key)
        except Exception:
            data = {}
        if not data:
            self._set_vu_silence(target)
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
            self._set_vu_silence(target)
            self._record_vu_status(target, 'invalid-data', f'Datos sin valores numéricos en {key}')
            return
        updated = data.get('updated_ts') or data.get('ts')
        if updated is not None:
            try:
                updated = float(updated)
            except Exception:
                updated = None
            if updated is not None and (time.time() - updated) > 5:
                self._set_vu_silence(target)
                self._record_vu_status(target, 'stale', f'Datos viejos ({time.time()-updated:.1f}s) en {key}')
                return
        self._apply_vu_values(target, left_val, right_val)
        self._record_vu_status(target, 'ok', None)

    def update_vu_loop(self):
        try:
            self._update_link_details_from_args()
            client = self._get_redis_client()
            if client and self.link_name:
                self._fetch_and_apply_vu(client, 'tx', 'local')
                self._fetch_and_apply_vu(client, 'rx', 'remote')
            else:
                reason = 'Sin Redis' if not client else 'Link no definido'
                self._set_vu_silence('local')
                self._set_vu_silence('remote')
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
                img = Image.open(str(img_path)).convert('RGBA')
                return img
        except Exception:
            pass
        # fallback: create a simple blank image
        try:
            img = Image.new('RGBA', (64, 64), (50, 50, 50, 255))
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
