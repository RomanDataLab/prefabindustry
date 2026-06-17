import pandas as pd
from geopy.geocoders import Nominatim, OpenCage, GoogleV3, ArcGIS
from geopy.exc import GeocoderTimedOut, GeocoderServiceError, GeocoderQuotaExceeded
import time
from tqdm import tqdm
import os

def geocode_address(address, geolocator, geocoder_name, max_retries=3):
    """
    Geocode an address with retry logic.
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
        except GeocoderQuotaExceeded:
            print(f"\nQuota exceeded for {geocoder_name}. Please check your API limits.")
            return None, None
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
            else:
                # Don't print every failure to avoid spam
                return None, None
        except Exception as e:
            if attempt == max_retries - 1:
                # Only print on final attempt
                return None, None
            time.sleep(1)
    
    return None, None

def main():
    # Read the CSV file
    csv_path = 'maps/prefabworld.csv'
    print(f"Reading {csv_path}...")
    df = pd.read_csv(csv_path)
    
    print(f"Total rows: {len(df)}")
    
    # Check if latitude and longitude columns already exist
    has_lat = 'latitude' in df.columns
    has_lon = 'longitude' in df.columns
    
    if has_lat and has_lon:
        print("Latitude and longitude columns already exist. Will preserve existing data.")
        # Initialize columns if they don't exist (shouldn't happen, but just in case)
        if 'latitude' not in df.columns:
            df['latitude'] = None
        if 'longitude' not in df.columns:
            df['longitude'] = None
    else:
        # Create new columns
        print("Creating new latitude and longitude columns.")
        df['latitude'] = None
        df['longitude'] = None
    
    # Initialize geocoder - try multiple options
    geolocator = None
    geocoder_name = "Unknown"
    rate_limit_delay = 1.0
    
    # Try OpenCage first (faster, free tier: 2500/day)
    opencage_api_key = os.getenv('OPENCAGE_API_KEY')
    if opencage_api_key:
        try:
            geolocator = OpenCage(api_key=opencage_api_key)
            geocoder_name = "OpenCage"
            rate_limit_delay = 0.1  # Faster rate limit
            print("Using OpenCage Geocoding API (faster)")
        except Exception as e:
            print(f"Failed to initialize OpenCage: {e}")
    
    # Try ArcGIS as fallback (free, no API key needed, faster than Nominatim)
    if geolocator is None:
        try:
            geolocator = ArcGIS()
            geocoder_name = "ArcGIS"
            rate_limit_delay = 0.2  # Faster than Nominatim
            print("Using ArcGIS Geocoding API (free, no API key needed)")
        except Exception as e:
            print(f"Failed to initialize ArcGIS: {e}")
    
    # Fallback to Nominatim (slowest but most reliable)
    if geolocator is None:
        geolocator = Nominatim(user_agent="prefab_geocoding_script")
        geocoder_name = "Nominatim"
        rate_limit_delay = 1.0
        print("Using Nominatim Geocoding API (free, slower)")
    
    print(f"\nGeocoder: {geocoder_name}")
    print(f"Rate limit delay: {rate_limit_delay} seconds\n")
    
    # Count how many addresses need geocoding
    needs_geocoding = df['address'].notna() & (df['latitude'].isna() | df['longitude'].isna())
    count_to_geocode = needs_geocoding.sum()
    
    print(f"Addresses to geocode: {count_to_geocode}")
    print(f"Addresses already geocoded: {len(df) - count_to_geocode}")
    
    if count_to_geocode == 0:
        print("All addresses are already geocoded. Exiting.")
        return
    
    # Geocode addresses
    print("\nStarting geocoding process...")
    print("Progress will be saved every 50 addresses.\n")
    
    geocoded_count = 0
    failed_count = 0
    save_interval = 50  # Save every 50 addresses
    
    for idx, row in tqdm(df.iterrows(), total=len(df), desc="Geocoding"):
        # Skip if already geocoded
        if pd.notna(row['latitude']) and pd.notna(row['longitude']):
            continue
        
        # Skip if no address
        if pd.isna(row['address']) or row['address'].strip() == '':
            continue
        
        # Geocode the address
        lat, lon = geocode_address(row['address'], geolocator, geocoder_name)
        
        if lat is not None and lon is not None:
            df.at[idx, 'latitude'] = lat
            df.at[idx, 'longitude'] = lon
            geocoded_count += 1
        else:
            failed_count += 1
        
        # Save progress periodically
        if (geocoded_count + failed_count) % save_interval == 0:
            df.to_csv(csv_path, index=False)
            print(f"\nProgress saved: {geocoded_count} geocoded, {failed_count} failed")
        
        # Rate limiting based on geocoder
        time.sleep(rate_limit_delay)
    
    # Final save
    output_path = csv_path
    print(f"\nSaving final data to {output_path}...")
    df.to_csv(output_path, index=False)
    
    print(f"\nGeocoding complete!")
    print(f"Successfully geocoded: {geocoded_count} addresses")
    print(f"Failed to geocode: {failed_count} addresses")
    print(f"Total rows with coordinates: {(df['latitude'].notna() & df['longitude'].notna()).sum()}")

if __name__ == "__main__":
    main()
