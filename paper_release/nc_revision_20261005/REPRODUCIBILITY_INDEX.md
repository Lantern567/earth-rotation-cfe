# NC revision calculations and source data

This package is version `v1.2.0-nc-revision` for “Chasing wind and sun narrows but does not close the same-hour clean-power gap for interactive data centres”. It supplies real derived hourly inputs, the reconstructed submitted waveform results, new conditional sensitivities and strict full-service dispatch results. The reviewed inputs are main manuscript rev39 and supplement rev37; their SHA-256 values are retained in `inputs/reviewed_submission/input_hashes.json` using original file basenames. The public `v1.1.0-submission` tag identifies an earlier release.

Run commands from this archive directory. Paths resolve relative to the archive and require no original E drive or development checkout. The installed versions and input checksums are recorded in the component requirements and manifests. Figures 1–4 retain their submitted numerical sources; Figure 2 and Figure 3 are additionally reconstructed from hourly inputs. Figure 5 is replaced throughout with strict zero-unserved dispatch. Source Data contains the complete figure tables and new sensitivities.

For a frozen-result inspection, restore `results/waveform/hourly_separating_vectors.npz` from the release asset as described in `README.md`. Its hash and Git/Release storage locations are recorded in `PUBLIC_MANIFEST.json`. A full reconstruction also regenerates that file from the supplied country certificate arrays.

| Paper output | Supplied input and calculation | Output and validation |
| --- | --- | --- |
| Figures 1 and 4 | Reviewed frozen source workbooks in `inputs/reference/figures`; input descriptions in SI S9–S10 | Preserved source sheets in `Source_Data_NC_Revision.xlsx`; these figures retain their submitted calculations |
| Figure 2 | `scripts/waveform/run_waveform_revision.py --mode grid --full-grid`; `inputs/hourly` | Full 104-country × 36 grid, intermediate fits and original-grid comparison in `results/waveform` |
| Figure 2 baseline label | `scripts/figures/plot_r2_latency_fig2.py`; frozen original grid and style in `inputs/reference` | “Domestic only” replaces the status-quo interpretation; other pixels and all numerical sources are unchanged, verified in `results/fig2/validation.json` |
| Figure 3 | Same waveform entry and `scripts/waveform/verify_fig3_statistics.py` | Four attribution tables, mean-coverage summaries and receiver solar-time summaries |
| SI S24 and Fig S6 | `scripts/waveform/run_waveform_revision.py --mode objective`; `verify_separating_certificates.py` | 312 solver certificates, 208 normalized routing separation checks, explicit hourly arrays, domestic refit comparisons |
| SI S26 and Fig S7 | Waveform entry with `--mode mix` or `--mode windows` | Business–consumer results for 104 countries and six-country full grids; window factors and conditional matching results |
| SI S25 and Fig S8 | `scripts/power/run_power_case.py`, `finalize_power_evidence.py`, `plot_and_price_power_case.py`; `inputs/power` | Thirty finite-site cases, complete power/flow/background ledgers, facility and power-curve sensitivities and verification |
| Figure 5 and SI S22 | Storage entries listed in `README_storage.md`; real hourly inputs and scientific helpers in `collective_attention_research_plan` | Strict cost table 1,248 rows, grid 3,744 rows and yearly table 3,744 rows in `results/storage` |
| SI S16 and S27 | Strict reliability and batch entries in `scripts/storage` | 208 strict core cases, 208 `original_soft` implementation-audit cases, 416 strict batch cases and 12 labelled target/cycle sensitivities; achieved service and feasibility per case |
| SI S26 storage | `scripts/storage/run_window_storage_sensitivity.py` | Thirty-six strict selected-country window-scale cases and paired comparisons |
| SI S28 | `scripts/power/plot_and_price_power_case.py` | Frozen-ledger hypothetical prices and fee thresholds; no observed tariff or contract claim |
| Revised Figure 5 and Fig S9 | `scripts/figures/plot_strict_revision.py` | PDF and 300-dpi PNG figures from complete strict tables; Figure 5 retains the submitted four-panel presentation |

## Final SI additions 28 October 2026

