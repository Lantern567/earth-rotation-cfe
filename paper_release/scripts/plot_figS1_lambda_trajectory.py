#!/usr/bin/env python3
"""Supplementary Figure S1 — AI demand-share trajectory and inference/training
split, 2024-2050.

Two panels (double-column, ~7.0 x 3.0 in), English-only, colorblind-safe.

  (a) An approximate logistic display fit over 2024-2050 with adopted anchors
      (2025/2030/2040/2050), source-range uncertainty (2030 [0.35,0.50],
      2050 [0.60,0.80]) and the individual Gartner / EDNA source estimates.
  (b) Decomposition: stacked lambda_inf (drives the intraday shape operators)
      + lambda_train (flat training baseload) summing to lambda_AI, with the
      inference fraction f_inf overlaid on a secondary right axis.

The inference and training components follow the four anchors in the analysis
code, with piecewise linear interpolation; the inference fraction is their
ratio. The logistic fit is displayed separately from these model inputs.
"""
from __future__ import annotations
import argparse
import csv
import json
import warnings
from pathlib import Path
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent
FIG = SCRIPT_DIR.parent / "figures"
FIT_PARAMETERS = {"floor": 0.02, "ceiling": 0.70, "k": 0.31, "year_midpoint": 2028.6}

# ---- palette / style (consistent with the SI figures) --------------------
INK = "#111827"
GRID = "#E5E7EB"
C_AI = "#1F4E8C"      # lambda_AI logistic curve (deep blue)
C_INF = "#0F766E"     # inference component (teal)  -> drives P2/P3 shapes
C_TRAIN = "#B45309"   # training baseload (amber/brown)
C_FINF = "#7C3AED"    # inference fraction overlay (violet, matches Mix hue)
C_GARTNER = "#C2410C"
C_EDNA = "#0E7490"


def set_style(fs=8.5):
    mpl.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": fs,
        "axes.titlesize": fs + 1.0, "axes.titleweight": "bold", "axes.labelsize": fs,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": "#374151", "axes.labelcolor": INK,
        "xtick.color": "#374151", "ytick.color": "#374151",
        "xtick.labelsize": fs - 0.5, "ytick.labelsize": fs - 0.5,
        "legend.fontsize": fs - 0.5, "legend.frameon": False,
        "figure.facecolor": "white", "savefig.facecolor": "white",
        "savefig.dpi": 300, "axes.axisbelow": True,
        "grid.color": GRID, "grid.linewidth": 0.6, "grid.alpha": 0.6,
        "mathtext.default": "regular",
    })


def load():
    # S2 的近似拟合参数仅用于展示，不生成模型输入。
    return FIT_PARAMETERS.copy()


def lambda_ai(t, fit):
    k, t0 = fit["k"], fit["year_midpoint"]
    floor, ceil = fit["floor"], fit["ceiling"]
    return floor + (ceil - floor) / (1.0 + np.exp(-k * (t - t0)))


# ---- anchor numbers the figure must honour (SI tables, rounded mids) ------
ANCHOR_YEARS = [2025, 2030, 2040, 2050]
LAM_INF = {2025: 0.130, 2030: 0.308, 2040: 0.510, 2050: 0.560}
LAM_TRAIN = {2025: 0.070, 2030: 0.132, 2040: 0.170, 2050: 0.140}
LAM_AI = {year: LAM_INF[year] + LAM_TRAIN[year] for year in ANCHOR_YEARS}
F_INF = {year: LAM_INF[year] / LAM_AI[year] for year in ANCHOR_YEARS}
# source ranges shown as uncertainty bands / error bars on lambda_AI
RANGE_AI = {2030: (0.35, 0.50), 2050: (0.60, 0.80)}
# individual source estimates (mid), from lambda_anchor_table.csv
SRC_GARTNER = {2025: 0.208, 2030: 0.441}
SRC_EDNA = {2025: 0.169, 2030: 0.425}  # IEA-4E/EDNA mid

