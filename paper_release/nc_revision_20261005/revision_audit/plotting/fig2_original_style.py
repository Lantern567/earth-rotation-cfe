import matplotlib as mpl
import matplotlib.patheffects

PRIMARY = "#2563EB"
SECONDARY = "#F59E0B"
FIG_PA = mpl.colors.LinearSegmentedColormap.from_list(
    "fig_pa", ["#F2EFF7", "#B6A8D0", "#8A6FB0", "#C75D88", "#E8A33D"])


def set_style():
    mpl.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 13,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "axes.labelsize": 13,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.edgecolor": "#374151",
        "axes.labelcolor": "#111827",
        "xtick.color": "#374151",
        "ytick.color": "#374151",
        "xtick.labelsize": 11.5,
        "ytick.labelsize": 11.5,
        "legend.fontsize": 11,
        "legend.frameon": False,
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
        "savefig.dpi": 300,
        "axes.grid": True,
        "grid.color": "#E5E7EB",
        "grid.linewidth": 0.6,
        "grid.alpha": 0.7,
    })


def soften_axes(ax):
    ax.set_axisbelow(True)
    ax.grid(True, color="#E5E7EB", linewidth=0.6, alpha=0.7)


def panel_letter(ax, letter, x=-0.06, y=1.04, size=20):
    ax.text(x, y, letter, transform=ax.transAxes,
            fontsize=size, fontweight="bold", ha="left", va="bottom")
