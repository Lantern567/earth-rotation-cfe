from pathlib import Path
import argparse
import json

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

import run_waveform_revision as W


def main():
    parser=argparse.ArgumentParser()
    W.add_path_arguments(parser)
    W.configure(parser.parse_args())
    idx,countries,demand,home,shapes,hours,reach,meta=W.load_data()
    rows,edges=[] , []
    W.HERE.mkdir(parents=True,exist_ok=True)
    frozen=pd.read_csv(W.FROZEN/'r2_waveform_grid.csv',keep_default_na=False)
    with threadpool_limits(limits=1):
        for c in countries:
            d=demand[c]
            local=W.fit_nnls(d,home[c])[1]
            residual=np.maximum(d-local,0)
            for tau in [100,150,200,500]:
                partners=reach[c][tau]
                if not partners:
                    cov=np.zeros_like(d)
                else:
                    p=np.column_stack([shapes[r] for r in partners])
                    w,fit=W.fit_nnls(residual,p)
                    cov=np.minimum(residual,fit)
                    fractions=np.divide(p*w,fit[:,None],out=np.zeros_like(p),where=fit[:,None]>0)
                    attr=(cov[:,None]*fractions).sum(axis=0)/d.sum()
                    if abs(attr.sum()-cov.sum()/d.sum())>1e-9:
                        raise ValueError(f'Attribution failed to conserve covered fraction: {c}, {tau}')
                    for r,val in zip(partners,attr):
                        edges.append({'country':c,'tau_ms':tau,'partner':r,'attributed_covered_share':float(val),'passes_published_flow_threshold':bool(val>=.0015)})
                rows.append({'country':c,'tau_ms':tau,'n_partners':len(partners),'domestic_share':float(residual.sum()/d.sum()),'uncovered_share':float((residual-cov).sum()/d.sum()),'covered_share':float(cov.sum()/d.sum())})
    df=pd.DataFrame(rows)
    df.to_csv(W.HERE/'fig3_country_statistics.csv',index=False)
    edge_df=pd.DataFrame(edges)
    edge_df.to_csv(W.HERE/'fig3_basis_attribution_unfiltered.csv',index=False)
    summary=df.groupby('tau_ms').agg(n_countries=('country','size'),mean_domestic_share=('domestic_share','mean'),mean_uncovered_share=('uncovered_share','mean'),mean_covered_share=('covered_share','mean'),median_domestic_share=('domestic_share','median'),median_uncovered_share=('uncovered_share','median'),median_covered_share=('covered_share','median'))
    summary['difference_of_medians']=summary.median_domestic_share-summary.median_uncovered_share
    summary['mean_identity_error']=abs(summary.mean_domestic_share-summary.mean_uncovered_share-summary.mean_covered_share)
    summary.to_csv(W.HERE/'fig3_four_tiers_summary.csv')
    errors=[]
    for tau in [100,150,200,500]:
        new=df[df.tau_ms.eq(tau)].set_index('country')
        old=frozen[frozen.tau_ms.eq(tau)&frozen.phi.eq(1)].set_index('country')
        fpath=W.FROZEN/('r2_wf_compute_flows.csv' if tau==500 else f'r2_wf_compute_flows_tau{tau}.csv')
        oldflows=pd.read_csv(fpath,keep_default_na=False)
        newedges=edge_df[edge_df.tau_ms.eq(tau)&edge_df.passes_published_flow_threshold].set_index(['country','partner'])
        oldflows=oldflows.set_index(['sender_country','receiver_country'])
        if set(newedges.index)!=set(oldflows.index):
            raise ValueError(f'Flow keys differ at tau={tau}')
        errors.append({'tau_ms':tau,'max_U_error':float((new.uncovered_share-old.uncovered_share).abs().max()),'max_covered_error':float((new.covered_share-old.migrated_share).abs().max()),'max_flow_weight_error':float((newedges.attributed_covered_share-oldflows.weight).abs().max()),'published_flow_edges':len(oldflows),'retained_mean_covered_share':float(oldflows.weight.sum()/104),'full_mean_covered_share':float(new.covered_share.mean()),'positive_partner_count':int(edge_df[edge_df.tau_ms.eq(tau)&edge_df.attributed_covered_share.gt(1e-8)].partner.nunique())})
    (W.HERE/'fig3_validation.json').write_text(json.dumps(errors,indent=2),encoding='utf-8')
    print(summary.to_string())
    print(json.dumps(errors,indent=2))


if __name__=='__main__':
    main()
