#!/usr/bin/env python3
# Deep continuous research of non-EU prefab home companies using OpenAI
# Excludes: Russia, Belarus, Georgia, Armenia, Azerbaijan
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
csv_path = output_dir / 'noneu_prefab_core.csv'

# Store all companies
all_companies = []
company_id = 1

# Rate limiting configuration
RATE_LIMIT_CONFIG = {
    'requests_per_minute': 50,
    'requests_per_hour': 2000,
    'requests_per_day': 10000,
    'min_delay_between_requests': 1.2,
    'backoff_multiplier': 2.0,
    'max_backoff_seconds': 300,
}

# Rate limiter class
class RateLimiter:
    """Track and enforce API rate limits"""
    def __init__(self, config: Dict):
        self.config = config
        self.request_times = deque()
        self.hourly_requests = deque()
        self.daily_requests = deque()
        self.last_request_time = 0
        self.consecutive_errors = 0
        
    def _clean_old_requests(self):
        """Remove old request timestamps outside the time windows"""
        now = time.time()
        
        while self.request_times and now - self.request_times[0] > 60:
            self.request_times.popleft()
        
        while self.hourly_requests and now - self.hourly_requests[0] > 3600:
            self.hourly_requests.popleft()
        
        while self.daily_requests and now - self.daily_requests[0] > 86400:
            self.daily_requests.popleft()
    
    def wait_if_needed(self):
        """Wait if we're approaching rate limits"""
        self._clean_old_requests()
        now = time.time()
        
        if len(self.request_times) >= self.config['requests_per_minute']:
            oldest_request = self.request_times[0]
            wait_time = 60 - (now - oldest_request) + 1
            if wait_time > 0:
                print(f"  ⏳ Rate limit: Waiting {wait_time:.1f}s (RPM limit: {len(self.request_times)}/{self.config['requests_per_minute']})")
                time.sleep(wait_time)
                self._clean_old_requests()
        
        if len(self.hourly_requests) >= self.config['requests_per_hour']:
            oldest_request = self.hourly_requests[0]
            wait_time = 3600 - (now - oldest_request) + 1
            if wait_time > 0:
                print(f"  ⏳ Rate limit: Waiting {wait_time:.1f}s (RPH limit: {len(self.hourly_requests)}/{self.config['requests_per_hour']})")
                time.sleep(wait_time)
                self._clean_old_requests()
        
        if len(self.daily_requests) >= self.config['requests_per_day']:
            oldest_request = self.daily_requests[0]
            wait_time = 86400 - (now - oldest_request) + 1
            if wait_time > 0:
                print(f"  ⏳ Rate limit: Waiting {wait_time:.1f}s (RPD limit: {len(self.daily_requests)}/{self.config['requests_per_day']})")
                time.sleep(wait_time)
                self._clean_old_requests()
        
        # Minimum delay between requests
        time_since_last = now - self.last_request_time
        if time_since_last < self.config['min_delay_between_requests']:
            sleep_time = self.config['min_delay_between_requests'] - time_since_last
            time.sleep(sleep_time)
        
        # Record this request
        now = time.time()
        self.request_times.append(now)
        self.hourly_requests.append(now)
        self.daily_requests.append(now)
        self.last_request_time = now
    
    def handle_rate_limit_error(self, error: Exception) -> float:
        """Handle rate limit errors with exponential backoff"""
        self.consecutive_errors += 1
        backoff_time = min(
            self.config['min_delay_between_requests'] * (self.config['backoff_multiplier'] ** self.consecutive_errors),
            self.config['max_backoff_seconds']
        )
        print(f"  ⚠️  Rate limit error (attempt {self.consecutive_errors}): Waiting {backoff_time:.1f}s")
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
            'requests_last_day': len(self.daily_requests)
        }

# Initialize rate limiter
rate_limiter = RateLimiter(RATE_LIMIT_CONFIG)

