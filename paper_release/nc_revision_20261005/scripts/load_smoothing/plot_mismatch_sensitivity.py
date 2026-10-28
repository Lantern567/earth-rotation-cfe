import argparse
import hashlib
import io
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, findfont
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
STATIC = [('base', 0.), ('static10', .1), ('static25', .25), ('static50', .5), ('static75', .75), ('flat100', 1.)]
DAILY = [('base', 0.), ('daily10', .1), ('daily25', .25), ('daily50', .5), ('daily75', .75)]
CASES = dict(STATIC + DAILY)
COLORS = {'static': '#4477AA', 'daily': '#EE7733'}
LABELS = {'static': 'Fixed flat component', 'daily': 'Finite daily pool'}
CAPTION = (
    'Figure S10 | Conditional annual power-shape sensitivity to fixed and finite background components. '
    'a, Country-median annual uncovered fraction U from the original NNLS procedure, with all components '
    'permitted in the matching comparison. Domestic generation is refitted and partner annual energy is '
    'set to each scenario\'s domestic shortfall. Points retain every tested component share; the daily-pool '
    'series joins the common zero-share baseline. b, Empirical cumulative distributions of country-paired '
    'changes in U at a 50% component share, relative to the same country\'s baseline, in percentage points. '
    'c, At the same 50% share, country medians under the original refit-and-budget procedure, refitted '
    'domestic generation with the baseline partner annual-energy budget, and unchanged baseline hourly '
    'domestic-plus-partner supply. d, Country-paired U at a 50% share when all components are permitted '
    'versus when only the interactive component may be routed, using the same unmatched-energy LP '
    'objective, domestic shortfall and partner annual-energy budget. Each point denotes a country; '
    'diamonds denote component-wise country medians, and the dashed line denotes equality. Panels a–c '
    'use the original NNLS procedure; panel d uses the metric-aligned LP. All countries are retained without sampling '
    'confidence intervals. Annual demand energy is conserved within each shape scenario. Component '
    'shares and daily scheduling are assumptions; these comparisons describe normalized power shapes '
    'and do not measure global or facility electricity.'
)


def read_inputs(input_dir, expected_countries):
    frames, fingerprints = {}, {}
    for name in ['routing_results.csv', 'country_results.csv']:
        path = input_dir / name
        raw = path.read_bytes()
        frames[name] = pd.read_csv(io.BytesIO(raw), keep_default_na=False, na_values=[''])
        fingerprints[name] = {'path': str(path.resolve()), 'sha256': hashlib.sha256(raw).hexdigest()}
    routes = frames['routing_results.csv']
    countries = frames['country_results.csv']
    required_r = {'country', 'case', 'method', 'budget', 'scope', 'annual_uncovered_share'}
    required_c = {'country', 'case', 'beta', 'annual_energy', 'entirely_frozen_nnls_share'}
    for frame, required in [(routes, required_r), (countries, required_c)]:
        if not required.issubset(frame.columns):
            raise ValueError(f'Missing input columns: {sorted(required - set(frame.columns))}')
    all_routes = routes.copy()
    routes = routes.loc[routes['method'].eq('NNLS')].copy()
    if routes.duplicated(['country', 'case', 'budget', 'scope']).any():
        raise ValueError('Duplicate NNLS country/case/budget/scope rows')
    if countries.duplicated(['country', 'case']).any():
        raise ValueError('Duplicate country/case rows')
    reference = set(countries.loc[countries['case'].eq('base'), 'country'])
    if len(reference) != expected_countries:
        raise ValueError(f'Expected {expected_countries} baseline countries; found {len(reference)}')
    for case, beta in CASES.items():
        group = countries.loc[countries['case'].eq(case)]
        if set(group['country']) != reference or len(group) != expected_countries:
            raise ValueError(f'Incomplete country input for {case}')
        if not np.allclose(group['beta'], beta, atol=1e-12, rtol=0):
            raise ValueError(f'Unexpected beta for {case}')
        for budget in ['current_R', 'fixed_R0']:
            for scope in ['upper', 'restricted']:
                selected = routes.loc[routes['case'].eq(case) & routes['budget'].eq(budget) & routes['scope'].eq(scope)]
                if set(selected['country']) != reference or len(selected) != expected_countries:
                    raise ValueError(f'Incomplete NNLS routing input for {case}/{budget}/{scope}')
    for values in [routes['annual_uncovered_share'], countries['entirely_frozen_nnls_share']]:
        if not np.isfinite(values).all() or (values < -1e-10).any() or (values > 1 + 1e-10).any():
            raise ValueError('Invalid uncovered fractions')
    annual = countries.pivot(index='country', columns='case', values='annual_energy')
    if not np.allclose(annual[list(CASES)].to_numpy(), annual['base'].to_numpy()[:, None], atol=1e-7, rtol=1e-10):
        raise ValueError('Annual-energy conservation failed')
    return routes, countries, fingerprints, all_routes


