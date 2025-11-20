#!/usr/bin/env python3
"""
Simple Tkinter GUI to start/stop Redis and OpenOB, show status and logs, and edit launch args.

Usage: run from repo root (or double-click):
    python ui\main.py

Notes:
 - Uses the repository layout created during the session:
     .venv\Scripts\python.exe
     .venv\Scripts\openob
     redis-server\redis-server.exe
 - Checks for Python modules `redis` and `gi` (GStreamer) and presence of GStreamer bins.
 - Default OpenOB args: -v 127.0.0.1 emetteur transmission tx 192.168.8.17 -e pcm -r 48000 -j 60 -a test
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
from pathlib import Path


# Hide PowerShell windows on Windows
creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0


REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_PY = REPO_ROOT / '.venv' / 'Scripts' / 'python.exe'
OPENOB_SCRIPT = REPO_ROOT / '.venv' / 'Scripts' / 'openob'
SCRIPT_START_OPENOB = REPO_ROOT / 'scripts' / 'start_openob.ps1'
GSTREAMER_BIN = Path(r'C:\Program Files\gstreamer\1.0\msvc_x86_64\bin')
GSTREAMER_GIR = Path(r'C:\Program Files\gstreamer\1.0\msvc_x86_64\lib\girepository-1.0')

DEFAULT_OPENOB_ARGS = '-v 127.0.0.1 emetteur transmission tx 192.168.1.17 -e pcm -r 48000 -j 60 -a auto'

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
        self.title('OpenOB Controller')
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
        # tray icon state
        self.tray_icon = None
        self.tray_thread = None

        # Handle window close
        self.protocol('WM_DELETE_WINDOW', self.on_close)

        self.create_widgets()
        self.check_requirements()
        self.update_status_loop()

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

        # Args entry
        args_frame = ttk.LabelFrame(frm, text='OpenOB launch args')
        args_frame.pack(fill='x', pady=6)
        self.args_var = tk.StringVar(value=DEFAULT_OPENOB_ARGS)
        args_entry = ttk.Entry(args_frame, textvariable=self.args_var)
        args_entry.pack(fill='x', padx=6, pady=6)

        # Controls
        ctl = ttk.Frame(frm)
        ctl.pack(fill='x', pady=6)

        self.redis_status = tk.StringVar(value='Redis: unknown')
        self.openob_status = tk.StringVar(value='OpenOB: stopped')

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

        subctl = ttk.Frame(frm)
        subctl.pack(fill='x')
        ttk.Button(subctl, text='Start Redis', command=self.start_redis).pack(side='left', padx=4, pady=4)
        ttk.Button(subctl, text='Stop Redis', command=self.stop_redis).pack(side='left', padx=4)
        ttk.Button(subctl, text='Start OpenOB', command=self.start_openob).pack(side='left', padx=4)
        ttk.Button(subctl, text='Stop OpenOB', command=self.stop_openob).pack(side='left', padx=4)

        # Autostart checkbox (default enabled)
        self.autostart_var = tk.BooleanVar(value=True)
        autostart_frame = ttk.Frame(frm)
        autostart_frame.pack(fill='x', pady=6)
        autostart_checkbox = ttk.Checkbutton(autostart_frame, text='Autostart OpenOB', variable=self.autostart_var)
        autostart_checkbox.pack(side='left', padx=4)

        # VU Meter area (stereo: Left / Right)
        vu_frame = ttk.LabelFrame(frm, text='VU Meter')
        vu_frame.pack(fill='x', pady=(6, 0))
        self.vu_canvas = tk.Canvas(vu_frame, height=36)
        self.vu_canvas.pack(fill='x', padx=6, pady=6)
        # parameters for drawing
        self._vu_max_width = 300
        self._vu_left_rect = self.vu_canvas.create_rectangle(6, 6, 6, 14, fill='green', outline='black')
        self._vu_right_rect = self.vu_canvas.create_rectangle(6, 20, 6, 28, fill='green', outline='black')
        # labels
        self.vu_canvas.create_text(0, 10, anchor='w', text='L', font=('TkDefaultFont', 9))
        self.vu_canvas.create_text(0, 24, anchor='w', text='R', font=('TkDefaultFont', 9))

        # Log area
        log_frame = ttk.LabelFrame(frm, text='Logs')
        log_frame.pack(fill='both', expand=True, pady=6)
        self.log_widget = scrolledtext.ScrolledText(log_frame, state='disabled', wrap='none')
        self.log_widget.pack(fill='both', expand=True, padx=4, pady=4)

        # Load saved autostart state (defaults to enabled if no saved file)
        self.autostart_var.set(self.load_autostart_state())

        # Bind save_autostart_state to checkbox toggle
        try:
            self.autostart_var.trace_add('write', lambda *args: self.save_autostart_state())
        except Exception:
            pass

        # If autostart enabled, start OpenOB automatically
        if self.autostart_var.get():
            self.after(100, self.start_openob)

    def append_log(self, text):
        self.log_widget.configure(state='normal')
        self.log_widget.insert('end', text)
        self.log_widget.see('end')
        self.log_widget.configure(state='disabled')

    def check_requirements(self):
        msgs = []
        # python module redis
        try:
            import redis as _
            msgs.append('redis: OK')
        except Exception:
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
        self.openob_status.set('OpenOB: running' if openob_running else 'OpenOB: stopped')
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
            messagebox.showinfo('Info', 'OpenOB already running')
            return
        if not VENV_PY.exists():
            messagebox.showerror('Error', f'Venv python not found at {VENV_PY}')
            return

        args = self.args_var.get().strip()
        if not args:
            messagebox.showerror('Error', 'Empty OpenOB args')
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
                if not messagebox.askyesno('Warning', f'OpenOB entry script not found at {OPENOB_SCRIPT}. Use helper script instead?'):
                    return
            else:
                messagebox.showerror('Error', f'OpenOB entry script not found at {OPENOB_SCRIPT} and helper missing at {SCRIPT_START_OPENOB}')
                return

        # Build direct command: <venv_python> <openob_script> <args...>
        try:
            split_args = shlex.split(args)
        except Exception:
            split_args = args.split()

        cmd = [str(VENV_PY), str(OPENOB_SCRIPT)] + split_args
        try:
            # Start the real OpenOB process and stream output into the UI
            self.openob_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(REPO_ROOT), creationflags=creationflags)
            threading.Thread(target=self._stream_process_output, args=(self.openob_proc, 'OPENOB'), daemon=True).start()
            self.append_log('Started OpenOB (direct venv python)\n')
            self.openob_status.set('OpenOB: running')
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
                        threading.Thread(target=self._stream_process_output, args=(self.openob_proc, 'OPENOB'), daemon=True).start()
                        self.append_log('Started OpenOB (via start_openob.ps1 fallback)\n')
                        self.openob_status.set('OpenOB: running')
                        try:
                            self._update_indicators(self.redis_running, True)
                        except Exception:
                            pass
                        return
                    except Exception as e2:
                        messagebox.showerror('Error', f'Fallback also failed: {e2}')
                        return
            messagebox.showerror('Error', f'Failed to start OpenOB: {e}')

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
                # If this is OpenOB output, try to parse numeric level values (0..124)
                if tag == 'OPENOB':
                    try:
                        # find numbers (allow optional negative sign and decimals)
                        found = re.findall(r"(-?\d{1,3}(?:\.\d+)?)", line)
                        vals = []
                        for s in found:
                            try:
                                v = float(s)
                                # keep plausible audio numbers
                                if -200.0 <= v <= 1000.0:
                                    vals.append(v)
                            except Exception:
                                continue
                        if vals:
                            # interpret as stereo if two or more numbers, else use one value for both
                            if len(vals) >= 2:
                                lval, rval = vals[-2], vals[-1]
                            else:
                                lval = rval = vals[-1]
                            # schedule UI update (pass floats)
                            try:
                                self.after(0, lambda L=lval, R=rval: self._set_vu(L, R))
                            except Exception:
                                pass
                    except Exception:
                        pass
        except Exception:
            pass

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

    def _set_vu(self, left_val, right_val):
        """Render VU bars from raw numeric levels.

        The function accepts two numeric inputs which may be:
        - dB-like negatives (e.g. -65 .. 0) where -65 -> silence and 0 -> max
        - legacy positive scale (0 .. 124) where 0 -> max and 124 -> silence

        The function auto-detects negative values and maps accordingly.
        """
        try:
            # convert to floats
            lv_raw = float(left_val)
            rv_raw = float(right_val)

            # Detect dB-style negatives: if either is negative, map from [-65..0]
            if lv_raw < 0 or rv_raw < 0:
                # dB scale mapping: clamp to [-65, 0]
                min_db = -65.0
                lv = max(min_db, min(0.0, lv_raw))
                rv = max(min_db, min(0.0, rv_raw))
                lam = (lv - min_db) / (0.0 - min_db)
                ram = (rv - min_db) / (0.0 - min_db)
            else:
                # legacy mapping 0..124 where 0 = loud, 124 = silent
                lv = max(0.0, min(124.0, lv_raw))
                rv = max(0.0, min(124.0, rv_raw))
                lam = 1.0 - (lv / 124.0)
                ram = 1.0 - (rv / 124.0)

            # clamp amplitudes 0..1
            lam = max(0.0, min(1.0, lam))
            ram = max(0.0, min(1.0, ram))

            # pixel width (leave padding)
            canvas_w = max(50, self.vu_canvas.winfo_width() or self._vu_max_width)
            max_w = canvas_w - 40
            lpx = int(24 + lam * max_w)
            rpx = int(24 + ram * max_w)

            # decide colors by amplitude
            def color_for(a):
                if a >= 0.75:
                    return '#33cc33'  # green
                if a >= 0.4:
                    return '#ebd02b'  # yellow
                return '#e03b3b'     # red

            lcol = color_for(lam)
            rcol = color_for(ram)

            # update left rect (y 6..14)
            try:
                self.vu_canvas.coords(self._vu_left_rect, 24, 6, lpx, 14)
                self.vu_canvas.itemconfig(self._vu_left_rect, fill=lcol)
            except Exception:
                pass
            # update right rect (y 20..28)
            try:
                self.vu_canvas.coords(self._vu_right_rect, 24, 20, rpx, 28)
                self.vu_canvas.itemconfig(self._vu_right_rect, fill=rcol)
            except Exception:
                pass
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
        ttk.Label(frm, text='OpenOB está en ejecución. ¿Qué desea hacer al cerrar la interfaz?').pack(padx=6, pady=(0,10))

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
        ttk.Button(btns, text='Detener OpenOB antes de cerrar', command=do_stop).pack(side='left', padx=4)
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
            pystray.MenuItem('Detener OpenOB', lambda _: self.after(0, self.stop_openob)),
            pystray.MenuItem('Salir', lambda _: self.after(0, self._tray_exit))
        )

        self.tray_icon = pystray.Icon('openob', image, 'OpenOB', menu)

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

    def load_autostart_state(self):
        """Load the saved autostart state from a file."""
        try:
            state_file = REPO_ROOT / 'ui' / 'autostart_state.txt'
            if state_file.exists():
                with open(state_file, 'r') as f:
                    return f.read().strip().lower() == 'true'
            # default: enabled when no saved state exists
            return True
        except Exception as e:
            self.append_log(f'Error loading autostart state: {e}\n')
        return True

    def save_autostart_state(self):
        """Save the current autostart state to a file."""
        try:
            state_file = REPO_ROOT / 'ui' / 'autostart_state.txt'
            with open(state_file, 'w') as f:
                f.write('true' if self.autostart_var.get() else 'false')
        except Exception as e:
            self.append_log(f'Error saving autostart state: {e}\n')
        


def main():
    app = OpenOBGUI()
    app.mainloop()


if __name__ == '__main__':
    main()
