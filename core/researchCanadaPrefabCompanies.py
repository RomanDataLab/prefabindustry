#!/usr/bin/env python3
# Deep continuous research of Canada prefab home companies using OpenAI
import sys
import os
import json
import csv
import time
import re
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from collections import deque

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

# Initialize OpenAI with API key from configix
openai_config = get_ai_provider('ai_openai')
openai_client = OpenAI(api_key=openai_config['api_key'])

# Output directory
output_dir = Path(__file__).parent.parent / 'research_output'
output_dir.mkdir(exist_ok=True)
csv_path = output_dir / 'canada_prefab_core.csv'

# Store all companies
all_companies = []
company_id = 1

# Rate limiting configuration
# OpenAI API typical quotas (adjust based on your tier):
# Free tier: ~3 RPM, ~200 RPD
# Paid tier: ~500 RPM, ~10000 RPD (varies by model)
RATE_LIMIT_CONFIG = {
    'requests_per_minute': 50,  # Conservative limit (adjust based on your API tier)
    'requests_per_hour': 2000,  # Conservative limit
    'requests_per_day': 10000,   # Conservative limit
    'min_delay_between_requests': 1.2,  # Minimum seconds between requests
    'backoff_multiplier': 2.0,   # Exponential backoff multiplier
    'max_backoff_seconds': 300,  # Maximum backoff time (5 minutes)
}

# Rate limiter class
class RateLimiter:
    """Track and enforce API rate limits"""
    def __init__(self, config: Dict):
        self.config = config
        self.request_times = deque()  # Track request timestamps
        self.hourly_requests = deque()  # Track requests in last hour
        self.daily_requests = deque()  # Track requests today
        self.last_request_time = 0
        self.consecutive_errors = 0
        
    def _clean_old_requests(self):
        """Remove old request timestamps outside the time windows"""
        now = time.time()
        
        # Remove requests older than 1 minute
        while self.request_times and now - self.request_times[0] > 60:
            self.request_times.popleft()
        
        # Remove requests older than 1 hour
        while self.hourly_requests and now - self.hourly_requests[0] > 3600:
            self.hourly_requests.popleft()
        
        # Remove requests older than 24 hours
        while self.daily_requests and now - self.daily_requests[0] > 86400:
            self.daily_requests.popleft()
    
    def wait_if_needed(self):
        """Wait if we're approaching rate limits"""
        self._clean_old_requests()
        now = time.time()
        
        # Check per-minute limit
        if len(self.request_times) >= self.config['requests_per_minute']:
            oldest_request = self.request_times[0]
            wait_time = 60 - (now - oldest_request) + 1  # Add 1 second buffer
            if wait_time > 0:
                print(f"  ⏳ Rate limit: Waiting {wait_time:.1f}s (RPM limit: {len(self.request_times)}/{self.config['requests_per_minute']})")
                time.sleep(wait_time)
                self._clean_old_requests()
        
        # Check per-hour limit
        if len(self.hourly_requests) >= self.config['requests_per_hour']:
            oldest_request = self.hourly_requests[0]
            wait_time = 3600 - (now - oldest_request) + 1
            if wait_time > 0:
                print(f"  ⏳ Rate limit: Waiting {wait_time/60:.1f} minutes (RPH limit: {len(self.hourly_requests)}/{self.config['requests_per_hour']})")
                time.sleep(wait_time)
                self._clean_old_requests()
        
        # Check per-day limit
        if len(self.daily_requests) >= self.config['requests_per_day']:
            oldest_request = self.daily_requests[0]
            wait_time = 86400 - (now - oldest_request) + 1
            if wait_time > 0:
                print(f"  ⏳ Rate limit: Waiting {wait_time/3600:.1f} hours (RPD limit: {len(self.daily_requests)}/{self.config['requests_per_day']})")
                time.sleep(wait_time)
                self._clean_old_requests()
        
        # Enforce minimum delay between requests
        time_since_last = now - self.last_request_time
        min_delay = self.config['min_delay_between_requests']
        if time_since_last < min_delay:
            wait_time = min_delay - time_since_last
            time.sleep(wait_time)
            now = time.time()
        
        # Record this request
        self.request_times.append(now)
        self.hourly_requests.append(now)
        self.daily_requests.append(now)
        self.last_request_time = now
    
    def handle_rate_limit_error(self, error: Exception) -> float:
        """Handle rate limit errors with exponential backoff"""
        self.consecutive_errors += 1
        
        # Calculate backoff time
        backoff_time = min(
            self.config['min_delay_between_requests'] * (self.config['backoff_multiplier'] ** self.consecutive_errors),
            self.config['max_backoff_seconds']
        )
        
        print(f"  ⚠️  Rate limit error (attempt {self.consecutive_errors}): Waiting {backoff_time:.1f}s before retry...")
        return backoff_time
    
    def reset_error_count(self):
        """Reset consecutive error count on successful request"""
        self.consecutive_errors = 0
    
    def get_stats(self) -> Dict:
        """Get current rate limit statistics"""
        self._clean_old_requests()
        return {
            'requests_last_minute': len(self.request_times),
            'requests_last_hour': len(self.hourly_requests),
            'requests_last_day': len(self.daily_requests),
            'consecutive_errors': self.consecutive_errors
        }

