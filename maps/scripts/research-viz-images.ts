/**
 * research-viz-images.ts
 *
 * For each company, fetches its [configurator] page (falls back to [webpage]),
 * finds up to 5 house/product images ≥ 800×600 px, and saves them as a JSON
 * array in the [viz] column.  Clears old viz data first.
 *
 * Image dimension detection:
 *   1. HTML width/height attributes
 *   2. URL dimension patterns  (e.g. -1024x768.jpg)
 *   3. srcset descriptors
 *   4. Probe first 32 KB of file to read JPEG / PNG / WebP headers
 *
 * Usage:  npx tsx scripts/research-viz-images.ts
 * Resume: npx tsx scripts/research-viz-images.ts        (skips done rows)
 * Force:  npx tsx scripts/research-viz-images.ts --force (redo all)
 */

import fs from 'node:fs';
import path from 'node:path';

/* ------------------------------------------------------------------ */
/*  Paths                                                              */
/* ------------------------------------------------------------------ */
const ROOT = process.cwd();
const PUBLIC_DIR = path.join(ROOT, 'public');
const CSV_PATH = path.join(PUBLIC_DIR, 'prefabworldfin_reducedby_7.csv');
const PROGRESS_FILE = path.join(ROOT, 'scripts', '.viz-progress.json');

/* ------------------------------------------------------------------ */
/*  Config                                                             */
/* ------------------------------------------------------------------ */
const CONCURRENCY = 5;
const FETCH_TIMEOUT_MS = 15_000;
const PROBE_TIMEOUT_MS = 8_000;
const DELAY_BETWEEN_BATCHES_MS = 500;
const MAX_RETRIES = 2;
const TARGET_IMAGES = 5;
const MIN_WIDTH = 800;
const MIN_HEIGHT = 600;
const FORCE = process.argv.includes('--force');

/* ------------------------------------------------------------------ */
/*  CSV helpers                                                        */
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
          i++;
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

function parseCsvContent(content: string): string[][] {
  const rows: string[][] = [];
  const lines = content.split('\n');
  let currentLine = '';
  let inQuotes = false;

  for (const line of lines) {
    if (currentLine === '' && !inQuotes) {
      currentLine = line;
    } else {
      currentLine += '\n' + line;
    }
    let quoteCount = 0;
    for (let i = 0; i < currentLine.length; i++) {
      if (currentLine[i] === '"') {
        if (i + 1 < currentLine.length && currentLine[i + 1] === '"') {
          i++;
        } else {
          quoteCount++;
        }
      }
    }
    inQuotes = quoteCount % 2 !== 0;
    if (!inQuotes) {
      const trimmed = currentLine.trim();
      if (trimmed.length > 0) rows.push(parseCsvLine(trimmed));
      currentLine = '';
    }
  }
  if (currentLine.trim().length > 0) rows.push(parseCsvLine(currentLine.trim()));
  return rows;
}

function csvEscape(value: string): string {
  if (!value) return '';
  if (value.includes(',') || value.includes('"') || value.includes('\n') || value.includes('\r')) {
    return '"' + value.replace(/"/g, '""') + '"';
  }
  return value;
}

function rowToCsv(fields: string[]): string {
  return fields.map(csvEscape).join(',');
}

/* ------------------------------------------------------------------ */
/*  Fetch helpers                                                      */
/* ------------------------------------------------------------------ */
const HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
  Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
  'Accept-Language': 'en-US,en;q=0.9',
};

async function fetchHtml(url: string, timeoutMs = FETCH_TIMEOUT_MS): Promise<string> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: controller.signal, headers: HEADERS, redirect: 'follow' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const ct = res.headers.get('content-type') || '';
    if (!ct.includes('text/html') && !ct.includes('application/xhtml')) throw new Error(`Not HTML: ${ct}`);
    return (await res.text()).slice(0, 600_000);
  } finally {
    clearTimeout(timer);
  }
}

async function fetchRetry(url: string, retries = MAX_RETRIES): Promise<string> {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try { return await fetchHtml(url); } catch (err: any) {
      if (attempt === retries) throw err;
      await delay(1000 * (attempt + 1));
    }
  }
  throw new Error('unreachable');
}

