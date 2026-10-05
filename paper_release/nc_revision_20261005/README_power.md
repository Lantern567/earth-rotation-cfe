# Three-site power accounting and economic scenarios

This component recomputes the supplemental three-site experiment, Supplementary Fig. S8 and a frozen-dispatch economic sensitivity. It uses the complete Azure coding trace through an included hourly aggregation, without rescaling its 16,803,695 requests. The experiment has specified origins, GPU capacity, power interpolation and network budgets. Electricity and service quantities are model outputs; the request trace contains no metered facility power or TTFT/TBT observations.

## Inputs and provenance

Required portable inputs are in `inputs/power/`:

- `azure_coding_hourly_with_scenario_origins.csv`: 504 origin-hour rows covering 168 hours, 10–16 May 2024 UTC. Original CSV row index modulo ten assigns residues 0–4 to US, 5–7 to Germany, and 8–9 to Japan. Assignment is a controlled scenario and is not observed user geography. Request and input/output token totals are retained.
- `renewable_three_site_hourly.csv`: 1,008 site/technology/hour rows from the article's reconstructed country wind and solar inputs, 10–16 May 2025 UTC. Each 2024 request hour is paired with the same civil month/day/hour one year later. These records are derived from the original reconstruction and are sufficient to reproduce this component.
- `input_provenance.json`: raw and derived SHA-256 values, source URLs, assignment rules, fleet parameters, hardware references and tested library versions. Historical producer paths are provenance labels; execution uses the included files and does not require those directories.

