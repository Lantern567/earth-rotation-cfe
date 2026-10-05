import os
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
import argparse
import concurrent.futures
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
configuration = argparse.ArgumentParser(add_help=False)
configuration.add_argument('--project-root',type=Path,default=Path(os.environ.get('NC_PROJECT_ROOT',Path.cwd())))
configuration.add_argument('--output-dir',type=Path,default=Path(os.environ.get('NC_STORAGE_OUTPUT',SCRIPT_DIR)))
config, _ = configuration.parse_known_args()
PROJECT_ROOT = config.project_root.resolve()
HERE = config.output_dir.resolve()
HERE.mkdir(parents=True,exist_ok=True)
os.environ['NC_PROJECT_ROOT'] = str(PROJECT_ROOT)
os.environ['NC_STORAGE_OUTPUT'] = str(HERE)
SOURCE = PROJECT_ROOT/'collective_attention_research_plan/scripts'
if not SOURCE.is_dir():
    raise FileNotFoundError(f'No scientific scripts directory at {SOURCE}; supply --project-root')
sys.path.insert(0, str(SOURCE))
import run_dispatch_cost_full as F
import storage_dispatch_lp as ORIGINAL
sys.path.insert(0, str(SCRIPT_DIR))
import strict_storage_dispatch as STRICT


def prepare_jobs():
    cached = HERE / 'dispatch_inputs_2030.pkl'
    if cached.exists():
        with cached.open('rb') as handle:
            return pickle.load(handle)
    started = time.time()
    _, demand, _, supply, smeta = F.G.load_inputs_expanded()
    idx = demand[next(iter(demand))]['d'].index
    codes = sorted(c for c in demand if c in smeta)
    reach, receivers = F.A.precompute_reach(codes, smeta)
    nat_shape = {r: F.A.national_shape(supply, r, idx) for r in receivers}
    year = 2030
    li, lt = F.A._ai_share(F.base.AI_SHARE_INFERENCE, year), F.A._ai_share(F.base.AI_SHARE_TRAINING, year)
    ecl, ecd = F.e_costs('central', year)
    jobs = []
    for count, cc in enumerate(codes, 1):
        dp = F.A.perturb('P_mix', F.base.as_arr(demand[cc]['d']).astype(float), F.base.as_arr(demand[cc]['local_hour']).astype(int), li, lt)
        for tau, phi, tier in F.TIERS:
            fh = F.front_half(cc, tau, phi, demand, supply, smeta, reach, nat_shape, idx, dp)
            if fh is None:
                raise ValueError(f'No front-half result for {cc}')
            gen1 = F.P.gen_annual_cost(fh['np_pv'], fh['np_wind'], year, 'central')
            anc1 = F.P.ancillary_annual_cost(fh['gbb'], 'central')
            jobs.append({'cc': cc, 'year': year, 'tau': tau, 'phi': phi, 'tier': tier,
                         'd_mw': fh['d_mw'], 'fit_mw': fh['fit_mw'], 'gen1': gen1, 'anc1': anc1,
                         'ecl': ecl, 'ecd': ecd, 'unc': fh['unc'], 'region': fh['region']})
        if count % 10 == 0:
            print(f'Prepared {count}/{len(codes)} countries in {time.time()-started:.1f}s', flush=True)
    with cached.open('wb') as handle:
        pickle.dump(jobs, handle, protocol=pickle.HIGHEST_PROTOCOL)
    metadata = {'source_root': str(SOURCE.parent.parent), 'countries': codes, 'hours': len(idx),
                'year': year, 'inference_share': li, 'training_share': lt, 'batch_inference_share': 0.25,
                'flexible_energy_fraction': lt + 0.25*li, 'input_precision': 'float32, matching submitted dispatch script',
                'routing_basis': 'country-by-technology', 'refit': 'domestic NNLS after routing before firming',
                'timestamp_start': str(idx.min()), 'timestamp_end': str(idx.max())}
    (HERE / 'inputs_2030.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Prepared all {len(jobs)} inputs in {time.time()-started:.1f}s', flush=True)
    return jobs


