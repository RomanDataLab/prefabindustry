#!/usr/bin/env python3
"""
04_classify_type_ai.py
For each row in prefabworldfin_reducedby_3.csv where [type] is null:
  - Use ai_openai to fetch and analyze each [webpage] (and relevant subpages)
  - Understand what types of products [brand] produces
  - Classify as: 'home' (residential), 'industrial', 'panels', or other one-word
  - Certainty levels: [Confirmed] clearly stated, [Reported] inferred, [Unknown] not found
  - Only put value in [type] if certainty is Confirmed; otherwise skip
  - Progress logged to JSONL; result saved to prefabworldfin_reducedby_4.csv
"""
import sys
import re
import json
import time
from pathlib import Path
from typing import Optional, Tuple, List
from urllib.parse import urljoin, urlparse

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

# Initialize OpenAI
openai_config = get_ai_provider('ai_openai')
openai_client = OpenAI(api_key=openai_config['api_key'])

# Paths
INPUT_CSV = Path(__file__).parent / 'maps' / 'public' / 'prefabworldfin_reducedby_3.csv'
OUTPUT_CSV = Path(__file__).parent / 'maps' / 'public' / 'prefabworldfin_reducedby_4.csv'
PROGRESS_JSONL = Path(__file__).parent / '04_classify_type_progress.jsonl'

FETCH_TIMEOUT = 15
MAX_PAGES_PER_SITE = 6  # Main + up to 5 relevant subpages


def _is_null(v) -> bool:
    """Check if value is null (empty, NaN, etc.)."""
    if pd.isna(v):
        return True
    s = str(v).strip()
    return s in ('', 'NaN', 'null', 'None', 'nan')


def _is_valid_url(url: str) -> bool:
    """Check if string is a valid http(s) URL."""
    if not url or not isinstance(url, str):
        return False
    url = str(url).strip()
    return url.startswith(('http://', 'https://')) and bool(urlparse(url).netloc)


def fetch_webpage(url: str) -> Tuple[Optional[str], List[str]]:
    """Fetch webpage; return (text_content, list_of_links)."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        r = requests.get(url, timeout=FETCH_TIMEOUT, headers=headers, allow_redirects=True)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, 'html.parser')
        links = []
        base = urlparse(url)
        for a in soup.find_all('a', href=True):
            href = a.get('href', '').strip()
            if href:
                abs_url = urljoin(url, href)
                if abs_url not in links and urlparse(abs_url).netloc == base.netloc:
                    links.append(abs_url)
        for tag in soup(['script', 'style', 'nav', 'footer']):
            tag.decompose()
        text = soup.get_text(separator=' ', strip=True)
        text = ' '.join(text.split())[:12000]
        return text, links
    except Exception as e:
        return None, []


def _find_relevant_product_links(
    text: str, links: List[str], base_url: str, visited: set, brand: str
) -> List[str]:
    """Use AI to pick links likely to describe products/services offered."""
    candidates = [
        l for l in links
        if l not in visited and l.startswith(('http://', 'https://'))
        and urlparse(l).netloc == urlparse(base_url).netloc
    ][:60]
    if not candidates:
        return []
    prompt = f"""Base URL: {base_url}
Brand: {brand}
Page content (first 4000 chars):
{(text or '')[:4000]}

Links (first 40):
{chr(10).join(candidates[:40])}

Which links likely contain: products, services, what we build, portfolio, projects, residential, industrial, panels, modular, prefab?
Return ONLY a JSON array of up to 5 URLs: ["url1", "url2"]
If none relevant: []"""
    try:
        resp = openai_client.chat.completions.create(
            model='gpt-4o',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.1,
            max_tokens=500
        )
        content = (resp.choices[0].message.content or '').strip()
        m = re.search(r'\[[\s\S]*?\]', content)
        if m:
            arr = json.loads(m.group(0))
            return [u for u in arr if isinstance(u, str) and u in candidates][:5]
    except Exception:
        pass
    return []


def collect_site_content(webpage: str, brand: str) -> str:
    """
    Visit main page and relevant subpages; concatenate content for AI analysis.
    Returns combined text (up to ~30k chars).
    """
    if not _is_valid_url(webpage):
        return ''
    visited = set()
    to_visit = [webpage.strip()]
    collected = []

    for _ in range(MAX_PAGES_PER_SITE):
        if not to_visit:
            break
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)

        text, links = fetch_webpage(url)
        if text:
            collected.append(f"--- Page: {url} ---\n{text}")

        # On first page, find relevant product links
        if len(visited) == 1 and links:
            rel = _find_relevant_product_links(
                text or '', links, url, visited, brand
            )
            for link in rel[:4]:
                if link not in visited:
                    to_visit.append(link)

        time.sleep(0.8)

    return '\n\n'.join(collected)[:35000]


def call_openai_classify(brand: str, content: str, webpage: str) -> Tuple[Optional[str], str]:
    """
    Use AI to classify product type from webpage content.
    Returns (type_value or None, certainty: 'Confirmed'|'Reported'|'Unknown').
    Only return type if Confirmed.
    """
    if not content or len(content.strip()) < 200:
        return None, 'Unknown'

    prompt = f"""Analyze the following webpage content from "{brand}" (URL: {webpage}).