def eligibility_controls(all_routes, directory, expected_countries):
    path = directory / 'routing_results.csv'
    raw = path.read_bytes()
    restricted = pd.read_csv(io.BytesIO(raw), keep_default_na=False, na_values=[''])
    upper = all_routes.loc[all_routes['method'].eq('LP') & all_routes['scope'].eq('upper')
        & all_routes['budget'].eq('current_R') & all_routes['case'].isin(['static50', 'daily50'])]
    restricted = restricted.loc[restricted['method'].eq('LP') & restricted['scope'].eq('restricted')
        & restricted['budget'].eq('current_R') & restricted['case'].isin(['static50', 'daily50'])]
    required = ['country', 'case', 'annual_uncovered_share', 'annual_energy',
        'domestic_shortfall_energy', 'partner_energy_budget']
    if upper.duplicated(['country', 'case']).any() or restricted.duplicated(['country', 'case']).any():
        raise ValueError('Duplicate eligibility-LP country/case inputs')
    for case in ['static50', 'daily50']:
        u, r = upper.loc[upper['case'].eq(case)], restricted.loc[restricted['case'].eq(case)]
        if len(u) != expected_countries or len(r) != expected_countries or set(u['country']) != set(r['country']):
            raise ValueError(f'Incomplete all-country eligibility LP pairing: {case}')
    paired = upper[required].merge(restricted[required], on=['country', 'case'],
        suffixes=('_upper', '_restricted'), validate='one_to_one')
    for field in ['annual_energy', 'domestic_shortfall_energy', 'partner_energy_budget']:
        if np.abs(paired[field + '_upper'] - paired[field + '_restricted']).max() > 1e-7:
            raise ValueError(f'Eligibility LP controls differ in {field}')
    if (paired['annual_uncovered_share_restricted'] < paired['annual_uncovered_share_upper'] - 1e-8).any():
        raise ValueError('Nested eligibility LP ordering failed')
    return paired, {'path': str(path.resolve()), 'sha256': hashlib.sha256(raw).hexdigest()}


def route_values(routes, case, budget='current_R', scope='upper'):
    selected = routes.loc[routes['case'].eq(case) & routes['budget'].eq(budget) & routes['scope'].eq(scope)]
    return selected.set_index('country')['annual_uncovered_share'].sort_index() * 100


def aggregate(routes, countries, lp_controls):
    records = []
    base = route_values(routes, 'base')
    for family, cases in [('static', STATIC), ('daily', DAILY)]:
        for case, beta in cases:
            values = route_values(routes, case)
            changes = values - base
            records.append({'panel': 'a', 'method': 'NNLS', 'family': family, 'case': case, 'beta': beta, 'n': len(values),
                'median_U_pct': float(values.median()), 'paired_change_median_pp': float(changes.median()),
                'paired_change_q25_pp': float(changes.quantile(.25)), 'paired_change_q75_pp': float(changes.quantile(.75)),
                'maximum_absolute_change_pp': float(changes.abs().max())})
    for family, case in [('static', 'static50'), ('daily', 'daily50')]:
        for control in ['refit_current', 'refit_fixed_R0', 'frozen_supply']:
            if control == 'frozen_supply':
                values = countries.loc[countries['case'].eq(case)].set_index('country')['entirely_frozen_nnls_share'] * 100
            else:
                values = route_values(routes, case, budget='fixed_R0' if control == 'refit_fixed_R0' else 'current_R')
            records.append({'panel': 'c', 'method': 'NNLS', 'family': family, 'case': case, 'beta': .5, 'control': control,
                'n': len(values), 'median_U_pct': float(values.median())})
        for scope in ['upper', 'restricted']:
            values = lp_controls.loc[lp_controls['case'].eq(case), 'annual_uncovered_share_' + scope] * 100
            records.append({'panel': 'd', 'method': 'LP', 'family': family, 'case': case, 'beta': .5, 'scope': scope,
                'n': len(values), 'median_U_pct': float(values.median())})
    return pd.DataFrame(records)


