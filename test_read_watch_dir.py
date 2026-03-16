#!/usr/bin/env python3
"""
Test whether the current process can list and read files in the watch directory.
Run with: python test_read_watch_dir.py
Use the same Terminal/app you use for the agent to compare permissions.
"""

import os
import sys
from pathlib import Path

# Load .env from project root
PROJECT_DIR = Path(__file__).resolve().parent
os.chdir(PROJECT_DIR)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

WATCH_DIR = os.path.expanduser(os.getenv('WATCH_DIR', ''))


def main():
    print("=" * 60)
    print("Test: Can this process read the watch directory?")
    print("=" * 60)
    print(f"WATCH_DIR: {WATCH_DIR or '(not set)'}")
    print()

    if not WATCH_DIR:
        print("FAIL: WATCH_DIR is not set in .env")
        return 1

    watch_path = Path(WATCH_DIR)

    # 1. Path exists?
    print("1. Checking if path exists...")
    try:
        if not watch_path.exists():
            print("   FAIL: Path does not exist.")
            return 1
        print("   OK: Path exists.")
    except OSError as e:
        print(f"   FAIL: {e}")
        return 1

    # 2. Is it a directory?
    print("2. Checking if it's a directory...")
    try:
        if not watch_path.is_dir():
            print("   FAIL: Not a directory.")
            return 1
        print("   OK: Is a directory.")
    except OSError as e:
        print(f"   FAIL: {e}")
        return 1

    # 3. List directory (this often raises "Operation not permitted" without Full Disk Access)
    print("3. Listing directory contents...")
    try:
        items = list(watch_path.iterdir())
        print(f"   OK: Found {len(items)} item(s).")
    except OSError as e:
        print(f"   FAIL: Cannot list directory — {e}")
        print("   → Grant Full Disk Access to this app (Terminal/Cursor) in System Settings.")
        return 1

    # 4. Find .txt files
    txt_files = [p for p in items if p.is_file() and p.suffix.lower() == '.txt']
    print(f"4. .txt files in root: {len(txt_files)}")
    if not txt_files:
        print("   (No .txt files to try reading.)")
        print()
        print("Overall: Can list directory, but no .txt files in root.")
        return 0

    # 5. Try to read first few .txt files
    to_try = txt_files[:3]
    print(f"5. Reading up to {len(to_try)} .txt file(s)...")
    read_ok = 0
    for p in to_try:
        try:
            with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            print(f"   OK: Read {len(content)} chars from {p.name}")
            read_ok += 1
        except OSError as e:
            print(f"   FAIL: {p.name} — {e}")
        except Exception as e:
            print(f"   FAIL: {p.name} — {e}")

    print()
    if read_ok == len(to_try):
        print("Overall: SUCCESS — can list and read files. Agent should be able to process alerts.")
    else:
        print(f"Overall: Can list directory but failed to read some files ({read_ok}/{len(to_try)} read).")
        print("         Grant Full Disk Access to this app and try again.")
    return 0 if read_ok > 0 else 1


if __name__ == '__main__':
    sys.exit(main())
