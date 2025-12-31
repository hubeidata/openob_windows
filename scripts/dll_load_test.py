import ctypes
from pathlib import Path
base=Path(r'C:/Users/vamanuel/Documents/openob_windows/openob-embedded-installer/packaging/openob_runtime/gvsbuild/bin')
for name in ['pcre2-8-0.dll','intl.dll','glib-2.0-0.dll','girepository-1.0-1.dll']:
    p=base/name
    try:
        ctypes.CDLL(str(p))
        print('loaded',name)
    except Exception as e:
        print('failed to load',name,repr(e))
