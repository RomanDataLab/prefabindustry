/**
 * Batch Isochrone Generator — pre-compute 30/60/120 min driving isochrones
 * for EVERY company in the CSV. Saves to a single GeoJSON file.
 *
 * Resumable: if the output file already exists, only missing company IDs
 * are fetched. Safe to re-run after hitting the 500 req/day ORS limit.
 *
 * Usage:
 *   node generate_isochrones.js
 *
 * Output:
 *   public/isochrones_all.geojson
 */

const https = require('https');
const fs = require('fs');
const path = require('path');

// --- Config ---
const CSV_PATH = path.join(__dirname, 'prefabworldfin_reducedby_7.csv');
const OUT_PATH = path.join(__dirname, 'isochrones_all.geojson');
// ORS free tier: time-based driving-car, max 3600s
// 1800s = 30 min, 3600s = 60 min
const RANGES_S = [1800, 3600];
const RANGE_LABELS = ['30 min', '60 min'];
const DELAY_MS = 3200; // ~18 req/min — well within 20/min limit

// Load API key from config
let API_KEY = '';
const configPaths = [
  path.join(__dirname, '..', '..', '..', 'config', 'config_isochrone.json'),
  'C:/12_CODINGHARD/config/config_isochrone.json',
];
for (const p of configPaths) {
  try {
    const cfg = JSON.parse(fs.readFileSync(p, 'utf8'));
    if (cfg.ors_api_key) { API_KEY = cfg.ors_api_key; break; }
  } catch (_) {}
}
if (!API_KEY) {
  // fallback: openrouteservice.env
  const envPaths = [
    path.join(__dirname, '..', '..', '..', 'config', 'openrouteservice.env'),
    'C:/12_CODINGHARD/config/openrouteservice.env',
  ];
  for (const p of envPaths) {
    try {
      const txt = fs.readFileSync(p, 'utf8');
      const m = txt.match(/ORS_API_KEY\s*=\s*(.+)/);
      if (m) { API_KEY = m[1].trim(); break; }
    } catch (_) {}
  }
}
if (!API_KEY) { console.error('No ORS API key found.'); process.exit(1); }

// --- CSV parser ---
function parseRow(line) {
  const row = []; let inQ = false, f = '';
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (c === '"') {
      if (inQ && i + 1 < line.length && line[i + 1] === '"') { f += '"'; i++; }
      else inQ = !inQ;
    } else if (c === ',' && !inQ) { row.push(f); f = ''; }
    else if (c !== '\r') f += c;
  }
  row.push(f);
  return row;
}

// --- HTTP POST ---
function postJSON(url, body, headers) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const options = {
      hostname: parsed.hostname, port: 443,
      path: parsed.pathname + parsed.search, method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8',
                 Accept: 'application/json, application/geo+json', ...headers },
    };
    const req = https.request(options, res => {
      let data = '';
      res.on('data', ch => (data += ch));
      res.on('end', () => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          try { resolve(JSON.parse(data)); }
          catch { reject(new Error('JSON parse error')); }
        } else {
          reject(new Error(`HTTP ${res.statusCode}: ${data.substring(0, 300)}`));
        }
      });
    });
    req.on('error', reject);
    req.setTimeout(30000, () => { req.destroy(); reject(new Error('timeout')); });
    req.write(JSON.stringify(body));
    req.end();
  });
}

