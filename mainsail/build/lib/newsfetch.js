// Shared headline fetcher. Used by build/news.js (GitHub workflow, writes assets/data/news.json)
// and by api/news.js (Vercel endpoint the page refreshes from). No dependencies: Node 18+ fetch.
'use strict';

const UA = 'Mozilla/5.0 (compatible; MainsailNewsBot/1.0; +https://www.bymainsail.com)';
const MAX_AGE_DAYS = 45;
const PER_FEED = 10;
const KEEP = 60;

const gnews = (q) => `https://news.google.com/rss/search?q=${encodeURIComponent(q + ' when:45d')}&hl=en-US&gl=US&ceid=US:en`;

/* ---------- Organisations Mainsail is working with ----------
   Each entry adds Google News searches that surface candidate stories, and a title pattern: a story is
   tagged "work" (the "Our work" filter) only when its headline names the organisation, whichever feed it
   came from, so body-only mentions do not count. `sector` is the sector image key.
   To add one: give the full organisation name as it appears in the press, a pattern, and one or two searches. */
const CLIENTS = [
  { key: 'mgh', name: 'Massachusetts General Hospital', sector: 'hospital',
    match: /\b(massachusetts general hospital|mass general brigham|mass general\b|mgh\b|mgb\b)/i,
    queries: ['"Massachusetts General Hospital" construction OR building OR expansion OR renovation OR facility', '"Mass General Brigham" construction OR building OR campus OR facility'] },
  { key: '42north', name: '42 North Dental', sector: 'medical',
    match: /\b42\s?north dental\b/i,
    queries: ['"42 North Dental"'] },
  // VPP: add once the organisation's full name is confirmed, for example
  // { key: 'vpp', name: '<full name>', sector: 'pharma', match: /\b<full name>\b/i, queries: ['"<full name>" construction OR facility OR expansion'] },
];

/* Sector keys match the sector image keys in data.js: hospital, medical, pharma, education. */
const FEEDS = [
  ...CLIENTS.flatMap(c => c.queries.map(q => ({ url: gnews(q), google: true, source: null, tags: [c.sector], client: c.key }))),
  { url: 'https://www.constructiondive.com/feeds/news/', source: 'Construction Dive', tags: [] },
  { url: gnews('hospital construction project'), google: true, tags: ['hospital'] },
  { url: gnews('hospital OR "medical center" construction Boston OR Massachusetts'), google: true, tags: ['hospital'] },
  { url: gnews('medical office building OR outpatient center OR dental office construction'), google: true, tags: ['medical'] },
  { url: gnews('pharmaceutical OR biotech manufacturing facility construction'), google: true, tags: ['pharma'] },
  { url: gnews('"life sciences" OR biotech lab construction Massachusetts OR "New England"'), google: true, tags: ['pharma'] },
  { url: gnews('university campus construction project'), google: true, tags: ['education'] },
  { url: gnews('university OR college campus construction Massachusetts OR "New England"'), google: true, tags: ['education'] },
  { url: gnews('construction project management Massachusetts'), google: true, tags: [] },
];

/* Keyword tagging for general feeds, so the sector filter has something to show. */
const RULES = [
  ['hospital', /\b(hospitals?|health systems?|medical cent(er|re)s?|cancer cent(er|re)|children's)\b/i],
  ['medical', /\b(medical office|outpatient|ambulatory|clinics?|dental|health ?care)\b/i],
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
    let client = null;
    CLIENTS.forEach(c => { if (c.match.test(title)) { client = client || c.key; tags.add(c.sector); } });
    if (client) tags.add('work');
    const item = { title, url: decode(url), source: source || 'Source', date: when.toISOString(), tags: [...tags] };
    if (client) item.client = client;
    out.push(item);
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

/* Fetches every feed (failures are skipped), dedupes, drops old items, sorts newest first. */
async function fetchNews({ log = () => {} } = {}) {
  const cutoff = Date.now() - MAX_AGE_DAYS * 86400000;
  const seen = new Set();
  const items = [];
  const results = await Promise.allSettled(FEEDS.map(f => get(f.url).then(xml => parse(xml, f))));
  results.forEach((r, i) => {
    const feed = FEEDS[i];
    const label = feed.source || (feed.client ? `Google News (${feed.client})` : 'Google News');
    if (r.status !== 'fulfilled') { log(`skip ${label}: ${r.reason && r.reason.message}`); return; }
    let added = 0;
    for (const it of r.value) {
      const key = it.title.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
      if (seen.has(key) || new Date(it.date).getTime() < cutoff) continue;
      seen.add(key); items.push(it); added++;
    }
    log(`ok   ${label}: ${r.value.length} parsed, ${added} kept`);
  });
  items.sort((a, b) => new Date(b.date) - new Date(a.date));
  return { updated: new Date().toISOString(), items: items.slice(0, KEEP) };
}

module.exports = { fetchNews, FEEDS, CLIENTS };
