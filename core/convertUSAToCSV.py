#!/usr/bin/env python3
# Convert USA progress backup JSON to CSV
import json
import csv
from pathlib import Path

# Output directory
output_dir = Path(__file__).parent.parent / 'research_output'
json_path = output_dir / 'usa_progress_backup.json'
csv_path = output_dir / 'usa_prefab_core.csv'

# Load JSON data
print(f"Loading data from {json_path}...")
with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Found {len(data)} companies")

# Field names
fieldnames = [
    'id', 'brand', 'head_office_legal_name', 'address', 'webpage',
    'configurator', 'models_amount', 'min_sqm', 'max_sqm',
    'main_structure_material', 'min_home_price', 'average_price_sqm'
]

# Convert data for CSV
csv_data = []
for company in data:
    csv_company = {}
    for field in fieldnames:
        value = company.get(field)
        
        # Handle None values
        if value is None:
            csv_company[field] = ''
        # Handle string 'NaN' or 'null' from JSON
        elif isinstance(value, str) and value.lower() in ['nan', 'null']:
            csv_company[field] = ''
        # Handle numeric NaN
        elif isinstance(value, float) and (value != value):  # NaN check
            csv_company[field] = ''
        # Handle configurator specifically - use 'NaN' string if None/empty
        elif field == 'configurator' and (value is None or value == ''):
            csv_company[field] = 'NaN'
        # Keep other values as-is
        else:
            csv_company[field] = value if value is not None else ''
    
    csv_data.append(csv_company)

# Write CSV
print(f"Writing CSV to {csv_path}...")
with open(csv_path, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(csv_data)

print(f"Successfully converted {len(csv_data)} companies to CSV")