Content from website (may include multiple pages):
{content[:30000]}

Determine what types of prefabricated products this company PREDOMINANTLY produces:

- 'home' = predominantly prefabricated residential houses / single-family homes / housing
- 'industrial' = predominantly prefabricated industrial buildings (warehouses, factories, commercial)
- 'panels' = predominantly prefabricated panels / wall panels / structural panels
- If something else predominates, use ONE word (e.g. commercial, modular, cabins, etc.)

Data extracted certainty levels:
- [Confirmed] = clearly stated on the site (explicit product descriptions, "we build X", product categories)
- [Reported] = inferred/approximate from context, wording, or indirect references
- [Unknown] = not found, insufficient information

Respond with ONLY valid JSON, no other text:
{{"type": "home"|"industrial"|"panels"|"<one_word>"|null, "certainty": "Confirmed"|"Reported"|"Unknown"}}

Use null for type if certainty is not Confirmed. Be thorough - check all content before deciding."""

    for retry in range(3):
        try:
            resp = openai_client.chat.completions.create(
                model='gpt-4o',
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.1,
                max_tokens=150
            )
            text = (resp.choices[0].message.content or '').strip()
            # Extract JSON
            m = re.search(r'\{[^{}]*\}', text)
            if m:
                data = json.loads(m.group(0))
                t = data.get('type')
                c = data.get('certainty', 'Unknown')
                if c not in ('Confirmed', 'Reported', 'Unknown'):
                    c = 'Unknown'
                # Normalize type to one lowercase word
                if t and isinstance(t, str):
                    t = t.strip().lower()
                    if ' ' in t:
                        t = t.split()[0]
                    if len(t) > 25:
                        t = t[:25]
                return (t if c == 'Confirmed' else None), c
        except Exception as e:
            err = str(e).lower()
            if any(k in err for k in ['rate limit', 'quota', '429', 'resource_exhausted']):
                wait = min(60 * (retry + 1), 300)
                print(f"    ⚠ Rate limit. Waiting {wait}s...")
                if retry < 2:
                    time.sleep(wait)
                    continue
            if retry == 2:
                return None, 'Unknown'
            time.sleep(2 * (retry + 1))
    return None, 'Unknown'


def log_progress(record: dict, jsonl_path: Path):
    """Append one JSON object per line to progress file."""
    with open(jsonl_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')


def main():
    if not INPUT_CSV.exists():
        print(f"Error: input CSV not found: {INPUT_CSV}")
        sys.exit(1)

    print(f"Reading {INPUT_CSV.name}...")
    df = pd.read_csv(INPUT_CSV)

    if 'type' not in df.columns:
        df['type'] = pd.NA

    # Rows where type is null and we have a valid webpage
    to_process = []
    for idx, row in df.iterrows():
        if _is_null(row.get('type')) and not _is_null(row.get('webpage')):
            url = str(row.get('webpage', '')).strip()
            if _is_valid_url(url):
                to_process.append(idx)

    total = len(to_process)
    print(f"Rows with null type and valid webpage: {total}\n")

    if total == 0:
        df.to_csv(OUTPUT_CSV, index=False)
        print("Nothing to classify. Saved unchanged to prefabworldfin_reducedby_4.csv")
        return

    # Clear/create progress file
    if PROGRESS_JSONL.exists():
        PROGRESS_JSONL.write_text('', encoding='utf-8')
    log_progress(
        {'event': 'start', 'total': total, 'input': str(INPUT_CSV), 'output': str(OUTPUT_CSV)},
        PROGRESS_JSONL
    )

    confirmed_count = 0
    for i, idx in enumerate(to_process):
        row = df.iloc[idx]
        brand = row.get('brand', '') or f'Row {idx}'
        webpage = str(row.get('webpage', '')).strip()

        print(f"[{i + 1}/{total}] {brand} | {webpage[:50]}...")

        content = collect_site_content(webpage, brand)
        type_val, certainty = call_openai_classify(brand, content, webpage)

        record = {
            'idx': int(idx),
            'brand': brand,
            'webpage': webpage,
            'type': type_val,
            'certainty': certainty,
            'content_length': len(content) if content else 0,
        }
        log_progress(record, PROGRESS_JSONL)
        print(f"  {json.dumps(record, ensure_ascii=False)}")

        if type_val and certainty == 'Confirmed':
            df.at[idx, 'type'] = type_val
            confirmed_count += 1
            print(f"  ✓ Updated type = {type_val}")
        else:
            print(f"  ○ Skipped (certainty={certainty})")

        time.sleep(1.2)

    df.to_csv(OUTPUT_CSV, index=False)
    log_progress({'event': 'done', 'confirmed': confirmed_count, 'total': total}, PROGRESS_JSONL)

    print(f"\nSaved to {OUTPUT_CSV.name}")
    print(f"Progress: {PROGRESS_JSONL.name}")
    print(f"Types confirmed and written: {confirmed_count} / {total}")


if __name__ == '__main__':
    main()
