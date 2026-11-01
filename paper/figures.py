"""Generate manuscript figures from frozen JSON and original local walnut data."""
from pathlib import Path
import sys
import json
import hashlib
import zipfile
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIG = ROOT / 'paper' / 'figures'
FILES = ['denoised_eval.json','denoised_eval_d2.json','tv_eval.json',
         'walnut_eval_summary.json','walnut_eval_d0.25.json','walnut_eval_d0.125.json']

def load(name):
    return json.loads((ROOT/'results'/name).read_text())

def conditions(name):
    return {(c['size_cm'],c['dose_fraction']):c for c in load(name)['conditions']}

def save(fig, n):
    # Deliberate top headroom for portal labels; do not use bbox_inches='tight'.
    fig.subplots_adjust(top=0.84 if n==2 else 0.87, bottom=0.16, left=0.10, right=0.97, hspace=0.55, wspace=0.8 if n==5 else 0.4)
    fig.savefig(FIG/f'figure{n}.png', dpi=300, facecolor='white')
    # Omit the PDF CreationDate. With it, every rebuild produced different bytes for
    # identical content, so the manifest and the visual review went stale on a rerun and
    # a clean-environment byte comparison could never pass. The PNGs were already
    # reproducible; only the date differed.
    fig.savefig(FIG/f'figure{n}.pdf', facecolor='white', metadata={'CreationDate': None})
    plt.close(fig)

