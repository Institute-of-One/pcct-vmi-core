"""Reaggregate saved slice records and independently replay fixed walnut slice 530.

Does not overwrite frozen results. Not a rerun of all training or primary simulations.
"""
import sys
import json
from pathlib import Path
import zipfile
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.walnut_summary import summarize
from tools.walnut_eval import process_slice, ZIP_PATH
from pcctvmi.noise_inject import NoiseModel
from pcctvmi.denoiser import VMIDenoiser

def numeric_leaves(x,prefix=''):
    if isinstance(x,dict):
        for k,v in x.items():
            if k!='elapsed_s': yield from numeric_leaves(v,prefix+'/'+k)
    elif isinstance(x,list):
        for k,v in enumerate(x): yield from numeric_leaves(v,prefix+'/'+str(k))
    elif isinstance(x,(float,int)): yield prefix,float(x)

def main():
    stored=json.loads((ROOT/'results/walnut_eval_summary.json').read_text())
    regenerated={f'd{d:g}':summarize(d) for d in (.25,.125)}
    a=dict(numeric_leaves(stored));b=dict(numeric_leaves(regenerated))
    assert a.keys()==b.keys()
    max_summary=max(abs(a[k]-b[k]) for k in a)
    assert max_summary<1e-9
    torch.set_num_threads(4)
    net=VMIDenoiser(n_channels=2);net.load_state_dict(torch.load(ROOT/'results/denoiser_d1w_weights.pt',weights_only=True))
    model=NoiseModel.load(ROOT/'results/walnut_noise_model_d0.25.npz')
    with zipfile.ZipFile(ZIP_PATH) as z: replay=process_slice(z,model,net,.25,530)
    rows=json.loads((ROOT/'results/walnut_eval_d0.25.json').read_text())['slices']
    saved=next(r for r in rows if r['slice']==530)
    aa=dict(numeric_leaves(saved));bb=dict(numeric_leaves(replay));assert aa.keys()==bb.keys()
    errors={k:abs(aa[k]-bb[k]) for k in aa if not np.isclose(aa[k],bb[k],rtol=1e-5,atol=1e-5)}
    report={'reaggregation':'PASS','summary_numeric_values':len(a),'max_absolute_difference':max_summary,
            'slice_replay':'FAIL' if errors else 'PASS','slice':530,'dose':.25,'mismatches':errors,
            'scope':'Reaggregation of both 60-slice datasets and one 25% slice replay; not full experiment rerun'}
    (ROOT/'paper/result_verification.json').write_text(json.dumps(report,indent=2))
    print(report)
    if errors: raise SystemExit(1)

if __name__=='__main__':main()
