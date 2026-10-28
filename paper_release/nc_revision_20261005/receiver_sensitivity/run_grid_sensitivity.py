import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from zipfile import ZipFile

os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
import scipy
from threadpoolctl import threadpool_limits

work = Path(__file__).resolve().parent
root = work.parents[2]
package = root / 'NC返修_20261002/Reproducibility_Package'
archive = root / 'NC返修_20261002/NC_Revision_Package.zip'
digest = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
inputs_dir = work / 'inputs'
inputs_dir.mkdir(exist_ok=True)
filenames = ['country_meta.csv', 'country_hourly_demand.csv.gz', 'site_hourly_cf.parquet', 'country_hourly_cf.parquet', 'country_capacity.csv']
records = {}
prefix = 'NC返修_20261002/Reproducibility_Package/inputs/hourly/'
with ZipFile(archive) as zipped:
    package_manifest = json.loads(zipped.read('NC返修_20261002/Reproducibility_Package/PACKAGE_MANIFEST.json').decode('utf-8'))
    for name in filenames:
        member = prefix + name
        target = inputs_dir / name
        payload = zipped.read(member)
        target.write_bytes(payload)
        checksum = hashlib.sha256(payload).hexdigest()
        records[name] = {'path_used': str(target), 'sha256': checksum, 'archive': str(archive), 'archive_member': member, 'bytes': len(payload)}
        candidates = [entry for entry in package_manifest.get('files', []) if entry.get('path') == 'inputs/hourly/' + name]
        if candidates:
            assert candidates[0]['sha256'] == checksum, name
            records[name]['archived_manifest_sha256_matches'] = True
