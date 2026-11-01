"""Render final Word-exported PDFs and report pages changed since the last review."""
import hashlib
import json
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'submission/jxst/output'
POPPLER=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe'

def main():
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('final-*.png')}
    for pdf,prefix in [('manuscript','final-page'),('title_page','final-title')]:
        subprocess.run([str(POPPLER),'-r','150','-png',str(OUT/f'{pdf}.pdf'),str(OUT/prefix)],check=True)
    after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('final-*.png')}
    changed=[n for n,h in after.items() if before.get(n)!=h]
    print('Changed pages:',changed)
    (OUT/'render_changes.json').write_text(json.dumps({'changed':changed,'before':before,'after':after},indent=2))

if __name__=='__main__':main()
