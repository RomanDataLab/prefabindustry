#!/usr/bin/env python3
# Deep search for company webpages and fill requisites using OpenAI
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

try:
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderTimedOut, GeocoderServiceError
    geopy_available = True
except ImportError:
    print("Warning: geopy not installed. Geocoding will use OpenAI only.")
    geopy_available = False

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
    'Malta': 'Maltese', 'MLT': 'Maltese',
    'Cyprus': 'Greek', 'CYP': 'Greek',
    'Switzerland': 'German/French/Italian', 'CHE': 'German/French/Italian',
    'Norway': 'Norwegian', 'NOR': 'Norwegian',
    'Iceland': 'Icelandic', 'ISL': 'Icelandic',
    'United Kingdom': 'English', 'GBR': 'English',
    'Ukraine': 'Ukrainian', 'UKR': 'Ukrainian',
    'United States': 'English', 'USA': 'English', 'US': 'English',
    'Canada': 'English/French', 'CAN': 'English/French',
    'Mexico': 'Spanish', 'MEX': 'Spanish',
    'Brazil': 'Portuguese', 'BRA': 'Portuguese',
    'Chile': 'Spanish', 'CHL': 'Spanish',
    'Argentina': 'Spanish', 'ARG': 'Spanish',
    'China': 'Chinese', 'CHN': 'Chinese',
    'Japan': 'Japanese', 'JPN': 'Japanese',
    'India': 'Hindi and English', 'IND': 'Hindi and English',
    'Russia': 'Russian', 'RUS': 'Russian',
    'Turkey': 'Turkish', 'TUR': 'Turkish',
    'Australia': 'English', 'AUS': 'English',
    'New Zealand': 'English', 'NZL': 'English',
    'South Africa': 'English', 'ZAF': 'English',
    'South Korea': 'Korean', 'KOR': 'Korean',
    'Thailand': 'Thai', 'THA': 'Thai',
    'Vietnam': 'Vietnamese', 'VNM': 'Vietnamese',
    'Indonesia': 'Indonesian', 'IDN': 'Indonesian',
    'Malaysia': 'Malay', 'MYS': 'Malay',
    'Singapore': 'English', 'SGP': 'English',
    'Philippines': 'English', 'PHL': 'English',
    'Israel': 'Hebrew', 'ISR': 'Hebrew',
    'Saudi Arabia': 'Arabic', 'SAU': 'Arabic',
    'UAE': 'Arabic', 'ARE': 'Arabic',
    'Egypt': 'Arabic', 'EGY': 'Arabic',
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
        
        # Limit to first 10000 characters to avoid token limits
        return text[:10000]
    except Exception as e:
        print(f"  ⚠️  Error fetching webpage: {e}")
        return None

def verify_company_exists(brand: str, company_name: str, country: str, language: str) -> Tuple[bool, Optional[str]]:
    """Verify company exists and find webpage. Returns (exists, webpage_url)"""
    if not brand and not company_name:
        return False, None
    
    prompt = f"""You are verifying if a prefab/modular home company actually exists and finding proven evidence of its existence and official website.

Company brand name: {brand or 'Unknown'}
Legal company name: {company_name or 'Unknown'}
Country: {country or 'Unknown'}
Search language: {language}

IMPORTANT: You need to find PROVEN EVIDENCE that this company exists:
- Official website URL (must be verifiable)
- Company registration information
- Business listings
- News articles mentioning the company
- Industry directories
- Social media presence

Search using {language} language if helpful.

If you find PROVEN EVIDENCE that the company exists and can find its official website, return:
- The official website homepage URL (must start with http:// or https://)

If you CANNOT find proven evidence that this company exists, return exactly: null

Return ONLY the URL or null, nothing else."""

    try:
        response = call_openai([{'role': 'user', 'content': prompt}])
        result = response.strip()
        
        # Clean up response
        result = result.replace('"', '').replace("'", "").replace('`', '')
        
        if result and result.lower() != 'null' and (result.startswith('http://') or result.startswith('https://')):
            return True, result
        return False, None
    except Exception as e:
        print(f"  ⚠️  Error verifying company: {e}")
        return False, None

