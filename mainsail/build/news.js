// Writes recent industry headlines to assets/data/news.json.
// Runs on GitHub Actions (.github/workflows/news.yml); this sandbox has no outbound access to the feeds.
// The fetcher itself lives in build/lib/newsfetch.js and is shared with api/news.js.
'use strict';
const fs = require('fs');
const path = require('path');
const { fetchNews } = require('./lib/newsfetch.js');

const OUT = path.join(__dirname, '..', 'assets', 'data', 'news.json');

(async () => {
  const next = await fetchNews({ log: (m) => console.log(m) });
  let prev = null;
  try { prev = JSON.parse(fs.readFileSync(OUT, 'utf8')); } catch (e) { /* first run */ }
  if (next.items.length < 6 && prev && prev.items && prev.items.length >= next.items.length) {
    console.log(`only ${next.items.length} headlines fetched; keeping the previous ${prev.items.length}`);
    process.exit(0);
  }
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(next, null, 1) + '\n');
  console.log(`wrote ${next.items.length} headlines to assets/data/news.json`);
})().catch(e => { console.error(e); process.exit(1); });
