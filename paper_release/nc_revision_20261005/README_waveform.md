This component reconstructs the submitted Fig. 2 waveform grid, Fig. 3 partner attribution and follow-the-sun statistics from hourly inputs. It also calculates the revised fixed-shortfall LP certificates, domestic-refit comparisons, working-hours mixtures and unknown-window-scale sensitivities, and produces Supplementary Figs S6 and S7.

## Inputs and calculation scope

`inputs/hourly` contains the actual 104-country, 8,760-hour human-traffic proxy, 461 station profiles, national technology profiles, installed-capacity and location metadata, BurstGPT token profile and download-window metadata. `normalization_windows.csv` records the boundaries and normalization metadata inspected in 1,248 actual retained total-volume responses. No absolute normalization factor or overlapping window was found. Its window-scale experiments are conditional assumptions. The request and token inputs contain no metered facility electricity.

`inputs/reference/waveform` retains the submitted country grid, objective comparison, four attribution tables and follow-the-sun statistics for verification. The revised pipeline uses these tables only to check its hourly reconstruction. The revised calculations are performed from the hourly inputs.

The routing LP holds the first-stage domestic shortfall fixed. The original complete LP sequence changes that shortfall and is reported separately. Unit-shortfall residual rho and annual-demand residual U are distinct: at full routing eligibility U = (R/E)rho for each country. Applying that relation precedes country aggregation. Neither certificate identifies a joint domestic-portfolio and operational-routing optimum.

## Runtime

The computations were verified with Python 3.13.5 on Windows and the versions in `requirements_waveform.txt`. Install those dependencies in a Python environment:

```text
python -m pip install -r requirements_waveform.txt
```

Numerical calculations require no internet access or original project directory. Plotting additionally requires an installed Arial font; the plotting script checks its presence explicitly. The supplied PDF figures embed the fonts used. This component does not contain a licensed Arial font file.

## Complete reconstruction

Run the following commands from this package directory, `paper_release/nc_revision_20261005`:

```text
python scripts/waveform/run_waveform_revision.py --data-root inputs/hourly --reference-dir inputs/reference/waveform --output-dir results/waveform --mode all --full-grid
python scripts/waveform/verify_separating_certificates.py --results-dir results/waveform --demand-file inputs/hourly/country_hourly_demand.csv.gz
python scripts/waveform/verify_fig3_statistics.py --data-root inputs/hourly --reference-dir inputs/reference/waveform --output-dir results/waveform
python scripts/waveform/plot_revision_figures.py --results-dir results/waveform --output-dir figures
python scripts/waveform/verify_package_content.py
```

The first command rebuilds all 104 countries and all 36 Fig. 2 combinations, four Fig. 3 attribution tables, the follow-the-sun table, 312 LP solves, five demand mixtures and ten window-scale scenarios. It also writes hourly primal/dual certificate arrays for every country. The second command checks the 208 routing separation certificates and stores their explicit normalized hourly vectors. The third checks coverage aggregation and complete partner attribution. The fourth uses the revised CSV tables to draw the figures.

The scripts' default input and output paths also resolve relative to this archive. `--data-root`, `--reference-dir` and `--output-dir` allow a different layout. `--project-root` supports auditing an original developer project and is unnecessary for archive execution.

Individual analyses can be selected with `--mode grid`, `--mode objective`, `--mode mix` or `--mode windows`. `--limit 3` limits the objective and sensitivity calculations to the first three usable countries for a smoke check. The original grid always retains all 104 countries when requested. The complete business–consumer sensitivity includes all 104 countries at the full-routing/global corner; six illustrative countries additionally receive the 36-cell grid for each mixture.

## Stored evidence

- `results/waveform/objective_results.csv` separates the NNLS pipeline, same-shortfall routing LP and complete LP pipeline, with country-specific energy ratios.
- `results/waveform/lp_certificates.csv` records unnormalized primal/dual objectives, constraint errors and solver status for all 312 solves.
- `results/waveform/certificates/*.npz` retain the hourly targets, partner dictionary, primal weights/slack and dual marginals for all 104 countries.
- `results/waveform/hourly_separating_vectors.npz` supplies the hourly request-proxy shortfall, normalized shortfall and partner profiles, separating vectors h, mixture weights and uncovered slack for both routing stages. Restore this large file from the `v1.2.0-nc-revision` release asset using the download command and SHA-256 in `README.md` before inspecting all frozen hourly arrays; the reconstruction commands regenerate it.
- `results/waveform/normalized_separation_certificates.csv` records unit-energy primal and dual objectives, rho, R/E, annual U, h bounds and explicit separating margins.
- `results/waveform/fig3_four_tiers_summary.csv` distinguishes mean coverage from the difference of country medians.
- The business–consumer, window-weight and domestic-refit CSV tables retain country-specific results. The window-weight table supplies every assumed factor.
- `figures/FigS6_conditional_certificate.pdf` and `figures/FigS7_demand_and_window_sensitivity.pdf` are the final figures, with corresponding 300-dpi PNG files.
- `results/waveform/figure_captions_and_methods.txt` gives the English captions and full calculation definitions.

## Actual validation records

The following executions used real supplied hourly data on 2 October 2026:

1. All 104 countries and 312 LP solves completed with optimal status. The same-shortfall LP annual U median is 12.2081157%, compared with NNLS 12.7142118%; no country has a larger LP residual on that same shortfall. The complete LP pipeline reproduces 12.3699985% and has fourteen larger country residuals because its domestic shortfall changes. Results and actual errors are recorded in `objective_summary.json`.
2. All 208 unit-energy routing certificates passed an independent absolute verification tolerance of 1e-8. Their largest separation-margin error is 8.1046e-15, primal–dual gap 4.1078e-15 and mixture-energy error 1.2101e-14. The h bounds have no violation. The unnormalized summary also includes domestic LP checks and reports a maximum reduced-cost/stationarity residual of 1.2235e-8; it is a distinct scale and stage. Details are in `normalized_separation_summary.json` and `lp_certificates.csv`.
3. All five business–consumer mixtures and ten window-scale scenarios completed for all 104 countries. Every scenario preserves the original annual demand energy. These comparisons establish sensitivity under specified shapes and scales, without recovering missing historical traffic volume or identifying measured electricity.
4. The original 3,744-row country grid, all four published attribution tables and follow-the-sun table were rebuilt from hourly data. Grid fractions agree within 3.3307e-16, attribution weights within 5.5789e-15 and follow-the-sun hours within 1.7764e-14. These checks are recorded in `original_grid_validation.json`.
5. A separate flat-input execution reproduced all 3,744 grid rows and the same attribution/follow-the-sun comparisons without the developer-directory layout. A flat-input `--mode all --limit 3` execution also exercised LP, mixture and normalization-window inputs successfully. Final-package verification is recorded in `package_execution_validation.json`.
6. Both supplementary figures were generated as PDF and 300-dpi PNG. All panels were inspected for missing glyphs, overlapping labels, clipping and complete inclusion of the country observations. The final plotting execution produced no warnings.

Numerical solver tolerances are primal feasibility 1e-8, dual feasibility 1e-8 and IPM optimality 1e-9. The reported verification errors are measured independently and should be distinguished from configured solver tolerances. Counterfactual domestic refits retain their stated energy budgets and use NNLS; they need not reduce the uncovered-energy metric.
