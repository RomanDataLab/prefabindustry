#!/usr/bin/env python3
# Verify and update company data using OpenAI for rows with at least 2 non-empty columns
import sys
import os
import json
import csv
import time
import re
from pathlib import Path
from typing import List, Dict, Optional

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

# Input and output files
input_csv = Path(__file__).parent.parent / 'research_output' / 'prefab_core.csv'
output_csv = Path(__file__).parent.parent / 'research_output' / 'prefab_core_verified.csv'
backup_csv = Path(__file__).parent.parent / 'research_output' / 'prefab_core_backup.csv'

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
            print(f"Attempt {i + 1} failed: {error}")
            if i == max_retries - 1:
                raise
            time.sleep(2 * (i + 1))

def count_non_empty_fields(row: Dict) -> int:
    """Count non-empty fields in a row (excluding id)"""
    count = 0
    for key, value in row.items():
        if key != 'id' and value and str(value).strip() not in ['', 'NaN', 'null', 'None']:
            count += 1
    return count

def verify_company_data(row: Dict) -> Dict:
    """Use OpenAI to verify and update company data"""
    company_id = row.get('id', 'Unknown')
    brand = row.get('brand', '')
    
    print(f"\n🔍 Verifying company ID {company_id}: {brand}")
    
    # Build prompt with existing data
    existing_data = []
    for key, value in row.items():
        if key != 'id' and value and str(value).strip() not in ['', 'NaN', 'null', 'None']:
            existing_data.append(f"{key}: {value}")
    
    prompt = f"""You are verifying and updating information about a prefab home company in the EU.

Existing data for this company:
{chr(10).join(existing_data) if existing_data else 'No existing data'}

Please verify and update ALL fields. Return ONLY valid JSON in this exact format (use null for missing data, NaN for numeric fields that cannot be determined):

{{
  "brand": "brand name or trading name (the name customers know them by)",
  "head_office_legal_name": "full legal registered company name",
  "address": "complete address: street number, street name, city, postal code, country",
  "webpage": "main website homepage URL (https://...)",
  "configurator": "direct URL to online configurator page if they have one, else null",
  "models_amount": number of different prefab home models/designs they currently offer (integer, count actual models),
  "min_sqm": minimum square meters of their smallest available model (number, living area),
  "max_sqm": maximum square meters of their largest available model (number, living area),
  "main_structure_material": "primary construction material: wood/timber/concrete/steel/composite/CLT/cross-laminated timber/etc",
  "min_home_price": minimum starting price in EUR for their cheapest model (number, convert from other currencies if needed, base price without land),
  "average_price_sqm": average price per square meter in EUR across their models (number, calculate from their pricing)
}}

CRITICAL REQUIREMENTS:
- Verify and correct any existing data that may be inaccurate
- Fill in missing fields if you can find the information
- For "configurator": Only provide URL if they have an online tool where customers can configure/combine home options. If it's just a contact form or gallery, use null.
- Convert ALL prices to EUR (use current exchange rates)
- "models_amount" should be the actual count of different home models/designs they offer
- "min_sqm" and "max_sqm" refer to living area/square meters of the homes
- Be precise with addresses - include full street address when possible
- For "main_structure_material", use the most common material (wood, concrete, steel, etc.)
- Only include verified, factual information
- Return ONLY the JSON object, no explanations or additional text before/after"""

    try:
        response = call_openai([{'role': 'user', 'content': prompt}])
        
        # Extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                
                # Helper functions for safe conversion
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
                
                # Clean and validate configurator URL
                configurator = data.get('configurator')
                if configurator and configurator != 'null' and configurator is not None:
                    if not configurator.startswith('http'):
                        webpage = data.get('webpage')
                        if webpage:
                            base_url = webpage.rstrip('/')
                            configurator = base_url + configurator if configurator.startswith('/') else base_url + '/' + configurator
                        else:
                            configurator = None
                else:
                    configurator = None
                
                # Update row with verified data
                updated_row = row.copy()
                updated_row['brand'] = data.get('brand') or row.get('brand') or None
                updated_row['head_office_legal_name'] = data.get('head_office_legal_name') or row.get('head_office_legal_name') or None
                updated_row['address'] = data.get('address') or row.get('address') or None
                updated_row['webpage'] = data.get('webpage') or row.get('webpage') or None
                updated_row['configurator'] = configurator or row.get('configurator') or None
                updated_row['models_amount'] = safe_int(data.get('models_amount')) or safe_int(row.get('models_amount'))
                updated_row['min_sqm'] = safe_float(data.get('min_sqm')) or safe_float(row.get('min_sqm'))
                updated_row['max_sqm'] = safe_float(data.get('max_sqm')) or safe_float(row.get('max_sqm'))
                updated_row['main_structure_material'] = data.get('main_structure_material') or row.get('main_structure_material') or None
                updated_row['min_home_price'] = safe_float(data.get('min_home_price')) or safe_float(row.get('min_home_price'))
                updated_row['average_price_sqm'] = safe_float(data.get('average_price_sqm')) or safe_float(row.get('average_price_sqm'))
                
                # Convert None values to empty string for CSV (will be written as NaN)
                for key in updated_row:
                    if updated_row[key] is None:
                        updated_row[key] = ''
                
                print(f"  ✅ Verified: {updated_row.get('brand', 'Unknown')}")
                return updated_row
                
            except json.JSONDecodeError as e:
                print(f"  ⚠️  Error parsing JSON: {e}")
                print(f"  Response snippet: {response[:200]}...")
                return row
        else:
            print(f"  ⚠️  No JSON found in response")
            return row
            
    except Exception as error:
        print(f"  ❌ Error verifying company: {error}")
        return row

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
        response = call_openai([{'role': 'user', 'content': prompt}])
        result = response.strip()
        
        # Check if it's a valid URL
        if result and result != 'NaN' and result != 'null' and (result.startswith('http://') or result.startswith('https://')):
            return result
        
        return None  # Will be converted to NaN in CSV
    except Exception as error:
        print(f"  ⚠️  Error checking configurator: {error}")
        return None

