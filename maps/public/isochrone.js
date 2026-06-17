/**
 * Isochrone Generator - Creates 50, 100, 200 km driving isochrones from a point
 * Uses OpenRouteService free-tier API (https://openrouteservice.org)
 *
 * Sign up for a free API key at: https://openrouteservice.org/dev/#/signup
 * Free tier: 500 requests/day, 20 req/min
 *
 * Usage:
 *   node isochrone.js <lat> <lon> <ORS_API_KEY>
 *   node isochrone.js 52.52 13.405 your_api_key_here
 *
 * Output:
 *   isochrone_<lat>_<lon>.geojson   - GeoJSON with 3 isochrone polygons
 *   isochrone_<lat>_<lon>.html      - Interactive Leaflet map preview
 */

const https = require('https');
const fs = require('fs');
const path = require('path');

// --- Parse args ---
const lat = parseFloat(process.argv[2]);
const lon = parseFloat(process.argv[3]);
const API_KEY = process.argv[4] || process.env.ORS_API_KEY || '';

if (!lat || !lon || !API_KEY) {
  console.log(`
╔══════════════════════════════════════════════════════════════════╗
║  Isochrone Generator — 50 / 100 / 200 km driving isochrones    ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  Usage:                                                          ║
║    node isochrone.js <lat> <lon> <ORS_API_KEY>                   ║
║                                                                  ║
║  Example:                                                        ║
║    node isochrone.js 52.52 13.405 5b3ce3597851110001cf624812...   ║
║                                                                  ║
║  Get a FREE API key at:                                          ║
║    https://openrouteservice.org/dev/#/signup                     ║
║                                                                  ║
║  Free tier: 500 requests/day                                     ║
╚══════════════════════════════════════════════════════════════════╝
`);
  process.exit(1);
}

// --- Config ---
const DISTANCES_KM = [50, 100, 200];
const DISTANCES_M = DISTANCES_KM.map(d => d * 1000);
const COLORS = ['#2ecc71', '#f39c12', '#e74c3c']; // green, orange, red
const LABELS = ['50 km', '100 km', '200 km'];

// --- HTTP POST helper ---
function postJSON(url, body, headers) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const options = {
      hostname: parsed.hostname,
      port: 443,
      path: parsed.pathname + parsed.search,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Accept': 'application/json, application/geo+json',
        ...headers
      }
    };

    const req = https.request(options, res => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          try { resolve(JSON.parse(data)); }
          catch(e) { reject(new Error(`JSON parse error: ${data.substring(0, 500)}`)); }
        } else {
          reject(new Error(`HTTP ${res.statusCode}: ${data.substring(0, 500)}`));
        }
      });
    });
    req.on('error', reject);
    req.setTimeout(30000, () => { req.destroy(); reject(new Error('Request timeout')); });
    req.write(JSON.stringify(body));
    req.end();
  });
}

