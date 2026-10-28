import concurrent.futures
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pickle
import sys
import time

os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from run_mix_sensitivity import load_original_mix_context, original_definitions


def source_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def solve_one(job):
    work = Path(__file__).resolve().parent
    package = work.parents[2] / 'NC返修_20261002/Reproducibility_Package'
    strict = source_module(package / 'scripts/storage/strict_storage_dispatch.py', 'original_strict_dispatch_receiver_check')
    started = time.perf_counter()
    with threadpool_limits(limits=1):
        result = strict.solve_dispatch(job['d_mw'].astype(float), job['fit_mw'].astype(float),
            job['gen1'], job['anc1'], job['ecl'], job['ecd'], rel_target=1.0, cyclic=True)
    assert result['ok'] and result['solver_status'] == 0, (job['cc'], result)
    assert result['unmet_mwh'] == 0, (job['cc'], result)
    return {'country': job['cc'], 'tau_ms': 500, 'phi': 1., 'year': 2030, 'uncovered_share': job['unc'],
        'elapsed_seconds': time.perf_counter() - started, **result}


def main():
    started = time.perf_counter()
    work = Path(__file__).resolve().parent
    assert json.loads((work / 'mix2030_reproduction_check.json').read_text(encoding='utf-8'))['passed']
    with threadpool_limits(limits=1):
        C = load_original_mix_context()
        source = C.package / 'collective_attention_research_plan/scripts'
        P = source_module(source / 'fullsystem_cost_params.py', 'original_cost_parameters_receiver_check')
        front = original_definitions(source / 'run_dispatch_cost_full.py', ['front_half', 'e_costs'], [],
            {'np': np, 'pd': pd, 'base': C.base, 'A': C.A, 'P': P})
        cache_path = work.parents[2] / 'work/nc_revision_20261002/storage/dispatch_inputs_2030.pkl'
        with cache_path.open('rb') as handle:
            cached = pickle.load(handle)
        cached = {(j['cc'], j['tau'], j['phi']): j for j in cached if j['year'] == 2030}
        reference_path = C.package / 'results/storage/r3_dispatch_grid_2030.csv'
        reference = pd.read_csv(reference_path, keep_default_na=False)
        frozen_global = reference[reference.tau_ms.eq(500) & reference.phi.eq(1)].set_index('country')
        frozen_local = reference[reference.tau_ms.eq(50) & reference.phi.eq(0)].set_index('country')
        jobs = []
        checks = []
        ecl, ecd = front.e_costs('central', 2030)
        for c in C.codes:
            dp = C.A.perturb('P_mix', C.base.as_arr(C.demand[c]['d']).astype(float),
                C.base.as_arr(C.demand[c]['local_hour']).astype(int), .308, .132)
            fh39 = front.front_half(c, 500, 1., C.demand, C.supply, C.smeta, C.reach39, C.shapes, C.idx, dp)
            fh34 = front.front_half(c, 500, 1., C.demand, C.supply, C.smeta, C.reach34, C.shapes, C.idx, dp)
            j39 = cached[(c, 500, 1.)]
            gen39 = P.gen_annual_cost(fh39['np_pv'], fh39['np_wind'], 2030, 'central')
            anc39 = P.ancillary_annual_cost(fh39['gbb'], 'central')
            errors = {'d_mw_error': float(np.max(np.abs(fh39['d_mw'] - j39['d_mw']))),
                'fit_mw_error': float(np.max(np.abs(fh39['fit_mw'] - j39['fit_mw']))),
                'gen1_error': abs(gen39 - j39['gen1']), 'anc1_error': abs(anc39 - j39['anc1']),
                'ecl_error': abs(ecl - j39['ecl']), 'ecd_error': abs(ecd - j39['ecd']),
                'unc_error': abs(fh39['unc'] - float(frozen_global.loc[c, 'uncovered_share']))}
            assert max(errors.values()) < 1e-6, (c, errors)
            checks.append({'country': c, **errors,
                'd34_vs_d39_max_abs_MW': float(np.max(np.abs(fh34['d_mw'] - fh39['d_mw']))),
                'fit34_vs_fit39_max_abs_MW': float(np.max(np.abs(fh34['fit_mw'] - fh39['fit_mw'])))})
            jobs.append({'cc': c, **fh34,
                'gen1': P.gen_annual_cost(fh34['np_pv'], fh34['np_wind'], 2030, 'central'),
                'anc1': P.ancillary_annual_cost(fh34['gbb'], 'central'), 'ecl': ecl, 'ecd': ecd})
        pd.DataFrame(checks).to_csv(work / 'storage2030_front_half_validation.csv', index=False)
        with (work / 'storage2030_global_jobs_34.pkl').open('wb') as handle:
            pickle.dump(jobs, handle, protocol=pickle.HIGHEST_PROTOCOL)
        timing = frozen_global.elapsed_seconds
        # 只重算主要全球角点；国内角点完全不受 receiver 集合影响。
        estimate = {'global_104_serial_seconds_from_saved_runs': float(timing.sum()),
            'full_grid_3744_serial_seconds_from_saved_runs': float(reference.elapsed_seconds.sum()),
            'workers': 4, 'global_104_rough_parallel_seconds': float(timing.sum() / 4),
            'cached_input_path': str(cache_path), 'cached_input_sha256': hashlib.sha256(cache_path.read_bytes()).hexdigest(),
            'reference_path': str(reference_path), 'reference_sha256': hashlib.sha256(reference_path.read_bytes()).hexdigest(),
            'scope': '104 new global corner strict hourly dispatch solves; unchanged local corner reused',
            'front_half_max_errors': pd.DataFrame(checks).filter(regex='_error$').max().to_dict()}
        assert estimate['global_104_rough_parallel_seconds'] < 3300, estimate
        (work / 'storage2030_plan.json').write_text(json.dumps(estimate, ensure_ascii=False, indent=2), encoding='utf-8')
        print('STORAGE_FRONT_HALF_VERIFIED ' + json.dumps(estimate), flush=True)
    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(solve_one, job): job['cc'] for job in jobs}
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            if len(results) == 1 or len(results) % 10 == 0:
                pd.DataFrame(results).sort_values('country').to_csv(work / 'storage2030_global_34.csv', index=False)
                print(f'STORAGE34 {len(results)}/104 seconds={time.perf_counter()-started:.1f}', flush=True)
            assert time.perf_counter() - started < 3500, 'Single-item one-hour budget reached'
    reduced = pd.DataFrame(results).sort_values('country').set_index('country')
    reduced.to_csv(work / 'storage2030_global_34.csv')
    compare = frozen_global.add_suffix('_39').join(reduced.add_suffix('_34'), validate='one_to_one')
    compare['pi_39_percent'] = 100 * (compare.lcoe_elec_39 - compare.lcoe_gen_39) / compare.lcoe_gen_39
    compare['pi_34_percent'] = 100 * (compare.lcoe_elec_34 - compare.lcoe_gen_34) / compare.lcoe_gen_34
    compare['pi_change_pp'] = compare.pi_34_percent - compare.pi_39_percent
    compare['total_cost_change_USD_per_MWh'] = compare.lcoe_elec_34 - compare.lcoe_elec_39
    compare.to_csv(work / 'storage2030_global_comparison.csv')
    local_pi = float((100 * (frozen_local.lcoe_elec - frozen_local.lcoe_gen) / frozen_local.lcoe_gen).median())
    result = {'countries': len(reduced), 'year': 2030, 'global_new_solves': len(reduced),
        'domestic_median_firming_premium_percent_39_and_34': local_pi,
        'global_39_median_firming_premium_percent': float(compare.pi_39_percent.median()),
        'global_34_median_firming_premium_percent': float(compare.pi_34_percent.median()),
        'global_39_median_total_cost_USD_per_MWh': float(compare.lcoe_elec_39.median()),
        'global_34_median_total_cost_USD_per_MWh': float(compare.lcoe_elec_34.median()),
        'global_39_median_storage_cost_USD_per_MWh': float(compare.lcoe_store_39.median()),
        'global_34_median_storage_cost_USD_per_MWh': float(compare.lcoe_store_34.median()),
        'global_max_absolute_country_premium_change_pp': float(compare.pi_change_pp.abs().max()),
        'all_full_hourly_supply': bool(reduced.unmet_mwh.eq(0).all()),
        'maximum_equality_error_MW': float(reduced.equality_max_abs_error_mw.max()),
        'maximum_inequality_violation_MW': float(reduced.inequality_max_violation_mw.max()),
        'maximum_bound_violation': float(reduced.bound_max_violation.max()),
        'seconds': time.perf_counter() - started,
        'source_hashes': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [source / 'run_dispatch_cost_full.py', source / 'fullsystem_cost_params.py', C.package / 'scripts/storage/strict_storage_dispatch.py']}}
    (work / 'storage2030_summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('STORAGE_SENSITIVITY_COMPLETE ' + json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