def main():
    """Main verification function"""
    print('🚀 Starting company data verification using OpenAI...\n')
    print(f"Using OpenAI API ({openai_config['name']})\n")
    
    # Check if input file exists
    if not input_csv.exists():
        print(f"❌ Input file not found: {input_csv}")
        sys.exit(1)
    
    # Read CSV file
    print(f"📖 Reading CSV file: {input_csv}")
    rows = []
    fieldnames = []
    
    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    
    print(f"✅ Loaded {len(rows)} rows\n")
    
    # Filter rows with at least 2 non-empty columns
    rows_to_verify = []
    for row in rows:
        non_empty_count = count_non_empty_fields(row)
        if non_empty_count >= 2:
            rows_to_verify.append(row)
    
    print(f"📊 Found {len(rows_to_verify)} rows with at least 2 non-empty columns\n")
    
    if len(rows_to_verify) == 0:
        print("⚠️  No rows to verify. Exiting.")
        return
    
    # Create backup
    print(f"💾 Creating backup: {backup_csv}")
    import shutil
    shutil.copy2(input_csv, backup_csv)
    print("✅ Backup created\n")
    
    # Verify each row
    verified_rows = []
    skipped_rows = []
    
    total_to_verify = len(rows_to_verify)
    verified_count = 0
    
    for i, row in enumerate(rows, 1):
        if row in rows_to_verify:
            verified_count += 1
            print(f"\n[{verified_count}/{total_to_verify}] Processing row {i}...")
            
            # Verify this row
            verified_row = verify_company_data(row)
            
            # Check configurator separately if webpage exists
            if verified_row.get('webpage') and not verified_row.get('configurator'):
                print(f"  🔍 Checking configurator for {verified_row.get('brand', 'Unknown')}...")
                configurator_url = check_configurator(verified_row.get('brand', ''), verified_row.get('webpage', ''))
                if configurator_url:
                    verified_row['configurator'] = configurator_url
                time.sleep(0.5)
            
            verified_rows.append(verified_row)
            
            # Save progress every 10 rows
            if verified_count % 10 == 0:
                print(f"\n💾 Progress: {verified_count}/{total_to_verify} rows verified")
            
            time.sleep(1.5)  # Delay to avoid rate limits
        else:
            # Keep original row
            skipped_rows.append(row)
    
    # Combine verified and skipped rows
    all_verified_rows = verified_rows + skipped_rows
    
    # Sort by ID to maintain order
    try:
        all_verified_rows.sort(key=lambda x: int(x.get('id', 0)) if x.get('id') and str(x.get('id')).isdigit() else 0)
    except:
        pass
    
    # Write verified CSV
    print(f"\n💾 Saving verified data to: {output_csv}")
    
    # Convert empty strings back to None for proper CSV handling
    for row in all_verified_rows:
        for key in row:
            if row[key] == '':
                row[key] = None
    
    # Write CSV with NaN for None values
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_verified_rows:
            csv_row = {}
            for key in fieldnames:
                value = row.get(key)
                if value is None or value == '':
                    csv_row[key] = 'NaN'
                else:
                    csv_row[key] = value
            writer.writerow(csv_row)
    
    print(f"✅ Verified data saved to: {output_csv}")
    
    # Print summary
    print(f"\n📊 Summary:")
    print(f"   Total rows: {len(rows)}")
    print(f"   Rows verified: {len(verified_rows)}")
    print(f"   Rows skipped: {len(skipped_rows)}")
    
    # Count improvements
    filled_fields = 0
    for original, verified in zip(rows_to_verify, verified_rows):
        for key in fieldnames:
            if key != 'id':
                orig_val = original.get(key) or ''
                ver_val = verified.get(key) or ''
                if not orig_val and ver_val:
                    filled_fields += 1
    
    print(f"   Fields filled: {filled_fields}")
    print(f"\n🎉 Verification complete!")

if __name__ == '__main__':
    main()
