const fs = require('fs');
const csv = require('csv-parser');

const geo = JSON.parse(fs.readFileSync('public/isochrones_all.geojson', 'utf8'));
const isoIds = new Set();
for (const f of geo.features) {
  const cid = String(f.properties.company_id || '').trim();
  if (cid) isoIds.add(cid);
}
console.log('Isochrone company IDs:', isoIds.size);

const rows = [];
fs.createReadStream('public/prefabworldfin_reducedby_7.csv')
  .pipe(csv())
  .on('data', (r) => rows.push(r))
  .on('end', () => {
    console.log('CSV rows:', rows.length);
    const missing = [];
    for (const r of rows) {
      if (isoIds.has(r.id) === false) missing.push(r);
    }
    console.log('Missing:', missing.length);
    console.log('');
    for (const r of missing) {
      console.log(
        r.id + ' | ' + r.brand + ' | ' + r.country + ' | ' + r.region +
        ' | ' + r.latitude + ',' + r.longitude
      );
    }
  });
