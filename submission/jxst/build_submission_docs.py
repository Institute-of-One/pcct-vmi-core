"""Build Word manuscript from editable text and frozen JSON; never edit DOCX manually."""
import csv
import hashlib
import html
import json
import re
import sys
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT=Path(__file__).resolve().parents[2]
PAPER=ROOT/'paper'
OUT=ROOT/'submission/jxst/output'
sys.path.insert(0,str(Path(__file__).resolve().parent))
from readiness_gates import pending_gates
from author_block import load_author

def load(name): return json.loads((ROOT/'results'/name).read_text())
def conditions(name): return {(c['size_cm'],c['dose_fraction']):c for c in load(name)['conditions']}
def peak(c,field):
    p=max(c['per_kev'],key=lambda x:x[field]); return f"{p['kev']} / {p[field]:.2f}"
def stat(q): return f"{1000*q['mean']:+.3f} ± {1000*q['sd']:.3f}"

def tables():
    d1=conditions('denoised_eval.json'); d2=conditions('denoised_eval_d2.json'); tv=conditions('tv_eval.json')
    t1=[['Diameter / count','Raw frozen','D1 frozen','Raw scaled','D1 scaled']]
    t2=[['Diameter / count','Baseline','Raw deviation','D1 deviation','D2 deviation','TV deviation']]
    for key,c in d1.items():
        label=f'{key[0]*10:g} mm / {100*key[1]:g}%'
        t1.append([label]+[peak(c,f) for f in ('d_npwe_raw','d_npwe_denoised','d_npwe_raw_processed','d_npwe_denoised_processed')])
        t2.append([label,f"{1000*c['quantitation']['baseline_b_g_cm3']:.3f}",stat(c['quantitation']['raw_dev']),stat(c['quantitation']['denoised_dev']),stat(d2[key]['quantitation']['denoised_dev']),stat(tv[key]['quantitation']['tv_dev'])])
    t3=[['Count / arm','VMI RMSE (HU)','SSIM','Pulp bias / SD','Shell bias / SD']]
    for tag,c in load('walnut_eval_summary.json').items():
        for a in ('raw','d1w','tv'):
            p=c[a]['md_pulp_roi_pulp']; s=c[a]['md_shell_roi_shell']
            t3.append([f"{c['dose']*100:g}% / {a.upper()}",f"{c[a]['vmi_rmse_mean_hu']:.1f}",f"{c[a]['vmi_ssim_mean']:.3f}",f"{p['bias']:+.1f} / {p['sd']:.1f}",f"{s['bias']:+.1f} / {s['sd']:.1f}"])
    return [t1,t2,t3]

TITLES=['Table 1. Peak energy (keV) / NPWE d′ magnitude. Scaled columns retain template shape and modify amplitude only.',
        'Table 2. Noiseless iodine baseline and deviation mean ± realization SD (mgI/mL). N = 64 per condition.',
        'Table 3. Walnut summary over 60 adjacent slices from one specimen. Material bias / mean pixel SD are on the calibration-table mg/cm³-scale. RMSE is centrally masked; SSIM is whole-image.']

def clean(s):
    """Crossref titles carry HTML. Printed as-is they reach the editor as '&amp;'."""
    return re.sub(r'\s+',' ',re.sub(r'<[^>]+>','',html.unescape(str(s)))).strip()

def refs_text():
    refs=json.loads((PAPER/'references.json').read_text(encoding='utf-8'))
    out=[]
    for i,r in enumerate(refs,1):
        c=r['csl']; authors=list(r.get('display_authors',[]))
        if not authors:
            for a in c.get('author',[])[:6]:
                # Split on dots as well as spaces: 'F.R.' is one token and rendered as
                # 'F', which lost an initial on two references.
                given=[p for p in re.split(r'[\s.\-]+',a.get('given','') or '') if p]
                authors.append((a.get('family',a.get('literal',''))+' '+''.join(p[0] for p in given)).strip())
            if len(c.get('author',[]))>6: authors.append('et al.')
        container=c.get('container-title','')
        if isinstance(container,list): container='; '.join(container)
        container=clean(container)
        title=clean(r.get('display_title',r['title']))
        if r['doi'].startswith('10.5281/'):
            publication=f"Zenodo. {r['year']}."
        else:
            vol=c.get('volume',''); pages=c.get('page',c.get('article-number',''))
            publication=f"{container}. {r['year']}"+(f';{vol}' if vol else '')+(f':{pages}' if pages else '')+'.'
        out.append(f"[{i}] {', '.join(authors).rstrip('.')}. {title}. {publication} https://doi.org/{r['doi']}")
    return '\n\n'.join(out)

