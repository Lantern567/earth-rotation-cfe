from pathlib import Path
import argparse

import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.font_manager import findfont


PURPLE='#7C3AED'
ORANGE='#F59E0B'
INK='#1F2937'


def style():
    findfont('Arial',fallback_to_default=False)
    mpl.rcParams.update({'font.family':'Arial','font.size':8,'axes.labelsize':8,'xtick.labelsize':7,'ytick.labelsize':7,'legend.fontsize':7,'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#6B7280','axes.labelcolor':INK,'xtick.color':INK,'ytick.color':INK,'axes.linewidth':.6,'xtick.major.width':.6,'ytick.major.width':.6,'pdf.fonttype':42,'ps.fonttype':42,'savefig.dpi':300,'figure.facecolor':'white','savefig.facecolor':'white','legend.frameon':False})


def panels(axes):
    for label,ax in zip('abcd',axes.flat):
        ax.text(-.14,1.06,label,transform=ax.transAxes,fontsize=11,fontweight='bold',ha='left',va='top')
        ax.tick_params(length=3,pad=2)


def identity(ax,limit):
    ax.plot([0,limit],[0,limit],color='#9CA3AF',lw=.8,ls='--',zorder=0)
    ax.set_xlim(0,limit)
    ax.set_ylim(0,limit)


def save(fig,path):
    fig.savefig(path.with_suffix('.pdf'),bbox_inches='tight',pad_inches=.08)
    fig.savefig(path.with_suffix('.png'),dpi=300,bbox_inches='tight',pad_inches=.08)
    plt.close(fig)


def s6(results,out):
    obj=pd.read_csv(results/'objective_results.csv',keep_default_na=False)
    refit=pd.read_csv(results/'domestic_refit_comparison.csv',keep_default_na=False)
    cert=pd.read_csv(results/'normalized_separation_certificates.csv',keep_default_na=False)
    cert=cert[cert.stage.eq('fixed_nnls_residual')]
    if len(obj)!=104 or len(refit)!=104 or len(cert)!=104:
        raise ValueError('Figure S6 requires all 104 countries')
    fig,axes=plt.subplots(2,2,figsize=(7.1,6.5),gridspec_kw={'wspace':.36,'hspace':.45})
    panels(axes)
    ax=axes[0,0]
    identity(ax,30)
    ax.scatter(obj.rt_nnls*100,obj.rt_lp_fixed_nnls_residual*100,s=14,color=PURPLE,alpha=.65,edgecolors='none')
    ax.set_xlabel('NNLS annual matching gap U (%)')
    ax.set_ylabel('LP annual matching gap U (%)')
    ax.text(.04,.95,'Same domestic shortfall\n104 countries',transform=ax.transAxes,va='top',fontsize=7,color=INK)
    ax=axes[0,1]
    ax.scatter(obj.rho_fixed_nnls_residual*100,obj.rt_lp_fixed_nnls_residual*100,s=14,color=ORANGE,alpha=.65,edgecolors='none')
    ax.set_xlabel('Unit-shortfall residual ρ (%)')
    ax.set_ylabel('Annual matching gap U (%)')
    ax.set_xlim(0,60)
    ax.set_ylim(0,30)
    ax.text(.04,.96,'U = (R/E) ρ\nComputed separately for each country',transform=ax.transAxes,va='top',fontsize=7,color=INK)
    ax=axes[1,0]
    identity(ax,60)
    ax.scatter(cert.rho_primal*100,cert.separation_margin*100,s=15,color=PURPLE,alpha=.65,edgecolors='none')
    ax.set_xlabel('LP primal residual ρ (%)')
    ax.set_ylabel('Separating margin (%)')
    ax.text(.04,.96,'h · r̄ − maxᵢ h · s̄ᵢ\nMaximum absolute error: 8.1e-15',transform=ax.transAxes,va='top',fontsize=7,color=INK)
    ax=axes[1,1]
    cols=['original_uncovered_share','nnls_refit_fixed_domestic_energy','nnls_refit_reallocated_domestic_energy']
    vals=[refit[c].to_numpy()*100 for c in cols]
    for row in refit[cols].to_numpy()*100:
        ax.plot([1,2,3],row,color='#9CA3AF',alpha=.10,lw=.5,zorder=0)
    rng=np.random.default_rng(4721)
    colors=[PURPLE,ORANGE,'#64748B']
    for i,(data,color) in enumerate(zip(vals,colors),start=1):
        ax.scatter(i+rng.uniform(-.055,.055,len(data)),data,s=7,color=color,alpha=.38,edgecolors='none')
    box=ax.boxplot(vals,positions=[1,2,3],widths=.33,patch_artist=True,showfliers=False,medianprops={'color':INK,'linewidth':1.1},whiskerprops={'color':INK,'linewidth':.7},capprops={'color':INK,'linewidth':.7},boxprops={'linewidth':.7})
    for patch,color in zip(box['boxes'],colors):
        patch.set_facecolor(color)
        patch.set_alpha(.28)
    ax.set_xticks([1,2,3],['Fixed\ndomestic fit','Refit; original\ndomestic energy','Refit; remaining-\nload energy'])
    ax.set_ylabel('Annual matching gap U (%)')
    ax.set_ylim(0,max(40,np.ceil(max(v.max() for v in vals)/5)*5))
    save(fig,out/'FigS6_conditional_certificate')