// --- Fetch isochrone for one point (time-based, 30/60/120 min) ---
async function fetchOne(lat, lon) {
  const body = {
    locations: [[lon, lat]],
    range: RANGES_S,
    range_type: 'time',
    attributes: ['area', 'reachfactor'],
  };
  return await postJSON(
    'https://api.openrouteservice.org/v2/isochrones/driving-car',
    body, { Authorization: API_KEY }
  );
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

// --- Main ---
async function main() {
  // 1) Read CSV
  const csvText = fs.readFileSync(CSV_PATH, 'utf8');
  const lines = csvText.split('\n').filter(l => l.trim());
  const header = parseRow(lines[0]);
  const idIdx = header.indexOf('id');
  const latIdx = header.indexOf('latitude');
  const lonIdx = header.indexOf('longitude');
  const brandIdx = header.indexOf('brand');

  const companies = [];
  for (let i = 1; i < lines.length; i++) {
    const cols = parseRow(lines[i]);
    const id = cols[idIdx];
    const lat = parseFloat(cols[latIdx]);
    const lon = parseFloat(cols[lonIdx]);
    const brand = cols[brandIdx] || '';
    if (!id || !Number.isFinite(lat) || !Number.isFinite(lon)) continue;
    companies.push({ id, lat, lon, brand });
  }
  console.log(`CSV: ${companies.length} companies with valid coordinates`);

  // 2) Load existing output (for resume)
  let existing = { type: 'FeatureCollection', features: [] };
  const doneIds = new Set();
  if (fs.existsSync(OUT_PATH)) {
    try {
      existing = JSON.parse(fs.readFileSync(OUT_PATH, 'utf8'));
      for (const f of existing.features) {
        if (f.properties?.company_id) doneIds.add(f.properties.company_id);
      }
      console.log(`Existing file: ${doneIds.size} companies already done`);
    } catch { console.log('Existing file corrupt — starting fresh'); }
  }

  const todo = companies.filter(c => !doneIds.has(c.id));
  console.log(`To fetch: ${todo.length} companies`);
  if (todo.length === 0) { console.log('All done!'); return; }

  // 3) Fetch loop
  let fetched = 0;
  let errors = 0;
  const allFeatures = [...existing.features]; // keep existing

  for (const c of todo) {
    process.stdout.write(`[${fetched + 1}/${todo.length}] id=${c.id} ${c.brand} (${c.lat}, ${c.lon}) ... `);
    try {
      const ors = await fetchOne(c.lat, c.lon);
      if (!ors.features?.length) {
        console.log('⚠ no features');
        errors++;
      } else {
        // Sort ascending by range value
        const sorted = ors.features.slice().sort(
          (a, b) => (a.properties?.value || 0) - (b.properties?.value || 0)
        );
        for (let fi = 0; fi < sorted.length; fi++) {
          const f = sorted[fi];
          allFeatures.push({
            type: 'Feature',
            properties: {
              company_id: c.id,
              brand: c.brand,
              range_s: f.properties?.value || 0,
              label: RANGE_LABELS[fi] || `${Math.round((f.properties?.value || 0) / 60)} min`,
              area_km2: f.properties?.area ? +(f.properties.area / 1e6).toFixed(0) : null,
            },
            geometry: f.geometry,
          });
        }
        console.log(`✅ ${sorted.length} zones`);
      }
    } catch (e) {
      console.log(`❌ ${e.message}`);
      errors++;
      // If daily limit hit, save progress and exit
      if (e.message.includes('403') || e.message.includes('429')) {
        console.log('\n⛔ Rate/quota limit hit — saving progress and stopping.');
        break;
      }
    }
    fetched++;

    // Save every 10 companies for safety
    if (fetched % 10 === 0 || fetched === todo.length) {
      const out = { type: 'FeatureCollection', features: allFeatures };
      fs.writeFileSync(OUT_PATH, JSON.stringify(out));
      const uniqueIds = new Set(allFeatures.map(f => f.properties?.company_id).filter(Boolean));
      process.stdout.write(`  💾 saved (${uniqueIds.size} total companies)\n`);
    }

    await sleep(DELAY_MS);
  }

  // Final save
  const out = { type: 'FeatureCollection', features: allFeatures };
  fs.writeFileSync(OUT_PATH, JSON.stringify(out));
  const uniqueIds = new Set(allFeatures.map(f => f.properties?.company_id).filter(Boolean));
  console.log(`\n═══ Done ═══`);
  console.log(`Companies fetched this run: ${fetched}`);
  console.log(`Errors: ${errors}`);
  console.log(`Total companies in file: ${uniqueIds.size}/${companies.length}`);
  console.log(`Output: ${OUT_PATH}`);
  console.log(`File size: ${(fs.statSync(OUT_PATH).size / 1024 / 1024).toFixed(1)} MB`);
  if (uniqueIds.size < companies.length) {
    console.log(`\n⚡ Re-run this script tomorrow to fetch the remaining ${companies.length - uniqueIds.size} companies`);
  }
}

main().catch(e => { console.error(e); process.exit(1); });