/* ------------------------------------------------------------------ */
/*  Image dimension probing                                            */
/* ------------------------------------------------------------------ */

/** Read JPEG dimensions from binary data */
function jpegDimensions(buf: Buffer): { w: number; h: number } | null {
  if (buf[0] !== 0xff || buf[1] !== 0xd8) return null;
  let offset = 2;
  while (offset < buf.length - 8) {
    if (buf[offset] !== 0xff) return null;
    const marker = buf[offset + 1];
    // SOF markers: C0-C3, C5-C7, C9-CB, CD-CF
    if (
      (marker >= 0xc0 && marker <= 0xc3) ||
      (marker >= 0xc5 && marker <= 0xc7) ||
      (marker >= 0xc9 && marker <= 0xcb) ||
      (marker >= 0xcd && marker <= 0xcf)
    ) {
      const h = buf.readUInt16BE(offset + 5);
      const w = buf.readUInt16BE(offset + 7);
      if (w > 0 && h > 0) return { w, h };
    }
    // Skip marker
    if (marker === 0xd8 || marker === 0xd9) {
      offset += 2;
    } else {
      const len = buf.readUInt16BE(offset + 2);
      offset += 2 + len;
    }
  }
  return null;
}

/** Read PNG dimensions */
function pngDimensions(buf: Buffer): { w: number; h: number } | null {
  // PNG signature: 137 80 78 71 13 10 26 10
  if (buf.length < 24) return null;
  if (buf[0] !== 0x89 || buf[1] !== 0x50 || buf[2] !== 0x4e || buf[3] !== 0x47) return null;
  const w = buf.readUInt32BE(16);
  const h = buf.readUInt32BE(20);
  return w > 0 && h > 0 ? { w, h } : null;
}

/** Read WebP dimensions */
function webpDimensions(buf: Buffer): { w: number; h: number } | null {
  if (buf.length < 30) return null;
  const riff = buf.toString('ascii', 0, 4);
  const webp = buf.toString('ascii', 8, 12);
  if (riff !== 'RIFF' || webp !== 'WEBP') return null;
  const chunk = buf.toString('ascii', 12, 16);
  if (chunk === 'VP8 ' && buf.length >= 30) {
    const w = buf.readUInt16LE(26) & 0x3fff;
    const h = buf.readUInt16LE(28) & 0x3fff;
    return w > 0 && h > 0 ? { w, h } : null;
  }
  if (chunk === 'VP8L' && buf.length >= 25) {
    const bits = buf.readUInt32LE(21);
    const w = (bits & 0x3fff) + 1;
    const h = ((bits >> 14) & 0x3fff) + 1;
    return w > 0 && h > 0 ? { w, h } : null;
  }
  if (chunk === 'VP8X' && buf.length >= 30) {
    const w = ((buf[24] | (buf[25] << 8) | (buf[26] << 16)) & 0xffffff) + 1;
    const h = ((buf[27] | (buf[28] << 8) | (buf[29] << 16)) & 0xffffff) + 1;
    return w > 0 && h > 0 ? { w, h } : null;
  }
  return null;
}

