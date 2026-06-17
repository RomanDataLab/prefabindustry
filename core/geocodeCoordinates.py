#!/usr/bin/env python3
"""
Geocode coordinates for prefabworldfin.csv
- First try geocoding from address+country
- If that fails, use deep search on webpage to find address/coordinates
- Max 11 attempts per row for webpage navigation
"""
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
    'United States': 'English', 'USA': 'English',
    'United Kingdom': 'English', 'GBR': 'English',
    'Canada': 'English', 'CAN': 'English',
    'Germany': 'German', 'DEU': 'German',
    'France': 'French', 'FRA': 'French',
    'Spain': 'Spanish', 'ESP': 'Spanish',
    'Italy': 'Italian', 'ITA': 'Italian',
    'Portugal': 'Portuguese', 'PRT': 'Portuguese',
    'Netherlands': 'Dutch', 'NLD': 'Dutch',
    'Belgium': 'Dutch/French', 'BEL': 'Dutch/French',
    'Switzerland': 'German/French/Italian', 'CHE': 'German/French/Italian',
    'Austria': 'German', 'AUT': 'German',
    'Poland': 'Polish', 'POL': 'Polish',
    'Czech Republic': 'Czech', 'CZE': 'Czech',
    'Slovakia': 'Slovak', 'SVK': 'Slovak',
    'Hungary': 'Hungarian', 'HUN': 'Hungarian',
    'Romania': 'Romanian', 'ROU': 'Romanian',
    'Bulgaria': 'Bulgarian', 'BGR': 'Bulgarian',
    'Greece': 'Greek', 'GRC': 'Greek',
    'Sweden': 'Swedish', 'SWE': 'Swedish',
    'Norway': 'Norwegian', 'NOR': 'Norwegian',
    'Denmark': 'Danish', 'DNK': 'Danish',
    'Finland': 'Finnish', 'FIN': 'Finnish',
    'Latvia': 'Latvian', 'LVA': 'Latvian',
    'Lithuania': 'Lithuanian', 'LTU': 'Lithuanian',
    'Estonia': 'Estonian', 'EST': 'Estonian',
    'Russia': 'Russian', 'RUS': 'Russian',
    'Ukraine': 'Ukrainian', 'UKR': 'Ukrainian',
    'Japan': 'Japanese', 'JPN': 'Japanese',
    'China': 'Chinese', 'CHN': 'Chinese',
    'South Korea': 'Korean', 'KOR': 'Korean',
    'India': 'English', 'IND': 'English',
    'Brazil': 'Portuguese', 'BRA': 'Portuguese',
    'Mexico': 'Spanish', 'MEX': 'Spanish',
    'Argentina': 'Spanish', 'ARG': 'Spanish',
    'Chile': 'Spanish', 'CHL': 'Spanish',
    'Colombia': 'Spanish', 'COL': 'Spanish',
    'Australia': 'English', 'AUS': 'English',
    'New Zealand': 'English', 'NZL': 'English',
    'South Africa': 'English', 'ZAF': 'English',
    'Turkey': 'Turkish', 'TUR': 'Turkish',
    'Kazakhstan': 'Russian', 'KAZ': 'Russian',
    'Uzbekistan': 'Uzbek', 'UZB': 'Uzbek',
    'Luxembourg': 'French/German', 'LUX': 'French/German',
    'Slovenia': 'Slovenian', 'SVN': 'Slovenian',
    'Saudi Arabia': 'Arabic', 'SAU': 'Arabic',
    'United Arab Emirates': 'Arabic', 'ARE': 'Arabic',
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

