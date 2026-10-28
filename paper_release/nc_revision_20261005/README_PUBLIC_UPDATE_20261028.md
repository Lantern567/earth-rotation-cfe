# Public NC revision update 28 October 2026

This update is published as additional assets of the existing release `v1.2.0-nc-revision`. The tag and its commit remain unchanged. Use `NC_Revision_Reproducibility_Package_20261028_v3.zip` as the complete current scientific archive, and extract `NC_Revision_Update_20261028.zip` into the same directory to add the current publication guide and source-data index. Both archives have the top-level directory `Reproducibility_Package`.

The main manuscript is v14 and SI is v13. Scientific main results retain the original 39 receiver candidates. SI S32 and Tables S43-S44 report the operating-region evidence and the completed 34-country sensitivity, excluding DK, EG, GR, KW and TR while retaining all 104 demand countries. The 500-ms/full-routing median remains 12.7142%; the fixed-shortfall routing LP median remains 12.2081%. Table S44 also reports country effects under tighter latency limits.

## Published contents

- The complete archive v3 contains all eight restored hourly inputs, original computations, Source Data, frozen results and numerical certificates. No raw request traces or private reviewer correspondence are added.
- `results/load_smoothing/` and `results/load_smoothing_eligibility/` supply Figure S10 plotting values, metadata and verification tables. `scripts/load_smoothing/` supplies its three scientific scripts and `requirements_load_smoothing.txt` supplies the pinned dependencies.
- `receiver_sensitivity/` supplies summary CSV/JSON files and the original generation scripts. Large job pickle files and duplicate hourly inputs are excluded from this incremental update. The full v3 archive separately retains the numerical certificates. These scripts preserve their original audit execution layout as provenance; their local path setup is not a separate portable command interface. The original analysis functions and supplied hourly inputs are in the complete archive.
- `revision_integration/Receiver_Region_Evidence_20261028_v2.csv` supplies the updated provider evidence. Denmark East opened in March 2026, after the 2025-12-31 operating-region cutoff.
- `revision_audit/render_maps.py` and `revision_audit/plotting/` reproduce the coordinate-labelled Figure 3 and Figure 5 from frozen numerical results. The delivered original PDF/PNG figures are in `figures/`.
- `Source_Data_NC_Revision.xlsx` retains the 63-sheet coverage described in Data availability. Figure S10 and receiver-sensitivity tables are provided separately at the paths above.

## Verify Figure S10 without optimization

From the extracted `Reproducibility_Package` directory:

```text
python -m pip install -r requirements_load_smoothing.txt
python -B scripts/load_smoothing/plot_mismatch_sensitivity.py --input-dir results/load_smoothing --eligibility-dir results/load_smoothing_eligibility --output-dir figures
```

The second command verifies the delivered numerical tables without generating new optimization results. Add `--render` to regenerate the figure. Full reconstruction commands are retained in `README_load_smoothing.md`.

## Redraw coordinate-labelled maps

```text
python -m pip install -r requirements_figures.txt
python -m pip install frykit_data==0.1.0
python revision_audit/render_maps.py --package-root . --output-dir figures
```

This reads frozen CSV files and invokes plotting only. Map-source and licence evidence is supplied with the submission materials.

## Publication and integrity

The existing October 5 assets remain the earlier release snapshot. The complete v3 archive retains its dated local-audit README files unchanged; this guide and the release's `2026-10-28 update` section state the current public availability. The old load-smoothing README's local table numbering predates the final SI organization: Figure S10 is in S31, while Tables S43-S44 concern receiver eligibility in S32.

`PUBLIC_UPDATE_MANIFEST_20261028.json` hashes every file in this incremental update. `NC_Release_Update_20261028_SHA256SUMS.txt` hashes the separately downloadable assets. The release describes the file hashes and the unchanged tag commit. Code uses MIT and newly generated derived data use CC BY 4.0 under `DATA_LICENSE.md`; third-party material retains its original terms.
