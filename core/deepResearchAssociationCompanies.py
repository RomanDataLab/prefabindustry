#!/usr/bin/env python3
# Deep research of companies from association member directories using OpenAI
import sys
import os
import json
import csv
import time
import re
import requests
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from urllib.parse import urlparse, urljoin, urlunparse
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
        
        # Limit to first 15000 characters to avoid token limits
        return text[:15000]
    except Exception as e:
        print(f"  ⚠️  Error fetching webpage: {e}")
        return None

def find_pagination_links(soup: BeautifulSoup, base_url: str) -> List[str]:
    """Find pagination links (next page, page numbers, etc.)"""
    pagination_links = []
    visited_urls = set()
    
    # Common pagination patterns
    pagination_selectors = [
        'a[class*="next"]',
        'a[class*="page"]',
        'a[aria-label*="next"]',
        'a[aria-label*="Next"]',
        'a[title*="next"]',
        'a[title*="Next"]',
        '.pagination a',
        '.pager a',
        '.page-nav a',
        'nav[class*="pagination"] a',
        'nav[class*="pager"] a',
    ]
    
    # Find pagination elements
    for selector in pagination_selectors:
        try:
            elements = soup.select(selector)
            for elem in elements:
                href = elem.get('href', '').strip()
                text = elem.get_text(strip=True).lower()
                
                if href:
                    absolute_url = urljoin(base_url, href)
                    normalized_url = absolute_url.lower().rstrip('/')
                    
                    # Check if it's a pagination link
                    if (normalized_url not in visited_urls and 
                        normalized_url != base_url.lower().rstrip('/') and
                        (any(keyword in text for keyword in ['next', 'page', '>', '»', 'forward']) or
                         any(keyword in href.lower() for keyword in ['page=', 'p=', 'offset=', 'start=']) or
                         text.isdigit())):
                        pagination_links.append(absolute_url)
                        visited_urls.add(normalized_url)
        except Exception:
            continue
    
    # Also check for numbered page links
    try:
        for a_tag in soup.find_all('a', href=True):
            href = a_tag.get('href', '').strip()
            text = a_tag.get_text(strip=True)
            
            if href and text.isdigit():
                absolute_url = urljoin(base_url, href)
                normalized_url = absolute_url.lower().rstrip('/')
                
                if (normalized_url not in visited_urls and 
                    normalized_url != base_url.lower().rstrip('/') and
                    any(keyword in href.lower() for keyword in ['page=', 'p=', 'offset=', 'start='])):
                    pagination_links.append(absolute_url)
                    visited_urls.add(normalized_url)
    except Exception:
        pass
    
    return pagination_links

def extract_company_links_from_page(soup: BeautifulSoup, webpage_content: str, association_url: str) -> List[str]:
    """Extract company links from a single page"""
    # Find all links
    links = []
    for a_tag in soup.find_all('a', href=True):
        href = a_tag.get('href', '').strip()
        if href:
            # Convert relative URLs to absolute
            absolute_url = urljoin(association_url, href)
            links.append(absolute_url)
    
    # Use AI to identify which links are likely company websites
    print(f"    🤖 Analyzing {len(links)} links to find company websites...")
    
    prompt = f"""You are analyzing links from an association member directory page to identify which links point to company websites (manufacturers of prefab/modular homes or panels).

Association page URL: {association_url}

Page content (first 15000 chars):
{webpage_content[:15000] if webpage_content else 'No content available'}

Found links (first 150):
{chr(10).join(links[:150])}

Identify which links are likely company websites for manufacturers of:
- Prefab/prefabricated homes
- Modular homes
- Panelized construction companies
- Off-site construction manufacturers
- Timber frame/prefab house builders

Return ONLY a JSON array of URLs that are likely company websites, in this format:
["https://company1.com", "https://company2.com", ...]

If no company links are found, return: []

Return ONLY the JSON array, no explanations."""
    
    try:
        response = call_openai([{'role': 'user', 'content': prompt}])
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            company_links = json.loads(json_match.group(0))
            # Filter to only valid URLs
            valid_links = [link for link in company_links if isinstance(link, str) and (link.startswith('http://') or link.startswith('https://'))]
            return valid_links
    except Exception as e:
        print(f"    ⚠️  Error extracting company links: {e}")
    
    return []

