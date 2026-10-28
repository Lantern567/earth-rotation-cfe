import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits


work = Path(__file__).resolve().parent
root = work.parents[2]
package = root / 'NC返修_20261002/Reproducibility_Package'
read_json = lambda name: json.loads((work / name).read_text(encoding='utf-8'))
grid_summary = read_json('grid_summary.json')
mix_summary = read_json('mix2030_summary.json')
lp_summary = read_json('lp_summary.json')
station_summary = read_json('station_mix_summary.json')
storage_summary = read_json('storage2030_summary.json')
provenance = read_json('input_provenance.json')
reproduction = read_json('reproduction_check.json')
mix_reproduction = read_json('mix2030_reproduction_check.json')
sets = pd.read_csv(work / 'receiver_sets.csv', keep_default_na=False)
grid39 = pd.read_csv(work / 'receivers39/r2_waveform_grid.csv', keep_default_na=False)
grid34 = pd.read_csv(work / 'r2_waveform_grid_34.csv', keep_default_na=False)
lp = pd.read_csv(work / 'lp_country_comparison.csv', keep_default_na=False)
heatmap = pd.read_csv(work / 'fig2_heatmap_comparison.csv')
mix_heatmap = pd.read_csv(work / 'mix2030_heatmap_comparison.csv')
global34 = grid34[grid34.tau_ms.eq(500) & grid34.phi.eq(1)].set_index('country')
global39 = grid39[grid39.tau_ms.eq(500) & grid39.phi.eq(1)].set_index('country')
assert len(grid39) == len(grid34) == 3744
assert len(global34) == 104
assert set(sets.loc[~sets.retained_in_34, 'receiver_iso2']) == {'DK', 'EG', 'GR', 'KW', 'TR'}
assert sets.retained_in_34.sum() == 34
assert (grid34.uncovered_share >= -1e-12).all()
assert (grid34.uncovered_share <= grid34.uncovered_share_baseline + 1e-12).all()
assert (lp.rt_lp_fixed_34.to_numpy() <= global34.reindex(lp.country).uncovered_share.to_numpy() + 1e-8).all()
assert (lp.fixed_change_pp >= -1e-6).all()
assert (lp.pipeline_change_pp >= -1e-6).all()
certificates = pd.read_csv(work / 'lp_numerical_certificates.csv')
assert len(certificates) == 208 and certificates.solver_status.eq(0).all()
assert certificates.duality_gap_relative.abs().max() < 1e-9
assert certificates.primal_inequality_violation.max() < 1e-8
assert certificates.primal_equality_violation.max() < 1e-7
assert read_json('reproduction_check.json')['passed'] and mix_reproduction['passed']
assert storage_summary['all_full_hourly_supply']

script = package / 'scripts/waveform/run_waveform_revision.py'
spec = importlib.util.spec_from_file_location('receiver_read_only_validation', script)
W = importlib.util.module_from_spec(spec)
spec.loader.exec_module(W)
W.DATA = work / 'inputs'
with threadpool_limits(limits=1):
    inputs = W.load_data()
    reach = inputs[6]
    assert reach['UG'][100] == ['EG'], reach['UG'][100]
    retained = set(sets.loc[sets.retained_in_34, 'receiver_iso2'])
    assert not [r for r in reach['UG'][100] if r in retained]

storage = pd.read_csv(work / 'storage2030_global_comparison.csv', keep_default_na=False).set_index('country')
front = pd.read_csv(work / 'storage2030_front_half_validation.csv', keep_default_na=False).set_index('country')
unchanged = front.d34_vs_d39_max_abs_MW.eq(0) & front.fit34_vs_fit39_max_abs_MW.eq(0)
unchanged_cost_error = float(storage.loc[unchanged, 'total_cost_change_USD_per_MWh'].abs().max())
assert unchanged_cost_error < 1e-5, unchanged_cost_error
validation = {'checks_passed': True, 'Fig2_rows_each': 3744, 'Fig2_global_countries': 104,
    'LP_new_solves': 208, 'LP_optimality_and_feasibility_passed': True,
    'LP_subset_monotonicity_passed_per_country': True,
    'fixed_shortfall_LP_not_worse_than_NNLS_per_country': True,
    'all_U_bounded_between_zero_and_domestic_shortfall': True,
    'Uganda_100ms_original_only_receiver': reach['UG'][100],
    'storage_full_hourly_supply_countries': 104,
    'storage_unchanged_float32_input_countries': int(unchanged.sum()),
    'storage_unchanged_input_max_total_cost_error_USD_per_MWh': unchanged_cost_error}
