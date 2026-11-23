"""CI entry point; no registered papers means infrastructure only, never paper PASS."""
import subprocess
import sys
from pathlib import Path

def main(base=None):
    base = Path(base) if base is not None else Path(__file__).resolve().parent
    configs = sorted((base / 'entries').glob('*.json'))
    if not configs:
        print('INFRASTRUCTURE_ONLY: no manuscripts enrolled; no submission approval')
        return 0
    codes = [subprocess.run([sys.executable, str(base / 'publication_gate.py'), str(c)]).returncode
             for c in configs]
    return int(any(codes))

if __name__ == '__main__':
    raise SystemExit(main())
