import re, sys, os
pyd=r'C:\Users\vamanuel\AppData\Local\Programs\OpenOB\python\Lib\site-packages\gi\_gi.cp314-win_amd64.pyd'
if not os.path.exists(pyd):
    print('pyd not found',pyd); sys.exit(1)
b=open(pyd,'rb').read()
ss=set(re.findall(rb'([A-Za-z0-9_\-\.]{3,}\.dll)', b, flags=re.IGNORECASE))
names=sorted({s.decode('ascii',errors='ignore').lower() for s in ss})
print('Found candidate imports:', len(names))
print('\n'.join(names))
# check presence on PATH
path_dirs = os.environ.get('PATH','').split(os.pathsep)
missing=[]
for n in names:
    found=False
    for d in path_dirs:
        if os.path.exists(os.path.join(d,n)):
            found=True; break
    if not found: missing.append(n)
print('\nMissing from PATH:', len(missing))
print('\n'.join(missing[:200]))
