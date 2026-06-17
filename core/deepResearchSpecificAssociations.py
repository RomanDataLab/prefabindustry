#!/usr/bin/env python3
# Deep research of companies from specific association member directories with custom scraping
import sys
import os
import json
import csv
import time
import re
import requests
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from urllib.parse import urlparse, urljoin, urlunparse, parse_qs
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
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        webdriver_manager_available = True
    except ImportError:
        webdriver_manager_available = False
    selenium_available = True
except ImportError:
    print("Warning: selenium not installed. Some sites may not work. Run: pip install selenium webdriver-manager")
    selenium_available = False
    webdriver_manager_available = False

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
            return lang.split('/')[0]
    if country_code:
        lang = COUNTRY_LANGUAGE_MAP.get(country_code, None)
        if lang:
            return lang.split('/')[0]
    return 'English'

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
                backoff_time = min(60 * (i + 1), 300)
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
        
        soup = BeautifulSoup(response.content, 'html.parser')
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()
        
        text = soup.get_text(separator=' ', strip=True)
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        return text[:20000]
    except Exception as e:
        print(f"  ⚠️  Error fetching webpage: {e}")
        return None

def check_company_relevance(company_url: str) -> Tuple[bool, Optional[str]]:
    """Check if a company URL is relevant (prefab houses, structural panels, or architectural precast panels)"""
    print(f"    🔍 Checking relevance: {company_url}")
    
    webpage_content = fetch_webpage_content(company_url)
    
    prompt = f"""You are checking if a company website is relevant for a database of prefab/modular home manufacturers.

Company URL: {company_url}

Webpage content (first 20000 chars):
{webpage_content[:20000] if webpage_content else 'Could not fetch webpage content - use your knowledge to search'}

Determine if this company manufactures ANY of the following:
- Prefab/prefabricated houses/homes
- Modular houses/homes
- Structural panels for construction (SIP panels, CLT panels, structural wall panels, etc.)
- Architectural precast panels (for building facades, walls, etc.)
- Panelized construction systems
- Off-site construction for residential buildings
- Timber frame/prefab houses
- Prefab panels/modules for housing

IMPORTANT: Only include companies that produce:
1. Prefab houses (residential buildings)
2. Structural panels (for building construction)
3. Architectural precast panels (for building facades/walls)

EXCLUDE companies that only produce:
- Concrete products for infrastructure (bridges, roads, etc.)
- Non-structural precast elements (pipes, pavers, etc.)
- Only construction services without manufacturing
- Only materials/components without prefab systems

If YES (produces prefab houses, structural panels, or architectural precast panels), return a JSON object:
{{
  "relevant": true,
  "company_name": "company name or brand",
  "reason": "brief reason why it's relevant (prefab houses/structural panels/architectural precast)"
}}

If NO (does not produce prefab houses, structural panels, or architectural precast panels), return:
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
                print(f"    ✅ Relevant: {company_name}")
                return True, company_name
            else:
                reason = data.get('reason', 'Not a prefab manufacturer')
                print(f"    ❌ Not relevant: {reason}")
                return False, None
    except Exception as e:
        print(f"    ⚠️  Error checking relevance: {e}")
    
    return False, None

def check_company_exists(company_url: str, existing_webpages: Set[str]) -> bool:
    """Check if company already exists in the database"""
    normalized_url = company_url.lower().rstrip('/')
    normalized_url = normalized_url.replace('http://', 'https://')
    
    if normalized_url in existing_webpages:
        return True
    
    domain = urlparse(normalized_url).netloc.lower()
    domain = domain.replace('www.', '')
    for existing_url in existing_webpages:
        existing_domain = urlparse(existing_url.lower()).netloc.lower().replace('www.', '')
        if existing_domain == domain:
            return True
    
    return False

def geocode_address(address: str, country: str = None, region: str = None) -> Tuple[Optional[float], Optional[float]]:
    """Geocode an address using OpenAI and geopy"""
    if not address or address.strip() in ['', 'NaN', 'null', 'None']:
        return None, None
    
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
            
            lat = data.get('latitude')
            lon = data.get('longitude')
            if lat is not None and lon is not None:
                try:
                    return float(lat), float(lon)
                except (ValueError, TypeError):
                    pass
            
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

def investigate_webpage_and_extract_info(webpage: str, company_name: str) -> Dict:
    """Investigate webpage content and extract company information"""
    
    webpage_content = fetch_webpage_content(webpage)
    
    domain = urlparse(webpage).netloc.lower()
    country = None
    country_code = None
    
    country_domains = {
        '.de': ('Germany', 'DEU'), '.fr': ('France', 'FRA'), '.it': ('Italy', 'ITA'),
        '.es': ('Spain', 'ESP'), '.nl': ('Netherlands', 'NLD'), '.be': ('Belgium', 'BEL'),
        '.at': ('Austria', 'AUT'), '.se': ('Sweden', 'SWE'), '.dk': ('Denmark', 'DNK'),
        '.fi': ('Finland', 'FIN'), '.pl': ('Poland', 'POL'), '.cz': ('Czech Republic', 'CZE'),
        '.pt': ('Portugal', 'PRT'), '.gr': ('Greece', 'GRC'), '.ie': ('Ireland', 'IRL'),
        '.ro': ('Romania', 'ROU'), '.hu': ('Hungary', 'HUN'), '.sk': ('Slovakia', 'SVK'),
        '.bg': ('Bulgaria', 'BGR'), '.hr': ('Croatia', 'HRV'), '.si': ('Slovenia', 'SVN'),
        '.lt': ('Lithuania', 'LTU'), '.lv': ('Latvia', 'LVA'), '.ee': ('Estonia', 'EST'),
        '.ch': ('Switzerland', 'CHE'), '.no': ('Norway', 'NOR'), '.uk': ('United Kingdom', 'GBR'),
        '.ca': ('Canada', 'CAN'), '.au': ('Australia', 'AUS'), '.nz': ('New Zealand', 'NZL'),
        '.jp': ('Japan', 'JPN'), '.cn': ('China', 'CHN'), '.in': ('India', 'IND'),
        '.tr': ('Turkey', 'TUR'), '.br': ('Brazil', 'BRA'), '.mx': ('Mexico', 'MEX'),
        '.cl': ('Chile', 'CHL'), '.ar': ('Argentina', 'ARG'),
    }
    
    for domain_suffix, (country_name, code) in country_domains.items():
        if domain_suffix in domain:
            country = country_name
            country_code = code
            break
    
    language = get_language_for_country(country, country_code)
    
    prompt = f"""You are investigating a prefab/modular home company's website to extract detailed information.