The original trace is publicly downloadable from the [Azure dataset release](https://github.com/Azure/AzurePublicDataset/releases/download/dataset-llm-2024/AzureLLMInferenceTrace_code_1week.csv). Its exact filename is `AzureLLMInferenceTrace_code_1week.csv`, size 691,989,454 bytes, with SHA-256:

`71de5c55cbc35f8f1ed0b6b7806b4cd1e9764b0058469725a6aac98023a1448f`

The raw file is not duplicated here. The included request aggregation derives from that full file. The [official dataset description](https://github.com/Azure/AzurePublicDataset/blob/master/AzureLLMInferenceDataset2024.md) specifies a CC-BY Attribution License and requests citation to Jovan Stojkovic, Chaojie Zhang, Íñigo Goiri, Josep Torrellas and Esha Choukse, *DynamoLLM: Designing LLM Inference Clusters for Performance and Energy Efficiency*, HPCA 2025 ([paper](https://arxiv.org/abs/2408.00741)). The hourly counts and token totals are attributed to this dataset. No prompt text or user location is available.

GPU calibration comes from *Watt Counts: Energy-Aware Benchmark for Sustainable LLM Inference on Heterogeneous GPU Architectures*, arXiv:2604.09048v1 ([primary paper](https://arxiv.org/html/2604.09048v1)). Fig. 5 and Tables 5–6 supply board-level idle and model-class means. The external setup charge comes from Niu et al., *Energy Efficient or Exhaustive? Benchmarking Power Consumption of LLM Inference Engines* ([primary paper](https://hotcarbon.org/assets/2025/paper-11.pdf)), Table 1, a different two-H100 node. It is evaluated as a frozen-dispatch sensitivity and does not measure this experiment's transitions.

## Recompute

Run from the `Reproducibility_Package` directory with Python 3.11 or later; the verified environment used Python 3.13 and the versions pinned in `requirements_power.txt`.

```text
python -m pip install -r requirements_power.txt
python scripts/power/run_power_case.py
python scripts/power/finalize_power_evidence.py
python scripts/power/plot_and_price_power_case.py
```

The first command performs the scenario calculations and writes `results/power/`. The second independently checks the resulting energy, request, background and capacity ledgers, then computes the low-load power-curve sensitivity and evidence tables. The third creates `figures/FigS8/` and economic tables. All paths are derived from the package, with optional command-line overrides. Required imports are direct, and invalid or altered retained inputs fail with a diagnostic.

To reconstruct the hourly origin counts from the downloaded full trace, use:

```text
python scripts/power/run_power_case.py --raw-trace path/to/AzureLLMInferenceTrace_code_1week.csv --output-dir results/power_from_raw
```

The download hash must match the specified raw input version. `--renewable-parquet` also permits the full original processed renewable input; the included CSV is the default. CSV renewable values are read with round-trip floating-point precision.

## Model and validation

The fleet is fixed at 190 / 114 / 76 GPUs for US / Germany / Japan, chosen from actual hourly peak arrival counts plus the uniform background schedule. A published benchmark arrival rate of 0.3 requests/s and a selected 80% design-use ceiling provide the scenario capacity. All 30 cases preserve the same 16,803,695 interactive request-equivalents and 3,360,749 finite background job units. Background amounts are fixed by origin-day. Hourly aggregate flows are continuous; device power, token-specific serving energy and burst-level service remain unmeasured.

Within each hardware scenario, supply has one fixed clean-energy budget and three fixed renewable series. Remain-on retains all GPU idle power. Finite backfill rearranges the same daily local background pool within released capacity. Consolidation chooses integer awake counts, with a warm replica retained at each site and predictive prewarming assumed. It first minimizes uncovered kWh and then minimizes electricity while preserving the optimum; independent hourly MILPs implement this policy. Separate charge sensitivity evaluates the same dispatch with external setup energy.

`results/power/power_accounting_methods.md` contains the complete equations, assumptions and TTFT/TBT distinction. The main trace's mean input/output lengths are 2,511.28 / 22.69 tokens; the GPU benchmark endpoints describe a different workload distribution. These endpoints are scenario calibration, without measurement of Azure's serving power or capacity.

The portable calculation was run using only the included hourly inputs in a separate output directory and compared with the original full-trace/parquet calculation. `portable_recomputation_verification.json` reports 30 matching cases and zero differences for the retained comparison metrics under the tested versions. `power_case_verification.csv` checks all case ledgers, solver status and hourly/daily conservation. Numerical integer deviations are checked against 1e-6; no empirical TTFT/TBT claim follows from an hourly capacity check. Tied routing schedules can vary with a different solver version, so versions are pinned.

## Economic sensitivity

`frozen_dispatch_price_sensitivity.csv` evaluates local and 500 ms dispatches under five specified price vectors:

- Uniform 0.05, 0.10 or 0.20 USD/kWh.
- US / Germany / Japan at 0.05 / 0.10 / 0.20 USD/kWh.
- The reverse vector 0.20 / 0.10 / 0.05 USD/kWh.

These are hypothetical volumetric prices. The calculation multiplies all-site modeled GPU kWh by the chosen prices and leaves every flow and awake count unchanged. It does not model actual tariffs, PPA rights, clean procurement terms, reservation charges, taxes or egress contracts. Remain-on and finite backfill have zero uniform-price bill change when routed; their total modeled kWh remain constant. Consolidation's local-to-routed change is 8.909 kWh, corresponding to scenario bill decreases of 0.44545 / 0.89090 / 1.78180 USD under the three uniform prices.

`illustrative_routing_fee_thresholds.csv` adds explicitly assumed values of 30, 100 or 200 USD/MWh to avoided uncovered energy. For remain-on 500 ms versus local, the avoided uncovered amount is 0.30702093 MWh. The break-even additional fee per routed request-equivalent is:

`(v × avoided uncovered MWh - volumetric cost change) / routed request-equivalents`.

At uniform prices, this equals 0.0000008915 / 0.0000029717 / 0.0000059434 USD per routed request-equivalent. Those values depend on hypothetical shadow value v and are not observed bill savings. Negative thresholds are retained in the nonuniform-price sensitivity. Definitions and exclusions are recorded in `economic_sensitivity_definition.json`.

## Figure and outputs

`figures/FigS8/FigS8.pdf` and `FigS8.png` are four-panel vector PDF and 300 dpi raster outputs using Arial and purple/orange colors. `FigS8_caption.txt` has 193 English words. Main comparison data, hourly site-power changes and cumulative background completion are provided beside the figure. Percentage gaps use each policy's own modeled electricity denominator; the figure displays absolute kWh and total consumption separately.

Core outputs include the 30-case summary, hourly site ledger, hourly origin–destination flows, fixed background pools, conservation checks, fixed facility-load/PUE sensitivity, a low-load-endpoint sensitivity and primary power/latency evidence. These model outputs support the supplementary accounting analysis, with no claim of a measured annual global clean-power floor or request-tail service certification.
