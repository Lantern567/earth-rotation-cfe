from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator, StrMethodFormatter

PACKAGE = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description='Plot Supplementary Fig. S8 and evaluate explicitly assumed prices on frozen power-case ledgers')
parser.add_argument('--results-dir', type=Path, default=PACKAGE / 'results/power')
parser.add_argument('--figure-dir', type=Path, default=PACKAGE / 'figures/FigS8')
args = parser.parse_args()
RESULTS = args.results_dir.resolve()
FIGURES = args.figure_dir.resolve()
FIGURES.mkdir(parents=True, exist_ok=True)
summary = pd.read_csv(RESULTS / 'power_case_summary.csv')
ledger = pd.read_csv(RESULTS / 'power_case_hourly_site_ledger.csv')
ledger['timestamp_utc'] = pd.to_datetime(ledger['timestamp_utc'], utc=True)
base = summary[summary['hardware'].eq('H100_NVL') & summary['external_restart_charge_wh_per_replica_activation'].eq(0)].copy()
policies = ['remain_on_idle', 'finite_backfill', 'consolidate_sleep']
labels = ['Remain on', 'Finite backfill', 'Consolidate / sleep']
colors = ['#76549A', '#E69D4B', '#AE9AC8']
budgets = [0, 200, 500]


def case_row(policy, budget):
    rows = base[base['policy'].eq(policy) & base['network_budget_ms'].eq(budget)]
    assert len(rows) == 1
    return rows.iloc[0]


def case_ledger(policy, budget):
    return ledger[ledger['case'].eq(case_row(policy, budget)['case'])].copy()


plt.rcParams.update({'font.family': 'Arial', 'font.size': 9, 'axes.labelsize': 9, 'xtick.labelsize': 8, 'ytick.labelsize': 8, 'legend.fontsize': 7.5, 'pdf.fonttype': 42, 'ps.fonttype': 42, 'axes.linewidth': .7, 'axes.spines.top': False, 'axes.spines.right': False, 'savefig.dpi': 300})
fig, axs = plt.subplots(2, 2, figsize=(7.4, 6.3), layout='constrained')
positions = np.arange(3)
width = .23
for j, (policy, label, color) in enumerate(zip(policies, labels, colors)):
    records = [case_row(policy, budget) for budget in budgets]
    axs[0, 0].bar(positions + (j - 1) * width, [r['same_hour_gap_kwh'] for r in records], width=width, label=label, color=color, edgecolor='none')
    axs[0, 1].bar(positions + (j - 1) * width, [r['gpu_energy_kwh'] for r in records], width=width, label=label, color=color, edgecolor='none')
for ax in axs[0]:
    ax.set_xticks(positions, ['Local', '200', '500'])
    ax.set_xlabel('Added network budget (ms, scenario)')
    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_locator(MaxNLocator(5))
    ax.yaxis.set_major_formatter(StrMethodFormatter('{x:,.0f}'))
    ax.set_axisbelow(True)
    ax.grid(axis='y', color='#e7e7e7', linewidth=.5)
axs[0, 0].set_ylabel('Uncovered GPU electricity (kWh)')
axs[0, 0].set_ylim(0, 1470)
axs[0, 0].legend(loc='upper right', frameon=False)
axs[0, 1].set_ylabel('Total modeled GPU electricity (kWh)')
axs[0, 1].set_ylim(0, 6600)
axs[0, 1].axhline(case_row('remain_on_idle', 0)['clean_supply_kwh'], color='#484848', lw=.8, ls='--')
axs[0, 1].text(1.48, 5980, 'Fixed clean budget: 5,762 kWh', ha='center', fontsize=7.3, color='#484848')

local = case_ledger('remain_on_idle', 0).pivot(index='timestamp_utc', columns='site', values='gpu_power_kw')
route = case_ledger('remain_on_idle', 500).pivot(index='timestamp_utc', columns='site', values='gpu_power_kw')
changes = route - local
assert np.max(np.abs(changes.sum(axis=1))) < 1e-6
for country, color in zip(['US', 'DE', 'JP'], ['#76549A', '#E69D4B', '#777777']):
    axs[1, 0].plot(np.arange(48), changes[country].iloc[:48], color=color, lw=1.2, label=country)
