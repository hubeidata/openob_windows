import os, sys, glob, traceback
out=[]
try:
    out.append('TIME: %s' % (__import__('datetime').datetime.utcnow().isoformat()))
    out.append('PATH: %s' % os.environ.get('PATH',''))
    out.append('GI_TYPELIB_PATH: %s' % os.environ.get('GI_TYPELIB_PATH',''))
    out.append('GstBin: %s' % os.environ.get('GstBin',''))
    out.append('sys.executable: %s' % sys.executable)
    out.append('sys.path: %s' % repr(sys.path))
    runtime_root = os.path.abspath(os.path.join(os.path.dirname(sys.executable),'..'))
    out.append('runtime_root: %s' % runtime_root)
    gvs_bin = os.path.join(runtime_root,'gvsbuild','bin')
    out.append('gvsbuild_bin_exists: %s' % os.path.isdir(gvs_bin))
    if os.path.isdir(gvs_bin):
        out.append('gvsbuild_bin_files: %s' % ','.join(sorted(os.listdir(gvs_bin))[:200]))
    gstbin = os.environ.get('GstBin','')
    out.append('gstbin_exists: %s' % os.path.isdir(gstbin))
    if gstbin and os.path.isdir(gstbin):
        out.append('gstbin_files: %s' % ','.join(sorted(os.listdir(gstbin))[:200]))
    pyd_candidates=[]
    for p in sys.path:
        try:
            pfull = os.path.join(p,'gi')
            if os.path.isdir(pfull):
                pyd_candidates += glob.glob(os.path.join(pfull,'_gi.*.pyd'))
        except Exception:
            pass
    out.append('_gi_candidates: %s' % ','.join(pyd_candidates))
    # attempt ctypes load
    try:
        if pyd_candidates:
            import ctypes
            libpath=pyd_candidates[0]
            out.append('attempting ctypes.WinDLL load: %s' % libpath)
            try:
                ctypes.WinDLL(libpath)
                out.append('ctypes load succeeded')
            except Exception as win_e:
                out.append('ctypes load failed: %s' % repr(win_e))
    except Exception as ex:
        out.append('ctypes test exception: %s' % repr(ex))
except Exception as e:
    out.append('diagnostic exception: %s' % repr(e))
    out.append(traceback.format_exc())

logdir = os.path.join(runtime_root,'logs')
if not os.path.isdir(logdir):
    logdir = os.path.dirname(__file__)
fname = os.path.join(logdir,'gi_load_debug_manual.txt')
with open(fname,'w',encoding='utf-8') as f:
    f.write('\n'.join(out))
print('Wrote diagnostic to', fname)
print('\n'.join(out))