script = package / 'scripts/waveform/run_waveform_revision.py'
spec = importlib.util.spec_from_file_location('receiver_waveform_original', script)
W = importlib.util.module_from_spec(spec)
spec.loader.exec_module(W)
W.DATA = inputs_dir
W.FROZEN = package / 'inputs/reference/waveform'
W.DEVELOPMENT_LAYOUT = False
W.HERE = work / 'receivers39'
W.HERE.mkdir(exist_ok=True)
protected = {str(script): digest(script), str(W.FROZEN / 'r2_waveform_grid.csv'): digest(W.FROZEN / 'r2_waveform_grid.csv')}
provenance = {'runtime': {'executable': sys.executable, 'python': sys.version, 'numpy': np.__version__, 'pandas': pd.__version__, 'scipy': scipy.__version__}, 'inputs': records, 'original_script': str(script), 'original_script_sha256': digest(script), 'archive_sha256': digest(archive), 'excluded_receivers': ['DK', 'EG', 'GR', 'KW', 'TR'], 'protected_input_sha256': protected}
(work / 'input_provenance.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding='utf-8')
started = time.perf_counter()
with threadpool_limits(limits=1):
    inputs = W.load_data()
    actual39 = sorted(set(inputs[1]) & W.HYPERSCALERS)
    assert len(actual39) == 39
    print('INPUTS_READY countries=104 receivers=39 hours=8760', flush=True)
    baseline_start = time.perf_counter()
    W.rebuild_original_grid(inputs)
    keys = ['country', 'tau_ms', 'phi']
    frozen = pd.read_csv(W.FROZEN / 'r2_waveform_grid.csv', keep_default_na=False).set_index(keys).sort_index()
    reproduced = pd.read_csv(W.HERE / 'r2_waveform_grid.csv', keep_default_na=False).set_index(keys).sort_index()
    assert reproduced.index.equals(frozen.index)
    numeric = ['reach_km', 'n_partners', 'uncovered_share', 'uncovered_share_baseline', 'migrated_share']
    errors = {column: float((reproduced[column] - frozen[column]).abs().max()) for column in numeric}
    assert max(errors.values()) < 1e-7, errors
    reproduction = {'rows': len(reproduced), 'countries': 104, 'actual_receivers': actual39, 'max_absolute_errors': errors, 'seconds': time.perf_counter() - baseline_start, 'passed': True, 'baseline_function': 'Original load_data + original rebuild_original_grid without code changes'}
    (work / 'reproduction_check.json').write_text(json.dumps(reproduction, ensure_ascii=False, indent=2), encoding='utf-8')
    print('BASELINE_REPRODUCTION_PASSED ' + json.dumps(errors), flush=True)

    idx, countries, demand, home, shapes, hours, reach39, meta = inputs
    excluded = set(provenance['excluded_receivers'])
    actual34 = sorted(set(actual39) - excluded)
    assert len(actual34) == 34
    reach34 = {country: {tau: [r for r in reach39[country][tau] if r in actual34] for tau in W.TAUS} for country in countries}
    region_names = {'AF': 'Africa/MENA', 'AS': 'Asia-Pacific', 'EU': 'Europe', 'NA': 'North America', 'SA': 'Latin America', 'OC': 'Asia-Pacific', 'AN': 'Other'}
    rows = []
    reduced_start = time.perf_counter()
    domestic_rows = []
    for ci, country in enumerate(countries):
        d = demand[country]
        local = W.fit_nnls(d, home[country])[1]
        domestic_rows.append({'country': country, 'domestic_U': float(np.maximum(d - local, 0).sum() / d.sum())})
        for tau in W.TAUS:
            partners = reach34[country][tau]
            matrix = np.column_stack([shapes[r] for r in partners]) if partners else np.empty((len(idx), 0))
            for phi in W.PHIS:
                residual, baseline, covered = W.routed(d, home[country], matrix, phi, cached_home=local)
                rows.append({'country': country, 'region': region_names.get(meta.loc[country, 'region_code'], 'Other'), 'continent': meta.loc[country, 'continent_block'], 'tau_ms': tau, 'phi': phi, 'reach_km': round(max(200 * (tau / (2 * 1.4) - 20), 0)), 'n_partners': len(partners), 'uncovered_share': residual, 'uncovered_share_baseline': baseline, 'migrated_share': float(covered.sum() / d.sum())})
        if (ci + 1) % 20 == 0:
            print(f'RECEIVERS34_GRID {ci+1}/104 seconds={time.perf_counter()-reduced_start:.1f}', flush=True)
    reduced = pd.DataFrame(rows)
    assert len(reduced) == 3744
    reduced.to_csv(work / 'r2_waveform_grid_34.csv', index=False)
    pd.DataFrame(domestic_rows).to_csv(work / 'domestic_station_nnls.csv', index=False)
    pd.DataFrame({'receiver_iso2': actual39, 'retained_in_34': [r in actual34 for r in actual39]}).to_csv(work / 'receiver_sets.csv', index=False)
    med39 = reproduced.reset_index().groupby(['phi', 'tau_ms']).uncovered_share.median() * 100
    med34 = reduced.groupby(['phi', 'tau_ms']).uncovered_share.median() * 100
    summary = pd.DataFrame({'median_U_39_percent': med39, 'median_U_34_percent': med34})
    summary['difference_pp'] = summary.median_U_34_percent - summary.median_U_39_percent
    summary.to_csv(work / 'fig2_heatmap_comparison.csv')
    for name, values in [('39', med39), ('34', med34), ('difference_pp', summary.difference_pp)]:
        values.unstack('tau_ms').reindex(W.PHIS).to_csv(work / f'fig2_heatmap_{name}.csv')
    merged = reproduced.reset_index().merge(reduced, on=keys, suffixes=('_39', '_34'), validate='one_to_one')
    merged['change_pp'] = 100 * (merged.uncovered_share_34 - merged.uncovered_share_39)
    merged.to_csv(work / 'fig2_country_grid_comparison.csv', index=False)
    global_rows = merged[merged.tau_ms.eq(500) & merged.phi.eq(1)].copy()
    global_rows['absolute_change_pp'] = global_rows.change_pp.abs()
    global_rows.sort_values('absolute_change_pp', ascending=False).head(10).to_csv(work / 'top10_global_affected_countries.csv', index=False)
    country_max = merged.loc[merged.groupby('country').change_pp.apply(lambda v: v.abs().idxmax())]
    country_max = country_max.assign(absolute_change_pp=country_max.change_pp.abs()).sort_values('absolute_change_pp', ascending=False)
    country_max.head(10).to_csv(work / 'top10_any_tier_affected_countries.csv', index=False)
    result = {'baseline_seconds': reproduction['seconds'], 'reduced_seconds': time.perf_counter() - reduced_start, 'total_seconds': time.perf_counter() - started, 'actual_receivers_39': actual39, 'actual_receivers_34': actual34, 'global_39_median_percent': float(med39.loc[(1.0, 500)]), 'global_34_median_percent': float(med34.loc[(1.0, 500)]), 'domestic_39_median_percent': float(med39.loc[(0.0, 50)]), 'domestic_34_median_percent': float(med34.loc[(0.0, 50)]), 'global_34_positive_country_count': int((global_rows.uncovered_share_34 > 0).sum()), 'max_absolute_heatmap_difference_pp': float(summary.difference_pp.abs().max()), 'max_absolute_country_difference_pp': float(merged.change_pp.abs().max()), 'global_country_increase_count': int((global_rows.change_pp > 1e-7).sum()), 'global_country_decrease_count': int((global_rows.change_pp < -1e-7).sum())}
    (work / 'grid_summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    for path, checksum in protected.items():
        assert digest(path) == checksum
    print('GRID_SENSITIVITY_COMPLETE ' + json.dumps(result), flush=True)
