import argparse
import hashlib
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

parser = argparse.ArgumentParser()
parser.add_argument('--project-root',type=Path,required=True)
parser.add_argument('--reference-output',type=Path,required=True)
parser.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parent)
args = parser.parse_args()
package = args.project_root.resolve()
reference = args.reference_output.resolve()
expected = pd.read_csv(reference/'strict_reliability_2030.csv',keep_default_na=False)
records = []
for directory in ['storage_smoke','storage_package_check']:
    outputs = package/'outputs'/directory
    metadata = json.loads((outputs/'inputs_2030.json').read_text(encoding='utf-8'))
    assert Path(metadata['source_root']).resolve()==package
    actual = pd.read_csv(outputs/'strict_reliability_2030.csv',keep_default_na=False)
    assert len(actual)==4
    comparison = actual.merge(expected,on=['country','year','tau_ms','phi','mode'],suffixes=('_package','_reference'),validate='one_to_one')
    assert len(comparison)==4
    error = float(np.max(np.abs(comparison.lcoe_elec_package-comparison.lcoe_elec_reference)))
    assert error<1e-6
    with (outputs/'dispatch_inputs_2030.pkl').open('rb') as handle:
        inputs = pickle.load(handle)
    with (reference/'dispatch_inputs_2030.pkl').open('rb') as handle:
        reference_inputs = pickle.load(handle)
    assert len(inputs)==len(reference_inputs)==208
    max_array_error = 0.0
    max_cost_error = 0.0
    for a,b in zip(inputs,reference_inputs):
        assert (a['cc'],a['tier'])==(b['cc'],b['tier'])
        for field in ['d_mw','fit_mw']:
            max_array_error = max(max_array_error,float(np.max(np.abs(a[field]-b[field]))))
        for field in ['gen1','anc1','ecl','ecd']:
            max_cost_error = max(max_cost_error,float(abs(a[field]-b[field])))
    assert max_array_error==0.0
    assert max_cost_error==0.0
    records.append({'output':directory,'dispatch_rows':4,'countries':sorted(actual.country.unique().tolist()),
                    'source_root_in_package':True,'input_jobs_identical':208,'input_array_max_error':max_array_error,
                    'cost_parameter_max_error':max_cost_error,'dispatch_max_lcoe_error_usd_per_mwh':error})
report = {'portable_checks':records,'used_external_scientific_input_paths':False,
          'commands':['python scripts/storage/run_storage_revision.py --mode reliability --countries DE --workers 1 --output-dir outputs/storage_package_check']}
args.output_dir.mkdir(parents=True,exist_ok=True)
(args.output_dir/'portable_storage_validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
