from pathlib import Path
import argparse
import json
import hashlib
import numpy as np
import pandas as pd
from scipy.optimize import linprog, milp, Bounds, LinearConstraint
from scipy.sparse import coo_matrix

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
OUT = None
TRACE = None
CFPATH = None
HOURLY = None
RENEWABLE_HOURLY = None
SOURCE_MANIFEST = None
COUNTRIES = ['US', 'DE', 'JP']
REFERENCE_RATE = 0.3
REQUESTS_PER_GPU_HOUR = REFERENCE_RATE * 3600
HEADROOM_FACTOR = 0.8
DELAY = np.array([[0., 120., 180.], [120., 0., 220.], [180., 220., 0.]])
HARDWARE = {'H100_NVL': (59., 165.9, 39.), 'A100_SXM4': (56., 172.9, 48.), 'L4': (17., 68.7, 203.)}


def hash_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def aggregate_trace():
    if HOURLY is not None:
        assert hash_file(HOURLY) == SOURCE_MANIFEST['derived_trace_sha256'], 'Hourly trace input differs from the retained revision input'
        data = pd.read_csv(HOURLY, parse_dates=['timestamp_utc'])
        assert set(data['origin']) == set(COUNTRIES)
        assert not data[['requests', 'context_tokens', 'generated_tokens']].isna().any().any()
        assert int(data['requests'].sum()) == SOURCE_MANIFEST['original_requests']
        return data
    assert TRACE is not None
    assert hash_file(TRACE) == SOURCE_MANIFEST['trace_sha256'], 'Raw trace differs from the specified published input version'
    target = OUT / 'azure_coding_hourly_with_scenario_origins.csv'
    parts = []
    offset = 0
    for chunk in pd.read_csv(TRACE, chunksize=1_000_000):
        times = pd.to_datetime(chunk['TIMESTAMP'], utc=True)
        codes = np.arange(offset, offset + len(chunk), dtype=np.int64) % 10
        origins = np.select([codes < 5, codes < 8], ['US', 'DE'], default='JP')
        block = pd.DataFrame({'timestamp_utc': times.dt.floor('h'), 'origin': origins, 'requests': np.ones(len(chunk), dtype=np.int64), 'context_tokens': chunk['ContextTokens'].to_numpy(), 'generated_tokens': chunk['GeneratedTokens'].to_numpy()})
        parts.append(block.groupby(['timestamp_utc', 'origin']).sum().reset_index())
        offset += len(chunk)
        print('Read actual requests', offset, flush=True)
    data = pd.concat(parts).groupby(['timestamp_utc', 'origin']).sum().reset_index()
    assert int(data['requests'].sum()) == offset
    data.to_csv(target, index=False)
    return data


def make_inputs(data):
    times = pd.date_range(data['timestamp_utc'].min(), data['timestamp_utc'].max(), freq='h')
    requests = data.pivot(index='timestamp_utc', columns='origin', values='requests').reindex(index=times, columns=COUNTRIES).fillna(0).to_numpy()
    model_times = times + pd.DateOffset(years=1)
    if RENEWABLE_HOURLY is not None:
        assert hash_file(RENEWABLE_HOURLY) == SOURCE_MANIFEST['derived_renewable_sha256'], 'Renewable input differs from the retained revision input'
    raw = pd.read_csv(RENEWABLE_HOURLY, float_precision='round_trip') if RENEWABLE_HOURLY is not None else pd.read_parquet(CFPATH)
    raw['timestamp_utc'] = pd.to_datetime(raw['timestamp_utc'], utc=True)
    shapes = []
    for country in COUNTRIES:
        frame = raw[raw['iso2'].eq(country)].pivot(index='timestamp_utc', columns='tech', values='cf').reindex(model_times)
        assert not frame[['PV', 'WIND']].isna().any().any()
        blend = .5 * frame['PV'].to_numpy() + .5 * frame['WIND'].to_numpy()
        shapes.append(blend / blend.mean())
    shape = np.array(shapes).T
    days = times.floor('D')
    background = np.zeros_like(requests, dtype=float)
    pools = []
    for day in days.unique():
        select = np.asarray(days == day)
        pool = np.ceil(.2 * requests[select].sum(axis=0))
        background[select] = pool / select.sum()
        pools.append({'day_utc': day.isoformat(), **{country: float(pool[j]) for j, country in enumerate(COUNTRIES)}})
    q = requests / REQUESTS_PER_GPU_HOUR
    b = background / REQUESTS_PER_GPU_HOUR
    fleets = np.ceil(np.max(q + b, axis=0) / HEADROOM_FACTOR).astype(int)
    assert np.max((q + b) / fleets) <= HEADROOM_FACTOR + 1e-10
    pd.DataFrame(pools).to_csv(OUT / 'finite_background_daily_job_unit_pools.csv', index=False)
    return times, model_times, requests, q, b, fleets, shape, days