// --- Fetch isochrones from ORS ---
async function fetchIsochrones(lat, lon, distancesM) {
  console.log(`\nFetching isochrones from OpenRouteService...`);
  console.log(`  Point: ${lat}, ${lon}`);
  console.log(`  Distances: ${DISTANCES_KM.join(', ')} km`);
  console.log(`  Profile: driving-car\n`);

  // ORS wants [lon, lat] order
  const body = {
    locations: [[lon, lat]],
    range: distancesM,
    range_type: 'distance',
    units: 'm',
    attributes: ['area', 'reachfactor']
  };

  try {
    const result = await postJSON(
      'https://api.openrouteservice.org/v2/isochrones/driving-car',
      body,
      { 'Authorization': API_KEY }
    );
    return result;
  } catch(e) {
    // If distance-based fails (e.g., range too large), try time-based approximation
    console.log(`  ⚠ Distance-based request failed: ${e.message}`);
    console.log(`  Falling back to time-based isochrones...\n`);

    // Approximate: 50km ~35min, 100km ~70min, 200km ~140min (avg ~85 km/h highway)
    const timesSeconds = distancesM.map(d => Math.round((d / 1000 / 85) * 3600));
    console.log(`  Time approximations: ${timesSeconds.map(t => Math.round(t/60) + ' min').join(', ')}`);

    const bodyTime = {
      locations: [[lon, lat]],
      range: timesSeconds,
      range_type: 'time',
      attributes: ['area', 'reachfactor']
    };

    try {
      const result = await postJSON(
        'https://api.openrouteservice.org/v2/isochrones/driving-car',
        bodyTime,
        { 'Authorization': API_KEY }
      );
      // Tag features with distance labels
      result._fallback = true;
      return result;
    } catch(e2) {
      // If time-based also fails with large ranges, try splitting into individual requests
      console.log(`  ⚠ Combined time request failed: ${e2.message}`);
      console.log(`  Trying individual requests...\n`);

      const features = [];
      for (let i = 0; i < timesSeconds.length; i++) {
        const singleBody = {
          locations: [[lon, lat]],
          range: [timesSeconds[i]],
          range_type: 'time',
          attributes: ['area', 'reachfactor']
        };
        try {
          const res = await postJSON(
            'https://api.openrouteservice.org/v2/isochrones/driving-car',
            singleBody,
            { 'Authorization': API_KEY }
          );
          if (res.features && res.features.length > 0) {
            features.push(res.features[0]);
            console.log(`  ✅ ${LABELS[i]} isochrone OK`);
          }
        } catch(e3) {
          console.log(`  ❌ ${LABELS[i]} failed: ${e3.message}`);
        }
        // Rate limit: 20 req/min
        await new Promise(r => setTimeout(r, 3100));
      }

      return { type: 'FeatureCollection', features, _fallback: true };
    }
  }
}

// --- Build styled GeoJSON ---
function buildGeoJSON(orsResult, lat, lon) {
  const features = [];

  // ORS returns features from largest to smallest range
  // We need to sort by range value (ascending)
  const orsFeatures = (orsResult.features || []).slice().sort((a, b) => {
    const va = a.properties?.value || 0;
    const vb = b.properties?.value || 0;
    return va - vb;
  });

  for (let i = 0; i < orsFeatures.length; i++) {
    const f = orsFeatures[i];
    const distLabel = LABELS[i] || `Zone ${i+1}`;
    const color = COLORS[i] || '#999';
    const rangeVal = f.properties?.value || 0;
    const area = f.properties?.area ? (f.properties.area / 1e6).toFixed(0) : '?';

    features.push({
      type: 'Feature',
      properties: {
        label: distLabel,
        color: color,
        fillColor: color,
        fillOpacity: 0.15,
        weight: 2,
        range_m: rangeVal,
        area_km2: parseFloat(area),
        ...(orsResult._fallback ? { note: 'Time-based approximation' } : {})
      },
      geometry: f.geometry
    });
  }

  // Add center point
  features.push({
    type: 'Feature',
    properties: { label: 'Center', marker: true },
    geometry: { type: 'Point', coordinates: [lon, lat] }
  });

  return { type: 'FeatureCollection', features };
}

// --- Generate HTML map preview ---
function generateHTML(geojson, lat, lon) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Isochrone Map — ${lat}, ${lon}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<style>
  body { margin: 0; font-family: system-ui, sans-serif; }
  #map { width: 100vw; height: 100vh; }
  .legend { background: white; padding: 12px 16px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.2); line-height: 1.8; }
  .legend h4 { margin: 0 0 8px; font-size: 14px; }
  .legend-item { display: flex; align-items: center; gap: 8px; font-size: 13px; }
  .legend-color { width: 20px; height: 14px; border-radius: 3px; border: 1px solid rgba(0,0,0,0.2); }
  .info { background: white; padding: 10px 14px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.2); font-size: 13px; }
</style>
</head>
<body>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const geojson = ${JSON.stringify(geojson)};
const map = L.map('map').setView([${lat}, ${lon}], 7);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap contributors | Isochrones: OpenRouteService'
}).addTo(map);

