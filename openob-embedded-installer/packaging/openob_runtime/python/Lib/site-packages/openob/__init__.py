# Ensure native GObject/GStreamer DLL paths are registered early to help _gi load on Windows
import os, sys
try:
    runtime_root = os.path.abspath(os.path.join(os.path.dirname(sys.executable), '..'))
    gvs_bin = os.path.join(runtime_root, 'gvsbuild', 'bin')
    if os.path.isdir(gvs_bin):
        try:
            os.add_dll_directory(gvs_bin)
        except Exception:
            pass
    gstbin = os.environ.get('GstBin','')
    if gstbin and os.path.isdir(gstbin):
        try:
            os.add_dll_directory(gstbin)
        except Exception:
            pass
    # Try preloading _gi extension if present
    try:
        import glob, ctypes
        for p in sys.path:
            try:
                pfull = os.path.join(p, 'gi')
                if os.path.isdir(pfull):
                    pyds = glob.glob(os.path.join(pfull, '_gi.*.pyd'))
                    if pyds:
                        for libpath in pyds:
                            try:
                                ctypes.windll.kernel32.LoadLibraryExW(libpath, None, 0x00000008)
                                break
                            except Exception:
                                continue
                        break
            except Exception:
                continue
    except Exception:
        pass
except Exception:
    pass

__all__ = ["logger","link_config","rtp.rx","rtp.tx","node"]
