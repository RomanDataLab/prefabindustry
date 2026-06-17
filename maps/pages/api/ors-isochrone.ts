// API route to fetch isochrones from OpenRouteService
// Proxies the request so the ORS API key stays server-side
import type { NextApiRequest, NextApiResponse } from 'next';
import path from 'path';
import fs from 'fs';
import https from 'https';

function getOrsApiKey(): string | null {
  // Try multiple possible config directory locations
  let configDir = path.join(process.cwd(), '..', '..', 'config');
  if (!fs.existsSync(configDir)) {
    configDir = 'C:/12_CODINGHARD/config';
    if (!fs.existsSync(configDir)) {
      configDir = path.join(process.cwd(), '..', 'config');
    }
  }

  // 1) config_isochrone.json
  try {
    const cfg = JSON.parse(fs.readFileSync(path.join(configDir, 'config_isochrone.json'), 'utf8'));
    if (cfg.ors_api_key) return cfg.ors_api_key;
  } catch (_) { /* ignore */ }

  // 2) openrouteservice.env
  try {
    const env = fs.readFileSync(path.join(configDir, 'openrouteservice.env'), 'utf8');
    const m = env.match(/ORS_API_KEY\s*=\s*(.+)/);
    if (m) return m[1].trim();
  } catch (_) { /* ignore */ }

  return null;
}

function postJSON(url: string, body: object, headers: Record<string, string>): Promise<any> {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const options = {
      hostname: parsed.hostname,
      port: 443,
      path: parsed.pathname + parsed.search,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        Accept: 'application/json, application/geo+json',
        ...headers,
      },
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', (chunk: Buffer) => (data += chunk));
      res.on('end', () => {
        if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
          try {
            resolve(JSON.parse(data));
          } catch {
            reject(new Error(`JSON parse error: ${data.substring(0, 300)}`));
          }
        } else {
          reject(new Error(`HTTP ${res.statusCode}: ${data.substring(0, 300)}`));
        }
      });
    });
    req.on('error', reject);
    req.setTimeout(30000, () => {
      req.destroy();
      reject(new Error('Request timeout'));
    });
    req.write(JSON.stringify(body));
    req.end();
  });
}

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const apiKey = getOrsApiKey();
  if (!apiKey) {
    return res.status(500).json({ error: 'ORS API key not configured' });
  }

  const { lat, lon } = req.body;
  if (typeof lat !== 'number' || typeof lon !== 'number') {
    return res.status(400).json({ error: 'lat and lon required as numbers' });
  }

  // Time-based isochrones: 30, 60 min
  const rangesS = [1800, 3600];

  const body = {
    locations: [[lon, lat]],
    range: rangesS,
    range_type: 'time',
    attributes: ['area', 'reachfactor'],
  };

  try {
    const result = await postJSON(
      'https://api.openrouteservice.org/v2/isochrones/driving-car',
      body,
      { Authorization: apiKey }
    );
    return res.status(200).json(result);
  } catch (e: any) {
    return res.status(502).json({
      error: 'ORS API request failed',
      message: e.message,
    });
  }
}
