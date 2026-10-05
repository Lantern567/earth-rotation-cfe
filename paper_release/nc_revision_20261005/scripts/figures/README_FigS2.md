# Figure S2: frozen-data rendering

Run from the root of `Reproducibility_Package`:

```powershell
python scripts/figures/plot_figS2_burstgpt_diurnal.py
```

The defaults read `inputs/reference/figS2` and write `figures/FigS2.png` (300 dpi) and `figures/FigS2.pdf`. Both paths can be supplied explicitly:

```powershell
python scripts/figures/plot_figS2_burstgpt_diurnal.py --data-root inputs/reference/figS2 --output-dir figures
```

Dependencies are NumPy, pandas and Matplotlib, with tested versions in the archive's `requirements_waveform.txt`. The plot retains the original DejaVu Sans font, purple/slate/teal/amber palette, panel sizes and all scientific data.

The four inputs are the original frozen 24-hour token-share table, pooled fit parameters, 500 bootstrap draws and three trace-slice fits. No analysis is repeated. `results/figS2/validation.json` records their SHA-256 hashes, original and revised script hashes, and the completed 2 October 2026 comparison of Matplotlib artists. Every data curve, empirical bar, confidence-envelope vertex, confidence rectangle, axis limit, axis label, annotation text and color is identical. Only the placement of the two slice labels changes.

Acceptance records: four copied inputs matched the original files byte for byte; the artist comparison passed; the portable command above completed using only archive inputs; the PNG was visually inspected at its export size with both slice labels separated and no clipped text.
