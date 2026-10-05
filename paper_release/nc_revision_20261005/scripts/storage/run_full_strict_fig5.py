import os
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
import argparse
import concurrent.futures
import hashlib
import json
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

import run_storage_revision as R

HERE = R.HERE
ORIGINAL_TABLES = R.SOURCE.parent/'reports/cfe_geographic_portfolio_ai/data_globalsites'
TABLE_NAMES = ['r3_dispatch_cost_table.csv', 'r3_dispatch_grid_2030.csv', 'r3_dispatch_yearly_phi1.csv']


def table_key(row):
    return str(row['country']), int(row['year']), int(row['tau_ms']), round(float(row['phi']), 6)


def input_digest(job):
    digest = hashlib.sha256()
    digest.update(job['d_mw'].tobytes())
    digest.update(job['fit_mw'].tobytes())
    digest.update(np.array([job['gen1'],job['anc1'],job['ecl'],job['ecd']],dtype=np.float64).tobytes())
    return digest.hexdigest()


def prepare_all():
    cached = HERE/'all_fig5_inputs.pkl'
    if cached.exists():
        with cached.open('rb') as handle:
            return pickle.load(handle)
    started = time.time()
    original = {name: pd.read_csv(ORIGINAL_TABLES/name, keep_default_na=False) for name in TABLE_NAMES}
    desired = set()
    for table in original.values():
        desired.update(table_key(row) for row in table.to_dict('records'))
    _, demand, _, supply, smeta = R.F.G.load_inputs_expanded()
    idx = demand[next(iter(demand))]['d'].index
    codes = sorted(c for c in demand if c in smeta)
    reach, receivers = R.F.A.precompute_reach(codes, smeta)
    nat_shape = {r: R.F.A.national_shape(supply, r, idx) for r in receivers}
    aliases, jobs, country_year = {}, {}, {}
    for key in sorted(desired):
        cc, year, tau, phi = key
        ckey = cc, year
        if ckey not in country_year:
            li = R.F.A._ai_share(R.F.base.AI_SHARE_INFERENCE,year)
            lt = R.F.A._ai_share(R.F.base.AI_SHARE_TRAINING,year)
            dp = R.F.A.perturb('P_mix', R.F.base.as_arr(demand[cc]['d']).astype(float), R.F.base.as_arr(demand[cc]['local_hour']).astype(int),li,lt)
            country_year[ckey] = dp
        ecl, ecd = R.F.e_costs('central',year)
        fh = R.F.front_half(cc,tau,phi,demand,supply,smeta,reach,nat_shape,idx,country_year[ckey])
        if fh is None:
            raise RuntimeError(f'No front half for {key}')
        job = {'cc':cc,'year':year,'tau':tau,'phi':phi,'tier':f't{tau}p{int(round(100*phi))}',
               'd_mw':fh['d_mw'],'fit_mw':fh['fit_mw'],
               'gen1':R.F.P.gen_annual_cost(fh['np_pv'],fh['np_wind'],year,'central'),
               'anc1':R.F.P.ancillary_annual_cost(fh['gbb'],'central'), 'ecl':ecl,'ecd':ecd,
               'unc':fh['unc'],'region':fh['region']}
        digest = input_digest(job)
        aliases[key] = digest
        jobs.setdefault(digest,job)
        if len(aliases)%500 == 0:
            print(f'Prepared {len(aliases)}/{len(desired)} keys; {len(jobs)} distinct inputs; {time.time()-started:.1f}s',flush=True)
    result = original, aliases, jobs
    with cached.open('wb') as handle:
        pickle.dump(result,handle,protocol=pickle.HIGHEST_PROTOCOL)
    (HERE/'full_fig5_inputs.json').write_text(json.dumps({'keys':len(aliases),'distinct_inputs':len(jobs),
            'tables':{name:len(table) for name,table in original.items()},'hours':len(idx),
            'reliability':'unserved_t fixed to zero every hour','objective':'same original annualized generation, storage and ancillary cost',
            'deduplication':'Exact SHA-256 equality of float32 demand/supply arrays and float64 costs'},indent=2),encoding='utf-8')
    print(f'Prepared {len(aliases)} keys / {len(jobs)} inputs in {time.time()-started:.1f}s',flush=True)
    return result


def solve(task):
    digest, job = task
    result = R.solve_one((job,'strict',0))
    result['input_digest'] = digest
    return result


def write_tables(original, aliases, finished):
    output_dir = HERE
    output_dir.mkdir(exist_ok=True)
    for name,table in original.items():
        rows = []
        for old in table.to_dict('records'):
            key = table_key(old)
            result = finished[aliases[key]]
            row = dict(old)
            for field in ['ob_star','lcoe_gen','lcoe_store','lcoe_anc','lcoe_elec','lcoe_gen_floor','ldes_energy_share','P_li','E_li','P_ld','E_ld']:
                row[field] = result['ob'] if field == 'ob_star' else result[field]
            for field in ['unmet_mwh','firm_share','solver_status','solver_message','equality_max_abs_error_mw',
                          'inequality_max_violation_mw','bound_max_violation','objective_usd_yr','elapsed_seconds','input_digest']:
                row[field] = result[field]
            rows.append(row)
        pd.DataFrame(rows).to_csv(output_dir/name,index=False)
    print(f'Wrote 3 complete strict-reliability Fig5 tables to {output_dir}',flush=True)


def main():
    global HERE, ORIGINAL_TABLES
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--workers',type=int,default=18)
    parser.add_argument('--project-root',type=Path,default=R.PROJECT_ROOT)
    parser.add_argument('--output-dir',type=Path,default=HERE)
    args = parser.parse_args()
    R.PROJECT_ROOT = args.project_root.resolve()
    HERE = args.output_dir.resolve()
    HERE.mkdir(parents=True,exist_ok=True)
    R.HERE = HERE
    ORIGINAL_TABLES = R.PROJECT_ROOT/'collective_attention_research_plan/reports/cfe_geographic_portfolio_ai/data_globalsites'
    os.environ['NC_PROJECT_ROOT'] = str(R.PROJECT_ROOT)
    os.environ['NC_STORAGE_OUTPUT'] = str(HERE)
    original,aliases,jobs = prepare_all()
    if args.prepare_only:
        return
    output = HERE/'all_fig5_strict_results.csv'
    finished = {}
    if output.exists():
        for row in pd.read_csv(output,keep_default_na=False).to_dict('records'):
            finished[row['input_digest']] = row
    main_results = HERE/'strict_reliability_2030.csv'
    if main_results.exists():
        for row in pd.read_csv(main_results,keep_default_na=False).to_dict('records'):
            if row['mode'] != 'strict':
                continue
            key = (row['country'],int(row['year']),int(row['tau_ms']),round(float(row['phi']),6))
            if key in aliases:
                row['input_digest'] = aliases[key]
                finished[aliases[key]] = row
    pending = [(digest,job) for digest,job in jobs.items() if digest not in finished]
    started = time.time()
    print(f'Solving {len(pending)} remaining inputs with {args.workers} workers',flush=True)
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(solve,task):task for task in pending}
        for future in concurrent.futures.as_completed(futures):
            row = future.result()
            finished[row['input_digest']] = row
            if len(finished)%16 == 0:
                pd.DataFrame(finished.values()).to_csv(output,index=False)
                print(f'{len(finished)}/{len(jobs)} inputs solved, elapsed {time.time()-started:.1f}s; latest {row["country"]} {row["year"]}',flush=True)
    pd.DataFrame(finished.values()).to_csv(output,index=False)
    write_tables(original,aliases,finished)


if __name__ == '__main__':
    main()