def main():
    FIG.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False})
    d1=conditions(FILES[0]); d2=conditions(FILES[1]); tv=conditions(FILES[2])
    keys=list(d1)
    fig,ax=plt.subplots(figsize=(10,4)); ax.axis('off')
    boxes=[(.01,.62,'120 kVp water/iodine\nPoisson projections'),(.35,.62,'2 bins / FBP / 2 bases\n16 VMI levels: 40-190 keV'),(.69,.62,'Raw / D1 / D2 / TV\n64 paired realizations'),(.01,.10,'Walnut 1 reconstructions\n60 slices / one specimen'),(.35,.10,'Correlated Gaussian injection\n25% and 12.5% nominal dose'),(.69,.10,'Raw / retrained D1w / TV\nVMI and material errors')]
    for x,y,s in boxes: ax.text(x,y,s,transform=ax.transAxes,va='center',bbox={'boxstyle':'round,pad=0.6','facecolor':'#edf2f7','edgecolor':'#334155'})
    for y in (.62,.10):
        for x in (.29,.63): ax.annotate('',xy=(x+.05,y),xytext=(x,y),xycoords='axes fraction',arrowprops={'arrowstyle':'->'})
    save(fig,1)
    fig,axs=plt.subplots(3,2,figsize=(10,9))
    for ax,key in zip(axs.flat,keys):
        for label,data,field,style in [('Raw',d1,'d_npwe_raw','--'),('D1',d1,'d_npwe_denoised','-'),('D2',d2,'d_npwe_denoised','-'),('TV',tv,'d_npwe_tv','-')]:
            rows=data[key]['per_kev']; x=[p['kev'] for p in rows]
            line=ax.plot(x,[p[field] for p in rows],style,label=label+' frozen')[0]
            ax.plot(x,[abs(p[field+'_processed']) for p in rows],':',color=line.get_color(),label=label+' amplitude-scaled')
        ax.set(title=f'{key[0]*10:g} mm, {key[1]*100:g}%',xlabel='Energy (keV)',ylabel="NPWE d-prime magnitude")
        ax.set_yscale('symlog',linthresh=1)
        ax.grid(alpha=.2)
    handles,labels=axs[0,0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='upper center',bbox_to_anchor=(.54,.93),fontsize=8,ncol=4,frameon=False)
    save(fig,2)
    fig,axs=plt.subplots(1,2,figsize=(10,4.5))
    for j,dose in enumerate((1.,.25)):
        ax=axs[j]
        for idx,(label,data,field) in enumerate([('Raw',d1,'raw_dev'),('D1',d1,'denoised_dev'),('D2',d2,'denoised_dev'),('TV',tv,'tv_dev')]):
            q=[data[(s,dose)]['quantitation'][field] for s in (.3,.5,.8)]
            ax.errorbar(np.arange(3)+(idx-1.5)*.16,[p['mean']*1000 for p in q],yerr=[p['sd']*1000 for p in q],fmt='o',capsize=3,label=label)
        ax.axhline(0,color='gray',lw=.7); ax.set(xticks=np.arange(3),xticklabels=['3','5','8'],xlabel='Insert diameter (mm)',ylabel='Iodine deviation (mgI/mL)',title=f'{dose*100:g}% dose')
    axs[0].legend(fontsize=8); save(fig,3)
    fig,axs=plt.subplots(1,2,figsize=(10,4.5))
    for ax,dose in zip(axs,(1.,.25)):
        for label,data,field,qfield in [('Raw',d1,'d_npwe_raw_processed','raw_dev'),('D1',d1,'d_npwe_denoised_processed','denoised_dev'),('D2',d2,'d_npwe_denoised_processed','denoised_dev'),('TV',tv,'d_npwe_tv_processed','tv_dev')]:
            xx=[]; yy=[]
            for s in (.3,.5,.8):
                c=data[(s,dose)]; q=c['quantitation'][qfield]
                xx.append(max(abs(p[field]) for p in c['per_kev']))
                yy.append(np.hypot(q['mean'],q['sd'])*1000)
            ax.scatter(xx,yy,label=label)
            for k,(x,y,s) in enumerate(zip(xx,yy,(3,5,8))):
                offset=[(-12,10),(8,0),(0,-13)][k] if label=='TV' else [(4,8),(4,2),(4,-8)][k]
                ax.annotate(str(s),(x,y),xytext=offset,textcoords='offset points',fontsize=7)
        ax.set(xlabel='Maximum absolute d-prime\n(amplitude-scaled template)',ylabel='Deviation RMS proxy (mgI/mL)',title=f'{dose*100:g}% dose',xscale='log',yscale='log'); ax.grid(alpha=.2)
    axs[0].legend(); save(fig,4)
    # Reuse the authoritative evaluation functions, never a pre-existing preview bitmap.
    import torch
    from tools.walnut_eval import _load_dcm, ZIP_PATH, SERIES, HU_SCALE, SEED_BASE
    from pcctvmi.noise_inject import NoiseModel,synthesize
    from pcctvmi.denoiser import VMIDenoiser
    from pcctvmi.tv import chambolle_tv_3d,laplacian_noise_sd
    from pcctvmi.walnut import vmi_stack
    torch.set_num_threads(4)
    slice_idx=530 # fixed midpoint of 500..559, established preview index; no metric selection
    with zipfile.ZipFile(ZIP_PATH) as z:
        ref=np.stack([_load_dcm(z,f'{SERIES}/{b}/{slice_idx:05d}.dcm') for b in ('Low','High')])
    model=NoiseModel.load(ROOT/'results/walnut_noise_model_d0.25.npz')
    raw=ref+synthesize(model,ref.shape[1:],np.random.default_rng(SEED_BASE+slice_idx))*np.asarray(HU_SCALE)[:,None,None]
    net=VMIDenoiser(n_channels=2); net.load_state_dict(torch.load(ROOT/'results/denoiser_d1w_weights.pt',weights_only=True)); net.eval()
    with torch.no_grad(): den=net(torch.from_numpy(raw.astype(np.float32))[None])[0].numpy()
    smooth=chambolle_tv_3d(raw,.5*laplacian_noise_sd(raw)**2)
    fig=plt.figure(figsize=(10,7)); gs=fig.add_gridspec(2,4)
    for i,(label,stack) in enumerate([('Reference',ref),('Raw',raw),('D1w',den),('TV',smooth)]):
        ax=fig.add_subplot(gs[0,i]); ax.imshow(vmi_stack(*stack)[3],cmap='gray',vmin=-500,vmax=500); ax.set_title(label+' / 40 keV'); ax.axis('off')
    summary=load(FILES[3])
    for j,metric in enumerate(('md_pulp_roi_pulp','md_shell_roi_shell')):
        ax=fig.add_subplot(gs[1,j*2:j*2+2]); entries=[summary['d0.25'][a][metric] for a in ('raw','d1w','tv')]
        ax.errorbar(range(3),[p['bias'] for p in entries],yerr=[p['sd'] for p in entries],fmt='o',capsize=5)
        ax.set(xticks=range(3),xticklabels=['Raw','D1w','TV'],ylabel='Material deviation\n(mg/cm3-scale)',title=('Pulp in pulp ROI' if j==0 else 'Shell in shell ROI')); ax.axhline(0,color='gray',lw=.5)
    save(fig,5)
    inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'results'/f for f in FILES]+[Path(__file__),ROOT/'tools/walnut_eval.py',ROOT/'pcctvmi/walnut.py',ROOT/'pcctvmi/denoiser.py',ROOT/'pcctvmi/tv.py',ROOT/'pcctvmi/noise_inject.py',ROOT/'results/denoiser_d1w_weights.pt',ROOT/'results/walnut_noise_model_d0.25.npz']}
    # Hash the source archive via acquisition provenance instead of reading 19 GB on each build.
    provenance=ROOT/'data/walnut/PROVENANCE.json'
    if provenance.exists(): inputs[str(provenance.relative_to(ROOT))]=hashlib.sha256(provenance.read_bytes()).hexdigest()
    outputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in FIG.glob('figure*.*')}
    (ROOT/'paper/figure_manifest.json').write_text(json.dumps({'inputs':inputs,'outputs':outputs,'visual_review':'PENDING','archive':str(ZIP_PATH),'slice':slice_idx,'window_hu':[-500,500]},indent=2))
    print('Generated figures 1-5')

if __name__=='__main__': main()
