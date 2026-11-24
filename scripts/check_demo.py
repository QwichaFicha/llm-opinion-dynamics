"""Optional Chrome + Node 22+ check of the network-free replay."""
import argparse
from pathlib import Path
import shutil
import subprocess

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--chrome', default=r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    parser.add_argument('--node', default=shutil.which('node'))
    parser.add_argument('--discussion',action='store_true',help='Check the v2 changing-partner replay')
    args = parser.parse_args()
    if not args.node:
        raise SystemExit('Install Node 22+ or pass --node')
    if not Path(args.chrome).is_file():
        raise SystemExit('Pass an installed Chrome/Chromium path with --chrome')
    raise SystemExit(subprocess.call([args.node, str(Path(__file__).with_suffix('.mjs')), args.chrome]+(['discussion'] if args.discussion else [])))
