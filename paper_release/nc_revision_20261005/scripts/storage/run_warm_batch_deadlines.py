import os
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
import argparse
import concurrent.futures
import time
from pathlib import Path

import pandas as pd

import run_storage_revision as R
import strict_storage_dispatch as S

HERE = R.HERE


def run_country(job):
    rows = []
    basis = None
    for deadline in [0,1,6,24]:
        started = time.time()
        d = job['d_mw'].astype(float)
        flexible = (0.132 + 0.25*0.308)*float(d.mean())
        result = S.solve_dispatch(d,job['fit_mw'].astype(float),job['gen1'],job['anc1'],job['ecl'],job['ecd'],
                                  batch_arrival_mw=flexible,deadline_h=deadline,batch_capacity_multiple=2.0,
                                  lp_method='highspy',warm_basis=basis,return_basis=True)
        if not result['ok']:
            raise RuntimeError(f'{job["cc"]} deadline {deadline}: {result}')
        basis = result.pop('_basis')
        if result['unmet_mwh'] != 0.0 or result['batch_energy_error_mwh']>1e-6 or result['equality_max_abs_error_mw']>1e-6:
            raise ArithmeticError(f'Invalid batch solution {job["cc"]}: {result}')
        result.update({'country':job['cc'],'tier':'local','year':2030,'deadline_h':deadline,'elapsed_seconds':time.time()-started,
                       'batch_capacity_multiple':2.0,'flexible_energy_fraction':0.209})
        result['pi'] = (result['lcoe_elec']-result['lcoe_gen'])/result['lcoe_gen']
        rows.append(result)
    for earlier,later in zip(rows,rows[1:]):
        if later['objective_usd_yr']>earlier['objective_usd_yr']+0.1:
            raise ArithmeticError(f'Cost increased for wider deadline in {job["cc"]}')
    return rows


def main():
    global HERE
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers',type=int,default=6)
    parser.add_argument('--project-root',type=Path,default=R.PROJECT_ROOT)
    parser.add_argument('--output-dir',type=Path,default=HERE)
    args = parser.parse_args()
    R.PROJECT_ROOT = args.project_root.resolve()
    HERE = args.output_dir.resolve()
    HERE.mkdir(parents=True,exist_ok=True)
    R.HERE = HERE
    os.environ['NC_PROJECT_ROOT'] = str(R.PROJECT_ROOT)
    os.environ['NC_STORAGE_OUTPUT'] = str(HERE)
    jobs = [job for job in R.prepare_jobs() if job['tier']=='local']
    output = HERE/'batch_deadlines_2030.csv'
    rows = []
    complete = set()
    if output.exists():
        prior = pd.read_csv(output,keep_default_na=False)
        for country,part in prior.groupby('country'):
            if set(part.deadline_h)=={0,1,6,24}:
                rows.extend(part.to_dict('records'))
                complete.add(country)
    tasks = [job for job in jobs if job['cc'] not in complete]
    started = time.time()
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_country,job):job for job in tasks}
        for future in concurrent.futures.as_completed(futures):
            country_rows = future.result()
            rows.extend(country_rows)
            pd.DataFrame(rows).sort_values(['country','deadline_h']).to_csv(output,index=False)
            print(f'{len(rows)}/416 rows completed; latest {country_rows[0]["country"]}; elapsed {time.time()-started:.1f}s',flush=True)
    print(f'Wrote {output}',flush=True)


if __name__ == '__main__':
    main()