# European non-EU countries (excluding Russia, Belarus, Georgia, Armenia, Azerbaijan, 
# Liechtenstein, Monaco, San Marino, Vatican City, Andorra, Moldova, Serbia, 
# Bosnia and Herzegovina, Montenegro, North Macedonia, Albania, Kosovo)
# Format: {'code': 'XX', 'name': 'Country Name', 'currency': 'XXX', 'language': 'Language'}
NON_EU_COUNTRIES = [
    # Western Europe
    {'code': 'CH', 'name': 'Switzerland', 'currency': 'CHF', 'language': 'German/French/Italian'},
    {'code': 'NO', 'name': 'Norway', 'currency': 'NOK', 'language': 'Norwegian'},
    {'code': 'IS', 'name': 'Iceland', 'currency': 'ISK', 'language': 'Icelandic'},
    {'code': 'GB', 'name': 'United Kingdom', 'currency': 'GBP', 'language': 'English'},
    
    # Eastern Europe (excluding Russia, Belarus, Georgia, Armenia, Azerbaijan, Moldova)
    {'code': 'UA', 'name': 'Ukraine', 'currency': 'UAH', 'language': 'Ukrainian'},
]

def call_openai(prompt: str, max_retries: int = 3) -> str:
    """Call OpenAI API with retry logic and rate limiting"""
    for i in range(max_retries):
        try:
            rate_limiter.wait_if_needed()
            
            response = openai_client.chat.completions.create(
                model='gpt-4o',
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.7,
                max_tokens=4000
            )
            
            rate_limiter.reset_error_count()
            return response.choices[0].message.content
        except Exception as error:
            error_str = str(error).lower()
            
            if any(keyword in error_str for keyword in ['rate limit', 'quota', '429', 'resource_exhausted', 'too many requests']):
                backoff_time = rate_limiter.handle_rate_limit_error(error)
                if i < max_retries - 1:
                    time.sleep(backoff_time)
                    continue
                else:
                    print(f"  ❌ Rate limit exceeded after {max_retries} attempts. Please wait and try again later.")
                    raise Exception(f"Rate limit exceeded: {error}")
            
            print(f"  ⚠️  Attempt {i + 1}/{max_retries} failed: {error}")
            if i == max_retries - 1:
                raise
            
            backoff_time = min(2 * (i + 1), 60)
            time.sleep(backoff_time)

def get_companies_for_country(country: Dict) -> List[Dict]:
    """Get companies for a specific country"""
    currency = country['currency']
    country_name = country['name']
    
    prompt = f"""You are a research expert specializing in prefabricated/modular home companies in {country_name}.

Your task is to provide a COMPREHENSIVE list of ALL companies in {country_name} that manufacture, build, or sell prefab homes. This includes:

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
- Include companies headquartered in {country_name}
- Include companies with manufacturing facilities in {country_name}
- Include companies that primarily serve {country_name} market
- Search thoroughly - there are typically many such companies
- Include both well-known and lesser-known companies
- Don't skip smaller or regional companies

Return ONLY a JSON array with at least 10-20 companies if they exist. Format:
[{{"name": "Company Name", "country": "{country_name}"}}, {{"name": "Another Company", "country": "{country_name}"}}, ...]

If you find companies, return them. If you cannot find any companies, return an empty array [].

Return ONLY the JSON array, no explanations or additional text."""

    try:
        response = call_openai(prompt)
        
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            try:
                companies = json.loads(json_match.group(0))
                companies_list = [{'name': c.get('name', ''), 'country': country_name} for c in companies if c.get('name')]
                
                if not companies_list:
                    print(f"  🔄 No companies found with first prompt, trying alternative approach...")
                    return get_companies_for_country_alternative(country)
                
                return companies_list
            except json.JSONDecodeError as e:
                print(f"  ⚠️  Error parsing JSON for {country_name}: {e}")
                companies_list = extract_company_names(response, country_name)
                if not companies_list:
                    return get_companies_for_country_alternative(country)
                return companies_list
        
        companies_list = extract_company_names(response, country_name)
        if not companies_list:
            return get_companies_for_country_alternative(country)
        return companies_list
    except Exception as error:
        print(f"  ❌ Error researching {country_name}: {error}")
        try:
            return get_companies_for_country_alternative(country)
        except:
            return []

