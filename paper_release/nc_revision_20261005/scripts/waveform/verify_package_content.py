from pathlib import Path
import hashlib
import importlib.metadata
import json
import platform

import numpy as np
import pandas as pd
from PIL import Image


ROOT=Path(__file__).resolve().parents[2]
RESULTS=ROOT/'results/waveform'


def main():
    names=['country_hourly_demand.csv.gz','site_hourly_cf.parquet','country_hourly_cf.parquet','country_capacity.csv','country_meta.csv','burstgpt_diurnal_fit_v2.csv','normalization_windows.csv']
    hashes={}
    for name in names:
        path=ROOT/'inputs/hourly'/name
        with path.open('rb') as handle:
            hashes[name]=hashlib.file_digest(handle,'sha256').hexdigest()
    expected={'objective_results.csv':104,'lp_certificates.csv':312,'normalized_separation_certificates.csv':208,'r2_waveform_grid.csv':3744,'business_consumer_country_results.csv':520,'business_consumer_key_country_grid.csv':1080,'window_weight_country_results.csv':1040,'window_normalization_audit.csv':1248}
    rows={}
    for name,count in expected.items():
        df=pd.read_csv(RESULTS/name,keep_default_na=False)
        if len(df)!=count:
            raise ValueError(f'Unexpected row count: {name}, {len(df)} != {count}')
        rows[name]=len(df)
    if len(list((RESULTS/'certificates').glob('*.npz')))!=104:
        raise ValueError('Missing hourly LP certificate files')
    with np.load(RESULTS/'hourly_separating_vectors.npz',allow_pickle=False) as cert:
        for c in ['US','GB','DE','CN','IN','AU']:
            for field in ['r_proxy_raw','rbar','partner_sbar','fixed_nnls_residual_h','lp_domestic_residual_h']:
                if f'{c}_{field}' not in cert.files:
                    raise ValueError(f'Missing hourly vector: {c}, {field}')
    original=json.loads((RESULTS/'original_grid_validation.json').read_text(encoding='utf-8'))
    if original['grid_rows']!=3744 or max(original['grid_max_absolute_difference'].values())>1e-7:
        raise ValueError('Final-package grid validation failed')
    smoke=pd.read_csv(RESULTS/'validation_smoke/window_weight_country_results.csv',keep_default_na=False)
    if len(smoke)!=30 or smoke.country.nunique()!=3:
        raise ValueError('Final-package normalization-window smoke check is incomplete')
    figures={}
    for stem in ['FigS6_conditional_certificate','FigS7_demand_and_window_sensitivity']:
        with Image.open(ROOT/'figures'/f'{stem}.png') as img:
            dpi=img.info['dpi']
            if min(dpi)<299:
                raise ValueError(f'PNG below 300 dpi: {stem}, {dpi}')
            figures[stem]={'pixels':img.size,'dpi':dpi,'pdf_bytes':(ROOT/'figures'/f'{stem}.pdf').stat().st_size}
    report={'status':'passed','verification_date':'2026-10-02','platform':platform.platform(),'python':platform.python_version(),'versions':{name:importlib.metadata.version(name) for name in ['numpy','pandas','scipy','pyarrow','threadpoolctl','matplotlib','pillow']},'hourly_input_sha256':hashes,'result_row_counts':rows,'country_certificate_npz_count':104,'explicit_hourly_separating_vectors_present':True,'package_default_paths_full_grid_execution':original,'package_default_normalization_windows_smoke_rows':len(smoke),'package_default_normalization_windows_smoke_countries':smoke.country.nunique(),'figures':figures}
    (RESULTS/'package_execution_validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
