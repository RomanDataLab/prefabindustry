#!/usr/bin/env python3
"""
06_verify_prefab_production.py
Fetches each company's webpage via Scrapfly API, extracts SEO metadata, and uses
AI to evaluate whether the company produces prefab homes or panels.
Removes rows that don't. Considers local language content.
Runs in 5 parallel tracks with terminal progress.
Saves result as prefabworldfin_reducedby_8.csv.
"""
import sys
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import quote

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

# Config
INPUT_CSV = Path(__file__).parent / 'maps' / 'public' / 'prefabworldfin_reducedby_7.csv'
OUTPUT_CSV = Path(__file__).parent / 'maps' / 'public' / 'prefabworldfin_reducedby_8.csv'
PROGRESS_FILE = Path(__file__).parent / '06_verify_progress.json'
FETCH_TIMEOUT = 15
PARALLEL_TRACKS = 5
SAVE_EVERY = 20

# Scrapfly API
config_dir = Path(__file__).parent.parent / 'config'
if not config_dir.exists():
    config_dir = Path('C:/12_CODINGHARD/config')
with open(config_dir / 'config_scrapefly.json', 'r') as f:
    scrapfly_config = json.load(f)
SCRAPFLY_KEY = scrapfly_config['api_key']

# OpenAI setup
openai_config = get_ai_provider('ai_openai')
openai_client = OpenAI(api_key=openai_config['api_key'])

# Progress tracking
lock = threading.Lock()
progress = {
    'total': 0,
    'processed': 0,
    'kept': 0,
    'removed': 0,
    'fetch_failed': 0,
    'tracks': {i: '' for i in range(PARALLEL_TRACKS)},
}


class SEOExtractor(HTMLParser):
    """Extract SEO-relevant info from HTML."""
    def __init__(self):
        super().__init__()
        self.title = ''
        self.meta_desc = ''
        self.meta_keywords = ''
        self.h1s = []
        self.h2s = []
        self.og_desc = ''
        self.og_title = ''
        self._in_title = False
        self._in_h1 = False
        self._in_h2 = False
        self._text_chunks = []
        self._in_body = False
        self._skip_tag = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = {k.lower(): v for k, v in attrs if k}
        if tag == 'title':
            self._in_title = True
        elif tag == 'h1':
            self._in_h1 = True
        elif tag == 'h2':
            self._in_h2 = True
        elif tag == 'body':
            self._in_body = True
        elif tag in ('script', 'style', 'noscript'):
            self._skip_tag = True
        elif tag == 'meta':
            name = attrs_dict.get('name', '').lower()
            prop = attrs_dict.get('property', '').lower()
            content = attrs_dict.get('content', '')
            if name == 'description':
                self.meta_desc = content[:500]
            elif name == 'keywords':
                self.meta_keywords = content[:300]
            elif prop == 'og:description':
                self.og_desc = content[:500]
            elif prop == 'og:title':
                self.og_title = content[:200]

    def handle_endtag(self, tag):
        if tag == 'title':
            self._in_title = False
        elif tag == 'h1':
            self._in_h1 = False
        elif tag == 'h2':
            self._in_h2 = False
        elif tag in ('script', 'style', 'noscript'):
            self._skip_tag = False

    def handle_data(self, data):
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title += text
        if self._in_h1:
            self.h1s.append(text)
        if self._in_h2 and len(self.h2s) < 5:
            self.h2s.append(text)
        if self._in_body and not self._skip_tag and len(self._text_chunks) < 40:
            if len(text) > 10:
                self._text_chunks.append(text[:200])

    def get_body_snippet(self):
        return ' | '.join(self._text_chunks)[:2000]


def fetch_seo_scrapfly(url: str) -> dict:
    """Fetch webpage via Scrapfly API and extract SEO metadata."""
    if pd.isna(url) or not str(url).strip().startswith('http'):
        return None
    url = str(url).strip()
    try:
        api_url = f"https://api.scrapfly.io/scrape?key={SCRAPFLY_KEY}&url={quote(url, safe='')}&render_js=false&asp=true&country=us"
        r = requests.get(api_url, timeout=FETCH_TIMEOUT)
        if r.status_code != 200:
            return None
        data = r.json()
        html = data.get('result', {}).get('content', '')
        if not html:
            return None
        html = html[:100000]
        parser = SEOExtractor()
        try:
            parser.feed(html)
        except Exception:
            pass
        return {
            'title': parser.title[:300],
            'meta_desc': parser.meta_desc or parser.og_desc,
            'meta_keywords': parser.meta_keywords,
            'h1': ' | '.join(parser.h1s[:3])[:300],
            'h2': ' | '.join(parser.h2s[:5])[:300],
            'og_title': parser.og_title,
            'body_snippet': parser.get_body_snippet(),
        }
    except Exception:
        return None