def solve_case(q, b, fleets, clean, days, idle_w, high_w, policy, budget_ms, restart_wh):
    hours, sites = q.shape
    if policy == 'consolidate_sleep' and hours > 1:
        pieces = [solve_case(q[h:h + 1], b[h:h + 1], fleets, clean[h:h + 1], days[h:h + 1], idle_w, high_w, policy, budget_ms, 0.) for h in range(hours)]
        whole = {key: np.concatenate([part[key] for part in pieces], axis=0) for key in ('flow', 'background', 'awake', 'served', 'power', 'gap')}
        whole['starts'] = np.zeros_like(whole['awake'])
        whole['starts'][1:] = np.maximum(whole['awake'][1:] - whole['awake'][:-1], 0.)
        whole['transition'] = np.zeros_like(whole['awake'])
        whole['transition'][:-1] = whole['starts'][1:] * restart_wh / 1000.
        whole['power'] += whole['transition']
        whole['gap'] = np.maximum(whole['power'] - clean, 0.)
        whole['solver_status'] = max(part['solver_status'] for part in pieces)
        whole['solver_message'] = 'Optimal independent-hour lexicographic MILP; external restart charge evaluated on frozen dispatch' if restart_wh else 'Optimal independent-hour lexicographic MILP'
        whole['constraint_violation'] = max(part['constraint_violation'] for part in pieces)
        whole['conservation_error'] = max(part['conservation_error'] for part in pieces)
        whole['objective'] = sum(part['objective'] for part in pieces)
        return whole
    count_x = hours * sites * sites
    count_b = hours * sites
    x_idx = np.arange(count_x).reshape(hours, sites, sites)
    b_idx = np.arange(count_x, count_x + count_b).reshape(hours, sites)
    n_idx = np.arange(count_x + count_b, count_x + 2 * count_b).reshape(hours, sites)
    g_idx = np.arange(count_x + 2 * count_b, count_x + 3 * count_b).reshape(hours, sites)
    start_idx = np.arange(count_x + 3 * count_b, count_x + 4 * count_b).reshape(hours, sites)
    total_vars = count_x + 4 * count_b
    lower = np.zeros(total_vars)
    upper = np.full(total_vars, np.inf)
    lower[b_idx] = b if policy != 'finite_backfill' else 0
    upper[b_idx] = b if policy != 'finite_backfill' else np.broadcast_to(fleets * HEADROOM_FACTOR, b.shape)
    lower[n_idx] = 1 if policy == 'consolidate_sleep' else np.broadcast_to(fleets, q.shape)
    upper[n_idx] = np.broadcast_to(fleets, q.shape)
    if policy != 'consolidate_sleep':
        upper[start_idx] = 0
    else:
        upper[start_idx] = np.broadcast_to(fleets, q.shape)
        upper[start_idx[0]] = 0
    allowed = DELAY <= budget_ms
    for h in range(hours):
        upper[x_idx[h][~allowed]] = 0
    energy_coeff = (high_w - idle_w) / 1000.
    idle_coeff = idle_w / 1000.
    transition_coeff = restart_wh / 1000.
    objective = np.zeros(total_vars)
    objective[g_idx] = 1.
    objective[n_idx] = idle_coeff * 1e-6
    objective[start_idx] = transition_coeff * 1e-6 + 1e-8
    objective[x_idx] = energy_coeff * 1e-6
    objective[b_idx] = energy_coeff * 1e-6
    rows, columns, values = [], [], []
    constraint_lower, constraint_upper = [], []

    def add(coefficients, lo=-np.inf, hi=np.inf):
        row = len(constraint_lower)
        for col, val in coefficients:
            rows.append(row)
            columns.append(int(col))
            values.append(float(val))
        constraint_lower.append(lo)
        constraint_upper.append(hi)

    for h in range(hours):
        for origin in range(sites):
            add([(x_idx[h, origin, j], 1.) for j in range(sites)], q[h, origin], q[h, origin])
        for j in range(sites):
            serve = [(x_idx[h, o, j], 1.) for o in range(sites)]
            add(serve + [(b_idx[h, j], 1.), (n_idx[h, j], -HEADROOM_FACTOR)], hi=0.)
            power = [(col, energy_coeff) for col, _ in serve]
            power += [(b_idx[h, j], energy_coeff), (n_idx[h, j], idle_coeff), (g_idx[h, j], -1.)]
            if h + 1 < hours:
                # 下一小时需要的新副本在本小时结束前预热。
                power += [(start_idx[h + 1, j], transition_coeff)]
            add(power, hi=clean[h, j])
            if policy == 'finite_backfill':
                # 背景池只在原站点由固定均匀安排或释放的交互容量执行。
                add([(b_idx[h, j], 1.), (x_idx[h, j, j], 1.)], hi=b[h, j] + q[h, j])
            if policy == 'consolidate_sleep' and h > 0:
                add([(n_idx[h, j], 1.), (n_idx[h - 1, j], -1.), (start_idx[h, j], -1.)], hi=0.)
    for day in days.unique():
        select = np.flatnonzero(np.asarray(days == day))
        for j in range(sites):
            amount = b[select, j].sum()
            add([(b_idx[h, j], 1.) for h in select], amount, amount)
    matrix = coo_matrix((values, (rows, columns)), shape=(len(constraint_lower), total_vars)).tocsc()
    con_lo = np.array(constraint_lower)
    con_hi = np.array(constraint_upper)
    if policy == 'consolidate_sleep':
        integer = np.zeros(total_vars, dtype=int)
        integer[n_idx] = 1
        primary = np.zeros(total_vars)
        primary[g_idx] = 1.
        first = milp(primary, integrality=integer, bounds=Bounds(lower, upper), constraints=LinearConstraint(matrix, con_lo, con_hi), options={'mip_rel_gap': 1e-7, 'time_limit': 240})
        assert first.success, first.message
        # 在保持最小绝对缺口的可行解中，再最小化 GPU 总用电。
        gap_cap = coo_matrix((np.ones(count_b), (np.zeros(count_b, dtype=int), g_idx.ravel())), shape=(1, total_vars)).tocsc()
        secondary = np.zeros(total_vars)
        secondary[n_idx] = idle_coeff
        secondary[x_idx] = energy_coeff
        secondary[b_idx] = energy_coeff
        secondary[start_idx[1:]] = transition_coeff
        result = milp(secondary, integrality=integer, bounds=Bounds(lower, upper), constraints=[LinearConstraint(matrix, con_lo, con_hi), LinearConstraint(gap_cap, -np.inf, first.fun + 1e-8)], options={'mip_rel_gap': 1e-7, 'time_limit': 240})
    else:
        eq = np.isfinite(con_lo) & np.isfinite(con_hi) & np.isclose(con_lo, con_hi)
        assert np.all(~np.isfinite(con_lo[~eq]))
        result = linprog(objective, A_ub=matrix[~eq], b_ub=con_hi[~eq], A_eq=matrix[eq], b_eq=con_hi[eq], bounds=list(zip(lower, upper)), method='highs', options={'primal_feasibility_tolerance': 1e-8, 'dual_feasibility_tolerance': 1e-8})
    assert result.success, result.message
    flow = result.x[x_idx]
    background = result.x[b_idx]
    awake = result.x[n_idx]
    starts = np.zeros_like(awake)
    starts[1:] = np.maximum(awake[1:] - awake[:-1], 0.)
    transition = np.zeros_like(awake)
    transition[:-1] = starts[1:] * transition_coeff
    served = flow.sum(axis=1)
    power = idle_coeff * awake + energy_coeff * (served + background) + transition
    gap = np.maximum(power - clean, 0.)
    constraint_value = matrix @ result.x
    violation = max(float(np.maximum(con_lo - constraint_value, 0).max()), float(np.maximum(constraint_value - con_hi, 0).max()))
    conservation_error = float(np.max(np.abs(flow.sum(axis=2) - q)))
    assert violation < 1e-5
    assert conservation_error < 1e-5
    assert np.max(served + background - HEADROOM_FACTOR * awake) < 1e-5
    for day in days.unique():
        select = np.asarray(days == day)
        assert np.max(np.abs(background[select].sum(axis=0) - b[select].sum(axis=0))) < 1e-5
    assert abs(gap.sum() - result.x[g_idx].sum()) < 1e-3
    return {'flow': flow, 'background': background, 'awake': awake, 'starts': starts, 'served': served, 'transition': transition, 'power': power, 'gap': gap, 'solver_status': result.status, 'solver_message': result.message, 'constraint_violation': violation, 'conservation_error': conservation_error, 'objective': result.fun}


