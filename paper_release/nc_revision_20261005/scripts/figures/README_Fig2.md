# Figure 2

Run from the root of `Reproducibility_Package`:

```powershell
python scripts/figures/plot_r2_latency_fig2.py --data-root inputs/reference/waveform --output-dir figures
python scripts/figures/verify_Fig2.py --archive-root .
```

The plot uses the frozen, original `r2_waveform_grid.csv` (104 countries × 6 routable fractions × 6 latency tiers; 3,744 rows) and `r2_wf_followsun.csv` (104 countries). Uncovered shares are dimensionless in the inputs and are multiplied by 100 for display. Heatmap and violin annotations use country medians. The plotting functions, coordinates, colors, type sizes, and original DejaVu Sans font are retained from `paper_release/scripts/plot_r2_latency_fig2.py`. `fig2_original_style.py` contains only the three style functions and palette constants used from the original plotting helper, without importing unrelated map or analysis dependencies.

The domestic counterfactual cell is labelled “Domestic only”. Figures are exported as 300 dpi PNG and vector PDF. No scientific analysis is rerun by this command. To rebuild the full 3,744-row grid from the hourly inputs, use the full-grid command in `README_waveform.md`.

Actual acceptance on 2026-10-02: both PNGs have dimensions 4,672 × 3,336 pixels. Comparing the new PNG against the frozen original gives changes only in the text rectangle `(326, 2990, 797, 3058)`; every pixel outside that annotation is exactly equal. Frozen CSV SHA-256 values and all heatmap medians are recorded in `results/fig2/validation.json`. The reference original PNG and original plotting script are archived under `inputs/reference/fig2/` for verification and provenance. The PNG comparison requires the recorded rendering environment (Python 3.13.5, Matplotlib 3.10.3, NumPy 2.2.6, pandas 2.3.1, Pillow 11.3.0); on a different renderer, verify the input hashes and numeric medians before interpreting minor raster differences.
