// Fetches industry headlines into assets/data/news.json.
// Runs on GitHub Actions (.github/workflows/news.yml); this sandbox has no outbound access to the feeds.
// No dependencies: Node 18+ fetch and a small RSS/Atom parser.
'use strict';
const fs = require('fs');
const path = require('path');

const OUT = path.join(__dirname, '..', 'assets', 'data', 'news.json');
const UA = 'Mozilla/5.0 (compatible; MainsailNewsBot/1.0; +https://www.bymainsail.com)';
const MAX_AGE_DAYS = 45;
const PER_FEED = 10;
const KEEP = 48;

const gnews = (q) => `https://news.google.com/rss/search?q=${encodeURIComponent(q + ' when:30d')}&hl=en-US&gl=US&ceid=US:en`;

/* Sector keys match the sector image keys in data.js: hospital, medical, pharma, education. */
const FEEDS = [
  { url: 'https://www.constructiondive.com/feeds/news/', source: 'Construction Dive', tags: [] },
  { url: gnews('hospital construction project'), google: true, tags: ['hospital'] },
  { url: gnews('hospital OR "medical center" construction Boston OR Massachusetts'), google: true, tags: ['hospital'] },
  { url: gnews('medical office building OR outpatient center construction'), google: true, tags: ['medical'] },
  { url: gnews('pharmaceutical OR biotech manufacturing facility construction'), google: true, tags: ['pharma'] },
  { url: gnews('"life sciences" OR biotech lab construction Massachusetts OR "New England"'), google: true, tags: ['pharma'] },
  { url: gnews('university campus construction project'), google: true, tags: ['education'] },
  { url: gnews('university OR college campus construction Massachusetts OR "New England"'), google: true, tags: ['education'] },
  { url: gnews('construction project management Massachusetts'), google: true, tags: [] },
];

/* Keyword tagging for general feeds, so the sector filter has something to show. */
const RULES = [
  ['hospital', /\b(hospitals?|health systems?|medical cent(er|re)s?|cancer cent(er|re)|children's)\b/i],
  ['medical', /\b(medical office|outpatient|ambulatory|clinics?|health ?care)\b/i],
  ['pharma', /\b(pharma|pharmaceutical|biotech|biopharma|life[- ]sciences?|laborator(y|ies)|lab space|cgmp)\b/i],
  ['education', /\b(universit(y|ies)|colleges?|campus|higher[- ]ed(ucation)?)\b/i],
];

/* Keep the strip professional: no social-media sources, no crime, accident or legal-dispute stories. */
const BLOCK_SOURCES = /\b(facebook|twitter|x\.com|instagram|tiktok|youtube|reddit|linkedin|threads\.net)\b/i;
const BLOCK_TITLES = /\b(died|dies|dead|deaths?|killed|shot|shooting|crash|arrest(ed)?|charged|lawsuit|sued|police|fire chief|indicted|fraud|scandal)\b/i;

const decode = (s) => String(s || '')
  .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
  .replace(/<[^>]+>/g, '')
  .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;|&apos;/g, "'")
  .replace(/&#(\d+);/g, (m, n) => String.fromCharCode(Number(n)))
  .replace(/&nbsp;/g, ' ')
  .replace(/\s+/g, ' ').trim();
const pick = (xml, tag) => { const m = xml.match(new RegExp(`<${tag}(?:\\s[^>]*)?>([\\s\\S]*?)</${tag}>`, 'i')); return m ? decode(m[1]) : ''; };
const escRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

function parse(xml, feed) {
  const out = [];
  const blocks = xml.match(/<item[\s>][\s\S]*?<\/item>/gi) || xml.match(/<entry[\s>][\s\S]*?<\/entry>/gi) || [];
  for (const b of blocks) {
    let title = pick(b, 'title');
    let url = pick(b, 'link') || (b.match(/<link[^>]*href="([^"]+)"/i) || [])[1] || '';
    const date = pick(b, 'pubDate') || pick(b, 'dc:date') || pick(b, 'published') || pick(b, 'updated');
    let source = feed.source || pick(b, 'source');
    if (feed.google && source) title = title.replace(new RegExp(`\\s+-\\s+${escRe(source)}\\s*$`), '');
    if (!title || !url) continue;
    if (BLOCK_SOURCES.test(source) || BLOCK_SOURCES.test(url) || BLOCK_TITLES.test(title)) continue;
    const when = new Date(date);
    if (Number.isNaN(when.getTime())) continue;
    const tags = new Set(feed.tags);
    RULES.forEach(([tag, re]) => { if (re.test(title)) tags.add(tag); });
    out.push({ title, url: decode(url), source: source || 'Source', date: when.toISOString(), tags: [...tags] });
    if (out.length >= PER_FEED) break;
  }
  return out;
}

async function get(url) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 20000);
  try {
    const res = await fetch(url, { headers: { 'User-Agent': UA, Accept: 'application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.5' }, signal: ctrl.signal, redirect: 'follow' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.text();
  } finally { clearTimeout(t); }
}

(async () => {
  const cutoff = Date.now() - MAX_AGE_DAYS * 86400000;
  const seen = new Set();
  const items = [];
  for (const feed of FEEDS) {
    try {
      const xml = await get(feed.url);
      const got = parse(xml, feed);
      let added = 0;
      for (const it of got) {
        const key = it.title.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
        if (seen.has(key) || new Date(it.date).getTime() < cutoff) continue;
        seen.add(key); items.push(it); added++;
      }
      console.log(`ok   ${feed.source || 'Google News'}: ${got.length} parsed, ${added} kept`);
    } catch (e) {
      console.log(`skip ${feed.source || feed.url}: ${e.message}`);
    }
  }
  items.sort((a, b) => new Date(b.date) - new Date(a.date));
  const next = { updated: new Date().toISOString(), items: items.slice(0, KEEP) };

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
