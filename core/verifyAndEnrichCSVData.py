#!/usr/bin/env python3
# Verify webpage links and enrich missing data using OpenAI for all CSV files in research_output
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

# Initialize OpenAI with API key from configix
openai_config = get_ai_provider('ai_openai')
openai_client = OpenAI(api_key=openai_config['api_key'])

# Research output directory
research_output_dir = Path(__file__).parent.parent / 'research_output'

# Language mapping based on CSV filename
LANGUAGE_MAP = {
    'india': 'Hindi and English',
    'turkey': 'Turkish',
    'china': 'Chinese',
    'russia': 'Russian',
    'usa': 'English',
    'noneu': 'English',  # Will be determined per country
    'prefab_core_verified': 'English',  # EU companies
    'prefab_core': 'English'
}

# CSV field names (excluding configurator)
CSV_FIELDS = [
    'brand', 'head_office_legal_name', 'address', 'webpage',
    'models_amount', 'min_sqm', 'max_sqm', 'main_structure_material',
    'min_home_price', 'average_price_sqm'
]

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

def check_url_valid(url: str, timeout: int = 10) -> Tuple[bool, Optional[str]]:
    """Check if URL is valid and accessible. Returns (is_valid, error_message)"""
    if not url or url.strip() in ['', 'NaN', 'null', 'None']:
        return False, "Empty URL"
    
    url = url.strip()
    
    # Add protocol if missing
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True, verify=True)
        if response.status_code < 400:
            return True, None
        else:
            return False, f"HTTP {response.status_code}"
    except requests.exceptions.Timeout:
        return False, "Timeout"
    except requests.exceptions.SSLError:
        # Try HTTP if HTTPS fails
        if url.startswith('https://'):
            http_url = url.replace('https://', 'http://', 1)
            try:
                response = requests.head(http_url, timeout=timeout, allow_redirects=True, verify=False)
                if response.status_code < 400:
                    return True, None
            except:
                pass
        return False, "SSL Error"
    except requests.exceptions.ConnectionError:
        return False, "Connection Error"
    except requests.exceptions.RequestException as e:
        return False, str(e)
    except Exception as e:
        return False, f"Unknown error: {str(e)}"

def find_alternative_webpage(brand: str, company_name: str, language: str) -> Optional[str]:
    """Use AI to find alternative webpage URL for a company"""
    if not brand and not company_name:
        return None
    
    prompt = f"""Find the official website URL for this prefab/modular home company. Search using {language} language if helpful.

Company brand name: {brand or 'Unknown'}
Legal company name: {company_name or 'Unknown'}

Return ONLY the official website homepage URL (must start with http:// or https://).
If you cannot find a website, return exactly: null

Return ONLY the URL or null, nothing else."""

    try:
        response = call_openai([{'role': 'user', 'content': prompt}])
        result = response.strip()
        
        # Clean up response
        result = result.replace('"', '').replace("'", "")
        
        if result and result.lower() != 'null' and (result.startswith('http://') or result.startswith('https://')):
            return result
        return None
    except Exception as e:
        print(f"  ⚠️  Error finding alternative webpage: {e}")
        return None

