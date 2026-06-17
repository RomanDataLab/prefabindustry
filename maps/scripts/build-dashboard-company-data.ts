import fs from 'node:fs';
import path from 'node:path';
import csv from 'csv-parser';

type CsvRow = Record<string, string>;

interface DashboardCompany {
  id: string;
  brand: string;
  webpage: string;
  latitude: number;
  longitude: number;
  country: string;
  countryCode: string;
  region: string;
  address: string;
  type: string;
  mainStructureMaterial: string;
  modelsAmount: number | null;
  minSqm: number | null;
  medianSqm: number | null;
  maxSqm: number | null;
  minHomePriceK: number | null;
  medianUPriceK: number | null;
  vizUrls: string[];
  planUrls: string[];
  configurator: string;
  desc: string;
  flagUrl: string;
  iconColor: string;
}

const ROOT = process.cwd();
const PUBLIC_DIR = path.join(ROOT, 'public');
const COMPANIES_CSV = path.join(PUBLIC_DIR, 'prefabworldfin_reducedby_7.csv');
const FLAG_CSV_PRIMARY = path.join(PUBLIC_DIR, 'flag.csv');
const FLAG_CSV_FALLBACK = path.join(PUBLIC_DIR, 'old', 'flag.csv');
const OUTPUT_JSON = path.join(PUBLIC_DIR, 'prefab-dashboard-data.json');

const readCsv = (filePath: string): Promise<CsvRow[]> =>
  new Promise((resolve, reject) => {
    const rows: CsvRow[] = [];
    fs.createReadStream(filePath)
      .pipe(csv())
      .on('data', (row: CsvRow) => rows.push(row))
      .on('end', () => resolve(rows))
      .on('error', (err) => reject(err));
  });

const toNumber = (value: string | undefined): number | null => {
  if (!value) return null;
  const parsed = Number.parseFloat(String(value).trim());
  return Number.isFinite(parsed) ? parsed : null;
};

const toInteger = (value: string | undefined): number | null => {
  if (!value) return null;
  const parsed = Number.parseInt(String(value).trim(), 10);
  return Number.isFinite(parsed) ? parsed : null;
};

const round1 = (value: number): number => Math.round(value * 10) / 10;

const toThousands = (value: number | null): number | null => {
  if (value === null) return null;
  return round1(value / 1000);
};

const parseUrlArray = (raw: string | undefined): string[] => {
  if (!raw) return [];
  const trimmed = raw.trim();
  if (!trimmed) return [];

  try {
    const parsed = JSON.parse(trimmed);
    if (Array.isArray(parsed)) {
      return parsed
        .map((item) => String(item).trim())
        .filter(Boolean);
    }
  } catch {
    // fall back to lightweight parser below
  }

  const unwrapped = trimmed.replace(/^\[/, '').replace(/\]$/, '');
  return unwrapped
    .split(',')
    .map((value) => value.replace(/^"+|"+$/g, '').trim())
    .filter(Boolean);
};

const parseSqmRanges = (raw: string | undefined): number[] => {
  if (!raw) return [];
  const cleaned = raw.trim().replace(/^\[/, '').replace(/\]$/, '');
  if (!cleaned) return [];

  return cleaned
    .split(',')
    .map((value) => Number.parseFloat(value.trim()))
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => a - b);
};

const medianOf = (values: number[]): number | null => {
  if (values.length === 0) return null;
  const middle = Math.floor(values.length / 2);
  if (values.length % 2 === 1) return values[middle];
  return round1((values[middle - 1] + values[middle]) / 2);
};

const getIconColor = (materialRaw: string, typeRaw: string): string => {
  const type = typeRaw.trim().toLowerCase();
  if (type === 'panels') return '#ffffff';

  const material = materialRaw.trim().toLowerCase();
  switch (material) {
    case 'hempcrete':
    case 'bamboo':
      return '#00bfa5';
    case 'wood':
    case 'wood/timber':
      return '#006400';
    case 'clt':
      return '#ffd700';
    case 'composite':
    case 'sip':
      return '#ff8c00';
    case 'concrete':
      return '#ff0000';
    case 'aac blocks':
      return '#8a2be2';
    case 'steel':
      return '#1e90ff';
    default:
      return '#888888';
  }
};

const chooseFlagCsv = (): string => {
  if (fs.existsSync(FLAG_CSV_PRIMARY)) return FLAG_CSV_PRIMARY;
  return FLAG_CSV_FALLBACK;
};

const main = async () => {
  const flagCsv = chooseFlagCsv();
  const [companyRows, flagRows] = await Promise.all([
    readCsv(COMPANIES_CSV),
    readCsv(flagCsv),
  ]);

  const flagByCode = new Map<string, string>();
  for (const row of flagRows) {
    const code = String(row.country_code || '').trim().toUpperCase();
    const flag = String(row.flag || '').trim();
    if (code && flag) {
      flagByCode.set(code, flag);
    }
  }

  const companies: DashboardCompany[] = [];
  for (const row of companyRows) {
    const lat = toNumber(row.latitude);
    const lon = toNumber(row.longitude);
    if (lat === null || lon === null) continue;
    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) continue;

    const countryCode = String(row.country_code || '').trim().toUpperCase();
    const sqmRanges = parseSqmRanges(row.sqm_ranges);
    const minHomePrice = toNumber(row.min_home_price);
    const medianUPrice = toNumber(row.median_u_price);
    const type = String(row.type || '').trim();
    const mainStructureMaterial = String(row.main_structure_material || '').trim();

    companies.push({
      id: String(row.id || '').trim() || `${companies.length + 1}`,
      brand: String(row.brand || '').trim(),
      webpage: String(row.webpage || '').trim(),
      latitude: lat,
      longitude: lon,
      country: String(row.country || '').trim(),
      countryCode,
      region: String(row.region || '').trim(),
      address: String(row.address || '').trim(),
      type,
      mainStructureMaterial,
      modelsAmount: toInteger(row.models_amount),
      minSqm: toNumber(row.min_sqm),
      medianSqm: medianOf(sqmRanges),
      maxSqm: toNumber(row.max_sqm),
      minHomePriceK: toThousands(minHomePrice),
      medianUPriceK: toThousands(medianUPrice),
      configurator: String(row.configurator || '').trim(),
      desc: String(row.desc_en || '').trim(),
      vizUrls: parseUrlArray(row.viz),
      planUrls: parseUrlArray(row.plans),
      flagUrl: flagByCode.get(countryCode) || '',
      iconColor: getIconColor(mainStructureMaterial, type),
    });
  }

  const payload = {
    source: {
      companiesCsv: path.basename(COMPANIES_CSV),
      flagsCsv: path.basename(flagCsv),
    },
    generatedAt: new Date().toISOString(),
    count: companies.length,
    companies,
  };

  fs.writeFileSync(OUTPUT_JSON, JSON.stringify(payload, null, 2), 'utf8');
  console.log(`Wrote ${companies.length} companies to ${OUTPUT_JSON}`);
};

main().catch((error) => {
  console.error('Failed to build dashboard data:', error);
  process.exit(1);
});
