#!/usr/bin/env python3
# Merge prefabassociated.csv below prefabworldtest_2.csv and enrich with deep search
import sys
import os
import json
import csv
import time
import re
import requests
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse
from bs4 import BeautifulSoup

# Fix Windows encoding issues
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add parent directory to path to import apiManager
sys.path.insert(0, str(Path(__file__).parent.parent))
from configix.apiManager import get_ai_provider

try:
    from openai import OpenAI
except ImportError:
    print("Error: openai package not installed. Run: pip install openai")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("Error: requests package not installed. Run: pip install requests")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Error: beautifulsoup4 package not installed. Run: pip install beautifulsoup4")
    sys.exit(1)

# Initialize OpenAI with API key from configix
openai_config = get_ai_provider('ai_openai')
openai_client = OpenAI(api_key=openai_config['api_key'])

# Country to language mapping
COUNTRY_LANGUAGE_MAP = {
    'Germany': 'German', 'DEU': 'German',
    'France': 'French', 'FRA': 'French',
    'Italy': 'Italian', 'ITA': 'Italian',
    'Spain': 'Spanish', 'ESP': 'Spanish',
    'Netherlands': 'Dutch', 'NLD': 'Dutch',
    'Belgium': 'Dutch/French', 'BEL': 'Dutch/French',
    'Austria': 'German', 'AUT': 'German',
    'Sweden': 'Swedish', 'SWE': 'Swedish',
    'Denmark': 'Danish', 'DNK': 'Danish',
    'Finland': 'Finnish', 'FIN': 'Finnish',
    'Poland': 'Polish', 'POL': 'Polish',
    'Czech Republic': 'Czech', 'CZE': 'Czech',
    'Portugal': 'Portuguese', 'PRT': 'Portuguese',
    'Greece': 'Greek', 'GRC': 'Greek',
    'Ireland': 'English', 'IRL': 'English',
    'Romania': 'Romanian', 'ROU': 'Romanian',
    'Hungary': 'Hungarian', 'HUN': 'Hungarian',
    'Slovakia': 'Slovak', 'SVK': 'Slovak',
    'Bulgaria': 'Bulgarian', 'BGR': 'Bulgarian',
    'Croatia': 'Croatian', 'HRV': 'Croatian',
    'Slovenia': 'Slovenian', 'SVN': 'Slovenian',
    'Lithuania': 'Lithuanian', 'LTU': 'Lithuanian',
    'Latvia': 'Latvian', 'LVA': 'Latvian',
    'Estonia': 'Estonian', 'EST': 'Estonian',
    'Luxembourg': 'Luxembourgish/French', 'LUX': 'Luxembourgish/French',
    'Switzerland': 'German/French/Italian', 'CHE': 'German/French/Italian',
    'Norway': 'Norwegian', 'NOR': 'Norwegian',
    'United Kingdom': 'English', 'GBR': 'English',
    'United States': 'English', 'USA': 'English', 'US': 'English',
    'Canada': 'English/French', 'CAN': 'English/French',
    'Mexico': 'Spanish', 'MEX': 'Spanish',
    'Brazil': 'Portuguese', 'BRA': 'Portuguese',
    'Chile': 'Spanish', 'CHL': 'Spanish',
    'China': 'Chinese', 'CHN': 'Chinese',
    'Japan': 'Japanese', 'JPN': 'Japanese',
    'India': 'Hindi and English', 'IND': 'Hindi and English',
    'Russia': 'Russian', 'RUS': 'Russian',
    'Turkey': 'Turkish', 'TUR': 'Turkish',
    'Australia': 'English', 'AUS': 'English',
    'Saudi Arabia': 'Arabic', 'SAU': 'Arabic',
    'UAE': 'Arabic', 'ARE': 'Arabic',
    'Kazakhstan': 'Kazakh/Russian', 'KAZ': 'Kazakh/Russian',
    'Uzbekistan': 'Uzbek/Russian', 'UZB': 'Uzbek/Russian',
}