The existing [v1.2.0-nc-revision release](https://github.com/Lantern567/earth-rotation-cfe/releases/tag/v1.2.0-nc-revision) provides `NC_Revision_Reproducibility_Package_20261028_v3.zip` and the incremental `NC_Revision_Update_20261028.zip`. Extract both into the same directory. Paths below are relative to `Reproducibility_Package` in the downloaded assets, or this package directory for the committed additions. `PUBLIC_UPDATE_MANIFEST_20261028.json` records the files supplied by the incremental release, including figures distributed as assets.

| Final output | Inputs and code | Frozen evidence |
| --- | --- | --- |
| SI S31, Figure S10 | `scripts/load_smoothing/run_sensitivity.py`, `run_eligibility_lp.py`, `plot_mismatch_sensitivity.py`; `requirements_load_smoothing.txt`; hourly inputs in the complete archive | `results/load_smoothing/FigS10_plot_values.csv`, `FigS10_plot_metadata.json`; matching and eligibility tables in `results/load_smoothing/` and `results/load_smoothing_eligibility/` |
| SI S32, Table S43 | Official provider evidence at the 2025-12-31 operating-region cutoff | `revision_integration/Receiver_Region_Evidence_20261028_v2.csv` |
| SI S32, Table S44 | Original 39 receiver candidates versus 34 operating-region countries; all 104 demand countries retained | `receiver_sensitivity/headline_comparison.csv`, `fig2_heatmap_comparison.csv`, `top10_any_tier_affected_countries.csv`, LP and 2030 dispatch comparison CSV/JSON files; original generation scripts and provenance in that directory |
| Coordinate-labelled Figures 3 and 5 | `revision_audit/render_maps.py` and `revision_audit/plotting/`; frozen original routing and storage tables | Original PDF/PNG figures in the current release assets; input and plotting checks in `revision_audit/map_redraw_validation.json` |

To verify Figure S10 plotting values without optimization:

```text
python -m pip install -r requirements_load_smoothing.txt
python -B scripts/load_smoothing/plot_mismatch_sensitivity.py --input-dir results/load_smoothing --eligibility-dir results/load_smoothing_eligibility --output-dir figures
```

Receiver generation scripts retain their original audit execution layout; their path initialization is recorded as provenance. The complete archive supplies the original waveform and storage entry points and the hourly input files. See `README_PUBLIC_UPDATE_20261028.md` for map drawing commands and current publication details.

## Distinct calculation stages

Figures 2 and 3 retain the initial domestic NNLS fit and subtract capped partner coverage from its shortfall, with no post-routing domestic refit. Counterfactual domestic-refit tables are separate sensitivity outputs.

Figure 5 refits domestic supply to the remaining demand after routing. Remaining demand and supply are jointly scaled by the same factor to 100 MW mean remaining domestic load; the factor is calculated separately for each scenario. Its primary tables enforce strict hourly zero unmet demand. `original_soft` records audit the previous finite-VOLL implementation and document achieved reliability; they are separate from the revised paper's strict-service main results. Costs use annual remaining domestic demand MWh as the denominator.

## Reconstruct the waveform and certificates

```text
python -m pip install -r requirements_waveform.txt
python scripts/waveform/run_waveform_revision.py --data-root inputs/hourly --reference-dir inputs/reference/waveform --output-dir results/waveform --mode all --full-grid
python scripts/waveform/verify_separating_certificates.py --results-dir results/waveform --demand-file inputs/hourly/country_hourly_demand.csv.gz
python scripts/waveform/verify_fig3_statistics.py --data-root inputs/hourly --reference-dir inputs/reference/waveform --output-dir results/waveform
python scripts/waveform/plot_revision_figures.py --results-dir results/waveform --output-dir figures
python scripts/waveform/verify_package_content.py
```

The original Figure 2 layout with its revised domestic-execution label can be regenerated and checked separately:

```text
python -m pip install -r scripts/figures/requirements_Fig2.txt
python scripts/figures/plot_r2_latency_fig2.py
python scripts/figures/verify_Fig2.py
```

The submitted NNLS annual residual has median 12.714%. The routing LP applied to that same fixed shortfall gives 12.208%; the distinct complete LP sequence gives 12.370%. Unit-shortfall ρ and original-demand U are converted separately for every country. The positive certificates concern the fixed shortfall and partner dictionary, without a joint operational optimum.

## Reconstruct finite-site power and economic scenarios

```text
python -m pip install -r requirements_power.txt
python scripts/power/run_power_case.py
python scripts/power/finalize_power_evidence.py
python scripts/power/plot_and_price_power_case.py
```

The default input is a verified hourly aggregation of all 16,803,695 Azure coding requests. Raw-source download and SHA-256 instructions appear in `README_power.md`. Both sending and receiving sites are counted. Origins, capacities, network allowances, power interpolation and prices are explicit scenario assumptions. This is not metered Azure electricity or a request-level SLO validation.

## Verify or reconstruct strict dispatch

```text
python -m pip install -r requirements_storage.txt
python scripts/storage/verify_storage_outputs.py
```

The verified delivered outputs can be checked without rerunning optimization. Exact regeneration commands, including a separate real US replay, appear in `README_storage.md`. The inputs include original country-hour traffic, national renewable profiles, capacities, location metadata and actual NREL component prices. The strict requirement is zero unserved energy in every hour. Costs and capacities refer to the remaining domestic load after routing and refitting, normalized independently to 100 MW mean; they exclude receiver computing and electricity. The 2030 domestic/global median premiums are 60.796%/56.138%.

## Regenerate revised dispatch figures

```text
python -m pip install -r requirements_figures.txt
python scripts/figures/plot_strict_revision.py
```

The entry reads the flat `results/storage` tables and national metadata in `inputs/hourly`, then writes `figures/Fig5.pdf`, `Fig5.png`, `FigS9.pdf` and `FigS9.png`. Figure 5 uses the submitted waterfall, 36-sector rose, domestic/global ridgelines with six-budget median trajectories, and Robinson maps. Waterfall and trajectory values are country medians of Π; rose components divide country-mean component costs by country-mean generation cost. The inherited drawing helpers preserve the submitted canvas, export dimensions and map projection. Their standalone legacy entry points are support code; the revised command above supplies the validated inputs. Arial is used for figure lettering; delivered PDFs embed the plotting fonts, without distributing a font license.

## Evidence and boundaries

Component JSON reports record optimality, achieved service, hourly/daily conservation, independent replays, input hashes and measured numerical differences. `results/source_workbook/source_workbook_verification.json` records source-sheet validation. `PUBLIC_MANIFEST.json` hashes the public files and identifies their Git or Release storage locations.

Traffic retains arbitrary normalized request-activity units. Non-overlapping independently normalized downloads contain no recoverable inter-window absolute factor. Window sensitivities expose that uncertainty without reconstructing measured seasonal volumes. Public request traces contain neither user-local geography nor metered power. Batch deadlines use fixed energy per work and stipulated compute headroom. Price sensitivities use hypothetical values. The package supports those precisely stated computations and their conditional scope.