def deep_search_webpage(brand: str, company_name: str, country: str, language: str) -> Optional[str]:
    """Use deep search to find company webpage"""
    if not brand and not company_name:
        return None
    
    prompt = f"""You are conducting a DEEP SEARCH to find the official website URL for a prefab/modular home company.

Company brand name: {brand or 'Unknown'}
Legal company name: {company_name or 'Unknown'}
Country: {country or 'Unknown'}
Search language: {language}

IMPORTANT: Perform a thorough search considering:
- The company name variations (with/without legal suffixes like GmbH, S.A., Ltd, etc.)
- Common domain patterns (.com, .de, .fr, .es, .it, country-specific TLDs)
- The local language and country context
- Alternative spellings or transliterations
- Industry-specific terms (prefab, modular, prefabricated, etc.)

Search using {language} language keywords if helpful.

Return ONLY the official website homepage URL (must start with http:// or https://).
If you cannot find a website after thorough search, return exactly: null

Return ONLY the URL or null, nothing else."""

    try:
        response = call_openai([{'role': 'user', 'content': prompt}])
        result = response.strip()
        
        # Clean up response
        result = result.replace('"', '').replace("'", "").replace('`', '')
        
        if result and result.lower() != 'null' and (result.startswith('http://') or result.startswith('https://')):
            return result
        return None
    except Exception as e:
        print(f"  ⚠️  Error in deep search: {e}")
        return None

def check_duplicate_webpages(rows: List[Dict]) -> List[Dict]:
    """Check for duplicate webpages using AI and remove duplicates, then renumber IDs"""
    print(f"\n{'='*80}")
    print("🔍 Checking for duplicate webpages...")
    print(f"{'='*80}\n")
    
    # Group rows by webpage
    webpage_groups = {}
    for i, row in enumerate(rows):
        webpage = row.get('webpage', '').strip()
        if webpage and webpage not in ['', 'NaN', 'null', 'None']:
            if webpage not in webpage_groups:
                webpage_groups[webpage] = []
            webpage_groups[webpage].append((i, row))
    
    # Check groups with multiple entries
    duplicates_to_check = {url: items for url, items in webpage_groups.items() if len(items) > 1}
    
    if not duplicates_to_check:
        print("✅ No duplicate webpages found\n")
        return rows
    
    print(f"Found {len(duplicates_to_check)} webpage URLs with multiple entries\n")
    
    rows_to_remove = set()
    
    for webpage, items in duplicates_to_check.items():
        if len(items) <= 1:
            continue
        
        print(f"  🔍 Checking duplicates for: {webpage}")
        print(f"     Found {len(items)} entries")
        
        # Use AI to determine which entries are actually the same company
        company_info_list = []
        for idx, (row_idx, row) in enumerate(items):
            brand = row.get('brand', '').strip()
            company_name = row.get('head_office_legal_name', '').strip()
            address = row.get('address', '').strip()
            company_info_list.append(f"Entry {idx+1}: Brand='{brand}', Legal Name='{company_name}', Address='{address}'")
        
        prompt = f"""You are checking if multiple database entries with the same webpage URL represent the same company or different companies.

Webpage URL: {webpage}

Entries:
{chr(10).join(company_info_list)}

Determine which entries represent the SAME company (duplicates) and which are DIFFERENT companies that happen to share a webpage.

Return ONLY a JSON array indicating which entries to KEEP (keep the most complete/accurate entry for each unique company):
{{
  "keep_entries": [1, 3],  // Entry numbers (1-indexed) to KEEP
  "remove_entries": [2, 4]  // Entry numbers (1-indexed) to REMOVE as duplicates
}}

If all entries represent the same company, keep only entry 1 and remove the rest.
If entries represent different companies, keep all entries.

Return ONLY the JSON object, no explanations."""

        try:
            response = call_openai([{'role': 'user', 'content': prompt}])
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group(0))
                keep_entries = data.get('keep_entries', [1])
                remove_entries = data.get('remove_entries', [])
                
                print(f"     Keeping entries: {keep_entries}")
                print(f"     Removing entries: {remove_entries}")
                
                # Mark entries for removal (convert to 0-indexed)
                for entry_num in remove_entries:
                    if 1 <= entry_num <= len(items):
                        row_idx, _ = items[entry_num - 1]
                        rows_to_remove.add(row_idx)
                
                time.sleep(1)  # Rate limiting
        except Exception as e:
            print(f"     ⚠️  Error checking duplicates: {e}")
            # If error, keep first entry, remove rest
            for idx, (row_idx, _) in enumerate(items[1:], 1):
                rows_to_remove.add(row_idx)
    
    # Remove duplicate rows
    if rows_to_remove:
        print(f"\n  🗑️  Removing {len(rows_to_remove)} duplicate entries")
        filtered_rows = [row for i, row in enumerate(rows) if i not in rows_to_remove]
        
        # Renumber IDs
        print(f"  🔢 Renumbering IDs...")
        for i, row in enumerate(filtered_rows, 1):
            row['id'] = i
        
        print(f"✅ Removed {len(rows) - len(filtered_rows)} duplicates, renumbered IDs\n")
        return filtered_rows
    
    return rows

