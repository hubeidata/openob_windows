import os
import sys

print("PATH:", os.environ.get("PATH", ""))
print("GI_TYPELIB_PATH:", os.environ.get("GI_TYPELIB_PATH", ""))
print("Python:", sys.version)
print("Executable:", sys.executable)

try:
    import gi
    print("gi import OK")
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst
    print("Gst version:", Gst.version_string())
except Exception as e:
    import traceback
    print("ERROR during import:")
    traceback.print_exc()
    input("Presiona Enter para salir...")
