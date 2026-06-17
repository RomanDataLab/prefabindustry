// API route to get Mapbox config from apiManager
import type { NextApiRequest, NextApiResponse } from 'next';
import path from 'path';
import fs from 'fs';

export default function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    // 1. Prefer environment variable (Vercel / production)
    if (process.env.MAPBOX_ACCESS_TOKEN) {
      return res.status(200).json({
        MAPBOX_ACCESS_TOKEN: process.env.MAPBOX_ACCESS_TOKEN,
        MAPBOX_STYLE: process.env.MAPBOX_STYLE || 'mapbox://styles/mapbox/dark-v11',
      });
    }

    // 2. Fall back to local config file (dev)
    let configDir = path.join(process.cwd(), '..', '..', 'config');
    if (!fs.existsSync(configDir)) {
      configDir = 'C:/12_CODINGHARD/config';
      if (!fs.existsSync(configDir)) {
        configDir = path.join(process.cwd(), '..', 'config');
        if (!fs.existsSync(configDir)) {
          return res.status(500).json({
            error: 'Config directory not found. Set MAPBOX_ACCESS_TOKEN env var for production.',
          });
        }
      }
    }

    const mapboxConfigPath = path.join(configDir, 'mapboxConfig.js');

    if (!fs.existsSync(mapboxConfigPath)) {
      return res.status(500).json({
        error: 'mapboxConfig.js not found. Set MAPBOX_ACCESS_TOKEN env var for production.',
      });
    }

    const content = fs.readFileSync(mapboxConfigPath, 'utf8');
    const tokenMatch = content.match(/MAPBOX_ACCESS_TOKEN\s*=\s*['"]([^'"]+)['"]/);
    const styleMatch = content.match(/MAPBOX_STYLE\s*=\s*['"]([^'"]+)['"]/);

    const mapboxConfig = {
      MAPBOX_ACCESS_TOKEN: tokenMatch ? tokenMatch[1] : null,
      MAPBOX_STYLE: styleMatch ? styleMatch[1] : 'mapbox://styles/mapbox/dark-v11'
    };

    if (!mapboxConfig.MAPBOX_ACCESS_TOKEN) {
      return res.status(500).json({
        error: 'MAPBOX_ACCESS_TOKEN not found in config'
      });
    }

    return res.status(200).json(mapboxConfig);
  } catch (error: any) {
    console.error('Error fetching Mapbox config:', error);
    return res.status(500).json({ 
      error: 'Failed to load Mapbox config',
      message: error.message 
    });
  }
}