def find_missing_data(row: Dict, language: str) -> Dict:
    """Use AI to find missing data fields (excluding configurator)"""
    brand = row.get('brand', '')
    company_name = row.get('head_office_legal_name', '')
    webpage = row.get('webpage', '')
    
    if not brand and not company_name:
        return {}
    
    # Build list of missing fields
    missing_fields = []
    for field in CSV_FIELDS:
        value = row.get(field, '')
        if not value or str(value).strip() in ['', 'NaN', 'null', 'None']:
            missing_fields.append(field)
    
    if not missing_fields:
        return {}
    
    # Build existing data context
    existing_data = []
    for field in CSV_FIELDS:
        value = row.get(field, '')
        if value and str(value).strip() not in ['', 'NaN', 'null', 'None']:
            existing_data.append(f"{field}: {value}")
    
    prompt = f"""You are researching information about a prefab/modular home company. Search using {language} language if helpful.

Company brand name: {brand or 'Unknown'}
Legal company name: {company_name or 'Unknown'}
Website: {webpage or 'Not provided'}

Existing data:
{chr(10).join(existing_data) if existing_data else 'No existing data'}

Find the following missing information (if available):
{', '.join(missing_fields)}

Return ONLY valid JSON in this exact format (use null for missing data, NaN for numeric fields that cannot be determined):
{{
  "brand": "brand name or trading name",
  "head_office_legal_name": "full legal registered company name",
  "address": "complete address: street number, street name, city, postal code, country",
  "webpage": "main website homepage URL (https://...)",
  "models_amount": number of different prefab home models/designs (integer),
  "min_sqm": minimum square meters of smallest model (number),
  "max_sqm": maximum square meters of largest model (number),
  "main_structure_material": "primary construction material: wood/timber/concrete/steel/composite/CLT/etc",
  "min_home_price": minimum starting price in local currency (number, base price without land),
  "average_price_sqm": average price per square meter in local currency (number)
}}

CRITICAL REQUIREMENTS:
- Only fill in the fields that were listed as missing above
- Use null for any field you cannot find
- Use NaN for numeric fields that cannot be determined
- For prices, use the local currency (do not convert)
- Be precise and factual
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
        print(f"  ⚠️  Error finding missing data: {e}")
        return {}

def get_language_for_csv(csv_filename: str) -> str:
    """Determine language based on CSV filename"""
    csv_name_lower = csv_filename.lower()
    
    for key, language in LANGUAGE_MAP.items():
        if key in csv_name_lower:
            return language
    
    return 'English'  # Default

def process_csv_file(csv_path: Path) -> Dict:
    """Process a single CSV file and return report data"""
    print(f"\n{'='*80}")
    print(f"📄 Processing: {csv_path.name}")
    print(f"{'='*80}\n")
    
    # Determine language
    language = get_language_for_csv(csv_path.name)
    print(f"🌐 Using language: {language}\n")
    
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
        return {}
    
    print(f"✅ Loaded {len(rows)} rows\n")
    
    # Process each row
    report_data = {
        'total_rows': len(rows),
        'processed_rows': 0,
        'webpage_checked': 0,
        'webpage_fixed': 0,
        'webpage_not_found': 0,
        'data_enriched': 0,
        'fields_filled': 0,
        'errors': []
    }
    
    updated_rows = []
    
    for i, row in enumerate(rows, 1):
        print(f"\n[{i}/{len(rows)}] Processing row {row.get('id', i)}: {row.get('brand', 'Unknown')}")
        report_data['processed_rows'] += 1
        
        updated_row = row.copy()
        
        # 1. Check webpage link
        webpage = row.get('webpage', '')
        if webpage and str(webpage).strip() not in ['', 'NaN', 'null', 'None']:
            print(f"  🔍 Checking webpage: {webpage}")
            report_data['webpage_checked'] += 1
            
            is_valid, error_msg = check_url_valid(webpage)
            
            if not is_valid:
                print(f"  ❌ Webpage not accessible: {error_msg}")
                
                # Try to find alternative webpage
                print(f"  🔎 Searching for alternative webpage...")
                alternative = find_alternative_webpage(
                    row.get('brand', ''),
                    row.get('head_office_legal_name', ''),
                    language
                )
                
                if alternative:
                    # Verify alternative URL
                    alt_valid, alt_error = check_url_valid(alternative)
                    if alt_valid:
                        print(f"  ✅ Found alternative webpage: {alternative}")
                        updated_row['webpage'] = alternative
                        report_data['webpage_fixed'] += 1
                    else:
                        print(f"  ❌ Alternative webpage also invalid: {alt_error}")
                        updated_row['webpage'] = ''
                        report_data['webpage_not_found'] += 1
                else:
                    print(f"  ❌ No alternative webpage found")
                    updated_row['webpage'] = ''
                    report_data['webpage_not_found'] += 1
                
                time.sleep(1)  # Rate limiting
            else:
                print(f"  ✅ Webpage is valid")
        
        # 2. Find missing data (excluding configurator)
        missing_fields = []
        for field in CSV_FIELDS:
            value = updated_row.get(field, '')
            if not value or str(value).strip() in ['', 'NaN', 'null', 'None']:
                missing_fields.append(field)
        
        if missing_fields:
            print(f"  🔍 Finding missing data for: {', '.join(missing_fields)}")
            found_data = find_missing_data(updated_row, language)
            
            if found_data:
                fields_filled_count = 0
                for field, value in found_data.items():
                    if field in CSV_FIELDS and value is not None and value != 'NaN' and value != 'null':
                        # Only update if field was missing
                        if field in missing_fields:
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
                            
                            fields_filled_count += 1
                            print(f"    ✅ Filled {field}: {value}")
                
                if fields_filled_count > 0:
                    report_data['data_enriched'] += 1
                    report_data['fields_filled'] += fields_filled_count
            
            time.sleep(1.5)  # Rate limiting
        
        updated_rows.append(updated_row)
        
        # Progress update every 10 rows
        if i % 10 == 0:
            print(f"\n💾 Progress: {i}/{len(rows)} rows processed")
    
    # Save updated CSV
    output_csv = csv_path.parent / f"{csv_path.stem}_enriched.csv"
    print(f"\n💾 Saving enriched data to: {output_csv.name}")
    
    try:
        with open(output_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in updated_rows:
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
        report_data['errors'].append(f"Error saving CSV: {e}")
    
    return report_data

def generate_combined_markdown_report(all_reports: Dict) -> str:
    """Generate a single combined markdown report for all CSV files"""
    
    # Calculate totals
    total_csv_files = len(all_reports)
    total_rows = sum(r['report_data']['total_rows'] for r in all_reports.values())
    total_processed = sum(r['report_data']['processed_rows'] for r in all_reports.values())
    total_webpages_checked = sum(r['report_data']['webpage_checked'] for r in all_reports.values())
    total_webpages_fixed = sum(r['report_data']['webpage_fixed'] for r in all_reports.values())
    total_webpages_not_found = sum(r['report_data']['webpage_not_found'] for r in all_reports.values())
    total_data_enriched = sum(r['report_data']['data_enriched'] for r in all_reports.values())
    total_fields_filled = sum(r['report_data']['fields_filled'] for r in all_reports.values())
    total_errors = sum(len(r['report_data']['errors']) for r in all_reports.values())
    
    md = f"""# Data Verification and Enrichment Report