def solve_one(task):
    job, mode, deadline = task
    started = time.time()
    d = job['d_mw'].astype(float)
    fit = job['fit_mw'].astype(float)
    args = (d, fit, job['gen1'], job['anc1'], job['ecl'], job['ecd'])
    if mode == 'original_soft':
        result = ORIGINAL.solve_dispatch(*args, rel_target=1.0, cyclic=True)
    elif mode == 'strict':
        result = STRICT.solve_dispatch(*args, rel_target=1.0, cyclic=True)
    elif mode == 'deadline':
        fraction = 0.132 + 0.25*0.308
        result = STRICT.solve_dispatch(*args, rel_target=1.0, cyclic=True,
                                       batch_arrival_mw=fraction*float(d.mean()), deadline_h=deadline,
                                       batch_capacity_multiple=2.0)
    else:
        raise ValueError(mode)
    row = {'country': job['cc'], 'year': job['year'], 'tau_ms': job['tau'], 'phi': job['phi'],
           'tier': job['tier'], 'region': job['region'], 'mode': mode, 'deadline_h': deadline,
           'uncovered_share': job['unc'], 'elapsed_seconds': time.time()-started,
           'lcoe_gen_floor': job['gen1']/float(d.sum())}
    row.update(result)
    if not result['ok']:
        raise RuntimeError(f"Failed {row['country']} {mode} {deadline}: {result}")
    row['pi'] = (row['lcoe_elec'] - row['lcoe_gen'])/row['lcoe_gen']
    return row


def main():
    global HERE, PROJECT_ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['prepare', 'benchmark', 'reliability', 'deadline'], required=True)
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--project-root',type=Path,default=PROJECT_ROOT)
    parser.add_argument('--output-dir',type=Path,default=HERE)
    parser.add_argument('--countries',default='',help='Optional comma-separated country subset for an independent reproduction check')
    options = parser.parse_args()
    PROJECT_ROOT = options.project_root.resolve()
    HERE = options.output_dir.resolve()
    HERE.mkdir(parents=True,exist_ok=True)
    os.environ['NC_PROJECT_ROOT'] = str(PROJECT_ROOT)
    os.environ['NC_STORAGE_OUTPUT'] = str(HERE)
    if SOURCE != PROJECT_ROOT/'collective_attention_research_plan/scripts':
        raise RuntimeError('Project root must be supplied before module loading')
    jobs = prepare_jobs()
    if options.countries:
        selected = {country.strip() for country in options.countries.split(',')}
        if selected.difference(job['cc'] for job in jobs):
            raise ValueError(f'Unknown country subset: {selected}')
        jobs = [job for job in jobs if job['cc'] in selected]
    if options.mode == 'prepare':
        return
    if options.mode == 'benchmark':
        job = next(j for j in jobs if j['cc'] == 'US' and j['tier'] == 'local')
        for mode, deadline in [('strict', 0), ('original_soft', 0), ('deadline', 1), ('deadline', 24)]:
            print(json.dumps(solve_one((job, mode, deadline)), ensure_ascii=False), flush=True)
        return
    if options.mode == 'reliability':
        tasks = [(job, mode, 0) for job in jobs for mode in ['strict', 'original_soft']]
        output = HERE / 'strict_reliability_2030.csv'
    else:
        tasks = [(job, 'deadline', deadline) for job in jobs if job['tier'] == 'local' for deadline in [0, 1, 6, 24]]
        output = HERE / 'batch_deadlines_2030.csv'
    finished = {}
    if output.exists():
        prior = pd.read_csv(output, keep_default_na=False)
        for row in prior.to_dict('records'):
            finished[(row['country'], row['tier'], row['mode'], int(row['deadline_h']))] = row
    pending = [task for task in tasks if (task[0]['cc'], task[0]['tier'], task[1], task[2]) not in finished]
    started = time.time()
    with concurrent.futures.ProcessPoolExecutor(max_workers=options.workers) as pool:
        futures = {pool.submit(solve_one, task): task for task in pending}
        for future in concurrent.futures.as_completed(futures):
            row = future.result()
            finished[(row['country'], row['tier'], row['mode'], row['deadline_h'])] = row
            pd.DataFrame(finished.values()).sort_values(['country','tier','mode','deadline_h']).to_csv(output, index=False)
            if len(finished) % 8 == 0:
                print(f'{len(finished)}/{len(tasks)} solved, {time.time()-started:.1f}s; latest {row["country"]} {row["mode"]} D={row["deadline_h"]}', flush=True)
    print(f'Wrote {output} with {len(finished)} rows', flush=True)


if __name__ == '__main__':
    main()
