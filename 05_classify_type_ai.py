#!/usr/bin/env python3
"""
05_classify_type_ai.py
Reads prefabworldfin_reducedby_4.csv and updates the same file.

If [type] is null:
  - Same goals/methods as 04: identify main product type (home, industrial, panels, etc.)
  - Never leave type null: use best inference (Confirmed/Reported) or fallback "unknown"

If [type] already has a value:
  - Assign from proposed list ONLY if Confirmed (clearly stated)
  - Otherwise: evaluate the actual main product or service from the website

Up to 15 page-fetch stages per site to evaluate main product or service.
Progress logged to 05_classify_type_progress.jsonl
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

# Paths - same file for input and output
INPUT_CSV = Path(__file__).parent / 'maps' / 'public' / 'prefabworldfin_reducedby_4.csv'
OUTPUT_CSV = Path(__file__).parent / 'maps' / 'public' / 'prefabworldfin_reducedby_4.csv'
PROGRESS_JSONL = Path(__file__).parent / '05_classify_type_progress.jsonl'

FETCH_TIMEOUT = 15
MAX_PAGES_PER_SITE = 15  # Main + up to 14 relevant subpages (stages of search)


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

Which links likely contain: products, services, what we build, portfolio, projects, residential, industrial, panels, modular, prefab, about, company?
Return ONLY a JSON array of up to 8 URLs: ["url1", "url2"]
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
            return [u for u in arr if isinstance(u, str) and u in candidates][:8]
    except Exception:
        pass
    return []


def collect_site_content(webpage: str, brand: str) -> str:
    """
    Visit main page and relevant subpages (up to MAX_PAGES_PER_SITE stages); concatenate for AI analysis.
    On each page, use AI to find more relevant product links; add to queue for deeper search.
    Returns combined text (up to ~60k chars).
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

        # On each page, find relevant product/service links to extend search (more stages)
        if links:
            rel = _find_relevant_product_links(
                text or '', links, url, visited, brand
            )
            for link in rel[:5]:
                if link not in visited and link not in to_visit:
                    to_visit.append(link)

        time.sleep(0.8)

    return '\n\n'.join(collected)[:60000]


def call_openai_classify(brand: str, content: str, webpage: str) -> Tuple[str, str]:
    """
    Use AI to classify product type from webpage content (when type is null).
    Returns (type_value, certainty). Never returns null for type; uses 'unknown' fallback.
    """
    if not content or len(content.strip()) < 200:
        return 'unknown', 'Unknown'

    prompt = f"""Analyze the following webpage content from "{brand}" (URL: {webpage}).

Content from website (may include multiple pages):
{content[:50000]}

Determine what types of prefabricated products or services this company PREDOMINANTLY produces/offers:

- 'home' = predominantly prefabricated residential houses / single-family homes / housing
- 'industrial' = predominantly prefabricated industrial buildings (warehouses, factories, commercial)
- 'panels' = predominantly prefabricated panels / wall panels / structural panels
- If something else predominates, use ONE word (e.g. commercial, modular, cabins, doors, etc.)
- If truly impossible to determine, use 'unknown'

ALWAYS return a type - never use null. Use your best inference.

Certainty levels:
- [Confirmed] = clearly stated on the site
- [Reported] = inferred from context
- [Unknown] = minimal info, best guess

Respond with ONLY valid JSON:
{{"type": "home"|"industrial"|"panels"|"<one_word>"|"unknown", "certainty": "Confirmed"|"Reported"|"Unknown"}}"""

    for retry in range(3):
        try:
            resp = openai_client.chat.completions.create(
                model='gpt-4o',
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.1,
                max_tokens=150
            )
            text = (resp.choices[0].message.content or '').strip()
            m = re.search(r'\{[^{}]*\}', text)
            if m:
                data = json.loads(m.group(0))
                t = data.get('type')
                c = data.get('certainty', 'Unknown')
                if c not in ('Confirmed', 'Reported', 'Unknown'):
                    c = 'Unknown'
                if t and isinstance(t, str):
                    t = t.strip().lower()
                    if ' ' in t:
                        t = t.split()[0]
                    if len(t) > 25:
                        t = t[:25]
                    return t, c
                return 'unknown', c
        except Exception as e:
            err = str(e).lower()
            if any(k in err for k in ['rate limit', 'quota', '429', 'resource_exhausted']):
                wait = min(60 * (retry + 1), 300)
                print(f"    ⚠ Rate limit. Waiting {wait}s...")
                if retry < 2:
                    time.sleep(wait)
                    continue
            if retry == 2:
                return 'unknown', 'Unknown'
            time.sleep(2 * (retry + 1))
    return 'unknown', 'Unknown'


