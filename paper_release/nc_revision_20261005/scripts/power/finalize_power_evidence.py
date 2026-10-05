from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd

parser = argparse.ArgumentParser(description='Verify the complete three-site ledgers and compute frozen-dispatch sensitivities')
parser.add_argument('--results-dir', type=Path, default=Path(__file__).resolve().parents[2] / 'results/power')
parser.add_argument('--input-hourly', type=Path, default=Path(__file__).resolve().parents[2] / 'inputs/power/azure_coding_hourly_with_scenario_origins.csv')
args = parser.parse_args()
OUT = args.results_dir.resolve()
PARAMS = {'H100_NVL': (59., 94.7, 165.9, 39.), 'A100_SXM4': (56., 70.7, 172.9, 48.), 'L4': (17., 38.8, 68.7, 203.)}
manifest = json.loads((OUT / 'power_case_manifest.json').read_text(encoding='utf-8'))
summary = pd.read_csv(OUT / 'power_case_summary.csv')
ledger = pd.read_csv(OUT / 'power_case_hourly_site_ledger.csv')
trace = pd.read_csv(args.input_hourly)
flow = pd.read_csv(OUT / 'power_case_hourly_origin_destination_flows.csv')
trace['timestamp_utc'] = pd.to_datetime(trace['timestamp_utc'], utc=True)
flow['timestamp_utc'] = pd.to_datetime(flow['timestamp_utc'], utc=True)
checks = []
for _, case in summary.iterrows():
    rows = ledger[ledger['case'].eq(case['case'])]
    actual_requests = rows['executed_interactive_request_equivalents'].sum()
    background = rows['executed_background_job_units'].sum()
    gaps = np.maximum(rows['gpu_power_kw'] - rows['clean_power_kw'], 0.)
    assert abs(actual_requests - manifest['original_requests']) < .02
    assert abs(background - manifest['background_job_units']) < .02
    assert abs(rows['gpu_power_kw'].sum() - case['gpu_energy_kwh']) < 1e-6
    assert abs(gaps.sum() - case['same_hour_gap_kwh']) < 1e-6
    assert abs(rows['clean_power_kw'].sum() - case['clean_supply_kwh']) < 1e-6
    assert np.min(rows['awake_gpus']) >= 1. - 1e-7
    assert np.max(rows['awake_gpus'] - rows['installed_gpus']) < 1e-7
    assert np.max(np.abs(rows['awake_gpus'] - np.round(rows['awake_gpus']))) < 1e-6
    load_units = (rows['executed_interactive_request_equivalents'] + rows['executed_background_job_units']) / 1080.
    assert np.max(load_units - .8 * rows['awake_gpus']) < 1e-5
    assert case['solver_status'] == 0
    checks.append({'case': case['case'], 'interactive_conservation_error_requests': float(actual_requests - manifest['original_requests']), 'background_conservation_error_job_units': float(background - manifest['background_job_units']), 'energy_ledger_consistent': True, 'gap_ledger_consistent': True, 'solver_optimal': True, 'empirical_slo_certification': False})
for (hardware, policy, restart), group in summary.groupby(['hardware', 'policy', 'external_restart_charge_wh_per_replica_activation']):
    if restart:
        continue
    ordered = group.sort_values('network_budget_ms')
    assert np.max(np.diff(ordered['same_hour_gap_kwh'].to_numpy()), initial=0) < 2e-4
for case, rows in flow.groupby('case'):
    assert abs(rows['request_equivalents'].sum() - manifest['original_requests']) < .02
    origin_hours = rows.groupby(['timestamp_utc', 'origin'])['request_equivalents'].sum().rename('executed').reset_index()
    compared = origin_hours.merge(trace[['timestamp_utc', 'origin', 'requests']], on=['timestamp_utc', 'origin'], validate='one_to_one')
    assert len(compared) == len(trace)
    assert np.max(np.abs(compared['executed'] - compared['requests'])) < .02
pd.DataFrame(checks).to_csv(OUT / 'power_case_verification.csv', index=False)

nonlinear = []
for key, rows in ledger.groupby('case'):
    hardware = summary.loc[summary['case'].eq(key), 'hardware'].iloc[0]
    idle, low, high, _ = PARAMS[hardware]
    rates = (rows['executed_interactive_request_equivalents'].to_numpy() + rows['executed_background_job_units'].to_numpy()) / 3600. / rows['awake_gpus'].to_numpy()
    assert np.max(rates) < .3 + 1e-7
    board_mean_w = np.interp(rates, [0., .017, .3], [idle, low, high])
    alternate_power = board_mean_w * rows['awake_gpus'].to_numpy() / 1000. + rows['transition_kwh_this_hour'].to_numpy()
    gaps = np.maximum(alternate_power - rows['clean_power_kw'].to_numpy(), 0.)
    nonlinear.append({'case': key, 'hardware': hardware, 'dispatch_frozen': True, 'curve': 'piecewise linear through idle, low-load mean at .017 req/s and high-load mean at .3 req/s; class averages, not per-trace measurements', 'gpu_energy_kwh': float(alternate_power.sum()), 'same_hour_gap_kwh': float(gaps.sum()), 'same_hour_gap_pct_gpu_energy': float(gaps.sum() / alternate_power.sum() * 100), 'unchanged_clean_budget_kwh': float(rows['clean_power_kw'].sum())})