def model_components(years):
    # 与分析程序一致，分别对推理和训练分量作四锚点线性插值。
    inf = np.interp(years, ANCHOR_YEARS, [LAM_INF[y] for y in ANCHOR_YEARS])
    train = np.interp(years, ANCHOR_YEARS, [LAM_TRAIN[y] for y in ANCHOR_YEARS])
    total = inf + train
    return inf, train, total, inf / total


def panel_a(ax, fit):
    yrs = np.linspace(2024, 2050, 400)
    lam = lambda_ai(yrs, fit)
    ax.plot(yrs, lam, color=C_AI, lw=1.9, zorder=4, label="Approximate logistic fit")

    # source-range uncertainty as vertical error bars at 2030 / 2050
    for y, (lo, hi) in RANGE_AI.items():
        mid = LAM_AI[y]
        ax.errorbar(y, mid, yerr=[[mid - lo], [hi - mid]], fmt="none",
                    ecolor=C_AI, elinewidth=1.4, capsize=3.5, capthick=1.4, zorder=5)

    # 四个采用的情景锚点，与分量输入一致。
    am_x = ANCHOR_YEARS
    am_y = [LAM_AI[y] for y in ANCHOR_YEARS]
    ax.scatter(am_x, am_y, s=42, color=C_AI, edgecolor="white", linewidth=1.0,
               zorder=6, label="Adopted scenario anchors")
    for y in ANCHOR_YEARS:
        ax.annotate(f"{LAM_AI[y]:.2f}", (y, LAM_AI[y]), xytext=(0, 8),
                    textcoords="offset points", ha="center", va="bottom",
                    fontsize=7.5, color=C_AI, fontweight="bold")

    # individual source estimates (Gartner, EDNA) at 2025/2030
    gx = sorted(SRC_GARTNER); gy = [SRC_GARTNER[y] for y in gx]
    ex = sorted(SRC_EDNA); ey = [SRC_EDNA[y] for y in ex]
    ax.scatter(gx, gy, s=26, marker="^", color=C_GARTNER, edgecolor="white",
               linewidth=0.6, zorder=5, label="Gartner")
    ax.scatter(ex, ey, s=26, marker="s", color=C_EDNA, edgecolor="white",
               linewidth=0.6, zorder=5, label="IEA-4E / EDNA")

    ax.set_xlim(2024, 2050)
    ax.set_ylim(0, 0.85)
    ax.set_xticks([2025, 2030, 2035, 2040, 2045, 2050])
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8])
    ax.set_xlabel("Year")
    ax.set_ylabel("AI share of data-centre electricity\n(energy basis)")
    ax.grid(True, axis="y")
    ax.legend(loc="lower right", handletextpad=0.5, labelspacing=0.35,
              borderaxespad=0.4)