**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}  
**Total CSV Files Processed:** {total_csv_files}

## Overall Summary

- **Total Rows:** {total_rows}
- **Rows Processed:** {total_processed}
- **Webpages Checked:** {total_webpages_checked}
- **Webpages Fixed:** {total_webpages_fixed}
- **Webpages Not Found:** {total_webpages_not_found}
- **Rows with Data Enriched:** {total_data_enriched}
- **Total Fields Filled:** {total_fields_filled}
- **Total Errors:** {total_errors}

---

## Files Processed

"""
    
    # Add section for each CSV file
    for csv_name, report_info in sorted(all_reports.items()):
        csv_path = report_info['csv_path']
        report_data = report_info['report_data']
        language = get_language_for_csv(csv_path.name)
        
        md += f"""### {csv_path.name}

**Language Used:** {language}  
**Output File:** `{csv_path.stem}_enriched.csv`

#### Statistics

- **Total Rows:** {report_data['total_rows']}
- **Rows Processed:** {report_data['processed_rows']}
- **Webpages Checked:** {report_data['webpage_checked']}
- **Webpages Fixed:** {report_data['webpage_fixed']}
- **Webpages Not Found:** {report_data['webpage_not_found']}
- **Rows with Data Enriched:** {report_data['data_enriched']}
- **Total Fields Filled:** {report_data['fields_filled']}

#### Webpage Verification