# Initialize rate limiter
rate_limiter = RateLimiter(RATE_LIMIT_CONFIG)

# Canadian provinces and territories
CANADA_PROVINCES = [
    {'code': 'AB', 'name': 'Alberta'},
    {'code': 'BC', 'name': 'British Columbia'},
    {'code': 'MB', 'name': 'Manitoba'},
    {'code': 'NB', 'name': 'New Brunswick'},
    {'code': 'NL', 'name': 'Newfoundland and Labrador'},
    {'code': 'NS', 'name': 'Nova Scotia'},
    {'code': 'NT', 'name': 'Northwest Territories'},
    {'code': 'NU', 'name': 'Nunavut'},
    {'code': 'ON', 'name': 'Ontario'},
    {'code': 'PE', 'name': 'Prince Edward Island'},
    {'code': 'QC', 'name': 'Quebec'},
    {'code': 'SK', 'name': 'Saskatchewan'},
    {'code': 'YT', 'name': 'Yukon'}
]

def call_openai(prompt: str, max_retries: int = 3) -> str:
    """Call OpenAI API with retry logic and rate limiting"""
    for i in range(max_retries):
        try:
            # Wait if needed to respect rate limits
            rate_limiter.wait_if_needed()
            
            response = openai_client.chat.completions.create(
                model='gpt-4o',
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.7,
                max_tokens=4000
            )
            
            # Reset error count on success
            rate_limiter.reset_error_count()
            return response.choices[0].message.content
            
        except Exception as error:
            error_str = str(error).lower()
            
            # Check for rate limit errors
            if any(keyword in error_str for keyword in ['rate limit', 'quota', '429', 'resource_exhausted', 'too many requests']):
                backoff_time = rate_limiter.handle_rate_limit_error(error)
                if i < max_retries - 1:
                    time.sleep(backoff_time)
                    continue
                else:
                    print(f"  ❌ Rate limit exceeded after {max_retries} attempts. Please wait and try again later.")
                    raise Exception(f"Rate limit exceeded: {error}")
            
            # Other errors
            print(f"  ⚠️  Attempt {i + 1}/{max_retries} failed: {error}")
            if i == max_retries - 1:
                raise
            
            # Exponential backoff for other errors
            backoff_time = min(2 * (i + 1), 60)
            time.sleep(backoff_time)