def extract_company_links_from_association(association_url: str) -> List[str]:
    """Extract company links from an association member directory page, handling pagination"""
    print(f"  📄 Fetching association page: {association_url}")
    
    all_company_links = []
    visited_pages = set()
    pages_to_visit = [association_url]
    page_number = 1
    
    while pages_to_visit:
        current_url = pages_to_visit.pop(0)
        normalized_url = current_url.lower().rstrip('/')
        
        if normalized_url in visited_pages:
            continue
        
        visited_pages.add(normalized_url)
        print(f"  📄 Page {page_number}: {current_url}")
        
        # Fetch page content
        webpage_content = fetch_webpage_content(current_url)
        if not webpage_content:
            print(f"    ⚠️  Could not fetch page content")
            continue
        
        # Parse HTML
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(current_url, timeout=15, headers=headers, allow_redirects=True)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract company links from this page
            page_company_links = extract_company_links_from_page(soup, webpage_content, current_url)
            all_company_links.extend(page_company_links)
            print(f"    ✅ Found {len(page_company_links)} company links on this page")
            
            # Find pagination links (only on first page or if explicitly checking)
            if page_number == 1 or len(pages_to_visit) == 0:
                pagination_links = find_pagination_links(soup, current_url)
                
                if pagination_links:
                    print(f"    🔍 Found {len(pagination_links)} pagination links")
                    
                    # Use AI to verify which pagination links are valid next pages
                    prompt = f"""You are analyzing pagination links from an association member directory page.

Current page URL: {current_url}

Found pagination links:
{chr(10).join(pagination_links[:20])}

Identify which links are valid "next page" or additional page links for the member directory (not other sections of the website).

Return ONLY a JSON array of URLs that are valid pagination links to other pages of the member directory, in this format:
["https://example.com/page2", "https://example.com/page3", ...]

If no valid pagination links are found, return: []

Return ONLY the JSON array, no explanations."""
                    
                    try:
                        response = call_openai([{'role': 'user', 'content': prompt}])
                        json_match = re.search(r'\[[\s\S]*\]', response)
                        if json_match:
                            valid_pagination_links = json.loads(json_match.group(0))
                            # Filter to only valid URLs
                            valid_pagination = [link for link in valid_pagination_links 
                                              if isinstance(link, str) and 
                                              (link.startswith('http://') or link.startswith('https://'))]
                            
                            # Add valid pagination links to queue
                            for pag_link in valid_pagination:
                                normalized_pag = pag_link.lower().rstrip('/')
                                if normalized_pag not in visited_pages and pag_link not in pages_to_visit:
                                    pages_to_visit.append(pag_link)
                            
                            if valid_pagination:
                                print(f"    ✅ Added {len(valid_pagination)} pagination pages to queue")
                    except Exception as e:
                        print(f"    ⚠️  Error analyzing pagination: {e}")
                        # Fallback: add all pagination links
                        for pag_link in pagination_links[:10]:  # Limit to prevent infinite loops
                            normalized_pag = pag_link.lower().rstrip('/')
                            if normalized_pag not in visited_pages and pag_link not in pages_to_visit:
                                pages_to_visit.append(pag_link)
            
            page_number += 1
            time.sleep(2)  # Rate limiting between pages
            
            # Safety limit: don't process more than 50 pages per association
            if page_number > 50:
                print(f"    ⚠️  Reached page limit (50), stopping pagination")
                break
                
        except Exception as e:
            print(f"    ⚠️  Error parsing page: {e}")
            continue
    
    # Remove duplicates while preserving order
    seen = set()
    unique_links = []
    for link in all_company_links:
        normalized = link.lower().rstrip('/').replace('http://', 'https://')
        if normalized not in seen:
            seen.add(normalized)
            unique_links.append(link)
    
    print(f"  ✅ Total: Found {len(unique_links)} unique company links across {page_number - 1} page(s)")
    return unique_links

