# OpenOB GUI

This small GUI lets you start/stop Redis and OpenOB, view logs, and edit the OpenOB launch arguments.

How to run

From the repository root (where `.venv` and `redis-server` live):

```powershell
# activate the venv if you want (optional)
# .\.venv\Scripts\Activate.ps1
python ui\main.py
```

Notes
- The GUI is implemented with Tkinter (bundled with Python).
- It expects the repository layout created during the session: `.venv\Scripts\python.exe`, `.venv\Scripts\openob`, and `redis-server\redis-server.exe`.
- Default OpenOB args are: `-v 127.0.0.1 emetteur transmission tx 192.168.8.17 -e pcm -r 48000 -j 60 -a test`.