def get_companies_for_province_deep(province: Dict, existing_companies: List[str], iteration: int) -> List[Dict]:
    """Deep research: Get additional companies for a province, excluding already found ones"""
    existing_names = ', '.join(existing_companies[:20]) if existing_companies else "none"
    
    prompt = f"""You are a research expert specializing in prefabricated/modular home companies in {province['name']}, Canada.

This is iteration {iteration} of deep research. We have already found these companies: {existing_names if existing_companies else "none"}

Your task is to find ADDITIONAL companies in {province['name']} that we haven't found yet. Do NOT repeat companies we already have.

Search for companies that manufacture, build, or sell prefab homes:
- Prefabricated home manufacturers
- Modular home builders
- Manufactured home companies
- Kit home suppliers
- Panelized home builders
- Pre-cut home companies
- System-built home manufacturers
- Factory-built home companies
- Off-site construction companies
- Pre-engineered home builders
- Prefab home manufacturers
- Modular builders
- Industrialized home manufacturers

IMPORTANT:
- Exclude companies we already found: {existing_names if existing_companies else "none"}
- Search for DIFFERENT companies - smaller, regional, or lesser-known ones
- Include companies headquartered in {province['name']}
- Include companies with manufacturing facilities in {province['name']}
- Include companies that primarily serve {province['name']} market

Return ONLY a JSON array with NEW companies (at least 5-15 if they exist). Format:
[{{"name": "New Company Name", "province": "{province['name']}"}}, {{"name": "Another New Company", "province": "{province['name']}"}}, ...]

If you cannot find any NEW companies, return an empty array [].

Return ONLY the JSON array, no explanations or additional text."""

    try:
        response = call_openai(prompt)
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            try:
                companies = json.loads(json_match.group(0))
                companies_list = [{'name': c.get('name', ''), 'province': province['name']} for c in companies if c.get('name')]
                # Filter out duplicates with existing companies
                existing_lower = {name.lower().strip() for name in existing_companies}
                companies_list = [c for c in companies_list if c['name'].lower().strip() not in existing_lower]
                return companies_list
            except json.JSONDecodeError as e:
                print(f"  ⚠️  Error parsing JSON in iteration {iteration}: {e}")
                companies_list = extract_company_names(response, province['name'])
                existing_lower = {name.lower().strip() for name in existing_companies}
                companies_list = [c for c in companies_list if c['name'].lower().strip() not in existing_lower]
                return companies_list
        companies_list = extract_company_names(response, province['name'])
        existing_lower = {name.lower().strip() for name in existing_companies}
        companies_list = [c for c in companies_list if c['name'].lower().strip() not in existing_lower]
        return companies_list
    except Exception as error:
        print(f"  ⚠️  Error in deep research iteration {iteration}: {error}")
        return []

