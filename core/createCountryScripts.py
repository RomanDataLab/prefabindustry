#!/usr/bin/env python3
# Create research scripts for India, China, Turkey, Russia from USA template
import re

# Read USA template
with open('researchUSAPrefabCompanies.py', 'r', encoding='utf-8') as f:
    template = f.read()

# Country configurations
countries = {
    'India': {
        'currency': 'INR',
        'region_var': 'INDIA_STATES',
        'region_name': 'state',
        'region_label': 'State',
        'regions': '''INDIA_STATES = [
    {'code': 'AP', 'name': 'Andhra Pradesh'}, {'code': 'AR', 'name': 'Arunachal Pradesh'},
    {'code': 'AS', 'name': 'Assam'}, {'code': 'BR', 'name': 'Bihar'},
    {'code': 'CT', 'name': 'Chhattisgarh'}, {'code': 'GA', 'name': 'Goa'},
    {'code': 'GJ', 'name': 'Gujarat'}, {'code': 'HR', 'name': 'Haryana'},
    {'code': 'HP', 'name': 'Himachal Pradesh'}, {'code': 'JH', 'name': 'Jharkhand'},
    {'code': 'KA', 'name': 'Karnataka'}, {'code': 'KL', 'name': 'Kerala'},
    {'code': 'MP', 'name': 'Madhya Pradesh'}, {'code': 'MH', 'name': 'Maharashtra'},
    {'code': 'MN', 'name': 'Manipur'}, {'code': 'ML', 'name': 'Meghalaya'},
    {'code': 'MZ', 'name': 'Mizoram'}, {'code': 'NL', 'name': 'Nagaland'},
    {'code': 'OR', 'name': 'Odisha'}, {'code': 'PB', 'name': 'Punjab'},
    {'code': 'RJ', 'name': 'Rajasthan'}, {'code': 'SK', 'name': 'Sikkim'},
    {'code': 'TN', 'name': 'Tamil Nadu'}, {'code': 'TG', 'name': 'Telangana'},
    {'code': 'TR', 'name': 'Tripura'}, {'code': 'UP', 'name': 'Uttar Pradesh'},
    {'code': 'UK', 'name': 'Uttarakhand'}, {'code': 'WB', 'name': 'West Bengal'},
    {'code': 'AN', 'name': 'Andaman and Nicobar Islands'}, {'code': 'CH', 'name': 'Chandigarh'},
    {'code': 'DN', 'name': 'Dadra and Nagar Haveli and Daman and Diu'}, {'code': 'DL', 'name': 'Delhi'},
    {'code': 'JK', 'name': 'Jammu and Kashmir'}, {'code': 'LA', 'name': 'Ladakh'},
    {'code': 'LD', 'name': 'Lakshadweep'}, {'code': 'PY', 'name': 'Puducherry'}
]'''
    },
    'China': {
        'currency': 'CNY',
        'region_var': 'CHINA_PROVINCES',
        'region_name': 'province',
        'region_label': 'Province',
        'regions': '''CHINA_PROVINCES = [
    {'code': 'BJ', 'name': 'Beijing'}, {'code': 'TJ', 'name': 'Tianjin'},
    {'code': 'HE', 'name': 'Hebei'}, {'code': 'SX', 'name': 'Shanxi'},
    {'code': 'NM', 'name': 'Inner Mongolia'}, {'code': 'LN', 'name': 'Liaoning'},
    {'code': 'JL', 'name': 'Jilin'}, {'code': 'HL', 'name': 'Heilongjiang'},
    {'code': 'SH', 'name': 'Shanghai'}, {'code': 'JS', 'name': 'Jiangsu'},
    {'code': 'ZJ', 'name': 'Zhejiang'}, {'code': 'AH', 'name': 'Anhui'},
    {'code': 'FJ', 'name': 'Fujian'}, {'code': 'JX', 'name': 'Jiangxi'},
    {'code': 'SD', 'name': 'Shandong'}, {'code': 'HA', 'name': 'Henan'},
    {'code': 'HB', 'name': 'Hubei'}, {'code': 'HN', 'name': 'Hunan'},
    {'code': 'GD', 'name': 'Guangdong'}, {'code': 'GX', 'name': 'Guangxi'},
    {'code': 'HI', 'name': 'Hainan'}, {'code': 'CQ', 'name': 'Chongqing'},
    {'code': 'SC', 'name': 'Sichuan'}, {'code': 'GZ', 'name': 'Guizhou'},
    {'code': 'YN', 'name': 'Yunnan'}, {'code': 'XZ', 'name': 'Tibet'},
    {'code': 'SN', 'name': 'Shaanxi'}, {'code': 'GS', 'name': 'Gansu'},
    {'code': 'QH', 'name': 'Qinghai'}, {'code': 'NX', 'name': 'Ningxia'},
    {'code': 'XJ', 'name': 'Xinjiang'}, {'code': 'HK', 'name': 'Hong Kong'},
    {'code': 'MO', 'name': 'Macau'}
]'''
    },
    'Turkey': {
        'currency': 'TRY',
        'region_var': 'TURKEY_PROVINCES',
        'region_name': 'province',
        'region_label': 'Province',
        'regions': '''TURKEY_PROVINCES = [
    {'code': '01', 'name': 'Adana'}, {'code': '06', 'name': 'Ankara'},
    {'code': '07', 'name': 'Antalya'}, {'code': '34', 'name': 'Istanbul'},
    {'code': '35', 'name': 'İzmir'}, {'code': '16', 'name': 'Bursa'},
    {'code': '27', 'name': 'Gaziantep'}, {'code': '33', 'name': 'Mersin'},
    {'code': '21', 'name': 'Diyarbakır'}, {'code': '38', 'name': 'Kayseri'},
    {'code': '41', 'name': 'Kocaeli'}, {'code': '42', 'name': 'Konya'},
    {'code': '31', 'name': 'Hatay'}, {'code': '61', 'name': 'Trabzon'},
    {'code': '54', 'name': 'Sakarya'}, {'code': '55', 'name': 'Samsun'},
    {'code': '10', 'name': 'Balıkesir'}, {'code': '17', 'name': 'Çanakkale'},
    {'code': '20', 'name': 'Denizli'}, {'code': '26', 'name': 'Eskişehir'},
    {'code': '32', 'name': 'Isparta'}, {'code': '45', 'name': 'Manisa'},
    {'code': '48', 'name': 'Muğla'}, {'code': '59', 'name': 'Tekirdağ'},
    {'code': '02', 'name': 'Adıyaman'}, {'code': '03', 'name': 'Afyonkarahisar'},
    {'code': '04', 'name': 'Ağrı'}, {'code': '05', 'name': 'Amasya'},
    {'code': '08', 'name': 'Artvin'}, {'code': '09', 'name': 'Aydın'},
    {'code': '11', 'name': 'Bilecik'}, {'code': '12', 'name': 'Bingöl'},
    {'code': '13', 'name': 'Bitlis'}, {'code': '14', 'name': 'Bolu'},
    {'code': '15', 'name': 'Burdur'}, {'code': '18', 'name': 'Çankırı'},
    {'code': '19', 'name': 'Çorum'}, {'code': '22', 'name': 'Edirne'},
    {'code': '23', 'name': 'Elazığ'}, {'code': '24', 'name': 'Erzincan'},
    {'code': '25', 'name': 'Erzurum'}, {'code': '28', 'name': 'Giresun'},
    {'code': '29', 'name': 'Gümüşhane'}, {'code': '30', 'name': 'Hakkari'},
    {'code': '36', 'name': 'Kars'}, {'code': '37', 'name': 'Kastamonu'},
    {'code': '39', 'name': 'Kırklareli'}, {'code': '40', 'name': 'Kırşehir'},
    {'code': '43', 'name': 'Kütahya'}, {'code': '44', 'name': 'Malatya'},
    {'code': '46', 'name': 'Kahramanmaraş'}, {'code': '47', 'name': 'Mardin'},
    {'code': '49', 'name': 'Muş'}, {'code': '50', 'name': 'Nevşehir'},
    {'code': '51', 'name': 'Niğde'}, {'code': '52', 'name': 'Ordu'},
    {'code': '53', 'name': 'Rize'}, {'code': '56', 'name': 'Siirt'},
    {'code': '57', 'name': 'Sinop'}, {'code': '58', 'name': 'Sivas'},
    {'code': '60', 'name': 'Tokat'}, {'code': '62', 'name': 'Tunceli'},
    {'code': '63', 'name': 'Şanlıurfa'}, {'code': '64', 'name': 'Uşak'},
    {'code': '65', 'name': 'Van'}, {'code': '66', 'name': 'Yozgat'},
    {'code': '67', 'name': 'Zonguldak'}, {'code': '68', 'name': 'Aksaray'},
    {'code': '69', 'name': 'Bayburt'}, {'code': '70', 'name': 'Karaman'},
    {'code': '71', 'name': 'Kırıkkale'}, {'code': '72', 'name': 'Batman'},
    {'code': '73', 'name': 'Şırnak'}, {'code': '74', 'name': 'Bartın'},
    {'code': '75', 'name': 'Ardahan'}, {'code': '76', 'name': 'Iğdır'},
    {'code': '77', 'name': 'Yalova'}, {'code': '78', 'name': 'Karabük'},
    {'code': '79', 'name': 'Kilis'}, {'code': '80', 'name': 'Osmaniye'},
    {'code': '81', 'name': 'Düzce'}
]'''
    },
    'Russia': {
        'currency': 'RUB',
        'region_var': 'RUSSIA_REGIONS',
        'region_name': 'region',
        'region_label': 'Region',
        'regions': '''RUSSIA_REGIONS = [
    {'code': 'MOW', 'name': 'Moscow'}, {'code': 'SPE', 'name': 'Saint Petersburg'},
    {'code': 'MOS', 'name': 'Moscow Oblast'}, {'code': 'LEN', 'name': 'Leningrad Oblast'},
    {'code': 'KDA', 'name': 'Krasnodar Krai'}, {'code': 'STA', 'name': 'Stavropol Krai'},
    {'code': 'ROS', 'name': 'Rostov Oblast'}, {'code': 'NVS', 'name': 'Novosibirsk Oblast'},
    {'code': 'SVE', 'name': 'Sverdlovsk Oblast'}, {'code': 'CHE', 'name': 'Chelyabinsk Oblast'},
    {'code': 'NIZ', 'name': 'Nizhny Novgorod Oblast'}, {'code': 'SAM', 'name': 'Samara Oblast'},
    {'code': 'KEM', 'name': 'Kemerovo Oblast'}, {'code': 'PER', 'name': 'Perm Krai'},
    {'code': 'TA', 'name': 'Republic of Tatarstan'}, {'code': 'BA', 'name': 'Republic of Bashkortostan'},
    {'code': 'VOR', 'name': 'Voronezh Oblast'}, {'code': 'SAR', 'name': 'Saratov Oblast'},
    {'code': 'KR', 'name': 'Republic of Karelia'}, {'code': 'IRK', 'name': 'Irkutsk Oblast'},
    {'code': 'KYA', 'name': 'Krasnoyarsk Krai'}, {'code': 'ORE', 'name': 'Orenburg Oblast'},
    {'code': 'VGG', 'name': 'Volgograd Oblast'}, {'code': 'BEL', 'name': 'Belgorod Oblast'},
    {'code': 'KRS', 'name': 'Kursk Oblast'}, {'code': 'RYA', 'name': 'Ryazan Oblast'},
    {'code': 'TUL', 'name': 'Tula Oblast'}, {'code': 'LIP', 'name': 'Lipetsk Oblast'},
    {'code': 'TVE', 'name': 'Tver Oblast'}, {'code': 'IVA', 'name': 'Ivanovo Oblast'},
    {'code': 'BRY', 'name': 'Bryansk Oblast'}, {'code': 'VLA', 'name': 'Vladimir Oblast'},
    {'code': 'KAL', 'name': 'Kaliningrad Oblast'}, {'code': 'YAR', 'name': 'Yaroslavl Oblast'},
    {'code': 'ULY', 'name': 'Ulyanovsk Oblast'}, {'code': 'PSK', 'name': 'Pskov Oblast'},
    {'code': 'KOS', 'name': 'Kostroma Oblast'}, {'code': 'MUR', 'name': 'Murmansk Oblast'},
    {'code': 'ARK', 'name': 'Arkhangelsk Oblast'}, {'code': 'VLG', 'name': 'Vologda Oblast'},
    {'code': 'NGR', 'name': 'Novgorod Oblast'}, {'code': 'KIR', 'name': 'Kirov Oblast'},
    {'code': 'PNZ', 'name': 'Penza Oblast'}, {'code': 'TAM', 'name': 'Tambov Oblast'},
    {'code': 'ORL', 'name': 'Oryol Oblast'}, {'code': 'SMO', 'name': 'Smolensk Oblast'},
    {'code': 'KGN', 'name': 'Kurgan Oblast'}, {'code': 'KLU', 'name': 'Kaluga Oblast'},
    {'code': 'TOM', 'name': 'Tomsk Oblast'}, {'code': 'TYU', 'name': 'Tyumen Oblast'},
    {'code': 'OMS', 'name': 'Omsk Oblast'}, {'code': 'AST', 'name': 'Astrakhan Oblast'},
    {'code': 'SAK', 'name': 'Sakhalin Oblast'}, {'code': 'MAG', 'name': 'Magadan Oblast'},
    {'code': 'AMU', 'name': 'Amur Oblast'}, {'code': 'ZAB', 'name': 'Zabaykalsky Krai'},
    {'code': 'PRI', 'name': 'Primorsky Krai'}, {'code': 'AD', 'name': 'Republic of Adygea'},
    {'code': 'AL', 'name': 'Republic of Altai'}, {'code': 'BU', 'name': 'Republic of Buryatia'},
    {'code': 'CE', 'name': 'Chechen Republic'}, {'code': 'CU', 'name': 'Chuvash Republic'},
    {'code': 'DA', 'name': 'Republic of Dagestan'}, {'code': 'IN', 'name': 'Republic of Ingushetia'},
    {'code': 'KB', 'name': 'Kabardino-Balkarian Republic'}, {'code': 'KL', 'name': 'Republic of Kalmykia'},
    {'code': 'KC', 'name': 'Karachay-Cherkess Republic'}, {'code': 'KH', 'name': 'Republic of Khakassia'},
    {'code': 'KO', 'name': 'Komi Republic'}, {'code': 'ME', 'name': 'Republic of Mari El'},
    {'code': 'MO', 'name': 'Republic of Mordovia'}, {'code': 'SA', 'name': 'Republic of Sakha (Yakutia)'},
    {'code': 'SE', 'name': 'Republic of North Ossetia-Alania'}, {'code': 'TY', 'name': 'Tuva Republic'},
    {'code': 'UD', 'name': 'Udmurt Republic'}, {'code': 'ALT', 'name': 'Altai Krai'},
    {'code': 'SEV', 'name': 'Sevastopol'}, {'code': 'YEV', 'name': 'Jewish Autonomous Oblast'},
    {'code': 'CHU', 'name': 'Chukotka Autonomous Okrug'}, {'code': 'KHM', 'name': 'Khanty-Mansi Autonomous Okrug'},
    {'code': 'NEN', 'name': 'Nenets Autonomous Okrug'}, {'code': 'YAN', 'name': 'Yamalo-Nenets Autonomous Okrug'}
]'''
    }
}

