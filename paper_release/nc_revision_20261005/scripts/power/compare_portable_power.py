from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd

parser = argparse.ArgumentParser(description='Compare portable recomputation with retained power-case outputs')
parser.add_argument('--retained-results', type=Path, required=True)
parser.add_argument('--recomputed-results', type=Path, required=True)
args = parser.parse_args()
retained = pd.read_csv(args.retained_results / 'power_case_summary.csv').sort_values('case').reset_index(drop=True)
recomputed = pd.read_csv(args.recomputed_results / 'power_case_summary.csv').sort_values('case').reset_index(drop=True)
assert retained['case'].tolist() == recomputed['case'].tolist()
metrics = ['interactive_requests', 'background_job_units', 'gpu_energy_kwh', 'clean_supply_kwh', 'same_hour_gap_kwh', 'same_hour_gap_pct_gpu_energy', 'routed_request_equivalents', 'awake_gpu_hours', 'replica_activations', 'transition_kwh']
errors = {metric: float(np.max(np.abs(retained[metric] - recomputed[metric]))) for metric in metrics}
assert max(errors.values()) < 1e-6
result = {'portable_recomputation_passed': True, 'case_count': len(recomputed), 'absolute_max_differences': errors, 'original_development_paths_required': False, 'required_inputs': ['azure_coding_hourly_with_scenario_origins.csv', 'renewable_three_site_hourly.csv', 'input_provenance.json'], 'comparison_scope': 'all 30 power scenarios, including routing, fleet energy, finite background, transition sensitivity and absolute/relative gaps'}
(args.recomputed_results / 'portable_recomputation_verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