- **Checked:** {report_data['webpage_checked']} webpage URLs were verified
- **Fixed:** {report_data['webpage_fixed']} broken webpages were replaced with alternatives
- **Not Found:** {report_data['webpage_not_found']} webpages could not be found or verified

#### Data Enrichment

- **Rows Enriched:** {report_data['data_enriched']} rows had missing data filled
- **Fields Filled:** {report_data['fields_filled']} total fields were populated

"""
        
        # Add errors if any
        if report_data['errors']:
            md += "#### Errors\n\n"
            for error in report_data['errors']:
                md += f"- {error}\n"
            md += "\n"
        
        md += "---\n\n"
    
    md += f"""## Overall Statistics

### Webpage Verification Summary

- **Total Webpages Checked:** {total_webpages_checked}
- **Total Webpages Fixed:** {total_webpages_fixed}
- **Total Webpages Not Found:** {total_webpages_not_found}
- **Success Rate:** {(total_webpages_fixed / total_webpages_checked * 100) if total_webpages_checked > 0 else 0:.1f}% (fixed/checked)

### Data Enrichment Summary

- **Total Rows Enriched:** {total_data_enriched}
- **Total Fields Filled:** {total_fields_filled}
- **Average Fields per Row:** {(total_fields_filled / total_data_enriched) if total_data_enriched > 0 else 0:.1f}

---

*Generated by verifyAndEnrichCSVData.py*
"""
    
    return md

def main():
    """Main function"""
    print('🚀 Starting CSV data verification and enrichment using OpenAI...\n')
    print(f"Using OpenAI API ({openai_config['name']})\n")
    
    # Find all CSV files in research_output
    csv_files = list(research_output_dir.glob('*.csv'))
    
    # Filter out already enriched files
    csv_files = [f for f in csv_files if not f.name.endswith('_enriched.csv')]
    
    if not csv_files:
        print("❌ No CSV files found in research_output directory")
        return
    
    print(f"📁 Found {len(csv_files)} CSV file(s) to process:\n")
    for csv_file in csv_files:
        print(f"  - {csv_file.name}")
    print()
    
    # Process each CSV file
    all_reports = {}
    
    for csv_file in csv_files:
        try:
            report_data = process_csv_file(csv_file)
            all_reports[csv_file.name] = {
                'csv_path': csv_file,
                'report_data': report_data
            }
        except Exception as e:
            print(f"❌ Error processing {csv_file.name}: {e}")
            all_reports[csv_file.name] = {
                'csv_path': csv_file,
                'report_data': {
                    'total_rows': 0,
                    'processed_rows': 0,
                    'webpage_checked': 0,
                    'webpage_fixed': 0,
                    'webpage_not_found': 0,
                    'data_enriched': 0,
                    'fields_filled': 0,
                    'errors': [str(e)]
                }
            }
    
    # Generate combined markdown report
    print(f"\n{'='*80}")
    print("📝 Generating Combined Markdown Report")
    print(f"{'='*80}\n")
    
    md_content = generate_combined_markdown_report(all_reports)
    md_path = research_output_dir / "verification_and_enrichment_report.md"
    
    try:
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        print(f"✅ Generated combined report: {md_path.name}")
    except Exception as e:
        print(f"❌ Error generating combined report: {e}")
    
    # Print final summary
    print(f"\n{'='*80}")
    print("📊 Final Summary")
    print(f"{'='*80}\n")
    
    total_processed = sum(r['report_data']['processed_rows'] for r in all_reports.values())
    total_webpages_fixed = sum(r['report_data']['webpage_fixed'] for r in all_reports.values())
    total_fields_filled = sum(r['report_data']['fields_filled'] for r in all_reports.values())
    
    print(f"Total CSV files processed: {len(all_reports)}")
    print(f"Total rows processed: {total_processed}")
    print(f"Total webpages fixed: {total_webpages_fixed}")
    print(f"Total fields filled: {total_fields_filled}")
    print(f"\n🎉 Processing complete!")
    print(f"\n📄 Combined report generated: verification_and_enrichment_report.md")

if __name__ == '__main__':
    main()
