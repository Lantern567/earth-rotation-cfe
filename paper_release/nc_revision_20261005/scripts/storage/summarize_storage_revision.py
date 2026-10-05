import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

configuration = argparse.ArgumentParser()
configuration.add_argument('--project-root',type=Path,required=True)
configuration.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parent)
config = configuration.parse_args()
HERE = config.output_dir.resolve()
FROZEN = config.project_root.resolve()/'collective_attention_research_plan/reports/cfe_geographic_portfolio_ai/data_globalsites'


def summarize(data, groups):
    results = []
    for keys, part in data.groupby(groups,dropna=False):
        values = keys if isinstance(keys,tuple) else (keys,)
        row = {name:value.item() if isinstance(value,np.generic) else value for name,value in zip(groups,values)}
        row['n'] = len(part)
        for field in ['lcoe_gen','lcoe_store','lcoe_anc','lcoe_elec','P_li','E_li','P_ld','E_ld']:
            row[field+'_median'] = float(part[field].median())
        row['pi_median_pct'] = float((((part['lcoe_elec']-part['lcoe_gen'])/part['lcoe_gen'])*100).median())
        if 'unmet_mwh' in part:
            row['unmet_mwh_max'] = float(part['unmet_mwh'].max())
            row['unmet_mwh_median'] = float(part['unmet_mwh'].median())
            row['countries_with_unmet'] = int((part['unmet_mwh']>1e-7).sum())
            row['firm_share_min'] = float(part['firm_share'].min())
        results.append(row)
    return results


def main():
    results = {}
    main_path = HERE/'strict_reliability_2030.csv'
    if main_path.exists():
        data = pd.read_csv(main_path,keep_default_na=False)
        results['main_reliability'] = summarize(data,['mode','tier'])
        strict = data[data['mode']=='strict']
        if len(strict)==208:
            pivot = strict.pivot(index='country',columns='tier',values=['lcoe_elec','E_li','E_ld','lcoe_store'])
            results['paired_main'] = {}
            for field in ['lcoe_elec','E_li','E_ld','lcoe_store']:
                relative = (pivot[field]['local']-pivot[field]['global'])/pivot[field]['local']*100
                results['paired_main'][field+'_paired_median_reduction_pct'] = float(relative.replace([np.inf,-np.inf],np.nan).median())
                results['paired_main'][field+'_paired_n'] = int((pivot[field]['local']>0).sum())
            results['strict_constraint_maxima'] = {field:float(strict[field].astype(float).max()) for field in ['equality_max_abs_error_mw','inequality_max_violation_mw','bound_max_violation']}
        frozen = pd.read_csv(FROZEN/'r3_dispatch_cost_table.csv',keep_default_na=False)
        results['frozen_main'] = summarize(frozen[frozen.year==2030],['tier'])
    deadlines = HERE/'batch_deadlines_2030.csv'
    if deadlines.exists():
        batch = pd.read_csv(deadlines,keep_default_na=False)
        results['deadlines'] = summarize(batch,['deadline_h'])
        if len(batch)==416:
            baseline = batch[batch.deadline_h==0].set_index('country')
            paired = []
            for deadline in [1,6,24]:
                chosen = batch[batch.deadline_h==deadline].set_index('country')
                row = {'deadline_h':deadline}
                for field in ['lcoe_elec','lcoe_store','E_li','E_ld']:
                    eligible = baseline[field]>0
                    reductions = (baseline.loc[eligible,field]-chosen.loc[eligible,field])/baseline.loc[eligible,field]*100
                    row[field+'_paired_median_reduction_pct'] = float(reductions.median())
                    row[field+'_paired_n'] = int(eligible.sum())
                paired.append(row)
            results['paired_deadlines'] = paired
            results['batch_checks'] = {field:float(batch[field].astype(float).max()) for field in ['batch_energy_error_mwh','equality_max_abs_error_mw','inequality_max_violation_mw','bound_max_violation']}
            results['batch_checks']['max_deadline_backlog_excess_mwh'] = float((batch.batch_backlog_max_mwh-batch.deadline_h*batch.batch_arrival_mw).max())
            results['batch_checks']['max_cost_increase_wider_deadline_usd_yr'] = float(batch.sort_values(['country','deadline_h']).groupby('country').objective_usd_yr.diff().max())
            results['batch_checks']['all_104_country_work_conserved_and_zero_unmet'] = bool((batch.unmet_mwh==0).all() and batch.batch_energy_error_mwh.max()<1e-6)
            domestic = strict[strict.tier=='local'].set_index('country')
            results['batch_checks']['zero_deadline_vs_strict_baseline_max_cost_error_usd_per_mwh'] = float((baseline.lcoe_elec-domestic.lcoe_elec).abs().max())
    all_strict = HERE/'r3_dispatch_cost_table.csv'
    if all_strict.exists():
        all_data = pd.read_csv(all_strict,keep_default_na=False)
        results['full_year_tier'] = summarize(all_data,['year','tier'])
    window_path = HERE/'window_storage_sensitivity_2030.csv'
    if window_path.exists():
        windows = pd.read_csv(window_path,keep_default_na=False)
        results['window_storage'] = summarize(windows,['scenario','tier'])
        if len(windows)==36:
            baseline = windows[windows.scenario=='published_equal_scale'][['country','tier','lcoe_elec','lcoe_store','E_li','E_ld']]
            compare = windows.merge(baseline,on=['country','tier'],suffixes=('','_baseline'),validate='many_to_one')
            for field in ['lcoe_elec','lcoe_store','E_li','E_ld']:
                compare[field+'_change_pct'] = (compare[field]/compare[field+'_baseline']-1)*100
                compare[field+'_change_abs'] = compare[field]-compare[field+'_baseline']
            compare.to_csv(HERE/'window_storage_comparison_2030.csv',index=False)
            ranges = []
            for keys,part in compare.groupby(['scenario','tier']):
                if keys[0]=='published_equal_scale':
                    continue
                row = {'scenario':keys[0],'tier':keys[1],'n':len(part)}
                for field in ['lcoe_elec','lcoe_store','E_li','E_ld']:
                    row[field+'_change_pct_min'] = float(part[field+'_change_pct'].min())
                    row[field+'_change_pct_median'] = float(part[field+'_change_pct'].median())
                    row[field+'_change_pct_max'] = float(part[field+'_change_pct'].max())
                ranges.append(row)
            results['window_storage_ranges'] = ranges
            results['window_storage_checks'] = {field:float(windows[field].astype(float).max()) for field in ['proxy_energy_error','equality_max_abs_error_mw','inequality_max_violation_mw','bound_max_violation']}
            results['window_storage_checks']['all_36_zero_unmet'] = bool((windows.unmet_mwh==0).all())
    (HERE/'storage_summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(results,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