def geocode_address(address: str, country: str = None, region: str = None) -> Tuple[Optional[float], Optional[float]]:
    """Geocode an address using OpenAI and geopy"""
    if not address or address.strip() in ['', 'NaN', 'null', 'None']:
        return None, None
    
    # Use OpenAI to format address
    context_parts = [f"Address: {address}"]
    if country:
        context_parts.append(f"Country: {country}")
    if region:
        context_parts.append(f"Region: {region}")
    
    prompt = f"""You are a geocoding assistant. Given the following address information, format it optimally for geocoding.

{chr(10).join(context_parts)}

Please return a JSON object with this format:
{{
    "formatted_address": "<optimally formatted address string>",
    "latitude": <latitude as number if you can determine it>,
    "longitude": <longitude as number if you can determine it>
}}

If you can determine the coordinates directly, provide them. Otherwise, format the address optimally for geocoding."""

    try:
        response = call_openai([{'role': 'user', 'content': prompt}])
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            data = json.loads(json_match.group(0))
            
            # Check if coordinates are provided directly
            lat = data.get('latitude')
            lon = data.get('longitude')
            if lat is not None and lon is not None:
                try:
                    return float(lat), float(lon)
                except (ValueError, TypeError):
                    pass
            
            # Otherwise, use geopy if available
            formatted_address = data.get('formatted_address', address)
            if geopy_available:
                try:
                    geolocator = Nominatim(user_agent="prefab_geocoder")
                    location = geolocator.geocode(formatted_address, timeout=15)
                    if location:
                        return location.latitude, location.longitude
                except (GeocoderTimedOut, GeocoderServiceError):
                    pass
                except Exception:
                    pass
        
        return None, None
    except Exception as e:
        print(f"  ⚠️  Error geocoding: {e}")
        return None, None

def investigate_webpage_and_extract_info(webpage: str, brand: str, company_name: str, country: str, language: str, existing_row: Dict) -> Dict:
    """Investigate webpage content and extract company information"""
    
    # Fetch webpage content
    print(f"  📄 Fetching webpage content...")
    webpage_content = fetch_webpage_content(webpage)
    
    if not webpage_content:
        print(f"  ⚠️  Could not fetch webpage content, using AI search only")
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

Webpage content (first 10000 chars):
{webpage_content[:10000] if webpage_content else 'Could not fetch webpage content - use your knowledge to search'}

Extract and fill in ALL available information. Return ONLY valid JSON in this exact format (use null for missing data, NaN for numeric fields that cannot be determined):

{{
  "brand": "brand name or trading name (the name customers know them by)",
  "head_office_legal_name": "full legal registered company name",
  "address": "complete address: street number, street name, city, postal code, country",
  "webpage": "main website homepage URL (https://...) - use the provided URL",
  "models_amount": number of different prefab home models/designs (integer),
  "min_sqm": minimum square meters of smallest model (number, living area),
  "max_sqm": maximum square meters of largest model (number, living area),
  "main_structure_material": "primary construction material: wood/timber/concrete/steel/composite/CLT/etc",
  "min_home_price": minimum starting price in local currency (number, base price without land),
  "average_price_sqm": average price per square meter in local currency (number)
}}

CRITICAL REQUIREMENTS:
- Use the provided webpage URL as the webpage value
- Extract information from the webpage content if available
- If webpage content is not available, use your knowledge to search for this company
- Only fill in fields where you can find reliable information
- For prices, use the local currency (do not convert)
- Be precise and factual
- Consider the local language ({language}) when interpreting information
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
                print(f"  ⚠️  Error parsing JSON: {e}")
                return {}
        return {}
    except Exception as e:
        print(f"  ⚠️  Error investigating webpage: {e}")
        return {}