(work / 'validation.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding='utf-8')

headline_rows = []
def add(metric, value39, value34, unit='%', scenario='500 ms, phi=1; median across 104 countries'):
    diff = float(value34 - value39)
    headline_rows.append({'metric': metric, 'scenario': scenario, 'unit': unit,
        'value_39': value39, 'value_34': value34, 'difference_34_minus_39': diff,
        'difference_unit': 'pp' if unit == '%' else unit})

add('Fig2 domestic station NNLS U', grid_summary['domestic_39_median_percent'], grid_summary['domestic_34_median_percent'], scenario='50 ms, phi=0; median across 104 countries')
add('Fig2 global station NNLS U', grid_summary['global_39_median_percent'], grid_summary['global_34_median_percent'])
add('Fixed domestic NNLS shortfall: routing LP U', lp_summary['same_shortfall_39_median_percent'], lp_summary['same_shortfall_34_median_percent'])
add('Domestic LP then routing LP U', lp_summary['pipeline_39_median_percent'], lp_summary['pipeline_34_median_percent'])
add('2030 Mix country x technology domestic U', mix_summary['domestic_39_median_percent'], mix_summary['domestic_34_median_percent'], scenario='50 ms, phi=0; median across 104 countries')
add('2030 Mix country x technology global U', mix_summary['global_39_median_percent'], mix_summary['global_34_median_percent'])
add('2030 Mix station basis domestic U', station_summary['station_Mix2030']['domestic_U']['39'], station_summary['station_Mix2030']['domestic_U']['34'], scenario='50 ms, phi=0; new cross-basis calculation; median across 104 countries')
add('2030 Mix station basis global U', station_summary['station_Mix2030']['global_U']['39'], station_summary['station_Mix2030']['global_U']['34'], scenario='500 ms, phi=1; new cross-basis calculation; median across 104 countries')
for version, frame in [(39, grid39), (34, grid34)]:
    assert np.allclose(frame.groupby('country').uncovered_share_baseline.nunique(), 1)
fig3 = []
for tau in [100, 150, 200, 500]:
    a = grid39[grid39.tau_ms.eq(tau) & grid39.phi.eq(1)]
    b = grid34[grid34.tau_ms.eq(tau) & grid34.phi.eq(1)]
    fig3.append({'tau_ms': tau, 'mean_covered_39_percent': 100 * a.migrated_share.mean(),
        'mean_covered_34_percent': 100 * b.migrated_share.mean(),
        'mean_routed_U_39_percent': 100 * a.uncovered_share.mean(),
        'mean_routed_U_34_percent': 100 * b.uncovered_share.mean()})
    add(f'Fig3 mean covered fraction at {tau} ms', 100 * a.migrated_share.mean(), 100 * b.migrated_share.mean(), scenario=f'{tau} ms, phi=1; mean across 104 countries')
pd.DataFrame(fig3).to_csv(work / 'fig3_mean_coverage_comparison.csv', index=False)
add('Fig5 domestic 2030 firming premium', storage_summary['domestic_median_firming_premium_percent_39_and_34'], storage_summary['domestic_median_firming_premium_percent_39_and_34'], scenario='50 ms, phi=0; unchanged domestic solution reused; median across 104 countries')
add('Fig5 global 2030 firming premium', storage_summary['global_39_median_firming_premium_percent'], storage_summary['global_34_median_firming_premium_percent'])
add('Fig5 global 2030 total cost', storage_summary['global_39_median_total_cost_USD_per_MWh'], storage_summary['global_34_median_total_cost_USD_per_MWh'], unit='USD/MWh')
add('Fig5 global 2030 storage cost', storage_summary['global_39_median_storage_cost_USD_per_MWh'], storage_summary['global_34_median_storage_cost_USD_per_MWh'], unit='USD/MWh')
headlines = pd.DataFrame(headline_rows)
headlines.to_csv(work / 'headline_comparison.csv', index=False)

def table(columns, records, digits=6):
    rows = ['| ' + ' | '.join(columns) + ' |', '| ' + ' | '.join(['---'] * len(columns)) + ' |']
    for record in records:
        cells = []
        for value in record:
            if isinstance(value, (float, np.floating)):
                if abs(value) < 1e-9:
                    value = 0.
                cells.append(f'{value:.{digits}f}')
            else:
                cells.append(str(value))
        rows.append('| ' + ' | '.join(cells) + ' |')
    return '\n'.join(rows)

compact_rows = [[r['metric'], r['value_39'], r['value_34'], r['difference_34_minus_39'], r['unit'], r['difference_unit']] for r in headline_rows]
key_table = table(['指标', '39 国', '34 国', '34−39', '数值单位', '差值单位'], compact_rows)
all_cells = table(['φ', 'τ (ms)', '39 国中位 U (%)', '34 国中位 U (%)', '差值 (pp)'],
    heatmap[['phi', 'tau_ms', 'median_U_39_percent', 'median_U_34_percent', 'difference_pp']].itertuples(index=False, name=None))
any_tier = pd.read_csv(work / 'top10_any_tier_affected_countries.csv', keep_default_na=False)
global_top = pd.read_csv(work / 'top10_global_affected_countries.csv', keep_default_na=False)
names = pd.read_csv(work / 'inputs/country_meta.csv', keep_default_na=False).set_index('iso2').country_long
def top_records(frame):
    return [[r.country, names.loc[r.country], int(r.tau_ms), r.phi, 100*r.uncovered_share_39, 100*r.uncovered_share_34, r.change_pp] for r in frame.itertuples()]
top_cols = ['ISO', '国家', 'τ (ms)', 'φ', '39 国 U (%)', '34 国 U (%)', '变化 (pp)']
any_table = table(top_cols, top_records(any_tier))
global_table = table(top_cols, top_records(global_top))
business = pd.read_csv(work / 'business_station_summary.csv')
business_table = table(['工作时段推理占比 β', '国内 U (%)', '全球 U：39 国 (%)', '全球 U：34 国 (%)', '差值 (pp)'],
    business[['business_fraction_of_inference', 'domestic_U_percent', 'global_U_39_percent', 'global_U_34_percent', 'change_pp']].itertuples(index=False, name=None))
lp_top = lp.sort_values('fixed_change_pp', ascending=False).head(10)
lp_top.to_csv(work / 'lp_top10_affected_countries.csv', index=False)
input_table = table(['输入', 'SHA-256', '使用路径'], [[name, record['sha256'], record['path_used']] for name, record in provenance['inputs'].items()])
retained_list = ', '.join(sets.loc[sets.retained_in_34, 'receiver_iso2'])
original_list = ', '.join(sets.receiver_iso2)
si_rows = [
    ['Unperturbed demand, domestic NNLS', grid_summary['domestic_39_median_percent'], grid_summary['domestic_34_median_percent']],
    ['Unperturbed demand, global NNLS routing', grid_summary['global_39_median_percent'], grid_summary['global_34_median_percent']],
    ['Same domestic NNLS shortfall, global routing LP', lp_summary['same_shortfall_39_median_percent'], lp_summary['same_shortfall_34_median_percent']],
    ['Domestic LP followed by global routing LP', lp_summary['pipeline_39_median_percent'], lp_summary['pipeline_34_median_percent']],
    ['2030 Mix, country × technology basis, domestic NNLS', mix_summary['domestic_39_median_percent'], mix_summary['domestic_34_median_percent']],
    ['2030 Mix, country × technology basis, global NNLS routing', mix_summary['global_39_median_percent'], mix_summary['global_34_median_percent']]]
si_table = table(['Demand and matching calculation', '39 candidates: median U (%)', '34 operating locations: median U (%)'], si_rows, digits=4)
si = f'''Restricting receivers to the 34 countries with operating hyperscale regions by 31 December 2025 preserves the positive spatial matching residual. We removed Denmark (DK), Egypt (EG), Greece (GR), Kuwait (KW) and Türkiye (TR) from the receiver set while retaining all 104 demand countries and the original hourly inputs, distance-based round-trip-time model, domestic fitting procedure, partner energy normalization, six latency thresholds and six routable shares. The unperturbed-demand median at 500 ms and full routing eligibility remains 12.7142%; the fixed-domestic-shortfall routing LP and the domestic-LP-then-routing-LP calculation retain medians of 12.2081% and 12.3700%, respectively, with positive residuals in every country. On the country × technology basis, the 2030 Mix global median changes from 13.8589% to 13.8571%, while its domestic median remains 33.2803%. Across the 36 unperturbed-demand grid cells, the largest change in the country median is 0.7452 percentage points. Country effects can be larger under tighter latency thresholds: at 100 ms and full routing eligibility, Uganda loses its only eligible foreign receiver, Egypt, and its residual increases from 34.1809% to 50.3286%. These results retain the central finding that spatial matching substantially reduces the gap while leaving a positive residual; local benefits under tighter latency limits depend on receiver availability.

{si_table}

Table. Receiver-set sensitivity of the country-median annual uncovered share U (n = 104 countries). Domestic cases use φ = 0; global cases use τ = 500 ms and φ = 1. Each percentage is divided by the original annual demand in its own scenario. The first four rows use the unperturbed demand and station basis; the last two use the 2030 Mix demand and country × technology basis. Domestic fitting, energy normalization and all other inputs are held fixed between the receiver sets. All 104 countries remain in the demand sample.
'''
(work / 'suggested_SI_text.md').write_text(si, encoding='utf-8')
main_sentence = 'Restricting receivers to 34 locations operating by the end of 2025 preserves the 12.7% global median gap and a positive residual in every country (Supplementary Section [receiver-set sensitivity]).'
(work / 'suggested_main_text_sentence.txt').write_text(main_sentence + '\n', encoding='utf-8')
report = f'''# receiver 名单敏感性计算（2026-10-28）

## 计算结论

**排除五个尚未运营的候选 receiver 后，本文关于空间匹配显著降低缺口、仍留下正残余的主要结论保持成立。** Fig.2 全球角点中位 U 在两组中均为 12.714212%，固定国内 NNLS 缺口的路由 LP 中位 U 均为 12.208116%，国内 LP 后再路由 LP 的中位 U 均为 12.369999%。34 国版本的这三项计算以及 2030 Mix 全球计算均在全部 104 个国家保留正缺口。固定国内缺口的 LP 中，最小国家残余仍为 {lp_summary['same_shortfall_34_minimum_percent']:.6f}%。

**较严格时延下的国家结果对 receiver 名单存在实质敏感性。** 36 格 Fig.2 热图中位数的最大绝对变化为 0.745163 pp（τ = 100 ms、φ = 0.8）；逐国逐格最大变化为 16.147708 pp（乌干达，τ = 100 ms、φ = 1）。乌干达在该档失去唯一外国 receiver 埃及，U 从 34.180915% 升至 50.328623%。全球角点逐国最大绝对变化为 0.163522 pp（突尼斯）。因此应同时报告总体中位数和受影响国家，不能概括为“名单变化对各国均无影响”。

## 输入与方法

- 本次计算按用户指定删除 DK、EG、GR、KW、TR；需求国仍为 104 个。这五国继续作为需求国保留，也继续使用各自国内风光曲线。region 运营状态的资格判定沿用主会话已确定的分组。
- 原 39 国：{original_list}。
- 保留 34 国：{retained_list}。
- 每个需求国排除自身作为外国 partner，因此全球角点实际有 33 或 34 个外国 partner。`receiver_sets.csv` 给出精确名单。
- 使用原脚本 `scripts/waveform/run_waveform_revision.py` 的 `load_data` 和未修改的 `rebuild_original_grid` 完整复现 39 国网格；34 国计算仅过滤原 reach 集合，再调用原 `fit_nnls` 和 `routed`。6 个 φ × 6 个 τ × 104 国，每组 3,744 行。
- 全部配对采用距离模型 RTT = 2(distance_km/200 + 20) × 1.4；τ ∈ {{50,100,150,200,300,500}} ms，φ ∈ {{0,0.2,0.4,0.6,0.8,1}}。国内 NNLS 先拟合原需求并按原年能量归一；伙伴 NNLS 针对可路由的正缺口拟合，按该部分缺口能量归一。U 的分母始终为该情景原始年需求。
- `Reproducibility_Package/inputs/hourly` 为空，所需输入从现存 `NC_Revision_Package.zip` 提取到本目录 `inputs/`，逐文件 SHA-256 与归档 `PACKAGE_MANIFEST.json` 一致。归档完整 SHA-256、成员路径、运行库版本见 `input_provenance.json`。未改动归档或原始输入。
- Python 3.13.5、NumPy 2.2.6、SciPy 1.16.2、pandas 2.3.1；所有脚本禁用 bytecode 写入，数值线性代数每个进程使用一个线程。

{input_table}

## 原 39 国复现检查

**原 Fig.2 网格已逐行复现通过。** 3,744 个国家—τ—φ 主键完全一致，U 最大绝对误差为 {reproduction['max_absolute_errors']['uncovered_share']:.3e}（比例单位），国内 U 最大误差 {reproduction['max_absolute_errors']['uncovered_share_baseline']:.3e}，迁移比例最大误差 {reproduction['max_absolute_errors']['migrated_share']:.3e}，partner 数量和 reach_km 无误差。原函数自带的 flow 与 followsun 检查同样通过。详情见 `reproduction_check.json` 和 `receivers39/original_grid_validation.json`。

**2030 Mix 的 39 国网格也逐行复现通过。** 使用原国家 × 技术 supply_basis、operator_mix、national_shape 和 waveform_cover 函数，省略原模块导入时创建文件夹的操作，函数本体保持不变。与已保存严格供电结果中的 uncovered_share 比较，3,744 行最大误差 {mix_reproduction['max_absolute_U_error']:.3e}。Mix 年能量相对原需求的最大误差为 {mix_summary['max_relative_annual_energy_error']:.3e}。

**LP 已完成 208 次新的 34 国求解并验证数值证书。** 原 39 国保存的逐小时 primal、国内 NNLS/LP 缺口和报告数值先逐国核对。receiver 集合不影响国内第一阶段，国内解复用已核验的原解；对固定 NNLS 缺口和固定国内 LP 缺口分别重新求解路由 LP。所有新解均为最优状态；最大相对 primal–dual 差为 {lp_summary['certificate_max']['duality_gap_relative']:.3e}，最大等式误差 {lp_summary['certificate_max']['primal_equality_violation']:.3e}，最大不等式违反量 {lp_summary['certificate_max']['primal_inequality_violation']:.3e}。104 国逐国满足缩减空间选择后 LP 最小残余不降低，且同一国内 NNLS 缺口下 LP 不高于 NNLS 残余。完整解和对偶向量保存在 `lp_certificates_34/`。

## 关键数值对照

{key_table}

差值统一为 34 国减 39 国。比例的差值使用百分点 pp；绝对值小于 1e−9 的表内变化显示为 0。完整精度见 `headline_comparison.csv`。

Fig.3 的覆盖比例采用 104 国算术平均数；Fig.2 热图采用各国 U 的中位数，二者各自独立比较。所有 U 都相对于各情景的原年需求。

NNLS 先最小化平方误差，再进行等年能量缩放；其 U 并非被直接最小化。因此减少 receiver 后个别 NNLS 的 U 可以略升或略降。此数值现象不适用于直接最小化缺口的 LP；LP 在各国均满足缩减可行选择不会降低最优残余。

## Fig.2 全部 36 格中位数

{all_cells}

CSV：`fig2_heatmap_comparison.csv`；三张 6 × 6 数值表为 `fig2_heatmap_39.csv`、`fig2_heatmap_34.csv`、`fig2_heatmap_difference_pp.csv`。

## 受影响最大的 10 个需求国

以下每个国家取全部 36 格内绝对变化最大的一个格子，再按绝对变化排序：

{any_table}

以下单独按主要全球角点（500 ms、φ = 1）排序：

{global_table}

固定国内 NNLS 缺口的 LP 中，最大国家变化为 {lp_summary['fixed_max_increase_pp']:.6f} pp；名单缩减后残余上升的具体国家见 `lp_top10_affected_countries.csv`。

## 其他依赖 receiver 的结果及计算范围

**2030 Mix 与站点层面的对照均已计算完成。** 国家 × 技术 Mix 的全球中位 U 为 13.858881%（39 国）与 13.857069%（34 国）；36 格中位数最大变化为 0.308144 pp。使用相同 Mix 需求算子和 Fig.2 站点基础另外求解两个角点，国内中位 U 在两组均为 42.213238%，全球中位 U 均为 12.556884%。该站点 Mix 对照是本次新增的跨基础检查，不替代 Fig.4 已有的国家 × 技术结果。

**S26 的工作时段—消费者组成检验也已复现并重算。** 原 39 国 520 个国家—组成组合的国内与全球 U 均与保存值完全一致，34 国版本仍在全部 520 个组合保留正缺口。五组结果如下，完整国家表和六个示例国的网格位于 `business_station_39/`、`business_station_34/`。

{business_table}

**Fig.5 的 2030 全球供电与储能角点已完成 104 次严格逐小时供电求解。** 原 39 国逐小时 d_mw、fit_mw 与已保存 pickle 输入完全一致；发电、辅助服务和储能能量成本参数完全一致。新 34 国全部实现零缺供，最大逐小时平衡误差为 {storage_summary['maximum_equality_error_MW']:.3e} MW。在 float32 逐小时输入完全未变的 {validation['storage_unchanged_float32_input_countries']} 国，新旧总成本最大误差仅为 {unchanged_cost_error:.3e} USD/MWh。国内角点不依赖 receiver，复用原值；供电保障溢价定义沿用 (lcoe_elec − lcoe_gen)/lcoe_gen，其中 lcoe_gen 为优化后的发电成本。

计算耗时：原 Fig.2 39 国复现 {grid_summary['baseline_seconds']:.1f} 秒，34 国整网格 {grid_summary['reduced_seconds']:.1f} 秒；国家 × 技术 Mix 两组网格合计 {mix_summary['seconds']:.1f} 秒；208 次路由 LP 合计 {lp_summary['seconds']:.1f} 秒；站点 Mix 和工作时段检验合计 {station_summary['seconds']:.1f} 秒；Fig.5 的 104 个全球角点合计 {storage_summary['seconds']:.1f} 秒。各项均低于一小时。

**本次没有重算完整储能成本热图及全部年份。** 已保存 3,744 格 strict dispatch 的逐项耗时合计为 {read_json('storage2030_plan.json')['full_grid_3744_serial_seconds_from_saved_runs']/3600:.2f} 小时，按本次四个进程估算仍约 {read_json('storage2030_plan.json')['full_grid_3744_serial_seconds_from_saved_runs']/4/3600:.2f} 小时，超过单项一小时限制。2030 的两个主要成本角点已包含；其他年份成本、完整成本热图、站点运行实验和所有更细的归因图没有据此宣称不变。固定安装容量国内混合的 Fig.1 40.1% 不使用 receiver 名单，保持不变。

## 建议加入 SI 的英文段落与小表

{si}

## 主文是否需要提及

建议在首次说明 receiver 准入条件或 Fig.2 主要结果处加一句，将已运营地点敏感性引到 SI。可使用：

> {main_sentence}

主文对 39 国的口径仍需按用户决定明确为“截至 2025 年已运营或已宣布的候选 hyperscale region 地点”。SI 同时报告中间时延的国家差异即可。本任务未修改任何正文、回稿、DOCX、PDF、图件或已有主结果。

## 输出索引

- `summary.md`：本报告。
- `suggested_SI_text.md`、`suggested_main_text_sentence.txt`：可供主会话整合的英文文本。
- `r2_waveform_grid_34.csv`：34 国 Fig.2 完整 3,744 行网格；`receivers39/r2_waveform_grid.csv` 为复现的 39 国网格。
- `headline_comparison.csv`、`fig2_heatmap_comparison.csv`、`fig2_country_grid_comparison.csv`、两份 top10 CSV：关键值与逐国比较。
- `mix2030_grid_39.csv`、`mix2030_grid_34.csv`、`mix2030_heatmap_comparison.csv`：2030 Mix 完整网格。
- `lp_country_comparison.csv`、`lp_numerical_certificates.csv`、`lp_certificates_34/`：LP 结果、验证和完整解。
- `station_mix2030_country_comparison.csv`、`business_station_summary.csv`、`business_station_34/`：站点与工作时段分析。
- `storage2030_global_34.csv`、`storage2030_global_comparison.csv`：Fig.5 的 2030 全球严格供电结果。
- `input_provenance.json`、各 reproduction/summary JSON、`validation.json`、`output_manifest.json`：输入、运行时间、验证与 SHA-256 索引。

全部新增输出均在 `{work}`。原稿件目录及原主结果均未写入。
'''
(work / 'summary.md').write_text(report, encoding='utf-8')
manifest = {'task': 'NC v18 receiver sensitivity only', 'date': '2026-10-28', 'output_root': str(work),
    'validation': validation, 'files': []}
for p in sorted(work.rglob('*')):
    if p.is_file() and p.name not in {'output_manifest.json', 'codex_events.jsonl', 'codex_stderr.log'}:
        manifest['files'].append({'path': str(p.relative_to(work)), 'bytes': p.stat().st_size,
            'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
(work / 'output_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'validation': validation, 'files_manifested': len(manifest['files']), 'summary': str(work / 'summary.md')}, ensure_ascii=False))