Company name: {company_name or 'Unknown'}
Website URL: {webpage}
Country: {country or 'Unknown'}
Language: {language}

Webpage content (first 20000 chars):
{webpage_content[:20000] if webpage_content else 'Could not fetch webpage content - use your knowledge to search'}

Extract and fill in ALL available information. Return ONLY valid JSON in this exact format (use null for missing data, NaN for numeric fields that cannot be determined):

{{
  "brand": "brand name or trading name",
  "head_office_legal_name": "full legal registered company name",
  "address": "complete address: street number, street name, city, postal code, country",
  "country": "country name",
  "country_code": "ISO 3166-1 alpha-3 country code",
  "region": "state/province/region name",
  "webpage": "main website homepage URL - use the provided URL",
  "models_amount": number of different prefab home models/designs (integer or null),
  "min_sqm": minimum square meters of smallest model (number or null, living area),
  "max_sqm": maximum square meters of largest model (number or null, living area),
  "main_structure_material": "primary construction material: wood/timber/concrete/steel/composite/CLT/etc",
  "min_home_price": minimum starting price in local currency (number or null, base price without land),
  "average_price_sqm": average price per square meter in local currency (number or null)
}}

CRITICAL REQUIREMENTS:
- Use the provided webpage URL as the webpage value
- Extract information from the webpage content if available
- Only fill in fields where you can find reliable information
- For prices, use the local currency (do not convert)
- Be precise and factual
- Consider the local language ({language}) when interpreting information
- Return ONLY the JSON object, no explanations"""

    try:
        response = call_openai([{'role': 'user', 'content': prompt}])
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

def create_chrome_driver():
    """Create Chrome driver with webdriver-manager"""
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    
    if webdriver_manager_available:
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    else:
        return webdriver.Chrome(options=options)

def save_progress_json(stats: Dict, output_file: Path):
    """Save progress to JSON file"""
    try:
        progress_data = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'stats': stats,
            'status': 'running'
        }
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"  ⚠️  Error saving progress JSON: {e}")

def double_check_structure_material(webpage: str, initial_material: str, company_name: str) -> str:
    """Double-check the main structure material"""
    print(f"    🔬 Double-checking structure material: {initial_material}")
    
    webpage_content = fetch_webpage_content(webpage)
    
    prompt = f"""You are verifying the main structure material for a prefab/modular home manufacturer.

Company: {company_name}
Website: {webpage}
Initial assessment: {initial_material}

Webpage content (first 20000 chars):
{webpage_content[:20000] if webpage_content else 'Could not fetch webpage content - use your knowledge to search'}

Analyze the overall company webpage content AND descriptions of house models to determine the PRIMARY construction material used.

Return ONLY a JSON object:
{{
  "main_structure_material": "the primary material (wood/timber/concrete/steel/composite/CLT/etc)",
  "confidence": "high/medium/low",
  "reasoning": "brief explanation"
}}

