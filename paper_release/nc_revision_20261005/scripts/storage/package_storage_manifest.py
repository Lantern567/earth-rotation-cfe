import hashlib
import json
from pathlib import Path

root = Path.cwd().resolve()
source = root/'collective_attention_research_plan'
paths = [
    source/'data/cloudflare_global_demand/country_hourly_demand.csv.gz',
    source/'data/global_renewable_sites/country_hourly_cf.parquet',
    source/'data/global_renewable_sites/country_capacity.csv',
    source/'data/global_renewable_sites/country_meta.csv',
    root/'inputs/hourly/normalization_windows.csv',
]
paths += [source/'scripts'/name for name in [
    'run_dispatch_cost_full.py','storage_dispatch_lp.py','analyze_cfe_r3_waveform_cost.py',
    'analyze_cfe_global_sites.py','analyze_cfe_geographic_portfolio_ai.py','fullsystem_cost_params.py'
]]
paths += [source/'reports/cfe_geographic_portfolio_ai/data_globalsites'/name for name in [
    'nrel_atb_2024_battery_4h.csv','r3_dispatch_cost_table.csv',
    'r3_dispatch_grid_2030.csv','r3_dispatch_yearly_phi1.csv'
]]
records = []
for path in paths:
    records.append({'path':path.relative_to(root).as_posix(),'bytes':path.stat().st_size,
                    'sha256':hashlib.file_digest(path.open('rb'),'sha256').hexdigest()})
manifest = {'default_project_root':'.','scientific_source_root':'collective_attention_research_plan',
            'revision_scripts':'scripts/storage','complete_results':'results/storage',
            'cache_files_included':False,'files':records}
target = root/'inputs/storage/portable_support_manifest.json'
target.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(f'Wrote {len(records)} real input/helper records to {target}')
