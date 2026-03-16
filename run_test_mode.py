#!/usr/bin/env python3
"""
Test the agent in DRY_RUN mode and capture output for 30 seconds
"""
import subprocess
import os
import sys
import time
import signal

os.chdir('/Users/haseeb.ahmedjaved/Downloads/ai-agents/email-agent')

# Clean database
if os.path.exists('alerts.db'):
    os.remove('alerts.db')

print("🧪 Starting agent in DRY_RUN mode for test...")
print("=" * 80)
print()

# Set environment
env = os.environ.copy()
env['DRY_RUN'] = 'true'

# Start process
proc = subprocess.Popen(
    ['./venv/bin/python', 'agent.py'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    env=env
)

# Read output for 30 seconds
output_lines = []
start_time = time.time()
max_duration = 30

try:
    while time.time() - start_time < max_duration:
        try:
            line = proc.stdout.readline()
            if line:
                output_lines.append(line.rstrip())
                print(line.rstrip())
            else:
                time.sleep(0.1)
        except:
            break
except KeyboardInterrupt:
    print("\n⏹ Stopped by user")

# Terminate process
proc.terminate()
try:
    proc.wait(timeout=5)
except subprocess.TimeoutExpired:
    proc.kill()

print()
print("=" * 80)
print("✅ Test output captured")
print()

# Save to file
with open('test_output.log', 'w') as f:
    f.write('\n'.join(output_lines))

print(f"📋 Full output saved to: test_output.log")
print(f"📊 Total lines: {len(output_lines)}")
