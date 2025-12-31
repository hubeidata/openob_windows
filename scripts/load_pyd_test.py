import ctypes
from pathlib import Path
import os
p=Path(r'C:/Users/vamanuel/Documents/openob_windows/openob-embedded-installer/packaging/openob_runtime/python/Lib/site-packages/gi/_gi.cp314-win_amd64.pyd')
# ensure PATH includes gvsbuild and system gst
os.environ['PATH'] = r'C:\Users\vamanuel\Documents\openob_windows\openob-embedded-installer\packaging\openob_runtime\gvsbuild\bin;C:\Program Files\gstreamer\1.0\msvc_x86_64\bin;' + os.environ.get('PATH','')
try:
    ctypes.CDLL(str(p))
    print('ctypes loaded _gi pyd OK')
except Exception as e:
    print('ctypes load failed:', e)
    import traceback; traceback.print_exc()
