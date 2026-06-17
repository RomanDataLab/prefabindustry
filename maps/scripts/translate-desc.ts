/**
 * translate-desc.ts
 *
 * Reads [desc] column, translates non-English text to English,
 * saves result in new [desc_en] column.
 *
 * Uses Google Translate unofficial API (no key needed).
 *
 * Usage:  npx tsx scripts/translate-desc.ts
 * Resume: npx tsx scripts/translate-desc.ts        (skips done rows)
 * Force:  npx tsx scripts/translate-desc.ts --force
 */

import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const PUBLIC_DIR = path.join(ROOT, 'public');
const CSV_PATH = path.join(PUBLIC_DIR, 'prefabworldfin_reducedby_7.csv');
const PROGRESS_FILE = path.join(ROOT, 'scripts', '.translate-progress.json');

const CONCURRENCY = 3; // gentle on Google
const DELAY_BETWEEN_BATCHES_MS = 800;
const FETCH_TIMEOUT_MS = 10_000;
const MAX_RETRIES = 2;
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
        if (i + 1 < line.length && line[i + 1] === '"') { current += '"'; i++; }
        else inQuotes = false;
      } else current += ch;
    } else {
      if (ch === '"') inQuotes = true;
      else if (ch === ',') { fields.push(current); current = ''; }
      else current += ch;
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
    currentLine = currentLine === '' && !inQuotes ? line : currentLine + '\n' + line;
    let qc = 0;
    for (let i = 0; i < currentLine.length; i++) {
      if (currentLine[i] === '"') {
        if (i + 1 < currentLine.length && currentLine[i + 1] === '"') i++;
        else qc++;
      }
    }
    inQuotes = qc % 2 !== 0;
    if (!inQuotes) {
      const t = currentLine.trim();
      if (t.length > 0) rows.push(parseCsvLine(t));
      currentLine = '';
    }
  }
  if (currentLine.trim().length > 0) rows.push(parseCsvLine(currentLine.trim()));
  return rows;
}