Return ONLY the JSON object, no explanations."""

    try:
        response = call_openai([{'role': 'user', 'content': prompt}])
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            data = json.loads(json_match.group(0))
            verified_material = data.get('main_structure_material', initial_material)
            confidence = data.get('confidence', 'medium')
            print(f"    ✅ Verified material: {verified_material} (confidence: {confidence})")
            return verified_material
    except Exception as e:
        print(f"    ⚠️  Error double-checking material: {e}")
    
    return initial_material

# Association-specific scrapers

def scrape_prefabaus(driver=None) -> List[str]:
    """Scrape prefabaus.org.au member directory"""
    print("  📄 Scraping prefabaus.org.au...")
    company_urls = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get('https://www.prefabaus.org.au/member-directory', headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all summary items
        items = soup.find_all('div', class_=re.compile(r'summary-item.*summary-item-record-type-text'))
        
        for item in items:
            # Check if contains 'Prefabrication or Modular builder/manufacturer'
            text = item.get_text()
            if 'Prefabrication or Modular builder/manufacturer' in text:
                # Find link to company page
                link_elem = item.find('a', href=True)
                if link_elem:
                    company_page_url = urljoin('https://www.prefabaus.org.au', link_elem['href'])
                    
                    # Fetch company page to find website
                    try:
                        comp_response = requests.get(company_page_url, headers=headers, timeout=15)
                        comp_soup = BeautifulSoup(comp_response.content, 'html.parser')
                        
                        # Look for website link
                        for a_tag in comp_soup.find_all('a', href=True):
                            href = a_tag['href']
                            if href.startswith('http') and 'prefabaus.org.au' not in href:
                                company_urls.append(href)
                                break
                    except Exception as e:
                        print(f"    ⚠️  Error fetching company page: {e}")
        
        print(f"  ✅ Found {len(company_urls)} company URLs")
    except Exception as e:
        print(f"  ⚠️  Error scraping prefabaus: {e}")
    
    return company_urls

def scrape_chba(driver=None) -> List[str]:
    """Scrape hub.chba.ca member directory"""
    print("  📄 Scraping hub.chba.ca...")
    company_urls = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get('https://hub.chba.ca/member-directory/Search/manufacturer-494628', headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all Rank10 gz-list-col divs
        items = soup.find_all('div', class_='Rank10 gz-list-col')
        
        for item in items:
            # Find website link
            for a_tag in item.find_all('a', href=True):
                href = a_tag['href']
                text = a_tag.get_text(strip=True).lower()
                if 'visit website' in text or 'website' in text:
                    if href.startswith('http'):
                        company_urls.append(href)
                        break
        
        print(f"  ✅ Found {len(company_urls)} company URLs")
    except Exception as e:
        print(f"  ⚠️  Error scraping CHBA: {e}")
    
    return company_urls

def scrape_woodhouse_ee(driver=None) -> List[str]:
    """Scrape woodhouse.ee partners"""
    print("  📄 Scraping woodhouse.ee...")
    company_urls = []
    
    if not selenium_available:
        print("  ⚠️  Selenium not available, skipping dynamic site")
        return company_urls
    
    try:
        if driver is None:
            driver = create_chrome_driver()
            created_driver = True
        else:
            created_driver = False
        
        driver.get('https://woodhouse.ee/partners/#/')
        time.sleep(3)  # Wait for page load
        
        # Find all partner divs
        partners = driver.find_elements(By.CSS_SELECTOR, 'div.filtered-list__partner')
        
        for partner in partners:
            try:
                text = partner.text
                if 'Modular houses' in text:
                    # Click to open company page
                    partner.click()
                    time.sleep(2)
                    
                    # Find company website link
                    try:
                        website_link = driver.find_element(By.CSS_SELECTOR, 'a[href^="http"]')
                        href = website_link.get_attribute('href')
                        if href and 'woodhouse.ee' not in href:
                            company_urls.append(href)
                    except NoSuchElementException:
                        pass
                    
                    # Go back
                    driver.back()
                    time.sleep(1)
            except Exception as e:
                print(f"    ⚠️  Error processing partner: {e}")
        
        if created_driver:
            driver.quit()
        
        print(f"  ✅ Found {len(company_urls)} company URLs")
    except Exception as e:
        print(f"  ⚠️  Error scraping woodhouse.ee: {e}")
    
    return company_urls

def scrape_itfma(driver=None) -> List[str]:
    """Scrape itfma.ie members"""
    print("  📄 Scraping itfma.ie...")
    company_urls = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get('https://itfma.ie/members/', headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all flipbox divs
        flipboxes = soup.find_all('div', class_=re.compile(r'elementor-element.*eael-flip-box'))
        
        for flipbox in flipboxes:
            # Find link to company webpage
            for a_tag in flipbox.find_all('a', href=True):
                href = a_tag['href']
                if href.startswith('http') and 'itfma.ie' not in href:
                    company_urls.append(href)
                    break
        
        print(f"  ✅ Found {len(company_urls)} company URLs")
    except Exception as e:
        print(f"  ⚠️  Error scraping ITFMA: {e}")
    
    return company_urls

def scrape_lignius(driver=None) -> List[str]:
    """Scrape lignius.it costruttori"""
    print("  📄 Scraping lignius.it...")
    company_urls = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get('https://www.lignius.it/migliori-costruttori-case-in-legno/', headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all company list items
        items = soup.find_all('div', class_='company-list-item')
        
        for item in items:
            # Find mt-5 div with webpage link
            mt5_div = item.find('div', class_='mt-5')
            if mt5_div:
                for a_tag in mt5_div.find_all('a', href=True):
                    href = a_tag['href']
                    if href.startswith('http') and 'lignius.it' not in href:
                        company_urls.append(href)
                        break
        
        print(f"  ✅ Found {len(company_urls)} company URLs")
    except Exception as e:
        print(f"  ⚠️  Error scraping Lignius: {e}")
    
    return company_urls

def scrape_drevovstavbe(driver=None) -> List[str]:
    """Scrape drevovstavbe.sk - use image search for logos"""
    print("  📄 Scraping drevovstavbe.sk...")
    company_urls = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get('https://www.drevovstavbe.sk/', headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find splide track with logos
        splide_track = soup.find('div', class_=re.compile(r'splide__track.*splide__track--loop'))
        if splide_track:
            # Find all images
            images = splide_track.find_all('img', src=True)
            
            for img in images:
                img_src = img.get('src', '')
                if img_src:
                    # Use AI to search for company website based on logo
                    # For now, try to extract company name from alt text or nearby text
                    alt_text = img.get('alt', '')
                    if alt_text:
                        # Use AI to find company website
                        prompt = f"""Find the official website URL for a Slovak prefab/modular home company based on this information:

Company name or logo alt text: {alt_text}
Logo image URL: {img_src}

