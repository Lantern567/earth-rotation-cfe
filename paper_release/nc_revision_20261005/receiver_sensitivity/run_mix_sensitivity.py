import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
from scipy.optimize import nnls
from threadpoolctl import threadpool_limits


def original_definitions(path, function_names, constant_names, namespace):
    tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    selected = []
    found = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in function_names:
            selected.append(node)
            found.add(node.name)
        elif isinstance(node, ast.Assign):
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if names & set(constant_names):
                selected.append(node)
                found |= names
    assert set(function_names) | set(constant_names) <= found, (path, found)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
    return SimpleNamespace(**namespace)


def load_original_mix_context():
    work = Path(__file__).resolve().parent
    package = work.parents[2] / 'NC返修_20261002/Reproducibility_Package'
    source = package / 'collective_attention_research_plan/scripts'
    base_path = source / 'analyze_cfe_geographic_portfolio_ai.py'
    global_path = source / 'analyze_cfe_global_sites.py'
    routing_path = source / 'analyze_cfe_r3_waveform_cost.py'
    base = original_definitions(base_path,
        ['as_arr', 'equal_energy_align', 'portfolio_nnls', 'supply_basis', 'operator_mix', 'great_circle_km'],
        ['PMIX_ALPHA_BATCH', 'PMIX_ALPHA_INTERACTIVE', 'PMIX_ALPHA_BURST', 'P2_PEAK_HOUR', 'P2_SIGMA_H', 'P3_GAMMA', 'AI_SHARE_INFERENCE', 'AI_SHARE_TRAINING'],
        {'np': np, 'pd': pd, 'nnls': nnls})
    G = original_definitions(global_path, ['_build_supply_from_cf', 'load_inputs_expanded'],
        ['REGION_FROM_CODE', 'HYPERSCALER_EXTENDED'],
        {'np': np, 'pd': pd, 'SITE_DIR': work / 'inputs', 'DEMAND_GLOBAL': work / 'inputs/country_hourly_demand.csv.gz'})
    A = original_definitions(routing_path, ['rtt_ms', 'reach_km', 'precompute_reach', 'national_shape', 'waveform_cover', '_ai_share', 'perturb'], [],
        {'np': np, 'pd': pd, 'base': base, 'G': G, 'TAU': [50, 100, 150, 200, 300, 500], 'SPEED': 200., 'SWITCH': 20., 'WAN': 1.4})
    _, demand, _, supply, smeta = G.load_inputs_expanded()
    idx = demand[next(iter(demand))]['d'].index
    codes = [c for c in demand if c in smeta]
    assert len(codes) == 104 and len(idx) == 8760
    reach39, receivers = A.precompute_reach(codes, smeta)
    assert len(receivers) == 39
    reach34 = {c: {t: [r for r in rs if r not in {'DK', 'EG', 'GR', 'KW', 'TR'}] for t, rs in row.items()} for c, row in reach39.items()}
    shapes = {r: A.national_shape(supply, r, idx) for r in receivers}
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in [base_path, global_path, routing_path]}
    return SimpleNamespace(work=work, package=package, base=base, G=G, A=A, demand=demand, supply=supply, smeta=smeta,
        idx=idx, codes=codes, reach39=reach39, reach34=reach34, shapes=shapes, source_hashes=hashes)


