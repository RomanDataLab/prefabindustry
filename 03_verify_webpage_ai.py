#!/usr/bin/env python3
"""
03_verify_webpage_ai.py
For each row in prefabworldfin_reducedby_2.csv:
  1) Attempt fetch of each row's webpage
  2) If fetch succeeds → keep the row as-is
  3) If fetch fails (HTTPS/443 error, DNS failure, timeout, etc.):
     - Use AI to search for relevant webpage (2 attempts)
     - If no URL found → delete row
     - If URL found → update webpage column, then verify new URL fetches
     - If new webpage fetch fails → erase row
     - If new webpage fetch succeeds → skip (keep row)
Saves result to prefabworldfin_reducedby_3.csv
"""
import sys
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

FETCH_TIMEOUT = 6
MAX_FETCH_WORKERS = 30

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
except ImportError:
    print("Error: requests required. Run: pip install requests")
    sys.exit(1)

# Initialize OpenAI
openai_config = get_ai_provider('ai_openai')
openai_client = OpenAI(api_key=openai_config['api_key'])

# Input/output paths
INPUT_CSV = Path(__file__).parent / 'maps' / 'public' / 'prefabworldfin_reducedby_2.csv'
OUTPUT_CSV = Path(__file__).parent / 'maps' / 'public' / 'prefabworldfin_reducedby_3.csv'


def _is_null(v) -> bool:
    """Check if value is null (empty, NaN, etc.)."""
    if pd.isna(v):
        return True
    s = str(v).strip()
    return s in ('', 'NaN', 'null', 'None', 'nan')


def _webpage_fetch_fails(url: str) -> Tuple[bool, Optional[str]]:
    """
    Try to fetch the webpage. Returns (failed, error_msg).
    failed=True when fetch errors (HTTPS/443, DNS failure, timeout, etc.)
    """
    if _is_null(url):
        return False, None
    url = str(url).strip()
    if not url.startswith(('http://', 'https://')):
        return False, None
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        r = requests.get(url, timeout=FETCH_TIMEOUT, headers=headers, allow_redirects=True, stream=True)
        r.close()
        return False, None  # fetch succeeded
    except Exception as e:
        return True, str(e)


def _is_valid_https_url(s: str) -> bool:
    """Check if string is a valid https URL."""
    if not s or not isinstance(s, str):
        return False
    s = s.strip().replace('"', '').replace("'", "")
    if s.lower() in ('null', 'none', 'n/a', 'unknown'):
        return False
    if not s.startswith('https://') and not s.startswith('http://'):
        return False
    parsed = urlparse(s)
    return bool(parsed.netloc) and len(s) > 12


def _ai_find_webpage(brand: str, country: str, region: str, attempt: int = 0) -> Optional[str]:
    """AI search for webpage URL. attempt 0 or 1 for 2 different prompts. Returns URL or None."""
    loc = ', '.join(filter(None, [str(r).strip() for r in [region, country] if not _is_null(r)]))
    loc = loc or country or 'unknown'
    prompts = [
        f"""What is the official website for "{brand}", a prefab/modular construction company in {loc}?
Reply with ONLY a valid https URL, or exactly 'null' if you cannot determine.""",
        f"""Find the official website of "{brand}" operating in {loc}. Prefab/modular homes industry.
Return ONLY the URL starting with https:// or 'null'."""
    ]
    prompt = prompts[min(attempt, len(prompts) - 1)]

    for retry in range(3):
        try:
            resp = openai_client.chat.completions.create(
                model='gpt-4o',
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.2,
                max_tokens=200
            )
            text = (resp.choices[0].message.content or '').strip().replace('"', '').replace("'", "").replace('`', '')
            url_match = re.search(r'https?://[^\s<>"\']+', text)
            if url_match:
                url = url_match.group(0).rstrip('.,;)')
                if _is_valid_https_url(url):
                    return url
            if _is_valid_https_url(text):
                return text
            if 'null' in text.lower() or not text:
                return None
        except Exception as e:
            err = str(e).lower()
            if any(k in err for k in ['rate limit', 'quota', '429', 'resource_exhausted']):
                wait = min(60 * (retry + 1), 300)
                print(f"    ⚠ Rate limit. Waiting {wait}s...")
                if retry < 2:
                    time.sleep(wait)
                    continue
            print(f"    ⚠ API error: {e}")
            if retry == 2:
                return None
            time.sleep(2 * (retry + 1))
    return None


def _ai_search_webpage(brand: str, country: str, region: str, max_attempts: int = 2) -> Optional[str]:
    """AI search for relevant webpage, up to max_attempts. Returns URL or None."""
    for attempt in range(max_attempts):
        url = _ai_find_webpage(brand, country, region, attempt)
        if url:
            return url
        if attempt < max_attempts - 1:
            time.sleep(0.8)
    return None


def main():
    if not INPUT_CSV.exists():
        print(f"Error: input CSV not found: {INPUT_CSV}")
        sys.exit(1)

    print(f"Reading {INPUT_CSV.name}...")
    df = pd.read_csv(INPUT_CSV)
    total = len(df)

    # Phase 1: Attempt fetch of each row's webpage; collect failures
    rows_to_check = [(idx, str(row.get('webpage', '')).strip()) for idx, row in df.iterrows()
                     if not _is_null(row.get('webpage', '')) and str(row.get('webpage', '')).strip().startswith(('http://', 'https://'))]
    to_process = []
    print(f"Checking {len(rows_to_check)} webpages (parallel, {MAX_FETCH_WORKERS} workers)...")
    with ThreadPoolExecutor(max_workers=MAX_FETCH_WORKERS) as ex:
        futures = {ex.submit(_webpage_fetch_fails, url): (idx, url) for idx, url in rows_to_check}
        for fut in as_completed(futures):
            idx, url = futures[fut]
            try:
                failed, err = fut.result()
                if failed:
                    to_process.append((idx, err))
            except Exception as e:
                to_process.append((idx, str(e)))

    print(f"Total rows: {total}")
    print(f"Rows with fetch failure: {len(to_process)}")
    print()

    # Phase 2: For fetch failures, AI search (2 attempts); found→update, then verify new URL fetches
    delete_indices = set()
    for i, (idx, fetch_err) in enumerate(to_process):
        row = df.iloc[idx]
        brand = row.get('brand', '') or f'Row {idx}'
        country = row.get('country', '')
        region = row.get('region', '')
        webpage = row.get('webpage', '')
        err_short = (fetch_err[:60] + '...') if fetch_err and len(fetch_err) > 60 else (fetch_err or '')
        print(f"[{i + 1}/{len(to_process)}] {brand} | {webpage[:40]}...")
        print(f"  Fetch error: {err_short}")

        url = _ai_search_webpage(brand, country, region, max_attempts=2)
        if not url:
            print(f"  ✗ No URL found after 2 attempts → delete row")
            delete_indices.add(idx)
            time.sleep(0.3)
            continue

        print(f"  ✓ Found: {url[:50]}...")
        df.at[idx, 'webpage'] = url

        # Step 3: Verify new webpage fetches; if fails → erase row
        failed, verify_err = _webpage_fetch_fails(url)
        if failed:
            print(f"  ✗ New webpage fetch failed → erase row")
            delete_indices.add(idx)
        else:
            print(f"  ✓ New webpage verified → skip (keep row)")
        time.sleep(0.3)

    df_out = df[~df.index.isin(delete_indices)].copy()
    df_out.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved to {OUTPUT_CSV.name}")
    print(f"Rows kept: {len(df_out)}, Rows deleted: {len(delete_indices)}")


if __name__ == '__main__':
    main()
