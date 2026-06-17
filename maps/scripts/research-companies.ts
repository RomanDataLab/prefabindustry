/**
 * research-companies.ts
 *
 * Fetches each company's webpage to extract:
 *   1. configurator URL – the main page listing models/houses/panels
 *   2. desc – a short company presentation (what it does, products/services)
 *
 * Saves progress incrementally so it can be resumed.
 *
 * Usage:  npx tsx scripts/research-companies.ts
 * Resume: npx tsx scripts/research-companies.ts   (skips already-done rows)
 * Force:  npx tsx scripts/research-companies.ts --force   (redo all)
 */

import fs from 'node:fs';
import path from 'node:path';

/* ------------------------------------------------------------------ */
/*  Paths                                                              */
/* ------------------------------------------------------------------ */
const ROOT = process.cwd();
const PUBLIC_DIR = path.join(ROOT, 'public');
const INPUT_CSV = path.join(PUBLIC_DIR, 'prefabworldfin_reducedby_7.csv');
const OUTPUT_CSV = path.join(PUBLIC_DIR, 'prefabworldfin_reducedby_7.csv'); // overwrite in place
const PROGRESS_FILE = path.join(ROOT, 'scripts', '.research-progress.json');

/* ------------------------------------------------------------------ */
/*  Config                                                             */
/* ------------------------------------------------------------------ */
const CONCURRENCY = 5;
const FETCH_TIMEOUT_MS = 15_000;
const DELAY_BETWEEN_BATCHES_MS = 500;
const MAX_RETRIES = 2;
const FORCE = process.argv.includes('--force');

/* ------------------------------------------------------------------ */
/*  CSV helpers (handle quoted fields with commas/newlines)            */
/* ------------------------------------------------------------------ */
function parseCsvLine(line: string): string[] {
  const fields: string[] = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"') {
        if (i + 1 < line.length && line[i + 1] === '"') {
          current += '"';
          i++; // skip escaped quote
        } else {
          inQuotes = false;
        }
      } else {
        current += ch;
      }
    } else {
      if (ch === '"') {
        inQuotes = true;
      } else if (ch === ',') {
        fields.push(current);
        current = '';
      } else {
        current += ch;
      }
    }
  }
  fields.push(current);
  return fields;
}

/** Properly handle multiline CSV fields (fields with newlines inside quotes) */
function parseCsvContent(content: string): string[][] {
  const rows: string[][] = [];
  const lines = content.split('\n');
  let currentLine = '';
  let inQuotes = false;

  for (const line of lines) {
    if (currentLine === '' && !inQuotes) {
      // Start a new logical line
      currentLine = line;
    } else {
      // Continue previous logical line (inside quotes)
      currentLine += '\n' + line;
    }

    // Count unescaped quotes to determine if we're inside a quoted field
    let quoteCount = 0;
    for (let i = 0; i < currentLine.length; i++) {
      if (currentLine[i] === '"') {
        if (i + 1 < currentLine.length && currentLine[i + 1] === '"') {
          i++; // skip escaped quote
        } else {
          quoteCount++;
        }
      }
    }
    inQuotes = quoteCount % 2 !== 0;

    if (!inQuotes) {
      const trimmed = currentLine.trim();
      if (trimmed.length > 0) {
        rows.push(parseCsvLine(trimmed));
      }
      currentLine = '';
    }
  }

  // Handle last line
  if (currentLine.trim().length > 0) {
    rows.push(parseCsvLine(currentLine.trim()));
  }

  return rows;
}

