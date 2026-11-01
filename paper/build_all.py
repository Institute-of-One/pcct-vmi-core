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

def pinned_versions(interpreter,only=None):
    """Refuse to build figures on an interpreter the pins do not describe.

    paper/requirements-manuscript.txt records the environment the shipped figures were
    drawn in. Running paper/figures.py under a different matplotlib produced different
    bytes for identical inputs, which silently replaced the reviewed figures and
    invalidated figure_manifest.json. The pins existed; nothing read them.
    """
    want={}
    for line in (ROOT/'paper/requirements-manuscript.txt').read_text(encoding='utf-8').splitlines():
        line=line.split('#')[0].strip()
        if '==' in line:
            name,version=line.split('==',1); want[name.strip()]=version.strip()
    if not want: raise SystemExit('requirements-manuscript.txt pins nothing; the build cannot check its environment')
    if only is not None:
        want={n:v for n,v in want.items() if n in only}
        if not want: raise SystemExit('none of %r is pinned in requirements-manuscript.txt'%sorted(only))
    probe=('import json,importlib.metadata as m\n'
           'out={}\n'
           'for n in %r:\n'
           '    try: out[n]=m.version(n)\n'
           '    except Exception: out[n]=None\n'
           'print(json.dumps(out))\n'%sorted(want))
    try:
        got=json.loads(subprocess.run([interpreter,'-c',probe],capture_output=True,text=True,check=True).stdout)
    except subprocess.CalledProcessError as exc:
        raise SystemExit('cannot read package versions from %s: %s'%(interpreter,exc.stderr.strip()[:200]))
    # torch reports a local version such as 2.14.1+cpu; the wheel index is a choice the
    # requirements file comments on, not a different build of the library.
    base=lambda s:(s or '').split('+',1)[0]
    wrong=['%s %s (pinned %s)'%(n,got.get(n) or 'missing',v) for n,v in sorted(want.items()) if base(got.get(n))!=v]
    if wrong:
        raise SystemExit('this interpreter does not match paper/requirements-manuscript.txt: '
                         +'; '.join(wrong)+'\nUse the project environment, e.g. .venv\\Scripts\\python.exe -X utf8 -B paper\\build_all.py')

def main():
    p=argparse.ArgumentParser(); p.add_argument('--strict',action='store_true')
    p.add_argument('--no-pdf',action='store_true',help='Draft-only build without Word PDF export')
    args=p.parse_args()
    docx_python=os.environ.get('DOCX_PYTHON',sys.executable)
    pinned_versions(sys.executable,only={'numpy','scipy','scikit-image','matplotlib','torch','pydicom'})
    pinned_versions(docx_python,only={'python-docx'})
    subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'paper/figures.py')],cwd=ROOT,check=True)
    subprocess.run([docx_python,'-X','utf8','-B',str(ROOT/'submission/jxst/build_submission_docs.py')],cwd=ROOT,check=True)
    if not args.no_pdf:
        if os.name!='nt': raise RuntimeError('PDF export requires Windows Word; use --no-pdf for a draft-only build')
        subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'submission/jxst/render_word.ps1')],cwd=ROOT,check=True)
    output=ROOT/'submission/jxst/output'
    artifacts=list(output.glob('*.docx'))+list(output.glob('*.pdf'))+list(output.glob('*.csv'))+[output/'manuscript.txt']
    (output/'delivery_manifest.json').write_text(json.dumps({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts},indent=2))
    # The author block, resolved against Crossref and against the page that was just
    # built. It is allowed to be unfinished in a draft build - the telephone and the
    # author's approval are his to give - but --strict refuses to call that ready.
    identity=subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'submission/jxst/check_author_identity.py')],cwd=ROOT)
    if identity.returncode and args.strict: raise SystemExit('author identity gate failed')
    # Does it cite like a research article in the journal it is going to? The threshold
    # is measured from the journal, not asserted; --measure rewrites the benchmark.
    density=subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'submission/jxst/check_reference_density.py')],cwd=ROOT)
    if density.returncode and args.strict: raise SystemExit('reference density gate failed')
    # A recorded visual review describes particular bytes. This build may have just
    # replaced them, which is exactly when the recorded PASS stops being true.
    currency=subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'submission/jxst/check_visual_review_currency.py')],cwd=ROOT)
    if currency.returncode and args.strict: raise SystemExit('visual review is stale')
    command=[sys.executable,'-X','utf8','-B',str(ROOT/'submission/jxst/check_template_conformance.py')]
    if args.strict: command.append('--strict')
    subprocess.run(command,cwd=ROOT,check=True)

if __name__=='__main__': main()
