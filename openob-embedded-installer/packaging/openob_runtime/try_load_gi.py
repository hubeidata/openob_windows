import ctypes, os
p = r'C:\Users\vamanuel\AppData\Local\Programs\OpenOB\python\Lib\site-packages\gi\_gi.cp314-win_amd64.pyd'
print('exists', os.path.exists(p))
LoadLibraryEx = ctypes.windll.kernel32.LoadLibraryExW
LOAD_WITH_ALTERED_SEARCH_PATH = 0x00000008
h = LoadLibraryEx(p, None, LOAD_WITH_ALTERED_SEARCH_PATH)
if h:
    print('LoadLibraryEx succeeded, handle', h)
else:
    err = ctypes.windll.kernel32.GetLastError()
    import ctypes.wintypes
    buf = ctypes.create_unicode_buffer(2048)
    ctypes.windll.kernel32.FormatMessageW(0x00001000, None, err, 0, buf, len(buf), None)
    print('LoadLibraryEx failed, err', err, buf.value)
