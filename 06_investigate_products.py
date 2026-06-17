"""
Stage 2: Product Investigation
Investigate each company's webpage to identify clear product ranges (homes/panels).
Adds 'clear_products' (0/1) and 'product_range' (URL) columns.
"""
import csv
import asyncio
import aiohttp
import json
import re
import sys
import time
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent))
from configix.apiManager import ai_openai

INPUT_CSV = Path(__file__).parent / 'maps' / 'public' / 'prefabworldfin_reducedby_8.csv'
OUTPUT_CSV = Path(__file__).parent / 'maps' / 'public' / 'prefabworldfin_reducedby_9.csv'
PROGRESS_FILE = Path(__file__).parent / '06_product_progress.jsonl'

CONCURRENCY = 15
FETCH_TIMEOUT = 20

# Keywords that indicate product/model pages in navigation
PRODUCT_KEYWORDS = [
    # English
    'products', 'product', 'models', 'model', 'homes', 'houses', 'house',
    'range', 'catalog', 'catalogue', 'collection', 'collections',
    'our homes', 'our houses', 'our models', 'our products',
    'home designs', 'house designs', 'floor plans', 'floorplans',
    'modular homes', 'prefab homes', 'prefabricated',
    'panels', 'panel systems', 'wall panels', 'building systems',
    'solutions', 'offerings', 'portfolio',
    'types', 'series', 'lines', 'configurations',
    'tiny house', 'tiny homes', 'cabins', 'pods', 'lodges', 'glamping',
    # German
    'häuser', 'haeuser', 'haustypen', 'hausbau', 'fertighäuser', 'fertighaeuser',
    'baureihe', 'modelle', 'produkte', 'typenhaus', 'angebot',
    'einfamilienhaus', 'einfamilienhäuser', 'zweifamilienhaus', 'doppelhaus',
    'bungalow', 'stadthaus', 'stadtvilla',
    # French
    'maisons', 'modèles', 'modeles', 'gamme', 'nos maisons', 'réalisations', 'realisations',
    # Spanish
    'casas', 'modelos', 'viviendas', 'proyectos', 'soluciones',
    'módulos', 'modulos', 'prefabricado',
    # Portuguese
    'casas', 'modelos', 'projectos', 'projetos', 'moradias',
    # Italian
    'case', 'modelli', 'prodotti', 'soluzioni', 'abitazioni',
    # Dutch
    'woningen', 'huizen', 'producten', 'modellen', 'woningtypen',
    # Nordic
    'hus', 'hustyper', 'husmodeller', 'bolig', 'boliger', 'produkter',
    'hytter', 'hytte', 'fritidshus', 'villor', 'villaer',
    'talomallit', 'talot', 'tuotteet',
    # Polish/Czech/Eastern European
    'domy', 'projekty', 'produkty', 'modely', 'nabídka',
    # Russian
    'дома', 'проекты', 'продукция', 'каталог', 'модели',
    # Japanese
    '商品', '製品', 'ラインアップ', 'ラインナップ',
    # Chinese
    '产品', '项目', '住宅',
]

# URL path segments that indicate product pages
PRODUCT_PATH_SEGMENTS = [
    'product', 'model', 'home', 'house', 'range', 'catalog', 'collection',
    'design', 'plan', 'panel', 'solution', 'portfolio', 'cabin', 'pod',
    'haeuser', 'hauser', 'haus', 'maison', 'casa', 'vivienda',
    'woning', 'hus', 'bolig', 'hytte', 'talo', 'dom', 'projekt',
    'projet', 'proyecto', 'progetto',
]

client = OpenAI(api_key=ai_openai['api_key'])


def load_progress():
    """Load already-processed company IDs from progress file."""
    done = {}
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        done[str(rec['id'])] = rec
                    except:
                        pass
    return done


