import argparse
import hashlib
import json
from pathlib import Path

import cartopy.crs as ccrs
from cartopy.mpl.ticker import LongitudeFormatter, LatitudeFormatter
from matplotlib.ticker import FixedLocator

import plot_r2_pairing as pairing

parser = argparse.ArgumentParser()
parser.add_argument('--package-root', required=True, type=Path)
parser.add_argument('--output-dir', required=True, type=Path)
args = parser.parse_args()
package = args.package_root.resolve()
output = args.output_dir.resolve()
output.mkdir(parents=True, exist_ok=True)
original_flow = pairing.draw_flow_map
maps = []


def draw_coordinates(axis, flows, centroids, show_legend):
    original_flow(axis, flows, centroids, show_legend)
    grid = axis.gridlines(crs=ccrs.PlateCarree(), draw_labels=True, linewidth=.35, color='#98A2B3', alpha=.45, linestyle=':')
    grid.xlocator = FixedLocator([-120, -60, 0, 60, 120])
    grid.ylocator = FixedLocator([-30, 0, 30, 60])
    grid.xformatter = LongitudeFormatter()
    grid.yformatter = LatitudeFormatter()
    grid.top_labels = False
    grid.right_labels = False
    grid.x_inline = False
    grid.y_inline = False
    grid.rotate_labels = False
    grid.xpadding = 1.5
    grid.ypadding = 1.5
    grid.xlabel_style = {'size': 9, 'color': '#667085'}
    grid.ylabel_style = {'size': 9, 'color': '#667085'}
    maps.append(grid)
    if show_legend:
        axis.get_legend().set_bbox_to_anchor((0, -.14))


pairing.DATA = package / 'inputs/reference/waveform'
pairing.F2.COUNTRY_META = package / 'collective_attention_research_plan/data/global_renewable_sites/country_meta.csv'
pairing.FIG = output
pairing.draw_flow_map = draw_coordinates
sources = [pairing.DATA / name for name in ('r2_waveform_grid.csv', 'r2_wf_compute_flows_tau100.csv', 'r2_wf_compute_flows_tau150.csv', 'r2_wf_compute_flows_tau200.csv', 'r2_wf_compute_flows.csv')]
before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
pairing.main()
assert len(maps) == 4
assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
for extension in ('png', 'pdf'):
    (output / f'fig3_pairing.{extension}').replace(output / f'Fig3.{extension}')
record = {'source_sha256': before, 'displayed_budgets_ms': [r[2] for r in pairing.SCEN], 'labels': [r[0] for r in pairing.SCEN], 'maps': len(maps), 'optimization_run': False}
(output / 'fig3_label_validation.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(record, ensure_ascii=False))