def fetch_seo_direct(url: str) -> dict:
    """Fallback: direct fetch without Scrapfly."""
    if pd.isna(url) or not str(url).strip().startswith('http'):
        return None
    url = str(url).strip()
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        r = requests.get(url, timeout=8, headers=headers, allow_redirects=True)
        r.raise_for_status()
        ct = r.headers.get('Content-Type', '')
        if 'text/html' not in ct and 'application/xhtml' not in ct:
            return None
        html = r.text[:100000]
        parser = SEOExtractor()
        try:
            parser.feed(html)
        except Exception:
            pass
        return {
            'title': parser.title[:300],
            'meta_desc': parser.meta_desc or parser.og_desc,
            'meta_keywords': parser.meta_keywords,
            'h1': ' | '.join(parser.h1s[:3])[:300],
            'h2': ' | '.join(parser.h2s[:5])[:300],
            'og_title': parser.og_title,
            'body_snippet': parser.get_body_snippet(),
        }
    except Exception:
        return None


def evaluate_prefab(brand: str, country: str, webpage: str, seo: dict, desc_en: str) -> bool:
    """Use OpenAI to determine if company produces prefab homes or panels.
    Understands content in any language."""
    site_info = f"""Brand: {brand}
Country: {country}
URL: {webpage}
Page Title: {seo.get('title', '')}
Meta Description: {seo.get('meta_desc', '')}
Keywords: {seo.get('meta_keywords', '')}
H1: {seo.get('h1', '')}
H2: {seo.get('h2', '')}
OG Title: {seo.get('og_title', '')}
Body excerpt: {seo.get('body_snippet', '')}
Existing description (EN): {desc_en[:500] if desc_en else ''}"""

    prompt = f"""You are a multilingual analyst. The website content may be in ANY language (Russian, Chinese, Portuguese, Turkish, German, Spanish, Arabic, Hindi, etc.). Read and understand it in its original language.

Determine if this company is a manufacturer or seller of PREFAB HOMES or PREFAB PANELS.

KEEP if the company:
- Manufactures, builds, or sells prefabricated/modular homes, tiny homes, container homes, mobile homes
- Produces structural panels for prefab construction (SIP panels, CLT panels, sandwich panels, wall panels, insulated panels for building)
- Is a modular/prefab home factory or builder
- Builds prefab buildings (residential or commercial modular buildings)

REMOVE if the company:
- Only sells raw materials (lumber, insulation, hardware, cement) without producing homes/panels
- Is purely a real estate agency, architecture firm without manufacturing, or general contractor with no prefab focus
- Is a software company, consultant, logistics company, or trade association with no manufacturing
- Sells only furniture, interior design, kitchens, bathrooms, or non-structural products
- Website is dead, domain-parked, completely unrelated, or content is unreadable

{site_info}

Answer with ONLY one word: KEEP or REMOVE"""

    try:
        resp = openai_client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=10,
            temperature=0,
        )
        answer = resp.choices[0].message.content.strip().upper()
        return 'KEEP' in answer
    except Exception:
        return True  # keep on API error (conservative)


def print_progress():
    """Print live progress dashboard."""
    p = progress
    pct = (p['processed'] / p['total'] * 100) if p['total'] > 0 else 0
    bar_len = 40
    filled = int(bar_len * p['processed'] / p['total']) if p['total'] > 0 else 0
    bar = '█' * filled + '░' * (bar_len - filled)

    lines = [
        f"\r\033[2K\033[{PARALLEL_TRACKS + 4}A",
        f"  ┌─── PREFAB VERIFICATION ─── [{bar}] {pct:.1f}% ───┐",
        f"  │ Total: {p['total']:>4}  Done: {p['processed']:>4}  Kept: {p['kept']:>4}  Removed: {p['removed']:>4}  FetchFail: {p['fetch_failed']:>4} │",
        f"  ├─── Tracks ──────────────────────────────────────────────────────┤",
    ]
    for i in range(PARALLEL_TRACKS):
        status = p['tracks'].get(i, '')[:60].ljust(60)
        lines.append(f"  │ T{i}: {status} │")
    lines.append(f"  └─────────────────────────────────────────────────────────────────┘")
    sys.stdout.write('\n'.join(lines))
    sys.stdout.flush()


