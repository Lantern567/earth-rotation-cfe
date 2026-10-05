import argparse
import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.transforms import Bbox
import numpy as np
import pandas as pd

import plot_r3_latency_fig3 as latency
import plot_r3_split_figs as split


PACKAGE = Path(__file__).resolve().parents[2]
ORIGINAL_DRAW_C = latency.draw_c
ORIGINAL_DRAW_B = latency.draw_b
ORIGINAL_DRAW_D = latency.draw_d
ORIGINAL_PNG_SIZE = (3814, 3672)
ORIGINAL_PDF_SIZE_PT = (915.2091064453125, 881.1353759765625)
ORIGINAL_CROP_ORIGIN_IN = (-0.0075277777777779525, 0.11282222222222138)


def draw_premium(ax, frame, phi=1.0):
    ORIGINAL_DRAW_C(ax, frame, phi=phi)
    part = frame[(frame.year == 2030) & (frame.perturbation == 'P_mix') & (frame.phi == phi)].copy()
    part['premium'] = 100 * (part.lcoe_elec - part.lcoe_gen) / part.lcoe_gen
    medians = part.groupby('tau_ms').premium.median().reindex(latency.TAU)
    # 箭头跟随实际最大下降；增加情景的标签放在实际数值位置。
    for artist in list(ax.texts):
        if 'crossing a hemisphere' in artist.get_text():
            artist.remove()
        elif artist.get_text().endswith('%') and hasattr(artist, 'xy'):
            index = int(artist.xy[0])
            if index > 0 and medians.iloc[index] > medians.iloc[index - 1]:
                artist.xy = (index, medians.iloc[index])
    drops = medians.to_numpy()[:-1] - medians.to_numpy()[1:]
    index = int(np.argmax(drops)) + 1
    ax.annotate('largest median\npremium decrease',
                xy=(index, max(medians.iloc[index - 1], medians.iloc[index]) + 1),
                xytext=(3.05, 92), fontsize=8.2, color=latency.BETTER,
                fontweight='bold', ha='center', va='center',
                arrowprops=dict(arrowstyle='-|>', color=latency.BETTER, lw=1.1))
    ax.set_xlabel('Additional-network RTT budget (ms)', fontsize=11)
    ax.set_ylabel('Domestic phase-firming premium\n(% of generation, 2030, φ=100%)', fontsize=11)


def draw_premium_components(fig, cell, frame, fs=10.5):
    ORIGINAL_DRAW_B(fig, cell, frame, fs=fs)


def draw_all_country_distribution(fig, cell, frame):
    part = frame[(frame.perturbation == 'P_mix') & (frame.phi == 1)]
    premiums = 100 * (part.lcoe_elec - part.lcoe_gen) / part.lcoe_gen
    upper = max(140, float(np.ceil(premiums.max() / 10) * 10))
    latency.RXG = np.linspace(0, upper, 520)
    before = len(fig.axes)
    ORIGINAL_DRAW_D(fig, cell, frame)
    # 密度曲线保留全部104国输入，并让范围覆盖实际最大值。
    for axis in fig.axes[before:before + 2]:
        axis.set_xlim(0, upper)
        for artist in axis.texts:
            artist.set_zorder(80)
            if artist.get_text() in {str(year) for year in latency.RIDGE_YEARS}:
                artist.set_x(upper * 132 / 134)
    fig.axes[before + 2].set_title('Median across 104 countries — all six RTT budgets',
                                  fontsize=8.6, color='#475569', loc='left', pad=4)


def save_fig5(fig, output):
    # 沿用原画布与原导出尺寸，避免文字变化自动改变图片大小。
    crop_x, crop_y = ORIGINAL_CROP_ORIGIN_IN
    png_bbox = Bbox.from_bounds(crop_x, crop_y, ORIGINAL_PNG_SIZE[0] / 300, ORIGINAL_PNG_SIZE[1] / 300)
    pdf_bbox = Bbox.from_bounds(crop_x, crop_y, ORIGINAL_PDF_SIZE_PT[0] / 72, ORIGINAL_PDF_SIZE_PT[1] / 72)
    fig.savefig(output / 'Fig5.png', dpi=300, bbox_inches=png_bbox, pad_inches=0)
    fig.savefig(output / 'Fig5.pdf', dpi=300, bbox_inches=pdf_bbox, pad_inches=0)
    plt.close(fig)


