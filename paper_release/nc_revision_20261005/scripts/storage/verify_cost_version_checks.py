import json
import pickle

import numpy as np
import pandas as pd

import run_storage_revision as R

here = R.HERE
keys = ['country', 'year', 'tau_ms', 'phi']
soft = pd.read_csv(here/'soft_2025_version_checks.csv', keep_default_na=False)
with (here/'all_fig5_inputs.pkl').open('rb') as handle:
    original, aliases, jobs = pickle.load(handle)
soft['solved_input_tau_ms'] = soft.tau_ms
for index, row in soft.iterrows():
    requested_tau = 50 if row.phi == 0 else 500
    solved_key = (row.country, int(row.year), int(row.tau_ms), float(row.phi))
    requested_key = (row.country, int(row.year), requested_tau, float(row.phi))
    assert aliases[solved_key] == aliases[requested_key]
    soft.loc[index, 'tau_ms'] = requested_tau
soft = soft.rename(columns={column: f'{column}_replayed' for column in ['lcoe_gen','lcoe_store','lcoe_anc','lcoe_elec']})
paired = pd.read_csv(here/'fig5_old_new_country_comparison.csv', keep_default_na=False)
paired = paired[paired.source_table == 'r3_dispatch_cost_table.csv']
check = soft.merge(paired, on=keys, suffixes=('_replayed', ''), validate='one_to_one')
assert len(check) == 6
for column in ['lcoe_gen', 'lcoe_store', 'lcoe_anc', 'lcoe_elec']:
    check[f'{column}_soft_minus_frozen'] = check[f'{column}_replayed']-check[f'{column}_old']
    np.testing.assert_allclose(check[f'{column}_replayed'], check[f'{column}_old'], rtol=1e-7, atol=1e-6)
check['strict_cost_increase_usd_per_mwh'] = check.lcoe_elec_new-check.lcoe_elec_replayed
check['strict_cost_increase_pct'] = 100*(check.lcoe_elec_new/check.lcoe_elec_replayed-1)
check['soft_service_pct'] = 100*check.firm_share_replayed
check['strict_service_pct'] = 100*check.firm_share
columns = keys+['solved_input_tau_ms']+[
    'lcoe_gen_old', 'lcoe_gen_replayed', 'lcoe_gen_new',
    'lcoe_store_old', 'lcoe_store_replayed', 'lcoe_store_new',
    'lcoe_elec_old', 'lcoe_elec_replayed', 'lcoe_elec_new',
    'lcoe_elec_soft_minus_frozen', 'strict_cost_increase_usd_per_mwh',
    'strict_cost_increase_pct', 'pi_old_pct', 'pi_new_pct',
    'unmet_mwh_replayed', 'unmet_mwh', 'soft_service_pct', 'strict_service_pct'
]
check[columns].to_csv(here/'soft_2025_reproduction_comparison.csv', index=False)
validation = {
    'passed': True,
    'replayed_cases': len(check),
    'maximum_soft_cost_difference_vs_frozen_usd_per_mwh': float(check.lcoe_elec_soft_minus_frozen.abs().max()),
    'maximum_soft_component_difference_vs_frozen_usd_per_mwh': float(check[[f'{c}_soft_minus_frozen' for c in ['lcoe_gen','lcoe_store','lcoe_anc']]].abs().to_numpy().max()),
    'strict_unmet_mwh_max': float(check.unmet_mwh.max()),
    'strict_service_pct_min': float(check.strict_service_pct.min()),
    'normalization': '100 MW mean remaining domestic load',
    'cost_denominator': 'annual remaining domestic demand MWh',
    'frozen_source_table': 'r3_dispatch_cost_table.csv',
    'replayed_objective': 'original VOLL penalty with no zero-shortfall constraint',
}
(here/'soft_2025_reproduction_validation.json').write_text(json.dumps(validation, indent=2), encoding='utf-8')
print(check[columns].to_string(index=False))
print(json.dumps(validation, indent=2))