def configure_style():
    findfont(FontProperties(family='Arial'), fallback_to_default=False)
    plt.rcParams.update({'font.family': 'Arial', 'font.size': 8, 'axes.labelsize': 8,
        'xtick.labelsize': 7.5, 'ytick.labelsize': 7.5, 'legend.fontsize': 7.5,
        'axes.linewidth': .7, 'xtick.major.width': .7, 'ytick.major.width': .7,
        'xtick.major.size': 3, 'ytick.major.size': 3, 'pdf.fonttype': 42,
        'ps.fonttype': 42, 'axes.unicode_minus': True})


def ecdf(ax, values, color):
    x = np.sort(values.to_numpy())
    y = np.arange(1, len(x) + 1) / len(x)
    ax.step(np.r_[x[0], x], np.r_[0., y], where='post', color=color, lw=1.4)


def make_figure(routes, countries, table, n, lp_controls):
    configure_style()
    fig, axes = plt.subplots(2, 2, figsize=(6.15, 5.5))
    fig.subplots_adjust(left=.12, right=.98, bottom=.145, top=.895, wspace=.46, hspace=.49)
    handles = [Line2D([], [], color=COLORS[f], marker='o', lw=1.3, ms=3.5, label=LABELS[f]) for f in COLORS]
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.55, .99), ncol=2, frameon=False,
        columnspacing=1.8, handlelength=1.5)
    for label, ax in zip('abcd', axes.flat):
        ax.text(-.23, 1.035, label, transform=ax.transAxes, fontsize=10, fontweight='bold', va='bottom')
        ax.spines[['top', 'right']].set_visible(False)
        ax.yaxis.set_major_locator(MaxNLocator(5))

    ax = axes[0, 0]
    for family in COLORS:
        rows = table.loc[table['panel'].eq('a') & table['family'].eq(family)].sort_values('beta')
        ax.plot(rows['beta'], rows['median_U_pct'], marker='o', ms=3.7, lw=1.3, color=COLORS[family])
    ax.set_xticks([0, .1, .25, .5, .75, 1], ['0', '.1', '.25', '.5', '.75', '1'])
    ax.set_xlabel('Component energy share, β')
    ax.set_ylabel('Country-median U (%)')
    ax.set_xlim(-.04, 1.04)

    ax = axes[0, 1]
    base = route_values(routes, 'base')
    changes = []
    for family, case in [('static', 'static50'), ('daily', 'daily50')]:
        paired = route_values(routes, case) - base
        changes.append(paired)
        ecdf(ax, paired, COLORS[family])
    ax.axvline(0, color='.65', ls='--', lw=.7, zorder=0)
    all_changes = pd.concat(changes)
    span = max(float(all_changes.max() - all_changes.min()), 1.)
    ax.set_xlim(float(all_changes.min() - .06 * span), float(all_changes.max() + .06 * span))
    ax.set_ylim(0, 1.02)
    ax.set_xlabel('ΔU versus baseline\n(percentage points)')
    ax.set_ylabel('Cumulative country fraction')
    ax.text(.97, .04, f'β = 0.50; n = {n}', transform=ax.transAxes, ha='right', fontsize=7)

    ax = axes[1, 0]
    controls = ['refit_current', 'refit_fixed_R0', 'frozen_supply']
    for position, control in enumerate(controls):
        rows = table.loc[table['panel'].eq('c') & table['control'].eq(control)].set_index('family')
        pair = [float(rows.loc[f, 'median_U_pct']) for f in ['static', 'daily']]
        ax.plot([position - .13, position + .13], pair, color='.72', lw=1, zorder=1)
        for offset, family, value in zip([-.13, .13], ['static', 'daily'], pair):
            ax.scatter(position + offset, value, s=24, color=COLORS[family], zorder=3)
    ax.set_xticks(range(3), ['Refit\nR(β)', 'Refit\nR0', 'Frozen\nsupply'])
    ax.set_xlim(-.4, 2.4)
    ax.set_ylabel('Country-median U (%)')
    ax.set_xlabel('Supply control')
    ax.text(.03, .96, 'β = 0.50', transform=ax.transAxes, va='top', fontsize=7)

    ax = axes[1, 1]
    limits = []
    for family, case in [('static', 'static50'), ('daily', 'daily50')]:
        paired = lp_controls.loc[lp_controls['case'].eq(case)].set_index('country')[
            ['annual_uncovered_share_upper', 'annual_uncovered_share_restricted']] * 100
        paired = paired.rename(columns={'annual_uncovered_share_upper': 'upper', 'annual_uncovered_share_restricted': 'restricted'})
        if paired.isna().any().any():
            raise ValueError('Incomplete country pairing in panel d')
        limits.extend(paired.to_numpy().ravel())
        ax.scatter(paired['upper'], paired['restricted'], s=8, alpha=.58, linewidths=0, color=COLORS[family])
        ax.scatter(paired['upper'].median(), paired['restricted'].median(), marker='D', s=30,
            color=COLORS[family], edgecolors='white', linewidths=.65, zorder=4)
    high = max(limits) * 1.08
    ax.plot([0, high], [0, high], ls='--', color='.65', lw=.8, zorder=0)
    ax.set_xlim(0, high)
    ax.set_ylim(0, high)
    ax.set_aspect('equal', adjustable='box')
    ax.set_xlabel('All components eligible, U (%)')
    ax.set_ylabel('Interactive-only routing, U (%)')
    ax.text(.03, .96, 'β = 0.50', transform=ax.transAxes, va='top', fontsize=7)
    fig.text(.55, .027, f'NNLS (a–c); same-objective LP (d); {n} countries; scenario power shapes.',
        ha='center', fontsize=7, color='.3')
    return fig


