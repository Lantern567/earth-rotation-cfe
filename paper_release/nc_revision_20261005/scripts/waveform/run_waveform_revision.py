from pathlib import Path
import argparse
import json
import time

import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.optimize import nnls, linprog
from threadpoolctl import threadpool_limits


SCRIPT_DIR = Path(__file__).resolve().parent
ARCHIVE_ROOT = SCRIPT_DIR.parents[1]
HERE = ARCHIVE_ROOT / 'results/waveform'
DATA = ARCHIVE_ROOT / 'inputs/hourly'
FROZEN = ARCHIVE_ROOT / 'inputs/reference/waveform'
CONSUMER_PROFILE = DATA / 'burstgpt_diurnal_fit_v2.csv'
RAW_CACHE = None
DEVELOPMENT_LAYOUT = False
WINDOW_METADATA = DATA / 'normalization_windows.csv'
HYPERSCALERS = {'US','CA','BR','CL','MX','GB','IE','FR','DE','NL','BE','CH','IT','ES','SE','NO','FI','PL','AT','GR','DK','JP','KR','IN','ID','MY','TH','AU','NZ','ZA','IL','AE','SA','BH','KW','TR','EG','CN','TW','QA'}
TAUS = [50,100,150,200,300,500]
PHIS = [0,.2,.4,.6,.8,1.]
KEY = ['US','GB','DE','CN','IN','AU']


def add_path_arguments(parser):
    parser.add_argument('--project-root',type=Path,help='Original developer project; use only to audit original inputs')
    parser.add_argument('--data-root',type=Path,help='Portable directory containing flat hourly input files')
    parser.add_argument('--output-dir',type=Path,default=HERE)
    parser.add_argument('--reference-dir',type=Path,help='Frozen published waveform tables')
    parser.add_argument('--consumer-profile',type=Path)
    parser.add_argument('--window-metadata',type=Path)
    parser.add_argument('--raw-cache',type=Path,help='Optional original total-volume JSON cache for a fresh metadata audit')


def configure(args):
    global HERE,DATA,FROZEN,CONSUMER_PROFILE,RAW_CACHE,WINDOW_METADATA,DEVELOPMENT_LAYOUT
    if args.project_root is not None and args.data_root is not None:
        raise ValueError('Choose either --project-root or --data-root')
    HERE=args.output_dir.resolve()
    if args.project_root is not None:
        DEVELOPMENT_LAYOUT=True
        project=args.project_root.resolve()
        DATA=project/'collective_attention_research_plan/data'
        FROZEN=project/'collective_attention_research_plan/reports/cfe_geographic_portfolio_ai/data_globalsites_stations_expanded'
        CONSUMER_PROFILE=project/'collective_attention_research_plan/reports/ai_inference_growth_curve_fit/burstgpt_diurnal_fit_v2.csv'
        RAW_CACHE=DATA/'cloudflare_global_demand/raw'
    elif args.data_root is not None:
        DATA=args.data_root.resolve()
        CONSUMER_PROFILE=DATA/'burstgpt_diurnal_fit_v2.csv'
        WINDOW_METADATA=DATA/'normalization_windows.csv'
    if args.reference_dir is not None:
        FROZEN=args.reference_dir.resolve()
    if args.consumer_profile is not None:
        CONSUMER_PROFILE=args.consumer_profile.resolve()
    if args.window_metadata is not None:
        WINDOW_METADATA=args.window_metadata.resolve()
    if args.raw_cache is not None:
        RAW_CACHE=args.raw_cache.resolve()


def input_path(filename,original_subdirectory):
    if DEVELOPMENT_LAYOUT:
        return DATA/original_subdirectory/filename
    return DATA/filename


