import subprocess, sys, time
p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
with open('tree_pids.txt', 'w') as f:
    f.write(f'{p.pid}\n')
time.sleep(60)
