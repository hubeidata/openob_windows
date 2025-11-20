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
from pathlib import Path


# Hide PowerShell windows on Windows
creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0


REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_PY = REPO_ROOT / '.venv' / 'Scripts' / 'python.exe'
OPENOB_SCRIPT = REPO_ROOT / '.venv' / 'Scripts' / 'openob'
SCRIPT_START_OPENOB = REPO_ROOT / 'scripts' / 'start_openob.ps1'
GSTREAMER_BIN = Path(r'C:\Program Files\gstreamer\1.0\msvc_x86_64\bin')
GSTREAMER_GIR = Path(r'C:\Program Files\gstreamer\1.0\msvc_x86_64\lib\girepository-1.0')

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

        ttk.Label(ctl, textvariable=self.redis_status).pack(side='left', padx=6)
        ttk.Label(ctl, textvariable=self.openob_status).pack(side='left', padx=6)

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

        # Log area
        log_frame = ttk.LabelFrame(frm, text='Logs')
        log_frame.pack(fill='both', expand=True, pady=6)
        self.log_widget = scrolledtext.ScrolledText(log_frame, state='disabled', wrap='none')
        self.log_widget.pack(fill='both', expand=True, padx=4, pady=4)

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
        try:
            res = subprocess.run([
                'powershell', '-NoProfile', '-Command',
                "(Get-Service -Name Redis -ErrorAction SilentlyContinue).Status -join ''"
            ], capture_output=True, text=True, cwd=str(REPO_ROOT), creationflags=creationflags)
            svc = res.stdout.strip()
            if svc:
                msgs.append(f'Redis service: {svc}')
                self.redis_status.set(f'Redis: {svc.lower()}')
            else:
                msgs.append('Redis service: NOT INSTALLED')
                self.redis_status.set('Redis: not installed')
        except Exception:
            msgs.append('Redis service: UNKNOWN')
            self.redis_status.set('Redis: unknown')

        self.req_label.config(text=' | '.join(msgs))

        # Also update OpenOB status
        openob_running = self.openob_proc and self.openob_proc.poll() is None
        self.openob_status.set('OpenOB: running' if openob_running else 'OpenOB: stopped')

    def start_redis(self):
        # Start the Redis Windows service (requires service to be installed)
        try:
            res = subprocess.run(['powershell', '-NoProfile', '-Command', 'Start-Service -Name Redis'], capture_output=True, text=True, cwd=str(REPO_ROOT), creationflags=creationflags)
            if res.returncode == 0:
                self.append_log('Requested Start-Service Redis\n')
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
        openob_running = self.openob_proc and self.openob_proc.poll() is None
        self.redis_status.set('Redis: running' if redis_running else 'Redis: stopped')
        self.openob_status.set('OpenOB: running' if openob_running else 'OpenOB: stopped')
        # No recursive call to avoid constant loop


def main():
    app = OpenOBGUI()
    app.mainloop()


if __name__ == '__main__':
    main()
