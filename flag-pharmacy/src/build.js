// Assembles flag-pharmacy/*.html from src/pages/*.html + src/partials.
// Usage: node flag-pharmacy/src/build.js
const fs = require('fs');
const path = require('path');
const SRC = __dirname;
const OUT = path.join(__dirname, '..');
const partial = (n) => fs.readFileSync(path.join(SRC, 'partials', n), 'utf8');
const head = partial('head.html'), header = partial('header.html'), footer = partial('footer.html');
const ICONS = {
  pin: '<path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
  phone: '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  truck: '<path d="M3 7h11v9H3zM14 10h4l3 3v3h-7z"/><circle cx="7" cy="18" r="1.8"/><circle cx="17" cy="18" r="1.8"/>',
  pill: '<rect x="3" y="9" width="18" height="6" rx="3" transform="rotate(-45 12 12)"/><path d="M9 9l6 6"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
  box: '<path d="M3 8l9-4 9 4v8l-9 4-9-4z"/><path d="M3 8l9 4 9-4M12 12v8"/>',
  heart: '<path d="M12 20s-7-4.5-7-10a4 4 0 0 1 7-2.5A4 4 0 0 1 19 10c0 5.5-7 10-7 10z"/>',
  shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  phoneapp: '<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/>',
  chat: '<path d="M4 5h16v10H9l-5 4z"/>',
  dollar: '<path d="M12 3v18M16 7.5A3.5 3.5 0 0 0 12.5 5h-1A3.5 3.5 0 0 0 8 8.5c0 2 1.5 3 4 3.5s4 1.5 4 3.5A3.5 3.5 0 0 1 12.5 19h-1A3.5 3.5 0 0 1 8 15.5"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
  syringe: '<path d="M4 20l4-4M7 17l10-10 3 3-10 10zM14 7l3 3M12 9l2 2M9 12l2 2"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9M19 14v6H4V5h6"/>',
  leaf: '<path d="M5 19C5 9 11 5 20 4c-1 9-5 15-15 15z"/><path d="M5 19l9-9"/>',
  photo: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="1.5"/><path d="M21 16l-5-5-9 8"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>'
};
const icon = (n, cls) => `<svg class="${cls || 'icon'}" aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">${ICONS[n] || ''}</svg>`;
const photo = (file, caption, alt, cls) => `<figure class="photo${cls ? ' ' + cls : ''}" data-caption="Photo: ${caption}"><img src="assets/img/${file}" alt="${alt}" loading="lazy" onerror="this.closest('.photo').classList.add('photo--missing')">${icon('photo', 'photo__mark')}</figure>`;
const expand = (s) => s
  .replace(/{{PHOTO ([^|}]+)\|([^|}]+)\|([^|}]+)(?:\|([^}]+))?}}/g, (_, f, c, a, k) => photo(f.trim(), c.trim(), a.trim(), (k || '').trim()))
  .replace(/{{ICON ([a-z]+)(?: ([^}]+))?}}/g, (_, n, k) => icon(n, k));
const written = [];
for (const f of fs.readdirSync(path.join(SRC, 'pages')).filter((f) => f.endsWith('.html'))) {
  let src = fs.readFileSync(path.join(SRC, 'pages', f), 'utf8');
  const m = src.match(/^<!--META\s*([\s\S]*?)-->/);
  if (!m) throw new Error('Missing META in ' + f);
  const meta = JSON.parse(m[1]);
  src = expand(src.slice(m[0].length).trim());
  const h = head.replace(/{{TITLE}}/g, meta.title).replace(/{{DESC}}/g, meta.desc).replace('{{BODYCLASS}}', meta.bodyClass || '');
  // mark current nav item (and its parent group)
  let hd = header.replace(new RegExp(`<a href="${meta.slug}.html"`, 'g'), `<a href="${meta.slug}.html" aria-current="page"`);
  if (meta.group) hd = hd.replace(`data-group="${meta.group}"`, `data-group="${meta.group}" data-active`);
  const out = [h.trim(), expand(hd.trim()), src, expand(footer.trim())].join('\n') + '\n';
  fs.writeFileSync(path.join(OUT, meta.slug + '.html'), out);
  written.push(meta.slug + '.html');
}
console.log('built:', written.join(', '));
