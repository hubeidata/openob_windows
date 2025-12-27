import importlib, traceback, sys, os
try:
    import openob.rtp.tx
    print('openob.rtp.tx imported OK')
except Exception as e:
    traceback.print_exc()
    rt = os.path.abspath(os.path.join(os.path.dirname(sys.executable), '..'))
    df = os.path.join(rt, 'logs', 'gi_load_debug.txt')
    print('expected debug file:', df)
    if os.path.exists(df):
        print('--- file tail ---')
        print('\n'.join(open(df,'r',encoding='utf-8').read().splitlines()[-200:]))
    else:
        print('No debug file found at expected path:', df)
