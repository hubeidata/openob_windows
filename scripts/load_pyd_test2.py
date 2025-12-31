import ctypes
from pathlib import Path
import os
p=Path(r'C:/Users/vamanuel/Documents/openob_windows/openob-embedded-installer/packaging/openob_runtime/python/Lib/site-packages/gi/_gi.cp314-win_amd64.pyd')
with os.add_dll_directory(r'C:\Users\vamanuel\Documents\openob_windows\openob-embedded-installer\packaging\openob_runtime\gvsbuild\bin'):
    with os.add_dll_directory(r'C:\Program Files\gstreamer\1.0\msvc_x86_64\bin'):
        try:
            ctypes.CDLL(str(p))
            print('ctypes loaded _gi pyd OK (via add_dll_directory)')
        except Exception as e:
            print('ctypes load failed (add_dll_directory):', e)
            import traceback; traceback.print_exc()