def check_company_relevance(company_url: str) -> Tuple[bool, Optional[str]]:
    """Check if a company URL is relevant (prefab/modular manufacturer)"""
    print(f"    🔍 Checking relevance: {company_url}")
    
    webpage_content = fetch_webpage_content(company_url)
    
    prompt = f"""You are checking if a company website is relevant for a database of prefab/modular home manufacturers.

Company URL: {company_url}

Webpage content (first 15000 chars):
{webpage_content[:15000] if webpage_content else 'Could not fetch webpage content - use your knowledge to search'}

Determine if this company manufactures:
- Prefab/prefabricated homes
- Modular homes
- Panelized construction
- Off-site construction
- Timber frame/prefab houses
- Prefab panels/modules

If YES, return a JSON object:
{{
  "relevant": true,
  "company_name": "company name or brand",
  "reason": "brief reason why it's relevant"
}}

If NO (not a prefab/modular manufacturer), return:
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

def investigate_webpage_and_extract_info(webpage: str, company_name: str) -> Dict:
    """Investigate webpage content and extract company information"""
    
    # Fetch webpage content
    print(f"    📄 Fetching webpage content...")
    webpage_content = fetch_webpage_content(webpage)
    
    if not webpage_content:
        print(f"    ⚠️  Could not fetch webpage content, using AI search only")
        webpage_content = ""
    
    # Determine country from URL or domain
    domain = urlparse(webpage).netloc.lower()
    country = None
    country_code = None
    
    # Try to infer country from domain
    country_domains = {
        '.de': ('Germany', 'DEU'),
        '.fr': ('France', 'FRA'),
        '.it': ('Italy', 'ITA'),
        '.es': ('Spain', 'ESP'),
        '.nl': ('Netherlands', 'NLD'),
        '.be': ('Belgium', 'BEL'),
        '.at': ('Austria', 'AUT'),
        '.se': ('Sweden', 'SWE'),
        '.dk': ('Denmark', 'DNK'),
        '.fi': ('Finland', 'FIN'),
        '.pl': ('Poland', 'POL'),
        '.cz': ('Czech Republic', 'CZE'),
        '.pt': ('Portugal', 'PRT'),
        '.gr': ('Greece', 'GRC'),
        '.ie': ('Ireland', 'IRL'),
        '.ro': ('Romania', 'ROU'),
        '.hu': ('Hungary', 'HUN'),
        '.sk': ('Slovakia', 'SVK'),
        '.bg': ('Bulgaria', 'BGR'),
        '.hr': ('Croatia', 'HRV'),
        '.si': ('Slovenia', 'SVN'),
        '.lt': ('Lithuania', 'LTU'),
        '.lv': ('Latvia', 'LVA'),
        '.ee': ('Estonia', 'EST'),
        '.ch': ('Switzerland', 'CHE'),
        '.no': ('Norway', 'NOR'),
        '.uk': ('United Kingdom', 'GBR'),
        '.ca': ('Canada', 'CAN'),
        '.au': ('Australia', 'AUS'),
        '.nz': ('New Zealand', 'NZL'),
        '.jp': ('Japan', 'JPN'),
        '.cn': ('China', 'CHN'),
        '.in': ('India', 'IND'),
        '.tr': ('Turkey', 'TUR'),
        '.br': ('Brazil', 'BRA'),
        '.mx': ('Mexico', 'MEX'),
        '.cl': ('Chile', 'CHL'),
        '.ar': ('Argentina', 'ARG'),
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

Webpage content (first 15000 chars):
{webpage_content[:15000] if webpage_content else 'Could not fetch webpage content - use your knowledge to search'}

Extract and fill in ALL available information. Return ONLY valid JSON in this exact format (use null for missing data, NaN for numeric fields that cannot be determined):

{{
  "brand": "brand name or trading name (the name customers know them by)",
  "head_office_legal_name": "full legal registered company name",
  "address": "complete address: street number, street name, city, postal code, country",
  "country": "country name",
  "country_code": "ISO 3166-1 alpha-3 country code",
  "region": "state/province/region name",
  "webpage": "main website homepage URL (https://...) - use the provided URL",
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
                print(f"    ⚠️  Error parsing JSON: {e}")
                return {}
        return {}
    except Exception as e:
        print(f"    ⚠️  Error investigating webpage: {e}")
        return {}

def double_check_structure_material(webpage: str, initial_material: str, company_name: str) -> str:
    """Double-check the main structure material by analyzing overall webpage content and house model descriptions"""
    print(f"    🔬 Double-checking structure material: {initial_material}")
    
    webpage_content = fetch_webpage_content(webpage)
    
    prompt = f"""You are verifying the main structure material for a prefab/modular home manufacturer.

Company: {company_name}
Website: {webpage}
Initial assessment: {initial_material}

Webpage content (first 20000 chars):
{webpage_content[:20000] if webpage_content else 'Could not fetch webpage content - use your knowledge to search'}