def get_language_for_country(country: str, country_code: str = None) -> str:
    """Get language for a country"""
    if country:
        lang = COUNTRY_LANGUAGE_MAP.get(country, None)
        if lang:
            return lang.split('/')[0]  # Use first language if multiple
    if country_code:
        lang = COUNTRY_LANGUAGE_MAP.get(country_code, None)
        if lang:
            return lang.split('/')[0]
    return 'English'  # Default

def call_openai(messages: List[Dict], max_retries: int = 3) -> str:
    """Call OpenAI API with retry logic"""
    for i in range(max_retries):
        try:
            response = openai_client.chat.completions.create(
                model='gpt-4o',
                messages=messages,
                temperature=0.7,
                max_tokens=4000
            )
            return response.choices[0].message.content
        except Exception as error:
            error_str = str(error).lower()
            if any(keyword in error_str for keyword in ['rate limit', 'quota', '429', 'resource_exhausted', 'too many requests']):
                backoff_time = min(60 * (i + 1), 300)  # Max 5 minutes
                print(f"  ⚠️  Rate limit hit. Waiting {backoff_time}s...")
                if i < max_retries - 1:
                    time.sleep(backoff_time)
                    continue
                else:
                    raise Exception(f"Rate limit exceeded: {error}")
            
            print(f"  ⚠️  Attempt {i + 1}/{max_retries} failed: {error}")
            if i == max_retries - 1:
                raise
            time.sleep(2 * (i + 1))

def fetch_webpage_content(url: str, timeout: int = 15) -> Optional[str]:
    """Fetch webpage content and return text"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, timeout=timeout, headers=headers, allow_redirects=True)
        response.raise_for_status()
        
        # Parse HTML and extract text
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()
        
        # Get text
        text = soup.get_text(separator=' ', strip=True)
        
        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        # Limit to first 20000 characters to avoid token limits
        return text[:20000]
    except Exception as e:
        print(f"  ⚠️  Error fetching webpage: {e}")
        return None

def check_configurator(company_name: str, webpage: str) -> Optional[str]:
    """Check if company has an online configurator and get direct link"""
    if not webpage:
        return None
    
    prompt = f"""You are checking if a prefab home company has an online configurator tool where users can model or configure homes online.

Company: {company_name}
Website: {webpage}

Check if this company has ANY online tool where customers can:
- Configure or customize their home online
- Model their home online
- Design their home online
- Use an interactive configurator
- Select options/features for their home online
- Browse model range pages with detailed specifications

This includes tools like:
- Home configurators
- Design tools
- Customization tools
- Interactive planners
- Online builders
- Model range pages with detailed specifications

This does NOT include:
- Simple contact forms
- Image galleries
- PDF downloads
- Static product pages
- Request a quote forms (unless they include configuration)