def s7(results,out):
    profiles=pd.read_csv(results/'business_consumer_profiles.csv')
    mixes=pd.read_csv(results/'business_consumer_country_results.csv',keep_default_na=False)
    windows=pd.read_csv(results/'window_weight_country_results.csv',keep_default_na=False)
    if mixes.country.nunique()!=104 or windows.country.nunique()!=104:
        raise ValueError('Figure S7 requires all 104 countries')
    fig,axes=plt.subplots(2,2,figsize=(7.1,6.8),gridspec_kw={'wspace':.39,'hspace':.43})
    panels(axes)
    ax=axes[0,0]
    ax.plot(profiles.local_hour,profiles.consumer_token_shape,color=ORANGE,lw=1.8,label='Consumer; trace-derived tokens')
    ax.plot(profiles.local_hour,profiles.business_assumed_shape,color=PURPLE,lw=1.8,label='Working hours; assumed')
    ax.set_xlabel('Assigned local hour')
    ax.set_ylabel('Inference shape (daily mean = 1)')
    ax.set_xticks([0,6,12,18,23])
    ax.set_xlim(0,23)
    ax.set_ylim(0,4.1)
    ax.legend(loc='upper left',fontsize=6.5)
    ax=axes[0,1]
    alpha=np.array([0,.25,.5,.75,1.])
    for field,color,label in [('domestic_uncovered_share',PURPLE,'Domestic'),('routed_uncovered_share',ORANGE,'Global waveform match')]:
        groups=mixes.groupby('business_fraction_of_inference')[field]
        med=groups.median().reindex(alpha).to_numpy()*100
        lower=groups.quantile(.25).reindex(alpha).to_numpy()*100
        upper=groups.quantile(.75).reindex(alpha).to_numpy()*100
        ax.fill_between(alpha*100,lower,upper,color=color,alpha=.15,lw=0)
        ax.plot(alpha*100,med,'o-',color=color,lw=1.5,ms=4,label=label)
    ax.set_xlabel('Working-hours fraction of inference (%)')
    ax.set_ylabel('Annual matching gap U (%)')
    ax.set_xlim(-3,103)
    ax.set_xticks([0,25,50,75,100])
    ax.set_ylim(0,60)
    ax.legend(loc='upper right',fontsize=6.5)
    ax=axes[1,0]
    consumer=mixes[mixes.business_fraction_of_inference.eq(0)].set_index('country')
    business=mixes[mixes.business_fraction_of_inference.eq(1)].set_index('country')
    dd=(business.domestic_uncovered_share-consumer.domestic_uncovered_share)*100
    dr=(business.routed_uncovered_share-consumer.routed_uncovered_share)*100
    ax.scatter(dd,dr,s=14,color=PURPLE,alpha=.65,edgecolors='none')
    ax.axhline(0,color='#9CA3AF',lw=.8,ls='--',zorder=0)
    ax.axvline(0,color='#9CA3AF',lw=.8,ls='--',zorder=0)
    ax.set_xlabel('Paired domestic ΔU (percentage points)')
    ax.set_ylabel('Paired global ΔU (percentage points)')
    ax=axes[1,1]
    order=['published_equal_scale','equal_mean_each_window']+[f'assumed_amp{a}_phase{p}' for a in [25,50] for p in [0,3,6,9]]
    labels=['Published scales','Equal window means']+[f'±{a}%, offset {p}' for a in [25,50] for p in [0,3,6,9]]
    grouped=windows.groupby('scenario')[['domestic_uncovered_share','routed_uncovered_share']].median().reindex(order)*100
    y=np.arange(len(order))
    for field,color,label,delta in [('domestic_uncovered_share',PURPLE,'Domestic',-.10),('routed_uncovered_share',ORANGE,'Global',.10)]:
        ax.scatter(grouped[field],y+delta,s=20,color=color,label=label)
    ax.set_yticks(y,labels)
    ax.invert_yaxis()
    ax.set_xlabel('Median annual matching gap U (%)')
    ax.set_xlim(0,50)
    ax.legend(loc='lower center',ncol=2,fontsize=6.5,bbox_to_anchor=(.58,-.30))
    save(fig,out/'FigS7_demand_and_window_sensitivity')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--results-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    style()
    s6(args.results_dir,args.output_dir)
    s7(args.results_dir,args.output_dir)


if __name__=='__main__':
    main()