def geocode_address(address: str, country: str = None, region: str = None) -> Tuple[Optional[float], Optional[float]]:
    """Geocode an address using OpenAI and geopy"""
    if not address or address.strip() in ['', 'NaN', 'null', 'None']:
        return None, None
    
    print(f"    📍 Geocoding address: {address}")
    
    # First, use OpenAI to format address optimally
    prompt = f"""You are a geocoding assistant. Given the following address information, format it optimally for geocoding and provide coordinates if possible.

Address: {address}
Country: {country or 'Unknown'}
Region: {region or 'Unknown'}

If you can determine the coordinates directly from your knowledge, provide them in this format:
LATITUDE,LONGITUDE

If you cannot determine coordinates directly, format the address optimally for geocoding in this format:
FORMATTED_ADDRESS

Return ONLY either:
- LATITUDE,LONGITUDE (if you have coordinates)
- FORMATTED_ADDRESS (if you need geocoding service)

Example outputs:
-48.123456,-123.654321
or
123 Main Street, City, State 12345, Country"""

    try:
        response = call_openai([{'role': 'user', 'content': prompt}])
        response = response.strip()
        
        # Check if response contains coordinates
        coord_match = re.search(r'(-?\d+\.?\d*),(-?\d+\.?\d*)', response)
        if coord_match:
            lat = float(coord_match.group(1))
            lon = float(coord_match.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                print(f"    ✅ Geocoded via AI: {lat}, {lon}")
                return lat, lon
        
        # Otherwise, use geopy if available
        formatted_address = response
        if geopy_available:
            try:
                geolocator = Nominatim(user_agent="prefab_geocoder")
                location = geolocator.geocode(formatted_address, timeout=15)
                if location:
                    print(f"    ✅ Geocoded via Nominatim: {location.latitude}, {location.longitude}")
                    return location.latitude, location.longitude
            except (GeocoderTimedOut, GeocoderServiceError):
                print(f"    ⚠️  Geocoding service timed out")
            except Exception as e:
                print(f"    ⚠️  Geocoding error: {e}")
        
        print(f"    ⚠️  Could not geocode address")
        return None, None
    except Exception as e:
        print(f"  ⚠️  Error geocoding: {e}")
        return None, None

def fetch_webpage_content(url: str, timeout: int = 15) -> Tuple[Optional[str], Optional[BeautifulSoup], List[str]]:
    """Fetch webpage content and return text, soup, and links"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, timeout=timeout, headers=headers, allow_redirects=True)
        response.raise_for_status()
        
        # Parse HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract links
        links = []
        base_url = url
        for a_tag in soup.find_all('a', href=True):
            href = a_tag.get('href', '').strip()
            if href:
                absolute_url = urljoin(base_url, href)
                if absolute_url not in links:
                    links.append(absolute_url)
        
        # Remove script and style elements for text extraction
        soup_copy = BeautifulSoup(response.content, 'html.parser')
        for script in soup_copy(["script", "style"]):
            script.decompose()
        
        # Get text
        text = soup_copy.get_text(separator=' ', strip=True)
        
        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        # Limit to first 15000 characters
        return text[:15000], soup, links
    except Exception as e:
        print(f"    ⚠️  Error fetching webpage: {e}")
        return None, None, []

def find_relevant_links(webpage_content: str, links: List[str], base_url: str, language: str, visited_urls: set) -> List[str]:
    """Use AI to find relevant links for contact/address information"""
    # Filter out already visited links
    candidate_links = [link for link in links if link not in visited_urls]
    
    if not candidate_links:
        return []
    
    prompt = f"""You are analyzing a website to find links that are likely to contain contact information, address, or location details.

Base URL: {base_url}
Language: {language}

Page content (first 10000 chars):
{webpage_content[:10000] if webpage_content else 'No content available'}

Available links (first 50):
{chr(10).join(candidate_links[:50])}

Identify which links are most likely to contain:
- Contact information
- Address
- Location
- Office location
- "About Us" or "Company" pages (which often have addresses)
- "Find Us" or "Visit Us" pages
- Maps or location pages

Return ONLY a JSON array of the most relevant URLs (maximum 5), prioritized by likelihood of containing address/contact info:
["https://example.com/contact", "https://example.com/about", ...]

If no relevant links found, return: []

Return ONLY the JSON array, no explanations."""

    try:
        response = call_openai([{'role': 'user', 'content': prompt}])
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            relevant_links = json.loads(json_match.group(0))
            # Filter to only valid URLs that are in our candidate list
            valid_links = [link for link in relevant_links 
                          if isinstance(link, str) and 
                          (link.startswith('http://') or link.startswith('https://')) and
                          link in candidate_links]
            return valid_links[:5]  # Max 5 links
    except Exception as e:
        print(f"    ⚠️  Error finding relevant links: {e}")
    
    return []

def extract_address_from_content(webpage_content: str, brand: str, company_name: str, country: str, language: str, url: str) -> Optional[str]:
    """Extract address from webpage content using AI"""
    prompt = f"""You are extracting address information from a company website.

Company brand: {brand or 'Unknown'}
Company name: {company_name or 'Unknown'}
Country: {country or 'Unknown'}
Language: {language}
Page URL: {url}

Page content (first 12000 chars):
{webpage_content[:12000] if webpage_content else 'No content available'}

Extract the complete physical address (street address, city, postal code, country) if available.
Look for:
- Office address
- Head office address
- Factory address
- Mailing address
- Contact address

Return ONLY the complete address in this format:
Street Number Street Name, City, Postal Code, Country

If no address found, return exactly: null

Return ONLY the address or null, nothing else."""

    try:
        response = call_openai([{'role': 'user', 'content': prompt}])
        response = response.strip()
        
        if response and response.lower() not in ['null', 'none', '']:
            # Clean up response
            address = response.replace('"', '').replace("'", "").replace('`', '').strip()
            if address and len(address) > 10:  # Basic validation
                return address
    except Exception as e:
        print(f"    ⚠️  Error extracting address: {e}")
    
    return None

def extract_coordinates_from_content(webpage_content: str, url: str) -> Tuple[Optional[float], Optional[float]]:
    """Extract coordinates directly from webpage content"""
    # Look for common coordinate patterns
    patterns = [
        r'(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)',  # lat, lon
        r'lat[itude]*:\s*(-?\d+\.?\d*).*lon[gitude]*:\s*(-?\d+\.?\d*)',  # latitude: X, longitude: Y
        r'coordinates?[:\s]*(-?\d+\.?\d*)[,\s]+(-?\d+\.?\d*)',  # coordinates: X, Y
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, webpage_content, re.IGNORECASE)
        for match in matches:
            try:
                if isinstance(match, tuple):
                    lat = float(match[0])
                    lon = float(match[1])
                else:
                    continue
                
                # Validate coordinates
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    print(f"    ✅ Found coordinates in content: {lat}, {lon}")
                    return lat, lon
            except (ValueError, IndexError):
                continue
    
    return None, None

def deep_search_webpage_for_coordinates(webpage: str, brand: str, company_name: str, country: str, region: str, language: str, max_attempts: int = 11) -> Tuple[Optional[float], Optional[float]]:
    """Deep search webpage to find coordinates, navigating relevant pages"""
    if not webpage or webpage.strip() in ['', 'NaN', 'null', 'None']:
        return None, None
    
    print(f"    🔍 Deep searching webpage: {webpage}")
    
    visited_urls = set()
    urls_to_visit = [webpage]
    attempts = 0
    
    while urls_to_visit and attempts < max_attempts:
        attempts += 1
        current_url = urls_to_visit.pop(0)
        
        if current_url in visited_urls:
            continue
        
        visited_urls.add(current_url)
        print(f"    [{attempts}/{max_attempts}] Visiting: {current_url}")
        
        # Fetch page content
        webpage_content, soup, links = fetch_webpage_content(current_url)
        
        if not webpage_content:
            continue
        
        # Try to extract coordinates directly from content
        lat, lon = extract_coordinates_from_content(webpage_content, current_url)
        if lat is not None and lon is not None:
            return lat, lon
        
        # Try to extract address from content
        address = extract_address_from_content(webpage_content, brand, company_name, country, language, current_url)
        if address:
            print(f"    📍 Found address: {address}")
            lat, lon = geocode_address(address, country, region)
            if lat is not None and lon is not None:
                return lat, lon
        
        # If this is the first page (homepage), find relevant links to visit
        if attempts == 1 and links:
            relevant_links = find_relevant_links(webpage_content, links, current_url, language, visited_urls)
            if relevant_links:
                print(f"    🔗 Found {len(relevant_links)} relevant links to explore")
                urls_to_visit.extend(relevant_links[:max_attempts - attempts])  # Don't exceed max attempts
        
        time.sleep(1)  # Rate limiting
    
    print(f"    ⚠️  Could not find coordinates after {attempts} attempts")
    return None, None

def process_csv_file(csv_path: Path) -> None:
    """Process CSV file and geocode coordinates"""
    print(f"\n{'='*80}")
    print(f"📍 Geocoding coordinates for: {csv_path.name}")
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
    
    # Statistics
    stats = {
        'total': len(rows),
        'already_has_coords': 0,
        'geocoded_from_address': 0,
        'geocoded_from_webpage': 0,
        'failed': 0
    }
    
    # Process each row
    for i, row in enumerate(rows, 1):
        row_id = row.get('id', i)
        brand = row.get('brand', '')
        address = row.get('address', '')
        country = row.get('country', '')
        country_code = row.get('country_code', '')
        region = row.get('region', '')
        webpage = row.get('webpage', '')
        latitude = row.get('latitude', '')
        longitude = row.get('longitude', '')
        
        # Check if already has coordinates
        if latitude and str(latitude).strip() not in ['', 'NaN', 'null', 'None']:
            if longitude and str(longitude).strip() not in ['', 'NaN', 'null', 'None']:
                try:
                    lat_val = float(latitude)
                    lon_val = float(longitude)
                    if -90 <= lat_val <= 90 and -180 <= lon_val <= 180:
                        stats['already_has_coords'] += 1
                        continue
                except (ValueError, TypeError):
                    pass
        
        print(f"\n[{i}/{len(rows)}] Row {row_id}: {brand}")
        
        language = get_language_for_country(country, country_code)
        
        # Step 1: Try geocoding from address
        lat, lon = None, None
        if address and str(address).strip() not in ['', 'NaN', 'null', 'None']:
            lat, lon = geocode_address(address, country, region)
            if lat is not None and lon is not None:
                row['latitude'] = str(lat)
                row['longitude'] = str(lon)
                stats['geocoded_from_address'] += 1
                print(f"  ✅ Geocoded from address: {lat}, {lon}")
                time.sleep(1)  # Rate limiting
                continue
        
        # Step 2: Try deep search on webpage
        if webpage and str(webpage).strip() not in ['', 'NaN', 'null', 'None']:
            lat, lon = deep_search_webpage_for_coordinates(
                webpage, brand, row.get('head_office_legal_name', ''), 
                country, region, language, max_attempts=11
            )
            if lat is not None and lon is not None:
                row['latitude'] = str(lat)
                row['longitude'] = str(lon)
                stats['geocoded_from_webpage'] += 1
                print(f"  ✅ Geocoded from webpage: {lat}, {lon}")
            else:
                stats['failed'] += 1
                print(f"  ❌ Could not find coordinates")
        else:
            stats['failed'] += 1
            print(f"  ⚠️  No webpage available")
        
        time.sleep(2)  # Rate limiting between rows
    
    # Write updated CSV
    print(f"\n{'='*80}")
    print("💾 Saving updated CSV...")
    print(f"{'='*80}\n")
    
    # Create backup
    backup_path = csv_path.parent / f"{csv_path.stem}_backup_{int(time.time())}.csv"
    import shutil
    shutil.copy2(csv_path, backup_path)
    print(f"✅ Backup created: {backup_path.name}")
    
    # Write updated file
    try:
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"✅ Updated CSV saved: {csv_path.name}")
    except Exception as e:
        print(f"❌ Error writing CSV: {e}")
        return
    
    # Print statistics
    print(f"\n{'='*80}")
    print("📊 Statistics")
    print(f"{'='*80}")
    print(f"Total rows: {stats['total']}")
    print(f"Already had coordinates: {stats['already_has_coords']}")
    print(f"Geocoded from address: {stats['geocoded_from_address']}")
    print(f"Geocoded from webpage: {stats['geocoded_from_webpage']}")
    print(f"Failed: {stats['failed']}")
    print(f"{'='*80}\n")

def main():
    """Main function"""
    csv_path = Path(__file__).parent.parent / 'maps' / 'public' / 'prefabworldfin.csv'
    
    if not csv_path.exists():
        print(f"❌ CSV file not found: {csv_path}")
        sys.exit(1)
    
    process_csv_file(csv_path)

if __name__ == '__main__':
    main()