Return ONLY the website URL if found, or null if not found."""
                        
                        try:
                            ai_response = call_openai([{'role': 'user', 'content': prompt}])
                            url_match = re.search(r'https?://[^\s]+', ai_response)
                            if url_match:
                                company_urls.append(url_match.group(0))
                        except Exception as e:
                            print(f"    ⚠️  Error finding company URL: {e}")
        
        print(f"  ✅ Found {len(company_urls)} company URLs")
    except Exception as e:
        print(f"  ⚠️  Error scraping drevovstavbe: {e}")
    
    return company_urls

def scrape_casasdepaja(driver=None) -> List[str]:
    """Scrape casasdepaja.org member directory"""
    print("  📄 Scraping casasdepaja.org...")
    company_urls = []
    base_url = 'https://www.casasdepaja.org'
    
    # Handle pagination
    page = 1
    while True:
        try:
            url = f'{base_url}/la-red/listado-de-socios/listado-de-socios-pro-4/'
            if page > 1:
                url += f'?page_MzmIb={page}'
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all member covers
            members = soup.find_all('div', class_='um-member-cover')
            
            if not members:
                break
            
            for member in members:
                # Find um-field-area with website
                field_area = member.find('div', class_='um-field-area')
                if field_area:
                    for a_tag in field_area.find_all('a', href=True):
                        href = a_tag['href']
                        if href.startswith('http') and 'casasdepaja.org' not in href:
                            company_urls.append(href)
                            break
            
            # Check for next page
            next_link = soup.find('a', href=re.compile(r'page_MzmIb=' + str(page + 1)))
            if not next_link:
                break
            
            page += 1
            time.sleep(2)
        except Exception as e:
            print(f"  ⚠️  Error on page {page}: {e}")
            break
    
    print(f"  ✅ Found {len(company_urls)} company URLs")
    return company_urls

def scrape_timberdevelopment(driver=None) -> List[str]:
    """Scrape timberdevelopment.uk - need to scroll to load all"""
    print("  📄 Scraping timberdevelopment.uk...")
    company_urls = []
    
    if not selenium_available:
        print("  ⚠️  Selenium not available, trying basic scraping")
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get('https://timberdevelopment.uk/find-your-timber-partner/search/?_sfm_member-business_type=Manufacturer', headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find company links
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                if '/find-your-timber-partner/' in href and href != 'https://timberdevelopment.uk/find-your-timber-partner/search/':
                    # Fetch company page
                    try:
                        comp_response = requests.get(href, headers=headers, timeout=15)
                        comp_soup = BeautifulSoup(comp_response.content, 'html.parser')
                        
                        # Find website link
                        for link in comp_soup.find_all('a', href=True):
                            link_href = link['href']
                            if link_href.startswith('http') and 'timberdevelopment.uk' not in link_href:
                                company_urls.append(link_href)
                                break
                    except Exception:
                        pass
        except Exception as e:
            print(f"  ⚠️  Error scraping: {e}")
    else:
        try:
            if driver is None:
                from selenium.webdriver.chrome.options import Options
                options = Options()
                options.add_argument('--headless')
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                driver = webdriver.Chrome(options=options)
                created_driver = True
            else:
                created_driver = False
            
            driver.get('https://timberdevelopment.uk/find-your-timber-partner/search/?_sfm_member-business_type=Manufacturer')
            time.sleep(3)
            
            # Scroll to load all listings
            last_height = driver.execute_script("return document.body.scrollHeight")
            while True:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
            
            # Find all company listing links
            listing_links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/find-your-timber-partner/"]')
            
            visited = set()
            for link in listing_links:
                href = link.get_attribute('href')
                if href and href not in visited and '/search/' not in href:
                    visited.add(href)
                    try:
                        driver.get(href)
                        time.sleep(2)
                        
                        # Find website link
                        try:
                            website_link = driver.find_element(By.CSS_SELECTOR, 'a[href^="http"]:not([href*="timberdevelopment.uk"])')
                            company_url = website_link.get_attribute('href')
                            if company_url:
                                company_urls.append(company_url)
                        except NoSuchElementException:
                            pass
                    except Exception as e:
                        print(f"    ⚠️  Error processing listing: {e}")
            
            if created_driver:
                driver.quit()
        except Exception as e:
            print(f"  ⚠️  Error scraping with Selenium: {e}")
    
    print(f"  ✅ Found {len(company_urls)} company URLs")
    return company_urls

def scrape_tmf(driver=None) -> List[str]:
    """Scrape tmf.se - filter by 'Hus'"""
    print("  📄 Scraping tmf.se...")
    company_urls = []
    
    if not selenium_available:
        print("  ⚠️  Selenium not available, skipping dynamic site")
        return company_urls
    
    try:
        if driver is None:
            driver = create_chrome_driver()
            created_driver = True
        else:
            created_driver = False
        
        driver.get('https://www.tmf.se/sok-medlem')
        time.sleep(3)
        
        # Find and click filter button with 'Hus'
        try:
            filter_buttons = driver.find_elements(By.XPATH, "//*[contains(@x-text, 'item.EgenskapName')]")
            for btn in filter_buttons:
                if 'Hus' in btn.text:
                    btn.click()
                    time.sleep(2)
                    break
        except Exception as e:
            print(f"    ⚠️  Error clicking filter: {e}")
        
        # Find all listings
        listings = driver.find_elements(By.CSS_SELECTOR, 'div.py-24.w-full.border-b')
        
        for listing in listings:
            try:
                # Find website link
                links = listing.find_elements(By.CSS_SELECTOR, 'a[href^="http"]')
                for link in links:
                    href = link.get_attribute('href')
                    if href and 'tmf.se' not in href:
                        company_urls.append(href)
                        break
            except Exception as e:
                print(f"    ⚠️  Error processing listing: {e}")
        
        if created_driver:
            driver.quit()
        
        print(f"  ✅ Found {len(company_urls)} company URLs")
    except Exception as e:
        print(f"  ⚠️  Error scraping TMF: {e}")
    
    return company_urls

def scrape_vgq(driver=None) -> List[str]:
    """Scrape vgq.ch members"""
    print("  📄 Scraping vgq.ch...")
    company_urls = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get('https://vgq.ch/netzwerk/vgq-mitglieder', headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all member-mini-logo divs
        logos = soup.find_all('div', class_='member-mini-logo')
        
        for logo in logos:
            # Find parent container and look for company webpage link
            parent = logo.find_parent()
            if parent:
                # Look for links in the listing
                for a_tag in parent.find_all('a', href=True):
                    href = a_tag['href']
                    if href.startswith('http') and 'vgq.ch' not in href:
                        company_urls.append(href)
                        break
                # Also check if clicking logo leads to company page
                if logo.find('a', href=True):
                    link = logo.find('a', href=True)
                    company_page = urljoin('https://vgq.ch', link['href'])
                    try:
                        comp_response = requests.get(company_page, headers=headers, timeout=15)
                        comp_soup = BeautifulSoup(comp_response.content, 'html.parser')
                        for a_tag in comp_soup.find_all('a', href=True):
                            href = a_tag['href']
                            if href.startswith('http') and 'vgq.ch' not in href:
                                company_urls.append(href)
                                break
                    except Exception:
                        pass
        
        print(f"  ✅ Found {len(company_urls)} company URLs")
    except Exception as e:
        print(f"  ⚠️  Error scraping VGQ: {e}")
    
    return company_urls

def scrape_woodhouses_lv(driver=None) -> List[str]:
    """Scrape woodhouses.lv manufacturers"""
    print("  📄 Scraping woodhouses.lv...")
    company_urls = []
    
    if not selenium_available:
        print("  ⚠️  Selenium not available, trying basic scraping")
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get('https://woodhouses.lv/en/manufacturers/', headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all post listings
            posts = soup.find_all('li', class_='post')
            
            for post in posts:
                # Find link to company page
                link = post.find('a', href=True)
                if link:
                    company_page = urljoin('https://woodhouses.lv', link['href'])
                    try:
                        comp_response = requests.get(company_page, headers=headers, timeout=15)
                        comp_soup = BeautifulSoup(comp_response.content, 'html.parser')
                        for a_tag in comp_soup.find_all('a', href=True):
                            href = a_tag['href']
                            if href.startswith('http') and 'woodhouses.lv' not in href:
                                company_urls.append(href)
                                break
                    except Exception:
                        pass
        except Exception as e:
            print(f"  ⚠️  Error scraping: {e}")
    else:
        try:
            if driver is None:
                from selenium.webdriver.chrome.options import Options
                options = Options()
                options.add_argument('--headless')
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                driver = webdriver.Chrome(options=options)
                created_driver = True
            else:
                created_driver = False
            
            driver.get('https://woodhouses.lv/en/manufacturers/')
            time.sleep(3)
            
            # Find all post listings
            posts = driver.find_elements(By.CSS_SELECTOR, 'li.post')
            
            for post in posts:
                try:
                    # Click on listing
                    post.click()
                    time.sleep(2)
                    
                    # Find company website link
                    try:
                        website_link = driver.find_element(By.CSS_SELECTOR, 'a[href^="http"]:not([href*="woodhouses.lv"])')
                        href = website_link.get_attribute('href')
                        if href:
                            company_urls.append(href)
                    except NoSuchElementException:
                        pass
                    
                    # Go back
                    driver.back()
                    time.sleep(1)
                except Exception as e:
                    print(f"    ⚠️  Error processing post: {e}")
            
            if created_driver:
                driver.quit()
        except Exception as e:
            print(f"  ⚠️  Error scraping with Selenium: {e}")
    
    print(f"  ✅ Found {len(company_urls)} company URLs")
    return company_urls

def scrape_klaster_lt(driver=None) -> List[str]:
    """Scrape klaster.lt PrefabLT members"""
    print("  📄 Scraping klaster.lt...")
    company_urls = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get('https://klaster.lt/en/klateris/prefablt/', headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all col-6 listings
        listings = soup.find_all('div', class_=re.compile(r'col-6.*col-lg-6.*col-xl-6'))
        
        for listing in listings:
            # Find claster-contacts div
            contacts = listing.find('div', class_='claster-contacts')
            if contacts:
                # Find company webpage links
                for a_tag in contacts.find_all('a', href=True):
                    href = a_tag['href']
                    if href.startswith('http') and 'klaster.lt' not in href:
                        company_urls.append(href)
        
        print(f"  ✅ Found {len(company_urls)} company URLs")
    except Exception as e:
        print(f"  ⚠️  Error scraping KlasterLT: {e}")
    
    return company_urls

def scrape_massmadera(driver=None) -> List[str]:
    """Scrape massmadera.org pioneros"""
    print("  📄 Scraping massmadera.org...")
    company_urls = []
    
    if not selenium_available:
        print("  ⚠️  Selenium not available, trying basic scraping")
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get('https://massmadera.org/pioneros/', headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all grid items
            items = soup.find_all('div', class_=re.compile(r'vc_grid-item-mini.*vc_clearfix'))
            
            for item in items:
                # Find link to company page
                link = item.find('a', href=True)
                if link:
                    company_page = urljoin('https://massmadera.org', link['href'])
                    try:
                        comp_response = requests.get(company_page, headers=headers, timeout=15)
                        comp_soup = BeautifulSoup(comp_response.content, 'html.parser')
                        for a_tag in comp_soup.find_all('a', href=True):
                            href = a_tag['href']
                            if href.startswith('http') and 'massmadera.org' not in href:
                                company_urls.append(href)
                                break
                    except Exception:
                        pass
        except Exception as e:
            print(f"  ⚠️  Error scraping: {e}")
    else:
        try:
            if driver is None:
                from selenium.webdriver.chrome.options import Options
                options = Options()
                options.add_argument('--headless')
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                driver = webdriver.Chrome(options=options)
                created_driver = True
            else:
                created_driver = False
            
            driver.get('https://massmadera.org/pioneros/')
            time.sleep(3)
            
            # Find all grid items
            items = driver.find_elements(By.CSS_SELECTOR, 'div.vc_grid-item-mini.vc_clearfix')
            
            for item in items:
                try:
                    # Click on listing
                    item.click()
                    time.sleep(2)
                    
                    # Find company website link
                    try:
                        website_link = driver.find_element(By.CSS_SELECTOR, 'a[href^="http"]:not([href*="massmadera.org"])')
                        href = website_link.get_attribute('href')
                        if href:
                            company_urls.append(href)
                    except NoSuchElementException:
                        pass
                    
                    # Go back
                    driver.back()
                    time.sleep(1)
                except Exception as e:
                    print(f"    ⚠️  Error processing item: {e}")
            
            if created_driver:
                driver.quit()
        except Exception as e:
            print(f"  ⚠️  Error scraping with Selenium: {e}")
    
    print(f"  ✅ Found {len(company_urls)} company URLs")
    return company_urls

def scrape_andece(driver=None) -> List[str]:
    """Scrape andece.org modulos prefabricados"""
    print("  📄 Scraping andece.org...")
    company_urls = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get('https://andece.org/directorio-de-negocios/wpbdp_category/modulos-prefabricados/', headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all field-label spans with 'Sitio web'
        field_labels = soup.find_all('span', class_='field-label')
        
        for label in field_labels:
            if 'Sitio web' in label.get_text():
                # Find the value/link in next sibling or parent
                parent = label.find_parent()
                if parent:
                    for a_tag in parent.find_all('a', href=True):
                        href = a_tag['href']
                        if href.startswith('http') and 'andece.org' not in href:
                            company_urls.append(href)
                            break
        
        print(f"  ✅ Found {len(company_urls)} company URLs")
    except Exception as e:
        print(f"  ⚠️  Error scraping ANDECE: {e}")
    
    return company_urls

def scrape_bis(driver=None) -> List[str]:
    """Scrape bis.org.rs members - search for company webpages"""
    print("  📄 Scraping bis.org.rs...")
    company_urls = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get('https://bis.org.rs/en/members', headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all member links
        member_links = soup.find_all('a', href=True)
        
        visited = set()
        for link in member_links:
            href = link.get('href', '')
            if href and '/en/members/' in href and href not in visited:
                visited.add(href)
                member_url = urljoin('https://bis.org.rs', href)
                
                try:
                    member_response = requests.get(member_url, headers=headers, timeout=15)
                    member_soup = BeautifulSoup(member_response.content, 'html.parser')
                    
                    # Extract company name
                    company_name = member_soup.find('h1')
                    if company_name:
                        company_name = company_name.get_text(strip=True)
                        
                        # Use AI to search for company website
                        prompt = f"""Find the official website URL for a Serbian prefab/concrete company.

