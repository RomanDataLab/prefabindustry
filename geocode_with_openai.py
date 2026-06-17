import pandas as pd
from geopy.geocoders import ArcGIS, Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
import time
from tqdm import tqdm
import os
import sys
import json
from pathlib import Path

# Add parent directory to path to import apiManager
sys.path.insert(0, str(Path(__file__).parent))
from configix.apiManager import get_ai_provider

try:
    from openai import OpenAI
except ImportError:
    print("Error: openai package not installed. Run: pip install openai")
    sys.exit(1)

# Initialize OpenAI with API key from configix
openai_config = get_ai_provider('ai_openai')
openai_client = OpenAI(api_key=openai_config['api_key'])

def geocode_with_openai(address, country=None, region=None, geolocator=None):
    """
    Use OpenAI to intelligently format and parse addresses, then geocode them.
    Returns (latitude, longitude) or (None, None) if geocoding fails.
    """
    if pd.isna(address) or address.strip() == '':
        return None, None
    
    # Build context for OpenAI to help format the address
    context_parts = [f"Address: {address}"]
    if country:
        context_parts.append(f"Country: {country}")
    if region:
        context_parts.append(f"Region: {region}")
    
    prompt = f"""You are a geocoding assistant. Given the following address information, format it optimally for geocoding and extract the key location components.

{chr(10).join(context_parts)}

Please return a JSON object with this format:
{{
    "formatted_address": "<optimally formatted address string>",
    "city": "<city name if identifiable>",
    "country": "<country name if identifiable>"
}}

Format the address to be clear and complete for geocoding. Include country if not already in the address."""

    try:
        response = openai_client.chat.completions.create(
            model='gpt-4o',
            messages=[
                {'role': 'system', 'content': 'You are a geocoding assistant. Format addresses optimally for geocoding services.'},
                {'role': 'user', 'content': prompt}
            ],
            temperature=0.1,
            max_tokens=200,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        formatted_address = result.get('formatted_address', address)
        
        # Now geocode the formatted address using the geocoding service
        if geolocator:
            for attempt in range(2):
                try:
                    location = geolocator.geocode(formatted_address, timeout=15)
                    if location:
                        return location.latitude, location.longitude
                except (GeocoderTimedOut, GeocoderServiceError):
                    if attempt < 1:
                        time.sleep(1)
                    continue
                except Exception:
                    continue
        
        return None, None
        
    except json.JSONDecodeError:
        # Fallback: try geocoding original address
        if geolocator:
            try:
                location = geolocator.geocode(address, timeout=15)
                if location:
                    return location.latitude, location.longitude
            except:
                pass
        return None, None
    except Exception:
        return None, None

def geocode_with_service(address, geolocator, geocoder_name, max_retries=2):
    """
    Geocode an address using a geocoding service (fallback).
    Returns (latitude, longitude) or (None, None) if geocoding fails.
    """
    if pd.isna(address) or address.strip() == '':
        return None, None
    
    for attempt in range(max_retries):
        try:
            location = geolocator.geocode(address, timeout=15)
            if location:
                return location.latitude, location.longitude
            return None, None
        except (GeocoderTimedOut, GeocoderServiceError):
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                return None, None
        except Exception:
            return None, None
    
    return None, None

def main():
    # Read the CSV file
    csv_path = 'maps/prefabworld.csv'
    print(f"Reading {csv_path}...")
    df = pd.read_csv(csv_path)
    
    print(f"Total rows: {len(df)}")
    
    # Ensure latitude and longitude columns exist
    if 'latitude' not in df.columns:
        df['latitude'] = None
    if 'longitude' not in df.columns:
        df['longitude'] = None
    
    # Count how many addresses need geocoding
    needs_geocoding = df['address'].notna() & (df['latitude'].isna() | df['longitude'].isna())
    count_to_geocode = needs_geocoding.sum()
    
    print(f"Addresses to geocode: {count_to_geocode}")
    print(f"Addresses already geocoded: {(df['latitude'].notna() & df['longitude'].notna()).sum()}")
    
    if count_to_geocode == 0:
        print("All addresses are already geocoded. Exiting.")
        return
    
    # Initialize fallback geocoder (ArcGIS)
    try:
        fallback_geolocator = ArcGIS()
        fallback_geocoder_name = "ArcGIS"
        print("Fallback geocoder: ArcGIS")
    except Exception:
        fallback_geolocator = Nominatim(user_agent="prefab_geocoding_script")
        fallback_geocoder_name = "Nominatim"
        print("Fallback geocoder: Nominatim")
    
    # Geocode addresses
    print("\nStarting geocoding process with OpenAI...")
    print("Progress will be saved every 25 addresses.\n")
    
    geocoded_count = 0
    failed_count = 0
    openai_success = 0
    fallback_success = 0
    save_interval = 25  # Save every 25 addresses
    
    for idx, row in tqdm(df.iterrows(), total=len(df), desc="Geocoding"):
        # Skip if already geocoded
        if pd.notna(row['latitude']) and pd.notna(row['longitude']):
            continue
        
        # Skip if no address
        if pd.isna(row['address']) or row['address'].strip() == '':
            continue
        
        # Try OpenAI to format address, then geocode
        lat, lon = geocode_with_openai(
            row['address'],
            country=row.get('country') if pd.notna(row.get('country')) else None,
            region=row.get('region') if pd.notna(row.get('region')) else None,
            geolocator=fallback_geolocator
        )
        
        if lat is not None and lon is not None:
            df.at[idx, 'latitude'] = lat
            df.at[idx, 'longitude'] = lon
            geocoded_count += 1
            openai_success += 1
        else:
            # Try fallback geocoding service
            lat, lon = geocode_with_service(row['address'], fallback_geolocator, fallback_geocoder_name)
            if lat is not None and lon is not None:
                df.at[idx, 'latitude'] = lat
                df.at[idx, 'longitude'] = lon
                geocoded_count += 1
                fallback_success += 1
            else:
                failed_count += 1
        
        # Save progress periodically
        if (geocoded_count + failed_count) % save_interval == 0:
            df.to_csv(csv_path, index=False)
            print(f"\nProgress saved: {geocoded_count} geocoded ({openai_success} OpenAI, {fallback_success} fallback), {failed_count} failed")
        
        # Rate limiting for OpenAI (to avoid hitting limits)
        time.sleep(0.5)  # Small delay to avoid rate limits
    
    # Final save
    print(f"\nSaving final data to {csv_path}...")
    df.to_csv(csv_path, index=False)
    
    print(f"\nGeocoding complete!")
    print(f"Successfully geocoded: {geocoded_count} addresses")
    print(f"  - OpenAI: {openai_success}")
    print(f"  - Fallback ({fallback_geocoder_name}): {fallback_success}")
    print(f"Failed to geocode: {failed_count} addresses")
    print(f"Total rows with coordinates: {(df['latitude'].notna() & df['longitude'].notna()).sum()}")

if __name__ == "__main__":
    main()
