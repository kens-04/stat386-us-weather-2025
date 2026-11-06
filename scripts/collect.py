"""Collect/cache Open-Meteo geocoding and 2025 daily ERA5 weather."""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw'
OUT = ROOT / 'data/processed'
CITIES = [('Provo', 'Utah'), ('Salt Lake City', 'Utah'), ('Seattle', 'Washington'),
          ('Los Angeles', 'California'), ('Phoenix', 'Arizona'), ('Denver', 'Colorado'),
          ('Chicago', 'Illinois'), ('New York', 'New York'), ('Miami', 'Florida'),
          ('Boston', 'Massachusetts')]
VARIABLES = ['temperature_2m_max', 'temperature_2m_min', 'temperature_2m_mean',
             'precipitation_sum', 'wind_speed_10m_max']
RENAME = dict(zip(VARIABLES, ['temp_max_c', 'temp_min_c', 'temp_mean_c',
                            'precipitation_mm', 'wind_max_kmh']))
SESSION = requests.Session()
SESSION.mount('https://', HTTPAdapter(max_retries=Retry(
    total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=['GET'], respect_retry_after_header=True)))


def fetch(name, url, params, offline=False):
    """Reuse unchanged raw responses; offline mode never contacts the API."""
    path = RAW / (name + '.json')
    if path.exists():
        return json.loads(path.read_text())
    if offline:
        raise FileNotFoundError(f'Missing cache: {path}')
    response = SESSION.get(url, params=params, timeout=90)
    response.raise_for_status()
    data = response.json()
    if data.get('error'):
        raise ValueError(data)
    path.write_bytes(response.content)
    metadata = {'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
                'url': response.url, 'sha256': hashlib.sha256(response.content).hexdigest()}
    (RAW / (name + '.metadata.json')).write_text(json.dumps(metadata, indent=2) + '\n')
    time.sleep(1)
    return data


def main(offline=False):
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    tables, locations = [], []
    for city, state in CITIES:
        slug = city.lower().replace(' ', '_')
        geo = fetch(slug + '_geocoding', 'https://geocoding-api.open-meteo.com/v1/search',
                    {'name': city, 'count': 100, 'language': 'en', 'format': 'json',
                     'countryCode': 'US'}, offline)
        # Do not silently take the first city sharing a name.
        matches = [r for r in geo.get('results', []) if r.get('country_code') == 'US'
                   and r.get('admin1') == state and r.get('name') in {city, city + ' City'}]
        if len(matches) != 1:
            raise ValueError(f'Ambiguous geocoding for {city}: {matches}')
        place = matches[0]
        params = {'latitude': place['latitude'], 'longitude': place['longitude'],
                  'start_date': '2025-01-01', 'end_date': '2025-12-31',
                  'daily': ','.join(VARIABLES), 'timezone': place['timezone'],
                  'models': 'era5', 'temperature_unit': 'celsius',
                  'wind_speed_unit': 'kmh', 'precipitation_unit': 'mm'}
        weather = fetch(slug + '_weather', 'https://archive-api.open-meteo.com/v1/archive',
                        params, offline)
        expected_units = dict(zip(VARIABLES, ['°C', '°C', '°C', 'mm', 'km/h']))
        assert all(weather['daily_units'][k] == v for k, v in expected_units.items())
        frame = pd.DataFrame(weather['daily']).rename(columns={'time': 'date', **RENAME})
        frame.insert(0, 'state', state)
        frame.insert(0, 'city', city)
        frame['latitude'] = place['latitude']
        frame['longitude'] = place['longitude']
        frame['timezone'] = place['timezone']
        tables.append(frame)
        locations.append({'city': city, 'state': state, 'geonames_id': place['id'],
                          'latitude': place['latitude'], 'longitude': place['longitude'],
                          'timezone': place['timezone'], 'grid_latitude': weather['latitude'],
                          'grid_longitude': weather['longitude'], 'grid_elevation_m': weather['elevation']})
        print(f'{city}: {len(frame)} days', flush=True)
    df = pd.concat(tables, ignore_index=True)
    dates = pd.to_datetime(df['date'])
    df['month'] = dates.dt.month
    df['season'] = df.month.map({12:'Winter', 1:'Winter', 2:'Winter', 3:'Spring', 4:'Spring',
                                5:'Spring', 6:'Summer', 7:'Summer', 8:'Summer',
                                9:'Fall', 10:'Fall', 11:'Fall'})
    df['diurnal_range_c'] = (df.temp_max_c - df.temp_min_c).round(2)
    df['wet_day'] = (df.precipitation_mm >= 1).astype(int)
    assert len(df) == 3650 and not df.duplicated(['city', 'date']).any()
    assert not df.isna().any().any(), 'Missing data: investigate rather than impute'
    for _, group in df.groupby('city'):
        assert list(group.date) == list(pd.date_range('2025-01-01', '2025-12-31').strftime('%Y-%m-%d'))
    assert (df.temp_min_c <= df.temp_mean_c).all() and (df.temp_mean_c <= df.temp_max_c).all()
    assert (df[['precipitation_mm', 'wind_max_kmh']] >= 0).all().all()
    df.to_csv(OUT / 'weather_2025.csv', index=False)
    pd.DataFrame(locations).to_csv(OUT / 'cities.csv', index=False)
    report = {'rows': len(df), 'columns': len(df.columns), 'cities': df.city.nunique(),
              'missing_cells': int(df.isna().sum().sum()), 'duplicate_city_dates': 0,
              'days_per_city': df.groupby('city').size().to_dict(), 'validation': 'passed'}
    (OUT / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true', help='Rebuild using saved raw JSON only')
    main(parser.parse_args().offline)
