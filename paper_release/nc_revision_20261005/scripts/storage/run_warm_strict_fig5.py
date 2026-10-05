import os
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
import argparse
import concurrent.futures
import time
from pathlib import Path

import pandas as pd

import run_full_strict_fig5 as F
import strict_storage_dispatch as S

HERE = F.HERE


def solve_country(task):
    country, tasks = task
    basis = None
    rows = []
    country_dir = HERE/'warm_country_results'
    country_dir.mkdir(exist_ok=True)
    for digest,job in tasks:
        started = time.time()
        result = S.solve_dispatch(job['d_mw'].astype(float),job['fit_mw'].astype(float),job['gen1'],job['anc1'],job['ecl'],job['ecd'],
                                  lp_method='highspy',warm_basis=basis,return_basis=True)
        if not result['ok']:
            raise RuntimeError(f'Failed {country} {job["year"]} {job["tau"]} {job["phi"]}: {result}')
        basis = result.pop('_basis')
        if result['unmet_mwh'] != 0.0 or result['equality_max_abs_error_mw']>1e-6 or result['inequality_max_violation_mw']>1e-6:
            raise ArithmeticError(f'Invalid numerical solution: {country} {result}')
        result.update({'country':country,'year':job['year'],'tau_ms':job['tau'],'phi':job['phi'],
                       'tier':job['tier'],'region':job['region'],'mode':'strict','deadline_h':0,
                       'uncovered_share':job['unc'],'elapsed_seconds':time.time()-started,
                       'input_digest':digest,'lcoe_gen_floor':job['gen1']/float(job['d_mw'].astype(float).sum())})
        result['pi'] = (result['lcoe_elec']-result['lcoe_gen'])/result['lcoe_gen']
        rows.append(result)
        if len(rows)%4==0:
            pd.DataFrame(rows).to_csv(country_dir/f'{country}.csv',index=False)
    pd.DataFrame(rows).to_csv(country_dir/f'{country}.csv',index=False)
    return rows


def main():
    global HERE
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers',type=int,default=16)
    parser.add_argument('--project-root',type=Path,default=F.R.PROJECT_ROOT)
    parser.add_argument('--output-dir',type=Path,default=HERE)
    args = parser.parse_args()
    F.R.PROJECT_ROOT = args.project_root.resolve()
    HERE = args.output_dir.resolve()
    HERE.mkdir(parents=True,exist_ok=True)
    F.HERE = HERE
    F.R.HERE = HERE
    F.ORIGINAL_TABLES = F.R.PROJECT_ROOT/'collective_attention_research_plan/reports/cfe_geographic_portfolio_ai/data_globalsites'
    os.environ['NC_PROJECT_ROOT'] = str(F.R.PROJECT_ROOT)
    os.environ['NC_STORAGE_OUTPUT'] = str(HERE)
    original, aliases, jobs = F.prepare_all()
    finished = {}
    output = HERE/'all_fig5_strict_results.csv'
    inputs = [output] + sorted((HERE/'warm_country_results').glob('*.csv'))
    for item in inputs:
        if item.exists():
            for row in pd.read_csv(item,keep_default_na=False).to_dict('records'):
                finished[row['input_digest']] = row
    if (HERE/'strict_reliability_2030.csv').exists():
        for row in pd.read_csv(HERE/'strict_reliability_2030.csv',keep_default_na=False).to_dict('records'):
            if row['mode']=='strict':
                key = (row['country'],int(row['year']),int(row['tau_ms']),round(float(row['phi']),6))
                row['input_digest'] = aliases[key]
                finished[aliases[key]] = row
    grouped = {}
    for digest,job in jobs.items():
        if digest not in finished:
            grouped.setdefault(job['cc'],[]).append((digest,job))
    for tasks in grouped.values():
        tasks.sort(key=lambda task:(task[1]['tau'],task[1]['phi'],task[1]['year']))
    started = time.time()
    print(f'Warm-basis solving {sum(len(v) for v in grouped.values())} inputs / {len(grouped)} countries with {args.workers} workers',flush=True)
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(solve_country,task):task[0] for task in grouped.items()}
        for future in concurrent.futures.as_completed(futures):
            rows = future.result()
            for row in rows:
                finished[row['input_digest']] = row
            pd.DataFrame(finished.values()).to_csv(output,index=False)
            print(f'{len(finished)}/{len(jobs)} solved; finished {rows[0]["country"]}; elapsed {time.time()-started:.1f}s',flush=True)
    F.write_tables(original,aliases,finished)
    print('All Fig5 cells complete and verified',flush=True)


if __name__ == '__main__':
    main()