def get_companies_for_country_alternative(country: Dict) -> List[Dict]:
    """Alternative approach to get companies if first attempt fails"""
    currency = country['currency']
    country_name = country['name']
    
    prompt = f"""List all prefab home companies in {country_name}.

Include companies that manufacture or build:
- Prefabricated homes
- Modular homes
- Manufactured homes
- Kit homes
- Panelized homes
- Factory-built homes

Provide at least 10-15 company names if they exist in {country_name}.

Return ONLY a JSON array: [{{"name": "Company Name", "country": "{country_name}"}}, ...]"""

    try:
        response = call_openai(prompt)
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            try:
                companies = json.loads(json_match.group(0))
                return [{'name': c.get('name', ''), 'country': country_name} for c in companies if c.get('name')]
            except json.JSONDecodeError:
                return extract_company_names(response, country_name)
        return extract_company_names(response, country_name)
    except Exception as error:
        print(f"  ⚠️  Alternative approach also failed for {country_name}: {error}")
        return []

def extract_company_names(text: str, country: str) -> List[Dict]:
    """Extract company names from text response"""
    companies = []
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    for line in lines:
        # Try to extract company names from various formats
        match = re.match(r'(?:^|\d+\.\s*)(.+?)(?:\s*[-–]\s*)?([A-Z][a-z]+)?$', line)
        if match:
            company_name = match.group(1).strip()
            # Avoid common non-company words
            if not any(word in line.lower() for word in ['company', 'companies', 'list', 'include', 'example']):
                companies.append({'name': company_name, 'country': country})
    
    # Remove duplicates while preserving order
    seen = set()
    unique_companies = []
    for company in companies:
        name_lower = company['name'].lower()
        if name_lower not in seen:
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
        
        if result and result != 'NaN' and result != 'null' and (result.startswith('http://') or result.startswith('https://')):
            return result
        
        return None
    except Exception as error:
        print(f"  ⚠️  Error checking configurator for {company_name}: {error}")
        return None

def research_company(company_name: str, country: str, country_info: Dict) -> Dict:
    """Research detailed information about a single company"""
    global company_id
    currency = country_info['currency']
    country_name = country_info['name']
    
    print(f"\n📊 Researching: {company_name} ({country_name})")
    
    prompt = f"""You are a professional researcher gathering detailed information about a prefabricated/modular home company in {country_name}.

Company to research: {company_name}
Country: {country_name}
Currency: {currency}

Conduct thorough research and provide comprehensive, accurate information. Return ONLY valid JSON in this exact format (use null for missing data, NaN for numeric fields that cannot be determined):

{{
  "brand": "brand name or trading name (the name customers know them by)",
  "head_office_legal_name": "full legal registered company name",
  "address": "complete address: street number, street name, city, state/province, postal code, {country_name}",
  "webpage": "main website homepage URL (https://...)",
  "configurator": "direct URL to online configurator/combinator tool page if they have one (e.g., /configurator, /design-your-home, /home-configurator), else null",
  "models_amount": number of different prefab home models/designs they currently offer (integer, count actual models),
  "min_sqm": minimum square meters of their smallest available model (number, living area, convert from square feet if needed: 1 sqm = 10.764 sqft),
  "max_sqm": maximum square meters of their largest available model (number, living area, convert from square feet if needed: 1 sqm = 10.764 sqft),
  "main_structure_material": "primary construction material: wood/timber/concrete/steel/composite/CLT/cross-laminated timber/etc",
  "min_home_price": minimum starting price in {currency} for their cheapest model (number, base price without land),
  "average_price_sqm": average price per square meter in {currency} across their models (number, calculate from their pricing, convert from sqft pricing if needed)
}}

CRITICAL REQUIREMENTS:
- For "configurator": Only provide URL if they have an online tool where customers can configure/combine home options. If it's just a contact form or gallery, use null. Must be direct link to the configurator page.
- All prices should be in {currency}
- "models_amount" should be the actual count of different home models/designs they offer
- "min_sqm" and "max_sqm" refer to living area/square meters of the homes (convert from square feet: divide sqft by 10.764)
- Be precise with addresses - include full street address when possible
- For "main_structure_material", use the most common material (wood, concrete, steel, etc.)
- Only include verified, factual information
- Return ONLY the JSON object, no explanations or additional text before/after"""
    
    try:
        response = call_openai(prompt)
        
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                
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
                    'webpage': data.get('webpage') or None,
                    'configurator': None,
                    'models_amount': safe_int(data.get('models_amount')),
                    'min_sqm': safe_float(data.get('min_sqm')),
                    'max_sqm': safe_float(data.get('max_sqm')),
                    'main_structure_material': data.get('main_structure_material') or None,
                    'min_home_price': safe_float(data.get('min_home_price')),
                    'average_price_sqm': safe_float(data.get('average_price_sqm'))
                }
                
                if result['webpage']:
                    print(f"  🔍 Checking configurator for {company_name}...")
                    configurator_url = check_configurator(company_name, result['webpage'])
                    result['configurator'] = configurator_url or None
                    time.sleep(0.3)
                else:
                    result['configurator'] = None
                
                company_id += 1
                return result
            except json.JSONDecodeError as e:
                print(f"  ⚠️  Error parsing JSON for {company_name}: {e}")
                print(f"  Response snippet: {response[:200]}...")
                return create_default_entry(company_name, country_name)
        
        return create_default_entry(company_name, country_name)
    except Exception as error:
        print(f"  ❌ Error researching {company_name}: {error}")
        return create_default_entry(company_name, country_name)