def get_companies_for_province(province: Dict) -> List[Dict]:
    """Get companies for a specific Canadian province with deep research (up to 15 iterations)"""
    all_found_companies = []
    max_iterations = 15
    
    # Initial discovery
    print(f"  🔍 Initial discovery...")
    prompt = f"""You are a research expert specializing in prefabricated/modular home companies in {province['name']}, Canada.

Your task is to provide a COMPREHENSIVE list of ALL companies in {province['name']} that manufacture, build, or sell prefab homes. This includes:

TYPES OF COMPANIES TO INCLUDE:
- Prefabricated home manufacturers
- Modular home builders
- Manufactured home companies
- Kit home suppliers
- Panelized home builders
- Pre-cut home companies
- System-built home manufacturers
- Factory-built home companies
- Off-site construction companies
- Pre-engineered home builders
- Prefab home manufacturers
- Modular builders
- Industrialized home manufacturers

COMPANY SIZES TO INCLUDE:
- Large national manufacturers
- Medium-sized regional companies
- Small local builders
- Custom prefab builders
- Luxury prefab companies
- Eco-friendly/sustainable prefab builders
- Tiny home manufacturers (if they do prefab)
- ADU (Accessory Dwelling Unit) prefab builders

IMPORTANT:
- Include companies headquartered in {province['name']}
- Include companies with manufacturing facilities in {province['name']}
- Include companies that primarily serve {province['name']} market
- Search thoroughly - there are typically dozens of such companies per province
- Include both well-known and lesser-known companies
- Don't skip smaller or regional companies

Return ONLY a JSON array with at least 10-20 companies if they exist. Format:
[{{"name": "Company Name", "province": "{province['name']}"}}, {{"name": "Another Company", "province": "{province['name']}"}}, ...]

If you find companies, return them. If you cannot find any companies, return an empty array [].

Return ONLY the JSON array, no explanations or additional text."""

    try:
        response = call_openai(prompt)
        
        # Extract JSON from response
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            try:
                companies = json.loads(json_match.group(0))
                companies_list = [{'name': c.get('name', ''), 'province': province['name']} for c in companies if c.get('name')]
                
                # If no companies found, try alternative prompt
                if not companies_list:
                    print(f"  🔄 No companies found with first prompt, trying alternative approach...")
                    companies_list = get_companies_for_province_alternative(province)
                
                if companies_list:
                    all_found_companies.extend(companies_list)
                    print(f"  ✅ Found {len(companies_list)} companies in initial discovery")
            except json.JSONDecodeError as e:
                print(f"  ⚠️  Error parsing JSON for {province['name']}: {e}")
                companies_list = extract_company_names(response, province['name'])
                if not companies_list:
                    companies_list = get_companies_for_province_alternative(province)
                if companies_list:
                    all_found_companies.extend(companies_list)
        else:
            companies_list = extract_company_names(response, province['name'])
            if not companies_list:
                companies_list = get_companies_for_province_alternative(province)
            if companies_list:
                all_found_companies.extend(companies_list)
    except Exception as error:
        print(f"  ❌ Error in initial research for {province['name']}: {error}")
        # Try alternative approach on error
        try:
            companies_list = get_companies_for_province_alternative(province)
            if companies_list:
                all_found_companies.extend(companies_list)
        except:
            pass
    
    # Deep research: iterate up to 15 times to find more companies
    existing_company_names = [c['name'] for c in all_found_companies]
    
    for iteration in range(2, max_iterations + 1):
        if len(existing_company_names) == 0:
            break  # No companies found, stop iterating
        
        print(f"  🔍 Deep research iteration {iteration}/{max_iterations}...")
        new_companies = get_companies_for_province_deep(province, existing_company_names, iteration)
        
        if not new_companies:
            print(f"  ⏹️  No new companies found in iteration {iteration}, stopping deep research")
            break
        
        # Remove duplicates
        existing_lower = {name.lower().strip() for name in existing_company_names}
        unique_new = [c for c in new_companies if c['name'].lower().strip() not in existing_lower]
        
        if unique_new:
            all_found_companies.extend(unique_new)
            existing_company_names.extend([c['name'] for c in unique_new])
            print(f"  ✅ Found {len(unique_new)} new companies in iteration {iteration} (total: {len(all_found_companies)})")
        else:
            print(f"  ⏹️  Only duplicates found in iteration {iteration}, stopping deep research")
            break
        
        # Small delay between iterations
        time.sleep(0.3)
    
    # Remove duplicates from final list
    seen = set()
    unique_companies = []
    for company in all_found_companies:
        name_lower = company['name'].lower().strip()
        if name_lower and name_lower not in seen:
            seen.add(name_lower)
            unique_companies.append(company)
    
    print(f"  📊 Total unique companies found: {len(unique_companies)}")
    return unique_companies

def get_companies_for_province_alternative(province: Dict) -> List[Dict]:
    """Alternative approach to find companies using a different prompt style"""
    prompt = f"""List all prefab home companies in {province['name']} province, Canada.

Search for companies that make:
- Modular homes
- Prefabricated homes  
- Manufactured homes
- Kit homes
- Panelized homes
- Factory-built homes

Include companies like:
- Local prefab builders in {province['name']}
- Regional modular manufacturers in {province['name']}
- Prefab home manufacturers
- Modular builders
- Industrialized home manufacturers

Provide at least 10-15 company names if they exist in {province['name']}.

Return ONLY a JSON array: [{{"name": "Company Name", "province": "{province['name']}"}}, ...]"""
    
    try:
        response = call_openai(prompt)
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            try:
                companies = json.loads(json_match.group(0))
                return [{'name': c.get('name', ''), 'province': province['name']} for c in companies if c.get('name')]
            except json.JSONDecodeError:
                return extract_company_names(response, province['name'])
        return extract_company_names(response, province['name'])
    except Exception as error:
        print(f"  ⚠️  Alternative approach also failed for {province['name']}: {error}")
        return []