PROPOSED_TYPES = ['home', 'industrial', 'panels', 'modular', 'commercial', 'cabins', 'doors']


def call_openai_evaluate_existing_type(
    brand: str, content: str, webpage: str, proposed_type: str
) -> Tuple[str, str]:
    """
    When type already has a value:
    - Assign from proposed list ONLY if Confirmed
    - Otherwise: evaluate the actual main product or service (not from list)
    Never returns null; uses proposed_type as fallback.
    """
    if not content or len(content.strip()) < 200:
        return proposed_type, 'unchanged'

    prompt = f"""Analyze the following webpage content from "{brand}" (URL: {webpage}).

Content from website (may include multiple pages):
{content[:50000]}

The snippet proposes type = "{proposed_type}" for this company.

Step 1: Check if the MAIN product or service is CLEARLY (explicitly stated) one from this list:
{', '.join(PROPOSED_TYPES)}

Only use from_list_type if it is Confirmed (clearly stated on the site). Otherwise use null.

Step 2: Always determine evaluated_type = the actual main product or service (one word, lowercase) from the website.

Certainty for from_list: Confirmed = clearly stated; Reported = inferred; Unknown = not found.

Respond with ONLY valid JSON:
{{"from_list_type": "home"|"industrial"|"panels"|"modular"|"commercial"|"cabins"|"doors"|null, "from_list_certainty": "Confirmed"|"Reported"|"Unknown", "evaluated_type": "<one_word>"}}

Use from_list_type only when from_list_certainty is Confirmed. Otherwise use evaluated_type as the result."""

    for retry in range(3):
        try:
            resp = openai_client.chat.completions.create(
                model='gpt-4o',
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.1,
                max_tokens=150
            )
            text = (resp.choices[0].message.content or '').strip()
            m = re.search(r'\{[^{}]*\}', text)
            if m:
                data = json.loads(m.group(0))
                from_list = data.get('from_list_type')
                certainty = data.get('from_list_certainty', 'Unknown')
                evaluated = data.get('evaluated_type')

                def _norm(s):
                    if not s or not isinstance(s, str):
                        return None
                    s = s.strip().lower()
                    if ' ' in s:
                        s = s.split()[0]
                    return s[:25] if len(s) > 25 else s

                if certainty == 'Confirmed' and from_list and _norm(from_list) in PROPOSED_TYPES:
                    t = _norm(from_list)
                    return t, 'from_list'
                if evaluated:
                    t = _norm(evaluated)
                    if t:
                        return t, 'evaluated'
                return proposed_type, 'unchanged'
        except Exception as e:
            err = str(e).lower()
            if any(k in err for k in ['rate limit', 'quota', '429', 'resource_exhausted']):
                wait = min(60 * (retry + 1), 300)
                print(f"    ⚠ Rate limit. Waiting {wait}s...")
                if retry < 2:
                    time.sleep(wait)
                    continue
            if retry == 2:
                return proposed_type, 'unchanged'
            time.sleep(2 * (retry + 1))
    return proposed_type, 'unchanged'


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

    # Two groups: null type (classify) vs existing type (evaluate)
    to_classify = []
    to_evaluate = []
    for idx, row in df.iterrows():
        if _is_null(row.get('webpage')):
            continue
        url = str(row.get('webpage', '')).strip()
        if not _is_valid_url(url):
            continue
        if _is_null(row.get('type')):
            to_classify.append(idx)
        else:
            proposed = str(row.get('type', '')).strip()
            if proposed:
                to_evaluate.append((idx, proposed))

    total_classify = len(to_classify)
    total_evaluate = len(to_evaluate)
    total = total_classify + total_evaluate
    print(f"Rows with null type (classify): {total_classify}")
    print(f"Rows with existing type (evaluate): {total_evaluate}\n")

    if total == 0:
        print("Nothing to process.")
        return

    if PROGRESS_JSONL.exists():
        PROGRESS_JSONL.write_text('', encoding='utf-8')
    log_progress(
        {
            'event': 'start',
            'total_classify': total_classify,
            'total_evaluate': total_evaluate,
            'input': str(INPUT_CSV),
            'output': str(OUTPUT_CSV),
        },
        PROGRESS_JSONL
    )

    confirmed_count = 0
    updated_count = 0
    i = 0

    # 1. Classify rows with null type
    for idx in to_classify:
        i += 1
        row = df.iloc[idx]
        brand = row.get('brand', '') or f'Row {idx}'
        webpage = str(row.get('webpage', '')).strip()

        print(f"[{i}/{total}] (classify) {brand} | {webpage[:50]}...")

        content = collect_site_content(webpage, brand)
        type_val, certainty = call_openai_classify(brand, content, webpage)

        record = {
            'mode': 'classify',
            'idx': int(idx),
            'brand': brand,
            'webpage': webpage,
            'type': type_val,
            'certainty': certainty,
            'content_length': len(content) if content else 0,
        }
        log_progress(record, PROGRESS_JSONL)
        print(f"  {json.dumps(record, ensure_ascii=False)}")

        # Never leave type null; always write best inference or fallback
        df.at[idx, 'type'] = type_val
        if certainty == 'Confirmed':
            confirmed_count += 1
            print(f"  ✓ Updated type = {type_val}")
        else:
            print(f"  ✓ Assigned type = {type_val} (certainty={certainty})")

        time.sleep(1.2)

    # 2. Evaluate rows with existing type: first try from list, else figure out different
    for idx, proposed_type in to_evaluate:
        i += 1
        row = df.iloc[idx]
        brand = row.get('brand', '') or f'Row {idx}'
        webpage = str(row.get('webpage', '')).strip()

        print(f"[{i}/{total}] (evaluate) {brand} | proposed={proposed_type} | {webpage[:40]}...")

        content = collect_site_content(webpage, brand)
        type_val, source = call_openai_evaluate_existing_type(
            brand, content, webpage, proposed_type
        )

        record = {
            'mode': 'evaluate',
            'idx': int(idx),
            'brand': brand,
            'webpage': webpage,
            'proposed_type': proposed_type,
            'type': type_val,
            'source': source,
            'content_length': len(content) if content else 0,
        }
        log_progress(record, PROGRESS_JSONL)
        print(f"  {json.dumps(record, ensure_ascii=False)}")

        # Never leave type null; type_val is always set (from_list/different or proposed fallback)
        df.at[idx, 'type'] = type_val
        updated_count += 1
        print(f"  ✓ Updated type = {type_val} (source={source})")

        time.sleep(1.2)

    df.to_csv(OUTPUT_CSV, index=False)
    log_progress(
        {
            'event': 'done',
            'classified': confirmed_count,
            'updated': updated_count,
            'total_classify': total_classify,
            'total_evaluate': total_evaluate,
        },
        PROGRESS_JSONL
    )

    print(f"\nSaved to {OUTPUT_CSV.name}")
    print(f"Progress: {PROGRESS_JSONL.name}")
    print(f"Classified (null→type): {confirmed_count} / {total_classify}")
    print(f"Updated (evaluated): {updated_count} / {total_evaluate}")


if __name__ == '__main__':
    main()
