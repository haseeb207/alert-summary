#!/usr/bin/env python3
"""Comprehensive test of alert parser"""
import os
import sys
import subprocess
import time
import shutil

os.chdir('/Users/haseeb.ahmedjaved/Downloads/ai-agents/email-agent')
sys.path.insert(0, '.')

# Remove old database
if os.path.exists('alerts.db'):
    os.remove('alerts.db')

# Restore test files
watch_dir = '/Users/haseeb.ahmedjaved/Library/CloudStorage/OneDrive-VisionetSystemsInc/Work/datadog-alert-emails'
archive_path = os.path.join(watch_dir, 'archive')

restored = 0
if os.path.exists(archive_path):
    files = [f for f in os.listdir(archive_path) if f.endswith('.txt')]
    for f in files:
        src = os.path.join(archive_path, f)
        dst = os.path.join(watch_dir, f)
        if not os.path.exists(dst) and os.path.isfile(src):
            shutil.move(src, dst)
            restored += 1

# Run agent with DRY_RUN
env = os.environ.copy()
env['DRY_RUN'] = 'true'

proc = subprocess.Popen(['./venv/bin/python', 'agent.py'],
                       stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT,
                       text=True,
                       env=env)

lines = []
start = time.time()
while time.time() - start < 35:
    try:
        line = proc.stdout.readline()
        if line:
            lines.append(line.rstrip())
        else:
            time.sleep(0.1)
    except:
        pass

proc.terminate()
proc.wait(timeout=5)

print("\n" + "="*80)
print("FINAL TEST RESULTS")  
print("="*80 + "\n")

show = False
for line in lines:
    if 'Alert Summary' in line or 'P3 -' in line or '**' in line:
        show = True
    if show:
        print(line)
        if 'Trend:' in line:
            print()

print("="*80 + "\n")