def process_row(idx: int, row, track_id: int) -> bool:
    """Process a single row. Returns True if should keep."""
    brand = str(row.get('brand', ''))[:40] if not pd.isna(row.get('brand', '')) else f'Row {idx}'
    country = str(row.get('country', '')) if not pd.isna(row.get('country', '')) else ''
    webpage = row.get('webpage', '')
    row_id = row.get('id', idx)
    desc_en = str(row.get('desc_en', '')) if not pd.isna(row.get('desc_en', '')) else ''

    with lock:
        progress['tracks'][track_id] = f"Fetching #{row_id} {brand}..."
        print_progress()

    # Try Scrapfly first, then direct fetch as fallback
    seo = fetch_seo_scrapfly(webpage)
    if seo is None:
        seo = fetch_seo_direct(webpage)

    if seo is None:
        with lock:
            progress['fetch_failed'] += 1
            progress['tracks'][track_id] = f"FETCH FAIL #{row_id} {brand}"
            print_progress()
        # Use existing description if available
        if desc_en and len(desc_en) > 20:
            seo = {
                'title': brand,
                'meta_desc': desc_en[:500],
                'meta_keywords': '',
                'h1': '', 'h2': '',
                'og_title': '',
                'body_snippet': desc_en[:1500],
            }
        else:
            # No webpage, no description — keep conservatively
            with lock:
                progress['processed'] += 1
                progress['kept'] += 1
                print_progress()
            return True

    with lock:
        progress['tracks'][track_id] = f"AI eval #{row_id} {brand}..."
        print_progress()

    keep = evaluate_prefab(brand, country, str(webpage), seo, desc_en)

    with lock:
        progress['processed'] += 1
        if keep:
            progress['kept'] += 1
            progress['tracks'][track_id] = f"KEPT #{row_id} {brand}"
        else:
            progress['removed'] += 1
            progress['tracks'][track_id] = f"REMOVED #{row_id} {brand}"
        print_progress()

    return keep


def load_progress() -> dict:
    """Load saved progress if exists."""
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_progress(results: dict):
    """Save progress to file."""
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(results, f)


def main():
    print(f"Reading {INPUT_CSV}...")
    df = pd.read_csv(INPUT_CSV, encoding='utf-8')
    total = len(df)
    progress['total'] = total

    # Load any saved progress
    saved = load_progress()
    if saved:
        print(f"Found saved progress: {len(saved)} rows already processed.")
    else:
        print("No saved progress found. Starting fresh.")

    print(f"Loaded {total} rows. Starting verification with {PARALLEL_TRACKS} parallel tracks...\n")

    # Print initial empty dashboard
    for _ in range(PARALLEL_TRACKS + 5):
        print()

    results = dict(saved)  # {str(idx): True/False}
    save_counter = 0

    # Skip already-processed rows
    tasks = []
    for idx, row in df.iterrows():
        if str(idx) in results:
            # Already processed
            with lock:
                progress['processed'] += 1
                if results[str(idx)]:
                    progress['kept'] += 1
                else:
                    progress['removed'] += 1
        else:
            tasks.append((idx, row, len(tasks) % PARALLEL_TRACKS))

    if not tasks:
        print("\n  All rows already processed!")
    else:
        print_progress()

        def worker(args):
            idx, row, track_id = args
            return idx, process_row(idx, row, track_id)

        with ThreadPoolExecutor(max_workers=PARALLEL_TRACKS) as executor:
            futures = {executor.submit(worker, task): task[0] for task in tasks}
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    row_idx, keep = future.result()
                    results[str(row_idx)] = keep
                except Exception as e:
                    print(f"\n  ERROR on row {idx}: {e}")
                    results[str(idx)] = True

                save_counter += 1
                if save_counter % SAVE_EVERY == 0:
                    save_progress(results)
                    keep_flags = [results.get(str(i), True) for i in range(total)]
                    df_out = df[keep_flags].copy()
                    df_out.to_csv(OUTPUT_CSV, index=False, encoding='utf-8')

    # Final save
    save_progress(results)
    keep_flags = [results.get(str(i), True) for i in range(total)]
    df_out = df[keep_flags].copy()
    df_out.to_csv(OUTPUT_CSV, index=False, encoding='utf-8')

    removed = total - len(df_out)
    print(f"\n\n  DONE! {total} -> {len(df_out)} rows (removed {removed})")
    print(f"  Saved to: {OUTPUT_CSV}")

    # Clean up progress file on completion
    if PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()


if __name__ == '__main__':
    main()
