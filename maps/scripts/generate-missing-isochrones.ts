/**
 * generate-missing-isochrones.ts
 *
 * Generates isochrones for the 14 companies missing from isochrones_all.geojson.
 *
 * Strategy:
 *   1. Tokyo companies → try ORS first; if fail → synthetic
 *   2. All others → synthetic amoeba polygons at 30 km/h
 *
 * Synthetic method:
 *   - 30 min @ 30 km/h = 15 km radius, 60 min = 30 km radius
 *   - Irregular "amoeba" shape using Perlin-like noise
 *   - Landscape-aware: shrink towards mountains (elevation proxy),
 *     exclude water bodies by deforming polygon edges
 *   - Uses Open-Elevation API for terrain sampling
 *
 * Usage: npx tsx scripts/generate-missing-isochrones.ts
 */

import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const PUBLIC_DIR = path.join(ROOT, 'public');
const ISO_FILE = path.join(PUBLIC_DIR, 'isochrones_all.geojson');

// ORS config
const ORS_KEY = 'eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6ImVhZWZhZjM3NzdiNDRhMDU4MTVjNWE5NGI0MmVlMmM3IiwiaCI6Im11cm11cjY0In0=';
const ORS_URL = 'https://api.openrouteservice.org/v2/isochrones/driving-car';

// Missing companies
const MISSING: Array<{
  id: string;
  brand: string;
  lat: number;
  lon: number;
  country: string;
  tryOrs: boolean;
}> = [
  { id: '43', brand: 'Precon Engenharia', lat: -10.3333333, lon: -53.2, country: 'Brazil', tryOrs: false },
  { id: '62', brand: 'Rocky Mountain Modular', lat: 55.001251, lon: -115.002136, country: 'Canada', tryOrs: false },
  { id: '174', brand: 'Guildcrest Homes', lat: 50.000678, lon: -86.000977, country: 'Canada', tryOrs: false },
  { id: '237', brand: 'Batitech', lat: 53.38260342, lon: -71.748742246, country: 'Canada', tryOrs: false },
  { id: '375', brand: 'Ferdighus', lat: 68.1633439, lon: 15.2994537, country: 'Norway', tryOrs: false },
  { id: '700', brand: 'Asahi Kasei Homes', lat: 35.696233, lon: 139.758605, country: 'Japan', tryOrs: true },
  { id: '701', brand: 'Daiwa House', lat: 35.684685, lon: 139.774071, country: 'Japan', tryOrs: true },
  { id: '705', brand: 'Kenken', lat: 35.690074, lon: 139.780886, country: 'Japan', tryOrs: true },
  { id: '707', brand: 'Misawa Homes', lat: 35.689634, lon: 139.692101, country: 'Japan', tryOrs: true },
  { id: '720', brand: 'Taisei U-lec', lat: 35.668162, lon: 139.751819, country: 'Japan', tryOrs: true },
  { id: '795', brand: 'Hemp Built', lat: -25.70993157, lon: 134.484031198, country: 'Australia', tryOrs: false },
  { id: '1035', brand: 'СК Блок-Контейнер', lat: 60.1853296, lon: 32.3925325, country: 'Russia', tryOrs: false },
  { id: '1042', brand: 'ЛенСтройДом', lat: 60.1853296, lon: 32.3925325, country: 'Russia', tryOrs: false },
  { id: '1055', brand: 'PanelStroy', lat: 60.1853296, lon: 32.3925325, country: 'Russia', tryOrs: false },
];