axs[1, 0].axhline(0, color='#333333', lw=.6, ls='--')
axs[1, 0].set_ylabel('Site power change after routing (kW)')
axs[1, 0].set_xlabel('Hour since 10 May 2024 00:00 UTC')
axs[1, 0].set_xticks([0, 12, 24, 36, 48])
axs[1, 0].set_xlim(0, 48)
axs[1, 0].legend(loc='lower right', frameon=False, ncol=3)

bg_uniform = case_ledger('remain_on_idle', 500).groupby('timestamp_utc')['executed_background_job_units'].sum()
bg_backfill = case_ledger('finite_backfill', 500).groupby('timestamp_utc')['executed_background_job_units'].sum()
bg_sleep = case_ledger('consolidate_sleep', 500).groupby('timestamp_utc')['executed_background_job_units'].sum()
assert np.max(np.abs(bg_uniform.to_numpy() - bg_sleep.to_numpy())) < .001
days = bg_uniform.index.floor('D')
daily = bg_uniform.groupby(days).sum()
released = np.array([daily.loc[daily.index <= day].sum() for day in days])
axs[1, 1].step(np.arange(169), np.r_[released, released[-1]] / 1e6, where='post', color='#888888', lw=1, ls=':', label='Finite pool released')
axs[1, 1].plot(np.arange(1, 169), bg_uniform.cumsum() / 1e6, color=colors[0], lw=1.3, label='Remain on / sleep')
axs[1, 1].plot(np.arange(1, 169), bg_backfill.cumsum() / 1e6, color=colors[1], lw=1.3, ls='--', label='Finite backfill')
axs[1, 1].set_ylabel('Background work completed (million job units)')
axs[1, 1].set_xlabel('Hour since 10 May 2024 00:00 UTC')
axs[1, 1].set_xticks([0, 48, 96, 144, 168])
axs[1, 1].set_xlim(0, 168)
axs[1, 1].set_ylim(0, 3.85)
axs[1, 1].legend(loc='upper left', frameon=False)
axs[1, 1].text(162, .16, 'Same final pool: 3.361 million', ha='right', fontsize=7.3)
for letter, ax in zip('abcd', axs.flat):
    ax.text(-.16, 1.03, letter, transform=ax.transAxes, fontsize=12, fontweight='bold')
fig.savefig(FIGURES / 'FigS8.png', dpi=300)
fig.savefig(FIGURES / 'FigS8.pdf')
plt.close(fig)
caption = 'Supplementary Fig. S8. A three-site accounting experiment conserves workload and clean supply across routing and power policies. a, Absolute uncovered GPU electricity for local execution and two assumed added-network budgets. b, Total GPU electricity under the same fixed 5,762.47 kWh clean-supply budget. The experiment uses all 16,803,695 Azure coding arrivals and the same finite 3,360,749 background job units. The remain-on and backfill policies retain all installed GPU idle power; consolidation changes awake counts. c, Changes in the US, Germany and Japan site powers for the first 48 hours under 500 ms routing with GPUs remaining on, relative to local execution; site changes sum to zero each hour. d, Cumulative completion of the same background pool, including its daily release schedule. Background schedules differ within a day and converge at daily deadlines. The three 500 ms policies have uncovered fractions of 15.80%, 13.60% and 9.22%, respectively; each fraction is divided by its own total electricity in b. Origin assignment, design capacity, power interpolation and network delays are controlled assumptions. Reconstructed 2025 wind/solar profiles are paired with 2024 arrival hours. Results quantify modeled power accounting and do not certify request-level service or measured facility consumption.'
assert len(caption.split()) < 300
(FIGURES / 'FigS8_caption.txt').write_text(caption + '\n', encoding='utf-8')
base.to_csv(FIGURES / 'FigS8_source_data.csv', index=False)
changes.reset_index().to_csv(FIGURES / 'FigS8_panel_c_source_data.csv', index=False)
pd.DataFrame({'timestamp_utc': bg_uniform.index, 'uniform_completed_job_units': bg_uniform.to_numpy(), 'backfill_completed_job_units': bg_backfill.to_numpy(), 'sleep_completed_job_units': bg_sleep.to_numpy(), 'cumulative_released_job_units': released}).to_csv(FIGURES / 'FigS8_panel_d_source_data.csv', index=False)

