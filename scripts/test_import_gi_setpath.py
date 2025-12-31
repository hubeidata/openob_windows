import os,traceback
os.environ['PATH'] = r'C:\Users\vamanuel\Documents\openob_windows\openob-embedded-installer\packaging\openob_runtime\gvsbuild\bin;' + os.environ.get('PATH','')
# add GI_TYPELIB_PATH to find .typelib files installed with system GStreamer
os.environ['GI_TYPELIB_PATH'] = r'C:\Program Files\gstreamer\1.0\msvc_x86_64\lib\girepository-1.0'
try:
    import gi
    print('import gi OK')
    import gi.repository.GLib as GLib
    print('imported GLib OK')
except Exception as e:
    print('Import failed:', e)
    traceback.print_exc()
