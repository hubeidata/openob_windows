import gi, traceback
try:
    print("gi file:", getattr(gi, "__file__", None))
    gi.require_version("Gst","1.0")
    from gi.repository import Gst
    try:
        Gst.init(None)
    except Exception as e:
        print("Gst.init() warning:", e)
    print("Gst:", Gst.version_string())
except Exception as e:
    print("ERROR:", e)
    traceback.print_exc()