def load_data():
    meta = pd.read_csv(input_path('country_meta.csv','global_renewable_sites'), keep_default_na=False).set_index('iso2')
    raw = pd.read_csv(input_path('country_hourly_demand.csv.gz','cloudflare_global_demand'), keep_default_na=False)
    raw['timestamp_utc'] = pd.to_datetime(raw['timestamp_utc'], utc=True).dt.tz_localize(None)
    site = pd.read_parquet(input_path('site_hourly_cf.parquet','global_renewable_sites'))
    site['timestamp_utc'] = pd.to_datetime(site['timestamp_utc'], utc=True).dt.tz_localize(None)
    idx = pd.DatetimeIndex(sorted(site['timestamp_utc'].unique()))
    station = site.pivot(index='timestamp_utc', columns='site_id', values='cf').reindex(idx)
    if len(idx) != 8760 or station.isna().any().any():
        raise ValueError('Station inputs are incomplete or do not span 8760 hours')
    station_meta = site[['site_id','iso2','tech']].drop_duplicates().set_index('site_id')
    home, shapes, demand, hours = {}, {}, {}, {}
    for c, g in raw.groupby('cf_location'):
        if c not in meta.index:
            continue
        vals = g.set_index('timestamp_utc')['human_volume_proxy'].reindex(idx)
        if vals.isna().any() or vals.mean() <= 0:
            raise ValueError(f'Incomplete demand: {c}')
        sids = station_meta.index[station_meta['iso2'].eq(c)]
        mat = station[sids].to_numpy(float)
        mat = mat[:, mat.mean(axis=0) > 0]
        if mat.shape[1] == 0:
            continue
        mat = mat / mat.mean(axis=0)
        home[c] = mat
        shapes[c] = mat.mean(axis=1)
        demand[c] = vals.to_numpy(float) / float(vals.mean())
        hours[c] = (idx.hour.to_numpy() + int(round(float(meta.loc[c,'lon'])/15))) % 24
    countries = sorted(demand)
    if len(countries) != 104 or station.shape[1] != 461:
        raise ValueError(f'Unexpected country/station counts: {len(countries)}, {station.shape[1]}')
    reach = {}
    for c in countries:
        reach[c] = {tau: [] for tau in TAUS}
        a = np.radians([meta.loc[c,'lat'],meta.loc[c,'lon']])
        for r in countries:
            if c == r or r not in HYPERSCALERS:
                continue
            b = np.radians([meta.loc[r,'lat'],meta.loc[r,'lon']])
            hav = np.sin((b[0]-a[0])/2)**2 + np.cos(a[0])*np.cos(b[0])*np.sin((b[1]-a[1])/2)**2
            km = 2*6371*np.arcsin(np.sqrt(np.clip(hav,0,1)))
            rtt = 2*(km/200 + 20)*1.4
            for tau in TAUS:
                if rtt <= tau:
                    reach[c][tau].append(r)
    return idx, countries, demand, home, shapes, hours, reach, meta


def fit_nnls(d, mat, energy=None):
    w, _ = nnls(mat, d)
    fit = mat @ w
    target = float(d.sum()) if energy is None else float(energy)
    if fit.sum() <= 0:
        raise ValueError('NNLS returned zero energy')
    w *= target / fit.sum()
    return w, mat @ w


def direct_lp(d, mat, energy=None):
    # 约束与对偶均保存，单位平均负荷便于跨国家核查数值误差。
    t, k = mat.shape
    target = float(d.sum()) if energy is None else float(energy)
    obj = np.r_[np.zeros(k),np.ones(t)]
    aub = sp.hstack([-sp.csr_matrix(mat), -sp.eye(t,format='csr')],format='csr')
    bub = -d
    aeq = sp.csr_matrix(np.r_[mat.sum(axis=0),np.zeros(t)].reshape(1,-1))
    result = linprog(obj,A_ub=aub,b_ub=bub,A_eq=aeq,b_eq=[target],bounds=(0,None),method='highs',options={'primal_feasibility_tolerance':1e-8,'dual_feasibility_tolerance':1e-8,'ipm_optimality_tolerance':1e-9})
    if not result.success:
        raise RuntimeError(f'LP failed ({result.status}): {result.message}')
    fit = mat @ result.x[:k]
    dual = float(bub @ result.ineqlin.marginals + target * result.eqlin.marginals[0])
    reduced = obj - np.asarray(aub.T @ result.ineqlin.marginals).ravel() - np.asarray(aeq.T @ result.eqlin.marginals).ravel()
    metrics = {
        'solver_status':result.status,
        'primal_objective':float(result.fun),
        'dual_objective':dual,
        'duality_gap_absolute':abs(float(result.fun)-dual),
        'duality_gap_relative':abs(float(result.fun)-dual)/max(1,abs(result.fun)),
        'primal_inequality_violation':float(max(0,np.max(aub @ result.x - bub))),
        'primal_equality_violation':abs(float((aeq @ result.x)[0])-target),
        'primal_bound_violation':float(max(0,-np.min(result.x))),
        'dual_sign_violation':float(max(0,np.max(result.ineqlin.marginals))),
        'dual_stationarity_violation':float(np.max(np.abs(reduced-result.lower.marginals))),
        'dual_reduced_cost_violation':float(max(0,-np.min(reduced))),
        'complementarity_max':float(max(np.max(np.abs(result.x*reduced)),np.max(np.abs(result.ineqlin.marginals*result.ineqlin.residual))))
    }
    return fit, metrics, result


