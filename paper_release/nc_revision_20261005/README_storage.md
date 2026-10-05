# Storage and strict-service revision

Run all commands from this archive root. The revised entries are in `scripts/storage`; the complete paper results are in `results/storage`. The original scientific helpers and real hourly demand/supply inputs are supplied in `collective_attention_research_plan`, preserving the relative paths used by the submitted helpers. `inputs/storage/portable_support_manifest.json` lists their SHA-256 hashes. The window metadata are in `inputs/hourly/normalization_windows.csv`.

Install the pinned dependencies:

```text
python -m pip install -r requirements_storage.txt
```

Verify every supplied numerical table without rerunning an optimization:

```text
python scripts/storage/verify_storage_outputs.py
```

The complete strict Fig. 5 source tables contain 1,248, 3,744 and 3,744 rows. Their union contains 7,384 country/year/latency/eligibility keys and 4,591 exactly distinct dispatch inputs. All primary dispatches fix each hourly unserved-energy variable to zero. `strict_reliability_2030.csv` contains 208 strict cases and 208 replays of the submitted VOLL-only objective; `batch_deadlines_2030.csv` contains 416 domestic deadline cases; `table_s23_reliability.csv` contains 12 target/cycle sensitivity cases; and `window_storage_sensitivity_2030.csv` contains 36 window-scale cases. The supplied CSVs, validation reports, price audit and original/strict comparisons are complete.

To independently regenerate the calculations, use the following commands in order. These commands produce the same flat `results/storage` structure consumed by the revised figures:

```text
python scripts/storage/run_storage_revision.py --mode reliability --workers 4 --output-dir results/storage
python scripts/storage/run_warm_strict_fig5.py --workers 4 --output-dir results/storage
python scripts/storage/run_warm_batch_deadlines.py --workers 4 --output-dir results/storage
python scripts/storage/reliability_sensitivity.py --workers 2 --output-dir results/storage
python scripts/storage/run_window_storage_sensitivity.py --workers 2 --output-dir results/storage
python scripts/storage/summarize_storage_revision.py --project-root . --output-dir results/storage
python scripts/storage/verify_storage_outputs.py
python scripts/storage/audit_cost_versions.py --output-dir results/storage
python scripts/storage/verify_cost_version_checks.py --output-dir results/storage
```

The first two commands build exact intermediate fits and cache files from the supplied real hourly inputs. Caches and repeated development outputs are excluded from this archive; they are generated on demand and are not required for verification of the supplied tables. An alternative input tree can be selected using `--project-root`; every calculation entry accepts `--output-dir`. The three exported Fig. 5 tables retain their original row keys and geometric uncovered-share columns and add realized service, solver status and feasibility errors.

For a separate small independent replay, use a fresh output directory:

```text
python scripts/storage/run_storage_revision.py --mode reliability --countries US --workers 1 --output-dir results/storage_replay_us
```

The cost denominator is annual remaining domestic demand after routing and domestic NNLS refitting. Every scenario is independently normalized to a 100-MW mean remaining domestic load. These costs exclude receiver electricity/hardware procurement and shared receiver budgets. The batch calculation concerns domestic 2030 Mix with constant 20.9-MW deferrable arrivals, execution at most 41.8 MW, cyclic annual work conservation and 0/1/6/24-hour FIFO backlog limits; these are explicit scheduling assumptions. Window factors are assumptions about unidentified acquisition-window scales, not measured seasonal volumes. See `results/storage/storage_revision_methods.md` for complete definitions and numerical findings.

`portable_storage_validation.json` records independent real US and DE dispatch replays against the final 2030 inputs; all input arrays and cost parameters match exactly and replay costs differ by zero. `soft_2025_reproduction_validation.json` records six actual submitted-objective replays, reproducing the frozen original costs within 1.14 × 10⁻¹² USD/MWh. The 2025 cost increase under strict service follows from eliminating those original unserved-energy optima. `table_s21_actual_cost_components.csv` records the actual model input prices: Li energy costs equal the NREL four-hour system CAPEX less the separately modeled power component of 280/4 = 70 USD/kWh.
