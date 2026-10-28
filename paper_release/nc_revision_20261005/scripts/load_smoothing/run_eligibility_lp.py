import argparse
import hashlib
import io
import json
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

import run_sensitivity as runner


ROOT = Path(__file__).resolve().parent
CASES = ['static25', 'static50', 'daily25', 'daily50']
REFERENCES = ['base', 'flat100']


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')


def read_csv(path):
    return pd.read_csv(path, keep_default_na=False, na_values=[''])


def compare_upper(output, upper_path, require_complete=False):
    restricted = read_csv(output / 'routing_results.csv')
    raw = upper_path.read_bytes()
    upper = pd.read_csv(io.BytesIO(raw), keep_default_na=False, na_values=[''])
    upper = upper.loc[upper['method'].eq('LP') & upper['budget'].eq('current_R') & upper['scope'].eq('upper')
        & upper['case'].isin(CASES + REFERENCES)]
    expected = set(map(tuple, restricted[['country', 'case']].to_numpy()))
    present = set(map(tuple, upper[['country', 'case']].to_numpy()))
    missing = sorted(expected - present)
    if missing:
        if require_complete:
            raise ValueError(f'Upper LP results incomplete: {len(missing)} missing country/case pairs')
        return {'status': 'awaiting_complete_upper_results', 'required_pairs': len(expected),
            'available_pairs': len(expected & present), 'missing_pairs': len(missing)}
    if upper.duplicated(['country', 'case']).any():
        raise ValueError('Duplicate upper LP comparisons')
    paired = restricted.merge(upper[['country', 'case', 'annual_uncovered_share', 'annual_energy',
        'domestic_shortfall_energy', 'partner_energy_budget']], on=['country', 'case'],
        suffixes=('_restricted', '_upper'), validate='one_to_one')
    for field in ['annual_energy', 'domestic_shortfall_energy', 'partner_energy_budget']:
        error = np.abs(paired[field + '_restricted'] - paired[field + '_upper'])
        if error.max() > 1e-7:
            raise ValueError(f'Nested comparisons differ in {field}: {error.max()}')
    paired['restricted_minus_upper_pp'] = 100 * (paired['annual_uncovered_share_restricted'] - paired['annual_uncovered_share_upper'])
    tolerance = 1e-8
    if (paired['restricted_minus_upper_pp'] < -100 * tolerance).any():
        failed = paired.loc[paired['restricted_minus_upper_pp'] < -100 * tolerance]
        raise ValueError('Restricted optimum below upper optimum: ' + failed.to_json(orient='records'))
    paired.to_csv(output / 'nested_comparison.csv', index=False)
    report = {'status': 'passed', 'pairs': len(paired), 'annual_share_tolerance': tolerance,
        'minimum_restricted_minus_upper_pp': float(paired['restricted_minus_upper_pp'].min()),
        'violating_pairs': 0, 'upper_source_sha256': hashlib.sha256(raw).hexdigest()}
    write_json(output / 'nested_validation.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description='Same-objective interactive-only eligibility LP sensitivity')
    parser.add_argument('--data-root', type=Path, default=runner.ARCHIVE / 'inputs/hourly')
    parser.add_argument('--waveform-script', type=Path, default=runner.ARCHIVE / 'scripts/waveform/run_waveform_revision.py')
    parser.add_argument('--archive-results', type=Path, default=runner.ARCHIVE / 'results/waveform/objective_results.csv')
    parser.add_argument('--upper-results', type=Path, default=ROOT / 'results/routing_results.csv')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'results_eligibility')
    parser.add_argument('--compare-only', action='store_true')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.compare_only:
        report = compare_upper(args.output_dir, args.upper_results, require_complete=True)
        validation = json.loads((args.output_dir / 'validation.json').read_text(encoding='utf-8'))
        validation['nested_comparison'] = report
        write_json(args.output_dir / 'validation.json', validation)
        print(json.dumps(report), flush=True)
        return
    args.data_root = args.data_root.resolve()
    start = time.perf_counter()
    archive = read_csv(args.archive_results).set_index('country')
    paths = {'rows': args.output_dir / 'routing_results.csv', 'metrics': args.output_dir / 'lp_solver_metrics.csv'}
    rows = read_csv(paths['rows']).to_dict('records') if paths['rows'].exists() else []
    metrics_rows = read_csv(paths['metrics']).to_dict('records') if paths['metrics'].exists() else []
    complete = {(row['country'], row['case']) for row in rows}
    if len(complete) != len(rows):
        raise ValueError('Duplicate checkpoint rows')
    fingerprint = {'waveform_script_sha256': runner.digest(args.waveform_script),
        'archive_results_sha256': runner.digest(args.archive_results),
        'hourly_inputs': {name: runner.digest(args.data_root / name)
            for name in ['country_hourly_demand.csv.gz', 'site_hourly_cf.parquet', 'country_meta.csv']},
        'cases_solved': CASES, 'reference_cases': REFERENCES, 'budget': 'current_R',
        'eligible_rule': 'e=min(interactive,domestic shortfall); fixed L=residual-e',
        'objective': 'sum(L)+sum(max(e-partner fit,0))',
        'partner_budget': 'same total domestic shortfall R; excess hourly generation may remain unused'}
    fingerprint_path = args.output_dir / 'input_fingerprint.json'
    if fingerprint_path.exists() and json.loads(fingerprint_path.read_text(encoding='utf-8')) != fingerprint:
        raise ValueError('Inputs changed since checkpoint')
    write_json(fingerprint_path, fingerprint)
    with threadpool_limits(limits=1):
        W, data = runner.load_waveform(SimpleNamespace(waveform_script=args.waveform_script,
            data_root=args.data_root, output_dir=args.output_dir))
        _, countries, demands, homes, shapes, _, reach, _ = data
        for ci, country in enumerate(countries):
            d, home = demands[country], homes[country]
            partner = np.column_stack([shapes[p] for p in reach[country][500]])
            for case in REFERENCES + CASES:
                if (country, case) in complete:
                    continue
                D, interactive, checks = runner.profile(d, case)
                local = W.fit_nnls(D, home)[1]
                residual = np.maximum(D - local, 0.)
                eligible = np.minimum(interactive, residual)
                fixed = residual - eligible
                E, R = float(D.sum()), float(residual.sum())
                if abs(E - float(d.sum())) > 1e-7 or fixed.min() < -1e-12:
                    raise ValueError(f'Annual energy or fixed shortfall mismatch: {country}/{case}')
                tick = time.perf_counter()
                if case == 'base':
                    original = archive.loc[country]
                    if abs(R - original['R_nnls']) > 1e-7 or abs(E - original['E']) > 1e-7:
                        raise ValueError(f'Archived reference inputs differ: {country}')
                    share = float(original['rt_lp_fixed_nnls_residual'])
                    fitted_energy = R
                    matched_energy = R - E * share
                    objective_error = 0.
                    kind = 'archived_same_shortfall_LP'
                elif case == 'flat100':
                    if eligible.max() != 0:
                        raise ValueError('Flat endpoint has a nonzero interactive component')
                    share = R / E
                    fitted_energy = R
                    matched_energy = 0.
                    objective_error = 0.
                    kind = 'zero_eligible_exact_reference'
                else:
                    mean = float(eligible.mean())
                    if mean <= 0:
                        raise ValueError(f'Unexpected zero eligible shortfall: {country}/{case}')
                    fitted, metrics, solution = W.direct_lp(eligible / mean, partner, energy=R / mean)
                    fit = fitted * mean
                    fitted_energy = float(fit.sum())
                    matched_energy = float(np.minimum(eligible, fit).sum())
                    gap = float(np.maximum(eligible - fit, 0.).sum())
                    share = float((fixed.sum() + gap) / E)
                    objective_error = abs(gap - metrics['primal_objective'] * mean)
                    feasibility = max(metrics[k] for k in ['primal_inequality_violation',
                        'primal_equality_violation', 'primal_bound_violation'])
                    dual_violation = max(metrics[k] for k in ['dual_stationarity_violation',
                        'dual_reduced_cost_violation', 'dual_sign_violation'])
                    if feasibility > 1e-7 or dual_violation > 1e-7 or metrics['duality_gap_relative'] > 1e-8 or metrics['duality_gap_absolute'] > 1e-5:
                        raise ValueError(f'LP certificate failed: {country}/{case}: {metrics}')
                    if abs(fitted_energy - R) > 1e-5 or objective_error > 1e-5:
                        raise ValueError(f'Budget/objective failed: {country}/{case}')
                    metrics_rows.append({'country': country, 'case': case, 'budget': 'current_R',
                        'solve_seconds': time.perf_counter() - tick, 'annual_uncovered_share': share,
                        'lp_mean_scale': mean, 'partner_energy_budget': R,
                        'raw_primal_objective': float(fixed.sum() + metrics['primal_objective'] * mean),
                        'raw_dual_objective': float(fixed.sum() + metrics['dual_objective'] * mean), **metrics})
                    kind = 'new_same_budget_eligibility_LP'
                if not np.isfinite(share) or share < -1e-10 or share > 1 + 1e-10 or E * share < fixed.sum() - 1e-7:
                    raise ValueError(f'Invalid total residual: {country}/{case}')
                row = {'country': country, 'case': case, 'method': 'LP', 'budget': 'current_R',
                    'scope': 'restricted', 'annual_uncovered_share': share, 'annual_energy': E,
                    'domestic_shortfall_energy': R, 'eligible_shortfall_energy': float(eligible.sum()),
                    'fixed_unroutable_energy': float(fixed.sum()), 'partner_energy_budget': R,
                    'partner_fit_energy': fitted_energy, 'matched_eligible_energy': matched_energy,
                    'unused_partner_generation_energy': fitted_energy - matched_energy,
                    'budget_absolute_error': abs(fitted_energy - R), 'objective_absolute_error': objective_error,
                    'annual_energy_relative_error': checks['annual_energy_relative_error'],
                    'background_pool_max_error': checks['background_pool_max_error'],
                    'capacity_violation': checks['capacity_violation'], 'solution_kind': kind}
                rows.append(row)
                complete.add((country, case))
            # 每国只保存一轮完整检查点，避免逐情景反复写入。
            pd.DataFrame(rows).to_csv(paths['rows'], index=False)
            pd.DataFrame(metrics_rows).to_csv(paths['metrics'], index=False)
            print(f'COUNTRY {ci + 1}/{len(countries)} {country}; elapsed={time.perf_counter() - start:.1f}s', flush=True)
    frame = pd.DataFrame(rows)
    cert = pd.DataFrame(metrics_rows)
    if len(frame) != 624 or len(cert) != 416 or frame.duplicated(['country', 'case']).any():
        raise ValueError(f'Incomplete eligibility results: rows={len(frame)}, certificates={len(cert)}')
    summary = frame.groupby('case').agg(n=('country', 'count'), median_share=('annual_uncovered_share', 'median'),
        min_share=('annual_uncovered_share', 'min'), max_share=('annual_uncovered_share', 'max')).reset_index()
    summary['median_pct'] = 100 * summary['median_share']
    summary.to_csv(args.output_dir / 'summary.csv', index=False)
    comparison = compare_upper(args.output_dir, args.upper_results)
    validation = {'status': 'passed', 'countries': 104, 'new_solved_country_case_rows': 416,
        'reference_rows': 208, 'total_rows': len(frame), 'solver_certificates': len(cert),
        'all_cases_positive': bool((frame['annual_uncovered_share'] > 1e-10).all()),
        'maximum_budget_absolute_error': float(frame['budget_absolute_error'].max()),
        'maximum_objective_absolute_error': float(frame['objective_absolute_error'].max()),
        'maximum_annual_energy_relative_error': float(frame['annual_energy_relative_error'].max()),
        'maximum_background_pool_error': float(frame['background_pool_max_error'].max()),
        'maximum_capacity_violation': float(frame['capacity_violation'].max()),
        'certificate_maxima': {key: float(cert[key].max()) for key in ['duality_gap_absolute',
            'duality_gap_relative', 'primal_inequality_violation', 'primal_equality_violation',
            'primal_bound_violation', 'dual_stationarity_violation', 'dual_reduced_cost_violation']},
        'nested_comparison': comparison, 'elapsed_seconds': time.perf_counter() - start}
    write_json(args.output_dir / 'validation.json', validation)
    print(summary.to_string(index=False), flush=True)
    print(json.dumps(validation), flush=True)


if __name__ == '__main__':
    main()