def extract_company_names(text: str, province: str) -> List[Dict]:
    """Extract company names from text response"""
    companies = []
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Try to extract from various formats
    for line in lines:
        # Skip empty lines and common non-company text
        if not line or len(line) < 3:
            continue
        if any(skip in line.lower() for skip in ['json', 'array', 'return', 'format', 'example', 'note:', 'important']):
            continue
        
        # Pattern 1: Numbered list "1. Company Name"
        match = re.match(r'^\d+[\.\)]\s*(.+?)(?:\s*[-–]\s*.+)?$', line)
        if match:
            name = match.group(1).strip()
            if len(name) > 2 and len(name) < 100:  # Reasonable company name length
                companies.append({'name': name, 'province': province})
            continue
        
        # Pattern 2: Bullet points "- Company Name" or "* Company Name"
        match = re.match(r'^[-*•]\s*(.+?)(?:\s*[-–]\s*.+)?$', line)
        if match:
            name = match.group(1).strip()
            if len(name) > 2 and len(name) < 100:
                companies.append({'name': name, 'province': province})
            continue
        
        # Pattern 3: Quoted names '"Company Name"'
        match = re.search(r'"([^"]+)"', line)
        if match:
            name = match.group(1).strip()
            if len(name) > 2 and len(name) < 100:
                companies.append({'name': name, 'province': province})
            continue
        
        # Pattern 4: Lines that look like company names (capitalized, reasonable length)
        if re.match(r'^[A-Z][A-Za-z\s&\-\.]+$', line) and 3 <= len(line) <= 80:
            # Avoid common non-company words
            if not any(word in line.lower() for word in ['company', 'companies', 'list', 'include', 'example']):
                companies.append({'name': line, 'province': province})
    
    # Remove duplicates while preserving order
    seen = set()
    unique_companies = []
    for company in companies:
        name_lower = company['name'].lower().strip()
        if name_lower and name_lower not in seen:
            seen.add(name_lower)
            unique_companies.append(company)
    
    return unique_companies

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

This includes tools like:
- Home configurators
- Design tools
- Customization tools
- Interactive planners
- Online builders

This does NOT include:
- Simple contact forms
- Image galleries
- PDF downloads
- Static product pages
- Request a quote forms (unless they include configuration)