If a configurator or model range page exists, return ONLY the direct URL to that page (must be a full URL starting with http:// or https://).
If no configurator exists, return exactly: NaN

Return ONLY the URL or NaN, nothing else."""

    try:
        response = call_openai([{'role': 'user', 'content': prompt}])
        result = response.strip()
        
        # Check if it's a valid URL
        if result and result != 'NaN' and result != 'null' and (result.startswith('http://') or result.startswith('https://')):
            return result
        
        return None  # Will be converted to NaN in CSV
    except Exception as error:
        print(f"  ⚠️  Error checking configurator for {company_name}: {error}")
        return None

def investigate_webpage_and_extract_info(webpage: str, brand: str, company_name: str, country: str, language: str, existing_row: Dict) -> Dict:
    """Investigate webpage content and extract company information"""
    
    # Fetch webpage content
    print(f"    📄 Fetching webpage content...")
    webpage_content = fetch_webpage_content(webpage)
    
    if not webpage_content:
        print(f"    ⚠️  Could not fetch webpage content, using AI search only")
        webpage_content = ""
    
    # Build prompt for extraction
    existing_data = []
    for key, value in existing_row.items():
        if key != 'id' and value and str(value).strip() not in ['', 'NaN', 'null', 'None']:
            existing_data.append(f"{key}: {value}")
    
    prompt = f"""You are investigating a prefab/modular home company's website to extract detailed information.

Company brand name: {brand or 'Unknown'}
Legal company name: {company_name or 'Unknown'}
Country: {country or 'Unknown'}
Website URL: {webpage}
Language: {language}

Existing data:
{chr(10).join(existing_data) if existing_data else 'No existing data'}

Webpage content (first 15000 chars):
{webpage_content[:15000] if webpage_content else 'Could not fetch webpage content - use your knowledge to search'}

Extract and fill in ALL available information. Return ONLY valid JSON in this exact format (use null for missing data, NaN for numeric fields that cannot be determined):

{{
  "head_office_legal_name": "full legal registered company name",
  "address": "complete address: street number, street name, city, postal code, country",
  "country": "country name",
  "country_code": "ISO 3166-1 alpha-3 country code",
  "region": "state/province/region name",
  "models_amount": number of different prefab home models/designs (integer),
  "min_sqm": minimum square meters of smallest model (number, living area),
  "max_sqm": maximum square meters of largest model (number, living area),
  "main_structure_material": "primary construction material: wood/timber/concrete/steel/composite/CLT/etc",
  "min_home_price": minimum starting price in local currency (number, base price without land),
  "average_price_sqm": average price per square meter in local currency (number)
}}

CRITICAL REQUIREMENTS:
- Extract information from the webpage content if available
- If webpage content is not available, use your knowledge to search for this company
- Only fill in fields where you can find reliable information
- For prices, use the local currency (do not convert)
- Be precise and factual
- Consider the local language ({language}) when interpreting information
- Count actual house models/designs available on the website
- Return ONLY the JSON object, no explanations"""

    try:
        response = call_openai([{'role': 'user', 'content': prompt}])
        
        # Extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                return data
            except json.JSONDecodeError as e:
                print(f"    ⚠️  Error parsing JSON: {e}")
                return {}
        return {}
    except Exception as e:
        print(f"    ⚠️  Error investigating webpage: {e}")
        return {}

def is_nan_or_empty(value) -> bool:
    """Check if value is NaN or empty"""
    if value is None:
        return True
    value_str = str(value).strip()
    return value_str in ['', 'NaN', 'null', 'None', 'nan']

def merge_and_enrich_csvs(resume_from: int = 0):
    """Merge CSVs and enrich with deep search"""
    print('🚀 Starting merge and enrichment process...\n')
    print(f"Using OpenAI API ({openai_config['name']})\n")
    
    # File paths
    base_dir = Path(__file__).parent.parent / 'maps' / 'public'
    csv1_path = base_dir / 'prefabworldtest_2.csv'
    csv2_path = base_dir / 'prefabassociated.csv'
    output_path = base_dir / 'prefabworldtest_2.csv'  # Overwrite the first file
    checkpoint_path = base_dir / 'merge_checkpoint.json'
    
    # Read first CSV
    print(f"📄 Reading {csv1_path.name}...")
    rows1 = []
    fieldnames = []
    try:
        with open(csv1_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows1 = list(reader)
        print(f"✅ Loaded {len(rows1)} rows from {csv1_path.name}\n")
    except Exception as e:
        print(f"❌ Error reading CSV: {e}")
        return
    
    # Read second CSV
    print(f"📄 Reading {csv2_path.name}...")
    rows2 = []
    try:
        with open(csv2_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            # Merge fieldnames if CSV2 has additional columns
            csv2_fieldnames = reader.fieldnames
            if csv2_fieldnames != fieldnames:
                print(f"⚠️  Fieldnames differ - CSV1: {len(fieldnames)} columns, CSV2: {len(csv2_fieldnames)} columns")
                # Add missing columns from CSV2 to fieldnames
                for col in csv2_fieldnames:
                    if col not in fieldnames:
                        fieldnames.append(col)
                        print(f"  ➕ Added column: {col}")
            rows2 = list(reader)
        print(f"✅ Loaded {len(rows2)} rows from {csv2_path.name}\n")
    except Exception as e:
        print(f"❌ Error reading CSV: {e}")
        return
    
    # Ensure all rows have all columns
    for row in rows1:
        for col in fieldnames:
            if col not in row:
                row[col] = 'NaN'
    
    for row in rows2:
        for col in fieldnames:
            if col not in row:
                row[col] = 'NaN'
    
    # Merge rows (rows2 below rows1)
    merged_rows = rows1 + rows2
    print(f"✅ Merged {len(merged_rows)} total rows\n")
    
    # Update IDs to be sequential
    for i, row in enumerate(merged_rows, 1):
        row['id'] = str(i)
    
    # Check for checkpoint
    enriched_rows = []
    if resume_from > 0 and checkpoint_path.exists():
        print(f"📂 Resuming from checkpoint at row {resume_from}...")
        try:
            with open(checkpoint_path, 'r', encoding='utf-8') as f:
                checkpoint_data = json.load(f)
                enriched_rows = checkpoint_data.get('enriched_rows', [])
                stats = checkpoint_data.get('stats', {
                    'total': len(merged_rows),
                    'processed': 0,
                    'webpages_investigated': 0,
                    'fields_filled': 0,
                    'configurators_found': 0
                })
                print(f"✅ Loaded checkpoint: {len(enriched_rows)} rows already processed")
        except Exception as e:
            print(f"⚠️  Error loading checkpoint: {e}, starting fresh")
            enriched_rows = []
            stats = {
                'total': len(merged_rows),
                'processed': 0,
                'webpages_investigated': 0,
                'fields_filled': 0,
                'configurators_found': 0
            }
    else:
        stats = {
            'total': len(merged_rows),
            'processed': 0,
            'webpages_investigated': 0,
            'fields_filled': 0,
            'configurators_found': 0
        }
    
    # Process each row and enrich with deep search
    print(f"\n{'='*80}")
    print("🔬 Enriching data with deep search...")
    print(f"{'='*80}\n")
    
    start_idx = len(enriched_rows)
    for i, row in enumerate(merged_rows[start_idx:], start_idx + 1):
        row_id = row.get('id', i)
        brand = row.get('brand', '').strip()
        company_name = row.get('head_office_legal_name', '').strip()
        webpage = row.get('webpage', '').strip()
        country = row.get('country', '').strip()
        country_code = row.get('country_code', '').strip()
        
        print(f"\n[{i}/{len(merged_rows)}] Row {row_id}: {brand or company_name or 'Unknown'}")
        
        updated_row = row.copy()
        
        # Skip if no webpage
        if not webpage or is_nan_or_empty(webpage):
            print(f"  ⏭️  Skipping - no webpage URL")
            enriched_rows.append(updated_row)
            continue
        
        # Check if row needs enrichment (has at least one missing field)
        needs_enrichment = (
            is_nan_or_empty(updated_row.get('head_office_legal_name')) or
            is_nan_or_empty(updated_row.get('address')) or
            is_nan_or_empty(updated_row.get('country')) or
            is_nan_or_empty(updated_row.get('country_code')) or
            is_nan_or_empty(updated_row.get('region')) or
            is_nan_or_empty(updated_row.get('configurator')) or
            is_nan_or_empty(updated_row.get('models_amount')) or
            is_nan_or_empty(updated_row.get('min_sqm')) or
            is_nan_or_empty(updated_row.get('max_sqm')) or
            is_nan_or_empty(updated_row.get('main_structure_material')) or
            is_nan_or_empty(updated_row.get('min_home_price')) or
            is_nan_or_empty(updated_row.get('average_price_sqm'))
        )
        
        if not needs_enrichment:
            print(f"  ⏭️  Skipping - all fields already filled")
            enriched_rows.append(updated_row)
            continue
        
        # Get language for country
        language = get_language_for_country(country, country_code)
        print(f"  🌐 Language: {language}")
        
        # Investigate webpage and extract information
        print(f"  🔬 Investigating webpage: {webpage}")
        extracted_data = investigate_webpage_and_extract_info(
            webpage, brand, company_name, country, language, updated_row
        )
        
        stats['webpages_investigated'] += 1
        
        # Update fields if they are NaN or empty
        fields_updated = 0
        if extracted_data:
            # Update head_office_legal_name if NaN
            if is_nan_or_empty(updated_row.get('head_office_legal_name')) and extracted_data.get('head_office_legal_name'):
                updated_row['head_office_legal_name'] = extracted_data['head_office_legal_name']
                fields_updated += 1
                print(f"    ✅ Filled head_office_legal_name: {extracted_data['head_office_legal_name']}")
            
            # Update address if empty
            if is_nan_or_empty(updated_row.get('address')) and extracted_data.get('address'):
                updated_row['address'] = extracted_data['address']
                fields_updated += 1
                print(f"    ✅ Filled address: {extracted_data['address']}")
            
            # Update country if empty
            if is_nan_or_empty(updated_row.get('country')) and extracted_data.get('country'):
                updated_row['country'] = extracted_data['country']
                fields_updated += 1
                print(f"    ✅ Filled country: {extracted_data['country']}")
            
            # Update country_code if empty
            if is_nan_or_empty(updated_row.get('country_code')) and extracted_data.get('country_code'):
                updated_row['country_code'] = extracted_data['country_code']
                fields_updated += 1
                print(f"    ✅ Filled country_code: {extracted_data['country_code']}")
            
            # Update region if empty
            if is_nan_or_empty(updated_row.get('region')) and extracted_data.get('region'):
                updated_row['region'] = extracted_data['region']
                fields_updated += 1
                print(f"    ✅ Filled region: {extracted_data['region']}")
            
            # Update models_amount if NaN
            if is_nan_or_empty(updated_row.get('models_amount')) and extracted_data.get('models_amount'):
                try:
                    models_amount = int(extracted_data['models_amount'])
                    updated_row['models_amount'] = str(models_amount)
                    fields_updated += 1
                    print(f"    ✅ Filled models_amount: {models_amount}")
                except (ValueError, TypeError):
                    pass
            
            # Update min_sqm if NaN
            if is_nan_or_empty(updated_row.get('min_sqm')) and extracted_data.get('min_sqm'):
                try:
                    min_sqm = float(extracted_data['min_sqm'])
                    updated_row['min_sqm'] = str(min_sqm)
                    fields_updated += 1
                    print(f"    ✅ Filled min_sqm: {min_sqm}")
                except (ValueError, TypeError):
                    pass
            
            # Update max_sqm if NaN
            if is_nan_or_empty(updated_row.get('max_sqm')) and extracted_data.get('max_sqm'):
                try:
                    max_sqm = float(extracted_data['max_sqm'])
                    updated_row['max_sqm'] = str(max_sqm)
                    fields_updated += 1
                    print(f"    ✅ Filled max_sqm: {max_sqm}")
                except (ValueError, TypeError):
                    pass
            
            # Update main_structure_material if NaN
            if is_nan_or_empty(updated_row.get('main_structure_material')) and extracted_data.get('main_structure_material'):
                updated_row['main_structure_material'] = extracted_data['main_structure_material']
                fields_updated += 1
                print(f"    ✅ Filled main_structure_material: {extracted_data['main_structure_material']}")
            
            # Update min_home_price if NaN
            if is_nan_or_empty(updated_row.get('min_home_price')) and extracted_data.get('min_home_price'):
                try:
                    min_price = float(extracted_data['min_home_price'])
                    updated_row['min_home_price'] = str(min_price)
                    fields_updated += 1
                    print(f"    ✅ Filled min_home_price: {min_price}")
                except (ValueError, TypeError):
                    pass
            
            # Update average_price_sqm if NaN
            if is_nan_or_empty(updated_row.get('average_price_sqm')) and extracted_data.get('average_price_sqm'):
                try:
                    avg_price = float(extracted_data['average_price_sqm'])
                    updated_row['average_price_sqm'] = str(avg_price)
                    fields_updated += 1
                    print(f"    ✅ Filled average_price_sqm: {avg_price}")
                except (ValueError, TypeError):
                    pass
        
        # Check for configurator if NaN
        if is_nan_or_empty(updated_row.get('configurator')):
            print(f"  🔍 Checking for configurator...")
            configurator_url = check_configurator(brand or company_name, webpage)
            if configurator_url:
                updated_row['configurator'] = configurator_url
                stats['configurators_found'] += 1
                print(f"    ✅ Found configurator: {configurator_url}")
            else:
                updated_row['configurator'] = 'NaN'
            time.sleep(1)  # Rate limiting
        
        stats['fields_filled'] += fields_updated
        stats['processed'] += 1
        enriched_rows.append(updated_row)
        
        # Rate limiting between rows
        time.sleep(2)
        
        # Progress update and checkpoint every 10 rows
        if i % 10 == 0:
            print(f"\n💾 Progress: {i}/{len(merged_rows)} rows processed")
            print(f"   Stats: {stats['webpages_investigated']} webpages investigated, {stats['fields_filled']} fields filled")
            
            # Save checkpoint
            try:
                checkpoint_data = {
                    'enriched_rows': enriched_rows,
                    'stats': stats,
                    'last_row': i
                }
                with open(checkpoint_path, 'w', encoding='utf-8') as f:
                    json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
                print(f"   💾 Checkpoint saved")
            except Exception as e:
                print(f"   ⚠️  Error saving checkpoint: {e}")
    
    # Save enriched CSV
    print(f"\n{'='*80}")
    print("💾 Saving enriched CSV...")
    print(f"{'='*80}\n")
    
    try:
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in enriched_rows:
                csv_row = {}
                for key in fieldnames:
                    value = row.get(key)
                    if value is None or value == '':
                        csv_row[key] = 'NaN'
                    else:
                        csv_row[key] = str(value)
                writer.writerow(csv_row)
        print(f"✅ Saved enriched CSV: {output_path.name}\n")
        
        # Remove checkpoint file on successful completion
        if checkpoint_path.exists():
            checkpoint_path.unlink()
            print(f"✅ Removed checkpoint file\n")
    except Exception as e:
        print(f"❌ Error saving CSV: {e}\n")
        import traceback
        traceback.print_exc()
        return
    
    # Print summary
    print(f"\n{'='*80}")
    print("📊 Summary")
    print(f"{'='*80}")
    print(f"Total rows: {stats['total']}")
    print(f"Rows processed: {stats['processed']}")
    print(f"Webpages investigated: {stats['webpages_investigated']}")
    print(f"Total fields filled: {stats['fields_filled']}")
    print(f"Configurators found: {stats['configurators_found']}")
    print(f"Final rows: {len(enriched_rows)}")
    print(f"{'='*80}\n")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Merge and enrich CSV files')
    parser.add_argument('--resume', type=int, default=0, help='Resume from row number (0 = start from beginning)')
    args = parser.parse_args()
    
    try:
        merge_and_enrich_csvs(resume_from=args.resume)
        print("🎉 Processing complete!")
    except KeyboardInterrupt:
        print("\n\n⚠️  Process interrupted by user. Checkpoint saved. Resume with --resume <row_number>")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