def configure(doc):
    s=doc.sections[0]; s.top_margin=Inches(.8); s.bottom_margin=Inches(.8); s.left_margin=Inches(.8); s.right_margin=Inches(.8)
    s.page_width=Inches(8.27); s.page_height=Inches(11.69)
    style=doc.styles['Normal']; style.font.name='Times New Roman'; style.font.size=Pt(11)
    style.paragraph_format.space_after=Pt(6); style.paragraph_format.line_spacing=1.15
    for n in ('Normal','Title','Heading 1','Heading 2','Heading 3','Caption'):
        st=doc.styles[n]; st.font.name='Times New Roman'; st.font.color.rgb=RGBColor(0,0,0)
        for fonts in st.element.findall('.//'+qn('w:rFonts')):
            for attr in list(fonts.attrib):
                if 'theme' in attr.lower(): del fonts.attrib[attr]
        for border in st.element.findall('.//'+qn('w:pBdr')): border.getparent().remove(border)
    doc.styles['Title'].font.size=Pt(20)
    doc.styles['Caption'].font.size=Pt(10); doc.styles['Caption'].font.bold=False
    p=s.footer.paragraphs[0]; p.alignment=2
    fld=OxmlElement('w:fldSimple'); fld.set(qn('w:instr'),'PAGE'); p._p.append(fld)
    doc.core_properties.author=''; doc.core_properties.last_modified_by=''

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    source=(PAPER/'manuscript.md').read_text(encoding='utf-8')
    ts=tables(); refs=refs_text()
    expanded=source.replace('{{REFERENCES}}',refs)
    for i,t in enumerate(ts,1):
        with (OUT/f'table{i}.csv').open('w',encoding='utf-8-sig',newline='') as f: csv.writer(f).writerows(t)
        expanded=expanded.replace('{{TABLE'+str(i)+'}}',TITLES[i-1]+'\n\n'+'\n'.join(' | '.join(row) for row in t))
    (OUT/'manuscript.txt').write_text(expanded,encoding='utf-8')
    doc=Document(); configure(doc)
    for block in source.replace('{{REFERENCES}}',refs).split('\n\n'):
        block=block.strip()
        if not block: continue
        m=re.fullmatch(r'\{\{TABLE(\d)\}\}',block)
        if m:
            i=int(m[1])-1; doc.add_paragraph(TITLES[i],style='Caption')
            table=doc.add_table(rows=0,cols=len(ts[i][0])); table.style='Table Grid'
            for k,row in enumerate(ts[i]):
                cells=table.add_row().cells
                for cell,value in zip(cells,row):
                    cell.text=value
                    for p in cell.paragraphs:
                        for r in p.runs: r.font.size=Pt(8)
                if k==0:
                    hdr=OxmlElement('w:tblHeader'); table.rows[-1]._tr.get_or_add_trPr().append(hdr)
            doc.add_paragraph()
        elif block.startswith('# '): doc.add_paragraph(block[2:],style='Title')
        elif block.startswith('### '): doc.add_heading(block[4:],level=2)
        elif block.startswith('## '):
            if block=='## Figure captions': doc.add_page_break()
            doc.add_heading(block[3:],level=1)
        else:
            if block.startswith('Figure ') and re.match(r'Figure [1-5]\.',block):
                n=int(block[7])
                if n!=1: doc.add_page_break()
                doc.add_picture(str(PAPER/f'figures/figure{n}.png'),width=Inches(6.6))
                doc.add_paragraph(block,style='Caption')
            else: doc.add_paragraph(block)
    doc.save(OUT/'manuscript.docx')
    title=Document(); configure(title)
    title.add_paragraph(source.splitlines()[0][2:],style='Title')
    # The author block comes from paper/author.json, never from a literal here: the
    # affiliation is checked against Crossref and a second copy would drift from it.
    # The telephone and street address come from paper/author_contact.local.json, which
    # is outside the public repository; without it those two lines say [PENDING].
    a=load_author()
    title.add_paragraph('\n'.join([a['name'],a['affiliation'],'ORCID: '+a['orcid']]))
    title.add_paragraph('\n'.join(['Corresponding author: '+a['name'],
                                   'Address: '+(a['street_address'] or '[PENDING]'),
                                   'Telephone: '+(a['telephone'] or '[PENDING]'),
                                   'Email: '+a['email']]))
    # The draft stamp is resolved from the gates, not from a sentence written here. It
    # used to be keyed on two fields of author.json, so filling in the telephone would
    # have removed a warning that also named the AI disclosure and the data locator.
    open_gates=pending_gates()
    if open_gates:
        title.add_paragraph('DRAFT - not for submission while these gates are open in '
                            'paper/readiness.json: '+', '.join(open_gates)+'.')
    for heading in ('Acknowledgements','Author Contributions','Statements and Declarations'):
        part=source.split('## '+heading+'\n',1)[1].split('\n## ',1)[0]
        title.add_heading(heading,level=1)
        for b in part.strip().split('\n\n'):
            if b.startswith('### '): title.add_heading(b[4:],level=2)
            else: title.add_paragraph(b)
    title.save(OUT/'title_page.docx')
    body=source.split('## 1. Introduction')[1].split('## Acknowledgements')[0]
    abstract=source.split('## Abstract')[1].split('Keywords:')[0]
    summary={'body_words':len(body.split()),'abstract_words_including_labels':len(abstract.split()),'tables':3,'figures':5,
             'inputs':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [PAPER/'manuscript.md',PAPER/'references.json',Path(__file__)]},
             'status':('DRAFT - open gates: '+', '.join(open_gates)) if open_gates else 'all gates in paper/readiness.json record PASS'}
    (OUT/'build_report.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(summary)

if __name__=='__main__': main()
