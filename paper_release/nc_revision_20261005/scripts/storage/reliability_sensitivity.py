import os
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
import concurrent.futures
import argparse
import time
from pathlib import Path

import pandas as pd

import strict_storage_dispatch as S
import run_storage_revision as R

HERE = R.HERE


def run(task):
    job, target, cyclic = task
    started = time.time()
    result = S.solve_dispatch(job['d_mw'].astype(float),job['fit_mw'].astype(float),job['gen1'],job['anc1'],job['ecl'],job['ecd'],rel_target=target,cyclic=cyclic)
    if not result['ok']:
        raise RuntimeError(f'{job["cc"]} {target} {cyclic}: {result}')
    result.update({'country':job['cc'],'target_service_fraction':target,'annual_soc_cyclic':cyclic,'year':2030,'elapsed_seconds':time.time()-started})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-root',type=Path,default=R.PROJECT_ROOT)
    parser.add_argument('--output-dir',type=Path,default=HERE)
    parser.add_argument('--workers',type=int,default=2)
    args = parser.parse_args()
    jobs = R.prepare_jobs()
    tasks = [(job,target,cyclic) for job in jobs if job['cc'] in ['US','DE','PS'] and job['tier']=='local'
             for target,cyclic in [(1.0,True),(.999,True),(.99,True),(.999,False)]]
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(run,tasks))
    frame = pd.DataFrame(rows)
    frame.to_csv(HERE/'table_s23_reliability.csv',index=False)
    print(frame[['country','target_service_fraction','annual_soc_cyclic','lcoe_elec','firm_share','unmet_mwh','solver_status']].to_string(index=False),flush=True)
