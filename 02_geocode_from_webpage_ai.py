#!/usr/bin/env python3
"""
02_geocode_from_webpage_ai.py
Geocode companies where latitude/longitude are null in prefabworldfin_reducedby_1.csv.
Uses ai_openai via configix/apiManager.py with 3-step strategy:
  1) Find contacts, map, address on website (researching webpage)
  2) Look for Google/Bing/other map widget on webpage, extract coordinates
  3) Geocode [brand] + country + region (simulate Google Maps search)
  4) Skip if all fail
Saves result to prefabworldfin_reducedby_2.csv
"""
import sys
import re
import json
import time
from pathlib import Path
from typing import Optional, Tuple, List
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).parent))
from configix.apiManager import get_ai_provider

try:
    from openai import OpenAI
except ImportError:
    print("Error: openai package not installed. Run: pip install openai")
    sys.exit(1)

try:
    import pandas as pd
except ImportError:
    print("Error: pandas not installed. Run: pip install pandas")
    sys.exit(1)

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Error: requests and beautifulsoup4 required. Run: pip install requests beautifulsoup4")
    sys.exit(1)

try:
    from geopy.geocoders import ArcGIS, Nominatim
    from geopy.exc import GeocoderTimedOut, GeocoderServiceError
    geopy_available = True
except ImportError:
    geopy_available = False

# Initialize OpenAI
openai_config = get_ai_provider('ai_openai')
openai_client = OpenAI(api_key=openai_config['api_key'])

# Input/output paths
INPUT_CSV = Path(__file__).parent / 'maps' / 'public' / 'prefabworldfin_reducedby_1.csv'
OUTPUT_CSV = Path(__file__).parent / 'maps' / 'public' / 'prefabworldfin_reducedby_2.csv'


def _is_null(v) -> bool:
    """Check if value is null (empty, NaN, etc.)."""
    if pd.isna(v):
        return True
    s = str(v).strip()
    return s in ('', 'NaN', 'null', 'None', 'nan')


def _has_valid_coords(lat, lon) -> bool:
    """Check if lat/lon are valid non-null coordinates."""
    if _is_null(lat) or _is_null(lon):
        return False
    try:
        la, lo = float(lat), float(lon)
        return -90 <= la <= 90 and -180 <= lo <= 180
    except (ValueError, TypeError):
        return False


def call_openai(messages: List[dict], max_retries: int = 3) -> str:
    """Call OpenAI API with retry logic."""
    for i in range(max_retries):
        try:
            resp = openai_client.chat.completions.create(
                model='gpt-4o',
                messages=messages,
                temperature=0.3,
                max_tokens=2000
            )
            return resp.choices[0].message.content or ''
        except Exception as e:
            err = str(e).lower()
            if any(k in err for k in ['rate limit', 'quota', '429', 'resource_exhausted']):
                wait = min(60 * (i + 1), 300)
                print(f"  ⚠ Rate limit. Waiting {wait}s...")
                if i < max_retries - 1:
                    time.sleep(wait)
                    continue
            print(f"  ⚠ Attempt {i + 1}/{max_retries} failed: {e}")
            if i == max_retries - 1:
                raise
            time.sleep(2 * (i + 1))
    return ''


def fetch_webpage(url: str, timeout: int = 15) -> Tuple[Optional[str], Optional[BeautifulSoup], List[str]]:
    """Fetch webpage; return (text_content, soup, list_of_links)."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        r = requests.get(url, timeout=timeout, headers=headers, allow_redirects=True)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, 'html.parser')
        links = []
        for a in soup.find_all('a', href=True):
            href = a.get('href', '').strip()
            if href:
                abs_url = urljoin(url, href)
                if abs_url not in links:
                    links.append(abs_url)
        soup_clean = BeautifulSoup(r.content, 'html.parser')
        for tag in soup_clean(['script', 'style']):
            tag.decompose()
        text = soup_clean.get_text(separator=' ', strip=True)
        text = ' '.join(text.split())[:15000]
        return text, soup, links
    except Exception as e:
        print(f"    ⚠ Fetch error: {e}")
        return None, None, []


# --- Step 1: Research website for contacts, map, address ---

def find_relevant_links(text: str, links: List[str], base_url: str, visited: set) -> List[str]:
    """Use AI to pick links likely to have contact/address/map info."""
    candidates = [l for l in links if l not in visited and l.startswith(('http://', 'https://'))]
    if not candidates:
        return []
    prompt = f"""Base URL: {base_url}
Page content (first 8000 chars):
{text[:8000] if text else 'No content'}

Links (first 50):
{chr(10).join(candidates[:50])}

Which links likely contain: contact, address, map, office location, "find us", "visit us"?
Return ONLY a JSON array of up to 5 URLs: ["url1", "url2"]
If none relevant: []"""
    try:
        resp = call_openai([{'role': 'user', 'content': prompt}])
        m = re.search(r'\[[\s\S]*\]', resp)
        if m:
            arr = json.loads(m.group(0))
            return [u for u in arr if isinstance(u, str) and u in candidates][:5]
    except Exception:
        pass
    return []


def extract_address_from_content(text: str, brand: str, country: str, url: str) -> Optional[str]:
    """Use AI to extract physical address from page content."""
    prompt = f"""Brand: {brand}, Country: {country}, URL: {url}
