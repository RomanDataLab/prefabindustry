#!/usr/bin/env python3
# Enrich company data with type, visualization images, and layout plans using Gemini Deep Research
import sys
import os
import json
import csv
import time
import re
import requests
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse, urljoin
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
    from google import genai
except ImportError:
    print("Error: google-genai package not installed. Run: pip install google-genai")
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

# Initialize Gemini with API key from configix
gemini_config = get_ai_provider('ai_gemini')
gemini_client = genai.Client(api_key=gemini_config['api_key'])

# Cache for available models
_available_models_cache = None

def get_available_gemini_models_via_api():
    """Get list of available Gemini models using REST API ListModels endpoint"""
    global _available_models_cache
    if _available_models_cache is None:
        api_key = gemini_config['api_key']
        try:
            # Call ListModels API endpoint
            list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
            response = requests.get(list_url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                models = []
                if 'models' in data:
                    for model in data['models']:
                        model_name = model.get('name', '')
                        # Extract just the model name (e.g., "models/gemini-1.5-flash" -> "gemini-1.5-flash")
                        if '/' in model_name:
                            model_name = model_name.split('/')[-1]
                        
                        # Check if model supports generateContent
                        supported_methods = model.get('supportedGenerationMethods', [])
                        if 'generateContent' in supported_methods:
                            models.append(model_name)
                
                if models:
                    _available_models_cache = models
                    print(f"  📋 Found {len(models)} available Gemini models: {', '.join(models[:5])}...")
                else:
                    print(f"  ⚠️  No models found with generateContent support")
                    _available_models_cache = []
            else:
                print(f"  ⚠️  ListModels API returned {response.status_code}: {response.text[:200]}")
                _available_models_cache = []
        except Exception as e:
            print(f"  ⚠️  Could not list models via API: {e}")
            _available_models_cache = []
    
    return _available_models_cache if _available_models_cache else []

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

def call_gemini_deep_research(prompt: str, max_retries: int = 3, max_wait_time: int = 300) -> str:
    """Call Gemini API for deep research using REST API directly"""
    api_key = gemini_config['api_key']
    
    # Get available models from ListModels API first
    available_models = get_available_gemini_models_via_api()
    
    if not available_models:
        # If ListModels failed, try common model names as fallback
        print(f"  ⚠️  Could not get models from API, using fallback list...")
        available_models = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro', 'gemini-2.0-flash-exp']
    
    # Build model configs with v1beta API endpoint
    model_configs = []
    for model_name in available_models:
        model_configs.append({
            'name': model_name,
            'url': f'https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent'
        })
    
    if not model_configs:
        raise Exception("No available models found. Please check your API key and permissions.")
    
    for attempt in range(max_retries):
        for model_config in model_configs:
            try:
                print(f"  🤖 Starting Gemini Deep Research (attempt {attempt + 1}/{max_retries}) with {model_config['name']}...")
                
                # Use REST API directly
                url = model_config['url']
                headers = {
                    'Content-Type': 'application/json',
                }
                payload = {
                    'contents': [{
                        'parts': [{
                            'text': prompt
                        }]
                    }],
                    'generationConfig': {
                        'temperature': 0.7,
                        'maxOutputTokens': 8000,
                    }
                }
                
                response = requests.post(
                    f"{url}?key={api_key}",
                    headers=headers,
                    json=payload,
                    timeout=120
                )
                
                if response.status_code == 200:
                    result_data = response.json()
                    if 'candidates' in result_data and len(result_data['candidates']) > 0:
                        if 'content' in result_data['candidates'][0]:
                            parts = result_data['candidates'][0]['content'].get('parts', [])
                            if parts and 'text' in parts[0]:
                                result = parts[0]['text']
                                print(f"  ✅ Research completed with {model_config['name']}")
                                return result
                    
                    # Fallback: try to extract text from response
                    result = json.dumps(result_data)
                    print(f"  ✅ Research completed with {model_config['name']} (raw response)")
                    return result
                elif response.status_code == 404:
                    # Model not found, try next model
                    if model_config != model_configs[-1]:
                        print(f"  ⚠️  Model {model_config['name']} not found (404), trying next...")
                        continue
                    else:
                        print(f"  ⚠️  All models returned 404. Last response: {response.text[:200]}")
                        # Refresh model list and retry
                        if attempt == 0:
                            print(f"  🔄 Refreshing model list...")
                            global _available_models_cache
                            _available_models_cache = None
                            available_models = get_available_gemini_models_via_api()
                            if available_models:
                                model_configs.clear()
                                for model_name in available_models:
                                    model_configs.append({
                                        'name': model_name,
                                        'url': f'https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent'
                                    })
                                continue
                        raise Exception(f"All models not found. Last error: {response.text[:200]}")
                else:
                    error_text = response.text[:500] if hasattr(response, 'text') else str(response.status_code)
                    raise Exception(f"API error {response.status_code}: {error_text}")
                    
            except requests.exceptions.RequestException as req_error:
                error_str = str(req_error).lower()
                
                # Rate limit - retry with backoff
                if any(keyword in error_str for keyword in ['rate limit', 'quota', '429', 'resource_exhausted', 'too many requests']):
                    backoff_time = min(60 * (attempt + 1), 300)  # Max 5 minutes
                    print(f"  ⚠️  Rate limit hit. Waiting {backoff_time}s...")
                    if attempt < max_retries - 1:
                        time.sleep(backoff_time)
                        break  # Break out of model loop, retry attempt
                    else:
                        raise Exception(f"Rate limit exceeded: {req_error}")
                
                # If not the last model, try next
                if model_config != model_configs[-1]:
                    print(f"  ⚠️  Error with {model_config['name']}: {req_error}, trying next model...")
                    continue
                else:
                    # Last model failed
                    if attempt == max_retries - 1:
                        raise Exception(f"All models failed. Last error: {req_error}")
                    continue
                    
            except Exception as error:
                error_str = str(error).lower()
                
                # Rate limit - retry with backoff
                if any(keyword in error_str for keyword in ['rate limit', 'quota', '429', 'resource_exhausted', 'too many requests']):
                    backoff_time = min(60 * (attempt + 1), 300)  # Max 5 minutes
                    print(f"  ⚠️  Rate limit hit. Waiting {backoff_time}s...")
                    if attempt < max_retries - 1:
                        time.sleep(backoff_time)
                        break
                    else:
                        raise Exception(f"Rate limit exceeded: {error}")
                
                # If not the last model, try next
                if model_config != model_configs[-1]:
                    print(f"  ⚠️  Error with {model_config['name']}: {error}, trying next model...")
                    continue
                else:
                    if attempt == max_retries - 1:
                        raise
                    continue
        
        # If we get here, all models failed for this attempt
        print(f"  ⚠️  Attempt {attempt + 1}/{max_retries} failed with all models")
        if attempt == max_retries - 1:
            raise Exception("All retry attempts failed with all available models")
        time.sleep(2 * (attempt + 1))
    
    raise Exception("All retry attempts failed")

def fetch_webpage_content(url: str, timeout: int = 15) -> Tuple[Optional[str], List[str]]:
    """Fetch webpage content and return text and image URLs"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, timeout=timeout, headers=headers, allow_redirects=True)
        response.raise_for_status()
        
        # Parse HTML and extract text
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract image URLs before removing elements
        image_urls = []
        for img in soup.find_all('img'):
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src') or img.get('data-original')
            if src:
                # Convert relative URLs to absolute
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    src = urljoin(url, src)
                elif not src.startswith('http'):
                    src = urljoin(url, src)
                
                # Filter out very small images and common non-content images
                if src not in image_urls:
                    # Skip common non-content images
                    skip_patterns = ['logo', 'icon', 'button', 'arrow', 'badge', 'social']
                    img_alt = (img.get('alt') or '').lower()
                    if not any(pattern in img_alt for pattern in skip_patterns):
                        image_urls.append(src)
        
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
        return text[:20000], image_urls[:50]  # Return up to 50 image URLs
    except Exception as e:
        print(f"  ⚠️  Error fetching webpage: {e}")
        return None, []

def find_images_on_page(url: str, image_type: str = 'facade') -> List[str]:
    """Find images on webpage (facade or layout)"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, timeout=15, headers=headers, allow_redirects=True)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        images = []
        
        # Find all img tags
        for img in soup.find_all('img'):
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if src:
                # Convert relative URLs to absolute
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    src = urljoin(url, src)
                elif not src.startswith('http'):
                    src = urljoin(url, src)
                
                # Filter by image type keywords
                img_alt = (img.get('alt') or '').lower()
                img_class = (img.get('class') or [])
                img_class_str = ' '.join(img_class).lower() if isinstance(img_class, list) else str(img_class).lower()
                
                if image_type == 'facade':
                    keywords = ['facade', 'exterior', 'outside', 'front', 'house', 'home', 'building', 'model']
                else:  # layout
                    keywords = ['layout', 'plan', 'floor', 'interior', 'design', 'blueprint', 'scheme']
                
                # Check if image matches type
                if any(keyword in img_alt or keyword in img_class_str for keyword in keywords):
                    if src not in images and src.endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
                        images.append(src)
        
        return images[:5]  # Return up to 5 images
    except Exception as e:
        print(f"  ⚠️  Error finding images: {e}")
        return []

def convert_sqf_to_sqm(sqf: float) -> float:
    """Convert square feet to square meters"""
    return sqf * 0.092903

def convert_currency_to_eur(amount: float, currency: str) -> float:
    """Convert currency to EUR (simplified - would need actual exchange rates)"""
    # Common currency conversions (approximate)
    conversions = {
        'USD': 0.92, 'EUR': 1.0, 'GBP': 1.17, 'CAD': 0.68,
        'AUD': 0.61, 'CHF': 1.02, 'JPY': 0.0061, 'CNY': 0.13,
        'BRL': 0.18, 'MXN': 0.054, 'INR': 0.011, 'RUB': 0.010,
        'ZAR': 0.050, 'SEK': 0.088, 'NOK': 0.086, 'DKK': 0.13,
        'PLN': 0.23, 'CZK': 0.040, 'HUF': 0.0026, 'RON': 0.20
    }
    currency_upper = currency.upper()
    if currency_upper in conversions:
        return amount * conversions[currency_upper]
    return amount  # Return as-is if unknown currency

def investigate_webpage_and_extract_info(webpage: str, brand: str, company_name: str, country: str, language: str, existing_row: Dict) -> Dict:
    """Investigate webpage and extract company information using deep search"""
    
    # Fetch webpage content and image URLs
    webpage_content, image_urls = fetch_webpage_content(webpage)
    
    # Format image URLs for prompt
    image_urls_text = '\n'.join(image_urls[:50]) if image_urls else 'No images found on page'
    
    prompt = f"""You are analyzing a prefab/modular building company's website to extract detailed information.

Company Information:
- Brand: {brand or 'Unknown'}
- Legal Name: {company_name or 'Unknown'}
- Country: {country or 'Unknown'}
- Website: {webpage}
- Language: {language}

Current Data:
- Models Amount: {existing_row.get('models_amount', 'NaN')}
- Min SQM: {existing_row.get('min_sqm', 'NaN')}
- Max SQM: {existing_row.get('max_sqm', 'NaN')}
- Main Structure Material: {existing_row.get('main_structure_material', 'NaN')}
- Min Home Price: {existing_row.get('min_home_price', 'NaN')}
- Average Price per SQM: {existing_row.get('average_price_sqm', 'NaN')}

Webpage Content (first 20000 chars):
{webpage_content[:20000] if webpage_content else 'Could not fetch webpage content'}

Image URLs found on the webpage (use these to identify facade and layout images):
{image_urls_text}

TASKS:
1. Identify the TYPE of buildings the company produces:
   - If they produce residential homes → return "home"
   - If they produce industrial/commercial buildings → return "industrial"
   - If they produce panels (SIP, CLT, concrete panels, etc.) → return "panels"
   - If multiple types, prioritize: home > industrial > panels

2. If TYPE = "home":
   a. Count the number of distinct home models offered → update models_amount
   b. Find the MINIMAL size in square meters (convert from sqf if needed: 1 sqf = 0.092903 sqm) → update min_sqm
   c. Find the MAXIMUM size in square meters (convert from sqf if needed) → update max_sqm
   d. Find the MINIMAL home price in EURO (convert from local currency if needed) → update min_home_price
   e. Calculate the MEDIAN home price per sqm in EURO:
      - Consider all main models in the range
      - Convert sqf to sqm if needed
      - Convert local currency to EURO if needed
      - Calculate: (price / sqm) for each model, then find median → update average_price_sqm

3. If main_structure_material is "NaN" or null or empty:
   - Identify the main structure material (steel, concrete, wood, panels, etc.) → update main_structure_material

4. Find 5 facade/exterior images:
   - Look for images showing home exteriors, facades, front views, building exteriors
   - Use the Image URLs list above to identify relevant images
   - You can also extract image URLs mentioned in the webpage content
   - Return full URLs (absolute paths) as JSON array
   - If fewer than 5 found, return what you can find

5. Find 5 layout/floor plan images:
   - Look for images showing floor plans, layouts, blueprints, interior designs, architectural plans
   - Use the Image URLs list above to identify relevant images
   - You can also extract image URLs mentioned in the webpage content
   - Return full URLs (absolute paths) as JSON array
   - If fewer than 5 found, return what you can find

Return ONLY a JSON object with this exact structure:
{{
  "type": "home" | "industrial" | "panels",
  "models_amount": number or null,
  "min_sqm": number or null,
  "max_sqm": number or null,
  "main_structure_material": "steel" | "concrete" | "wood" | "panels" | etc. or null,
  "min_home_price": number (in EUR) or null,
  "average_price_sqm": number (in EUR per sqm) or null,
  "viz": ["url1", "url2", "url3", "url4", "url5"],
  "plans": ["url1", "url2", "url3", "url4", "url5"]
}}

IMPORTANT:
- Only update fields that you can find reliable information for
- Keep existing values if you cannot find better information
- For prices: convert to EURO (use approximate exchange rates if needed)
- For sizes: convert sqf to sqm (1 sqf = 0.092903 sqm)
- Return ONLY the JSON object, no explanations or markdown formatting
- If you cannot find information, use null for that field
- For images, return full absolute URLs"""

    try:
        response = call_gemini_deep_research(prompt)
        
        # Extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                return data
            except json.JSONDecodeError as e:
                print(f"  ⚠️  Error parsing JSON: {e}")
                print(f"  Response: {response[:500]}")
                return {}
        return {}
    except Exception as e:
        print(f"  ⚠️  Error investigating webpage: {e}")
        return {}

def process_csv_file(csv_path: Path, output_path: Path, start_row: int = 1) -> None:
    """Process CSV file and enrich with company data"""
    
    print(f"\n📊 Processing CSV: {csv_path}")
    print(f"💾 Output file: {output_path}")
    print(f"🚀 Starting from row: {start_row}\n")
    
    # Read input CSV
    rows = []
    fieldnames = None
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    
    # Add new columns if they don't exist
    new_columns = ['type', 'viz', 'plans']
    if fieldnames:
        for col in new_columns:
            if col not in fieldnames:
                fieldnames = list(fieldnames) + [col]
    
    # Load existing output file if it exists to preserve previous data
    if output_path.exists():
        print(f"📂 Loading existing output file: {output_path}")
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                existing_reader = csv.DictReader(f)
                existing_rows = list(existing_reader)
                # Update rows with existing data up to start_row
                for i, existing_row in enumerate(existing_rows[:start_row-1], 1):
                    if i <= len(rows):
                        # Preserve existing data
                        for key in existing_row:
                            if key in rows[i-1]:
                                rows[i-1][key] = existing_row[key]
                print(f"   ✅ Loaded {len(existing_rows)} existing rows")
        except Exception as e:
            print(f"   ⚠️  Could not load existing file: {e}")
    
    print(f"📋 Total rows in input: {len(rows)}")
    print(f"📋 Rows to process: {len(rows) - start_row + 1} (from row {start_row} to {len(rows)})\n")
    
    # Process each row
    processed_count = 0
    
    for idx, row in enumerate(rows, 1):
        # Skip rows before start_row
        if idx < start_row:
            continue
        webpage = row.get('webpage', '').strip()
        brand = row.get('brand', '').strip()
        company_name = row.get('head_office_legal_name', '').strip()
        country = row.get('country', '').strip()
        country_code = row.get('country_code', '').strip()
        
        # Skip if no webpage
        if not webpage or webpage.lower() in ['nan', 'none', '']:
            print(f"⏭️  Row {idx}/{len(rows)}: {brand} - No webpage, skipping")
            # Initialize new columns
            if 'type' not in row:
                row['type'] = ''
            if 'viz' not in row:
                row['viz'] = ''
            if 'plans' not in row:
                row['plans'] = ''
            continue
        
        print(f"\n🔍 Row {idx}/{len(rows)}: {brand}")
        print(f"   Webpage: {webpage}")
        
        # Get language
        language = get_language_for_country(country, country_code)
        
        # Investigate webpage
        try:
            extracted_data = investigate_webpage_and_extract_info(
                webpage, brand, company_name, country, language, row
            )
            
            # Update row with extracted data
            if 'type' in extracted_data:
                row['type'] = extracted_data['type'] or ''
                print(f"   ✅ Type: {row['type']}")
            
            if extracted_data.get('type') == 'home':
                # Update models_amount
                if 'models_amount' in extracted_data and extracted_data['models_amount'] is not None:
                    row['models_amount'] = str(extracted_data['models_amount'])
                    print(f"   ✅ Models Amount: {row['models_amount']}")
                
                # Update min_sqm
                if 'min_sqm' in extracted_data and extracted_data['min_sqm'] is not None:
                    row['min_sqm'] = str(extracted_data['min_sqm'])
                    print(f"   ✅ Min SQM: {row['min_sqm']}")
                
                # Update max_sqm
                if 'max_sqm' in extracted_data and extracted_data['max_sqm'] is not None:
                    row['max_sqm'] = str(extracted_data['max_sqm'])
                    print(f"   ✅ Max SQM: {row['max_sqm']}")
                
                # Update min_home_price
                if 'min_home_price' in extracted_data and extracted_data['min_home_price'] is not None:
                    row['min_home_price'] = str(extracted_data['min_home_price'])
                    print(f"   ✅ Min Home Price: {row['min_home_price']} EUR")
                
                # Update average_price_sqm
                if 'average_price_sqm' in extracted_data and extracted_data['average_price_sqm'] is not None:
                    row['average_price_sqm'] = str(extracted_data['average_price_sqm'])
                    print(f"   ✅ Average Price per SQM: {row['average_price_sqm']} EUR")
            
            # Update main_structure_material if NaN or null
            current_material = row.get('main_structure_material', '').strip().lower()
            if current_material in ['nan', 'none', '', 'null']:
                if 'main_structure_material' in extracted_data and extracted_data['main_structure_material']:
                    row['main_structure_material'] = extracted_data['main_structure_material']
                    print(f"   ✅ Main Structure Material: {row['main_structure_material']}")
            
            # Update viz (facade images)
            if 'viz' in extracted_data and extracted_data['viz']:
                viz_list = extracted_data['viz']
                if isinstance(viz_list, list):
                    row['viz'] = json.dumps(viz_list, ensure_ascii=False)
                    print(f"   ✅ Found {len(viz_list)} facade images")
                else:
                    row['viz'] = ''
            else:
                row['viz'] = ''
            
            # Update plans (layout images)
            if 'plans' in extracted_data and extracted_data['plans']:
                plans_list = extracted_data['plans']
                if isinstance(plans_list, list):
                    row['plans'] = json.dumps(plans_list, ensure_ascii=False)
                    print(f"   ✅ Found {len(plans_list)} layout images")
                else:
                    row['plans'] = ''
            else:
                row['plans'] = ''
            
            processed_count += 1
            
        except Exception as e:
            print(f"   ❌ Error processing row: {e}")
            # Initialize new columns with empty values
            if 'type' not in row:
                row['type'] = ''
            if 'viz' not in row:
                row['viz'] = ''
            if 'plans' not in row:
                row['plans'] = ''
        
        # Save incrementally every 5 rows
        if (idx - start_row + 1) % 5 == 0:
            print(f"\n💾 Saving progress (rows 1-{idx})...")
            with open(output_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows[:idx])
            print(f"   ✅ Saved {idx} rows to {output_path}\n")
        
        # Small delay to avoid rate limits
        time.sleep(1)
    
    # Final save
    print(f"\n💾 Final save...")
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"\n✅ Processing complete!")
    print(f"   Processed: {processed_count} rows")
    print(f"   Total rows: {len(rows)}")
    print(f"   Output saved to: {output_path}\n")

def main():
    """Main function"""
    # Set up paths
    script_dir = Path(__file__).parent
    maps_dir = script_dir.parent / 'maps' / 'public'
    input_csv = maps_dir / 'prefabworldtest_2.csv'
    output_csv = maps_dir / 'prefabworldfin.csv'
    
    if not input_csv.exists():
        print(f"❌ Error: Input file not found: {input_csv}")
        sys.exit(1)
    
    # Get start row from startrow.py
    try:
        from startrow import DEFAULT_START_ROW
        start_row = DEFAULT_START_ROW
    except ImportError:
        # Fallback if startrow.py is not available
        start_row = 184
    
    # Process CSV starting from the specified row
    process_csv_file(input_csv, output_csv, start_row=start_row)

if __name__ == '__main__':
    main()