/** Probe image URL to get dimensions by downloading first 32KB */
async function probeImageDimensions(url: string): Promise<{ w: number; h: number } | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
  try {
    const res = await fetch(url, {
      signal: controller.signal,
      headers: {
        ...HEADERS,
        Accept: 'image/*',
        Range: 'bytes=0-32767',
      },
      redirect: 'follow',
    });
    if (!res.ok && res.status !== 206) return null;
    const ct = res.headers.get('content-type') || '';
    if (!ct.includes('image/')) return null;

    const arrayBuf = await res.arrayBuffer();
    const buf = Buffer.from(arrayBuf);

    if (ct.includes('jpeg') || ct.includes('jpg')) return jpegDimensions(buf);
    if (ct.includes('png')) return pngDimensions(buf);
    if (ct.includes('webp')) return webpDimensions(buf);

    // Try all parsers
    return jpegDimensions(buf) || pngDimensions(buf) || webpDimensions(buf);
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/* ------------------------------------------------------------------ */
/*  Image extraction from HTML                                         */
/* ------------------------------------------------------------------ */

/** Patterns to exclude (logos, icons, social media, tracking pixels) */
const EXCLUDE_PATTERNS = [
  /logo/i, /icon/i, /favicon/i, /sprite/i,
  /social/i, /facebook/i, /twitter/i, /instagram/i, /linkedin/i, /youtube/i, /pinterest/i,
  /whatsapp/i, /tiktok/i, /telegram/i,
  /badge/i, /banner-ad/i, /advertisement/i, /tracking/i, /pixel/i, /analytics/i,
  /\.svg$/i, /\.gif$/i,
  /gravatar/i, /avatar/i,
  /payment/i, /visa/i, /mastercard/i, /paypal/i,
  /cookie/i, /gdpr/i,
  /arrow/i, /bullet/i, /separator/i, /divider/i,
  /placeholder/i, /dummy/i, /blank/i, /spacer/i,
  /1x1/i, /loading/i, /spinner/i,
  /wp-emoji/i, /smilies/i,
];

/** URL dimension pattern: 800x600, 1024x768, etc. */
function extractUrlDimensions(url: string): { w: number; h: number } | null {
  // Patterns like: -1024x768.jpg, _800x600.png, /1200x900/
  const match = url.match(/[-_\/](\d{3,5})x(\d{3,5})[-_\/.]/);
  if (match) {
    const w = parseInt(match[1], 10);
    const h = parseInt(match[2], 10);
    if (w >= 100 && h >= 100 && w < 10000 && h < 10000) return { w, h };
  }
  return null;
}

interface ImageCandidate {
  url: string;
  w: number | null;
  h: number | null;
  score: number; // higher = more likely a house photo
}

function extractImageCandidates(html: string, baseUrl: string): ImageCandidate[] {
  const candidates: ImageCandidate[] = [];
  const seen = new Set<string>();

  // Extract <img> tags
  const imgRegex = /<img\s([^>]+)\/?>/gi;
  let match;

  while ((match = imgRegex.exec(html)) !== null) {
    const attrs = match[1];

    // Get src
    const srcMatch = attrs.match(/src=["']([^"']+)["']/i);
    if (!srcMatch) continue;
    let src = srcMatch[1].trim();
    if (!src || src.startsWith('data:')) continue;

    // Resolve URL
    let fullUrl: string;
    try {
      fullUrl = new URL(src, baseUrl).href;
    } catch { continue; }

    // Skip excluded patterns
    if (EXCLUDE_PATTERNS.some((p) => p.test(fullUrl))) continue;

    // Deduplicate
    const urlKey = fullUrl.replace(/[?#].*$/, '');
    if (seen.has(urlKey)) continue;
    seen.add(urlKey);

    // Get dimensions from attributes
    let w: number | null = null;
    let h: number | null = null;
    const widthMatch = attrs.match(/\bwidth=["']?(\d+)/i);
    const heightMatch = attrs.match(/\bheight=["']?(\d+)/i);
    if (widthMatch && heightMatch) {
      w = parseInt(widthMatch[1], 10);
      h = parseInt(heightMatch[1], 10);
    }

    // Try URL dimension pattern
    if (w === null || h === null) {
      const urlDims = extractUrlDimensions(fullUrl);
      if (urlDims) {
        w = urlDims.w;
        h = urlDims.h;
      }
    }

    // Check srcset for larger versions
    const srcsetMatch = attrs.match(/srcset=["']([^"']+)["']/i);
    let bestSrcsetUrl = fullUrl;
    if (srcsetMatch) {
      const entries = srcsetMatch[1].split(',').map((e) => e.trim());
      let bestW = 0;
      for (const entry of entries) {
        const parts = entry.split(/\s+/);
        if (parts.length >= 2) {
          const wMatch = parts[1].match(/(\d+)w/);
          if (wMatch) {
            const srcW = parseInt(wMatch[1], 10);
            if (srcW > bestW) {
              bestW = srcW;
              try { bestSrcsetUrl = new URL(parts[0], baseUrl).href; } catch { /* keep prev */ }
            }
          }
        }
      }
      if (bestW >= MIN_WIDTH && bestSrcsetUrl !== fullUrl) {
        fullUrl = bestSrcsetUrl;
        w = bestW;
      }
    }

    // Scoring: higher = more likely a house photo
    let score = 0;
    const urlLower = fullUrl.toLowerCase();
    const altMatch = attrs.match(/alt=["']([^"']+)["']/i);
    const altText = (altMatch?.[1] || '').toLowerCase();

    // Positive signals
    if (/house|home|cabin|villa|modular|prefab|building|exterior|facade|model|project/i.test(urlLower)) score += 3;
    if (/house|home|cabin|villa|modular|prefab|building|exterior|facade|model|project/i.test(altText)) score += 3;
    if (/product|gallery|portfolio|photo|image|img/i.test(urlLower)) score += 2;
    if (/hero|featured|main|slider|banner/i.test(urlLower)) score += 2;
    if (/uploads|content|media|images/i.test(urlLower)) score += 1;

    // Known large image paths
    if (/wp-content\/uploads/i.test(urlLower)) score += 2;
    if (/\/gallery\//i.test(urlLower)) score += 2;

    // Negative signals
    if (/thumb|thumbnail|small|tiny|mini|preview/i.test(urlLower)) score -= 2;
    if (/team|staff|employee|author|profile/i.test(urlLower)) score -= 3;
    if (/blog|news|article/i.test(urlLower)) score -= 1;
    if (/certificate|award|partner|sponsor|client-logo/i.test(urlLower)) score -= 3;

    // If dimensions known and too small, skip entirely
    if (w !== null && h !== null && (w < MIN_WIDTH || h < MIN_HEIGHT)) continue;

    candidates.push({ url: fullUrl, w, h, score });
  }

  // Also look for background-image CSS patterns (common in sliders/heroes)
  const bgRegex = /background(?:-image)?\s*:\s*url\(["']?([^"')]+)["']?\)/gi;
  while ((match = bgRegex.exec(html)) !== null) {
    let src = match[1].trim();
    if (!src || src.startsWith('data:')) continue;
    let fullUrl: string;
    try { fullUrl = new URL(src, baseUrl).href; } catch { continue; }
    if (EXCLUDE_PATTERNS.some((p) => p.test(fullUrl))) continue;
    const urlKey = fullUrl.replace(/[?#].*$/, '');
    if (seen.has(urlKey)) continue;
    seen.add(urlKey);
    const urlDims = extractUrlDimensions(fullUrl);
    candidates.push({
      url: fullUrl,
      w: urlDims?.w || null,
      h: urlDims?.h || null,
      score: 2, // background images are often hero/product images
    });
  }

  // Sort by score descending
  candidates.sort((a, b) => b.score - a.score);
  return candidates;
}

/* ------------------------------------------------------------------ */
/*  Per-company research                                               */
/* ------------------------------------------------------------------ */
async function researchImages(
  brand: string,
  configurator: string,
  webpage: string,
): Promise<string[]> {
  const url = (configurator || webpage || '').trim();
  if (!url || url.length < 5) return [];

  const fullUrl = url.startsWith('http') ? url : 'https://' + url;

  try {
    const html = await fetchRetry(fullUrl);
    const candidates = extractImageCandidates(html, fullUrl);

    if (candidates.length === 0) return [];

    // Phase 1: collect images with known good dimensions
    const verified: string[] = [];

    for (const c of candidates) {
      if (verified.length >= TARGET_IMAGES) break;

      if (c.w !== null && c.h !== null) {
        if (c.w >= MIN_WIDTH && c.h >= MIN_HEIGHT) {
          verified.push(c.url);
        }
        continue;
      }

      // Phase 2: probe unknown-dimension images
      try {
        const dims = await probeImageDimensions(c.url);
        if (dims && dims.w >= MIN_WIDTH && dims.h >= MIN_HEIGHT) {
          verified.push(c.url);
        }
      } catch {
        // skip
      }
    }

    return verified;
  } catch (err: any) {
    console.warn(`  ⚠ ${brand}: ${err.message}`);
    return [];
  }
}

/* ------------------------------------------------------------------ */
/*  Progress                                                           */
/* ------------------------------------------------------------------ */
interface ProgressData {
  done: Record<string, string[]>; // id → image urls
  lastUpdated: string;
}

function loadProgress(): ProgressData {
  if (FORCE) return { done: {}, lastUpdated: '' };
  try {
    return JSON.parse(fs.readFileSync(PROGRESS_FILE, 'utf8'));
  } catch {
    return { done: {}, lastUpdated: '' };
  }
}

function saveProgress(progress: ProgressData): void {
  progress.lastUpdated = new Date().toISOString();
  fs.writeFileSync(PROGRESS_FILE, JSON.stringify(progress, null, 2), 'utf8');
}

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

/* ------------------------------------------------------------------ */
/*  Main                                                               */
/* ------------------------------------------------------------------ */
async function main() {
  console.log('Reading CSV...');
  const csvContent = fs.readFileSync(CSV_PATH, 'utf8');
  const allRows = parseCsvContent(csvContent);

  if (allRows.length < 2) { console.error('No data'); process.exit(1); }

  const headers = allRows[0];
  const dataRows = allRows.slice(1);

  const idIdx = headers.indexOf('id');
  const brandIdx = headers.indexOf('brand');
  const webpageIdx = headers.indexOf('webpage');
  const configIdx = headers.indexOf('configurator');
  const vizIdx = headers.indexOf('viz');

  if (idIdx < 0 || brandIdx < 0 || vizIdx < 0) {
    console.error('Missing columns'); process.exit(1);
  }

  console.log(`${dataRows.length} companies, viz column at index ${vizIdx}`);

  const progress = loadProgress();
  const prevDone = Object.keys(progress.done).length;
  if (prevDone > 0) console.log(`Resuming: ${prevDone} already done`);

  // Build work queue
  interface WorkItem { rowIdx: number; id: string; brand: string; configurator: string; webpage: string; }
  const work: WorkItem[] = [];

  for (let i = 0; i < dataRows.length; i++) {
    const row = dataRows[i];
    const id = row[idIdx] || '';
    if (progress.done[id] !== undefined) continue; // already done (even if empty)

    const brand = row[brandIdx] || '';
    const configurator = row[configIdx] || '';
    const webpage = row[webpageIdx] || '';

    if (!configurator.trim() && !webpage.trim()) {
      progress.done[id] = [];
      continue;
    }

    work.push({ rowIdx: i, id, brand, configurator, webpage });
  }

  console.log(`${work.length} companies to research\n`);

  let processed = 0;
  for (let batchStart = 0; batchStart < work.length; batchStart += CONCURRENCY) {
    const batch = work.slice(batchStart, batchStart + CONCURRENCY);

    const results = await Promise.allSettled(
      batch.map(async (item) => {
        const images = await researchImages(item.brand, item.configurator, item.webpage);
        return { ...item, images };
      }),
    );

    for (const r of results) {
      if (r.status === 'fulfilled') {
        const { id, brand, images } = r.value;
        progress.done[id] = images;
        processed++;
        console.log(
          `  [${prevDone + processed}/${dataRows.length}] ${brand.padEnd(35)} ${images.length} images`,
        );
      } else {
        processed++;
        console.warn(`  [${prevDone + processed}/${dataRows.length}] FAILED: ${r.reason}`);
      }
    }

    saveProgress(progress);
    if (batchStart + CONCURRENCY < work.length) await delay(DELAY_BETWEEN_BATCHES_MS);
  }

  console.log(`\nDone. Applying to CSV...\n`);

  // Apply to CSV
  let filled = 0;
  for (let i = 0; i < dataRows.length; i++) {
    const row = dataRows[i];
    const id = row[idIdx] || '';
    const images = progress.done[id];

    // Clear old viz and set new
    if (images && images.length > 0) {
      row[vizIdx] = JSON.stringify(images);
      filled++;
    } else {
      row[vizIdx] = '';
    }
  }

  console.log(`Viz populated: ${filled} / ${dataRows.length} companies`);

  // Write CSV
  const outputLines = [rowToCsv(headers)];
  for (const row of dataRows) {
    while (row.length < headers.length) row.push('');
    outputLines.push(rowToCsv(row));
  }

  fs.writeFileSync(CSV_PATH, outputLines.join('\n'), 'utf8');
  console.log(`Wrote ${CSV_PATH}`);
}

main().catch((err) => { console.error('Fatal:', err); process.exit(1); });
