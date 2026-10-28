import argparse
import hashlib
import json
from pathlib import Path
import sys

work = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--package-root', type=Path, required=True)
parser.add_argument('--output-dir', type=Path, default=work / 'Figures_20261028_v2')
args = parser.parse_args()
package = args.package_root.resolve()
output = args.output_dir.resolve()
output.mkdir(parents=True, exist_ok=True)
dependencies = work.parents[0] / 'meng-review/clarity-edit-20261023/python-deps'
if dependencies.exists():
    sys.path.insert(0, str(dependencies))
sys.path.insert(0, str(work / 'plotting'))
sys.path.insert(0, str(work / 'python-deps'))

import cartopy.crs as ccrs
from cartopy.mpl.geoaxes import GeoAxes
from cartopy.mpl.ticker import LongitudeFormatter, LatitudeFormatter
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator
import numpy as np
import plot_r2_pairing as pairing
import plot_strict_revision as strict

digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
meta = package / 'collective_attention_research_plan/data/global_renewable_sites/country_meta.csv'
records = {'numerical_results_recomputed': False, 'figure3_input_sha256': {}, 'figure5_input_sha256': {}, 'coordinate_labels': {}}
for name in ['r2_waveform_grid.csv', 'r2_wf_compute_flows_tau100.csv', 'r2_wf_compute_flows_tau150.csv', 'r2_wf_compute_flows_tau200.csv', 'r2_wf_compute_flows.csv']:
    records['figure3_input_sha256'][name] = digest(package / 'inputs/reference/waveform' / name)
for name in ['r3_dispatch_grid_2030.csv', 'r3_dispatch_yearly_phi1.csv']:
    records['figure5_input_sha256'][name] = digest(package / 'results/storage' / name)


def coordinates(axis, size):
    grid = axis.gridlines(crs=ccrs.PlateCarree(), draw_labels=True, linewidth=.35, color='#98A2B3', alpha=.45, linestyle=':')
    grid.xlocator = FixedLocator([-120, -60, 0, 60, 120])
    grid.ylocator = FixedLocator([-30, 0, 30, 60])
    grid.xformatter = LongitudeFormatter()
    grid.yformatter = LatitudeFormatter()
    grid.top_labels = False
    grid.right_labels = False
    grid.bottom_labels = True
    grid.left_labels = True
    grid.x_inline = False
    grid.y_inline = False
    grid.rotate_labels = False
    grid.xpadding = 1.5
    grid.ypadding = 1.5
    grid.xlabel_style = {'size': size, 'color': '#667085'}
    grid.ylabel_style = {'size': size, 'color': '#667085'}
    return grid


original_flow = pairing.draw_flow_map
figure3_grids = []


def flow_with_coordinates(axis, flows, centroids, show_legend):
    original_flow(axis, flows, centroids, show_legend)
    figure3_grids.append(coordinates(axis, 9))
    if show_legend:
        axis.get_legend().set_bbox_to_anchor((0, -.14))


pairing.DATA = package / 'inputs/reference/waveform'
pairing.F2.COUNTRY_META = meta
pairing.FIG = output
pairing.draw_flow_map = flow_with_coordinates
pairing.main()
for extension in ('png', 'pdf'):
    generated = output / f'fig3_pairing.{extension}'
    generated.replace(output / f'Fig3.{extension}')
records['coordinate_labels']['Fig3'] = {'maps': len(figure3_grids), 'longitude_degrees': [-120, -60, 0, 60, 120], 'latitude_degrees': [-30, 0, 30, 60]}
assert len(figure3_grids) == 4

figure5_grids = []


def save_figure5(figure, directory):
    for axis in figure.axes:
        if isinstance(axis, GeoAxes):
            figure5_grids.append(coordinates(axis, 8.2))
    assert len(figure5_grids) == 3
    replacements = {
        'Domestic phase-firming premium\n(% of generation, 2030, φ=100%)': 'Domestic firming premium\n(% of generation cost, 2030, φ=100%)',
        'Phase-firming\npremium (% of gen)': 'Domestic firming\npremium\n(% of generation\ncost)',
        'Per-country premium (% of gen)': 'Per-country domestic firming premium\n(% of generation cost)',
        'Phase-firming premium (% of gen)': 'Domestic firming premium (% of generation cost)',
        'Median premium\n(% of gen)': 'Median domestic\nfirming premium\n(% of generation cost)',
        'largest median\npremium decrease': 'largest median\ndomestic premium decrease',
        'Per-country phase-firming premium Π (% of generation · global reach)': 'Domestic firming premium Π (% of generation cost, global reach)',
    }
    for text in figure.findobj(match=matplotlib.text.Text):
        value = text.get_text()
        if value in replacements:
            text.set_text(replacements[value])
        elif 'phase-firming' in value:
            text.set_text(value.replace('phase-firming', 'domestic firming'))
        if text.get_text().startswith('Domestic firming\npremium\n'):
            text.set_fontsize(8.8)
        if text.get_text().startswith('Median domestic\n'):
            text.set_fontsize(8.6)
        if text.get_text().startswith('largest median\n'):
            text.set_fontsize(8.2)
    for extension in ('png', 'pdf'):
        figure.savefig(directory / f'Fig5.{extension}', dpi=300, bbox_inches='tight', pad_inches=.06)
    figure.canvas.draw()
    records['coordinate_labels']['Fig5'] = {'maps': len(figure5_grids), 'longitude_degrees': [-120, -60, 0, 60, 120], 'latitude_degrees': [-30, 0, 30, 60]}
    plt.close(figure)


strict.save_fig5 = save_figure5
sys.argv = [str(Path(strict.__file__)), '--storage-results', str(package / 'results/storage'), '--audit-results', str(package / 'results/storage'), '--country-meta', str(meta), '--output-dir', str(output), '--figure', 'fig5', '--validation-output', str(work / 'fig5_redraw_validation.json')]
strict.main()
records['outputs'] = {path.name: {'sha256': digest(path), 'bytes': path.stat().st_size} for path in sorted(output.iterdir()) if path.suffix in ('.png', '.pdf')}
(work / 'map_redraw_validation.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'map_count': 7, 'output': str(output), 'optimization_executed': False}, ensure_ascii=True))