// Add isochrone polygons (largest first for proper layering)
const polygonFeatures = geojson.features
  .filter(f => f.geometry.type !== 'Point')
  .sort((a, b) => (b.properties.range_m || 0) - (a.properties.range_m || 0));

const bounds = [];
polygonFeatures.forEach(f => {
  const layer = L.geoJSON(f, {
    style: {
      color: f.properties.color,
      fillColor: f.properties.fillColor,
      fillOpacity: f.properties.fillOpacity,
      weight: f.properties.weight
    }
  }).addTo(map);
  layer.bindPopup('<b>' + f.properties.label + '</b><br>Area: ' + (f.properties.area_km2 || '?') + ' km²');
  bounds.push(...layer.getBounds().toBBoxString().split(',').map(Number));
});

// Center marker
const center = geojson.features.find(f => f.properties.marker);
if (center) {
  L.marker([center.geometry.coordinates[1], center.geometry.coordinates[0]])
    .addTo(map)
    .bindPopup('<b>Center</b><br>' + ${lat} + ', ' + ${lon});
}

// Fit bounds
if (polygonFeatures.length > 0) {
  const allLayers = L.geoJSON({ type: 'FeatureCollection', features: polygonFeatures });
  map.fitBounds(allLayers.getBounds().pad(0.1));
}

// Legend
const legend = L.control({ position: 'bottomright' });
legend.onAdd = function() {
  const div = L.DomUtil.create('div', 'legend');
  div.innerHTML = '<h4>Driving Isochrones</h4>';
  ${JSON.stringify(COLORS)}.forEach((c, i) => {
    div.innerHTML += '<div class="legend-item"><div class="legend-color" style="background:' + c + '"></div>' + ${JSON.stringify(LABELS)}[i] + '</div>';
  });
  return div;
};
legend.addTo(map);

// Info
const info = L.control({ position: 'topleft' });
info.onAdd = function() {
  const div = L.DomUtil.create('div', 'info');
  div.innerHTML = '<b>Point:</b> ${lat}, ${lon}';
  return div;
};
info.addTo(map);
</script>
</body>
</html>`;
}

// --- Main ---
async function main() {
  console.log('═══════════════════════════════════════');
  console.log('  Isochrone Generator (ORS Free Tier)');
  console.log('═══════════════════════════════════════');

  const orsResult = await fetchIsochrones(lat, lon, DISTANCES_M);

  if (!orsResult.features || orsResult.features.length === 0) {
    console.error('\n❌ No isochrone data received. Check your API key and coordinates.');
    process.exit(1);
  }

  console.log(`\n✅ Received ${orsResult.features.length} isochrone(s)`);

  // Build styled GeoJSON
  const geojson = buildGeoJSON(orsResult, lat, lon);

  // File names
  const slug = `${lat}_${lon}`.replace(/[^0-9.\-]/g, '');
  const dir = path.dirname(process.argv[1]) || '.';
  const geojsonPath = path.join(dir, `isochrone_${slug}.geojson`);
  const htmlPath = path.join(dir, `isochrone_${slug}.html`);

  // Write GeoJSON
  fs.writeFileSync(geojsonPath, JSON.stringify(geojson, null, 2));
  console.log(`\n📄 GeoJSON: ${geojsonPath}`);

  // Write HTML preview
  const html = generateHTML(geojson, lat, lon);
  fs.writeFileSync(htmlPath, html);
  console.log(`🗺️  Map:     ${htmlPath}`);

  // Summary
  console.log('\n── Summary ──');
  for (const f of geojson.features) {
    if (f.properties.marker) continue;
    console.log(`  ${f.properties.label}: ${f.properties.area_km2 || '?'} km² reachable area`);
  }
  console.log('');
}

main().catch(e => {
  console.error(`\n❌ Error: ${e.message}`);
  process.exit(1);
});
