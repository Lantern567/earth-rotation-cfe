# Nature Communications revision: code, inputs and results

This package accompanies **Chasing wind and sun leaves hourly clean power gaps for data centres serving interactive workloads**. Its version is `v1.2.0-nc-revision`, dated 5 October 2026. The earlier `v1.1.0-submission` tag identifies an earlier release. Reviewed input versions and hashes are retained in `inputs/reviewed_submission/input_hashes.json` and the public manifest.

## Contents and execution directory

### Public update 28 October 2026

The current scientific archive is the release asset [NC_Revision_Reproducibility_Package_20261028_v3.zip](https://github.com/Lantern567/earth-rotation-cfe/releases/download/v1.2.0-nc-revision/NC_Revision_Reproducibility_Package_20261028_v3.zip). Extract [NC_Revision_Update_20261028.zip](https://github.com/Lantern567/earth-rotation-cfe/releases/download/v1.2.0-nc-revision/NC_Revision_Update_20261028.zip) into the same directory and follow `Reproducibility_Package/README_PUBLIC_UPDATE_20261028.md`. This supplies the final SI S31/S32 additions, current receiver evidence, coordinate-labelled Figure 3 and Figure 5, and their code. The complete archive contains all eight hourly inputs and the unchanged 63-sheet Source Data workbook. The incremental archive excludes large job pickle files and duplicate input copies.

The tag `v1.2.0-nc-revision` remains at commit `b50e3685ecdb44a7feb44ccdcea39f41561d0abc`. The October 5 assets and Git source snapshot remain available. Release notes and `NC_Release_Update_20261028_SHA256SUMS.txt` identify the current assets and hashes. The archive's dated audit READMEs retain their generation history; the public-update guide records the current publication status.

Figure S10's portable verification command is given in the public-update guide. Receiver generation scripts preserve the original audit layout as provenance; the complete archive provides the original analysis functions, inputs and numerical certificates. Figure S10 is in SI S31; Tables S43-S44 concern receiver eligibility in SI S32.

Run all commands below from this directory:

```text
cd paper_release/nc_revision_20261005
```

The package preserves the relative layout used by the supplied entries: `scripts/`, `inputs/`, `results/`, `figures/` and the required `collective_attention_research_plan/` scientific helpers and frozen inputs. `Source_Data_NC_Revision.xlsx` collects the original Figure 1–4 sources, the complete strict Figure 5 tables and the supplementary results. See `REPRODUCIBILITY_INDEX.md` for the result-to-command crosswalk and `README_waveform.md`, `README_power.md` and `README_storage.md` for exact component commands.

## Restore the large hourly certificate file

The combined hourly certificate file is distributed as a release asset. Its byte size is 273,857,463 and its SHA-256 is:

```text
d32ce1c3e740e40a628e17a673e8e8ef4424399ad5adf2a49861f7ee332943f7
```

Download it into its original package-relative location before running `verify_package_content.py`:

```text
gh release download v1.2.0-nc-revision --repo Lantern567/earth-rotation-cfe --pattern hourly_separating_vectors.npz --dir results/waveform
python -c "from pathlib import Path; import hashlib; p=Path('results/waveform/hourly_separating_vectors.npz'); h=hashlib.file_digest(p.open('rb'),'sha256').hexdigest(); assert h=='d32ce1c3e740e40a628e17a673e8e8ef4424399ad5adf2a49861f7ee332943f7', h; print(h)"
```

The direct asset is [hourly_separating_vectors.npz](https://github.com/Lantern567/earth-rotation-cfe/releases/download/v1.2.0-nc-revision/hourly_separating_vectors.npz). The [release page](https://github.com/Lantern567/earth-rotation-cfe/releases/tag/v1.2.0-nc-revision) also provides [NC_Reproducibility_v1.2.0.zip](https://github.com/Lantern567/earth-rotation-cfe/releases/download/v1.2.0-nc-revision/NC_Reproducibility_v1.2.0.zip), the complete public scientific package with its manifest and hourly certificate file. The automatically generated GitHub source archive contains the Git-tracked files; the separately supplied certificate asset completes the hourly certificate inspection.

## Reconstruct or verify the calculations

The supplied inputs are derived hourly series and aggregates. They permit reconstruction without the original development directories or private provider credentials. Acquisition of original third-party data is documented separately with source URLs and hashes.

```text
python -m pip install -r requirements_waveform.txt
python scripts/waveform/run_waveform_revision.py --data-root inputs/hourly --reference-dir inputs/reference/waveform --output-dir results/waveform --mode all --full-grid
python scripts/waveform/verify_separating_certificates.py --results-dir results/waveform --demand-file inputs/hourly/country_hourly_demand.csv.gz
python scripts/waveform/verify_fig3_statistics.py --data-root inputs/hourly --reference-dir inputs/reference/waveform --output-dir results/waveform
python scripts/waveform/verify_package_content.py
```

The restored hourly certificate file can also be regenerated by `verify_separating_certificates.py` from the supplied result certificates. To inspect the frozen published package directly, restore the asset and use the verification command without rerunning optimization.

```text
python -m pip install -r requirements_power.txt
python scripts/power/run_power_case.py
python scripts/power/finalize_power_evidence.py
python scripts/power/plot_and_price_power_case.py
python -m pip install -r requirements_storage.txt
python scripts/storage/verify_storage_outputs.py
```

Full strict-dispatch regeneration and separate replay commands are specified in `README_storage.md`. Component requirements record the verified library versions.

## Calculation stages and scientific scope

Figures 2 and 3 retain the initial domestic NNLS fit, allocate partner coverage against its specified shortfall, and subtract that coverage. Those results contain no post-routing domestic refit. Their annual-demand residual is distinct from a unit-shortfall routing certificate and from the separate complete LP pipeline.

Figure 5 uses a separate stage: after routing, domestic supply is refitted to remaining demand. Remaining demand and supply are then jointly scaled by the same factor, calculated separately for each scenario, to 100 MW mean remaining domestic load before dispatch. Costs are expressed per MWh of that remaining domestic demand; they exclude the receiving site's compute and electricity costs.

The revised paper's primary Figure 5 tables enforce strict zero unserved demand in every hour. `original_soft` results audit the previous finite-VOLL implementation and document achieved reliability; they are reported separately from the revised strict-service results. The full strict tables contain 1,248 cost rows, 3,744 routing-grid rows and 3,744 yearly rows.

Requests and tokens remain activity evidence. The three-site power study is a scenario with stated origins, capacities, power interpolation, clean-supply budgets and network allowances, with the same interactive work and finite background pool across policies. It does not certify measured electricity or request-tail SLOs. Business timing, traffic-window weights, completion deadlines, electricity prices and routing-fee values retain their explicitly stated assumption boundaries.

## Integrity, provenance and licences

`PUBLIC_MANIFEST.json` gives each public file's SHA-256, byte size and Git or Release storage location. Reviewed input hashes retain file basenames and version identifiers.

Code is licensed under MIT; newly generated derived data are licensed under CC BY 4.0 under `DATA_LICENSE.md`. Copies of `LICENSE` and `DATA_LICENSE.md` are included in this directory for the standalone archive. Third-party data retain their original licences, attribution requirements and source terms.
