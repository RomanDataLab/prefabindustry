#!/usr/bin/env python3
"""Create Mexico research script from USA template"""
import shutil
import re

# Copy USA script
shutil.copy('researchUSAPrefabCompanies.py', 'researchMexicoPrefabCompanies.py')

# Read the copied file
with open('researchMexicoPrefabCompanies.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Mexico states
mexico_states = """MEXICO_STATES = [
    {'code': 'AGU', 'name': 'Aguascalientes'},
    {'code': 'BCN', 'name': 'Baja California'},
    {'code': 'BCS', 'name': 'Baja California Sur'},
    {'code': 'CAM', 'name': 'Campeche'},
    {'code': 'CHP', 'name': 'Chiapas'},
    {'code': 'CHH', 'name': 'Chihuahua'},
    {'code': 'COA', 'name': 'Coahuila'},
    {'code': 'COL', 'name': 'Colima'},
    {'code': 'DIF', 'name': 'Ciudad de México'},
    {'code': 'DUR', 'name': 'Durango'},
    {'code': 'GUA', 'name': 'Guanajuato'},
    {'code': 'GRO', 'name': 'Guerrero'},
    {'code': 'HID', 'name': 'Hidalgo'},
    {'code': 'JAL', 'name': 'Jalisco'},
    {'code': 'MEX', 'name': 'Estado de México'},
    {'code': 'MIC', 'name': 'Michoacán'},
    {'code': 'MOR', 'name': 'Morelos'},
    {'code': 'NAY', 'name': 'Nayarit'},
    {'code': 'NLE', 'name': 'Nuevo León'},
    {'code': 'OAX', 'name': 'Oaxaca'},
    {'code': 'PUE', 'name': 'Puebla'},
    {'code': 'QUE', 'name': 'Querétaro'},
    {'code': 'ROO', 'name': 'Quintana Roo'},
    {'code': 'SLP', 'name': 'San Luis Potosí'},
    {'code': 'SIN', 'name': 'Sinaloa'},
    {'code': 'SON', 'name': 'Sonora'},
    {'code': 'TAB', 'name': 'Tabasco'},
    {'code': 'TAM', 'name': 'Tamaulipas'},
    {'code': 'TLA', 'name': 'Tlaxcala'},
    {'code': 'VER', 'name': 'Veracruz'},
    {'code': 'YUC', 'name': 'Yucatán'},
    {'code': 'ZAC', 'name': 'Zacatecas'}
]"""

# Replace states section
content = re.sub(r'USA_STATES = \[.*?\]', mexico_states, content, flags=re.DOTALL)

# Basic replacements
replacements = [
    ('USA prefab home companies', 'Mexico prefab home companies'),
    ('USA_STATES', 'MEXICO_STATES'),
    ('usa_prefab_core', 'mexico_prefab_core'),
    ('usa_progress_backup', 'mexico_progress_backup'),
    ('USA,', 'México,'),
    ('ZIP code, USA', 'código postal, México'),
    ('price in USD', 'price in MXN (Mexican Pesos)'),
    ('price per square meter in USD', 'price per square meter in MXN (Mexican Pesos)'),
    ('US states', 'Mexican states'),
    ('US state', 'Mexican state'),
    ('in {state}, USA', 'in {state}, México'),
]

for old, new in replacements:
    content = content.replace(old, new)

# Add country fields to result dictionary in research_company function
content = content.replace(
    """result = {
                    'id': company_id,
                    'brand': data.get('brand') or company_name,
                    'head_office_legal_name': data.get('head_office_legal_name') or None,
                    'address': data.get('address') or None,
                    'webpage': data.get('webpage') or None,""",
    """result = {
                    'id': company_id,
                    'brand': data.get('brand') or company_name,
                    'head_office_legal_name': data.get('head_office_legal_name') or None,
                    'address': data.get('address') or None,
                    'country': 'Mexico',
                    'country_code': 'MEX',
                    'region': state,
                    'webpage': data.get('webpage') or None,"""
)

# Update create_default_entry
content = content.replace(
    """    entry = {
        'id': company_id,
        'brand': company_name,
        'head_office_legal_name': None,
        'address': None,
        'webpage': None,""",
    """    entry = {
        'id': company_id,
        'brand': company_name,
        'head_office_legal_name': None,
        'address': None,
        'country': 'Mexico',
        'country_code': 'MEX',
        'region': state,
        'webpage': None,"""
)

# Update CSV fieldnames to include country, country_code, region
content = content.replace(
    """    fieldnames = [
        'id', 'brand', 'head_office_legal_name', 'address', 'webpage',
        'configurator', 'models_amount', 'min_sqm', 'max_sqm',
        'main_structure_material', 'min_home_price', 'average_price_sqm'
    ]""",
    """    fieldnames = [
        'id', 'brand', 'head_office_legal_name', 'address', 'country', 'country_code', 'region', 'webpage',
        'configurator', 'models_amount', 'min_sqm', 'max_sqm',
        'main_structure_material', 'min_home_price', 'average_price_sqm'
    ]"""
)

# Update CSV data building to include country fields
content = content.replace(
    """    # Convert data for CSV (handle None, NaN strings, and actual NaN values)
    csv_data = []
    for company in all_companies:
        csv_company = {}
        for field in fieldnames:""",
    """    # Convert data for CSV (handle None, NaN strings, and actual NaN values)
    csv_data = []
    for company in all_companies:
        csv_company = {}
        for field in fieldnames:
            # Handle country fields specially
            if field in ['country', 'country_code', 'region']:
                csv_company[field] = company.get(field, '') if company.get(field) else ''
                continue"""
)

# Write the modified content
with open('researchMexicoPrefabCompanies.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Created researchMexicoPrefabCompanies.py successfully!')
