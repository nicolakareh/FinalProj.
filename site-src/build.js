// Assembles the static pages from site-src/pages/*.html + site-src/partials into the repo root.
// Usage: node site-src/build.js
const fs = require('fs');
const path = require('path');
const SRC = __dirname;
const OUT = process.argv[2] || path.join(__dirname, '..');
const partial = (n) => fs.readFileSync(path.join(SRC, 'partials', n), 'utf8');
const head = partial('head.html'), header = partial('header.html'), footer = partial('footer.html');
const sprite = partial('sprite.html'), jsonld = partial('jsonld.html');
const written = [];
for (const f of fs.readdirSync(path.join(SRC, 'pages')).filter((f) => f.endsWith('.html'))) {
  let src = fs.readFileSync(path.join(SRC, 'pages', f), 'utf8');
  const m = src.match(/^<!--META\s*([\s\S]*?)-->/);
  if (!m) throw new Error('Missing META in ' + f);
  const meta = JSON.parse(m[1]);
  src = src.slice(m[0].length).trim();
  const h = head.replace(/{{TITLE}}/g, meta.title).replace(/{{DESC}}/g, meta.desc)
    .replace('{{BODYCLASS}}', meta.bodyClass || '').replace('{{JSONLD}}', meta.jsonld ? jsonld.trim() : '');
  const hd = header.replace(`<a href="${meta.slug}.html">`, `<a href="${meta.slug}.html" aria-current="page">`);
  const out = [h.trim(), sprite.trim(), hd.trim(), src, footer.trim()].join('\n') + '\n';
  fs.writeFileSync(path.join(OUT, meta.slug + '.html'), out);
  written.push(meta.slug + '.html');
}
console.log('built:', written.join(', '));
