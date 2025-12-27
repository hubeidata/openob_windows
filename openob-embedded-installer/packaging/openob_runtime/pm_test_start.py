from ui.services.process_service import OpenOBProcessManager
from pathlib import Path
import time
inst = Path(r'C:\Users\vamanuel\AppData\Local\Programs\OpenOB')
pm = OpenOBProcessManager(venv_python=inst/ 'python' / 'python.exe', openob_script=inst / 'python' / 'Scripts' / 'openob.exe', working_dir=inst)
res = pm.can_start()
print('can_start', res)
pr = pm.start("127.0.0.1 emetteur transmission tx 127.0.0.1 -a test")
print('start returned', pr)
# let it run a few seconds
time.sleep(3)
if pm.is_running:
    print('process is running, stopping...')
    pm.stop()
else:
    print('process not running')
