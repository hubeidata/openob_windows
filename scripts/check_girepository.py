import ctypes
from ctypes import WinError
try:
    ctypes.CDLL('girepository-1.0-1.dll')
    print('girepository DLL loaded')
except Exception as e:
    print('failed to load girepository DLL:', e)
    try:
        import traceback; traceback.print_exc()
    except:
        pass