If a configurator exists, return ONLY the direct URL to the configurator page (must be a full URL starting with http:// or https://).
If no configurator exists, return exactly: NaN

Return ONLY the URL or NaN, nothing else."""

    try:
        response = call_openai(prompt)
        result = response.strip()
        
        # Check if it's a valid URL
        if result and result != 'NaN' and result != 'null' and (result.startswith('http://') or result.startswith('https://')):
            return result
        
        return None  # Will be converted to NaN in CSV
    except Exception as error:
        print(f"  ⚠️  Error checking configurator for {company_name}: {error}")
        return None

def research_company(company_name: str, province: str) -> Dict:
    """Research detailed information about a single company"""
    global company_id
    print(f"\n📊 Researching: {company_name} ({province})")
    
    prompt = f"""You are a professional researcher gathering detailed information about a prefabricated/modular home company in {province}, Canada.

Company to research: {company_name}
Province: {province}

Conduct thorough research and provide comprehensive, accurate information. Return ONLY valid JSON in this exact format (use null for missing data, NaN for numeric fields that cannot be determined):

{{
  "brand": "brand name or trading name (the name customers know them by)",
  "head_office_legal_name": "full legal registered company name",
  "address": "complete address: street number, street name, city, province, postal code, Canada",
  "webpage": "main website homepage URL (https://...)",
  "configurator": "direct URL to online configurator/combinator tool page if they have one (e.g., /configurator, /design-your-home, /home-configurator), else null",
  "models_amount": number of different prefab home models/designs they currently offer (integer, count actual models),
  "min_sqm": minimum square meters of their smallest available model (number, living area, convert from square feet if needed: 1 sqm = 10.764 sqft),
  "max_sqm": maximum square meters of their largest available model (number, living area, convert from square feet if needed: 1 sqm = 10.764 sqft),
  "main_structure_material": "primary construction material: wood/timber/concrete/steel/composite/CLT/cross-laminated timber/etc",
  "min_home_price": minimum starting price in CAD (Canadian Dollars) for their cheapest model (number, base price without land),
  "average_price_sqm": average price per square meter in CAD (Canadian Dollars) across their models (number, calculate from their pricing, convert from sqft pricing if needed)
}}

CRITICAL REQUIREMENTS:
- For "configurator": Only provide URL if they have an online tool where customers can configure/combine home options. If it's just a contact form or gallery, use null. Must be direct link to the configurator page.
- All prices should be in CAD (Canadian Dollars)
- "models_amount" should be the actual count of different home models/designs they offer
- "min_sqm" and "max_sqm" refer to living area/square meters of the homes (convert from square feet: divide sqft by 10.764)
- Be precise with addresses - include full street address when possible, use Canadian postal code format (A1A 1A1)
- For "main_structure_material", use the most common material (wood, concrete, steel, etc.)
- Only include verified, factual information
- Return ONLY the JSON object, no explanations or additional text before/after"""
    
    try:
        response = call_openai(prompt)
        
        # Extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                
                # Validate and clean data (configurator will be checked separately)
                def safe_int(value):
                    try:
                        return int(value) if value is not None and value != 'null' and value != 'NaN' else None
                    except (ValueError, TypeError):
                        return None
                
                def safe_float(value):
                    try:
                        return float(value) if value is not None and value != 'null' and value != 'NaN' else None
                    except (ValueError, TypeError):
                        return None
                
                result = {
                    'id': company_id,
                    'brand': data.get('brand') or company_name,
                    'head_office_legal_name': data.get('head_office_legal_name') or None,
                    'address': data.get('address') or None,
                    'country': 'Canada',
                    'country_code': 'CAN',
                    'region': province,
                    'webpage': data.get('webpage') or None,
                    'configurator': None,  # Will be set by check_configurator function
                    'models_amount': safe_int(data.get('models_amount')),
                    'min_sqm': safe_float(data.get('min_sqm')),
                    'max_sqm': safe_float(data.get('max_sqm')),
                    'main_structure_material': data.get('main_structure_material') or None,
                    'min_home_price': safe_float(data.get('min_home_price')),
                    'average_price_sqm': safe_float(data.get('average_price_sqm'))
                }
                
                # Check for configurator using OpenAI
                if result['webpage']:
                    print(f"  🔍 Checking configurator for {company_name}...")
                    configurator_url = check_configurator(company_name, result['webpage'])
                    result['configurator'] = configurator_url or None  # None will be written as NaN in CSV
                    # Rate limiter handles delays, but add small extra delay for configurator checks
                    time.sleep(0.3)
                else:
                    result['configurator'] = None  # No webpage, so no configurator
                
                company_id += 1
                return result
            except json.JSONDecodeError as e:
                print(f"  ⚠️  Error parsing JSON for {company_name}: {e}")
                print(f"  Response snippet: {response[:200]}...")
                return create_default_entry(company_name, province)
        
        return create_default_entry(company_name, province)
    except Exception as error:
        print(f"  ❌ Error researching {company_name}: {error}")
        return create_default_entry(company_name, province)

def create_default_entry(company_name: str, province: str) -> Dict:
    """Create default entry when research fails"""
    global company_id
    entry = {
        'id': company_id,
        'brand': company_name,
        'head_office_legal_name': None,
        'address': None,
        'country': 'Canada',
        'country_code': 'CAN',
        'region': province,
        'webpage': None,
        'configurator': None,
        'models_amount': None,
        'min_sqm': None,
        'max_sqm': None,
        'main_structure_material': None,
        'min_home_price': None,
        'average_price_sqm': None
    }
    company_id += 1
    return entry

def save_progress():
    """Save progress to JSON backup"""
    backup_path = output_dir / 'canada_progress_backup.json'
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(all_companies, f, indent=2, ensure_ascii=False)
    print(f"💾 Progress saved: {len(all_companies)} companies")

def load_progress() -> bool:
    """Load existing progress if available"""
    global company_id
    backup_path = output_dir / 'canada_progress_backup.json'
    if backup_path.exists():
        try:
            with open(backup_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list) and len(data) > 0:
                all_companies.extend(data)
                company_id = max([c.get('id', 0) for c in data], default=0) + 1
                print(f"📂 Loaded {len(data)} companies from previous session")
                return True
        except Exception as e:
            print(f'⚠️  Could not load previous progress: {e}')
    return False

def save_csv():
    """Save results to CSV"""
    fieldnames = [
        'id', 'brand', 'head_office_legal_name', 'address', 'country', 'country_code', 'region', 'webpage',
        'configurator', 'models_amount', 'min_sqm', 'max_sqm',
        'main_structure_material', 'min_home_price', 'average_price_sqm'
    ]
    
    # Convert data for CSV (handle None, NaN strings, and actual NaN values)
    csv_data = []
    for company in all_companies:
        csv_company = {}
        for field in fieldnames:
            # Handle country fields specially
            if field in ['country', 'country_code', 'region']:
                csv_company[field] = company.get(field, '') if company.get(field) else ''
                continue
            value = company.get(field)
            
            # Handle None values
            if value is None:
                csv_company[field] = ''
            # Handle string 'NaN' or 'null' from JSON
            elif isinstance(value, str) and value.lower() in ['nan', 'null']:
                csv_company[field] = ''
            # Handle numeric NaN (from math.nan or float('nan'))
            elif isinstance(value, float) and (value != value):  # NaN check: NaN != NaN
                csv_company[field] = ''
            # Handle configurator specifically - use 'NaN' string if None
            elif field == 'configurator' and (value is None or value == ''):
                csv_company[field] = 'NaN'
            # Convert numbers to strings, but keep empty for NaN
            elif isinstance(value, (int, float)):
                csv_company[field] = value
            else:
                csv_company[field] = value if value is not None else ''
        
        csv_data.append(csv_company)
    
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_data)

def main():
    """Main research function - province by province"""
    global all_companies, company_id
    
    print('🚀 Starting deep continuous research of Canada prefab home companies...\n')
    print(f"Using OpenAI ({openai_config['name']})\n")
    print(f"Researching {len(CANADA_PROVINCES)} Canadian provinces and territories one by one\n")
    print(f"Rate limits configured:")
    print(f"  - Requests per minute: {RATE_LIMIT_CONFIG['requests_per_minute']}")
    print(f"  - Requests per hour: {RATE_LIMIT_CONFIG['requests_per_hour']}")
    print(f"  - Requests per day: {RATE_LIMIT_CONFIG['requests_per_day']}")
    print(f"  - Min delay between requests: {RATE_LIMIT_CONFIG['min_delay_between_requests']}s\n")
    
    # Check for existing progress
    has_progress = load_progress()
    
    # Track which provinces have been processed
    processed_provinces = set()
    if has_progress:
        for company in all_companies:
            address = company.get('address') or ''
            if address:
                for province in CANADA_PROVINCES:
                    if province['name'] in address or province['code'] in address:
                        processed_provinces.add(province['code'])
                        break
    
    try:
        # Process each province
        for i, province in enumerate(CANADA_PROVINCES, 1):
            if province['code'] in processed_provinces:
                print(f"\n⏭️  Skipping {province['name']} (already processed)")
                continue
            
            print(f"\n{'=' * 60}")
            print(f"🗺️  Province {i}/{len(CANADA_PROVINCES)}: {province['name']} ({province['code']})")
            print(f"{'=' * 60}\n")
            
            # Step 1: Get companies for this province
            print(f"🔍 Discovering companies in {province['name']}...")
            companies = get_companies_for_province(province)
            
            if not companies:
                print(f"  ⚠️  No companies found for {province['name']}")
                # Rate limiter will handle delays, but add small delay here too
                time.sleep(0.5)
                continue
            
            print(f"  ✅ Found {len(companies)} companies in {province['name']}\n")
            
            # Step 2: Research each company for this province
            processed = 0
            total = len(companies)
            
            for company in companies:
                try:
                    company_data = research_company(company['name'], company['province'])
                    all_companies.append(company_data)
                    processed += 1
                    
                    print(f"  ✅ [{processed}/{total}] Completed: {company_data['brand']}")
                    
                    # Save progress every 5 companies
                    if len(all_companies) % 5 == 0:
                        save_progress()
                        # Print rate limit stats periodically
                        stats = rate_limiter.get_stats()
                        print(f"  📊 Rate limit stats: {stats['requests_last_minute']}/min, {stats['requests_last_hour']}/hour, {stats['requests_last_day']}/day")
                    
                    # Rate limiter handles delays automatically, no need for manual sleep here
                except Exception as error:
                    print(f"  ❌ Failed to process {company['name']}: {error}")
            
            print(f"\n✅ Completed {province['name']}: {processed}/{total} companies researched")
            
            # Save progress after each province
            save_progress()
            
            # Print rate limit stats after each province
            stats = rate_limiter.get_stats()
            print(f"  📊 Rate limit stats: {stats['requests_last_minute']}/min, {stats['requests_last_hour']}/hour, {stats['requests_last_day']}/day")
            
            # Rate limiter handles delays automatically, but add small delay between provinces for safety
            if i < len(CANADA_PROVINCES):
                time.sleep(0.5)
        
        # Step 3: Save final results
        print(f"\n{'=' * 60}")
        print(f"💾 Saving {len(all_companies)} companies to CSV...")
        save_csv()
        print(f"✅ Data saved to: {csv_path}")
        
        # Also save as JSON
        json_path = output_dir / 'canada_prefab_core.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(all_companies, f, indent=2, ensure_ascii=False)
        print(f"✅ JSON backup saved to: {json_path}")
        
        # Print summary
        print(f"\n📊 Summary:")
        print(f"   Total companies: {len(all_companies)}")
        print(f"   With webpage: {sum(1 for c in all_companies if c.get('webpage'))}")
        print(f"   With configurator: {sum(1 for c in all_companies if c.get('configurator'))}")
        print(f"   With pricing: {sum(1 for c in all_companies if c.get('min_home_price'))}")
        
        # Province breakdown
        province_counts = {}
        for company in all_companies:
            address = company.get('address') or ''
            found = False
            if address:
                for province in CANADA_PROVINCES:
                    if province['name'] in address or province['code'] in address:
                        province_counts[province['name']] = province_counts.get(province['name'], 0) + 1
                        found = True
                        break
            if not found:
                province_counts['Unknown'] = province_counts.get('Unknown', 0) + 1
        
        print(f"\n📈 Companies by province:")
        for province, count in sorted(province_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"   {province}: {count}")
        
        # Final rate limit stats
        final_stats = rate_limiter.get_stats()
        print(f"\n📊 Final rate limit statistics:")
        print(f"   Requests in last minute: {final_stats['requests_last_minute']}")
        print(f"   Requests in last hour: {final_stats['requests_last_hour']}")
        print(f"   Requests in last day: {final_stats['requests_last_day']}")
        print(f"   Consecutive errors: {final_stats['consecutive_errors']}")
        
        print(f"\n🎉 Research complete! Processed {len(all_companies)} companies across {len(CANADA_PROVINCES)} provinces and territories.")
        
    except KeyboardInterrupt:
        print(f'\n\n⚠️  Interrupted by user. Saving progress...')
        save_progress()
        final_stats = rate_limiter.get_stats()
        print(f"📊 Final rate limit stats: {final_stats['requests_last_minute']}/min, {final_stats['requests_last_hour']}/hour, {final_stats['requests_last_day']}/day")
        print(f"💾 Progress saved. You can resume by running the script again.")
        sys.exit(0)
    except Exception as error:
        print(f'❌ Fatal error: {error}')
        save_progress()
        final_stats = rate_limiter.get_stats()
        print(f"📊 Rate limit stats at error: {final_stats['requests_last_minute']}/min, {final_stats['requests_last_hour']}/hour, {final_stats['requests_last_day']}/day")
        sys.exit(1)

if __name__ == '__main__':
    main()