def routed(d, home, partner, phi=1, cached_home=None):
    fit = fit_nnls(d, home)[1] if cached_home is None else cached_home
    residual = np.maximum(d-fit,0)
    r = np.minimum(phi*d,residual)
    if partner.shape[1] == 0 or r.sum() == 0:
        covered = np.zeros_like(d)
    else:
        route_fit = fit_nnls(r,partner)[1]
        covered = np.minimum(r,route_fit)
    return float((residual-covered).sum()/d.sum()),float(residual.sum()/d.sum()),covered


def rebuild_original_grid(inputs):
    idx,countries,demand,home,shapes,hours,reach,meta=inputs
    region_names={'AF':'Africa/MENA','AS':'Asia-Pacific','EU':'Europe','NA':'North America','SA':'Latin America','OC':'Asia-Pacific','AN':'Other'}
    rows,edges,fs=[],[],[]
    country_cf=pd.read_parquet(input_path('country_hourly_cf.parquet','global_renewable_sites'))
    country_cf['timestamp_utc']=pd.to_datetime(country_cf.timestamp_utc,utc=True).dt.tz_localize(None)
    curves=country_cf.pivot(index='timestamp_utc',columns=['iso2','tech'],values='cf').reindex(idx)
    capacities=pd.read_csv(input_path('country_capacity.csv','global_renewable_sites'),keep_default_na=False,na_values=['']).set_index(['iso2','tech'])
    start=time.time()
    for ci,c in enumerate(countries):
        d=demand[c]
        local=fit_nnls(d,home[c])[1]
        residual=np.maximum(d-local,0)
        for tau in TAUS:
            partners=reach[c][tau]
            p=np.column_stack([shapes[r] for r in partners]) if partners else np.empty((len(idx),0))
            for phi in PHIS:
                u,b,cov=routed(d,home[c],p,phi,cached_home=local)
                rows.append({'country':c,'region':region_names.get(meta.loc[c,'region_code'],'Other'),'continent':meta.loc[c,'continent_block'],'tau_ms':tau,'phi':phi,'reach_km':round(max(200*(tau/(2*1.4)-20),0)),'n_partners':len(partners),'uncovered_share':u,'uncovered_share_baseline':b,'migrated_share':float(cov.sum()/d.sum())})
            if tau in [100,150,200,500] and partners:
                w,fit=fit_nnls(residual,p)
                covered=np.minimum(residual,fit)
                contr=p*w
                fitpos=np.where(fit>0,fit,1.)
                cov_r=(covered[:,None]*contr/fitpos[:,None]).sum(axis=0)/d.sum()
                for r,value in zip(partners,cov_r):
                    if value>=.0015:
                        edges.append({'sender_country':c,'receiver_country':r,'weight':float(value),'recv_lon':float(meta.loc[r,'lon']),'recv_lat':float(meta.loc[r,'lat']),'send_lon':float(meta.loc[c,'lon']),'send_lat':float(meta.loc[c,'lat']),'tau_ms':tau})
                if tau==500:
                    phasors=np.column_stack([np.exp(1j*2*np.pi*((idx.hour.to_numpy()+float(meta.loc[r,'lon'])/15)%24)/24) for r in partners])
                    sender_phasor=(covered*(contr*phasors).sum(axis=1)/fitpos).sum()
                    solar=float((np.angle(sender_phasor)/(2*np.pi)*24)%24)
                    cpv=float(capacities.loc[(c,'PV'),'capacity_mw_used']) if (c,'PV') in capacities.index else 0.
                    cwind=float(capacities.loc[(c,'WIND'),'capacity_mw_used']) if (c,'WIND') in capacities.index else 0.
                    pv=curves[(c,'PV')].to_numpy(float) if (c,'PV') in curves else np.zeros(len(idx))
                    wind=curves[(c,'WIND')].to_numpy(float) if (c,'WIND') in curves else np.zeros(len(idx))
                    supply=(cpv*pv+cwind*wind)/(cpv+cwind) if cpv+cwind>0 else .5*(pv+wind)
                    peak=int(np.argmax([d[hours[c]==h].mean() for h in range(24)]))
                    supply_peak=int(np.argmax([supply[hours[c]==h].mean() for h in range(24)]))
                    lag=(peak-supply_peak)%24
                    if lag>12:
                        lag-=24
                    fs.append({'country':c,'x_peak':float(peak),'y_solar':solar,'reach':float(((peak-solar+12)%24)-12),'phase_lag':float(lag),'migrated_share':float(covered.sum()/d.sum())})
        if (ci+1)%20==0:
            print(f'full original grid {ci+1}/{len(countries)}; {time.time()-start:.1f}s',flush=True)
    df=pd.DataFrame(rows)
    df.to_csv(HERE/'r2_waveform_grid.csv',index=False)
    median=(df.groupby(['phi','tau_ms']).uncovered_share.median().unstack()*100).round(1).reindex(index=PHIS,columns=TAUS)
    median.to_csv(HERE/'r2_waveform_median.csv')
    edge_df=pd.DataFrame(edges)
    followsun=pd.DataFrame(fs)
    followsun.to_csv(HERE/'r2_wf_followsun.csv',index=False)
    checks={}
    frozen=pd.read_csv(FROZEN/'r2_waveform_grid.csv',keep_default_na=False).set_index(['country','tau_ms','phi'])
    new=df.set_index(['country','tau_ms','phi'])
    checks['grid_rows']=len(df)
    checks['grid_max_absolute_difference']={field:float((new[field]-frozen[field]).abs().max()) for field in ['uncovered_share','uncovered_share_baseline','migrated_share']}
    for tau in [100,150,200,500]:
        fname='r2_wf_compute_flows.csv' if tau==500 else f'r2_wf_compute_flows_tau{tau}.csv'
        part=edge_df[edge_df.tau_ms.eq(tau)].drop(columns=['tau_ms'])
        part.to_csv(HERE/fname,index=False)
        old=pd.read_csv(FROZEN/fname,keep_default_na=False).set_index(['sender_country','receiver_country'])
        keyed=part.set_index(['sender_country','receiver_country'])
        if set(old.index)!=set(keyed.index):
            raise ValueError(f'Flow index mismatch: tau={tau}')
        checks[f'flow_tau{tau}_max_absolute_difference']=float((keyed.weight-old.weight).abs().max())
    oldfs=pd.read_csv(FROZEN/'r2_wf_followsun.csv',keep_default_na=False).set_index('country')
    newfs=followsun.set_index('country')
    checks['followsun_max_absolute_difference']={field:float((newfs[field]-oldfs[field]).abs().max()) for field in ['x_peak','y_solar','reach','phase_lag','migrated_share']}
    if max(checks['grid_max_absolute_difference'].values())>1e-7 or max(checks['followsun_max_absolute_difference'].values())>1e-7:
        raise ValueError(f'Original grid reproduction failed: {checks}')
    (HERE/'original_grid_validation.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    print(json.dumps(checks,indent=2),flush=True)


def objective_analysis(inputs, limit=0):
    idx, countries, demand, home, shapes, hours, reach, meta = inputs
    subset = countries[:limit] if limit else countries
    rows, certs, refits = [],[],[]
    (HERE/'certificates').mkdir(exist_ok=True)
    start = time.time()
    for ci,c in enumerate(subset):
        d, s = demand[c],home[c]
        p = np.column_stack([shapes[r] for r in reach[c][500]])
        w, local = fit_nnls(d,s)
        residual = np.maximum(d-local,0)
        R = float(residual.sum())
        route_w, route_fit = fit_nnls(residual,p)
        covered = np.minimum(residual,route_fit)
        # 固定 NNLS 国内短缺，直接优化同一个可行集。
        r_unit = residual / residual.mean()
        fixed_fit, fixed_metrics, sol = direct_lp(r_unit,p)
        rho = float(np.maximum(r_unit-fixed_fit,0).sum()/r_unit.sum())
        fixed_cov = np.minimum(residual,fixed_fit*residual.mean())
        lp_local, local_metrics, local_sol = direct_lp(d,s)
        lp_residual = np.maximum(d-lp_local,0)
        lp_unit = lp_residual / lp_residual.mean()
        pipeline_fit, pipeline_metrics, pipeline_sol = direct_lp(lp_unit,p)
        lp_rho = float(np.maximum(lp_unit-pipeline_fit,0).sum()/lp_unit.sum())
        row = {'country':c,'n_home_stations':s.shape[1],'n_partners':p.shape[1],
            'E':float(d.sum()),'R_nnls':R,'L':0.,'dom_nnls':R/d.sum(),
            'dom_lp':float(lp_residual.sum()/d.sum()),
            'rt_nnls':float((residual-covered).sum()/d.sum()),
            'rt_lp_fixed_nnls_residual':float((residual-fixed_cov).sum()/d.sum()),
            'rho_fixed_nnls_residual':rho,
            'rt_lp_pipeline':float(lp_residual.sum()/d.sum())*lp_rho,
            'rho_lp_pipeline':lp_rho,
            'identity_error_fixed':abs(float((residual-fixed_cov).sum()/d.sum())-R/d.sum()*rho),
            'identity_error_pipeline':abs(float(lp_residual.sum()/d.sum())*lp_rho - float(np.maximum(lp_unit-pipeline_fit,0).sum()*lp_residual.mean()/d.sum()))}
        rows.append(row)
        for stage, metrics in [('fixed_nnls_residual_routing',fixed_metrics),('lp_domestic',local_metrics),('lp_domestic_residual_routing',pipeline_metrics)]:
            certs.append({'country':c,'stage':stage,**metrics})
        np.savez_compressed(HERE/'certificates'/f'{c}.npz',d=d,domestic_basis=s,partner_basis=p,partners=np.array(reach[c][500]),domestic_nnls_weights=w,r_nnls=residual,r_unit=r_unit,primal=sol.x,dual_inequality=sol.ineqlin.marginals,dual_equality=sol.eqlin.marginals,dual_lower=sol.lower.marginals,domestic_lp_primal=local_sol.x,domestic_lp_dual_inequality=local_sol.ineqlin.marginals,domestic_lp_dual_equality=local_sol.eqlin.marginals,lp_r_unit=lp_unit,lp_routing_primal=pipeline_sol.x,lp_routing_dual_inequality=pipeline_sol.ineqlin.marginals,lp_routing_dual_equality=pipeline_sol.eqlin.marginals)
        # 冻结已路由的 covered 后，再拟合 domestic；分开两种年度能源规则。
        remaining = d-covered
        refit_fixed = fit_nnls(remaining,s,energy=d.sum())[1]
        refit_reallocated = fit_nnls(remaining,s)[1]
        refits.append({'country':c,'original_uncovered_share':row['rt_nnls'],'covered_share':float(covered.sum()/d.sum()),'domestic_original_energy':float(d.sum()),'remaining_load_energy':float(remaining.sum()),'nnls_refit_fixed_domestic_energy':float(np.maximum(remaining-refit_fixed,0).sum()/d.sum()),'nnls_refit_reallocated_domestic_energy':float(np.maximum(remaining-refit_reallocated,0).sum()/d.sum())})
        if (ci+1)%10 == 0 or ci == 0:
            print(f'objective {ci+1}/{len(subset)}; {time.time()-start:.1f}s',flush=True)
            pd.DataFrame(rows).to_csv(HERE/'objective_results.csv',index=False)
            pd.DataFrame(certs).to_csv(HERE/'lp_certificates.csv',index=False)
            pd.DataFrame(refits).to_csv(HERE/'domestic_refit_comparison.csv',index=False)
    result = pd.DataFrame(rows)
    cert = pd.DataFrame(certs)
    result.to_csv(HERE/'objective_results.csv',index=False)
    cert.to_csv(HERE/'lp_certificates.csv',index=False)
    pd.DataFrame(refits).to_csv(HERE/'domestic_refit_comparison.csv',index=False)
    frozen = pd.read_csv(FROZEN/'r2_objective_robustness.csv',keep_default_na=False).set_index('country')
    check = result.set_index('country')
    errors = {name:float((check[new]-frozen.loc[check.index,old]).abs().max()) for name,new,old in [('dom_nnls','dom_nnls','dom_nnls'),('dom_lp','dom_lp','dom_lp'),('rt_nnls','rt_nnls','rt_nnls'),('rt_lp_pipeline','rt_lp_pipeline','rt_lp')]}
    summary = {'n_countries':len(result),'median_percent':{k:float(result[k].median()*100) for k in ['dom_nnls','dom_lp','rt_nnls','rt_lp_fixed_nnls_residual','rho_fixed_nnls_residual','rt_lp_pipeline','rho_lp_pipeline']},'frozen_max_absolute_difference':errors,'same_residual_lp_worse_count':int((result.rt_lp_fixed_nnls_residual-result.rt_nnls>1e-7).sum()),'pipeline_lp_worse_count':int((result.rt_lp_pipeline-result.rt_nnls>1e-7).sum()),'certificate_max':{c:float(cert[c].max()) for c in cert.columns if c not in ['country','stage']},'refit_median_percent':{c:float(pd.DataFrame(refits)[c].median()*100) for c in ['original_uncovered_share','nnls_refit_fixed_domestic_energy','nnls_refit_reallocated_domestic_energy']}}
    (HERE/'objective_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    if len(result)==104 and max(errors.values())>1e-6:
        raise ValueError(f'Frozen results disagree: {errors}')
    if summary['same_residual_lp_worse_count']:
        raise ValueError('Same-residual LP cannot be worse than feasible NNLS')
    print(json.dumps(summary,indent=2),flush=True)


def profiles():
    empirical = pd.read_csv(CONSUMER_PROFILE)
    consumer = empirical.sort_values('hour')['share_tokens'].to_numpy(float)
    consumer /= consumer.mean()
    h = np.arange(24)
    business = np.exp(-.5*((h-13)/3)**2)
    business /= business.mean()
    pd.DataFrame({'local_hour':h,'consumer_token_shape':consumer,'business_assumed_shape':business}).to_csv(HERE/'business_consumer_profiles.csv',index=False)
    return consumer,business


def mix_analysis(inputs, limit=0):
    idx,countries,demand,home,shapes,hours,reach,meta = inputs
    subset = countries[:limit] if limit else countries
    consumer,business = profiles()
    rows,grid = [],[]
    start = time.time()
    for c in subset:
        p = np.column_stack([shapes[r] for r in reach[c][500]])
        for alpha in [0,.25,.5,.75,1]:
            profile = ((1-alpha)*consumer + alpha*business)[hours[c]]
            # 2030 的推断负荷份额 0.308，训练份额 0.132；总能源保持不变。
            d = .56*demand[c]+.308*profile+.132
            d *= demand[c].sum()/d.sum()
            local = fit_nnls(d,home[c])[1]
            u,b,cov = routed(d,home[c],p,cached_home=local)
            rows.append({'country':c,'business_fraction_of_inference':alpha,'lambda_inf':.308,'lambda_train':.132,'domestic_uncovered_share':b,'routed_uncovered_share':u,'total_energy':float(d.sum()),'energy_relative_error':abs(float(d.sum()/demand[c].sum())-1)})
            if c in KEY:
                for tau in TAUS:
                    partners = reach[c][tau]
                    pt = np.column_stack([shapes[r] for r in partners]) if partners else np.empty((len(idx),0))
                    for phi in PHIS:
                        uv,bv,cv = routed(d,home[c],pt,phi,cached_home=local)
                        grid.append({'country':c,'business_fraction_of_inference':alpha,'tau_ms':tau,'phi':phi,'n_partners':len(partners),'domestic_uncovered_share':bv,'routed_uncovered_share':uv,'covered_share':float(cv.sum()/d.sum())})
        if len(rows)%100==0:
            print(f'business mix {len(rows)//5}/{len(subset)}; {time.time()-start:.1f}s',flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(HERE/'business_consumer_country_results.csv',index=False)
    pd.DataFrame(grid).to_csv(HERE/'business_consumer_key_country_grid.csv',index=False)
    summary = df.groupby('business_fraction_of_inference')[['domestic_uncovered_share','routed_uncovered_share']].median()*100
    summary.to_csv(HERE/'business_consumer_median_percent.csv')
    print(summary.to_string(),flush=True)


def window_analysis(inputs, limit=0):
    idx,countries,demand,home,shapes,hours,reach,meta = inputs
    subset = countries[:limit] if limit else countries
    audits,rows,weights = [],[],[]
    window_ids = {}
    metadata = None if RAW_CACHE is not None else pd.read_csv(WINDOW_METADATA,keep_default_na=False)
    for c in countries:
        seen, chunks = [],[]
        win = np.full(len(idx),-1,dtype=int)
        cache_paths=sorted((RAW_CACHE/f'{c}_total_volume').glob('*.json')) if RAW_CACHE is not None else []
        windows=list(enumerate(cache_paths)) if RAW_CACHE is not None else list(metadata[metadata.country.eq(c)].sort_values('window').iterrows())
        for j,item in windows:
            if RAW_CACHE is not None:
                doc = json.loads(item.read_text(encoding='utf-8'))
                ts = pd.DatetimeIndex(pd.to_datetime(doc['serie_0']['timestamps'],utc=True)).tz_localize(None)
                record={'country':c,'window':j,'start':str(ts.min()),'end':str(ts.max()),'n_hours':len(ts),'normalization':doc['meta']['normalization'],'meta_keys':'|'.join(sorted(doc['meta'])),'has_raw_scale':any(k in doc['meta'] for k in ['max','maximum','normalizationFactor','scaleFactor'])}
            else:
                record=item.to_dict()
                j=int(record['window'])
                ts=pd.date_range(record['start'],record['end'],freq='h')
            if record['normalization'] != 'MIN0_MAX':
                raise ValueError(f'Unexpected normalization: {c}, {j}')
            loc = idx.get_indexer(ts)
            if np.min(loc)<0:
                raise ValueError(f'Cache timestamp absent from common index: {c}')
            if (win[loc]>=0).any():
                raise ValueError(f'Overlapping windows unexpectedly found: {c}')
            win[loc]=j
            seen.extend(ts)
            chunks.append(record)
        if np.min(win)<0:
            raise ValueError(f'Window audit found missing coverage: {c}')
        audits.extend(chunks)
        window_ids[c]=win
    pd.DataFrame(audits).to_csv(HERE/'window_normalization_audit.csv',index=False)
    for c in subset:
        win = window_ids[c]
        nwin = int(win.max())+1
        p = np.column_stack([shapes[r] for r in reach[c][500]])
        # 季节幅度与相位均为条件假设，缓存未包含可恢复的原始总量。
        scenarios = [('published_equal_scale',np.ones(nwin)),('equal_mean_each_window',None)]
        for amplitude in [.25,.5]:
            for phase in [0,3,6,9]:
                scale = 1+amplitude*np.cos(2*np.pi*(np.arange(nwin)-phase)/12)
                scenarios.append((f'assumed_amp{int(100*amplitude)}_phase{phase}',scale))
        for name,scale in scenarios:
            if scale is None:
                scale = np.array([1/demand[c][win==j].mean() for j in range(nwin)])
            vals = demand[c]*scale[win]
            vals *= demand[c].sum()/vals.sum()
            u,b,cov = routed(vals,home[c],p)
            rows.append({'country':c,'scenario':name,'domestic_uncovered_share':b,'routed_uncovered_share':u,'scale_min':float(scale.min()),'scale_max':float(scale.max()),'energy_relative_error':abs(float(vals.sum()/demand[c].sum())-1)})
            for j,v in enumerate(scale):
                weights.append({'country':c,'scenario':name,'window':j,'conditional_scale_factor':v,'window_hours':int((win==j).sum())})
    df=pd.DataFrame(rows)
    df.to_csv(HERE/'window_weight_country_results.csv',index=False)
    pd.DataFrame(weights).to_csv(HERE/'window_weight_scenario_factors.csv',index=False)
    (df.groupby('scenario')[['domestic_uncovered_share','routed_uncovered_share']].median()*100).to_csv(HERE/'window_weight_median_percent.csv')
    print((df.groupby('scenario')[['domestic_uncovered_share','routed_uncovered_share']].median()*100).to_string(),flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['objective','mix','windows','grid','all'],default='all')
    parser.add_argument('--limit',type=int,default=0)
    parser.add_argument('--full-grid',action='store_true',help='Also rebuild all 104 countries x 6 x 6 and original Fig 3 attribution tables')
    add_path_arguments(parser)
    args=parser.parse_args()
    configure(args)
    HERE.mkdir(parents=True,exist_ok=True)
    with threadpool_limits(limits=1):
        inputs = load_data()
        if args.full_grid or args.mode=='grid':
            rebuild_original_grid(inputs)
        if args.mode in ['objective','all']:
            objective_analysis(inputs,args.limit)
        if args.mode in ['mix','all']:
            mix_analysis(inputs,args.limit)
        if args.mode in ['windows','all']:
            window_analysis(inputs,args.limit)


if __name__ == '__main__':
    main()