def panel_b(ax, fit):
    yrs = np.unique(np.r_[np.linspace(2024, 2050, 400), ANCHOR_YEARS])
    # interpolate the anchor splits across years (monotone-ish, anchor-consistent)
    inf, train, total, finf = model_components(yrs)

    # stacked areas: training baseload at bottom, inference on top (sum = lambda_AI)
    ax.fill_between(yrs, 0, train, color=C_TRAIN, alpha=0.85, lw=0,
                    label=r"$\lambda_{\mathrm{train}}$ (training baseload)", zorder=2)
    ax.fill_between(yrs, train, train + inf, color=C_INF, alpha=0.80, lw=0,
                    label=r"$\lambda_{\mathrm{inf}}$ (inference)", zorder=2)
    # sum line = lambda_AI for reference
    ax.plot(yrs, train + inf, color=C_AI, lw=1.2, ls="-", zorder=4,
            label=r"$\lambda_{\mathrm{AI}}=\lambda_{\mathrm{inf}}+\lambda_{\mathrm{train}}$")

    # anchor markers on the stack
    for y in ANCHOR_YEARS:
        ax.plot(y, LAM_TRAIN[y], "o", ms=3.5, color=C_TRAIN, mec="white", mew=0.7, zorder=6)
        ax.plot(y, LAM_TRAIN[y] + LAM_INF[y], "o", ms=3.5, color=C_INF, mec="white", mew=0.7, zorder=6)

    ax.set_xlim(2024, 2050)
    ax.set_ylim(0, 0.85)
    ax.set_xticks([2025, 2030, 2035, 2040, 2045, 2050])
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8])
    ax.set_xlabel("Year")
    ax.set_ylabel("AI share of data-centre electricity\n(energy basis)")
    ax.grid(True, axis="y")

    # secondary axis: f_inf
    ax2 = ax.twinx()
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(True)
    ax2.spines["right"].set_color(C_FINF)
    ln_finf, = ax2.plot(yrs, finf, color=C_FINF, lw=1.5, ls="--", zorder=5,
                        label=r"$f_{\mathrm{inf}}$ (inference fraction)")
    ax2.scatter(ANCHOR_YEARS, [F_INF[y] for y in ANCHOR_YEARS], s=22,
                color=C_FINF, edgecolor="white", linewidth=0.6, zorder=6)
    ax2.set_ylim(0, 1.0)
    ax2.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax2.set_ylabel(r"inference fraction $f_{\mathrm{inf}}$", color=C_FINF)
    ax2.tick_params(axis="y", colors=C_FINF, labelsize=8.0)

    # merged legend (areas + sum from ax, f_inf from ax2), light frame.
    # placed lower-centre so it clears the f_inf line (upper area) and the
    # rising stack; opaque frame so nothing shows through.
    h1, l1 = ax.get_legend_handles_labels()
    leg = ax2.legend(h1 + [ln_finf], l1 + [ln_finf.get_label()],
                     loc="lower center", bbox_to_anchor=(0.5, 0.005),
                     handletextpad=0.6, labelspacing=0.32, borderaxespad=0.4,
                     framealpha=1.0, fancybox=False)
    leg.set_zorder(10)
    leg.get_frame().set_edgecolor(GRID)
    leg.get_frame().set_linewidth(0.6)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=FIG)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    set_style(8.5)
    fit = load()
    fig, (axa, axb) = plt.subplots(1, 2, figsize=(7.0, 3.0))
    panel_a(axa, fit)
    panel_b(axb, fit)

    # bold (a)/(b) panel labels at top-left of each panel
    for ax, lab in ((axa, "a"), (axb, "b")):
        ax.text(-0.16, 1.04, lab, transform=ax.transAxes, fontsize=11,
                fontweight="bold", ha="left", va="bottom", color=INK)

    fig.tight_layout(w_pad=2.4)
    for ext in (".png", ".pdf"):
        out = args.output_dir / f"figS1_lambda_trajectory{ext}"
        fig.savefig(out, bbox_inches="tight", dpi=300)
        print(f"wrote {out}  ({out.stat().st_size/1024:.1f} KB)")
    plt.close(fig)
    years = np.unique(np.r_[np.linspace(2024, 2050, 400), ANCHOR_YEARS])
    inf, train, total, finf = model_components(years)
    with (args.output_dir / "figS1_plot_data.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["year", "lambda_inf", "lambda_train", "lambda_AI", "f_inf", "approximate_logistic_fit"])
        writer.writerows(zip(years, inf, train, total, finf, lambda_ai(years, fit)))
    ai, at, total_a, fraction = model_components(np.array(ANCHOR_YEARS))
    assert np.allclose(total_a, [0.20, 0.44, 0.68, 0.70], rtol=0, atol=1e-12)
    assert np.allclose(fraction, [0.65, 0.70, 0.75, 0.80], rtol=0, atol=1e-12)
    record = {"anchor_years": ANCHOR_YEARS, "lambda_inf": ai.tolist(), "lambda_train": at.tolist(), "lambda_AI": total_a.tolist(), "f_inf": fraction.tolist(), "2040_basis": "adopted intermediate scenario anchor from the analysis code", "interpolation": "piecewise linear separately for inference and training", "logistic_fit_used_as_model_input": False, "optimization_run": False}
    (args.output_dir / "figS1_validation.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record))


if __name__ == "__main__":
    main()