Analyze the overall company webpage content AND descriptions of house models to determine the PRIMARY construction material used.

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
    print('🚀 Starting deep research of companies from association directories...\n')
    print(f"Using OpenAI API ({openai_config['name']})\n")
    
    # Input files
    association_links_json = Path(__file__).parent.parent / 'research_output' / 'association_member_directory_links.json'
    existing_companies_csv = Path(__file__).parent.parent / 'maps' / 'public' / 'prefabworldtest_2.csv'
    output_csv = Path(__file__).parent.parent / 'maps' / 'public' / 'prefabassociated.csv'
    
    # Load association links
    if not association_links_json.exists():
        print(f"❌ Association links file not found: {association_links_json}")
        return
    
    try:
        with open(association_links_json, 'r', encoding='utf-8') as f:
            association_links = json.load(f)
    except Exception as e:
        print(f"❌ Error loading association links: {e}")
        return
    
    print(f"✅ Loaded {len(association_links)} association links\n")
    
    # Load existing companies
    print(f"📋 Loading existing companies from {existing_companies_csv.name}...")
    existing_webpages = load_existing_companies(existing_companies_csv)
    print(f"✅ Found {len(existing_webpages)} existing companies\n")
    
    # Define CSV fieldnames (matching prefabworldtest_2.csv schema + geocoordinates)
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
        'company_links_found': 0,
        'companies_relevant': 0,
        'companies_existing': 0,
        'companies_new': 0,
        'companies_saved': 0,
        'geocoded': 0
    }
    
    # Track associations with zero company links
    zero_result_associations = []
    
    # Process each association link
    for i, association_url in enumerate(association_links, 1):
        print(f"\n{'='*80}")
        print(f"[{i}/{len(association_links)}] Processing association: {association_url}")
        print(f"{'='*80}\n")
        
        # Extract company links from association page
        company_links = extract_company_links_from_association(association_url)
        stats['company_links_found'] += len(company_links)
        
        if not company_links:
            print(f"  ⚠️  No company links found")
            zero_result_associations.append(association_url)
            time.sleep(2)  # Rate limiting
            continue
        
        stats['associations_processed'] += 1
        
        # Process each company link
        for j, company_url in enumerate(company_links, 1):
            print(f"\n  [{j}/{len(company_links)}] Company: {company_url}")
            
            # Check if company already exists
            if check_company_exists(company_url, existing_webpages):
                print(f"    ⏭️  Company already exists in database")
                stats['companies_existing'] += 1
                time.sleep(1)  # Rate limiting
                continue
            
            # Check relevance
            is_relevant, company_name = check_company_relevance(company_url)
            if not is_relevant:
                stats['companies_relevant'] += 1
                time.sleep(2)  # Rate limiting
                continue
            
            stats['companies_relevant'] += 1
            
            # Investigate webpage and extract information
            print(f"    🔬 Investigating company webpage...")
            extracted_data = investigate_webpage_and_extract_info(company_url, company_name)
            
            if not extracted_data:
                print(f"    ⚠️  Could not extract company data")
                time.sleep(2)  # Rate limiting
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
            
            # Set configurator to NaN (will be checked separately if needed)
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
            
            # Add to existing webpages set to avoid duplicates in same run
            normalized_url = company_url.lower().rstrip('/').replace('http://', 'https://')
            existing_webpages.add(normalized_url)
            
            stats['companies_new'] += 1
            stats['companies_saved'] += 1
            
            print(f"    ✅ Company saved successfully!")
            
            time.sleep(3)  # Rate limiting between companies
        
        # Progress update
        print(f"\n💾 Progress: {i}/{len(association_links)} associations processed")
        print(f"   Stats: {stats['companies_saved']} companies saved, {stats['companies_existing']} already existed")
        time.sleep(2)  # Rate limiting between associations
    
    # Print summary
    print(f"\n{'='*80}")
    print("📊 Summary")
    print(f"{'='*80}")
    print(f"Associations processed: {stats['associations_processed']}")
    print(f"Company links found: {stats['company_links_found']}")
    print(f"Companies checked for relevance: {stats['companies_relevant']}")
    print(f"Companies already existing: {stats['companies_existing']}")
    print(f"New companies found: {stats['companies_new']}")
    print(f"Companies saved: {stats['companies_saved']}")
    print(f"Addresses geocoded: {stats['geocoded']}")
    print(f"Output file: {output_csv.name}")
    print(f"{'='*80}\n")
    
    # Report associations with zero company links
    if zero_result_associations:
        print(f"\n{'='*80}")
        print("⚠️  Associations with Zero Company Webpages")
        print(f"{'='*80}")
        print(f"Total associations with zero results: {len(zero_result_associations)}\n")
        for idx, url in enumerate(zero_result_associations, 1):
            print(f"  {idx}. {url}")
        print(f"\n{'='*80}\n")
    else:
        print(f"\n✅ All associations provided at least one company link\n")
    
    print("🎉 Processing complete!")

if __name__ == '__main__':
    main()
