import { OpenRouteService, OpenRouteServiceError } from 'ors-client';
import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import csvParser from 'csv-parser';

type CsvRow = {
  id?: string;
  brand?: string;
  address?: string;
  latitude?: string;
  longitude?: string;
};

const ORS_API_KEY = process.env.ORS_API_KEY;
const ORS_BASE_URL = process.env.ORS_BASE_URL;
const ORS_DELAY_MS = Number(process.env.ORS_DELAY_MS || 1200);

if (!ORS_API_KEY) {
  throw new Error('ORS_API_KEY env var is required (OpenRouteService API key).');
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const formatError = (error: unknown) => {
  if (!error) return 'Unknown error';
  if (error instanceof OpenRouteServiceError) {
    const status = error.statusCode ?? 'unknown_status';
    const rateLimit = error.getRateLimitInfo?.();
    const rateInfo = rateLimit
      ? ` rate_limit={limit:${rateLimit.limit}, remaining:${rateLimit.remaining}, reset:${rateLimit.reset}}`
      : '';
    return `status=${status}${rateInfo} message=${error.message}`;
  }
  const err = error as { message?: string; response?: unknown; statusCode?: number };
  if (err?.response) {
    const status = (err as { statusCode?: number }).statusCode ?? 'unknown_status';
    return `status=${status} body=${JSON.stringify(err.response).slice(0, 500)}`;
  }
  if (err?.message) return err.message;
  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
};

const getIsoOutputPath = () => {
  const repoRoot = path.resolve(process.cwd(), '..');
  try {
    const output = execSync(
      'python -c "from configix import apiManager; print(apiManager.iso)"',
      { cwd: repoRoot }
    )
      .toString()
      .trim();
    if (output) return output;
  } catch (error) {
    console.warn(`⚠️  Failed to read iso path from apiManager.py: ${formatError(error)}`);
  }
  return path.join(process.cwd(), 'isochrones.geojson');
};

const readCsv = async (csvPath: string) => {
  const records: CsvRow[] = [];
  await new Promise<void>((resolve, reject) => {
    fs.createReadStream(csvPath)
      .pipe(csvParser())
      .on('data', (data: CsvRow) => records.push(data))
      .on('end', resolve)
      .on('error', reject);
  });
  return records;
};

const generateIsochrones = async () => {
  console.log('🚀 Starting isochrone generation...');

  const csvPath = path.join(process.cwd(), 'public', 'prefabworld.csv');
  console.log(`📖 Reading CSV from: ${csvPath}`);

  const records = await readCsv(csvPath);
  console.log(`📊 Found ${records.length} records in CSV`);

  const ors = new OpenRouteService({
    apiKey: ORS_API_KEY,
    ...(ORS_BASE_URL ? { baseUrl: ORS_BASE_URL } : {}),
  });
  console.log(`🌐 Using OpenRouteService${ORS_BASE_URL ? ` at: ${ORS_BASE_URL}` : ''}`);
  console.log(`⏱️  Delay between requests: ${ORS_DELAY_MS}ms`);

  const validRecords = records.filter((record) => {
    const lat = Number(record.latitude);
    const lon = Number(record.longitude);
    return Number.isFinite(lat) && Number.isFinite(lon) && lat !== 0 && lon !== 0;
  });

  console.log(`✅ Found ${validRecords.length} valid records with coordinates`);

  const featureCollection = {
    type: 'FeatureCollection',
    features: [] as Array<unknown>,
  };

  let successCount = 0;
  let errorCount = 0;

  for (let i = 0; i < validRecords.length; i += 1) {
    const record = validRecords[i];
    const lat = Number(record.latitude);
    const lon = Number(record.longitude);
    const id = record.id ?? '';
    const brand = record.brand ?? 'Unknown';

    console.log(`\n📍 Processing ${i + 1}/${validRecords.length}: ${brand} (ID: ${id})`);
    console.log(`   Location: ${lat}, ${lon}`);

    try {
      const isochrone = await ors.isochrones.calculateIsochrones('driving-hgv', {
        locations: [[lon, lat]],
        range: [180000],
        range_type: 'distance',
        units: 'km',
      });

      if (isochrone.features?.length) {
        isochrone.features.forEach((feature: { properties?: Record<string, unknown> }) => {
          feature.properties = {
            ...(feature.properties ?? {}),
            point_id: id,
            brand,
            address: record.address ?? '',
            source_lat: lat,
            source_lon: lon,
            distance_km: 180,
            profile: 'driving-hgv',
          };
        });

        featureCollection.features.push(...isochrone.features);
        successCount += 1;
        console.log(`   ✅ Success! Generated ${isochrone.features.length} feature(s)`);
      } else {
        console.log('   ⚠️  Warning: No features returned');
        errorCount += 1;
      }

      if (i < validRecords.length - 1) {
        await sleep(ORS_DELAY_MS);
      }
    } catch (error) {
      errorCount += 1;
      console.error(`   ❌ Error generating isochrone: ${formatError(error)}`);

      if (error instanceof OpenRouteServiceError && error.isRateLimited?.()) {
        const rateInfo = error.getRateLimitInfo?.();
        const waitMs = rateInfo?.reset
          ? Math.max(1000, rateInfo.reset * 1000 - Date.now())
          : 30000;
        console.log(`   ⏳ Rate limited. Waiting ${Math.round(waitMs / 1000)}s...`);
        await sleep(waitMs);
      } else if (i < validRecords.length - 1) {
        await sleep(ORS_DELAY_MS);
      }
    }
  }

  const outputPath = getIsoOutputPath();
  fs.writeFileSync(outputPath, JSON.stringify(featureCollection, null, 2), 'utf-8');

  console.log('\n✨ Generation complete!');
  console.log(`   ✅ Successful: ${successCount}`);
  console.log(`   ❌ Errors: ${errorCount}`);
  console.log(`   📁 Output saved to: ${outputPath}`);
  console.log(`   📊 Total features: ${featureCollection.features.length}`);
};

generateIsochrones().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});