def process_csv_file(csv_path: Path) -> None:
    """Process CSV file and fill requisites"""
    print(f"\n{'='*80}")
    print(f"📄 Processing: {csv_path.name}")
    print(f"{'='*80}\n")
    
    # Read CSV
    rows = []
    fieldnames = []
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows = list(reader)
    except Exception as e:
        print(f"❌ Error reading CSV: {e}")
        return
    
    print(f"✅ Loaded {len(rows)} rows\n")
    
    # Step 1: Verify company existence and find webpage (remove if not found)
    print(f"\n{'='*80}")
    print("Step 1: Verifying company existence and finding webpages")
    print(f"{'='*80}\n")
    
    verified_rows = []
    stats = {
        'total': len(rows),
        'verified_exists': 0,
        'removed_no_evidence': 0,
        'skipped_has_webpage': 0,
        'webpage_found': 0,
        'webpage_not_found': 0,
        'data_extracted': 0,
        'fields_filled': 0,
        'geocoded': 0
    }
    
    for i, row in enumerate(rows, 1):
        row_id = row.get('id', i)
        brand = row.get('brand', '').strip()
        company_name = row.get('head_office_legal_name', '').strip()
        webpage = row.get('webpage', '').strip()
        country = row.get('country', '').strip()
        country_code = row.get('country_code', '').strip()
        
        print(f"\n[{i}/{len(rows)}] Row {row_id}: {brand or company_name or 'Unknown'}")
        
        updated_row = row.copy()
        
        # Skip if webpage already exists
        if webpage and webpage not in ['', 'NaN', 'null', 'None']:
            print(f"  ⏭️  Skipping verification - webpage already exists: {webpage}")
            stats['skipped_has_webpage'] += 1
            verified_rows.append(updated_row)
            continue
        
        # Skip if no company name
        if not brand and not company_name:
            print(f"  ⏭️  Skipping - no company name")
            verified_rows.append(updated_row)
            continue
        
        # Get language for country
        language = get_language_for_country(country, country_code)
        print(f"  🌐 Language: {language}")
        
        # Verify company exists and find webpage
        print(f"  🔍 Verifying company existence and finding webpage...")
        exists, found_webpage = verify_company_exists(brand, company_name, country, language)
        
        if exists and found_webpage:
            print(f"  ✅ Company verified, webpage found: {found_webpage}")
            updated_row['webpage'] = found_webpage
            stats['verified_exists'] += 1
            stats['webpage_found'] += 1
            verified_rows.append(updated_row)
            time.sleep(2)  # Rate limiting
        else:
            print(f"  ❌ No proven evidence found - removing row")
            stats['removed_no_evidence'] += 1
            time.sleep(1)  # Rate limiting
    
    print(f"\n✅ Step 1 complete: {stats['verified_exists']} verified, {stats['removed_no_evidence']} removed\n")
    
    # Step 2: Deep search for remaining companies without webpages
    print(f"\n{'='*80}")
    print("Step 2: Deep searching for webpages")
    print(f"{'='*80}\n")
    
    updated_rows = []
    for i, row in enumerate(verified_rows, 1):
        row_id = row.get('id', i)
        brand = row.get('brand', '').strip()
        company_name = row.get('head_office_legal_name', '').strip()
        webpage = row.get('webpage', '').strip()
        country = row.get('country', '').strip()
        country_code = row.get('country_code', '').strip()
        
        print(f"\n[{i}/{len(verified_rows)}] Row {row_id}: {brand or company_name or 'Unknown'}")
        
        updated_row = row.copy()
        
        # Skip if webpage already exists
        if webpage and webpage not in ['', 'NaN', 'null', 'None']:
            print(f"  ⏭️  Skipping - webpage already exists: {webpage}")
            updated_rows.append(updated_row)
            continue
        
        # Get language for country
        language = get_language_for_country(country, country_code)
        print(f"  🌐 Language: {language}")
        
        # Deep search for webpage
        print(f"  🔍 Deep searching for webpage...")
        found_webpage = deep_search_webpage(brand, company_name, country, language)
        
        if found_webpage:
            print(f"  ✅ Found webpage: {found_webpage}")
            updated_row['webpage'] = found_webpage
            stats['webpage_found'] += 1
            
            # Step 2: Investigate webpage and extract information
            print(f"  🔬 Investigating webpage and extracting information...")
            extracted_data = investigate_webpage_and_extract_info(
                found_webpage, brand, company_name, country, language, updated_row
            )
            
            if extracted_data:
                fields_filled = 0
                for field, value in extracted_data.items():
                    if field in fieldnames and value is not None and value != 'NaN' and value != 'null':
                        # Only update if field is missing or empty
                        current_value = updated_row.get(field, '').strip()
                        if not current_value or current_value in ['', 'NaN', 'null', 'None']:
                            # Handle numeric conversions
                            if field in ['models_amount', 'min_sqm', 'max_sqm', 'min_home_price', 'average_price_sqm']:
                                try:
                                    if isinstance(value, (int, float)):
                                        updated_row[field] = value
                                    elif isinstance(value, str) and value.lower() not in ['null', 'nan', 'none', '']:
                                        updated_row[field] = float(value) if '.' in value else int(value)
                                    else:
                                        continue
                                except (ValueError, TypeError):
                                    continue
                            else:
                                updated_row[field] = value
                            
                            fields_filled += 1
                            print(f"    ✅ Filled {field}: {value}")
                
                if fields_filled > 0:
                    stats['data_extracted'] += 1
                    stats['fields_filled'] += fields_filled
            
            time.sleep(2)  # Rate limiting
        else:
            print(f"  ❌ Webpage not found")
            stats['webpage_not_found'] += 1
            time.sleep(1)  # Rate limiting
        
        updated_rows.append(updated_row)
        
        # Progress update every 10 rows
        if i % 10 == 0:
            print(f"\n💾 Progress: {i}/{len(verified_rows)} rows processed")
            print(f"   Stats: {stats['webpage_found']} webpages found, {stats['data_extracted']} rows enriched")
    
    # Step 3: Check for duplicate webpages and remove them
    print(f"\n{'='*80}")
    print("Step 3: Checking for duplicate webpages")
    print(f"{'='*80}\n")
    
    deduplicated_rows = check_duplicate_webpages(updated_rows)
    stats['duplicates_removed'] = len(updated_rows) - len(deduplicated_rows)
    
    # Step 4: Geocode addresses for rows without coordinates
    print(f"\n{'='*80}")
    print("Step 4: Geocoding addresses")
    print(f"{'='*80}\n")
    
    final_rows = []
    for i, row in enumerate(deduplicated_rows, 1):
        row_id = row.get('id', i)
        latitude = row.get('latitude', '').strip()
        longitude = row.get('longitude', '').strip()
        address = row.get('address', '').strip()
        country = row.get('country', '').strip()
        region = row.get('region', '').strip()
        
        updated_row = row.copy()
        
        # Check if coordinates are missing
        if (not latitude or latitude in ['', 'NaN', 'null', 'None'] or 
            not longitude or longitude in ['', 'NaN', 'null', 'None']):
            
            if address and address not in ['', 'NaN', 'null', 'None']:
                print(f"\n[{i}/{len(deduplicated_rows)}] Row {row_id}: Geocoding address...")
                lat, lon = geocode_address(address, country, region)
                
                if lat is not None and lon is not None:
                    updated_row['latitude'] = lat
                    updated_row['longitude'] = lon
                    stats['geocoded'] += 1
                    print(f"  ✅ Geocoded: {lat}, {lon}")
                    time.sleep(1)  # Rate limiting
                else:
                    print(f"  ⚠️  Could not geocode address")
        
        final_rows.append(updated_row)
    
    print(f"\n✅ Step 4 complete: {stats['geocoded']} addresses geocoded\n")
    
    # Save updated CSV with suffix _2
    output_csv = csv_path.parent / f"{csv_path.stem}_2.csv"
    print(f"\n💾 Saving results to: {output_csv.name}")
    
    try:
        with open(output_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in final_rows:
                csv_row = {}
                for key in fieldnames:
                    value = row.get(key)
                    if value is None or value == '':
                        csv_row[key] = 'NaN'
                    else:
                        csv_row[key] = value
                writer.writerow(csv_row)
        print(f"✅ Saved: {output_csv.name}\n")
    except Exception as e:
        print(f"❌ Error saving CSV: {e}\n")
    
    # Print summary
    print(f"\n{'='*80}")
    print("📊 Summary")
    print(f"{'='*80}")
    print(f"Total rows (initial): {stats['total']}")
    print(f"Companies verified: {stats['verified_exists']}")
    print(f"Rows removed (no evidence): {stats['removed_no_evidence']}")
    print(f"Skipped (has webpage): {stats['skipped_has_webpage']}")
    print(f"Webpages found: {stats['webpage_found']}")
    print(f"Webpages not found: {stats['webpage_not_found']}")
    print(f"Rows with data extracted: {stats['data_extracted']}")
    print(f"Total fields filled: {stats['fields_filled']}")
    print(f"Duplicates removed: {stats.get('duplicates_removed', 0)}")
    print(f"Addresses geocoded: {stats['geocoded']}")
    print(f"Final rows: {len(final_rows)}")
    print(f"{'='*80}\n")

def main():
    """Main function"""
    print('🚀 Starting deep search and requisites filling using OpenAI...\n')
    print(f"Using OpenAI API ({openai_config['name']})\n")
    
    # Input CSV file
    csv_path = Path(__file__).parent.parent / 'maps' / 'public' / 'prefabworldtest.csv'
    
    if not csv_path.exists():
        print(f"❌ CSV file not found: {csv_path}")
        return
    
    # Process CSV file
    try:
        process_csv_file(csv_path)
        print("🎉 Processing complete!")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
