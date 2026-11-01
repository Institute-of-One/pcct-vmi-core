"""Rebuild all shipped figures, tables, and documents in dependency order.

Use the project interpreter; DOCX_PYTHON selects an interpreter with python-docx.
--strict checks submission readiness as well as structural correctness.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(); p.add_argument('--strict',action='store_true')
    p.add_argument('--no-pdf',action='store_true',help='Draft-only build without Word PDF export')
    args=p.parse_args()
    subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'paper/figures.py')],cwd=ROOT,check=True)
    subprocess.run([os.environ.get('DOCX_PYTHON',sys.executable),'-X','utf8','-B',str(ROOT/'submission/jxst/build_submission_docs.py')],cwd=ROOT,check=True)
    if not args.no_pdf:
        if os.name!='nt': raise RuntimeError('PDF export requires Windows Word; use --no-pdf for a draft-only build')
        subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'submission/jxst/render_word.ps1')],cwd=ROOT,check=True)
    output=ROOT/'submission/jxst/output'
    artifacts=list(output.glob('*.docx'))+list(output.glob('*.pdf'))+list(output.glob('*.csv'))+[output/'manuscript.txt']
    (output/'delivery_manifest.json').write_text(json.dumps({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts},indent=2))
    command=[sys.executable,'-X','utf8','-B',str(ROOT/'submission/jxst/check_template_conformance.py')]
    if args.strict: command.append('--strict')
    subprocess.run(command,cwd=ROOT,check=True)

if __name__=='__main__': main()
