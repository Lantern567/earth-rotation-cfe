import os
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
import argparse
import concurrent.futures
import time
from pathlib import Path

import numpy as np
import pandas as pd

import run_storage_revision as R
import strict_storage_dispatch as S

HERE = R.HERE
COUNTRIES = ['US','DE','PS','IN','BR','AU']


def solve_country(task):
    country,tasks,baseline = task
    rows = baseline.copy()
    basis = None
    for job in tasks:
        started = time.time()
        result = S.solve_dispatch(job['d_mw'].astype(float),job['fit_mw'].astype(float),job['gen1'],job['anc1'],job['ecl'],job['ecd'],
                                  lp_method='highspy',warm_basis=basis,return_basis=True)
        if not result['ok']:
            raise RuntimeError(f'{country} {job["scenario"]} {job["tier"]}: {result}')
        basis = result.pop('_basis')
        if result['unmet_mwh']!=0.0 or result['equality_max_abs_error_mw']>1e-6:
            raise ArithmeticError(f'Invalid result for {country}: {result}')
        result.update({'country':country,'year':2030,'tier':job['tier'],'tau_ms':job['tau'],'phi':job['phi'],
                       'scenario':job['scenario'],'window_amplitude':job['amplitude'],'window_phase':0,
                       'uncovered_share':job['unc'],'original_proxy_energy':job['original_proxy_energy'],
                       'scenario_proxy_energy':job['scenario_proxy_energy'],'proxy_energy_error':job['proxy_energy_error'],
                       'region':job['region'],'elapsed_seconds':time.time()-started})
        result['pi'] = (result['lcoe_elec']-result['lcoe_gen'])/result['lcoe_gen']
        rows.append(result)
    return rows


def main():
    global HERE
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-root',type=Path,default=R.PROJECT_ROOT)
    parser.add_argument('--output-dir',type=Path,default=HERE)
    parser.add_argument('--normalization-windows',type=Path,default=R.PROJECT_ROOT/'inputs/hourly/normalization_windows.csv')
    parser.add_argument('--workers',type=int,default=2)
    args = parser.parse_args()
    R.PROJECT_ROOT = args.project_root.resolve()
    HERE = args.output_dir.resolve()
    HERE.mkdir(parents=True,exist_ok=True)
    R.HERE = HERE
    os.environ['NC_PROJECT_ROOT'] = str(R.PROJECT_ROOT)
    os.environ['NC_STORAGE_OUTPUT'] = str(HERE)
    windows = pd.read_csv(args.normalization_windows,keep_default_na=False,parse_dates=['start','end'])
    _,demand,_,supply,smeta = R.F.G.load_inputs_expanded()
    idx = demand[next(iter(demand))]['d'].index
    codes = sorted(c for c in demand if c in smeta)
    reach,receivers = R.F.A.precompute_reach(codes,smeta)
    nat_shape = {r:R.F.A.national_shape(supply,r,idx) for r in receivers}
    ecl,ecd = R.F.e_costs('central',2030)
    main_results = pd.read_csv(HERE/'strict_reliability_2030.csv',keep_default_na=False)
    all_tasks = []
    factors = []
    for cc in COUNTRIES:
        raw = R.F.base.as_arr(demand[cc]['d']).astype(float)
        lh = R.F.base.as_arr(demand[cc]['local_hour']).astype(int)
        w = windows[windows.country==cc].sort_values('window')
        assert len(w)==12
        assignment = np.full(len(idx),-1,dtype=int)
        count = np.zeros(len(idx),dtype=int)
        for row in w.itertuples():
            mask = (idx>=row.start)&(idx<=row.end)
            assert int(mask.sum())==int(row.n_hours)
            assignment[mask] = int(row.window)
            count[mask] += 1
        assert (count==1).all()
        baseline = main_results[(main_results.country==cc)&(main_results['mode']=='strict')].to_dict('records')
        assert len(baseline)==2
        for row in baseline:
            row.update({'scenario':'published_equal_scale','window_amplitude':0.0,'window_phase':0,
                        'original_proxy_energy':float(raw.sum()),'scenario_proxy_energy':float(raw.sum()),'proxy_energy_error':0.0})
        tasks = []
        for amplitude in [.25,.50]:
            multipliers = 1+amplitude*np.cos(2*np.pi*assignment/12)
            perturbed = raw*multipliers
            perturbed *= float(raw.sum())/float(perturbed.sum())
            error = float(abs(perturbed.sum()-raw.sum()))
            if error>1e-9:
                raise ArithmeticError(f'Proxy energy changed for {cc}: {error}')
            scenario = f'assumed_amp{int(100*amplitude)}_phase0'
            for j in range(12):
                factors.append({'country':cc,'scenario':scenario,'window':j,'conditional_scale_factor':float(1+amplitude*np.cos(2*np.pi*j/12))})
            dp = R.F.A.perturb('P_mix',perturbed,lh,.308,.132)
            for tau,phi,tier in R.F.TIERS:
                fh = R.F.front_half(cc,tau,phi,demand,supply,smeta,reach,nat_shape,idx,dp)
                if fh is None:
                    raise ValueError(f'No front half for {cc}')
                tasks.append({'cc':cc,'year':2030,'tau':tau,'phi':phi,'tier':tier,'scenario':scenario,'amplitude':amplitude,
                              'd_mw':fh['d_mw'],'fit_mw':fh['fit_mw'], 'gen1':R.F.P.gen_annual_cost(fh['np_pv'],fh['np_wind'],2030,'central'),
                              'anc1':R.F.P.ancillary_annual_cost(fh['gbb'],'central'),'ecl':ecl,'ecd':ecd,
                              'unc':fh['unc'],'region':fh['region'],'original_proxy_energy':float(raw.sum()),
                              'scenario_proxy_energy':float(perturbed.sum()),'proxy_energy_error':error})
        tasks.sort(key=lambda job:(job['tier'],job['amplitude']))
        all_tasks.append((cc,tasks,baseline))
    pd.DataFrame(factors).to_csv(HERE/'window_storage_factors.csv',index=False)
    started = time.time()
    rows = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(solve_country,task):task[0] for task in all_tasks}
        for future in concurrent.futures.as_completed(futures):
            results = future.result()
            rows.extend(results)
            pd.DataFrame(rows).sort_values(['country','scenario','tier']).to_csv(HERE/'window_storage_sensitivity_2030.csv',index=False)
            print(f'{len(rows)}/36 window sensitivity rows; finished {results[0]["country"]}; elapsed {time.time()-started:.1f}s',flush=True)
    print('Complete six-country window/storage sensitivity',flush=True)


if __name__ == '__main__':
    main()