pd.DataFrame(nonlinear).to_csv(OUT / 'low_load_endpoint_sensitivity.csv', index=False)

evidence = []
for hardware, (idle, low, high, mean_p95) in PARAMS.items():
    evidence.extend([
        {'hardware': hardware, 'quantity': 'idle GPU power W', 'value': idle, 'source': 'https://arxiv.org/html/2604.09048v1', 'locator': 'Figure 5', 'meaning': 'pre-experiment board-level mean across runs; not facility power'},
        {'hardware': hardware, 'quantity': 'medium model class low-load GPU mean power W', 'value': low, 'source': 'https://arxiv.org/html/2604.09048v1', 'locator': 'Table 5', 'meaning': 'mean across models/experiments at .017 requests/s; not a particular Azure model'},
        {'hardware': hardware, 'quantity': 'medium model class high-load GPU mean power W', 'value': high, 'source': 'https://arxiv.org/html/2604.09048v1', 'locator': 'Table 6', 'meaning': 'mean across models/experiments at .3 requests/s; not measured saturation capacity'},
        {'hardware': hardware, 'quantity': 'mean of per-experiment TTFT p95 ms in medium class', 'value': mean_p95, 'source': 'https://arxiv.org/html/2604.09048v1', 'locator': 'Table 6', 'meaning': 'average of percentiles across experiments/models; cannot certify trace tail'},
    ])
evidence.extend([
    {'hardware': 'different two-H100 node', 'quantity': 'vLLM initialization total energy J', 'value': 27209.42, 'source': 'https://hotcarbon.org/assets/2025/paper-11.pdf', 'locator': 'Table 1', 'meaning': 'system total; separate restart sensitivity'},
    {'hardware': 'different two-H100 node', 'quantity': 'vLLM 8B model loading total energy J', 'value': 7184.06, 'source': 'https://hotcarbon.org/assets/2025/paper-11.pdf', 'locator': 'Table 1', 'meaning': 'system total; not the same hardware/power curve as the accounting experiment'},
    {'hardware': 'different two-H100 node', 'quantity': 'initialization plus 8B loading time s', 'value': 60.03, 'source': 'https://hotcarbon.org/assets/2025/paper-11.pdf', 'locator': 'Table 1', 'meaning': 'predictive prewarming required; no reactive cold start in admission path'},
])
pd.DataFrame(evidence).to_csv(OUT / 'primary_power_and_latency_evidence.csv', index=False)
budgets = []
for added_budget in (0, 200, 500):
    budgets.append({'added_network_budget_ms_scenario': added_budget, 'illustrative_ttft_total_budget_ms': added_budget + 200, 'engine_queue_prefill_allowance_ms_assumed': 100, 'handshake_and_jitter_reserve_ms_assumed': 100, 'illustrative_tbt_budget_ms': 100, 'tbt_measured_for_this_trace': False, 'network_tail_measured_for_this_trace': False, 'empirical_ttft_guarantee': False, 'empirical_tbt_guarantee': False, 'streaming_assumption': 'single destination per full response; constant path propagation affects start, while jitter and generation determine inter-token gaps'})
pd.DataFrame(budgets).to_csv(OUT / 'illustrative_ttft_tbt_budget_scenarios.csv', index=False)
stats = {'trace_requests': int(trace['requests'].sum()), 'trace_context_tokens': int(trace['context_tokens'].sum()), 'trace_generated_tokens': int(trace['generated_tokens'].sum()), 'mean_context_tokens': float(trace['context_tokens'].sum() / trace['requests'].sum()), 'mean_generated_tokens': float(trace['generated_tokens'].sum() / trace['requests'].sum()), 'countries': manifest['fleet'], 'hours': manifest['hours'], 'all_cases': len(summary), 'all_cases_ledger_verified': True}
(OUT / 'power_case_verification_summary.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(stats, ensure_ascii=False))
print(summary[summary['hardware'].eq('H100_NVL')][['network_budget_ms', 'policy', 'external_restart_charge_wh_per_replica_activation', 'gpu_energy_kwh', 'same_hour_gap_kwh', 'same_hour_gap_pct_gpu_energy', 'routed_fraction_pct']].to_string(index=False))