def main():
    parser = argparse.ArgumentParser(description='Validate or render Fig. S10 with NNLS sensitivity and nested eligibility LP controls')
    parser.add_argument('--input-dir', type=Path, default=ROOT / 'results')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'figures')
    parser.add_argument('--eligibility-dir', type=Path, default=ROOT / 'results_eligibility')
    parser.add_argument('--expected-countries', type=int, default=104)
    parser.add_argument('--dpi', type=int, default=300)
    parser.add_argument('--render', action='store_true', help='Write FigS10 PDF, PNG, aggregate CSV and provenance JSON')
    args = parser.parse_args()
    routes, countries, fingerprints, all_routes = read_inputs(args.input_dir, args.expected_countries)
    lp_controls, eligibility_fingerprint = eligibility_controls(all_routes, args.eligibility_dir, args.expected_countries)
    fingerprints['eligibility_lp_results.csv'] = eligibility_fingerprint
    table = aggregate(routes, countries, lp_controls)
    print(table.to_string(index=False), flush=True)
    if not args.render:
        print('Input validation passed; no figure files written. Add --render to export.', flush=True)
        return
    args.output_dir.mkdir(parents=True, exist_ok=True)
    fig = make_figure(routes, countries, table, args.expected_countries, lp_controls)
    # 不裁剪画布，保持规定的插图尺寸。
    fig.savefig(args.output_dir / 'FigS10.pdf', metadata={'Title': 'Conditional annual power-shape sensitivity',
        'Subject': 'NNLS sensitivity (a-c); same-objective eligibility LP (d); scenario power shapes'})
    fig.savefig(args.output_dir / 'FigS10.png', dpi=args.dpi)
    table.to_csv(args.output_dir / 'FigS10_plot_values.csv', index=False)
    metadata = {'input_files': fingerprints, 'methods': {'a': 'NNLS', 'b': 'NNLS', 'c': 'NNLS', 'd': 'LP'},
        'countries': args.expected_countries,
        'width_in': 6.15, 'height_in': 5.5, 'dpi': args.dpi, 'sampling_confidence_intervals': False,
        'caption_english': CAPTION, 'source_scope': 'Conditional annual power-shape sensitivity'}
    (args.output_dir / 'FigS10_plot_metadata.json').write_text(json.dumps(metadata, indent=2, allow_nan=False), encoding='utf-8')
    plt.close(fig)
    print(f'Rendered {args.output_dir / "FigS10.pdf"} and PNG', flush=True)


if __name__ == '__main__':
    main()