# Generate scripts
for country, config in countries.items():
    script = template
    
    # Replacements
    replacements = [
        (r'USA prefab home companies', f'{country} prefab home companies'),
        (r'usa_prefab_core\.csv', f'{country.lower()}_prefab_core.csv'),
        (r'usa_progress_backup\.json', f'{country.lower()}_progress_backup.json'),
        (r'usa_prefab_core\.json', f'{country.lower()}_prefab_core.json'),
        (r'USA_STATES', config['region_var']),
        (r'USA states', f'{country} {config["region_name"]}s'),
        (r'US states', f'{country} {config["region_name"]}s'),
        (r'state\[', f'{config["region_name"]}['),
        (r'state\[''name''\]', f'{config["region_name"]}[\'name\']'),
        (r'state\[''code''\]', f'{config["region_name"]}[\'code\']'),
        (r'state: str', f'{config["region_name"]}: str'),
        (r'state: Dict', f'{config["region_name"]}: Dict'),
        (r'state\[', f'{config["region_name"]}['),
        (r'get_companies_for_state', f'get_companies_for_{config["region_name"]}'),
        (r'get_companies_for_state_alternative', f'get_companies_for_{config["region_name"]}_alternative'),
        (r'research_company\(company_name: str, state: str\)', f'research_company(company_name: str, {config["region_name"]}: str)'),
        (r'create_default_entry\(company_name: str, state: str\)', f'create_default_entry(company_name: str, {config["region_name"]}: str)'),
        (r'extract_company_names\(text: str, state: str\)', f'extract_company_names(text: str, {config["region_name"]}: str)'),
        (r'company\[\'state\'\]', f'company[\'{config["region_name"]}\']'),
        (r'company_data = research_company\(company\[\'name\'\], company\[\'state\'\]\)', f'company_data = research_company(company[\'name\'], company[\'{config["region_name"]}\'])'),
        (r'company\[\'name\'\], company\[\'state\'\]', f'company[\'name\'], company[\'{config["region_name"]}\']'),
        (r'company\[\'name\'\], state', f'company[\'name\'], {config["region_name"]}'),
        (r'company_name, state', f'company_name, {config["region_name"]}'),
        (r'company_name, {state}', f'company_name, {{{config["region_name"]}}}'),
        (r'State {i}/{len\(USA_STATES\)}', f'{config["region_label"]} {{i}}/{{len({config["region_var"]})}}'),
        (r'USA_STATES\)', f'{config["region_var"]})'),
        (r'for i, state in enumerate\(USA_STATES', f'for i, {config["region_name"]} in enumerate({config["region_var"]}'),
        (r'for state in USA_STATES', f'for {config["region_name"]} in {config["region_var"]}'),
        (r'in {state\[\'name\'\]}', f'in {{{config["region_name"]}[\'name\']}}'),
        (r'state\[\'name\'\]', f'{config["region_name"]}[\'name\']'),
        (r'state\[\'code\'\]', f'{config["region_name"]}[\'code\']'),
        (r'state\[', f'{config["region_name"]}['),
        (r'USD', config['currency']),
        (r'ZIP code', 'postal code'),
        (r'ZIP code, USA', f'postal code, {country}'),
        (r', USA', f', {country}'),
        (r'USA\.', f'{country}.'),
    ]
    
    for pattern, replacement in replacements:
        script = re.sub(pattern, replacement, script)
    
    # Replace regions list
    script = re.sub(
        r'# USA states for comprehensive research\nUSA_STATES = \[.*?\]',
        f'# {country} {config["region_name"]}s for comprehensive research\n{config["regions"]}',
        script,
        flags=re.DOTALL
    )
    
    # Fix function signatures
    script = re.sub(
        r'def get_companies_for_state\(state: Dict\)',
        f'def get_companies_for_{config["region_name"]}({config["region_name"]}: Dict)',
        script
    )
    script = re.sub(
        r'def get_companies_for_state_alternative\(state: Dict\)',
        f'def get_companies_for_{config["region_name"]}_alternative({config["region_name"]}: Dict)',
        script
    )
    
    # Update prompts
    script = re.sub(
        r'You are a research expert specializing in prefabricated/modular home companies in \{state\[\'name\'\]\}, USA\.',
        f'You are a research expert specializing in prefabricated/modular home companies in {{{config["region_name"]}[\'name\']}}, {country}.',
        script
    )
    script = re.sub(
        r'Include companies headquartered in \{state\[\'name\'\]\}',
        f'Include companies headquartered in {{{config["region_name"]}[\'name\']}}',
        script
    )
    script = re.sub(
        r'Include companies with manufacturing facilities in \{state\[\'name\'\]\}',
        f'Include companies with manufacturing facilities in {{{config["region_name"]}[\'name\']}}',
        script
    )
    script = re.sub(
        r'Include companies that primarily serve \{state\[\'name\'\]\} market',
        f'Include companies that primarily serve {{{config["region_name"]}[\'name\']}} market',
        script
    )
    script = re.sub(
        r'List all prefab home companies in \{state\[\'name\'\]\} state, USA\.',
        f'List all prefab home companies in {{{config["region_name"]}[\'name\']}} {config["region_name"]}, {country}.',
        script
    )
    script = re.sub(
        r'You are a professional researcher gathering detailed information about a prefabricated/modular home company in \{state\}, USA\.',
        f'You are a professional researcher gathering detailed information about a prefabricated/modular home company in {{{config["region_name"]}}}, {country}.',
        script
    )
    script = re.sub(
        r'State: \{state\}',
        f'{config["region_label"]}: {{{config["region_name"]}}}',
        script
    )
    script = re.sub(
        r'address": "complete address: street number, street name, city, state, ZIP code, USA"',
        f'address": "complete address: street number, street name, city, {config["region_name"]}, postal code, {country}"',
        script
    )
    
    # Write script
    filename = f'research{country}PrefabCompanies.py'
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(script)
    print(f'Created: {filename}')

print('All scripts created!')
