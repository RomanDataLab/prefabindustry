#!/usr/bin/env python3
# Deep research of prefab home and structural panel companies in Luxembourg, Kazakhstan, Uzbekistan using OpenAI Deep Research
import sys
import os
import json
import csv
import time
import re
import requests
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
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

# Target countries
TARGET_COUNTRIES = [
    {'name': 'Luxembourg', 'code': 'LUX', 'language': 'French/German/Luxembourgish'},
    {'name': 'Kazakhstan', 'code': 'KAZ', 'language': 'Kazakh/Russian'},
    {'name': 'Uzbekistan', 'code': 'UZB', 'language': 'Uzbek/Russian'}
]

def call_openai(messages: List[Dict], max_retries: int = 3) -> str:
    """Call OpenAI API with retry logic"""
    for i in range(max_retries):
        try:
            response = openai_client.chat.completions.create(
                model='gpt-4.1',  # GPT-4.1 (Deep Research)
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

def search_companies_for_country(country: Dict, existing_webpages: Set[str]) -> List[Dict]:
    """Search for prefab home and structural panel companies in a specific country using OpenAI Deep Research"""
    country_name = country['name']
    country_code = country['code']
    language = country['language']
    
    print(f"\n{'='*80}")
    print(f"🔍 Searching for companies in {country_name} ({country_code})")
    print(f"{'='*80}\n")
    
    prompt = f"""You are conducting deep research to find ALL companies in {country_name} that manufacture:

1. Prefab/prefabricated homes
2. Modular homes
3. Structural panels for construction
4. Panelized construction systems
5. Off-site construction/prefabrication
6. Timber frame/prefab houses
7. Prefab panels/modules

Country: {country_name} ({country_code})
Language: {language}

Search comprehensively using your knowledge and web search capabilities. Find companies that:
- Manufacture prefabricated homes/buildings
- Produce structural panels (SIP panels, CLT panels, concrete panels, steel panels, etc.)
- Build modular/prefab homes
- Offer off-site construction solutions

For each company found, return a JSON array with company information. Each company object should have:
{{
  "company_name": "brand name or trading name",
  "legal_name": "full legal registered company name (if available)",
  "website": "company website URL (https://...)",
  "address": "complete address if available",
  "region": "region/state/province if available",
  "description": "brief description of what they manufacture"
}}

Return ONLY a JSON array of company objects, like this:
[
  {{"company_name": "...", "legal_name": "...", "website": "...", "address": "...", "region": "...", "description": "..."}},
  ...
]

If no companies are found, return: []

IMPORTANT:
- Search thoroughly and comprehensively
- Include all relevant companies, even small ones
- Verify website URLs are valid
- Return ONLY the JSON array, no explanations or markdown formatting"""

    try:
        print(f"  🤖 Using OpenAI Deep Research (GPT-4.1) to find companies...")
        response = call_openai([{'role': 'user', 'content': prompt}])
        
        # Extract JSON from response
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            companies = json.loads(json_match.group(0))
            print(f"  ✅ Found {len(companies)} companies")
            return companies
        else:
            print(f"  ⚠️  Could not parse JSON from response")
            return []
    except Exception as e:
        print(f"  ❌ Error searching companies: {e}")
        return []

def verify_company_webpage(company_url: str) -> Tuple[bool, Optional[str]]:
    """Verify that a company webpage is relevant (prefab/modular manufacturer)"""
    print(f"    🔍 Verifying webpage: {company_url}")
    
    webpage_content = fetch_webpage_content(company_url)
    
    prompt = f"""You are verifying if a company website is relevant for a database of prefab/modular home and structural panel manufacturers.

Company URL: {company_url}

Webpage content (first 20000 chars):
{webpage_content[:20000] if webpage_content else 'Could not fetch webpage content - use your knowledge to search'}

Determine if this company manufactures:
- Prefab/prefabricated homes
- Modular homes
- Panelized construction
- Off-site construction
- Timber frame/prefab houses
- Prefab panels/modules
- Structural panels (SIP, CLT, concrete, steel, etc.)

If YES, return a JSON object:
{{
  "relevant": true,
  "company_name": "company name or brand",
  "reason": "brief reason why it's relevant"
}}

If NO (not a prefab/modular/panel manufacturer), return:
{{
  "relevant": false,
  "reason": "brief reason why it's not relevant"
}}

Return ONLY the JSON object, no explanations."""

    try:
        response = call_openai([{'role': 'user', 'content': prompt}])
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            data = json.loads(json_match.group(0))
            is_relevant = data.get('relevant', False)
            if is_relevant:
                company_name = data.get('company_name', '')
                print(f"    ✅ Verified: {company_name}")
                return True, company_name
            else:
                reason = data.get('reason', 'Not a prefab manufacturer')
                print(f"    ❌ Not relevant: {reason}")
                return False, None
    except Exception as e:
        print(f"    ⚠️  Error verifying webpage: {e}")
    
    return False, None

def investigate_webpage_and_extract_info(webpage: str, company_name: str, country: Dict) -> Dict:
    """Investigate webpage content and extract comprehensive company information"""
    
    print(f"    📄 Fetching and analyzing webpage content...")
    webpage_content = fetch_webpage_content(webpage)
    
    country_name = country['name']
    country_code = country['code']
    language = country['language']
    
    prompt = f"""You are conducting deep research on a prefab/modular home or structural panel company's website to extract ALL available information.

Company name: {company_name or 'Unknown'}
Website URL: {webpage}
Country: {country_name} ({country_code})
Language: {language}

Webpage content (first 20000 chars):
{webpage_content[:20000] if webpage_content else 'Could not fetch webpage content - use your knowledge and web search to find information'}

Extract and fill in ALL available information. Return ONLY valid JSON in this exact format (use null for missing data, NaN for numeric fields that cannot be determined):

{{
  "brand": "brand name or trading name (the name customers know them by)",
  "head_office_legal_name": "full legal registered company name",
  "address": "complete address: street number, street name, city, postal code, country",
  "country": "{country_name}",
  "country_code": "{country_code}",
  "region": "state/province/region name",
  "webpage": "{webpage}",
  "models_amount": number of different prefab home models/designs (integer or null),
  "min_sqm": minimum square meters of smallest model (number or null, living area),
  "max_sqm": maximum square meters of largest model (number or null, living area),
  "main_structure_material": "primary construction material: wood/timber/concrete/steel/composite/CLT/SIP/etc",
  "min_home_price": minimum starting price in local currency (number or null, base price without land),
  "average_price_sqm": average price per square meter in local currency (number or null)
}}

CRITICAL REQUIREMENTS:
- Use the provided webpage URL as the webpage value
- Extract information from the webpage content if available
- If webpage content is not available, use your knowledge and web search to find information about this company
- Only fill in fields where you can find reliable information
- For prices, use the local currency (do not convert)
- Be precise and factual
- Consider the local language ({language}) when interpreting information
- Search thoroughly for all available data
- Return ONLY the JSON object, no explanations or markdown formatting"""

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

def double_check_structure_material(webpage: str, initial_material: str, company_name: str) -> str:
    """Double-check the main structure material by analyzing overall webpage content"""
    print(f"    🔬 Double-checking structure material: {initial_material}")
    
    webpage_content = fetch_webpage_content(webpage)
    
    prompt = f"""You are verifying the main structure material for a prefab/modular home or structural panel manufacturer.

Company: {company_name}
Website: {webpage}
Initial assessment: {initial_material}

Webpage content (first 20000 chars):
{webpage_content[:20000] if webpage_content else 'Could not fetch webpage content - use your knowledge to search'}

Analyze the overall company webpage content AND descriptions of house models/products to determine the PRIMARY construction material used.

Look for:
- Material mentions throughout the website
- House model descriptions and specifications
- Construction method descriptions
- Product catalogs and technical details
- About us / technology sections

Possible materials:
- wood / timber
- concrete
- steel
- composite
- CLT (Cross-Laminated Timber)
- SIP (Structural Insulated Panels)
- other

Return ONLY a JSON object:
{{
  "main_structure_material": "the primary material (wood/timber/concrete/steel/composite/CLT/etc)",
  "confidence": "high/medium/low",
  "reasoning": "brief explanation of why this material was chosen"
}}

Return ONLY the JSON object, no explanations."""

    try:
        response = call_openai([{'role': 'user', 'content': prompt}])
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            data = json.loads(json_match.group(0))
            verified_material = data.get('main_structure_material', initial_material)
            confidence = data.get('confidence', 'medium')
            reasoning = data.get('reasoning', '')
            print(f"    ✅ Verified material: {verified_material} (confidence: {confidence})")
            if reasoning:
                print(f"       Reasoning: {reasoning}")
            return verified_material
    except Exception as e:
        print(f"    ⚠️  Error double-checking material: {e}")
    
    return initial_material

def geocode_address(address: str, country: str = None, region: str = None) -> Tuple[Optional[float], Optional[float]]:
    """Geocode an address using OpenAI and geopy"""
    if not address or address.strip() in ['', 'NaN', 'null', 'None']:
        return None, None
    
    # Use OpenAI to format address and get coordinates
    context_parts = [f"Address: {address}"]
    if country:
        context_parts.append(f"Country: {country}")
    if region:
        context_parts.append(f"Region: {region}")
    
    prompt = f"""You are a geocoding assistant. Given the following address information, format it optimally for geocoding and provide coordinates if possible.

{chr(10).join(context_parts)}

Please return a JSON object with this format:
{{
    "formatted_address": "<optimally formatted address string>",
    "latitude": <latitude as number if you can determine it>,
    "longitude": <longitude as number if you can determine it>
}}

If you can determine the coordinates directly, provide them. Otherwise, format the address optimally for geocoding.

Return ONLY the JSON object, no explanations."""

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

def check_company_exists(company_url: str, existing_webpages: Set[str]) -> bool:
    """Check if company already exists in the database"""
    # Normalize URL for comparison
    normalized_url = company_url.lower().rstrip('/')
    normalized_url = normalized_url.replace('http://', 'https://')
    
    # Check exact match
    if normalized_url in existing_webpages:
        return True
    
    # Check domain match (without www)
    domain = urlparse(normalized_url).netloc.lower()
    domain = domain.replace('www.', '')
    for existing_url in existing_webpages:
        existing_domain = urlparse(existing_url.lower()).netloc.lower().replace('www.', '')
        if existing_domain == domain:
            return True
    
    return False

def load_existing_companies(csv_path: Path) -> Set[str]:
    """Load existing company webpages from CSV"""
    existing_webpages = set()
    
    if not csv_path.exists():
        return existing_webpages
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                webpage = row.get('webpage', '').strip()
                if webpage and webpage not in ['', 'NaN', 'null', 'None']:
                    normalized = webpage.lower().rstrip('/').replace('http://', 'https://')
                    existing_webpages.add(normalized)
    except Exception as e:
        print(f"  ⚠️  Error loading existing companies: {e}")
    
    return existing_webpages

def get_next_id(output_csv: Path) -> int:
    """Get the next ID for a new entry"""
    if not output_csv.exists():
        return 1
    
    try:
        with open(output_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            max_id = 0
            for row in reader:
                try:
                    row_id = int(row.get('id', 0))
                    max_id = max(max_id, row_id)
                except (ValueError, TypeError):
                    pass
            return max_id + 1
    except Exception as e:
        print(f"  ⚠️  Error getting next ID: {e}")
        return 1

def save_company_incrementally(company_data: Dict, output_csv: Path, fieldnames: List[str]) -> None:
    """Save a company entry incrementally to CSV"""
    # Ensure output directory exists
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    
    # Check if file exists and get headers
    file_exists = output_csv.exists()
    
    try:
        # Append mode
        with open(output_csv, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            # Write header if file is new
            if not file_exists:
                writer.writeheader()
            
            # Prepare row
            csv_row = {}
            for key in fieldnames:
                value = company_data.get(key)
                if value is None or value == '':
                    csv_row[key] = 'NaN'
                else:
                    csv_row[key] = value
            
            writer.writerow(csv_row)
            print(f"    💾 Saved to {output_csv.name}")
    except Exception as e:
        print(f"    ❌ Error saving company: {e}")

def main():
    """Main function"""
    print('🚀 Starting deep research of prefab home and structural panel companies')
    print(f"   Target countries: {', '.join([c['name'] for c in TARGET_COUNTRIES])}")
    print(f"   Using OpenAI API ({openai_config['name']}) - GPT-4.1 Deep Research model\n")
    
    # Input/output files
    existing_companies_csv = Path(__file__).parent.parent / 'maps' / 'public' / 'prefabworldtest_2.csv'
    output_csv = Path(__file__).parent.parent / 'maps' / 'public' / 'prefabassociated.csv'
    
    # Load existing companies
    print(f"📋 Loading existing companies from {existing_companies_csv.name}...")
    existing_webpages = load_existing_companies(existing_companies_csv)
    print(f"✅ Found {len(existing_webpages)} existing companies\n")
    
    # Define CSV fieldnames
    fieldnames = [
        'id', 'brand', 'head_office_legal_name', 'address', 'country', 'country_code', 
        'region', 'webpage', 'configurator', 'models_amount', 'min_sqm', 'max_sqm', 
        'main_structure_material', 'min_home_price', 'average_price_sqm', 
        'latitude', 'longitude'
    ]
    
    # Get next ID
    next_id = get_next_id(output_csv)
    
    stats = {
        'countries_processed': 0,
        'companies_found': 0,
        'companies_verified': 0,
        'companies_existing': 0,
        'companies_new': 0,
        'companies_saved': 0,
        'geocoded': 0
    }
    
    # Process each country
    for country in TARGET_COUNTRIES:
        print(f"\n{'='*80}")
        print(f"Processing: {country['name']} ({country['code']})")
        print(f"{'='*80}\n")
        
        # Search for companies using OpenAI Deep Research
        companies = search_companies_for_country(country, existing_webpages)
        stats['companies_found'] += len(companies)
        
        if not companies:
            print(f"  ⚠️  No companies found for {country['name']}")
            time.sleep(2)
            continue
        
        stats['countries_processed'] += 1
        
        # Process each company
        for j, company_info in enumerate(companies, 1):
            company_url = company_info.get('website', '').strip()
            company_name = company_info.get('company_name', 'Unknown')
            
            if not company_url or not company_url.startswith(('http://', 'https://')):
                print(f"\n  [{j}/{len(companies)}] ⚠️  Skipping invalid URL: {company_url}")
                continue
            
            print(f"\n  [{j}/{len(companies)}] Company: {company_name}")
            print(f"      URL: {company_url}")
            
            # Check if company already exists
            if check_company_exists(company_url, existing_webpages):
                print(f"    ⏭️  Company already exists in database")
                stats['companies_existing'] += 1
                time.sleep(1)
                continue
            
            # Verify webpage relevance
            is_relevant, verified_name = verify_company_webpage(company_url)
            if not is_relevant:
                time.sleep(2)
                continue
            
            stats['companies_verified'] += 1
            
            # Use verified name if available
            if verified_name:
                company_name = verified_name
            
            # Investigate webpage and extract comprehensive information
            print(f"    🔬 Extracting comprehensive company data...")
            extracted_data = investigate_webpage_and_extract_info(company_url, company_name, country)
            
            if not extracted_data:
                print(f"    ⚠️  Could not extract company data")
                time.sleep(2)
                continue
            
            # Ensure webpage URL is set
            extracted_data['webpage'] = company_url
            
            # Double-check structure material
            initial_material = extracted_data.get('main_structure_material', '')
            if initial_material:
                verified_material = double_check_structure_material(
                    company_url, initial_material, company_name
                )
                extracted_data['main_structure_material'] = verified_material
            
            # Geocode address
            address = extracted_data.get('address', '')
            country_name = extracted_data.get('country', '')
            region = extracted_data.get('region', '')
            
            latitude = None
            longitude = None
            
            if address and address not in ['', 'NaN', 'null', 'None']:
                print(f"    📍 Geocoding address...")
                latitude, longitude = geocode_address(address, country_name, region)
                if latitude and longitude:
                    extracted_data['latitude'] = latitude
                    extracted_data['longitude'] = longitude
                    stats['geocoded'] += 1
                    print(f"    ✅ Geocoded: {latitude}, {longitude}")
                else:
                    extracted_data['latitude'] = 'NaN'
                    extracted_data['longitude'] = 'NaN'
            else:
                extracted_data['latitude'] = 'NaN'
                extracted_data['longitude'] = 'NaN'
            
            # Set ID
            extracted_data['id'] = next_id
            next_id += 1
            
            # Set configurator to NaN
            extracted_data['configurator'] = 'NaN'
            
            # Handle numeric fields
            for field in ['models_amount', 'min_sqm', 'max_sqm', 'min_home_price', 'average_price_sqm']:
                value = extracted_data.get(field)
                if value is None or value == 'null' or value == 'NaN':
                    extracted_data[field] = 'NaN'
                elif isinstance(value, (int, float)):
                    extracted_data[field] = value
                else:
                    try:
                        extracted_data[field] = float(value) if '.' in str(value) else int(value)
                    except (ValueError, TypeError):
                        extracted_data[field] = 'NaN'
            
            # Save incrementally
            print(f"    💾 Saving company data...")
            save_company_incrementally(extracted_data, output_csv, fieldnames)
            
            # Add to existing webpages set to avoid duplicates
            normalized_url = company_url.lower().rstrip('/').replace('http://', 'https://')
            existing_webpages.add(normalized_url)
            
            stats['companies_new'] += 1
            stats['companies_saved'] += 1
            
            print(f"    ✅ Company saved successfully!")
            
            time.sleep(3)  # Rate limiting between companies
        
        # Progress update
        print(f"\n💾 Progress: {stats['countries_processed']}/{len(TARGET_COUNTRIES)} countries processed")
        print(f"   Stats: {stats['companies_saved']} companies saved, {stats['companies_existing']} already existed")
        time.sleep(2)  # Rate limiting between countries
    
    # Print summary
    print(f"\n{'='*80}")
    print("📊 Summary")
    print(f"{'='*80}")
    print(f"Countries processed: {stats['countries_processed']}")
    print(f"Companies found: {stats['companies_found']}")
    print(f"Companies verified: {stats['companies_verified']}")
    print(f"Companies already existing: {stats['companies_existing']}")
    print(f"New companies found: {stats['companies_new']}")
    print(f"Companies saved: {stats['companies_saved']}")
    print(f"Addresses geocoded: {stats['geocoded']}")
    print(f"Output file: {output_csv.name}")
    print(f"{'='*80}\n")
    
    print("🎉 Processing complete!")

if __name__ == '__main__':
    main()