function csvEscape(value: string): string {
  if (!value) return '';
  if (value.includes(',') || value.includes('"') || value.includes('\n') || value.includes('\r'))
    return '"' + value.replace(/"/g, '""') + '"';
  return value;
}

function rowToCsv(fields: string[]): string { return fields.map(csvEscape).join(','); }

/* ------------------------------------------------------------------ */
/*  Language detection (simple heuristic)                              */
/* ------------------------------------------------------------------ */
function looksEnglish(text: string): boolean {
  // Common English words - if many are present, likely English
  const markers = [
    'the', 'and', 'our', 'we', 'with', 'for', 'are', 'from', 'that', 'this',
    'have', 'has', 'your', 'you', 'offer', 'home', 'house', 'building',
    'quality', 'design', 'construction', 'modular', 'prefab', 'custom',
    'sustainable', 'built', 'company', 'solutions', 'provides', 'years',
    'experience', 'deliver', 'their', 'been', 'more', 'about', 'which',
  ];
  const words = text.toLowerCase().split(/\s+/);
  const totalWords = words.length;
  if (totalWords < 3) return true; // too short to tell

  let englishHits = 0;
  for (const w of words) {
    if (markers.includes(w)) englishHits++;
  }
  // If >15% of words are common English words, likely English
  return (englishHits / totalWords) > 0.15;
}

/* ------------------------------------------------------------------ */
/*  Google Translate                                                   */
/* ------------------------------------------------------------------ */
async function translateToEnglish(text: string): Promise<string> {
  const url = `https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=en&dt=t&q=${encodeURIComponent(text)}`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const res = await fetch(url, {
      signal: controller.signal,
      headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // Response format: [[["translated","original","","",1],...],null,"detected_lang"]
    if (Array.isArray(data) && Array.isArray(data[0])) {
      const translated = data[0]
        .filter((segment: any) => Array.isArray(segment) && segment[0])
        .map((segment: any) => segment[0])
        .join('');
      return translated.trim();
    }
    throw new Error('Unexpected response format');
  } finally {
    clearTimeout(timer);
  }
}

async function translateRetry(text: string, retries = MAX_RETRIES): Promise<string> {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try { return await translateToEnglish(text); } catch (err: any) {
      if (attempt === retries) throw err;
      await delay(2000 * (attempt + 1));
    }
  }
  throw new Error('unreachable');
}

/* ------------------------------------------------------------------ */
/*  Progress                                                           */
/* ------------------------------------------------------------------ */
interface ProgressData { done: Record<string, string>; lastUpdated: string; }

function loadProgress(): ProgressData {
  if (FORCE) return { done: {}, lastUpdated: '' };
  try { return JSON.parse(fs.readFileSync(PROGRESS_FILE, 'utf8')); }
  catch { return { done: {}, lastUpdated: '' }; }
}

function saveProgress(p: ProgressData): void {
  p.lastUpdated = new Date().toISOString();
  fs.writeFileSync(PROGRESS_FILE, JSON.stringify(p, null, 2), 'utf8');
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
  const descIdx = headers.indexOf('desc');

  if (idIdx < 0 || descIdx < 0) { console.error('Missing id or desc column'); process.exit(1); }

  // Add desc_en column if not present
  let descEnIdx = headers.indexOf('desc_en');
  if (descEnIdx < 0) {
    headers.push('desc_en');
    descEnIdx = headers.length - 1;
    for (const row of dataRows) { while (row.length < headers.length) row.push(''); }
    console.log('Added "desc_en" column');
  }

  console.log(`${dataRows.length} companies`);

  const progress = loadProgress();
  const prevDone = Object.keys(progress.done).length;
  if (prevDone > 0) console.log(`Resuming: ${prevDone} already done`);

  // Build work queue
  interface WorkItem { id: string; brand: string; desc: string; }
  const work: WorkItem[] = [];
  let skippedEmpty = 0;
  let skippedEnglish = 0;

  for (const row of dataRows) {
    const id = row[idIdx] || '';
    if (progress.done[id] !== undefined) continue;

    const desc = row[descIdx] || '';
    const brand = row[brandIdx] || '';

    if (!desc.trim()) {
      progress.done[id] = '';
      skippedEmpty++;
      continue;
    }

    if (looksEnglish(desc)) {
      progress.done[id] = desc; // already English
      skippedEnglish++;
      continue;
    }

    work.push({ id, brand, desc });
  }

  console.log(`Skipped: ${skippedEmpty} empty, ${skippedEnglish} already English`);
  console.log(`${work.length} to translate\n`);

  let processed = 0;
  for (let bStart = 0; bStart < work.length; bStart += CONCURRENCY) {
    const batch = work.slice(bStart, bStart + CONCURRENCY);

    const results = await Promise.allSettled(
      batch.map(async (item) => {
        const translated = await translateRetry(item.desc);
        return { ...item, translated };
      }),
    );

    for (const r of results) {
      processed++;
      if (r.status === 'fulfilled') {
        const { id, brand, translated } = r.value;
        progress.done[id] = translated;
        console.log(`  [${prevDone + processed}/${dataRows.length}] ${brand.padEnd(35)} ✓ ${translated.length}ch`);
      } else {
        console.warn(`  [${prevDone + processed}/${dataRows.length}] FAILED: ${r.reason}`);
      }
    }

    saveProgress(progress);
    if (bStart + CONCURRENCY < work.length) await delay(DELAY_BETWEEN_BATCHES_MS);
  }

  console.log(`\nApplying translations to CSV...\n`);

  let filled = 0;
  for (const row of dataRows) {
    const id = row[idIdx] || '';
    const translated = progress.done[id];
    while (row.length <= descEnIdx) row.push('');
    if (translated) {
      row[descEnIdx] = translated;
      filled++;
    } else {
      row[descEnIdx] = '';
    }
  }

  console.log(`desc_en populated: ${filled} / ${dataRows.length}`);

  const outputLines = [rowToCsv(headers)];
  for (const row of dataRows) {
    while (row.length < headers.length) row.push('');
    outputLines.push(rowToCsv(row));
  }
  fs.writeFileSync(CSV_PATH, outputLines.join('\n'), 'utf8');
  console.log(`Wrote ${CSV_PATH}`);
}

main().catch((err) => { console.error('Fatal:', err); process.exit(1); });
