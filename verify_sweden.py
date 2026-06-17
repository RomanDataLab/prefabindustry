#!/usr/bin/env python3
"""Verify Sweden regions"""

import json
from pathlib import Path

script_dir = Path(__file__).parent
maps_dir = script_dir / 'maps'
geojson_path = maps_dir / 'worldregion.geojson'

with open(geojson_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

se_features = [f for f in data['features'] if f['properties']['country_code'] == 'SE']
print(f'Sweden counties: {len(se_features)}\n')

for f in se_features:
    props = f['properties']
    print(f"  {props['region_name_en']} ({props['region_name_local']})")
