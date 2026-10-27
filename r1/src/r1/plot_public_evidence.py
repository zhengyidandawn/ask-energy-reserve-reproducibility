"""Render reserve-evidence figures from completed CSV records and prediction caches.

This module reads archived outputs only. It does not fit models, call services,
select policies, or recompute resampling intervals.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm, Normalize, TwoSlopeNorm
from matplotlib.patches import Rectangle
from matplotlib.ticker import FormatStrFormatter
import numpy as np
import pandas as pd


PROJECT = Path(__file__).resolve().parents[2]
FIGURES = PROJECT / 'elsarticle_unmark' / 'figures'
OUTPUT = PROJECT / 'results' / 'figure_revision_20261026'
COUNTRIES = ['DE', 'AT', 'BE', 'NL']
COUNTRY_NAMES = {'DE': 'Germany', 'AT': 'Austria', 'BE': 'Belgium', 'NL': 'Netherlands'}
METHODS = ['Static quantile', 'Quantile predictor', 'Global calibration', 'Local calibration',
           'Selected shrinkage', 'Block-score calibration', 'Scenario quantile', 'Scenario maximum']
METHOD_LABELS = ['Static quantile', 'Quantile predictor', 'Global calibration', 'Local calibration',
                 'Selected local', 'Block maximum', 'Scenario quantile', 'Scenario maximum']
SERVICE_NAMES = {'deepseek': 'DeepSeek', 'qwen': 'Qwen', 'ernie': 'ERNIE', 'hunyuan': 'Hunyuan'}
SERVICE_COLORS = {'deepseek': '#0072B2', 'qwen': '#E69F00', 'ernie': '#009E73', 'hunyuan': '#CC79A7'}
BLUE = '#0072B2'
ORANGE = '#D55E00'
GREEN = '#009E73'
SOURCES: dict[str, dict] = {}
MANIFEST = []

plt.rcParams.update({
    'font.family': 'serif', 'font.serif': ['Times New Roman', 'DejaVu Serif'],
    'font.size': 10, 'axes.titlesize': 11, 'axes.labelsize': 10,
    'xtick.labelsize': 9.2, 'ytick.labelsize': 9.2, 'legend.fontsize': 9,
    'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'none',
    'axes.spines.top': False, 'axes.spines.right': False,
    'axes.linewidth': .65, 'lines.linewidth': 1.2, 'savefig.facecolor': 'white',
})


def native(path: Path) -> Path:
    text = str(path.absolute())
    return Path('\\\\?\\' + text) if os.name == 'nt' and not text.startswith('\\\\?\\') else path


def register(path: Path) -> Path:
    relative = path.relative_to(PROJECT).as_posix()
    if relative not in SOURCES:
        with native(path).open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        SOURCES[relative] = {'sha256': digest, 'bytes': native(path).stat().st_size}
    return native(path)


def read(relative: str) -> pd.DataFrame:
    return pd.read_csv(register(PROJECT / relative))


def export(data: pd.DataFrame, name: str) -> None:
    data.to_csv(OUTPUT / (name + '_data.csv'), index=False, float_format='%.15g')


def save(fig, name: str, label: str, protocol: str, data_files: list[str]) -> None:
    for extension in ('pdf', 'svg', 'png'):
        fig.savefig(FIGURES / f'{name}.{extension}', dpi=300, bbox_inches='tight', pad_inches=.07)
    plt.close(fig)
    MANIFEST.append({'name': name, 'label': label, 'protocol': protocol,
                     'data_files': data_files, 'formats': ['pdf', 'svg', 'png']})


def heatmap(ax, values, row_labels, col_labels, cmap, norm, annotation, title, colorbar_label):
    mesh = ax.pcolormesh(np.arange(values.shape[1]+1), np.arange(values.shape[0]+1), values,
                         cmap=cmap, norm=norm, edgecolors='white', linewidth=.8)
    ax.set_xticks(np.arange(values.shape[1])+.5, col_labels)
    ax.set_yticks(np.arange(values.shape[0])+.5, row_labels)
    ax.invert_yaxis()
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for row in range(values.shape[0]):
        for column in range(values.shape[1]):
            rgba = mesh.cmap(mesh.norm(values[row, column]))
            light = .2126*rgba[0]+.7152*rgba[1]+.0722*rgba[2]
            ax.text(column+.5, row+.5, annotation(row, column), ha='center', va='center',
                    color='white' if light < .42 else '#111111', fontsize=9.5)
    ax.set_title(title, loc='left', pad=8)
    bar = ax.figure.colorbar(mesh, ax=ax, fraction=.035, pad=.025, aspect=25)
    bar.ax.set_ylabel(colorbar_label, fontsize=9.3)
    bar.ax.tick_params(labelsize=9.2)
    return mesh


def plot_frozen_policies(summary):
    data = summary.loc[summary.margin_applied.eq(True)].copy()
    assert len(data) == 32 and data.minimum_window_coverage.min() >= .95
    name = 'R1_F7_Frozen_Policies'
    export(data, name)
    values = {}
    for metric in ['normalized_cost', 'coverage', 'minimum_window_coverage', 'shortfall_CVaR95_MW']:
        values[metric] = data.pivot(index='method', columns='country', values=metric).loc[METHODS, COUNTRIES].to_numpy()
    fig, axes = plt.subplots(3, 1, figsize=(7.0, 8.4), constrained_layout=True)
    heatmap(axes[0], values['normalized_cost'], METHOD_LABELS, COUNTRIES, 'YlGnBu_r',
            Normalize(values['normalized_cost'].min(), values['normalized_cost'].max()),
            lambda i,j: f"{values['normalized_cost'][i,j]:.5f}",
            '(a) Mean cost index', 'Cost index')
    for column in range(4):
        row = int(np.argmin(values['normalized_cost'][:, column]))
        axes[0].add_patch(Rectangle((column+.025, row+.025), .95, .95, fill=False,
                                    edgecolor='#111111', linewidth=1.6))
    heatmap(axes[1], values['coverage'], METHOD_LABELS, COUNTRIES, 'YlGnBu', Normalize(.95, 1.0),
            lambda i,j: f"{values['coverage'][i,j]:.3f} / {values['minimum_window_coverage'][i,j]:.3f}",
            '(b) Mean / minimum window coverage', 'Mean coverage')
    heatmap(axes[2], values['shortfall_CVaR95_MW'], METHOD_LABELS, COUNTRIES, 'YlGnBu_r',
            LogNorm(values['shortfall_CVaR95_MW'].min(), values['shortfall_CVaR95_MW'].max()),
            lambda i,j: f"{values['shortfall_CVaR95_MW'][i,j]:.2f}",
            '(c) Upper-five-percent mean shortfall', 'Tail shortfall (MW; log colour)')
    save(fig, name, 'fig:r1_frozen_policies',
         'Eight later windows beginning in 2020; country-specific frozen common margins; all 256 policy-window coverages >=0.95.',
         [name+'_data.csv'])


def plot_frozen_gains(windows, intervals):
    frozen = windows.loc[windows.margin_applied.eq(True)]
    pivot = frozen.pivot(index=['country','window','test_start'], columns='method', values='normalized_cost')
    gains = (pivot['Global calibration'] - pivot['Selected shrinkage']).rename('global_minus_selected_cost').reset_index()
    matrix = gains.pivot(index='country', columns='window', values='global_minus_selected_cost').loc[COUNTRIES].to_numpy()*1e4
    selected = intervals.loc[(intervals.comparator == 'Global calibration') &
                             (intervals.metric == 'normalized_cost') & (intervals.block_months == 3)].set_index('country').loc[COUNTRIES].reset_index()
    for _, row in selected.iterrows():
        assert np.isclose(gains.loc[gains.country.eq(row.country), 'global_minus_selected_cost'].mean(), row.mean_gain, atol=1e-14)
    name = 'R1_F8_Frozen_Cost_Gains'
    export(gains, name+'_windows')
    export(selected, name+'_intervals')
    fig, axes = plt.subplots(2, 1, figsize=(7.0, 5.4), gridspec_kw={'height_ratios':[1,1.05]}, constrained_layout=True)
    limit = np.max(np.abs(matrix))
    heatmap(axes[0], matrix, COUNTRIES, [str(i+1) for i in range(8)], 'RdBu', TwoSlopeNorm(vmin=-limit,vcenter=0,vmax=limit),
            lambda i,j: f'{matrix[i,j]:+.2f}', '(a) Cost gain in each later window', r'Cost gain ($10^{-4}$)')
    axes[0].set_xlabel('Later 30-day test window')
    ax = axes[1]
    y = np.arange(4)
    mean = selected.mean_gain.to_numpy()*1e4
    low = selected.four_country_ci_low.to_numpy()*1e4
    high = selected.four_country_ci_high.to_numpy()*1e4
    ax.axvline(0, color='#555555', linestyle='--', linewidth=.8)
    ax.errorbar(mean, y, xerr=[mean-low, high-mean], fmt='o', color=BLUE, capsize=4, markersize=5)
    for index in range(4):
        ax.text(high[index]+.12, index, f'{mean[index]:+.2f} [{low[index]:+.2f}, {high[index]:+.2f}]', va='center', fontsize=9.3)
    ax.set_yticks(y, COUNTRIES)
    ax.invert_yaxis()
    ax.set_xlim(min(-2.8,low.min()-.3), max(7.8, high.max()+3.5))
    ax.set_title('(b) Mean gain and family-adjusted interval', loc='left')
    ax.set_xlabel(r'Global cost minus selected-local cost ($10^{-4}$)')
    ax.grid(axis='x', alpha=.18)
    save(fig, name, 'fig:r1_frozen_gains',
         'Saved paired intervals: 3,000 circular three-window block draws and four-country Bonferroni adjustment; no resampling performed by plotting script.',
         [name+'_windows_data.csv',name+'_intervals_data.csv'])


def plot_conditioned_reliability(conditional, bandwidth):
    selected = conditional.loc[(conditional.method == 'Selected shrinkage') &
                               conditional.regime.isin(['season_winter','season_spring','season_summer','season_autumn','high_observed_ramp'])]
    rows = []
    for (country,regime), group in selected.groupby(['country','regime']):
        rows.append({'country':country,'regime':regime,'decisions':int(group.n.sum()),
                     'coverage':np.average(group.coverage,weights=group.n),
                     'normalized_cost':np.average(group.normalized_cost,weights=group.n)})
    data = pd.DataFrame(rows)
    regimes = ['season_winter','season_spring','season_summer','season_autumn','high_observed_ramp']
    matrix = data.pivot(index='country', columns='regime', values='coverage').loc[COUNTRIES,regimes].to_numpy()
    assert np.isclose(matrix[1,1], .918, atol=.0005) and np.isclose(matrix[1,4], .915, atol=.0005)
    name = 'R1_F9_Conditional_Reliability'
    export(data,name+'_regimes')
    export(bandwidth,name+'_bandwidth')
    fig = plt.figure(figsize=(7.0,5.6),constrained_layout=True)
    gs = fig.add_gridspec(2,2,height_ratios=[1.05,1])
    ax = fig.add_subplot(gs[0,:])
    heatmap(ax,matrix,COUNTRIES,['Winter','Spring','Summer','Autumn','High ramp'],'RdBu',
            TwoSlopeNorm(vmin=.91,vcenter=.95,vmax=.98),lambda i,j:f'{matrix[i,j]:.3f}',
            '(a) Selected-local conditional coverage: 2019 benchmark','Coverage')
    for column in (1,4):
        ax.add_patch(Rectangle((column+.025,1.025),.95,.95,fill=False,edgecolor='#111111',linewidth=1.4))
    ax = fig.add_subplot(gs[1,0])
    x = bandwidth.bandwidth_factor
    ax.plot(x,bandwidth.mean_normalized_cost,'o-',color=BLUE,markersize=5)
    ax.yaxis.set_major_formatter(FormatStrFormatter('%.5f'))
    ax.set_ylim(.01650,.01660)
    ax.set_xticks(x)
    ax.set_xlabel('Gaussian bandwidth multiplier')
    ax.set_ylabel('Mean cost index')
    ax.set_title('(b) German bandwidth sensitivity',loc='left')
    ax.grid(alpha=.18)
    ax = fig.add_subplot(gs[1,1])
    ax.plot(x,bandwidth.mean_effective_sample,'o-',color=GREEN,markersize=5)
    for a,b in zip(x,bandwidth.mean_effective_sample):
        ax.annotate(f'{b:.1f}',(a,b),xytext=(0,7),textcoords='offset points',ha='center',fontsize=9.5)
    ax.set_ylim(0,285)
    ax.set_xticks(x)
    ax.set_xlabel('Gaussian bandwidth multiplier')
    ax.set_ylabel('Mean effective sample size')
    ax.set_title('(c) Effective residual neighborhood',loc='left')
    ax.grid(alpha=.18)
    save(fig,name,'fig:r1_conditional_bandwidth',
         '2019 selected-local conditional coverage weighted by held-out regime counts; bandwidth means from the saved four-origin German diagnostic.',
         [name+'_regimes_data.csv',name+'_bandwidth_data.csv'])


def plot_trajectory(windows):
    name = 'R1_F10_Public_Reserve_Trajectory'
    cache = PROJECT / 'data/evidence_completion_20261011/prediction_cache/reliability/main/load_calendar/DE_w3_H60_cal30_K256_req0.95_ffull_cs20.npz'
    with np.load(register(cache)) as archive:
        target = archive['target']
        stamps = pd.to_datetime(archive['timestamps'],utc=True)
        scale = float(archive['load_scale'])
        all_data = {'timestamp_UTC':stamps.astype(str),'target_MW':target}
        records = windows.loc[(windows.country == 'DE') & (windows.window == 3) & windows.margin_applied.eq(True)]
        for method,key in [('Global calibration','Global_calibration'),('Selected shrinkage','Selected_shrinkage'),('Quantile predictor','Quantile_predictor')]:
            row = records.loc[records.method.eq(method)].iloc[0]
            reserve = archive[key]+row.common_margin_MW
            assert np.isclose(reserve.mean(),row.mean_reserve_MW,atol=1e-8)
            assert np.isclose(np.mean(target<=reserve),row.coverage,atol=1e-12)
            cost = np.mean(reserve+20*np.maximum(target-reserve,0))/scale
            assert np.isclose(cost,row.normalized_cost,atol=1e-12)
            all_data[key+'_MW'] = reserve
    data = pd.DataFrame(all_data).iloc[:7*96].copy()
    export(data,name)
    fig,axes = plt.subplots(2,1,figsize=(7.0,4.7),sharex=True,gridspec_kw={'height_ratios':[2.1,1]},constrained_layout=True)
    time = pd.to_datetime(data.timestamp_UTC)
    axes[0].plot(time,data.target_MW,color='#222222',linewidth=.9,label='Realized ramp target')
    axes[0].plot(time,data.Selected_shrinkage_MW,color=BLUE,linewidth=1.1,label='Selected local')
    axes[0].plot(time,data.Quantile_predictor_MW,color=GREEN,linewidth=.9,alpha=.85,label='Quantile predictor')
    axes[0].set_title('(a) Target and frozen-margin reserve',loc='left')
    axes[0].set_ylabel('Ramp / reserve (MW)')
    axes[0].set_ylim(bottom=0)
    axes[0].legend(loc='upper left',ncol=3,frameon=False,fontsize=9)
    difference = data.Selected_shrinkage_MW-data.Global_calibration_MW
    axes[1].plot(time,difference,color=BLUE,linewidth=1)
    axes[1].axhline(0,color='#666666',linestyle='--',linewidth=.7)
    axes[1].fill_between(time,0,difference,color=BLUE,alpha=.12)
    axes[1].set_title('(b) Selected-local minus global reserve',loc='left')
    axes[1].set_ylabel('Reserve difference (MW)')
    axes[1].xaxis.set_major_locator(mdates.DayLocator(interval=1))
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    axes[1].set_xlim(time.iloc[0],time.iloc[-1])
    axes[1].set_xlabel('Germany, 31 March–6 April 2020 (UTC)')
    for ax in axes:
        ax.grid(alpha=.15)
    save(fig,name,'fig:r1_public_trajectory',
         'First seven days of the fourth later German window (fixed chronological choice). Cached reserves plus the saved common margin; full-window means, coverage and costs checked against formal CSV.',
         [name+'_data.csv'])


def plot_field_consequences(consequences,resource):
    name = 'R1_F11_Field_Consequences'
    reference = consequences.loc[consequences.condition.eq('Reference')].iloc[0]
    data = consequences.loc[~consequences.condition.eq('Reference')].copy()
    data['reserve_difference_MW'] = data.reserve_MW-reference.reserve_MW
    export(consequences.assign(reserve_difference_MW=consequences.reserve_MW-reference.reserve_MW),name+'_fields')
    export(resource,name+'_completion')
    labels = ['Region: AT','Horizon: 120 min','Horizon: 180 min','Load + calendar',
              'Shortfall weight: 10','Shortfall weight: 40','Coverage: 0.975','Tail reporting']
    colors = [ORANGE,BLUE,BLUE,GREEN,GREEN,GREEN,GREEN,GREEN]
    fig,axes = plt.subplots(2,2,figsize=(7.25,6.4),constrained_layout=True)
    y = np.arange(len(data))
    ax=axes[0,0]
    ax.barh(y,data.reserve_difference_MW,color=colors,height=.62)
    ax.set_yticks(y,labels)
    ax.invert_yaxis()
    ax.axvline(0,color='#555555',linewidth=.6)
    ax.set_xlabel('Mean reserve difference (MW)')
    ax.set_title('(a) Reserve consequence',loc='left')
    ax.grid(axis='x',alpha=.15)
    ax=axes[0,1]
    ax.barh(y,data.paired_cost_difference,color=colors,height=.62)
    ax.set_xscale('symlog',linthresh=.0003,linscale=.5)
    ax.set_xlim(-.0004,.25)
    ax.set_xticks([0,.001,.01,.1], ['0',r'$10^{-3}$',r'$10^{-2}$',r'$10^{-1}$'])
    ax.set_yticks(y,[])
    ax.invert_yaxis()
    ax.axvline(0,color='#555555',linewidth=.6)
    ax.set_xlabel('Cost-index difference (symlog scale)')
    ax.set_title('(b) Cost consequence',loc='left')
    ax.grid(axis='x',alpha=.15)
    ax=axes[1,0]
    ax.scatter(data.coverage,y,c=colors,s=30,zorder=3)
    ax.axvline(reference.coverage,color='#777777',linestyle='--',linewidth=.8,label='Reference: 0.968')
    for index,value in enumerate(data.coverage):
        ax.annotate(f'{value:.3f}',(value,index),xytext=(5 if value < .8 else -5,0),
                    textcoords='offset points',ha='left' if value < .8 else 'right',va='center',fontsize=9.4)
    ax.set_yticks(y,labels)
    ax.invert_yaxis()
    ax.set_xlim(.35,1.02)
    ax.set_xlabel('Coverage against the German reference target')
    ax.set_title('(c) Reference-target agreement',loc='left')
    ax.legend(loc='lower left',frameon=False,fontsize=9.4)
    ax.grid(axis='x',alpha=.15)
    ax=axes[1,1]
    services=['deepseek','qwen','ernie','hunyuan']
    for index,service in enumerate(services):
        group=resource.loc[resource.service.eq(service)]
        completed=int(group.loc[group.numerical_stage.eq('executed'),'trials'].iloc[0])
        returned=int(group.loc[group.numerical_stage.eq('preparation'),'trials'].iloc[0])
        ax.barh(index,completed,color=SERVICE_COLORS[service],height=.55)
        ax.barh(index,returned,left=completed,color='#DDDDDD',height=.55)
        ax.text(completed/2,index,str(completed),ha='center',va='center',fontsize=10,color='white' if service!='qwen' else '#111111')
        ax.text(completed+returned/2,index,str(returned),ha='center',va='center',fontsize=10)
    ax.set_yticks(range(4),[SERVICE_NAMES[x] for x in services])
    ax.invert_yaxis()
    ax.set_xlim(0,110)
    ax.set_xticks([0,25,50,75,110])
    ax.set_xlabel('Trials: completed (colour), returned (grey)')
    ax.set_title('(d) Independent-request offline replay',loc='left')
    ax.grid(axis='x',alpha=.15)
    save(fig,name,'fig:r1_field_consequences',
         'Panels a-c: controlled specifications evaluated on 2,880 common German reference timestamps and objective. Panel d: separate 22-request, five-trial-per-service replay; completed outputs reproduce each reference.',
         [name+'_fields_data.csv',name+'_completion_data.csv'])


def main():
    FIGURES.mkdir(parents=True,exist_ok=True)
    OUTPUT.mkdir(parents=True,exist_ok=True)
    summary=read('results/evidence_completion_20261011/reliability/main/summary.csv')
    windows=read('results/evidence_completion_20261011/reliability/main/window_results.csv')
    intervals=read('results/positive_revision_20261011/frozen_paired_intervals.csv')
    conditional=read('results/public_validation_r1/main/conditional_results.csv')
    bandwidth=read('results/strengthening_20261011/bandwidth_sensitivity_summary.csv')
    consequences=read('results/substantive_resolution_20261011/six_field_consequences.csv')
    resource=read('results/positive_revision_20261011/execution_resource_accounting.csv')
    plot_frozen_policies(summary)
    plot_frozen_gains(windows,intervals)
    plot_conditioned_reliability(conditional,bandwidth)
    plot_trajectory(windows)
    plot_field_consequences(consequences,resource)
    manifest={'figures':MANIFEST,'sources':SOURCES,'model_fits':0,'service_calls':0,'resampling_runs':0}
    (OUTPUT/'public_figure_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'figures':[row['name'] for row in MANIFEST], 'sources':len(SOURCES),
                      'model_fits':0,'service_calls':0,'resampling_runs':0}))


if __name__=='__main__':
    main()
