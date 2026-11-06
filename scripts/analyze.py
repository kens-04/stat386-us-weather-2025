"""Recreate all EDA summaries and figures from the curated city-day dataset."""
import os
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR', '/tmp/stat386-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/processed'
FIG = ROOT / 'figures'
FIG.mkdir(exist_ok=True)
df = pd.read_csv(DATA / 'weather_2025.csv')
summary = df.groupby('city').agg(days=('date', 'size'),
    mean_temp_c=('temp_mean_c', 'mean'), mean_max_c=('temp_max_c', 'mean'),
    mean_min_c=('temp_min_c', 'mean'), precipitation_mm=('precipitation_mm', 'sum'),
    wet_days=('wet_day', 'sum'), mean_daily_max_wind_kmh=('wind_max_kmh', 'mean'),
    mean_diurnal_range_c=('diurnal_range_c', 'mean'))
monthly = df.groupby(['city', 'month']).agg(mean_temp_c=('temp_mean_c', 'mean'),
    precipitation_mm=('precipitation_mm', 'sum')).reset_index()
seasonal = df.groupby(['city', 'season']).agg(mean_temp_c=('temp_mean_c', 'mean'),
    precipitation_mm=('precipitation_mm', 'sum'), days=('date', 'size')).reset_index()
pivot = seasonal.pivot(index='city', columns='season', values='mean_temp_c')
summary['summer_minus_winter_c'] = pivot.Summer - pivot.Winter
summary['mm_per_wet_day'] = df[df.wet_day.eq(1)].groupby('city').precipitation_mm.mean()
summary.round(3).to_csv(DATA / 'city_summary.csv')
monthly.round(3).to_csv(DATA / 'monthly_summary.csv', index=False)
seasonal.round(3).to_csv(DATA / 'seasonal_summary.csv', index=False)
df.select_dtypes('number').describe().round(3).to_csv(DATA / 'numeric_summary.csv')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,
                     'axes.spines.top':False,'axes.spines.right':False,
                     'figure.facecolor':'#fafafa','axes.facecolor':'#fafafa'})
credit = 'Weather data: Open-Meteo.com / Copernicus ERA5 • CC BY 4.0 • 2025 local calendar days'
def save(fig, name):
    fig.text(.02, .015, credit, fontsize=8, color='#555555')
    fig.savefig(FIG / (name + '.png'), dpi=170, bbox_inches='tight')
    plt.close(fig)

fig, axes = plt.subplots(2, 5, figsize=(15, 6.4), sharex=True, sharey=True)
for ax, city in zip(axes.flat, sorted(df.city.unique())):
    d = monthly[monthly.city.eq(city)]
    ax.plot(d.month, d.mean_temp_c, color='#176b87', marker='o', markersize=3)
    ax.set_title(city, fontsize=12)
    ax.set_xticks([1,4,7,10], ['Jan','Apr','Jul','Oct'])
    ax.set_ylim(-8,40)
    ax.grid(axis='y', alpha=.2)
fig.suptitle('One year, ten different temperature patterns', fontsize=18, y=1.01)
fig.supylabel('Monthly mean temperature (°C)')
fig.tight_layout(rect=[0,.06,1,.97])
save(fig, 'monthly_temperature')

fig, axes = plt.subplots(1,2,figsize=(12,6), sharey=True)
s = summary.sort_values('precipitation_mm')
axes[0].barh(s.index, s.precipitation_mm, color='#176b87')
axes[1].barh(s.index, s.wet_days, color='#c07839')
for ax, values in zip(axes,[s.precipitation_mm,s.wet_days]):
    ax.bar_label(ax.containers[0], labels=[f'{v:,.0f}' for v in values], padding=4, fontsize=9)
    ax.set_xlim(0, max(values)*1.19)
    ax.grid(axis='x', alpha=.15)
axes[0].set_xlabel('Annual precipitation (mm; rain + snow water equivalent)')
axes[1].set_xlabel('Wet days (daily precipitation ≥ 1 mm)')
fig.suptitle('Total precipitation and wet-day frequency tell different stories',fontsize=15)
fig.tight_layout(rect=[0,.06,1,.95])
save(fig, 'precipitation')

fig, ax = plt.subplots(figsize=(9,5.7))
s = summary.sort_values('mean_daily_max_wind_kmh')
ax.barh(s.index, s.mean_daily_max_wind_kmh, color='#49745a')
ax.bar_label(ax.containers[0], fmt='%.1f', padding=4)
ax.set_xlim(0, s.mean_daily_max_wind_kmh.max()*1.2)
ax.set_xlabel('Mean of daily maximum 10 m wind speed (km/h)')
ax.set_title('Wind comparison: daily maxima, not all-day average wind',pad=15)
ax.grid(axis='x',alpha=.15)
fig.tight_layout(rect=[0,.06,1,1])
save(fig, 'wind')
print(summary.round(2).to_string())
print('\nDaily mean temperature range:',df.temp_mean_c.min(),df.temp_mean_c.max())