def main():
    global OUT, TRACE, CFPATH, HOURLY, RENEWABLE_HOURLY, SOURCE_MANIFEST
    parser = argparse.ArgumentParser(description='Recompute the three-site power-accounting scenarios from hourly trace and renewable inputs')
    parser.add_argument('--input-hourly', type=Path, default=PACKAGE_ROOT / 'inputs/power/azure_coding_hourly_with_scenario_origins.csv')
    parser.add_argument('--renewable-hourly', type=Path, default=PACKAGE_ROOT / 'inputs/power/renewable_three_site_hourly.csv')
    parser.add_argument('--input-manifest', type=Path, default=PACKAGE_ROOT / 'inputs/power/input_provenance.json')
    parser.add_argument('--output-dir', type=Path, default=PACKAGE_ROOT / 'results/power')
    parser.add_argument('--raw-trace', type=Path)
    parser.add_argument('--renewable-parquet', type=Path)
    args = parser.parse_args()
    OUT = args.output_dir.resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    TRACE = args.raw_trace
    CFPATH = args.renewable_parquet
    HOURLY = None if TRACE is not None else args.input_hourly.resolve()
    RENEWABLE_HOURLY = None if CFPATH is not None else args.renewable_hourly.resolve()
    SOURCE_MANIFEST = json.loads(args.input_manifest.read_text(encoding='utf-8'))
    data = aggregate_trace()
    times, model_times, requests, q, b, fleets, shape, days = make_inputs(data)
    sources = {'trace_path': str(TRACE) if TRACE is not None else SOURCE_MANIFEST['trace_path'], 'trace_sha256': hash_file(TRACE) if TRACE is not None else SOURCE_MANIFEST['trace_sha256'], 'renewable_path': str(CFPATH) if CFPATH is not None else SOURCE_MANIFEST['renewable_path'], 'renewable_sha256': hash_file(CFPATH) if CFPATH is not None else SOURCE_MANIFEST['renewable_sha256'], 'derived_hourly_trace_sha256': hash_file(HOURLY) if HOURLY is not None else None, 'derived_hourly_renewable_sha256': hash_file(RENEWABLE_HOURLY) if RENEWABLE_HOURLY is not None else None, 'origin_assignment': 'zero-based CSV row index modulo 10: US 0-4, DE 5-7, JP 8-9; scenario, not observed geography', 'original_requests': int(requests.sum()), 'background_job_units': float((b * REQUESTS_PER_GPU_HOUR).sum()), 'first_hour_utc': times[0].isoformat(), 'last_hour_utc': times[-1].isoformat(), 'hours': len(times), 'solar_wind_calendar': 'same civil UTC month/day/hour shifted by one year; controlled 2024 requests with 2025 renewable reconstruction', 'fleet': {country: int(fleets[j]) for j, country in enumerate(COUNTRIES)}, 'design_rate_requests_per_second_per_gpu': REFERENCE_RATE, 'design_headroom_factor': HEADROOM_FACTOR, 'hardware_parameters': HARDWARE, 'delay_scenario_ms': DELAY.tolist(), 'hardware_source': 'https://arxiv.org/html/2604.09048v1', 'transition_sensitivity_source': 'https://hotcarbon.org/assets/2025/paper-11.pdf', 'baseline_supply': 'for each hardware, fixed solar/wind shape with budget equal to local always-on baseline GPU energy; retained across every routing/power policy for that hardware'}
    (OUT / 'power_case_manifest.json').write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding='utf-8')
    summaries, hourly, flow_rows, facility_rows = [], [], [], []
    for hardware, (idle, high, mean_p95) in HARDWARE.items():
        baseline_power = idle / 1000. * fleets + (high - idle) / 1000. * (q + b)
        clean = shape * (baseline_power.sum(axis=0) / len(times))
        for budget in (0, 200, 500):
            for policy in ('remain_on_idle', 'finite_backfill', 'consolidate_sleep'):
                # 34393.48 J 为另一种双 H100 系统的重启能耗，只作敏感性收费。
                transitions = (0., 34393.48 / 3600.) if policy == 'consolidate_sleep' and hardware == 'H100_NVL' else (0.,)
                for restart in transitions:
                    case = solve_case(q, b, fleets, clean, days, idle, high, policy, budget, restart)
                    key = f'{hardware}_{budget}ms_{policy}_restart{restart:.6f}Wh'
                    moved = case['flow'].sum() - sum(case['flow'][:, j, j].sum() for j in range(3))
                    summary = {'case': key, 'hardware': hardware, 'network_budget_ms': budget, 'policy': policy, 'external_restart_charge_wh_per_replica_activation': restart, 'external_restart_dispatch_frozen': bool(restart), 'interactive_requests': int(requests.sum()), 'background_job_units': float((case['background'] * REQUESTS_PER_GPU_HOUR).sum()), 'routed_request_equivalents': float(moved * REQUESTS_PER_GPU_HOUR), 'routed_fraction_pct': float(moved / q.sum() * 100), 'gpu_energy_kwh': float(case['power'].sum()), 'clean_supply_kwh': float(clean.sum()), 'same_hour_gap_kwh': float(case['gap'].sum()), 'same_hour_gap_pct_gpu_energy': float(case['gap'].sum() / case['power'].sum() * 100), 'transition_kwh': float(case['transition'].sum()), 'replica_activations': float(case['starts'].sum()), 'awake_gpu_hours': float(case['awake'].sum()), 'unserved_modeled_hourly_request_equivalents': float((q.sum() - case['flow'].sum()) * REQUESTS_PER_GPU_HOUR), 'max_conservation_error_requests_per_hour': case['conservation_error'] * REQUESTS_PER_GPU_HOUR, 'max_constraint_violation_model_units': case['constraint_violation'], 'solver_status': case['solver_status'], 'solver_message': case['solver_message'], 'trace_tail_latency_certified': False}
                    summaries.append(summary)
                    for h, stamp in enumerate(times):
                        for j, country in enumerate(COUNTRIES):
                            hourly.append({'case': key, 'timestamp_utc': stamp.isoformat(), 'renewable_timestamp_utc': model_times[h].isoformat(), 'site': country, 'origin_requests': int(requests[h, j]), 'executed_interactive_request_equivalents': float(case['served'][h, j] * REQUESTS_PER_GPU_HOUR), 'executed_background_job_units': float(case['background'][h, j] * REQUESTS_PER_GPU_HOUR), 'installed_gpus': int(fleets[j]), 'awake_gpus': float(case['awake'][h, j]), 'gpu_power_kw': float(case['power'][h, j]), 'clean_power_kw': float(clean[h, j]), 'gap_power_kw': float(case['gap'][h, j]), 'transition_kwh_this_hour': float(case['transition'][h, j])})
                        if hardware == 'H100_NVL' and restart == 0:
                            for o in range(3):
                                for j in range(3):
                                    flow_rows.append({'case': key, 'timestamp_utc': stamp.isoformat(), 'origin': COUNTRIES[o], 'destination': COUNTRIES[j], 'request_equivalents': float(case['flow'][h, o, j] * REQUESTS_PER_GPU_HOUR), 'assumed_added_network_delay_ms': float(DELAY[o, j])})
                    for pue in (1., 1.2, 1.5):
                        for fixed_host_w in (0., 50., 100.):
                            facility_power = pue * (case['power'] + fleets * fixed_host_w / 1000.)
                            facility_gap = np.maximum(facility_power - clean, 0.)
                            facility_rows.append({'case': key, 'pue_scenario': pue, 'fixed_non_gpu_w_per_installed_gpu_scenario': fixed_host_w, 'dispatch_frozen': True, 'facility_energy_kwh': float(facility_power.sum()), 'fixed_clean_supply_kwh': float(clean.sum()), 'facility_gap_kwh': float(facility_gap.sum()), 'facility_gap_pct': float(facility_gap.sum() / facility_power.sum() * 100)})
                    print(key, 'gap', round(summary['same_hour_gap_pct_gpu_energy'], 3), 'energy', round(summary['gpu_energy_kwh'], 3), flush=True)
                    pd.DataFrame(summaries).to_csv(OUT / 'power_case_summary.csv', index=False)
    pd.DataFrame(hourly).to_csv(OUT / 'power_case_hourly_site_ledger.csv', index=False)
    pd.DataFrame(flow_rows).to_csv(OUT / 'power_case_hourly_origin_destination_flows.csv', index=False)
    pd.DataFrame(facility_rows).to_csv(OUT / 'facility_overhead_sensitivity.csv', index=False)
    pd.DataFrame([{'origin': COUNTRIES[o], 'destination': COUNTRIES[j], 'assumed_added_network_delay_ms': DELAY[o, j], 'measured_network_tail': False} for o in range(3) for j in range(3)]).to_csv(OUT / 'illustrative_network_delay_assumptions.csv', index=False)


if __name__ == '__main__':
    main()
