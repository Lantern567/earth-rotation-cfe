import argparse
import hashlib
import importlib.util
import json
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from threadpoolctl import threadpool_limits


ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT.parents[1] / 'NC返修_20261002/Reproducibility_Package'
STATIC = [('base', 0.), ('static10', .1), ('static25', .25), ('static50', .5), ('static75', .75), ('flat100', 1.)]
DAILY = [('daily10', .1), ('daily25', .25), ('daily50', .5), ('daily75', .75)]
CASES = dict(STATIC + DAILY)
DEFAULT_LP = ['base', 'static25', 'static50', 'daily25', 'daily50', 'flat100']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def load_waveform(args):
    spec = importlib.util.spec_from_file_location('retained_waveform', args.waveform_script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.configure(SimpleNamespace(project_root=None, data_root=args.data_root, output_dir=args.output_dir,
        reference_dir=None, consumer_profile=None, window_metadata=None, raw_cache=None))
    return module, module.load_data()


def profile(d, name):
    beta = CASES[name]
    interactive = (1 - beta) * d
    background = np.full_like(d, beta)
    capacity = float(interactive.max() + beta)
    pool_error = 0.
    if name.startswith('daily'):
        for start in range(0, len(d), 24):
            load = interactive[start:start + 24]
            room = capacity - load
            target = beta * len(load)
            balance = lambda level: float(np.clip(level - load, 0., room).sum() - target)
            lower, upper = float(load.min()), capacity
            if abs(balance(upper)) <= 1e-12:
                level = upper
            else:
                level = brentq(balance, lower, upper, xtol=1e-12, rtol=1e-14)
            background[start:start + 24] = np.clip(level - load, 0., room)
            pool_error = max(pool_error, abs(float(background[start:start + 24].sum()) - target))
    total = interactive + background
    validation = {
        'beta': beta, 'execution_capacity': capacity, 'annual_energy': float(total.sum()),
        'annual_energy_relative_error': abs(float(total.sum() / d.sum()) - 1.),
        'background_pool_max_error': pool_error,
        'capacity_violation': float(max(0., (total - capacity).max())),
        'background_min': float(background.min()),
        'demand_coefficient_of_variation': float(total.std() / total.mean())}
    if validation['annual_energy_relative_error'] > 1e-10 or pool_error > 1e-8 or validation['capacity_violation'] > 1e-10:
        raise ValueError(f'Invalid profile {name}: {validation}')
    return total, interactive, validation


def baseline(W, c, d, home, partner, folder):
    path = folder / f'{c}.npz'
    if path.exists():
        with np.load(path, allow_pickle=False) as item:
            values = {key: item[key].copy() for key in item.files}
        if not np.array_equal(values['d'], d):
            raise ValueError(f'Baseline demand changed: {c}')
        return values
    local = W.fit_nnls(d, home)[1]
    residual = np.maximum(d - local, 0.)
    route = W.fit_nnls(residual, partner)[1] if residual.sum() > 0 else np.zeros_like(d)
    values = {'d': d, 'domestic': local, 'partner_nnls': route}
    np.savez_compressed(path, **values)
    return values


def route_nnls(W, d, residual, eligible, partner, energy):
    fit = W.fit_nnls(eligible, partner, energy=energy)[1] if eligible.sum() > 0 and energy > 0 else np.zeros_like(d)
    covered = np.minimum(eligible, fit)
    return float((residual - covered).sum() / d.sum()), fit


def summaries(country, routes, scales, output):
    cdf = pd.DataFrame(country)
    rdf = pd.DataFrame(routes)
    sdf = pd.DataFrame(scales)
    if not cdf.empty:
        cdf = cdf.drop_duplicates(['country', 'case'], keep='last').sort_values(['case', 'country'])
        cdf.to_csv(output / 'country_results.csv', index=False)
        records = []
        base = cdf[cdf['case'].eq('base')].set_index('country')
        for name, group in cdf.groupby('case', sort=False):
            for field in ['domestic_uncovered_share', 'entirely_frozen_nnls_share', 'entirely_frozen_lp_supply_share', 'demand_coefficient_of_variation']:
                if field not in group or not group[field].notna().any():
                    continue
                values = group[field].dropna()
                record = {'case': name, 'metric': field, 'n': len(values), 'median': float(values.median()),
                    'q25': float(values.quantile(.25)), 'q75': float(values.quantile(.75)),
                    'min': float(values.min()), 'max': float(values.max()), 'positive_count': int((values > 1e-10).sum())}
                if field in base:
                    paired = group.set_index('country')[field] - base[field]
                    paired = paired.dropna()
                    if len(paired):
                        record.update(paired_change_median_pp=float(paired.median() * 100),
                            paired_change_q25_pp=float(paired.quantile(.25) * 100), paired_change_q75_pp=float(paired.quantile(.75) * 100))
                records.append(record)
        pd.DataFrame(records).to_csv(output / 'case_summary.csv', index=False)
    if not rdf.empty:
        keys = ['country', 'case', 'method', 'budget', 'scope']
        rdf = rdf.drop_duplicates(keys, keep='last').sort_values(keys)
        rdf.to_csv(output / 'routing_results.csv', index=False)
        records = []
        for (name, method, budget, scope), group in rdf.groupby(['case', 'method', 'budget', 'scope']):
            values = group['annual_uncovered_share']
            base = rdf[rdf['case'].eq('base') & rdf.method.eq(method) & rdf.budget.eq(budget) & rdf.scope.eq(scope)].set_index('country')
            changes = (group.set_index('country')['annual_uncovered_share'] - base['annual_uncovered_share']).dropna()
            record = {'case': name, 'method': method, 'budget': budget, 'scope': scope, 'n': len(group),
                'median_pct': float(values.median() * 100), 'q25_pct': float(values.quantile(.25) * 100),
                'q75_pct': float(values.quantile(.75) * 100), 'min_pct': float(values.min() * 100),
                'max_pct': float(values.max() * 100), 'positive_count': int((values > 1e-10).sum())}
            if len(changes):
                record.update(paired_change_median_pp=float(changes.median() * 100),
                    paired_change_q25_pp=float(changes.quantile(.25) * 100), paired_change_q75_pp=float(changes.quantile(.75) * 100),
                    maximum_absolute_change_pp=float(changes.abs().max() * 100))
            records.append(record)
        pd.DataFrame(records).to_csv(output / 'routing_summary.csv', index=False)
    if not sdf.empty:
        sdf = sdf.drop_duplicates(['country', 'alpha'], keep='last').sort_values(['alpha', 'country'])
        sdf.to_csv(output / 'request_scale_control.csv', index=False)
        sdf.groupby('alpha').agg(n=('country', 'count'), domestic_median=('domestic_uncovered_share', 'median'),
            routed_median=('routed_uncovered_share', 'median'), domestic_max_error=('domestic_share_error', 'max'),
            routed_max_error=('routed_share_error', 'max')).reset_index().to_csv(output / 'request_scale_summary.csv', index=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root', type=Path, default=ARCHIVE / 'inputs/hourly')
    parser.add_argument('--waveform-script', type=Path, default=ARCHIVE / 'scripts/waveform/run_waveform_revision.py')
    parser.add_argument('--archive-results', type=Path, default=ARCHIVE / 'results/waveform/objective_results.csv')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--pilot', action='store_true')
    parser.add_argument('--nnls-only', action='store_true')
    parser.add_argument('--lp-cases', nargs='+', default=DEFAULT_LP)
    args = parser.parse_args()
    args.output_dir = (args.output_dir or ROOT / ('pilot_results' if args.pilot else 'results')).resolve()
    args.data_root = args.data_root.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    folder = args.output_dir / 'baseline_supply_arrays'
    folder.mkdir(exist_ok=True)
    start = time.perf_counter()
    fingerprint = {'waveform_script_sha256': digest(args.waveform_script), 'archive_results_sha256': digest(args.archive_results),
        'hourly_inputs': {name: digest(args.data_root / name) for name in ['country_hourly_demand.csv.gz', 'site_hourly_cf.parquet', 'country_meta.csv']},
        'cases': CASES, 'capacity_rule': 'max((1-beta)*d) + beta, fixed across the entire country year',
        'pool_rule': 'beta*24 per complete contiguous UTC day', 'routing_budgets': ['current_R', 'fixed_R0'],
        'restricted_eligibility': 'minimum(interactive increment, domestic shortfall); both budget rules retain their stated total shortfall energy'}
    manifest = args.output_dir / 'input_fingerprint.json'
    if manifest.exists() and json.loads(manifest.read_text(encoding='utf-8')) != fingerprint:
        raise ValueError('Input or experiment definition changed; choose a new output directory')
    write_json(manifest, fingerprint)
    W, inputs = load_waveform(args)
    idx, countries, demands, homes, shapes, hours, reach, meta = inputs
    if len(idx) != 8760 or idx[0].hour != 0 or any((idx[i + 1] - idx[i]).total_seconds() != 3600 for i in range(len(idx) - 1)):
        raise ValueError('Expected 8760 consecutive hours starting at UTC midnight')
    countries = ['US', 'DE', 'IN'] if args.pilot else countries
    names = ['base'] if args.pilot else list(CASES)
    lp_names = ['base'] if args.pilot else [x for part in args.lp_cases for x in part.split(',')]
    if not set(lp_names).issubset(CASES):
        raise ValueError(f'Unknown LP cases: {lp_names}')
    print(f'Loaded {len(countries)} countries; {len(idx)} hours; elapsed {time.perf_counter()-start:.2f}s', flush=True)
    archived = pd.read_csv(args.archive_results, keep_default_na=False).set_index('country')
    paths = {'country': args.output_dir / 'country_results.csv', 'routes': args.output_dir / 'routing_results.csv',
        'scales': args.output_dir / 'request_scale_control.csv', 'certs': args.output_dir / 'lp_solver_metrics.csv'}
    retained = {key: pd.read_csv(path, keep_default_na=False, na_values=['']).to_dict('records') if path.exists() else [] for key, path in paths.items()}
    country_rows, route_rows, scale_rows, cert_rows = (retained[k] for k in ['country', 'routes', 'scales', 'certs'])
    complete = {(x['country'], x['case']) for x in country_rows}
    scale_complete = {(x['country'], float(x['alpha'])) for x in scale_rows}
    base_cache = {}
    base_errors = []
    with threadpool_limits(limits=1):
        for ci, c in enumerate(countries):
            d, home = demands[c], homes[c]
            partner = np.column_stack([shapes[r] for r in reach[c][500]])
            base = baseline(W, c, d, home, partner, folder)
            base_cache[c] = base
            residual0 = np.maximum(d - base['domestic'], 0.)
            R0 = float(residual0.sum())
            base_u = float(np.maximum(residual0 - base['partner_nnls'], 0.).sum() / d.sum())
            base_dom = float(R0 / d.sum())
            base_errors.append({'country': c, 'domestic_error': abs(base_dom - archived.loc[c, 'dom_nnls']),
                'routing_nnls_error': abs(base_u - archived.loc[c, 'rt_nnls'])})
            for name in names:
                if (c, name) in complete:
                    continue
                D, interactive, checks = profile(d, name)
                local = base['domestic'] if name == 'base' else W.fit_nnls(D, home)[1]
                residual = np.maximum(D - local, 0.)
                R = float(residual.sum())
                row = {'country': c, 'case': name, **checks, 'R': R, 'R0': R0,
                    'domestic_uncovered_share': R / float(D.sum()),
                    'entirely_frozen_nnls_share': float(np.maximum(D - base['domestic'] - base['partner_nnls'], 0.).sum() / D.sum())}
                if 'partner_lp' in base:
                    row['entirely_frozen_lp_supply_share'] = float(np.maximum(D - base['domestic'] - base['partner_lp'], 0.).sum() / D.sum())
                country_rows.append(row)
                for budget, energy in [('current_R', R), ('fixed_R0', R0)]:
                    for scope, eligible in [('upper', residual), ('restricted', np.minimum(interactive, residual))]:
                        u, fit = route_nnls(W, D, residual, eligible, partner, energy)
                        route_rows.append({'country': c, 'case': name, 'method': 'NNLS', 'budget': budget, 'scope': scope,
                            'annual_uncovered_share': u, 'annual_energy': float(D.sum()), 'domestic_shortfall_energy': R,
                            'eligible_shortfall_energy': float(eligible.sum()), 'partner_energy_budget': energy,
                            'partner_fit_energy': float(fit.sum()), 'fixed_unroutable_energy': float((residual - eligible).sum())})
            if not args.pilot:
                for alpha in [1., 2., 5., 10.]:
                    if (c, alpha) in scale_complete:
                        continue
                    scaled = alpha * d
                    local = W.fit_nnls(scaled, home)[1]
                    residual = np.maximum(scaled - local, 0.)
                    fit = W.fit_nnls(residual, partner)[1] if residual.sum() > 0 else np.zeros_like(d)
                    domestic_share = float(residual.sum() / scaled.sum())
                    routed_share = float(np.maximum(residual - fit, 0.).sum() / scaled.sum())
                    scale_rows.append({'country': c, 'alpha': alpha, 'annual_demand_energy': float(scaled.sum()),
                        'domestic_supply_energy': float(local.sum()), 'partner_supply_energy': float(fit.sum()),
                        'domestic_uncovered_share': domestic_share, 'routed_uncovered_share': routed_share,
                        'domestic_share_error': abs(domestic_share - base_dom), 'routed_share_error': abs(routed_share - base_u),
                        'domestic_supply_scaling_error': abs(float(local.sum() / (alpha * d.sum())) - 1.),
                        'partner_supply_scaling_error': abs(float(fit.sum() / (alpha * R0)) - 1.) if R0 else 0.})
            print(f'NNLS {ci+1}/{len(countries)} {c}; elapsed {time.perf_counter()-start:.2f}s', flush=True)
            if (ci + 1) % 10 == 0 or ci + 1 == len(countries):
                summaries(country_rows, route_rows, scale_rows, args.output_dir)
        nnls_seconds = time.perf_counter() - start
        base_max = {key: max(x[key] for x in base_errors) for key in ['domestic_error', 'routing_nnls_error']}
        if max(base_max.values()) > 1e-8:
            raise ValueError(f'Archived NNLS baseline differs: {base_max}')
        write_json(args.output_dir / 'nnls_validation.json', {'status': 'passed', 'countries': len(countries),
            'case_count': len(names), 'country_case_rows': len(country_rows), 'archived_baseline_max_errors': base_max,
            'elapsed_seconds': nnls_seconds, 'newly_solved_power_or_storage_models': False})
        print(f'NNLS STAGE COMPLETE {nnls_seconds:.2f}s; archived max errors {base_max}', flush=True)
        if args.nnls_only:
            return
        solved = {(x['country'], x['case'], x['budget']) for x in cert_rows}
        solve_times = []
        for ci, c in enumerate(countries):
            d, home, base = demands[c], homes[c], base_cache[c]
            partner = np.column_stack([shapes[r] for r in reach[c][500]])
            R0 = float(np.maximum(d - base['domestic'], 0.).sum())
            for name in lp_names:
                D, interactive, checks = profile(d, name)
                local = base['domestic'] if name == 'base' else W.fit_nnls(D, home)[1]
                residual = np.maximum(D - local, 0.)
                R = float(residual.sum())
                same_budget_fit = None
                for budget, energy in [('current_R', R), ('fixed_R0', R0)]:
                    if (c, name, budget) in solved:
                        continue
                    tick = time.perf_counter()
                    if name == 'base' and same_budget_fit is not None:
                        fit, metrics = same_budget_fit
                        seconds = 0.
                    else:
                        mean = float(residual.mean())
                        if mean <= 0:
                            raise ValueError(f'Zero new shortfall requires explicit certificate handling: {c}/{name}')
                        fitted, metrics, solution = W.direct_lp(residual / mean, partner, energy=energy / mean)
                        fit = fitted * mean
                        metrics = {**metrics, 'lp_mean_scale': mean, 'raw_primal_objective': metrics['primal_objective'] * mean,
                            'raw_dual_objective': metrics['dual_objective'] * mean}
                        feasibility = max(metrics[key] for key in ['primal_inequality_violation', 'primal_equality_violation', 'primal_bound_violation'])
                        if feasibility > 1e-7 or metrics['duality_gap_relative'] > 1e-8 or metrics['duality_gap_absolute'] > 1e-5:
                            raise ValueError(f'LP independent feasibility/duality check failed: {c}/{name}/{budget}: {metrics}')
                        if max(metrics['dual_reduced_cost_violation'], metrics['dual_stationarity_violation'], metrics['dual_sign_violation']) > 1e-7:
                            raise ValueError(f'LP independent dual check failed: {c}/{name}/{budget}: {metrics}')
                        seconds = time.perf_counter() - tick
                        solve_times.append(seconds)
                        if name == 'base':
                            same_budget_fit = (fit, metrics)
                    share = float(np.maximum(residual - fit, 0.).sum() / D.sum())
                    cert_rows.append({'country': c, 'case': name, 'budget': budget, 'solve_seconds': seconds,
                        'annual_uncovered_share': share, 'partner_energy_budget': energy, **metrics})
                    route_rows.append({'country': c, 'case': name, 'method': 'LP', 'budget': budget, 'scope': 'upper',
                        'annual_uncovered_share': share, 'annual_energy': float(D.sum()), 'domestic_shortfall_energy': R,
                        'eligible_shortfall_energy': R, 'partner_energy_budget': energy, 'partner_fit_energy': float(fit.sum()),
                        'fixed_unroutable_energy': 0.})
                    if name == 'base':
                        error = abs(share - archived.loc[c, 'rt_lp_fixed_nnls_residual'])
                        if error > 1e-8:
                            raise ValueError(f'Archived LP baseline differs: {c}, {error}')
                        base['partner_lp'] = fit
                        np.savez_compressed(folder / f'{c}.npz', **base)
                        for row in country_rows:
                            if row['country'] == c:
                                total = profile(d, row['case'])[0]
                                row['entirely_frozen_lp_supply_share'] = float(np.maximum(total - base['domestic'] - fit, 0.).sum() / total.sum())
                    print(f'LP {c} {name} {budget}: U={100*share:.6f}% solve={seconds:.2f}s total={time.perf_counter()-start:.2f}s', flush=True)
            if (ci + 1) % 5 == 0 or ci + 1 == len(countries):
                pd.DataFrame(cert_rows).to_csv(paths['certs'], index=False)
                summaries(country_rows, route_rows, scale_rows, args.output_dir)
        certificate = pd.DataFrame(cert_rows)
        maxima = {key: float(certificate[key].max()) for key in ['duality_gap_absolute', 'duality_gap_relative',
            'primal_inequality_violation', 'primal_equality_violation', 'primal_bound_violation',
            'dual_stationarity_violation', 'dual_reduced_cost_violation', 'dual_sign_violation']}
        base_max['routing_lp_error'] = max((abs(row['annual_uncovered_share'] - archived.loc[row['country'], 'rt_lp_fixed_nnls_residual'])
            for row in cert_rows if row['case'] == 'base'), default=None)
        requested = {(c, name, budget) for c in countries for name in lp_names for budget in ['current_R', 'fixed_R0']}
        completed = {(row['country'], row['case'], row['budget']) for row in cert_rows}
        if not requested.issubset(completed):
            raise ValueError(f'Missing requested LP comparisons: {sorted(requested - completed)}')
        if base_max['routing_lp_error'] is not None and base_max['routing_lp_error'] > 1e-8:
            raise ValueError(f'Retained archived LP baseline differs: {base_max}')
        if max(maxima[key] for key in ['primal_inequality_violation', 'primal_equality_violation', 'primal_bound_violation']) > 1e-7 or maxima['duality_gap_relative'] > 1e-8 or maxima['duality_gap_absolute'] > 1e-5:
            raise ValueError(f'Retained LP certificate check failed: {maxima}')
        if max(maxima[key] for key in ['dual_stationarity_violation', 'dual_reduced_cost_violation', 'dual_sign_violation']) > 1e-7:
            raise ValueError(f'Retained LP dual certificate check failed: {maxima}')
        retained_times = certificate.loc[certificate['solve_seconds'] > 0, 'solve_seconds']
        write_json(args.output_dir / 'validation.json', {'status': 'passed', 'countries': len(countries), 'cases_nnls': names,
            'lp_cases_requested': lp_names, 'lp_case_budget_rows': len(cert_rows), 'unique_new_lp_solves': len(solve_times),
            'requested_lp_case_budget_rows': len(requested), 'requested_lp_complete': True,
            'retained_unique_lp_solves': int(len(retained_times)),
            'retained_lp_solve_seconds_median': float(retained_times.median()),
            'retained_lp_solve_seconds_max': float(retained_times.max()),
            'lp_solve_seconds_median': float(np.median(solve_times)) if solve_times else None,
            'lp_solve_seconds_max': max(solve_times) if solve_times else None,
            'estimated_104_country_two_budget_case_seconds_from_actual_pilot': float(np.median(solve_times) * 208) if solve_times else None,
            'elapsed_seconds': time.perf_counter()-start, 'archived_baseline_max_errors': base_max, 'lp_measured_error_maxima': maxima,
            'configured_primal_tolerance': 1e-8, 'configured_dual_tolerance': 1e-8, 'configured_ipm_tolerance': 1e-9,
            'independent_feasibility_acceptance_tolerance': 1e-7,
            'independent_duality_relative_acceptance_tolerance': 1e-8,
            'independent_duality_absolute_acceptance_tolerance': 1e-5,
            'restricted_cases_are_nnls_procedural_comparisons': True,
            'new_demand_requires_new_shortfall_certificate': True,
            'request_scale_control_supply_scales_with_demand': True})
        print(f'COMPLETE {time.perf_counter()-start:.2f}s; LP unique solves {len(solve_times)}', flush=True)


if __name__ == '__main__':
    main()