Company name: {company_name}
Country: Serbia

Return ONLY the website URL if found, or null if not found."""
                        
                        try:
                            ai_response = call_openai([{'role': 'user', 'content': prompt}])
                            url_match = re.search(r'https?://[^\s]+', ai_response)
                            if url_match:
                                company_urls.append(url_match.group(0))
                        except Exception as e:
                            print(f"    ⚠️  Error finding URL for {company_name}: {e}")
                    
                    time.sleep(2)
                except Exception as e:
                    print(f"    ⚠️  Error fetching member page: {e}")
        
        print(f"  ✅ Found {len(company_urls)} company URLs")
    except Exception as e:
        print(f"  ⚠️  Error scraping BIS: {e}")
    
    return company_urls

def scrape_prefabassociation_ua(driver=None) -> List[str]:
    """Scrape prefabassociation.webflow.io - search by logo images"""
    print("  📄 Scraping prefabassociation.webflow.io...")
    company_urls = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        url = 'https://prefabassociation.webflow.io/?fbclid=IwY2xjawPrHS9leHRuA2FlbQIxMABicmlkETBwRGF5OWk3OWE5aFp5VjFwc3J0YwZhcHBfaWQQMjIyMDM5MTc4ODIwMDg5MgABHlFqY05_LD0cqJVjcTnq8dA5TVIfVr0b9NfHGjL_-7mikiIUjnkrGJQa0yFA_aem_ihmd2hy4EsV21Q-lKTnSKw#directions'
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all logo slides
        logo_slides = soup.find_all('div', class_=re.compile(r'logo-slide.*slick-slide'))
        
        for slide in logo_slides:
            # Find images
            images = slide.find_all('img', src=True)
            for img in images:
                img_src = img.get('src', '')
                alt_text = img.get('alt', '')
                
                if img_src:
                    # Use AI to find company website based on logo/name
                    prompt = f"""Find the official website URL for a Ukrainian prefab/modular construction company.