def run():
    started = time.perf_counter()
    work = Path(__file__).resolve().parent
    assert json.loads((work / 'reproduction_check.json').read_text(encoding='utf-8'))['passed']
    with threadpool_limits(limits=1):
        C = load_original_mix_context()
        B = C.base
        rows = []
        means = []
        li, lt = B.AI_SHARE_INFERENCE[2030], B.AI_SHARE_TRAINING[2030]
        # 先完整验证原集合，再允许计算排除五国的结果。
        for version, reach in [(39, C.reach39), (34, C.reach34)]:
            version_started = time.perf_counter()
            for c in C.codes:
                original_d = B.as_arr(C.demand[c]['d']).astype(float)
                lh = B.as_arr(C.demand[c]['local_hour']).astype(int)
                d = C.A.perturb('P_mix', original_d, lh, li, lt)
                if version == 39:
                    means.append({'country': c, 'original_mean': float(original_d.mean()), 'mix_mean': float(d.mean()),
                        'relative_annual_energy_error': float(d.sum() / original_d.sum() - 1)})
                S, _ = B.supply_basis(C.supply, [c], C.idx, fixed=False)
                S1 = B.equal_energy_align(S, float(d.mean()))
                _, share0, fit = B.portfolio_nnls(d, S1)
                resid = np.maximum(d - fit, 0.)
                for tau in [50, 100, 150, 200, 300, 500]:
                    partners = [r for r in reach[c][tau] if C.shapes[r] is not None]
                    P = np.stack([C.shapes[r] for r in partners], axis=1) if partners else None
                    for phi in [0., .2, .4, .6, .8, 1.]:
                        if phi > 0:
                            covered = C.A.waveform_cover(np.minimum(phi * d, resid), P)
                            unc = float((resid - covered).sum() / d.sum())
                        else:
                            unc = share0
                        rows.append({'country': c, 'tau_ms': tau, 'phi': phi, 'uncovered_share': unc,
                            'uncovered_share_baseline': share0, 'n_partners': len(partners), 'receiver_count': version, 'year': 2030})
            table = pd.DataFrame([r for r in rows if r['receiver_count'] == version])
            table.to_csv(work / f'mix2030_grid_{version}.csv', index=False)
            if version == 39:
                reference = pd.read_csv(C.package / 'results/storage/r3_dispatch_grid_2030.csv', keep_default_na=False)
                keys = ['country', 'tau_ms', 'phi']
                left = table.set_index(keys).sort_index()
                right = reference.set_index(keys).sort_index()
                assert left.index.equals(right.index)
                error = float((left.uncovered_share - right.uncovered_share).abs().max())
                check = {'rows': len(table), 'passed': error < 1e-7, 'max_absolute_U_error': error,
                    'reference': str(C.package / 'results/storage/r3_dispatch_grid_2030.csv'),
                    'source_hashes': C.source_hashes, 'seconds': time.perf_counter() - version_started,
                    'execution': 'Original AST function definitions, with module-level filesystem side effects omitted; original function bodies unchanged'}
                (work / 'mix2030_reproduction_check.json').write_text(json.dumps(check, ensure_ascii=False, indent=2), encoding='utf-8')
                assert check['passed'], check
                print('MIX39_REPRODUCTION_PASSED ' + json.dumps(check), flush=True)
            print(f'MIX{version}_COMPLETE seconds={time.perf_counter()-version_started:.1f}', flush=True)
        table = pd.DataFrame(rows)
        medians = table.groupby(['phi', 'tau_ms', 'receiver_count']).uncovered_share.median().unstack('receiver_count') * 100
        medians.columns = ['median_U_39_percent' if c == 39 else 'median_U_34_percent' for c in medians.columns]
        medians['difference_pp'] = medians.median_U_34_percent - medians.median_U_39_percent
        medians.to_csv(work / 'mix2030_heatmap_comparison.csv')
        v39 = table[table.receiver_count.eq(39)]
        v34 = table[table.receiver_count.eq(34)]
        country = v39.merge(v34, on=['country', 'phi', 'tau_ms'], suffixes=('_39', '_34'), validate='one_to_one')
        country['change_pp'] = 100 * (country.uncovered_share_34 - country.uncovered_share_39)
        country.to_csv(work / 'mix2030_country_grid_comparison.csv', index=False)
        global_rows = country[country.phi.eq(1) & country.tau_ms.eq(500)].copy()
        global_rows['absolute_change_pp'] = global_rows.change_pp.abs()
        global_rows.sort_values('absolute_change_pp', ascending=False).head(10).to_csv(work / 'mix2030_top10_global_affected_countries.csv', index=False)
        pd.DataFrame(means).to_csv(work / 'mix2030_annual_energy_check.csv', index=False)
        summary = {'year': 2030, 'countries': 104, 'inference_share': li, 'training_share': lt,
            'domestic_39_median_percent': float(medians.loc[(0., 50), 'median_U_39_percent']),
            'domestic_34_median_percent': float(medians.loc[(0., 50), 'median_U_34_percent']),
            'global_39_median_percent': float(medians.loc[(1., 500), 'median_U_39_percent']),
            'global_34_median_percent': float(medians.loc[(1., 500), 'median_U_34_percent']),
            'max_absolute_heatmap_difference_pp': float(medians.difference_pp.abs().max()),
            'max_absolute_country_difference_pp': float(country.change_pp.abs().max()),
            'global_max_absolute_country_difference_pp': float(global_rows.change_pp.abs().max()),
            'global_34_positive_country_count': int((global_rows.uncovered_share_34 > 0).sum()),
            'max_relative_annual_energy_error': max(abs(r['relative_annual_energy_error']) for r in means),
            'seconds': time.perf_counter() - started}
        (work / 'mix2030_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        for path, digest in C.source_hashes.items():
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
        print('MIX_SENSITIVITY_COMPLETE ' + json.dumps(summary), flush=True)


if __name__ == '__main__':
    run()
