"""Export the built .docx files to PDF in a Word instance of our own.

Replaces render_word.ps1. PowerShell's New-Object -ComObject can bind to the Word the
author already has open, and the Quit at the end then closes their documents. DispatchEx
forces a separate instance, and only that instance is quit.

Pagination is off because Word's background repagination never finishes on a
figure-heavy manuscript (AGENTS.md section 3).
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

WD_EXPORT_PDF = 17
HERE = Path(__file__).resolve().parent
NAMES = ('manuscript', 'title_page')


def main(out_dir=None):
    import win32com.client                              # pywin32, Windows only
    out = Path(out_dir or HERE / 'output').resolve()
    word = win32com.client.DispatchEx('Word.Application')   # a new instance, not theirs
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        word.Options.Pagination = False
    except Exception as exc:                            # not fatal, but say so
        print('could not disable background pagination: %s' % exc)
    try:
        for name in NAMES:
            source = out / (name + '.docx')
            pdf = out / (name + '.pdf')
            doc = word.Documents.Open(str(source), False, True)
            try:
                doc.ExportAsFixedFormat(str(pdf), WD_EXPORT_PDF)
            finally:
                doc.Close(0)
            print('Exported %s' % pdf)
    finally:
        word.Quit()
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))