prices = {'uniform_005': {'US': .05, 'DE': .05, 'JP': .05}, 'uniform_010': {'US': .10, 'DE': .10, 'JP': .10}, 'uniform_020': {'US': .20, 'DE': .20, 'JP': .20}, 'site_ascending': {'US': .05, 'DE': .10, 'JP': .20}, 'site_descending': {'US': .20, 'DE': .10, 'JP': .05}}
bills = []
for name, rates in prices.items():
    for policy in policies:
        row = {'price_scenario': name, 'policy': policy, **{f'{country}_price_usd_per_kwh': rates[country] for country in rates}, 'dispatch_frozen': True, 'measured_tariff_or_contract': False}
        for budget, prefix in [(0, 'local'), (500, 'route500')]:
            by_site = case_ledger(policy, budget).groupby('site')['gpu_power_kw'].sum()
            row[f'{prefix}_gpu_energy_kwh'] = float(by_site.sum())
            row[f'{prefix}_modeled_volumetric_cost_usd'] = float(sum(by_site[country] * rates[country] for country in rates))
        row['modeled_cost_change_usd_route_minus_local'] = row['route500_modeled_volumetric_cost_usd'] - row['local_modeled_volumetric_cost_usd']
        if name.startswith('uniform') and policy != 'consolidate_sleep':
            assert abs(row['modeled_cost_change_usd_route_minus_local']) < 1e-8
            row['modeled_cost_change_usd_route_minus_local'] = 0.
        bills.append(row)
billframe = pd.DataFrame(bills)
billframe.to_csv(RESULTS / 'frozen_dispatch_price_sensitivity.csv', index=False)

local_record = case_row('remain_on_idle', 0)
route_record = case_row('remain_on_idle', 500)
avoided_mwh = (local_record['same_hour_gap_kwh'] - route_record['same_hour_gap_kwh']) / 1000.
routed_requests = route_record['routed_request_equivalents']
fees = []
for name in prices:
    cost_change = billframe[billframe['price_scenario'].eq(name) & billframe['policy'].eq('remain_on_idle')]['modeled_cost_change_usd_route_minus_local'].iloc[0]
    for value in (30., 100., 200.):
        assumed_value = avoided_mwh * value
        net_value = assumed_value - cost_change
        fees.append({'price_scenario': name, 'policy_comparison': '500 ms remain-on versus local remain-on', 'assumed_uncovered_energy_shadow_value_usd_per_mwh': value, 'avoided_uncovered_energy_mwh': avoided_mwh, 'modeled_cost_change_usd_route_minus_local': cost_change, 'assumed_clean_match_value_usd': assumed_value, 'net_assumed_value_before_fee_usd': net_value, 'routed_request_equivalents': routed_requests, 'break_even_fee_usd_per_routed_request_equivalent': net_value / routed_requests, 'value_per_all_arriving_requests_usd': net_value / local_record['interactive_requests'], 'actual_electricity_bill_savings_claim': False, 'ppa_or_egress_contract_modeled': False})
pd.DataFrame(fees).to_csv(RESULTS / 'illustrative_routing_fee_thresholds.csv', index=False)
(RESULTS / 'economic_sensitivity_definition.json').write_text(json.dumps({'dispatch': 'frozen original GPU dispatch; prices do not change routing or capacities', 'cost': 'all-site modeled GPU kWh times assumed volumetric site price; excludes PPA contract rights, clean procurement terms, taxes, egress, hardware reservation and other charges', 'fee': '(v * avoided uncovered MWh - modeled volumetric cost change) / routed request equivalents; v is a hypothetical shadow value; a negative threshold means this selected pricing/value scenario provides no positive fee margin', 'observed_tariffs': False, 'prices': prices, 'assumed_shadow_values_usd_per_mwh': [30, 100, 200]}, indent=2), encoding='utf-8')
print(billframe.to_string(index=False))
print(pd.DataFrame(fees)[['price_scenario', 'assumed_uncovered_energy_shadow_value_usd_per_mwh', 'break_even_fee_usd_per_routed_request_equivalent']].to_string(index=False))
print('Caption words', len(caption.split()))
