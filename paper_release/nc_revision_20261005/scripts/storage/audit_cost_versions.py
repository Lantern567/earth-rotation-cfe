import os
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
import json
import pickle

import numpy as np
import pandas as pd

import run_storage_revision as R

HERE = R.HERE
FROZEN = R.PROJECT_ROOT/'collective_attention_research_plan/reports/cfe_geographic_portfolio_ai/data_globalsites'
KEY = ['country','year','tau_ms','phi']
rows, medians = [], []
for name in ['r3_dispatch_cost_table.csv','r3_dispatch_grid_2030.csv','r3_dispatch_yearly_phi1.csv']:
    old = pd.read_csv(FROZEN/name,keep_default_na=False)
    new = pd.read_csv(HERE/name,keep_default_na=False)
    paired = old.merge(new,on=KEY,suffixes=('_old','_new'),validate='one_to_one')
    assert len(paired)==len(old)
    paired['source_table'] = name
    paired['pi_old_pct'] = 100*(paired.lcoe_elec_old-paired.lcoe_gen_old)/paired.lcoe_gen_old
    paired['pi_new_pct'] = 100*(paired.lcoe_elec_new-paired.lcoe_gen_new)/paired.lcoe_gen_new
    paired['pi_change_pp'] = paired.pi_new_pct-paired.pi_old_pct
    paired['lcoe_change_pct'] = 100*(paired.lcoe_elec_new/paired.lcoe_elec_old-1)
    rows.append(paired)
    corners = paired[((paired.tau_ms==50)&(paired.phi==0))|((paired.tau_ms.isin([50,500]))&(paired.phi==1))]
    for keys,part in corners.groupby(['year','tau_ms','phi']):
        year,tau,phi = keys
        medians.append({'source_table':name,'year':int(year),'tau_ms':int(tau),'phi':float(phi),'n':len(part),
                        'old_pi_median_pct':float(part.pi_old_pct.median()),'new_pi_median_pct':float(part.pi_new_pct.median()),
                        'old_gen_median':float(part.lcoe_gen_old.median()),'new_gen_median':float(part.lcoe_gen_new.median()),
                        'old_storage_median':float(part.lcoe_store_old.median()),'new_storage_median':float(part.lcoe_store_new.median()),
                        'old_total_median':float(part.lcoe_elec_old.median()),'new_total_median':float(part.lcoe_elec_new.median()),
                        'paired_median_total_change_pct':float(part.lcoe_change_pct.median())})
pd.concat(rows,ignore_index=True).to_csv(HERE/'fig5_old_new_country_comparison.csv',index=False)
pd.DataFrame(medians).to_csv(HERE/'fig5_old_new_medians.csv',index=False)
print(pd.DataFrame(medians).to_string(index=False),flush=True)

costs = []
for year in [2025,2030,2035,2040,2045,2050]:
    for case,column in [('high','Conservative'),('central','Moderate'),('low','Advanced')]:
        e_li,e_ld = R.F.e_costs(case,year)
        gross = float(np.interp(year,R.F.P._ATB_YR,R.F.P._ATB[column].to_numpy(float)))
        costs.append({'year':year,'case':case,'li_4h_system_capex_usd_per_kwh':gross,
                      'li_power_usd_per_kw':280.0,'li_energy_component_usd_per_kwh':e_li,
                      'ldes_power_usd_per_kw':1000.0,'ldes_energy_usd_per_kwh':e_ld})
pd.DataFrame(costs).to_csv(HERE/'table_s21_actual_cost_components.csv',index=False)
print(pd.DataFrame(costs).to_string(index=False),flush=True)

with (HERE/'all_fig5_inputs.pkl').open('rb') as handle:
    original,aliases,jobs = pickle.load(handle)
soft_checks = []
for country in ['US','DE','PS']:
    for tau,phi in [(50,0.),(500,1.)]:
        job = jobs[aliases[(country,2025,tau,phi)]]
        result = R.solve_one((job,'original_soft',0))
        result['scenario'] = 'current_inputs_and_costs_original_soft_2025'
        soft_checks.append(result)
        print(country,tau,result['lcoe_elec'],100*result['pi'],result['unmet_mwh'],flush=True)
pd.DataFrame(soft_checks).to_csv(HERE/'soft_2025_version_checks.csv',index=False)