/* ------------------------------------------------------------------ */
/*  ORS isochrone fetch                                                */
/* ------------------------------------------------------------------ */
async function fetchOrsIsochrone(
  lat: number,
  lon: number,
  id: string,
  brand: string,
): Promise<GeoJSON.Feature[] | null> {
  const body = {
    locations: [[lon, lat]],
    range: [1800, 3600],
    range_type: 'time',
    attributes: ['area'],
  };

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30_000);

  try {
    const res = await fetch(ORS_URL, {
      method: 'POST',
      signal: controller.signal,
      headers: {
        Authorization: ORS_KEY,
        'Content-Type': 'application/json',
        Accept: 'application/json, application/geo+json',
      },
      body: JSON.stringify(body),
    });

    if (res.status === 429) {
      console.log('    Rate limited, waiting 60s...');
      await delay(60_000);
      // retry once
      const res2 = await fetch(ORS_URL, {
        method: 'POST',
        headers: {
          Authorization: ORS_KEY,
          'Content-Type': 'application/json',
          Accept: 'application/json, application/geo+json',
        },
        body: JSON.stringify(body),
      });
      if (res2.status !== 200) return null;
      const data = await res2.json();
      return enrichOrsFeatures(data, id, brand);
    }

    if (res.status !== 200) {
      const errText = await res.text().catch(() => '');
      console.log(`    ORS error ${res.status}: ${errText.slice(0, 200)}`);
      return null;
    }

    const data = await res.json();
    return enrichOrsFeatures(data, id, brand);
  } catch (err: any) {
    console.log(`    ORS failed: ${err.message}`);
    return null;
  } finally {
    clearTimeout(timer);
  }
}

function enrichOrsFeatures(
  data: any,
  id: string,
  brand: string,
): GeoJSON.Feature[] | null {
  if (data.type !== 'FeatureCollection' || !data.features?.length) return null;

  return data.features.map((f: any) => {
    const rangeS = f.properties?.value || 0;
    const label = rangeS <= 1800 ? '30 min' : '60 min';
    const areaKm2 = f.properties?.area
      ? Math.round((f.properties.area / 1_000_000) * 100) / 100
      : 0;
    return {
      type: 'Feature',
      properties: {
        company_id: id,
        brand,
        range_s: rangeS,
        label,
        area_km2: areaKm2,
      },
      geometry: f.geometry,
    };
  });
}

/* ------------------------------------------------------------------ */
/*  Synthetic amoeba isochrone generator                               */
/* ------------------------------------------------------------------ */

