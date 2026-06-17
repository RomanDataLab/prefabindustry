# Prefab Maps - Vercel Project

A Next.js project displaying a Mapbox map centered on Astana, Kazakhstan with zoom level 15.

## Features

- Black/dark Mapbox map style
- Centered on Astana (51.1694° N, 71.4491° E)
- Default zoom level: 15
- Uses Mapbox configuration from `configix/apiManager.py`

## Setup

1. Install dependencies:
```bash
npm install
```

2. Run development server:
```bash
npm run dev
```

3. Open [http://localhost:3000](http://localhost:3000) in your browser

## Deployment to Vercel

1. Install Vercel CLI (if not already installed):
```bash
npm i -g vercel
```

2. Deploy:
```bash
vercel
```

Or connect your GitHub repository to Vercel for automatic deployments.

## Configuration

The app reads Mapbox configuration from the `config` directory's `mapboxConfig.js` file, following the same logic as `configix/apiManager.py`:

- Looks for config in: `../config` (relative to maps folder)
- Falls back to: `C:/12_CODINGHARD/config`
- Falls back to: `../../config`

The API route `/api/mapbox-config` extracts:
- `MAPBOX_ACCESS_TOKEN` - Your Mapbox access token
- `MAPBOX_STYLE` - Mapbox style URL (defaults to dark-v11 if not found)
