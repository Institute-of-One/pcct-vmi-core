"""Does the tagged archive still redraw the figures the manuscript prints?

A release is a claim that someone else can take this code and get these results. The
test suite does not check that claim: it runs against the working tree, with whatever
was installed months ago, and it never draws a figure. So this expands the tag into an
empty directory, builds a new environment from the pins the repository ships, runs
`paper/figures.py` there, and compares the bytes with the figures the manuscript was
built from.

It is written down here rather than typed out at each release because it has to run
before the tag is archived, and because two of its steps are traps:

* the 19 GB walnut archive is deliberately not in the repository, so it is linked in at
  `data/walnut`, where `docs/DATA.md` tells a reader to put it. On Windows that link is
  a junction, and `rm -rf` follows a junction into the original. The working directory
  is therefore emptied only after the link has been removed, and only if it looks like
  one of ours.
* the figures are reproducible only under the pinned matplotlib. Running them under a
  newer one silently produces different bytes, which is why
  `paper/requirements-manuscript.txt` exists and why this installs from it.

What this proves is that the code and the pins reproduce the figures. It does not prove
that the walnut download works; that is `tools/fetch_reconstructions.py` and the
checksums in `docs/DATA.md`.

    python tools/verify_archive.py v0.2.0
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[1]
MARKER = '.pcct-archive-check'
TORCH_CPU = 'https://download.pytorch.org/whl/cpu'


def run(cmd, **kw):
    kw.setdefault('check', True)
    return subprocess.run(cmd, **kw)


def unlink_data(workdir):
    """Remove the walnut link, never its target."""
    link = workdir / 'data' / 'walnut'
    if not link.exists() and not link.is_symlink():
        return
    if os.name == 'nt':
        subprocess.run(['cmd', '/c', 'rmdir', str(link)], check=False)
    else:
        link.unlink(missing_ok=True)
    if link.exists():
        raise SystemExit('could not remove the link at %s; refusing to delete anything '
                         'under it' % link)


def empty(workdir, force):
    """Make workdir an empty directory, without ever deleting through the data link."""
    if workdir.exists():
        if not force and not (workdir / MARKER).exists() and any(workdir.iterdir()):
            raise SystemExit('%s is not empty and was not made by this tool (no %s). '
                             'Pass --workdir somewhere else, or --force if you are sure.'
                             % (workdir, MARKER))
        unlink_data(workdir)
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)
    (workdir / MARKER).write_text('expanded by tools/verify_archive.py\n', encoding='utf-8')


def expand(tag, workdir):
    archive = workdir / 'archive.tar'
    with archive.open('wb') as fh:
        run(['git', 'archive', tag], cwd=str(ROOT), stdout=fh)
    shutil.unpack_archive(str(archive), str(workdir), 'tar')
    archive.unlink()
    print('expanded %s: %d files' % (tag, sum(1 for _ in workdir.rglob('*') if _.is_file())))


def make_environment(workdir):
    run([sys.executable, '-m', 'venv', str(workdir / '.venv')])
    py = workdir / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    pins = dict(line.split('==', 1) for line in
                (ROOT / 'paper/requirements-manuscript.txt').read_text(encoding='utf-8')
                .splitlines() if '==' in line.split('#')[0])
    run([str(py), '-m', 'pip', 'install', '-q', '--upgrade', 'pip'])
    torch = pins.get('torch', '').strip()
    if torch:
        # The default index serves the CUDA build; nothing here needs it.
        run([str(py), '-m', 'pip', 'install', '-q', 'torch==' + torch,
             '--index-url', TORCH_CPU])
    run([str(py), '-m', 'pip', 'install', '-q', '-r',
         str(workdir / 'paper/requirements-manuscript.txt')])
    run([str(py), '-m', 'pip', 'install', '-q', '-e', str(workdir), '--no-deps'])
    names = ('numpy', 'scipy', 'scikit-image', 'matplotlib', 'torch', 'pydicom')
    out = run([str(py), '-c', 'import importlib.metadata as m;print(" ".join('
               '"%s==%s"%(n,m.version(n)) for n in ' + repr(names) + '))'],
              capture_output=True, text=True).stdout.strip()
    print('environment:', out)
    return py


def link_data(workdir, data):
    (workdir / 'data').mkdir(exist_ok=True)
    link = workdir / 'data' / 'walnut'
    if os.name == 'nt':
        run(['cmd', '/c', 'mklink', '/J', str(link), str(data)],
            capture_output=True, text=True)
    else:
        os.symlink(data, link, target_is_directory=True)
    if not (link / 'Reconstructions.zip').exists():
        raise SystemExit('%s does not hold Reconstructions.zip; see docs/DATA.md' % link)
    print('linked data/walnut -> %s' % data)


def compare(workdir):
    src, new = ROOT / 'paper/figures', workdir / 'paper/figures'
    bad = 0
    for n in range(1, 6):
        for ext in ('png', 'pdf'):
            name = 'figure%d.%s' % (n, ext)
            a, b = src / name, new / name
            if not b.exists():
                print('MISSING   %s' % name)
                bad += 1
                continue
            ha = hashlib.sha256(a.read_bytes()).hexdigest()
            hb = hashlib.sha256(b.read_bytes()).hexdigest()
            print('%-9s %-12s %s' % ('SAME' if ha == hb else 'DIFFERENT', name, hb[:12]))
            bad += ha != hb
    print('clean-environment figure rebuild: %s'
          % ('IDENTICAL' if not bad else '%d of 10 differ' % bad))
    return bad


def main():
    p = argparse.ArgumentParser()
    p.add_argument('tag')
    p.add_argument('--workdir', default=None,
                   help='where to expand the archive; emptied first, and refused if it '
                        'holds anything this tool did not put there')
    p.add_argument('--data', default=str(ROOT / 'data/walnut'),
                   help='the fetched walnut directory to link in (docs/DATA.md)')
    p.add_argument('--force', action='store_true')
    args = p.parse_args()

    workdir = Path(args.workdir) if args.workdir else \
        Path(tempfile.gettempdir()) / ('pcct-archive-' + args.tag)
    data = Path(args.data).resolve()
    if not data.is_dir():
        raise SystemExit('%s is not a directory; fetch the walnut data as docs/DATA.md '
                         'describes, or pass --data' % data)

    empty(workdir, args.force)
    expand(args.tag, workdir)
    py = make_environment(workdir)
    link_data(workdir, data)
    print('--- paper/figures.py in the fresh environment ---')
    run([str(py), '-X', 'utf8', '-B', str(workdir / 'paper/figures.py')], cwd=str(workdir))
    print('--- byte comparison with the figures the manuscript was built from ---')
    bad = compare(workdir)
    unlink_data(workdir)
    print('the walnut link has been removed; %s can now be deleted safely' % workdir)
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