Page content (first 10000 chars):
{text[:10000] if text else 'No content'}

Extract the complete physical address (street, city, postal code, country) for this company.
Return ONLY the address or exactly 'null' if not found."""
    try:
        resp = call_openai([{'role': 'user', 'content': prompt}])
        resp = resp.strip().replace('"', '').replace("'", "").replace('`', '').strip()
        if resp and resp.lower() != 'null' and len(resp) > 10:
            return resp
    except Exception:
        pass
    return None


def extract_coords_from_text(text: str) -> Tuple[Optional[float], Optional[float]]:
    """Extract lat/lon from plain text (regex)."""
    patterns = [
        r'(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)',
        r'lat[itude]*:\s*(-?\d+\.?\d*).*lon[gitude]*:\s*(-?\d+\.?\d*)',
        r'coordinates?[:\s]*(-?\d+\.?\d*)[,\s]+(-?\d+\.?\d*)',
    ]
    for pat in patterns:
        for m in re.finditer(pat, text or '', re.I):
            try:
                lat, lon = float(m.group(1)), float(m.group(2))
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    return lat, lon
            except (ValueError, IndexError):
                continue
    return None, None


# --- Step 2: Extract from map widget URLs (Google Maps, Bing, etc.) ---

def extract_coords_from_map_widgets(html_soup: BeautifulSoup, html_raw: str) -> Tuple[Optional[float], Optional[float]]:
    """Extract coordinates from Google/Bing map embed URLs in page."""
    # Collect all URLs from iframes and links
    urls = []
    if html_soup:
        for iframe in html_soup.find_all('iframe', src=True):
            urls.append(iframe.get('src', ''))
        for a in html_soup.find_all('a', href=True):
            urls.append(a.get('href', ''))
    if html_raw:
        urls.extend(re.findall(r'https?://[^\s"\'<>]+', html_raw))
    urls = list(set(urls))
    # Patterns: Google embed !3dLAT!4dLON, @lat,lng, center=lat,lon; Bing cp=lat~lon
    patterns = [
        (r'!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)', 1, 2),
        (r'@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)', 1, 2),
        (r'center=(-?[\d.]+),(-?[\d.]+)', 1, 2),
        (r'cp=(-?[\d.]+)~(-?[\d.]+)', 1, 2),  # Bing Maps
    ]
    for url in urls:
        url_lower = url.lower()
        if 'google' in url_lower or 'maps' in url_lower or 'bing' in url_lower:
            for pat, g1, g2 in patterns:
                m = re.search(pat, url, re.I)
                if m:
                    try:
                        lat = float(m.group(g1))
                        lon = float(m.group(g2))
                        if -90 <= lat <= 90 and -180 <= lon <= 180:
                            return lat, lon
                    except (ValueError, IndexError):
                        continue
    return None, None


def geocode_address(address: str, country: str = None, region: str = None) -> Tuple[Optional[float], Optional[float]]:
    """Geocode using geopy (ArcGIS/Nominatim)."""
    if not address or not address.strip():
        return None, None
    if not geopy_available:
        return None, None
    geolocator = ArcGIS()  # fallback to Nominatim if needed
    try:
        loc = geolocator.geocode(address, timeout=15)
        if loc:
            return loc.latitude, loc.longitude
    except Exception:
        try:
            geolocator = Nominatim(user_agent='prefab_geocoder')
            loc = geolocator.geocode(address, timeout=15)
            if loc:
                return loc.latitude, loc.longitude
        except Exception:
            pass
    return None, None


# --- Step 3: Geocode brand + country + region (simulate Google Maps search) ---

def geocode_brand_location(brand: str, country: str, region: str) -> Tuple[Optional[float], Optional[float]]:
    """Geocode 'brand, region, country' to approximate location (like Google Maps search)."""
    if _is_null(brand):
        return None, None
    parts = [str(brand).strip()]
    if not _is_null(region):
        parts.append(str(region).strip())
    if not _is_null(country):
        parts.append(str(country).strip())
    query = ', '.join(parts)
    return geocode_address(query, country, region)


def step1_webpage_research(row: dict) -> Tuple[Optional[float], Optional[float], str]:
    """Step 1: Research website for contacts, map, address."""
    webpage = row.get('webpage', '')
    if _is_null(webpage):
        return None, None, 'no_webpage'
    brand = row.get('brand', '') or ''
    company = row.get('head_office_legal_name', '') or brand
    country = row.get('country', '') or ''
    region = row.get('region', '') or ''

    visited = set()
    to_visit = [webpage.strip()]
    max_pages = 8

    for _ in range(max_pages):
        if not to_visit:
            break
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)

        text, soup, links = fetch_webpage(url)
        if not text and not soup:
            continue

        # Try coords in text
        lat, lon = extract_coords_from_text(text)
        if lat is not None:
            return lat, lon, 'coords_in_text'

        # Try map widgets (iframe src, links)
        html_for_regex = str(soup) if soup else ''
        lat, lon = extract_coords_from_map_widgets(soup, html_for_regex)
        if lat is not None:
            return lat, lon, 'map_widget'

        # Extract address via AI and geocode
        addr = extract_address_from_content(text, brand or company, country, url)
        if addr:
            lat, lon = geocode_address(addr, country, region)
            if lat is not None:
                return lat, lon, 'address_from_page'

        # Find relevant links (only on first page)
        if len(visited) == 1 and links:
            rel = find_relevant_links(text, links, url, visited)
            for link in rel[:3]:
                if link not in visited:
                    to_visit.append(link)

        time.sleep(1)

    return None, None, 'not_found'


def step2_map_widget(row: dict) -> Tuple[Optional[float], Optional[float], str]:
    """Step 2: Look for map widget on main webpage."""
    webpage = row.get('webpage', '')
    if _is_null(webpage):
        return None, None, 'no_webpage'
    try:
        r = requests.get(webpage.strip(), timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, 'html.parser')
        lat, lon = extract_coords_from_map_widgets(soup, r.text)
        if lat is not None:
            return lat, lon, 'map_widget'
    except Exception:
        pass
    return None, None, 'not_found'


def step3_brand_search(row: dict) -> Tuple[Optional[float], Optional[float], str]:
    """Step 3: Geocode brand + country + region."""
    brand = row.get('brand', '')
    country = row.get('country', '')
    region = row.get('region', '')
    if _is_null(brand):
        return None, None, 'no_brand'
    lat, lon = geocode_brand_location(brand, country, region)
    if lat is not None:
        return lat, lon, 'brand_geocoded'
    return None, None, 'not_found'


def find_geocoordinates(row: dict) -> Tuple[Optional[float], Optional[float], str]:
    """Run 3-step strategy: 1) website research, 2) map widget, 3) brand search. Returns (lat, lon, method)."""
    # Step 1: research website
    lat, lon, method = step1_webpage_research(row)
    if lat is not None:
        return lat, lon, f'step1_{method}'
    # Step 2: map widget (redundant if step1 already checked, but explicit)
    lat, lon, method = step2_map_widget(row)
    if lat is not None:
        return lat, lon, f'step2_{method}'
    # Step 3: brand + country + region
    lat, lon, method = step3_brand_search(row)
    if lat is not None:
        return lat, lon, f'step3_{method}'
    return None, None, 'skipped'


def main():
    if not INPUT_CSV.exists():
        print(f"Error: input CSV not found: {INPUT_CSV}")
        sys.exit(1)

    print(f"Reading {INPUT_CSV.name}...")
    df = pd.read_csv(INPUT_CSV)
    total = len(df)

    # Ensure columns exist
    if 'latitude' not in df.columns:
        df['latitude'] = pd.NA
    if 'longitude' not in df.columns:
        df['longitude'] = pd.NA

    needs_geocode = []
    for idx, row in df.iterrows():
        lat, lon = row.get('latitude'), row.get('longitude')
        if not _has_valid_coords(lat, lon):
            needs_geocode.append(idx)

    print(f"Total rows: {total}")
    print(f"Already have valid coords: {total - len(needs_geocode)}")
    print(f"Need geocoding: {len(needs_geocode)}\n")

    if not needs_geocode:
        print("Nothing to geocode. Copying to output.")
        df.to_csv(OUTPUT_CSV, index=False)
        return

    stats = {'step1': 0, 'step2': 0, 'step3': 0, 'skipped': 0}
    for i, idx in enumerate(needs_geocode):
        row = df.iloc[idx].to_dict()
        brand = row.get('brand', '') or f'Row {idx}'
        print(f"[{i + 1}/{len(needs_geocode)}] {brand}")
        lat, lon, method = find_geocoordinates(row)
        if lat is not None and lon is not None:
            df.at[idx, 'latitude'] = lat
            df.at[idx, 'longitude'] = lon
            if method.startswith('step1'):
                stats['step1'] += 1
                print(f"  OK (step1): {lat}, {lon}")
            elif method.startswith('step2'):
                stats['step2'] += 1
                print(f"  OK (step2): {lat}, {lon}")
            elif method.startswith('step3'):
                stats['step3'] += 1
                print(f"  OK (step3): {lat}, {lon}")
        else:
            stats['skipped'] += 1
            print(f"  Skipped")
        time.sleep(1.5)

    df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved to {OUTPUT_CSV.name}")
    print(f"Step1 (website): {stats['step1']}, Step2 (widget): {stats['step2']}, Step3 (brand): {stats['step3']}, Skipped: {stats['skipped']}")


if __name__ == '__main__':
    main()
