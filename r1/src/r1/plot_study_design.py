from pathlib import Path
import hashlib
import json
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parents[2]
FIGURES = PROJECT / 'elsarticle_unmark' / 'figures'
EVIDENCE = PROJECT / 'results' / 'figure_revision_20261026'
EVIDENCE.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({'font.family': 'serif', 'font.serif': ['Times New Roman', 'DejaVu Serif'],
                     'font.size': 10, 'axes.labelsize': 10, 'axes.titlesize': 11,
                     'xtick.labelsize': 9, 'ytick.labelsize': 9, 'pdf.fonttype': 42,
                     'ps.fonttype': 42, 'svg.fonttype': 'none', 'axes.linewidth': 0.65})


def native(path):
    text = str(path.absolute())
    return '\\\\?\\' + text if os.name == 'nt' and not text.startswith('\\\\?\\') else str(path)


def digest(path):
    with open(native(path), 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(figure, name):
    for extension in ('pdf', 'svg', 'png'):
        figure.savefig(FIGURES / f'{name}.{extension}', dpi=320, bbox_inches='tight', facecolor='white')
    plt.close(figure)


def public_states():
    source = PROJECT / 'data' / 'public_validation_r1' / 'time_series_15min_singleindex.csv'
    countries = [('DE', 'Germany'), ('AT', 'Austria'), ('BE', 'Belgium'), ('NL', 'Netherlands')]
    columns = ['utc_timestamp'] + [f'{code}_load_actual_entsoe_transparency' for code, _ in countries]
    raw = pd.read_csv(source, usecols=columns)
    raw['timestamp'] = pd.to_datetime(raw['utc_timestamp'], utc=True)
    raw = raw.sort_values('timestamp').drop_duplicates('timestamp', keep='last').set_index('timestamp')
    grid = pd.date_range(raw.index.min(), raw.index.max(), freq='15min', tz='UTC')
    raw = raw.reindex(grid)
    sources = [{'path': source.relative_to(PROJECT).as_posix(), 'sha256': digest(source)}]
    frames = []
    fig, axes = plt.subplots(2, 2, figsize=(7.6, 6.0), layout='constrained')
    for index, ((code, name), axis) in enumerate(zip(countries, axes.flat)):
        load = pd.to_numeric(raw[f'{code}_load_actual_entsoe_transparency'], errors='coerce')
        load = load.where(load > 0)
        recent = load.diff().clip(lower=0).rolling(12, min_periods=12).max()
        cached = []
        for window in range(12):
            path = PROJECT / 'data' / 'public_validation_r1' / 'prediction_cache' / f'{code}_w{window}_H60_cal30_K256_req0.95_ffull_cs20.npz'
            with np.load(native(path)) as values:
                cached.append(pd.DataFrame({'timestamp': pd.to_datetime(values['timestamps'], utc=True),
                                            'target_MW': values['target'], 'window': window}))
            sources.append({'path': path.relative_to(PROJECT).as_posix(), 'sha256': digest(path)})
        data = pd.concat(cached, ignore_index=True)
        data['load_MW'] = load.reindex(pd.DatetimeIndex(data['timestamp'])).to_numpy()
        data['recent_ramp_MW'] = recent.reindex(pd.DatetimeIndex(data['timestamp'])).to_numpy()
        data['country'] = code
        assert len(data) == 34560
        assert data[['target_MW', 'load_MW', 'recent_ramp_MW']].notna().all().all()
        ramp_limit = float(data['recent_ramp_MW'].quantile(0.995))
        data['within_display_ramp_range'] = data['recent_ramp_MW'] <= ramp_limit
        image = axis.hexbin(data['load_MW'] / 1000, data['recent_ramp_MW'], C=data['target_MW'],
                            gridsize=23, mincnt=15, reduce_C_function=np.mean, cmap='viridis', linewidths=0,
                            extent=(data['load_MW'].min() / 1000, data['load_MW'].max() / 1000, 0, ramp_limit))
        axis.set_ylim(0, ramp_limit)
        axis.set_title(f'({chr(97 + index)}) {name} ({code})', loc='left')
        axis.set_xlabel('Current load ($10^3$ MW)')
        axis.set_ylabel('Recent maximum ramp (MW)')
        axis.ticklabel_format(axis='y', style='sci', scilimits=(0, 3), useMathText=True)
        axis.spines[['top', 'right']].set_visible(False)
        colorbar = fig.colorbar(image, ax=axis, fraction=0.046, pad=0.03)
        colorbar.set_label('Mean next-hour target (MW)', fontsize=9)
        colorbar.ax.tick_params(labelsize=8)
        axis.text(0.02, 0.98, '34,560 total decisions', transform=axis.transAxes, va='top', fontsize=8,
                  bbox={'facecolor': 'white', 'alpha': 0.85, 'edgecolor': 'none', 'pad': 1.5})
        frames.append(data)
    combined = pd.concat(frames, ignore_index=True)
    assert len(combined) == 138240
    data_path = EVIDENCE / 'public_state_observations.csv'
    combined.to_csv(data_path, index=False)
    save(fig, 'P3_state_density_risk')
    return {'figure': 'P3_state_density_risk.pdf', 'sources': sources,
            'plot_data': data_path.relative_to(PROJECT).as_posix(), 'plot_data_sha256': digest(data_path),
            'protocol': '2019 public benchmark; 12 archived test windows per country; no fitting',
            'observations': 138240, 'hexagon_minimum_count': 15,
            'display_extent': 'recent observed ramps through the country-specific 99.5th percentile',
            'x': 'current load / 1000 MW', 'y': 'maximum observed positive one-step ramp over 12 observations',
            'color': 'mean archived next-hour maximum positive one-step ramp in MW'}


def method_flow():
    figure, axis = plt.subplots(figsize=(8.0, 4.4))
    axis.set(xlim=(-0.25, 16.05), ylim=(0, 8.6))
    axis.axis('off')

    def box(x, y, width, height, text, face='#F3F5F7', edge='#627283', size=10):
        axis.add_patch(FancyBboxPatch((x, y), width, height, boxstyle='round,pad=0.08,rounding_size=0.1',
                                     facecolor=face, edgecolor=edge, linewidth=0.8))
        axis.text(x + width / 2, y + height / 2, text, ha='center', va='center', fontsize=size)

    def arrow(start, end):
        axis.add_patch(FancyArrowPatch(start, end, arrowstyle='-|>', mutation_scale=11,
                                      linewidth=0.85, color='#46596B', connectionstyle='arc3'))

    axis.text(0, 8.2, 'Checked study specification', fontsize=11, fontweight='bold')
    fields = ['Region', 'Horizon', 'Input variables', 'Cost weights', 'Reliability', 'Reporting']
    for i, value in enumerate(fields):
        box(i * 2.67, 6.9, 2.4, 0.8, value, '#EAF1F7')
    arrow((8, 6.75), (8, 6.15))
    box(0, 4.8, 15.75, 1.15,
        'Public numerical protocol\n700 fitting days  |  20 calibration-fit days  |  10 selection days  |  30 test days',
        '#F7F4E8', size=10)
    arrow((8, 4.65), (8, 4.0))
    items = ['Target and\nadmissible features', 'Quantile\nprediction', 'Residual calibration\nand policy selection',
             'Reserve\nseries', 'Cost, coverage\nand tail shortfall']
    for i, value in enumerate(items):
        box(i * 3.22, 2.5, 2.85, 1.2, value, '#EDF4EE' if i == 4 else '#F3F5F7', size=10)
        if i < 4:
            arrow((i * 3.22 + 2.93, 3.1), ((i + 1) * 3.22 - 0.1, 3.1))
    arrow((8, 2.35), (8, 1.75))
    box(0, 0.35, 15.75, 1.1,
        'Traceable calculation record\nSource identifier  |  Confirmed fields  |  Target and reserve hashes  |  Requested numerical report',
        '#EDF4EE', size=10)
    figure.tight_layout(pad=0.5)
    save(figure, 'F2_method_flow_cropped')
    return {'figure': 'F2_method_flow_cropped.pdf', 'kind': 'method schematic',
            'source': 'sections/02_Problem_Formulation.tex and public numerical protocol; no numerical fitting'}


if __name__ == '__main__':
    manifest = [public_states(), method_flow()]
    (EVIDENCE / 'study_design_figure_sources.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps([{'figure': row['figure'], 'observations': row.get('observations')} for row in manifest]))
