import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from run_mix_sensitivity import original_definitions


work = Path(__file__).resolve().parent
package = work.parents[2] / 'NC返修_20261002/Reproducibility_Package'
assert json.loads((work / 'reproduction_check.json').read_text(encoding='utf-8'))['passed']
path = package / 'scripts/waveform/run_waveform_revision.py'
spec = importlib.util.spec_from_file_location('original_station_mix_receiver_check', path)
W = importlib.util.module_from_spec(spec)
spec.loader.exec_module(W)
W.DATA = work / 'inputs'
W.CONSUMER_PROFILE = package / 'inputs/reference/figS2/burstgpt_diurnal_fit_v2.csv'
assert W.CONSUMER_PROFILE.is_file()
B = original_definitions(package / 'collective_attention_research_plan/scripts/analyze_cfe_geographic_portfolio_ai.py',
    ['operator_mix'], ['PMIX_ALPHA_BATCH', 'PMIX_ALPHA_INTERACTIVE', 'PMIX_ALPHA_BURST', 'P2_PEAK_HOUR', 'P2_SIGMA_H', 'P3_GAMMA'], {'np': np})
started = time.perf_counter()
with threadpool_limits(limits=1):
    inputs = W.load_data()
    idx, countries, demand, home, shapes, hours, reach39, meta = inputs
    reach34 = {c: {t: [r for r in rs if r not in {'DK', 'EG', 'GR', 'KW', 'TR'}] for t, rs in row.items()} for c, row in reach39.items()}
    station_mix_rows = []
    for count, reach in [(39, reach39), (34, reach34)]:
        W.HERE = work / f'business_station_{count}'
        W.HERE.mkdir(exist_ok=True)
        W.mix_analysis((idx, countries, demand, home, shapes, hours, reach, meta))
        if count == 39:
            reference = pd.read_csv(package / 'results/waveform/business_consumer_country_results.csv', keep_default_na=False)
            reproduced = pd.read_csv(W.HERE / 'business_consumer_country_results.csv', keep_default_na=False)
            keys = ['country', 'business_fraction_of_inference']
            reference = reference.set_index(keys).sort_index()
            reproduced = reproduced.set_index(keys).sort_index()
            assert reference.index.equals(reproduced.index)
            errors = (reference[['domestic_uncovered_share', 'routed_uncovered_share']] - reproduced[['domestic_uncovered_share', 'routed_uncovered_share']]).abs().max().to_dict()
            assert max(errors.values()) < 1e-10, errors
            print('BUSINESS39_REPRODUCTION_PASSED ' + json.dumps(errors), flush=True)
        for c in countries:
            d = B.operator_mix(demand[c], hours[c], .308, .132)
            local = W.fit_nnls(d, home[c])[1]
            p = np.column_stack([shapes[r] for r in reach[c][500]])
            u, baseline, _ = W.routed(d, home[c], p, 1., cached_home=local)
            station_mix_rows.append({'country': c, 'receiver_count': count,
                'domestic_U': baseline, 'global_U': u, 'annual_energy_relative_error': float(d.sum() / demand[c].sum() - 1)})
    station = pd.DataFrame(station_mix_rows)
    station.to_csv(work / 'station_mix2030_country_comparison.csv', index=False)
    med = station.groupby('receiver_count')[['domestic_U', 'global_U']].median() * 100
    med.to_csv(work / 'station_mix2030_summary.csv')
    b39 = pd.read_csv(work / 'business_station_39/business_consumer_country_results.csv', keep_default_na=False)
    b34 = pd.read_csv(work / 'business_station_34/business_consumer_country_results.csv', keep_default_na=False)
    business = b39.merge(b34, on=['country', 'business_fraction_of_inference'], suffixes=('_39', '_34'), validate='one_to_one')
    business['change_pp'] = 100 * (business.routed_uncovered_share_34 - business.routed_uncovered_share_39)
    business.to_csv(work / 'business_station_country_comparison.csv', index=False)
    group = 'business_fraction_of_inference'
    business_summary = pd.DataFrame({'domestic_U_percent': b39.groupby(group).domestic_uncovered_share.median() * 100,
        'global_U_39_percent': b39.groupby(group).routed_uncovered_share.median() * 100,
        'global_U_34_percent': b34.groupby(group).routed_uncovered_share.median() * 100})
    business_summary['change_pp'] = business_summary.global_U_34_percent - business_summary.global_U_39_percent
    business_summary.to_csv(work / 'business_station_summary.csv')
    result = {'station_Mix2030': med.to_dict(), 'business39_reproduction_max_absolute_errors': errors,
        'consumer_profile': str(W.CONSUMER_PROFILE), 'consumer_profile_sha256': hashlib.sha256(W.CONSUMER_PROFILE.read_bytes()).hexdigest(),
        'business_all_520_positive_country_scenarios': bool(b34.routed_uncovered_share.gt(0).all()),
        'station_mix_all_104_positive_countries': bool(station[station.receiver_count.eq(34)].global_U.gt(0).all()),
        'station_mix_max_relative_energy_error': float(station.annual_energy_relative_error.abs().max()),
        'seconds': time.perf_counter() - started,
        'scope': 'Unmodified waveform mix_analysis for business/consumer sweep; original operator_mix with original station fit/routing for new cross-basis 2030 Mix corner comparison'}
    (work / 'station_mix_summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('STATION_MIX_SENSITIVITY_COMPLETE ' + json.dumps(result), flush=True)