def validate_fig5(frame, sources, destination):
    keys = ['country', 'tau_ms', 'phi', 'year', 'perturbation']
    numeric = ['lcoe_elec', 'lcoe_gen', 'lcoe_store', 'lcoe_anc', 'unmet_mwh', 'firm_share', 'solver_status']
    if frame[numeric].isna().any().any() or not np.isfinite(frame[numeric].to_numpy()).all():
        raise ValueError('Missing or nonfinite strict Figure 5 inputs')
    if frame.country.nunique() != 104 or frame[keys].duplicated().any():
        raise ValueError('Figure 5 requires 104 identified countries and unique scenario keys')
    if not (frame.unmet_mwh.eq(0).all() and frame.firm_share.eq(1).all() and frame.solver_status.eq(0).all()):
        raise ValueError('Figure 5 requires optimal dispatch with zero hourly unserved energy')
    if not np.allclose(frame.lcoe_elec, frame.lcoe_gen + frame.lcoe_store + frame.lcoe_anc, rtol=0, atol=1e-8):
        raise ValueError('Strict cost components do not sum to total cost')
    if frame.groupby(['year', 'tau_ms', 'phi', 'perturbation']).country.nunique().ne(104).any():
        raise ValueError('Incomplete country coverage in a Figure 5 scenario')
    part = frame[(frame.year == 2030) & (frame.perturbation == 'P_mix') & (frame.phi == 1)].copy()
    part['premium'] = 100 * (part.lcoe_elec - part.lcoe_gen) / part.lcoe_gen
    medians = part.groupby('tau_ms').premium.median().reindex(latency.TAU)
    if medians.isna().any():
        raise ValueError('Missing 2030 network budget')
    grid = frame[(frame.year == 2030) & (frame.perturbation == 'P_mix')]
    if grid.groupby(['tau_ms', 'phi']).size().shape[0] != 36:
        raise ValueError('Figure 5 rose requires all 36 scenarios')
    grouped = grid.groupby(['tau_ms', 'phi'])
    rose = grouped[['lcoe_gen', 'lcoe_store', 'lcoe_anc']].mean()
    rose['country_n'] = grouped.country.nunique()
    rose['storage_premium_pct'] = 100 * rose.lcoe_store / rose.lcoe_gen
    rose['ancillary_premium_pct'] = 100 * rose.lcoe_anc / rose.lcoe_gen
    annual = frame[(frame.perturbation == 'P_mix') & (frame.phi == 1)].copy()
    annual['premium_pct'] = 100 * (annual.lcoe_elec - annual.lcoe_gen) / annual.lcoe_gen
    annual_summary = annual.groupby(['year', 'tau_ms']).agg(
        country_n=('country', 'nunique'), premium_median_pct=('premium_pct', 'median'),
        premium_min_pct=('premium_pct', 'min'), premium_max_pct=('premium_pct', 'max'))
    if annual_summary.shape[0] != 36 or annual_summary.country_n.ne(104).any():
        raise ValueError('Figure 5 ridgelines and trajectories require all six years and six budgets')
    waterfall = medians.rename('premium_median_pct').to_frame()
    waterfall['country_n'] = part.groupby('tau_ms').country.nunique()
    waterfall['premium_decrease_pp'] = -waterfall.premium_median_pct.diff()
    upper = max(140, float(np.ceil(annual.premium_pct.max() / 10) * 10))
    report = {
        'source_sha256': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
        'countries': int(frame.country.nunique()),
        'rows': len(frame),
        'unmet_mwh_max': float(frame.unmet_mwh.max()),
        'firm_share_min': float(frame.firm_share.min()),
        'solver_status': sorted(frame.solver_status.unique().tolist()),
        'premium_2030_country_median_pct': {str(budget): float(value) for budget, value in medians.items()},
        'rose_aggregation': 'Ratio of country-mean storage/ancillary cost to country-mean generation cost, as in the submitted plotting code',
        'ridgeline_input_countries_per_year_and_facet': 104,
        'ridgeline_kde_bandwidth_factor': 0.42,
        'ridgeline_premium_range_pct': [0, upper],
        'maximum_country_premium_pct': float(annual.premium_pct.max()),
        'annual_trajectory_aggregation': 'Within-year, within-RTT-budget median of all 104 country premiums',
        'cost_boundary': 'Remaining domestic load after routing and domestic refit; receiver and computing/network costs excluded',
        'network_budget': 'Additional-network RTT budget',
        'layout': 'Original four panels: waterfall, 36-sector polar rose, two ridgelines with six-budget annual trajectories, three Robinson maps',
        'canvas_inches': [13.2, 12.8],
        'png_pixels': list(ORIGINAL_PNG_SIZE),
        'pdf_page_points': list(ORIGINAL_PDF_SIZE_PT),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    waterfall.to_csv(destination.parent / 'fig5_waterfall_strict.csv')
    rose.to_csv(destination.parent / 'fig5_rose_strict.csv')
    annual_summary.to_csv(destination.parent / 'fig5_annual_strict.csv')
    annual[(annual.year.isin([2025, 2030, 2050])) & (annual.tau_ms == 500)][
        ['country', 'year', 'lcoe_gen', 'lcoe_store', 'lcoe_anc', 'lcoe_elec', 'premium_pct']
    ].to_csv(destination.parent / 'fig5_maps_strict.csv', index=False)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


def draw_s9(storage, output):
    strict = pd.read_csv(storage / 'strict_reliability_2030.csv')
    strict = strict[strict['mode'] == 'strict']
    batch = pd.read_csv(storage / 'batch_deadlines_2030.csv')
    if len(strict) != 208 or len(batch) != 416:
        raise ValueError('Supplementary Figure S9 requires complete strict and deadline comparisons')
    latency.R3P.set_style(11)
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    colors = ['#7C57C9', '#E8A33D']
    local = strict[strict.tier == 'local'].set_index('country').sort_index()
    remote = strict[strict.tier == 'global'].set_index('country').reindex(local.index)
    for axis, column, label in [(axes[0, 0], 'lcoe_elec', 'Domestic firmed cost\n(USD/MWh remaining load)'),
                                 (axes[0, 1], 'E_ld', 'LDES energy (MWh)\nper 100 MW remaining load')]:
        values = [local[column].to_numpy(), remote[column].to_numpy()]
        for first, second in zip(*values):
            axis.plot([1, 2], [first, second], color='#BBBBBB', lw=.45, alpha=.55)
        boxes = axis.boxplot(values, positions=[1, 2], widths=.4, showfliers=False, patch_artist=True)
        for patch, color in zip(boxes['boxes'], colors):
            patch.set_facecolor(color)
            patch.set_alpha(.55)
        axis.set_xticks([1, 2], ['Domestic only', 'Global match'])
        axis.set_ylabel(label)
        axis.set_ylim(bottom=0)
    for axis, column, label in [(axes[1, 0], 'lcoe_elec', 'Domestic firmed cost\n(USD/MWh domestic load)'),
                                 (axes[1, 1], 'E_li', 'Li energy (MWh)\nper 100 MW domestic load')]:
        pivot = batch.pivot(index='country', columns='deadline_h', values=column).reindex(columns=[0, 1, 6, 24])
        for row in pivot.to_numpy():
            axis.plot(range(4), row, color='#B6A8D0', lw=.5, alpha=.4)
        axis.plot(range(4), pivot.median(), color='#3D348B', marker='o', lw=2)
        axis.set_xticks(range(4), ['0 h', '1 h', '6 h', '24 h'])
        axis.set_xlabel('Additional batch completion window')
        axis.set_ylabel(label)
        axis.set_ylim(bottom=0)
    for index, axis in enumerate(axes.flat):
        axis.text(-.16, 1.06, 'abcd'[index], transform=axis.transAxes, fontweight='bold', fontsize=16)
        axis.spines[['top', 'right']].set_visible(False)
    fig.subplots_adjust(left=.13, right=.98, top=.93, bottom=.08, wspace=.38, hspace=.43)
    for suffix in ('png', 'pdf'):
        fig.savefig(output / f'FigS9.{suffix}', dpi=300)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-results', type=Path, default=PACKAGE / 'results' / 'storage')
    parser.add_argument('--audit-results', type=Path, default=PACKAGE / 'results' / 'storage')
    parser.add_argument('--country-meta', type=Path, default=PACKAGE / 'inputs' / 'hourly' / 'country_meta.csv')
    parser.add_argument('--output-dir', type=Path, default=PACKAGE / 'figures')
    parser.add_argument('--figure', choices=['all', 'fig5', 's9'], default='all')
    parser.add_argument('--validation-output', type=Path, default=PACKAGE / 'results' / 'figures' / 'fig5_style_validation.json')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.figure in ('all', 'fig5'):
        sources = [args.storage_results / name for name in ('r3_dispatch_grid_2030.csv', 'r3_dispatch_yearly_phi1.csv')]
        frames = [pd.read_csv(path, keep_default_na=False, na_values=['']) for path in sources]
        frame = pd.concat(frames, ignore_index=True).drop_duplicates(['country', 'tau_ms', 'phi', 'year', 'perturbation'])
        validate_fig5(frame, sources, args.validation_output)
        latency.R3P.COUNTRY_META = args.country_meta
        latency.draw_c = draw_premium
        latency.draw_b = draw_premium_components
        latency.draw_d = draw_all_country_distribution
        latency.load = lambda: (frame, None)
        split.R3L = latency
        split._save = lambda fig, name: save_fig5(fig, args.output_dir)
        split.render_results()
        plt.close('all')
        print('Figure 5 generated in the original submitted style from complete strict source tables')
    if args.figure in ('all', 's9'):
        draw_s9(args.audit_results, args.output_dir)
        print('Figure S9 generated from complete strict source tables')


if __name__ == '__main__':
    main()