def create_default_entry(company_name: str, country: str) -> Dict:
    """Create default entry when research fails"""
    global company_id
    entry = {
        'id': company_id,
        'brand': company_name,
        'head_office_legal_name': None,
        'address': None,
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
    backup_path = output_dir / 'noneu_progress_backup.json'
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(all_companies, f, indent=2, ensure_ascii=False)
    print(f"💾 Progress saved: {len(all_companies)} companies")

def load_progress() -> bool:
    """Load existing progress if available"""
    global company_id
    backup_path = output_dir / 'noneu_progress_backup.json'
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
    """Save all companies to CSV file"""
    fieldnames = [
        'id', 'brand', 'head_office_legal_name', 'address', 'webpage',
        'configurator', 'models_amount', 'min_sqm', 'max_sqm',
        'main_structure_material', 'min_home_price', 'average_price_sqm'
    ]
    
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for company in all_companies:
            row = {}
            for field in fieldnames:
                value = company.get(field)
                
                # Handle None values
                if value is None:
                    row[field] = ''
                # Handle string 'NaN' or 'null' from JSON
                elif isinstance(value, str) and value.lower() in ['nan', 'null']:
                    row[field] = ''
                # Handle numeric NaN
                elif isinstance(value, float) and (value != value):  # NaN check
                    row[field] = ''
                # Handle configurator specifically - use 'NaN' string if None/empty
                elif field == 'configurator' and (value is None or value == ''):
                    row[field] = 'NaN'
                # Keep other values as-is
                else:
                    row[field] = value if value is not None else ''
            
            writer.writerow(row)

def main():
    """Main research function - country by country"""
    global all_companies, company_id
    
    print('🚀 Starting deep continuous research of European non-EU prefab home companies...\n')
    print(f'Using OpenAI API (model: gpt-4o)\n')
    print(f'Researching {len(NON_EU_COUNTRIES)} European non-EU countries\n')
    print('Excluded: Russia, Belarus, Georgia, Armenia, Azerbaijan\n')
    
    # Check for existing progress
    has_progress = load_progress()
    
    # Track which countries have been processed
    processed_countries = set()
    if has_progress:
        for company in all_companies:
            address = company.get('address') or ''
            if address:
                for country in NON_EU_COUNTRIES:
                    if country['name'] in address or country['code'] in address:
                        processed_countries.add(country['code'])
                        break
    
    try:
        # Process each country
        for i, country in enumerate(NON_EU_COUNTRIES, 1):
            if country['code'] in processed_countries:
                print(f"\n⏭️  Skipping {country['name']} (already processed)")
                continue
            
            print(f"\n{'=' * 60}")
            print(f"🌍 Country {i}/{len(NON_EU_COUNTRIES)}: {country['name']} ({country['currency']})")
            print(f"{'=' * 60}\n")
            
            # Step 1: Get companies for this country
            print(f"🔍 Discovering companies in {country['name']}...")
            companies = get_companies_for_country(country)
            
            if not companies:
                print(f"  ⚠️  No companies found for {country['name']}")
                time.sleep(0.5)
                continue
            
            print(f"  ✅ Found {len(companies)} companies in {country['name']}\n")
            
            # Step 2: Research each company for this country
            processed = 0
            total = len(companies)
            
            for company in companies:
                try:
                    company_data = research_company(company['name'], company['country'], country)
                    all_companies.append(company_data)
                    processed += 1
                    
                    print(f"  ✅ [{processed}/{total}] Completed: {company_data['brand']}")
                    
                    # Save progress every 5 companies
                    if len(all_companies) % 5 == 0:
                        save_progress()
                        stats = rate_limiter.get_stats()
                        print(f"  📊 Rate limit stats: {stats['requests_last_minute']}/min, {stats['requests_last_hour']}/hour, {stats['requests_last_day']}/day")
                    
                    time.sleep(0.5)
                except Exception as error:
                    print(f"  ❌ Failed to process {company['name']}: {error}")
            
            print(f"\n✅ Completed {country['name']}: {processed}/{total} companies researched")
            
            # Save progress after each country
            save_progress()
            
            # Print rate limit stats after each country
            stats = rate_limiter.get_stats()
            print(f"  📊 Rate limit stats: {stats['requests_last_minute']}/min, {stats['requests_last_hour']}/hour, {stats['requests_last_day']}/day")
            
            # Small delay between countries
            if i < len(NON_EU_COUNTRIES):
                time.sleep(0.5)
        
        # Step 3: Save final results
        print(f"\n{'=' * 60}")
        print(f"💾 Saving {len(all_companies)} companies to CSV...")
        save_csv()
        print(f"✅ Data saved to: {csv_path}")
        
        # Also save as JSON
        json_path = output_dir / 'noneu_prefab_core.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(all_companies, f, indent=2, ensure_ascii=False)
        print(f"✅ JSON backup saved to: {json_path}")
        
        # Print summary
        print(f"\n📊 Summary:")
        print(f"   Total companies: {len(all_companies)}")
        print(f"   With webpage: {sum(1 for c in all_companies if c.get('webpage'))}")
        print(f"   With configurator: {sum(1 for c in all_companies if c.get('configurator'))}")
        print(f"   With pricing: {sum(1 for c in all_companies if c.get('min_home_price'))}")
        
        # Country breakdown
        country_counts = {}
        for company in all_companies:
            address = company.get('address') or ''
            found = False
            if address:
                for country in NON_EU_COUNTRIES:
                    if country['name'] in address or country['code'] in address:
                        country_counts[country['name']] = country_counts.get(country['name'], 0) + 1
                        found = True
                        break
            if not found:
                country_counts['Unknown'] = country_counts.get('Unknown', 0) + 1
        
        print(f"\n📊 Companies by country:")
        for country_name, count in sorted(country_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"   {country_name}: {count}")
        
    except KeyboardInterrupt:
        print(f"\n\n⚠️  Research interrupted by user")
        print(f"💾 Saving progress...")
        save_progress()
        save_csv()
        print(f"✅ Progress saved. Resume by running the script again.")
    except Exception as error:
        print(f"\n❌ Fatal error: {error}")
        import traceback
        traceback.print_exc()
        print(f"\n💾 Saving progress before exit...")
        save_progress()
        save_csv()

if __name__ == '__main__':
    main()
