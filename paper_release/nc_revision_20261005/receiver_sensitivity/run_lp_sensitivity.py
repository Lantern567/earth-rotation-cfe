import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

work = Path(__file__).resolve().parent
root = work.parents[2]
package = root / 'NC返修_20261002/Reproducibility_Package'
digest = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert json.loads((work / 'reproduction_check.json').read_text(encoding='utf-8'))['passed']
script = package / 'scripts/waveform/run_waveform_revision.py'
spec = importlib.util.spec_from_file_location('receiver_waveform_original_lp', script)
W = importlib.util.module_from_spec(spec)
spec.loader.exec_module(W)
frozen_path = package / 'results/waveform/objective_results.csv'
frozen = pd.read_csv(frozen_path, keep_default_na=False).set_index('country')
excluded = {'DK', 'EG', 'GR', 'KW', 'TR'}
rows, certificates, fingerprints = [], [], {}
started = time.perf_counter()
with threadpool_limits(limits=1):
    for ci, country in enumerate(sorted(frozen.index)):
        path = package / f'results/waveform/certificates/{country}.npz'
        fingerprints[country] = {'path': str(path), 'sha256': digest(path)}
        with np.load(path, allow_pickle=False) as arrays:
            d = arrays['d']
            domestic = arrays['domestic_basis']
            r_nnls = arrays['r_nnls']
            r_unit = arrays['r_unit']
            lp_unit = arrays['lp_r_unit']
            partners = arrays['partners'].astype(str)
            full_basis = arrays['partner_basis']
            cached_home_nnls = domestic @ arrays['domestic_nnls_weights']
            cached_home_lp = domestic @ arrays['domestic_lp_primal'][:domestic.shape[1]]
            E = float(d.sum())
            assert np.max(np.abs(np.maximum(d - cached_home_nnls, 0) - r_nnls)) < 1e-10
            R = float(r_nnls.sum())
            R_lp = float(np.maximum(d - cached_home_lp, 0).sum())
            assert abs(R / E - frozen.loc[country, 'dom_nnls']) < 1e-10
            assert abs(R_lp / E - frozen.loc[country, 'dom_lp']) < 1e-8
            assert np.max(np.abs(np.maximum(d - cached_home_lp, 0) / (R_lp / len(d)) - lp_unit)) < 1e-7
            cached_routing = full_basis @ arrays['primal'][:full_basis.shape[1]]
            cached_pipeline = full_basis @ arrays['lp_routing_primal'][:full_basis.shape[1]]
            fixed39 = R / E * float(np.maximum(r_unit - cached_routing, 0).sum() / r_unit.sum())
            pipe39 = R_lp / E * float(np.maximum(lp_unit - cached_pipeline, 0).sum() / lp_unit.sum())
            assert abs(fixed39 - frozen.loc[country, 'rt_lp_fixed_nnls_residual']) < 1e-8
            assert abs(pipe39 - frozen.loc[country, 'rt_lp_pipeline']) < 1e-8
            keep = np.array([r not in excluded for r in partners])
            matrix = full_basis[:, keep]
            fixed_fit, fixed_metrics, fixed_solution = W.direct_lp(r_unit, matrix)
            pipeline_fit, pipe_metrics, pipe_solution = W.direct_lp(lp_unit, matrix)
            rho_fixed = float(np.maximum(r_unit - fixed_fit, 0).sum() / r_unit.sum())
            rho_pipe = float(np.maximum(lp_unit - pipeline_fit, 0).sum() / lp_unit.sum())
            fixed34 = R / E * rho_fixed
            pipe34 = R_lp / E * rho_pipe
            assert fixed34 >= fixed39 - 1e-8, country
            assert pipe34 >= pipe39 - 1e-8, country
            rows.append({'country': country, 'n_partners_39': len(partners), 'n_partners_34': int(keep.sum()), 'E': E, 'R_nnls': R, 'R_lp': R_lp, 'dom_nnls': R / E, 'dom_lp': R_lp / E, 'rt_lp_fixed_39': fixed39, 'rt_lp_fixed_34': fixed34, 'fixed_change_pp': 100 * (fixed34 - fixed39), 'rho_fixed_34': rho_fixed, 'rt_lp_pipeline_39': pipe39, 'rt_lp_pipeline_34': pipe34, 'pipeline_change_pp': 100 * (pipe34 - pipe39), 'rho_pipeline_34': rho_pipe})
            certificates.extend([{'country': country, 'stage': 'same_domestic_nnls_shortfall_34', **fixed_metrics}, {'country': country, 'stage': 'same_domestic_lp_shortfall_34', **pipe_metrics}])
            save = work / 'lp_certificates_34'
            save.mkdir(exist_ok=True)
            np.savez_compressed(save / f'{country}.npz', partners=partners[keep], fixed_routing_primal=fixed_solution.x, fixed_dual_inequality=fixed_solution.ineqlin.marginals, fixed_dual_equality=fixed_solution.eqlin.marginals, fixed_dual_lower=fixed_solution.lower.marginals, pipeline_routing_primal=pipe_solution.x, pipeline_dual_inequality=pipe_solution.ineqlin.marginals, pipeline_dual_equality=pipe_solution.eqlin.marginals, pipeline_dual_lower=pipe_solution.lower.marginals)
        if ci == 0 or (ci + 1) % 10 == 0:
            print(f'LP34 {ci+1}/104 seconds={time.perf_counter()-started:.1f}', flush=True)
            pd.DataFrame(rows).to_csv(work / 'lp_country_comparison.csv', index=False)
            pd.DataFrame(certificates).to_csv(work / 'lp_numerical_certificates.csv', index=False)
        if time.perf_counter() - started > 3500:
            raise TimeoutError('LP item exceeded the one-hour budget; partial country results saved.')