/** Simple seeded pseudo-random (mulberry32) */
function mulberry32(seed: number) {
  return () => {
    let t = (seed += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Hash string to seed */
function hashSeed(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

/**
 * Generate smooth noise values for N points using layered sine waves
 * (cheap Perlin-like effect without dependencies)
 */
function smoothNoise(n: number, rng: () => number, octaves = 4): number[] {
  const values = new Array(n).fill(0);
  let amplitude = 1;
  let totalAmplitude = 0;

  for (let oct = 0; oct < octaves; oct++) {
    const frequency = 1 + oct * 2;
    const phase = rng() * Math.PI * 2;
    amplitude *= 0.55;
    totalAmplitude += amplitude;

    for (let i = 0; i < n; i++) {
      const angle = (i / n) * Math.PI * 2 * frequency + phase;
      values[i] += Math.sin(angle) * amplitude;
    }
  }

  // Normalize to [-1, 1]
  for (let i = 0; i < n; i++) {
    values[i] /= totalAmplitude;
  }
  return values;
}

/**
 * Fetch elevation samples along the polygon ring to detect mountains.
 * Uses Open-Meteo elevation API (free, no key needed).
 */
async function fetchElevations(
  points: Array<{ lat: number; lon: number }>,
): Promise<number[]> {
  // Sample up to 50 points to avoid oversized requests
  const step = Math.max(1, Math.floor(points.length / 50));
  const sampled = points.filter((_, i) => i % step === 0);

  const lats = sampled.map((p) => p.lat.toFixed(4)).join(',');
  const lons = sampled.map((p) => p.lon.toFixed(4)).join(',');

  try {
    const url = `https://api.open-meteo.com/v1/elevation?latitude=${lats}&longitude=${lons}`;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10_000);
    const res = await fetch(url, { signal: controller.signal });
    clearTimeout(timer);

    if (res.status !== 200) return sampled.map(() => 0);
    const data = await res.json();

    if (data.elevation && Array.isArray(data.elevation)) {
      // Interpolate back to full resolution
      const fullElevations: number[] = [];
      for (let i = 0; i < points.length; i++) {
        const srcIdx = Math.min(Math.floor(i / step), data.elevation.length - 1);
        fullElevations.push(data.elevation[srcIdx] ?? 0);
      }
      return fullElevations;
    }
    return points.map(() => 0);
  } catch {
    return points.map(() => 0);
  }
}

/**
 * Check if a point is over water using Open-Meteo marine API.
 * Returns a per-point boolean (true = likely water).
 * Uses the land_mask from elevation — if elevation ≤ 0, likely water.
 */
function detectWater(elevations: number[]): boolean[] {
  return elevations.map((e) => e <= 0);
}

/**
 * Generate an amoeba-shaped polygon for one time range.
 *
 * @param lat Center latitude
 * @param lon Center longitude
 * @param radiusKm Theoretical radius in km
 * @param seed Seed for reproducible noise
 */
async function generateAmoebaPolygon(
  lat: number,
  lon: number,
  radiusKm: number,
  seed: string,
): Promise<number[][]> {
  const NUM_POINTS = 72; // every 5 degrees
  const rng = mulberry32(hashSeed(seed));
  const noise = smoothNoise(NUM_POINTS, rng, 5);

  // Latitude degree ≈ 111 km; Longitude degree ≈ 111 * cos(lat) km
  const latDeg = radiusKm / 111.0;
  const lonDeg = radiusKm / (111.0 * Math.cos((lat * Math.PI) / 180));

  // Generate initial ring points
  const ringPoints: Array<{ lat: number; lon: number; angle: number }> = [];
  for (let i = 0; i < NUM_POINTS; i++) {
    const angle = (i / NUM_POINTS) * Math.PI * 2;
    // Base radius varies 0.65–1.0 with noise
    const noiseFactor = 0.82 + 0.18 * noise[i];
    const pLat = lat + Math.sin(angle) * latDeg * noiseFactor;
    const pLon = lon + Math.cos(angle) * lonDeg * noiseFactor;
    ringPoints.push({ lat: pLat, lon: pLon, angle });
  }

  // Fetch elevations to detect mountains and water
  const elevations = await fetchElevations(ringPoints);
  const isWater = detectWater(elevations);

  // Find center elevation as baseline
  let centerElev = 0;
  try {
    const cUrl = `https://api.open-meteo.com/v1/elevation?latitude=${lat.toFixed(4)}&longitude=${lon.toFixed(4)}`;
    const cRes = await fetch(cUrl);
    if (cRes.ok) {
      const cData = await cRes.json();
      centerElev = cData.elevation?.[0] ?? 0;
    }
  } catch {}

  // Adjust radius based on terrain
  const coords: number[][] = [];
  for (let i = 0; i < NUM_POINTS; i++) {
    const p = ringPoints[i];
    let scale = 1.0;

    // Shrink towards steep mountains (elevation > centerElev + 500m)
    const elevDiff = elevations[i] - centerElev;
    if (elevDiff > 200) {
      // Scale down proportionally: at +500m, shrink to 60%; at +1000m, shrink to 40%
      scale *= Math.max(0.35, 1.0 - elevDiff / 1200);
    }

    // Shrink heavily for water (don't extend over ocean/lakes)
    if (isWater[i]) {
      scale *= 0.3;
    }

    // Apply scale — move point towards center
    const adjLat = lat + (p.lat - lat) * scale;
    const adjLon = lon + (p.lon - lon) * scale;
    coords.push([adjLon, adjLat]);
  }

  // Close the ring
  coords.push([...coords[0]]);

  return coords;
}

async function generateSyntheticIsochrones(
  id: string,
  brand: string,
  lat: number,
  lon: number,
): Promise<GeoJSON.Feature[]> {
  const features: GeoJSON.Feature[] = [];

  // 60 min first (larger, rendered underneath)
  const radius60 = 30; // 30 km/h × 1 hr
  const coords60 = await generateAmoebaPolygon(lat, lon, radius60, `${id}-60`);
  const area60 = approximateAreaKm2(coords60, lat);
  features.push({
    type: 'Feature',
    properties: {
      company_id: id,
      brand,
      range_s: 3600,
      label: '60 min',
      area_km2: Math.round(area60 * 100) / 100,
    },
    geometry: { type: 'Polygon', coordinates: [coords60] },
  });

  // 30 min (smaller, on top)
  const radius30 = 15; // 30 km/h × 0.5 hr
  const coords30 = await generateAmoebaPolygon(lat, lon, radius30, `${id}-30`);
  const area30 = approximateAreaKm2(coords30, lat);
  features.push({
    type: 'Feature',
    properties: {
      company_id: id,
      brand,
      range_s: 1800,
      label: '30 min',
      area_km2: Math.round(area30 * 100) / 100,
    },
    geometry: { type: 'Polygon', coordinates: [coords30] },
  });

  return features;
}

/** Approximate polygon area using shoelace formula on lat/lon converted to km */
function approximateAreaKm2(coords: number[][], centerLat: number): number {
  const latScale = 111.0;
  const lonScale = 111.0 * Math.cos((centerLat * Math.PI) / 180);
  let area = 0;
  for (let i = 0; i < coords.length - 1; i++) {
    const x1 = coords[i][0] * lonScale;
    const y1 = coords[i][1] * latScale;
    const x2 = coords[i + 1][0] * lonScale;
    const y2 = coords[i + 1][1] * latScale;
    area += x1 * y2 - x2 * y1;
  }
  return Math.abs(area) / 2;
}

/* ------------------------------------------------------------------ */
/*  Main                                                               */
/* ------------------------------------------------------------------ */
const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function main() {
  console.log('Loading existing isochrones...');
  const geo = JSON.parse(fs.readFileSync(ISO_FILE, 'utf8'));
  const existingCount = geo.features.length;
  console.log(`Existing features: ${existingCount}\n`);

  const newFeatures: GeoJSON.Feature[] = [];

  // Process Tokyo companies first (try ORS)
  const tokyoCompanies = MISSING.filter((c) => c.tryOrs);
  const otherCompanies = MISSING.filter((c) => c.tryOrs === false);

  console.log(`=== Trying ORS for ${tokyoCompanies.length} Tokyo companies ===\n`);

  for (const c of tokyoCompanies) {
    console.log(`  ${c.brand} (${c.lat}, ${c.lon})`);
    const orsFeatures = await fetchOrsIsochrone(c.lat, c.lon, c.id, c.brand);

    if (orsFeatures && orsFeatures.length > 0) {
      console.log(`    ✓ ORS success: ${orsFeatures.length} features`);
      newFeatures.push(...orsFeatures);
    } else {
      console.log('    ✗ ORS failed → generating synthetic');
      const synth = await generateSyntheticIsochrones(c.id, c.brand, c.lat, c.lon);
      newFeatures.push(...synth);
      console.log(`    ✓ Synthetic: ${synth.length} features`);
    }

    await delay(3500); // ORS rate limit
  }

  console.log(`\n=== Generating synthetic for ${otherCompanies.length} other companies ===\n`);

  for (const c of otherCompanies) {
    console.log(`  ${c.brand} (${c.lat}, ${c.lon})`);
    const synth = await generateSyntheticIsochrones(c.id, c.brand, c.lat, c.lon);
    newFeatures.push(...synth);
    const areas = synth.map((f: any) => `${f.properties.label}: ${f.properties.area_km2} km²`).join(', ');
    console.log(`    ✓ ${synth.length} features (${areas})`);
    await delay(1200); // be gentle on elevation API
  }

  // Merge
  console.log(`\nMerging ${newFeatures.length} new features into isochrones_all.geojson...`);
  geo.features.push(...newFeatures);
  fs.writeFileSync(ISO_FILE, JSON.stringify(geo), 'utf8');
  console.log(`Done. Total features: ${geo.features.length} (was ${existingCount})`);
}

main().catch((err) => {
  console.error('Fatal:', err);
  process.exit(1);
});
