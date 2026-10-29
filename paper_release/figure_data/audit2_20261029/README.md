# Figure S1 and Figure 3 reproducibility

These figure updates use the existing numerical results and adopted scenario inputs. They build on the revision material merged in PR #2 (base commit 26e9d77f259cf6b52ac1a4b540802a5f19e433b1).

Figure S1 uses inference and training shares interpolated separately between 2025, 2030, 2040 and 2050. The logistic curve is an approximate display fit. The 2040 scenario anchor has total AI share 0.68 and inference fraction 0.75. Figure 3 labels its last map with the selected 500 ms budget. The CSV and JSON files record the plotted inputs and unchanged flow-data hashes.

From the repository root, run:

```powershell
python paper_release/scripts/plot_figS1_lambda_trajectory.py --output-dir paper_release/figures
python paper_release/scripts/redraw_fig3_label.py --package-root PATH_TO_EXPANDED_REPRODUCIBILITY_PACKAGE --output-dir OUTPUT_DIRECTORY
```

Figure 3 requires the frozen waveform inputs, country metadata and plotting dependencies in the revision reproducibility package. No optimization is run by either command. Existing release assets and tags are unchanged.