frame = pd.DataFrame(rows)
cert = pd.DataFrame(certificates)
assert len(frame) == 104 and len(cert) == 208
assert frame.rt_lp_fixed_34.gt(0).all() and frame.rt_lp_pipeline_34.gt(0).all()
frame.to_csv(work / 'lp_country_comparison.csv', index=False)
cert.to_csv(work / 'lp_numerical_certificates.csv', index=False)
summary = {'countries': 104, 'new_routing_lp_solves': 208, 'domestic_lp_reused': 'Exact unchanged first-stage solution verified against saved hourly arrays; receiver exclusions cannot change the domestic optimum', 'baseline_cached_routing_solutions_verified': True, 'same_shortfall_39_median_percent': float(frame.rt_lp_fixed_39.median() * 100), 'same_shortfall_34_median_percent': float(frame.rt_lp_fixed_34.median() * 100), 'pipeline_39_median_percent': float(frame.rt_lp_pipeline_39.median() * 100), 'pipeline_34_median_percent': float(frame.rt_lp_pipeline_34.median() * 100), 'same_shortfall_34_minimum_percent': float(frame.rt_lp_fixed_34.min() * 100), 'pipeline_34_minimum_percent': float(frame.rt_lp_pipeline_34.min() * 100), 'same_shortfall_positive_country_count': int(frame.rt_lp_fixed_34.gt(0).sum()), 'pipeline_positive_country_count': int(frame.rt_lp_pipeline_34.gt(0).sum()), 'fixed_max_increase_pp': float(frame.fixed_change_pp.max()), 'pipeline_max_increase_pp': float(frame.pipeline_change_pp.max()), 'certificate_max': {column: float(cert[column].max()) for column in cert.columns if column not in ('country', 'stage')}, 'seconds': time.perf_counter() - started, 'original_script_sha256': digest(script), 'original_objective_csv_sha256': digest(frozen_path)}
(work / 'lp_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
(work / 'lp_input_certificates.json').write_text(json.dumps(fingerprints, ensure_ascii=False, indent=2), encoding='utf-8')
print('LP_SENSITIVITY_COMPLETE ' + json.dumps(summary), flush=True)
