from pathlib import Path
import argparse
import json

import numpy as np
import pandas as pd


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--results-dir',type=Path,required=True)
    parser.add_argument('--demand-file',type=Path,required=True)
    args=parser.parse_args()
    original=pd.read_csv(args.demand_file,keep_default_na=False)
    demand_mean=original.groupby('cf_location').human_volume_proxy.mean().to_dict()
    rows=[]
    vectors={}
    for path in sorted((args.results_dir/'certificates').glob('*.npz')):
        c=path.stem
        cert=np.load(path,allow_pickle=False)
        t=len(cert['d'])
        pbar=cert['partner_basis']/t
        R=float(cert['r_nnls'].sum())
        original_scale=float(demand_mean[c])
        vectors[f'{c}_d_proxy_raw']=cert['d']*original_scale
        vectors[f'{c}_r_proxy_raw']=cert['r_nnls']*original_scale
        vectors[f'{c}_rbar']=cert['r_nnls']/R
        vectors[f'{c}_partner_sbar']=pbar
        vectors[f'{c}_partners']=cert['partners']
        for stage in ['fixed_nnls_residual','lp_domestic_residual']:
            if stage=='fixed_nnls_residual':
                r_unit=cert['r_unit']
                primal=cert['primal']
                h=-cert['dual_inequality']
                eqdual=cert['dual_equality'][0]
                R_current=R
            else:
                r_unit=cert['lp_r_unit']
                primal=cert['lp_routing_primal']
                h=-cert['lp_routing_dual_inequality']
                eqdual=cert['lp_routing_dual_equality'][0]
                domestic_fit=cert['domestic_basis']@cert['domestic_lp_primal'][:cert['domestic_basis'].shape[1]]
                R_current=float(np.maximum(cert['d']-domestic_fit,0).sum())
            rbar=r_unit/t
            k=pbar.shape[1]
            w=primal[:k]
            ubar=primal[k:]/t
            partner_dot=h@pbar
            separating_margin=float(h@rbar-partner_dot.max())
            primal_objective=float(ubar.sum())
            dual_objective=float(h@rbar+eqdual)
            exact_rho=float(np.maximum(rbar-pbar@w,0).sum())
            dual_weight_reduced_cost=-(pbar.T@h)-eqdual
            annual_U=exact_rho*R_current/float(cert['d'].sum())
            record={'country':c,'stage':stage,'E_proxy_raw':float(cert['d'].sum())*original_scale,'R_proxy_raw':R_current*original_scale,'R_over_E':R_current/float(cert['d'].sum()),'rho_primal':primal_objective,'rho_dual':dual_objective,'rho_exact_uncovered':exact_rho,'separation_margin':separating_margin,'U_annual':annual_U,'h_min':float(h.min()),'h_max':float(h.max()),'h_bound_violation':float(max(0,-h.min(),h.max()-1)),'margin_minus_rho_absolute':abs(separating_margin-exact_rho),'normalized_primal_dual_gap':abs(primal_objective-dual_objective),'normalized_energy_equality_error':abs(float(w.sum())-1),'normalized_uncovered_constraint_violation':float(max(0,(rbar-pbar@w-ubar).max())),'normalized_weight_reduced_cost_violation':float(max(0,-dual_weight_reduced_cost.min())),'dual_y_plus_max_partner_dot':abs(float(eqdual+partner_dot.max()))}
            rows.append(record)
            prefix=f'{c}_{stage}'
            vectors[f'{prefix}_h']=h
            vectors[f'{prefix}_rbar']=rbar
            vectors[f'{prefix}_w']=w
            vectors[f'{prefix}_ubar']=ubar
    df=pd.DataFrame(rows)
    if len(df)!=208:
        raise ValueError(f'Expected two 104-country certificates; got {len(df)}')
    columns=['h_bound_violation','margin_minus_rho_absolute','normalized_primal_dual_gap','normalized_energy_equality_error','normalized_uncovered_constraint_violation','normalized_weight_reduced_cost_violation','dual_y_plus_max_partner_dot']
    errors=df[columns].max().to_dict()
    if max(errors.values())>1e-8:
        raise ValueError(f'Normalized certificate exceeded external verification tolerance: {errors}')
    if not df.separation_margin.gt(0).all():
        raise ValueError('A country has no positive separation margin')
    df.to_csv(args.results_dir/'normalized_separation_certificates.csv',index=False)
    np.savez_compressed(args.results_dir/'hourly_separating_vectors.npz',**vectors)
    summary={'n_certificates':len(df),'external_verification_tolerance_unit_energy':1e-8,'max_errors':errors,'by_stage':{stage:{'median_rho':float(g.rho_exact_uncovered.median()),'median_annual_U':float(g.U_annual.median()),'minimum_separation_margin':float(g.separation_margin.min()),'maximum_separation_margin':float(g.separation_margin.max())} for stage,g in df.groupby('stage')}}
    (args.results_dir/'normalized_separation_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