function csvEscape(value: string): string {
  if (!value) return '';
  // Quote if contains comma, quote, or newline
  if (value.includes(',') || value.includes('"') || value.includes('\n') || value.includes('\r')) {
    return '"' + value.replace(/"/g, '""') + '"';
  }
  return value;
}

function rowToCsv(fields: string[]): string {
  return fields.map(csvEscape).join(',');
}

/* ------------------------------------------------------------------ */
/*  HTML helpers                                                       */
/* ------------------------------------------------------------------ */
function stripHtml(html: string): string {
  return html
    .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
    .replace(/<nav[^>]*>[\s\S]*?<\/nav>/gi, '')
    .replace(/<footer[^>]*>[\s\S]*?<\/footer>/gi, '')
    .replace(/<header[^>]*>[\s\S]*?<\/header>/gi, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/\s+/g, ' ')
    .trim();
}

/** Extract meta description or og:description */
function extractMetaDescription(html: string): string {
  // og:description first (usually richer)
  const ogMatch = html.match(/<meta[^>]+property=["']og:description["'][^>]+content=["']([^"']+)["']/i)
    || html.match(/<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:description["']/i);
  if (ogMatch?.[1]?.trim()) return ogMatch[1].trim();

  // meta description
  const metaMatch = html.match(/<meta[^>]+name=["']description["'][^>]+content=["']([^"']+)["']/i)
    || html.match(/<meta[^>]+content=["']([^"']+)["'][^>]+name=["']description["']/i);
  if (metaMatch?.[1]?.trim()) return metaMatch[1].trim();

  return '';
}

/** Extract page title */
function extractTitle(html: string): string {
  const match = html.match(/<title[^>]*>([^<]+)<\/title>/i);
  return match?.[1]?.trim() || '';
}

/** Find "about" or introductory text from the page */
function extractAboutText(html: string): string {
  // Look for about sections, hero text, intro paragraphs
  const aboutPatterns = [
    /<(?:section|div)[^>]*(?:class|id)=["'][^"']*(?:about|intro|hero|welcome|description|company)[^"']*["'][^>]*>([\s\S]*?)<\/(?:section|div)>/gi,
    /<main[^>]*>([\s\S]*?)<\/main>/gi,
  ];

  for (const pattern of aboutPatterns) {
    const match = pattern.exec(html);
    if (match?.[1]) {
      const text = stripHtml(match[1]);
      // Return first 2-3 meaningful sentences (up to 500 chars)
      if (text.length > 30) {
        const sentences = text.match(/[^.!?]+[.!?]+/g);
        if (sentences) {
          let result = '';
          for (const s of sentences) {
            if (result.length + s.length > 500) break;
            result += s.trim() + ' ';
          }
          return result.trim();
        }
        return text.slice(0, 500).trim();
      }
    }
  }

  // Fallback: first substantial <p> tag
  const pTags = html.match(/<p[^>]*>([\s\S]*?)<\/p>/gi);
  if (pTags) {
    for (const p of pTags) {
      const text = stripHtml(p);
      if (text.length > 40 && !text.includes('cookie') && !text.includes('©')) {
        const sentences = text.match(/[^.!?]+[.!?]+/g);
        if (sentences) {
          let result = '';
          for (const s of sentences) {
            if (result.length + s.length > 500) break;
            result += s.trim() + ' ';
          }
          return result.trim();
        }
        return text.slice(0, 500).trim();
      }
    }
  }

  return '';
}

/** Build company description from extracted data */
function buildDescription(
  brand: string,
  type: string,
  metaDesc: string,
  aboutText: string,
  pageTitle: string,
): string {
  // Prefer meta description if it's informative (> 50 chars, not just brand name)
  if (metaDesc.length > 50) {
    return metaDesc.slice(0, 600);
  }

  // Use about text if we found one
  if (aboutText.length > 50) {
    return aboutText.slice(0, 600);
  }

  // Use meta description even if shorter
  if (metaDesc.length > 20) {
    return metaDesc.slice(0, 600);
  }

  // Fallback
  return '';
}

/* ------------------------------------------------------------------ */
/*  URL finding: configurator / products page                         */
/* ------------------------------------------------------------------ */
const PRODUCT_PAGE_KEYWORDS = [
  'models', 'model', 'modelos', 'modeles', 'modelle',
  'products', 'product', 'productos', 'produits', 'produkte', 'prodotti',
  'houses', 'house', 'casas', 'maisons', 'hauser', 'hus',
  'homes', 'home',
  'catalogue', 'catalog', 'catalogo', 'katalog',
  'portfolio', 'progetti', 'projets', 'projekte',
  'projects', 'project',
  'collection', 'collections',
  'range', 'ranges', 'gamme',
  'modules', 'module', 'modulos',
  'configurator', 'configure',
  'typologies', 'typology',
  'floor-plans', 'floorplans', 'floor_plans',
  'gallery', 'galerie', 'galleria',
  'buildings', 'building',
  'solutions', 'solution',
  'series', 'serie',
  'designs', 'design',
  'panels', 'panel', 'paneles', 'panneaux',
  'prefab', 'prefabricated',
  'tiny-house', 'tiny-houses', 'tinyhouse',
  'cabin', 'cabins',
  'modular', 'modulaire',
  'offerta', 'angebote', 'angebot',
  'shop',
];

function extractProductPageUrl(html: string, baseUrl: string): string {
  // Parse all <a> links
  const linkRegex = /<a\s[^>]*href=["']([^"'#]+)["'][^>]*>([\s\S]*?)<\/a>/gi;
  const candidates: { url: string; score: number }[] = [];

  let match;
  while ((match = linkRegex.exec(html)) !== null) {
    const href = match[1].trim();
    const linkText = stripHtml(match[2]).toLowerCase();

    // Skip external links, anchors, mailto, tel, javascript
    if (href.startsWith('mailto:') || href.startsWith('tel:') || href.startsWith('javascript:')) continue;
    if (href.length < 2) continue;

    // Resolve relative URLs
    let fullUrl: string;
    try {
      fullUrl = new URL(href, baseUrl).href;
    } catch {
      continue;
    }

    // Only same-domain links
    try {
      const base = new URL(baseUrl);
      const link = new URL(fullUrl);
      if (link.hostname !== base.hostname && !link.hostname.endsWith('.' + base.hostname)) continue;
    } catch {
      continue;
    }

    // Score by how well it matches product-page keywords
    const hrefLower = href.toLowerCase();
    let score = 0;

    for (const kw of PRODUCT_PAGE_KEYWORDS) {
      // Check in path segments
      if (hrefLower.includes('/' + kw) || hrefLower.includes(kw + '/') || hrefLower.includes('/' + kw + '/')) {
        score += 3;
      }
      // Check in link text
      if (linkText.includes(kw)) {
        score += 2;
      }
    }

    // Bonus for nav links (likely main navigation)
    if (score > 0) {
      candidates.push({ url: fullUrl, score });
    }
  }

  if (candidates.length === 0) return '';

  // Sort by score descending, pick best
  candidates.sort((a, b) => b.score - a.score);

  // Deduplicate (same path)
  const seen = new Set<string>();
  for (const c of candidates) {
    try {
      const u = new URL(c.url);
      const key = u.pathname.replace(/\/$/, '');
      if (seen.has(key)) continue;
      seen.add(key);
      return c.url;
    } catch {
      continue;
    }
  }

  return candidates[0]?.url || '';
}

/* ------------------------------------------------------------------ */
/*  Fetch with timeout and retry                                       */
/* ------------------------------------------------------------------ */
async function fetchWithTimeout(url: string, timeoutMs: number): Promise<string> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
      },
      redirect: 'follow',
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status} ${response.statusText}`);
    }

    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('text/html') && !contentType.includes('text/plain') && !contentType.includes('application/xhtml')) {
      throw new Error(`Not HTML: ${contentType}`);
    }

    const text = await response.text();
    // Limit to first 500KB to avoid memory issues
    return text.slice(0, 500_000);
  } finally {
    clearTimeout(timer);
  }
}

async function fetchRetry(url: string, retries = MAX_RETRIES): Promise<string> {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      return await fetchWithTimeout(url, FETCH_TIMEOUT_MS);
    } catch (err: any) {
      if (attempt === retries) throw err;
      await delay(1000 * (attempt + 1));
    }
  }
  throw new Error('unreachable');
}

/* ------------------------------------------------------------------ */
/*  Per-company research                                               */
/* ------------------------------------------------------------------ */
interface ResearchResult {
  configurator: string;
  desc: string;
}

async function researchCompany(
  brand: string,
  webpage: string,
  type: string,
): Promise<ResearchResult> {
  if (!webpage || webpage.trim().length < 5) {
    return { configurator: '', desc: '' };
  }

  let url = webpage.trim();
  if (!url.startsWith('http')) url = 'https://' + url;

  try {
    const html = await fetchRetry(url);

    // Extract configurator URL
    const configurator = extractProductPageUrl(html, url);

    // Extract description
    const metaDesc = extractMetaDescription(html);
    const aboutText = extractAboutText(html);
    const pageTitle = extractTitle(html);
    const desc = buildDescription(brand, type, metaDesc, aboutText, pageTitle);

    return { configurator, desc };
  } catch (err: any) {
    console.warn(`  ⚠ ${brand}: ${err.message}`);
    return { configurator: '', desc: '' };
  }
}

/* ------------------------------------------------------------------ */
/*  Progress tracking                                                  */
/* ------------------------------------------------------------------ */
interface ProgressData {
  done: Record<string, ResearchResult>; // keyed by company id
  lastUpdated: string;
}

function loadProgress(): ProgressData {
  if (FORCE) return { done: {}, lastUpdated: '' };
  try {
    const raw = fs.readFileSync(PROGRESS_FILE, 'utf8');
    return JSON.parse(raw);
  } catch {
    return { done: {}, lastUpdated: '' };
  }
}

function saveProgress(progress: ProgressData): void {
  progress.lastUpdated = new Date().toISOString();
  fs.writeFileSync(PROGRESS_FILE, JSON.stringify(progress, null, 2), 'utf8');
}

/* ------------------------------------------------------------------ */
/*  Utility                                                            */
/* ------------------------------------------------------------------ */
const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

/* ------------------------------------------------------------------ */
/*  Main                                                               */
/* ------------------------------------------------------------------ */
async function main() {
  console.log('Reading CSV...');
  const csvContent = fs.readFileSync(INPUT_CSV, 'utf8');
  const allRows = parseCsvContent(csvContent);

  if (allRows.length < 2) {
    console.error('CSV has no data rows');
    process.exit(1);
  }

  const headers = allRows[0];
  const dataRows = allRows.slice(1);

  // Find column indices
  const idIdx = headers.indexOf('id');
  const brandIdx = headers.indexOf('brand');
  const webpageIdx = headers.indexOf('webpage');
  const configIdx = headers.indexOf('configurator');
  const typeIdx = headers.indexOf('type');

  if (idIdx < 0 || brandIdx < 0 || webpageIdx < 0 || configIdx < 0) {
    console.error('Missing required columns in CSV');
    process.exit(1);
  }

  // Add desc column if not present
  let descIdx = headers.indexOf('desc');
  if (descIdx < 0) {
    headers.push('desc');
    descIdx = headers.length - 1;
    // Extend all data rows
    for (const row of dataRows) {
      while (row.length < headers.length) row.push('');
    }
    console.log('Added new "desc" column');
  }

  console.log(`Found ${dataRows.length} companies, ${headers.length} columns`);
  console.log(`Columns: id=${idIdx}, brand=${brandIdx}, webpage=${webpageIdx}, configurator=${configIdx}, desc=${descIdx}`);

  // Load progress
  const progress = loadProgress();
  const doneCount = Object.keys(progress.done).length;
  if (doneCount > 0) {
    console.log(`Resuming: ${doneCount} companies already researched`);
  }

  // Build work queue
  interface WorkItem {
    rowIndex: number;
    id: string;
    brand: string;
    webpage: string;
    type: string;
  }

  const work: WorkItem[] = [];
  for (let i = 0; i < dataRows.length; i++) {
    const row = dataRows[i];
    const id = row[idIdx] || '';
    const brand = row[brandIdx] || '';
    const webpage = row[webpageIdx] || '';
    const type = row[typeIdx] || '';

    // Skip if already done
    if (progress.done[id]) continue;

    // Skip if no webpage
    if (!webpage.trim()) {
      progress.done[id] = { configurator: '', desc: '' };
      continue;
    }

    work.push({ rowIndex: i, id, brand, webpage, type });
  }

  console.log(`${work.length} companies to research\n`);

  // Process in batches
  let processed = 0;
  for (let batchStart = 0; batchStart < work.length; batchStart += CONCURRENCY) {
    const batch = work.slice(batchStart, batchStart + CONCURRENCY);

    const results = await Promise.allSettled(
      batch.map(async (item) => {
        const result = await researchCompany(item.brand, item.webpage, item.type);
        return { ...item, result };
      }),
    );

    for (const r of results) {
      if (r.status === 'fulfilled') {
        const { id, brand, result } = r.value;
        progress.done[id] = result;
        processed++;
        const confStatus = result.configurator ? '✓' : '✗';
        const descStatus = result.desc ? `${result.desc.length}ch` : '✗';
        console.log(
          `  [${doneCount + processed}/${dataRows.length}] ${brand.padEnd(35)} conf:${confStatus}  desc:${descStatus}`,
        );
      } else {
        processed++;
        console.warn(`  [${doneCount + processed}/${dataRows.length}] FAILED: ${r.reason}`);
      }
    }

    // Save progress every batch
    saveProgress(progress);

    // Rate limit
    if (batchStart + CONCURRENCY < work.length) {
      await delay(DELAY_BETWEEN_BATCHES_MS);
    }
  }

  console.log(`\nResearch complete. Total: ${Object.keys(progress.done).length} companies\n`);

  // Apply results to CSV rows
  let configFilled = 0;
  let descFilled = 0;

  for (let i = 0; i < dataRows.length; i++) {
    const row = dataRows[i];
    const id = row[idIdx] || '';
    const result = progress.done[id];
    if (!result) continue;

    // Only update configurator if currently empty
    if (!row[configIdx]?.trim() && result.configurator) {
      row[configIdx] = result.configurator;
      configFilled++;
    }

    // Update desc
    if (result.desc) {
      // Ensure row has enough columns
      while (row.length <= descIdx) row.push('');
      row[descIdx] = result.desc;
      descFilled++;
    }
  }

  console.log(`Configurator URLs found: ${configFilled}`);
  console.log(`Descriptions found: ${descFilled}`);

  // Write output CSV
  const outputLines = [rowToCsv(headers)];
  for (const row of dataRows) {
    // Ensure correct column count
    while (row.length < headers.length) row.push('');
    outputLines.push(rowToCsv(row));
  }

  fs.writeFileSync(OUTPUT_CSV, outputLines.join('\n'), 'utf8');
  console.log(`\nWrote ${OUTPUT_CSV}`);

  // Clean up progress file on full completion
  if (Object.keys(progress.done).length >= dataRows.length) {
    console.log('All companies processed, keeping progress file for reference.');
  }
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