def save_progress(rec):
    """Append one result to progress file."""
    with open(PROGRESS_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')


def find_product_links(html, base_url):
    """Parse HTML and find links that look like product/model pages."""
    soup = BeautifulSoup(html, 'html.parser')
    candidates = []

    # Check nav elements, header, and prominent links
    nav_areas = soup.find_all(['nav', 'header'])
    if not nav_areas:
        nav_areas = [soup]

    all_links = []
    for area in nav_areas:
        all_links.extend(area.find_all('a', href=True))
    # Also check all links on page for product-heavy sites
    all_links.extend(soup.find_all('a', href=True))

    seen_urls = set()
    for link in all_links:
        href = link.get('href', '').strip()
        if not href or href.startswith('#') or href.startswith('mailto:') or href.startswith('tel:'):
            continue

        full_url = urljoin(base_url, href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        text = link.get_text(strip=True).lower()
        title = (link.get('title', '') or '').lower()
        href_lower = href.lower()

        score = 0

        # Check link text against keywords
        for kw in PRODUCT_KEYWORDS:
            if kw in text or kw in title:
                score += 3
                break

        # Check URL path for product-related segments
        path = urlparse(full_url).path.lower()
        for seg in PRODUCT_PATH_SEGMENTS:
            if seg in path:
                score += 2
                break

        # Bonus for being in nav
        if link.find_parent(['nav', 'header']):
            score += 1

        # Penalty for blog, news, about, contact, etc.
        skip_patterns = ['blog', 'news', 'about', 'contact', 'career', 'press',
                        'login', 'cart', 'checkout', 'privacy', 'imprint', 'impressum',
                        'legal', 'cookie', 'faq', 'team', 'partner', 'investor',
                        'download', 'newsletter', 'social', 'facebook', 'twitter',
                        'instagram', 'linkedin', 'youtube']
        for sp in skip_patterns:
            if sp in text or sp in href_lower:
                score -= 5
                break

        if score > 0:
            candidates.append((score, full_url, text[:80]))

    # Sort by score descending, return best
    candidates.sort(key=lambda x: -x[0])
    return candidates[:5]


async def fetch_page(session, url, timeout=FETCH_TIMEOUT):
    """Fetch a webpage, return HTML or None."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout),
                              ssl=False, allow_redirects=True) as resp:
            if resp.status == 200:
                return await resp.text(errors='replace')
    except Exception as e:
        pass
    return None


def analyze_with_ai(brand, country, webpage, html_snippet, candidates):
    """Use OpenAI to analyze ambiguous cases."""
    candidate_text = "\n".join([f"  - score={s}, url={u}, text='{t}'" for s, u, t in candidates[:5]])

    # Extract page title and meta description
    soup = BeautifulSoup(html_snippet[:50000], 'html.parser')
    title = soup.title.string if soup.title else "N/A"
    meta_desc = ""
    meta = soup.find('meta', attrs={'name': 'description'})
    if meta:
        meta_desc = meta.get('content', '')[:200]

    # Extract main nav links
    nav_links = []
    for nav in soup.find_all(['nav', 'header']):
        for a in nav.find_all('a', href=True):
            txt = a.get_text(strip=True)
            if txt and len(txt) < 60:
                nav_links.append(f"{txt} -> {a['href']}")
    nav_text = "\n".join(nav_links[:30])

    prompt = f"""Analyze this prefab/modular construction company's webpage.

Company: {brand} ({country})
URL: {webpage}
Page title: {title}
Meta: {meta_desc}

Navigation links found:
{nav_text}

Product link candidates (scored by heuristic):
{candidate_text}

TASK: Does this website clearly show a PRODUCT RANGE or MODEL catalog?
I need to identify pages where users can browse specific home models, house types, panel products, or building system products.

Answer in JSON:
{{"clear_products": 0 or 1, "product_range": "URL of the best product range/catalog page or empty string", "reason": "brief explanation"}}

Rules:
- clear_products=1 ONLY if the site clearly presents browsable products (homes, houses, panels, modules, cabins, pods, building systems)
- The product_range URL must be a direct link to the product listing/range page (NOT the homepage, NOT a single project page)
- If the company is clearly a construction services/contractor with no standard product range, set 0
- If you can't determine, set 0"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=200
        )
        text = response.choices[0].message.content.strip()
        # Extract JSON from response
        match = re.search(r'\{[^}]+\}', text, re.DOTALL)
        if match:
            result = json.loads(match.group())
            return result.get('clear_products', 0), result.get('product_range', ''), result.get('reason', '')
    except Exception as e:
        print(f"  AI error: {e}")
    return 0, '', 'AI analysis failed'


async def process_company(session, row, semaphore):
    """Process a single company: fetch webpage, analyze products."""
    company_id = row['id']
    brand = row.get('brand', '')
    country = row.get('country', '')
    webpage = row.get('webpage', '').strip()
    configurator = row.get('configurator', '').strip()

    async with semaphore:
        print(f"  [{company_id}] {brand} ({country}) - {webpage}")

        # If we already have a configurator URL with models, high confidence
        if configurator and row.get('models_amount', '').strip():
            try:
                models = float(row['models_amount'])
                if models >= 2:
                    print(f"    -> Quick pass: has configurator + {int(models)} models")
                    return {
                        'id': company_id,
                        'clear_products': 1,
                        'product_range': configurator,
                        'reason': f'Has configurator URL with {int(models)} models'
                    }
            except:
                pass

        # Fetch the webpage
        html = await fetch_page(session, webpage)
        if not html:
            # Try http if https failed
            if webpage.startswith('https://'):
                html = await fetch_page(session, webpage.replace('https://', 'http://'))
            elif webpage.startswith('http://'):
                html = await fetch_page(session, webpage.replace('http://', 'https://'))

        if not html:
            print(f"    -> FAIL: couldn't fetch webpage")
            # If has configurator, still give credit
            if configurator:
                return {
                    'id': company_id,
                    'clear_products': 1,
                    'product_range': configurator,
                    'reason': 'Webpage unreachable but has configurator URL'
                }
            return {
                'id': company_id,
                'clear_products': 0,
                'product_range': '',
                'reason': 'Webpage unreachable'
            }

        # Find product links in HTML
        candidates = find_product_links(html, webpage)

        # Strong heuristic match: top candidate has high score
        if candidates and candidates[0][0] >= 5:
            best_url = candidates[0][1]
            best_text = candidates[0][2]
            print(f"    -> Strong match: '{best_text}' -> {best_url}")
            return {
                'id': company_id,
                'clear_products': 1,
                'product_range': best_url,
                'reason': f'Strong nav link: {best_text}'
            }

        # If has configurator and some product signal
        if configurator and candidates and candidates[0][0] >= 2:
            print(f"    -> Configurator + weak match")
            return {
                'id': company_id,
                'clear_products': 1,
                'product_range': configurator,
                'reason': f'Has configurator + product signals'
            }

        # Use AI for ambiguous cases
        print(f"    -> AI analysis (score={candidates[0][0] if candidates else 0})...")
        clear, product_url, reason = analyze_with_ai(brand, country, webpage, html, candidates)

        # If AI says yes but no product URL, use configurator or best candidate
        if clear == 1 and not product_url:
            if configurator:
                product_url = configurator
            elif candidates:
                product_url = candidates[0][1]

        print(f"    -> AI result: clear={clear}, url={product_url[:80] if product_url else 'none'}")
        return {
            'id': company_id,
            'clear_products': clear,
            'product_range': product_url or '',
            'reason': reason
        }


async def main():
    # Load input CSV
    with open(INPUT_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    print(f"Loaded {len(rows)} companies from {INPUT_CSV.name}")

    # Load progress
    progress = load_progress()
    print(f"Already processed: {len(progress)} companies")

    # Filter to unprocessed
    to_process = [r for r in rows if str(r['id']) not in progress]
    print(f"Remaining to process: {len(to_process)}")

    if to_process:
        semaphore = asyncio.Semaphore(CONCURRENCY)
        connector = aiohttp.TCPConnector(limit=CONCURRENCY, ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Process in batches of 30
            batch_size = 30
            for i in range(0, len(to_process), batch_size):
                batch = to_process[i:i+batch_size]
                batch_num = i // batch_size + 1
                total_batches = (len(to_process) + batch_size - 1) // batch_size
                print(f"\n=== Batch {batch_num}/{total_batches} ({len(batch)} companies) ===")

                tasks = [process_company(session, row, semaphore) for row in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if isinstance(result, Exception):
                        print(f"  ERROR: {result}")
                        continue
                    if result:
                        progress[str(result['id'])] = result
                        save_progress(result)

                # Brief pause between batches
                if i + batch_size < len(to_process):
                    await asyncio.sleep(1)

    # Write output CSV
    out_fieldnames = list(fieldnames) + ['clear_products', 'product_range']
    with open(OUTPUT_CSV, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=out_fieldnames, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            rid = str(row['id'])
            if rid in progress:
                row['clear_products'] = progress[rid].get('clear_products', 0)
                row['product_range'] = progress[rid].get('product_range', '')
            else:
                row['clear_products'] = 0
                row['product_range'] = ''
            writer.writerow(row)

    # Summary
    total = len(rows)
    clear = sum(1 for r in rows if str(r['id']) in progress and progress[str(r['id'])].get('clear_products') == 1)
    unclear = total - clear
    print(f"\n{'='*60}")
    print(f"DONE: {total} companies processed")
    print(f"  Clear products: {clear}")
    print(f"  No clear products: {unclear}")
    print(f"  Output: {OUTPUT_CSV.name}")


if __name__ == '__main__':
    asyncio.run(main())