Logo alt text or company name: {alt_text}
Logo image URL: {img_src}

Return ONLY the website URL if found, or null if not found."""
                    
                    try:
                        ai_response = call_openai([{'role': 'user', 'content': prompt}])
                        url_match = re.search(r'https?://[^\s]+', ai_response)
                        if url_match:
                            company_urls.append(url_match.group(0))
                    except Exception as e:
                        print(f"    ⚠️  Error finding company URL: {e}")
        
        print(f"  ✅ Found {len(company_urls)} company URLs")
    except Exception as e:
        print(f"  ⚠️  Error scraping PrefabAssociation UA: {e}")
    
    return company_urls

def scrape_anippac(driver=None) -> List[str]:
    """Scrape anippac.org.mx Prefabricadores"""
    print("  📄 Scraping anippac.org.mx...")
    company_urls = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get('https://anippac.org.mx/asociados-2/', headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find elementor-5950 div
        elementor_div = soup.find('div', class_=re.compile(r'elementor.*elementor-5950'))
        if elementor_div:
            # Check if contains 'Prefabricadores'
            if 'Prefabricadores' in elementor_div.get_text():
                # Find all listings within
                listings = elementor_div.find_all('div', recursive=True)
                
                for listing in listings:
                    # Find company webpage links
                    for a_tag in listing.find_all('a', href=True):
                        href = a_tag['href']
                        text = a_tag.get_text(strip=True).lower()
                        if ('ver pagina web' in text or 'sitio web' in text or 'website' in text) and href.startswith('http'):
                            if 'anippac.org.mx' not in href:
                                company_urls.append(href)
        
        print(f"  ✅ Found {len(company_urls)} company URLs")
    except Exception as e:
        print(f"  ⚠️  Error scraping ANIPPAC: {e}")
    
    return company_urls

def scrape_pci(driver=None) -> List[str]:
    """Scrape pci.org certified plants"""
    print("  📄 Scraping pci.org...")
    company_urls = []
    
    if not selenium_available:
        print("  ⚠️  Selenium not available, skipping dynamic site")
        return company_urls
    
    try:
        if driver is None:
            driver = create_chrome_driver()
            created_driver = True
        else:
            created_driver = False
        
        driver.get('https://www.pci.org/PCI/Directories/PCICertifiedPlants.aspx')
        time.sleep(3)
        
        # Click Find button
        try:
            find_button = driver.find_element(By.CSS_SELECTOR, 'input[value="Find"]')
            find_button.click()
            time.sleep(5)  # Wait for listings to load
        except Exception as e:
            print(f"    ⚠️  Error clicking Find button: {e}")
        
        # Find all rows
        rows = driver.find_elements(By.CSS_SELECTOR, 'tr.rgAltRow, tr.rgRow')
        
        for row in rows:
            try:
                text = row.text
                # Check if contains 'Architectural Precast' or 'Structural Wall Panels'
                if 'Architectural Precast' in text or 'Structural Wall Panels' in text:
                    # Find company website link
                    try:
                        links = row.find_elements(By.CSS_SELECTOR, 'a[href^="http"]')
                        for link in links:
                            href = link.get_attribute('href')
                            if href and 'pci.org' not in href:
                                company_urls.append(href)
                                break
                    except Exception:
                        pass
            except Exception as e:
                print(f"    ⚠️  Error processing row: {e}")
        
        if created_driver:
            driver.quit()
        
        print(f"  ✅ Found {len(company_urls)} company URLs")
    except Exception as e:
        print(f"  ⚠️  Error scraping PCI: {e}")
    
    return company_urls

def scrape_mfgmodhome(driver=None) -> List[str]:
    """Scrape mfgmodhome.org member directory"""
    print("  📄 Scraping mfgmodhome.org...")
    company_urls = []
    
    if not selenium_available:
        print("  ⚠️  Selenium not available, skipping dynamic site")
        return company_urls
    
    try:
        if driver is None:
            driver = create_chrome_driver()
            created_driver = True
        else:
            created_driver = False
        
        url = 'https://mfgmodhome.org/about/member-directory/#/action/AdvancedSearch/cid/1898/id/401/listingtype/O/category/102%2c107%2c115'
        driver.get(url)
        time.sleep(5)  # Wait for page to load
        
        # Find all listings
        listings = driver.find_elements(By.CSS_SELECTOR, 'div[id^="ucDirectory_ucResults_rptResults_ctl"]')
        
        for listing in listings:
            try:
                # Click on listing
                listing.click()
                time.sleep(2)
                
                # Find company website in social div
                try:
                    social_div = driver.find_element(By.CSS_SELECTOR, 'div.social')
                    website_link = social_div.find_element(By.CSS_SELECTOR, 'a[href^="http"]')
                    href = website_link.get_attribute('href')
                    if href:
                        company_urls.append(href)
                except NoSuchElementException:
                    pass
                
                # Go back
                driver.back()
                time.sleep(1)
            except Exception as e:
                print(f"    ⚠️  Error processing listing: {e}")
        
        if created_driver:
            driver.quit()
        
        print(f"  ✅ Found {len(company_urls)} company URLs")
    except Exception as e:
        print(f"  ⚠️  Error scraping MFGModHome: {e}")
    
    return company_urls

def scrape_ensun(driver=None) -> List[str]:
    """Scrape ensun.io prefabricated-home search"""
    print("  📄 Scraping ensun.io...")
    company_urls = []
    
    if not selenium_available:
        print("  ⚠️  Selenium not available, skipping dynamic site")
        return company_urls
    
    try:
        if driver is None:
            driver = create_chrome_driver()
            created_driver = True
        else:
            created_driver = False
        
        driver.get('https://ensun.io/search/prefabricated-home/china')
        time.sleep(5)  # Wait for page to load
        
        # Find all listings
        listings = driver.find_elements(By.CSS_SELECTOR, 'div.MuiPaper-root.MuiPaper-elevation.MuiPaper-rounded')
        
        for listing in listings:
            try:
                # Click on listing
                listing.click()
                time.sleep(2)
                
                # Find company website in MuiGrid div
                try:
                    grid_div = driver.find_element(By.CSS_SELECTOR, 'div.MuiGrid-root.MuiGrid-direction-xs-row.MuiGrid-grid-xs-auto')
                    website_link = grid_div.find_element(By.CSS_SELECTOR, 'a[href^="http"]')
                    href = website_link.get_attribute('href')
                    if href and 'ensun.io' not in href:
                        company_urls.append(href)
                except NoSuchElementException:
                    pass
                
                # Go back
                driver.back()
                time.sleep(1)
            except Exception as e:
                print(f"    ⚠️  Error processing listing: {e}")
        
        if created_driver:
            driver.quit()
        
        print(f"  ✅ Found {len(company_urls)} company URLs")
    except Exception as e:
        print(f"  ⚠️  Error scraping Ensun: {e}")
    
    return company_urls

# Association mapping
ASSOCIATION_SCRAPERS = {
    'https://www.prefabaus.org.au/member-directory': scrape_prefabaus,
    'https://hub.chba.ca/member-directory/Search/manufacturer-494628': scrape_chba,
    'https://woodhouse.ee/partners/#/': scrape_woodhouse_ee,
    'https://itfma.ie/members/': scrape_itfma,
    'https://www.lignius.it/migliori-costruttori-case-in-legno/': scrape_lignius,
    'https://www.drevovstavbe.sk/': scrape_drevovstavbe,
    'https://www.casasdepaja.org/la-red/listado-de-socios/listado-de-socios-pro-4/?page_MzmIb=2': scrape_casasdepaja,
    'https://timberdevelopment.uk/find-your-timber-partner/search/?_sfm_member-business_type=Manufacturer': scrape_timberdevelopment,
    'https://www.tmf.se/sok-medlem': scrape_tmf,
    'https://vgq.ch/netzwerk/vgq-mitglieder': scrape_vgq,
    'https://woodhouses.lv/en/manufacturers/': scrape_woodhouses_lv,
    'https://klaster.lt/en/klateris/prefablt/': scrape_klaster_lt,
    'https://massmadera.org/pioneros/': scrape_massmadera,
    'https://andece.org/directorio-de-negocios/wpbdp_category/modulos-prefabricados/': scrape_andece,
    'https://bis.org.rs/en/members': scrape_bis,
    'https://prefabassociation.webflow.io/?fbclid=IwY2xjawPrHS9leHRuA2FlbQIxMABicmlkETBwRGF5OWk3OWE5aFp5VjFwc3J0YwZhcHBfaWQQMjIyMDM5MTc4ODIwMDg5MgABHlFqY05_LD0cqJVjcTnq8dA5TVIfVr0b9NfHGjL_-7mikiIUjnkrGJQa0yFA_aem_ihmd2hy4EsV21Q-lKTnSKw#directions': scrape_prefabassociation_ua,
    'https://anippac.org.mx/asociados-2/': scrape_anippac,
    'https://www.pci.org/PCI/Directories/PCICertifiedPlants.aspx': scrape_pci,
    'https://mfgmodhome.org/about/member-directory/#/action/AdvancedSearch/cid/1898/id/401/listingtype/O/category/102%2c107%2c115': scrape_mfgmodhome,
    'https://ensun.io/search/prefabricated-home/china': scrape_ensun,
}

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
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    file_exists = output_csv.exists()
    
    try:
        with open(output_csv, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            if not file_exists:
                writer.writeheader()
            
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
    print('🚀 Starting deep research of companies from specific associations...\n')
    print(f"Using OpenAI API ({openai_config['name']})\n")
    
    # Input files
    existing_companies_csv = Path(__file__).parent.parent / 'maps' / 'public' / 'prefabworldtest_2.csv'
    output_csv = Path(__file__).parent.parent / 'maps' / 'public' / 'prefabassociated.csv'
    
    # Load existing companies
    print(f"📋 Loading existing companies from {existing_companies_csv.name}...")
    existing_webpages = load_existing_companies(existing_companies_csv)
    # Also load from output CSV
    existing_webpages.update(load_existing_companies(output_csv))
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
        'associations_processed': 0,
        'company_urls_found': 0,
        'companies_relevant': 0,
        'companies_existing': 0,
        'companies_new': 0,
        'companies_saved': 0,
        'geocoded': 0,
        'start_time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'errors': []
    }
    
    # Progress JSON file
    progress_json = Path(__file__).parent.parent / 'research_output' / 'association_research_progress.json'
    progress_json.parent.mkdir(parents=True, exist_ok=True)
    
    # Initialize Selenium driver if needed
    driver = None
    if selenium_available:
        try:
            driver = create_chrome_driver()
            print("✅ Selenium driver initialized")
        except Exception as e:
            print(f"⚠️  Could not initialize Selenium: {e}")
            driver = None
    
    # Process each association
    total_associations = len(ASSOCIATION_SCRAPERS)
    for assoc_idx, (association_url, scraper_func) in enumerate(ASSOCIATION_SCRAPERS.items(), 1):
        print(f"\n{'='*80}")
        print(f"[{assoc_idx}/{total_associations}] Processing association: {association_url}")
        print(f"{'='*80}\n")
        
        # Update progress JSON
        stats['current_association'] = association_url
        stats['current_association_index'] = assoc_idx
        stats['total_associations'] = total_associations
        save_progress_json(stats, progress_json)
        
        try:
            # Scrape company URLs
            company_urls = scraper_func(driver)
            stats['company_urls_found'] += len(company_urls)
            stats['associations_processed'] += 1
            stats['current_company_urls'] = len(company_urls)
            save_progress_json(stats, progress_json)
            
            if not company_urls:
                print(f"  ⚠️  No company URLs found")
                continue
            
            # Process each company URL
            for j, company_url in enumerate(company_urls, 1):
                stats['current_company'] = company_url
                stats['current_company_index'] = j
                stats['total_companies_in_association'] = len(company_urls)
                save_progress_json(stats, progress_json)
                print(f"\n  [{j}/{len(company_urls)}] Company: {company_url}")
                
                # Check if company already exists
                if check_company_exists(company_url, existing_webpages):
                    print(f"    ⏭️  Company already exists in database")
                    stats['companies_existing'] += 1
                    time.sleep(1)
                    continue
                
                # Check relevance
                is_relevant, company_name = check_company_relevance(company_url)
                if not is_relevant:
                    stats['companies_relevant'] += 1
                    time.sleep(2)
                    continue
                
                stats['companies_relevant'] += 1
                
                # Investigate webpage and extract information
                print(f"    🔬 Investigating company webpage...")
                extracted_data = investigate_webpage_and_extract_info(company_url, company_name)
                
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
                        company_url, initial_material, company_name or extracted_data.get('brand', 'Unknown')
                    )
                    extracted_data['main_structure_material'] = verified_material
                
                # Geocode address
                address = extracted_data.get('address', '')
                country = extracted_data.get('country', '')
                region = extracted_data.get('region', '')
                
                latitude = None
                longitude = None
                
                if address and address not in ['', 'NaN', 'null', 'None']:
                    print(f"    📍 Geocoding address...")
                    latitude, longitude = geocode_address(address, country, region)
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
                
                # Add to existing webpages set
                normalized_url = company_url.lower().rstrip('/').replace('http://', 'https://')
                existing_webpages.add(normalized_url)
                
                stats['companies_new'] += 1
                stats['companies_saved'] += 1
                save_progress_json(stats, progress_json)
                
                print(f"    ✅ Company saved successfully!")
                
                time.sleep(3)  # Rate limiting
            
        except Exception as e:
            print(f"  ❌ Error processing association: {e}")
            stats['errors'] = stats.get('errors', [])
            stats['errors'].append({
                'association': association_url,
                'error': str(e),
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
            })
            save_progress_json(stats, progress_json)
            import traceback
            traceback.print_exc()
        
        # Clear current association tracking
        stats.pop('current_association', None)
        stats.pop('current_company', None)
        stats.pop('current_company_urls', None)
        save_progress_json(stats, progress_json)
        
        time.sleep(2)  # Rate limiting between associations
    
    # Close Selenium driver if created
    if driver:
        try:
            driver.quit()
        except Exception:
            pass
    
    # Final progress update
    stats['end_time'] = time.strftime('%Y-%m-%d %H:%M:%S')
    stats['status'] = 'completed'
    stats.pop('current_association', None)
    stats.pop('current_company', None)
    stats.pop('current_company_urls', None)
    save_progress_json(stats, progress_json)
    
    # Print summary
    print(f"\n{'='*80}")
    print("📊 Summary")
    print(f"{'='*80}")
    print(f"Associations processed: {stats['associations_processed']}")
    print(f"Company URLs found: {stats['company_urls_found']}")
    print(f"Companies checked for relevance: {stats['companies_relevant']}")
    print(f"Companies already existing: {stats['companies_existing']}")
    print(f"New companies found: {stats['companies_new']}")
    print(f"Companies saved: {stats['companies_saved']}")
    print(f"Addresses geocoded: {stats['geocoded']}")
    print(f"Output file: {output_csv.name}")
    print(f"Progress JSON: {progress_json.name}")
    if stats.get('errors'):
        print(f"Errors encountered: {len(stats['errors'])}")
    print(f"{'='*80}\n")
    print("🎉 Processing complete!")
    
    # Print JSON summary
    print("\n📄 JSON Summary:")
    print(json.dumps(stats, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
