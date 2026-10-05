import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

parser = argparse.ArgumentParser()
parser.add_argument('--project-root',type=Path,default=Path.cwd())
parser.add_argument('--output-dir',type=Path,default=Path.cwd()/'results/storage')
args = parser.parse_args()
HERE = args.output_dir.resolve()
FROZEN = args.project_root.resolve()/'collective_attention_research_plan/reports/cfe_geographic_portfolio_ai/data_globalsites'
KEY = ['country','year','tau_ms','phi']
report = {}
for name,expected in [('r3_dispatch_cost_table.csv',1248),('r3_dispatch_grid_2030.csv',3744),('r3_dispatch_yearly_phi1.csv',3744)]:
    frame = pd.read_csv(HERE/name,keep_default_na=False)
    original = pd.read_csv(FROZEN/name,keep_default_na=False)
    assert len(frame)==expected
    assert frame[KEY].equals(original[KEY])
    uncovered_error = float(np.max(np.abs(frame.uncovered_share.to_numpy()-original.uncovered_share.to_numpy())))
    assert uncovered_error<1e-14
    for column in ['lcoe_gen','lcoe_store','lcoe_anc','lcoe_elec','P_li','E_li','P_ld','E_ld']:
        assert np.isfinite(frame[column]).all()
        assert (frame[column]>=-1e-6).all()
    assert (frame.unmet_mwh==0).all()
    assert (frame.firm_share==1).all()
    assert (frame.solver_status==0).all()
    numerical = {}
    for field in ['equality_max_abs_error_mw','inequality_max_violation_mw','bound_max_violation']:
        numerical[field] = float(frame[field].max())
        assert numerical[field]<1e-6
    assert np.max(np.abs(frame.lcoe_elec-frame.lcoe_gen-frame.lcoe_store-frame.lcoe_anc))<1e-7
    report[name] = {'rows':len(frame),'all_hourly_unmet_zero':True,'all_optimal':True,'maxima':numerical,
                    'unchanged_geometric_U_max_serialization_error':uncovered_error}

main = pd.read_csv(HERE/'strict_reliability_2030.csv',keep_default_na=False)
assert len(main)==416
strict = main[main['mode']=='strict']
assert len(strict)==208
assert (strict.unmet_mwh==0).all()
assert (strict.firm_share==1).all()
cost = pd.read_csv(HERE/'r3_dispatch_cost_table.csv',keep_default_na=False)
comparison = strict.merge(cost[KEY+['lcoe_elec']],on=KEY,suffixes=('_initial','_complete'),validate='one_to_one')
assert len(comparison)==208
primary_cost_error = float(np.max(np.abs(comparison.lcoe_elec_initial-comparison.lcoe_elec_complete)))
assert primary_cost_error<1e-6
report['primary_duplicate_max_cost_error_usd_per_mwh'] = primary_cost_error

batch = pd.read_csv(HERE/'batch_deadlines_2030.csv',keep_default_na=False)
assert len(batch)==416
assert batch.country.nunique()==104
assert set(batch.deadline_h)=={0,1,6,24}
assert (batch.unmet_mwh==0).all()
assert (batch.firm_share==1).all()
assert (batch.solver_status==0).all()
assert float(batch.batch_energy_error_mwh.max())<1e-6
assert float((batch.batch_backlog_max_mwh-batch.batch_arrival_mw*batch.deadline_h).max())<1e-6
assert float(batch.equality_max_abs_error_mw.max())<1e-6
assert float(batch.inequality_max_violation_mw.max())<1e-6
for country,part in batch.groupby('country'):
    assert part.deadline_h.tolist()==[0,1,6,24]
    assert np.max(np.diff(part.objective_usd_yr.to_numpy()))<0.1
baseline = batch[batch.deadline_h==0].merge(strict[strict.tier=='local'][['country','lcoe_elec']],on='country',suffixes=('_batch','_strict'),validate='one_to_one')
baseline_error = float(np.max(np.abs(baseline.lcoe_elec_batch-baseline.lcoe_elec_strict)))
assert baseline_error<1e-6
report['batch'] = {'rows':len(batch),'all_optimal':True,'all_unmet_zero':True,
                   'max_work_conservation_error_mwh':float(batch.batch_energy_error_mwh.max()),
                   'max_zero_deadline_cost_error_usd_per_mwh':baseline_error,
                   'max_equalities_error_mw':float(batch.equality_max_abs_error_mw.max())}

sensitivity = pd.read_csv(HERE/'table_s23_reliability.csv',keep_default_na=False)
assert len(sensitivity)==12
assert (sensitivity.solver_status==0).all()
assert (sensitivity[sensitivity.target_service_fraction==1].unmet_mwh==0).all()
assert np.max(sensitivity.target_service_fraction-sensitivity.firm_share)<1e-8
report['s23'] = {'rows':12,'all_optimal':True}
windows = pd.read_csv(HERE/'window_storage_sensitivity_2030.csv',keep_default_na=False)
assert len(windows)==36
assert windows.country.nunique()==6
assert windows.scenario.nunique()==3
assert (windows.unmet_mwh==0).all()
assert (windows.firm_share==1).all()
assert (windows.solver_status==0).all()
assert float(windows.proxy_energy_error.max())<1e-9
window_maxima = {field:float(windows[field].astype(float).max()) for field in ['equality_max_abs_error_mw','inequality_max_violation_mw','bound_max_violation']}
assert max(window_maxima.values())<1e-6
report['window_sensitivity'] = {'rows':36,'all_optimal':True,'all_unmet_zero':True,
                              'max_proxy_annual_energy_error':float(windows.proxy_energy_error.max()),
                              'maxima':window_maxima}
(HERE/'storage_validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
