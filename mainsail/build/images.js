// Generates responsive image variants from the source photography.
//   node mainsail/build/images.js
// Reads assets/img/src/*.jpg and writes assets/img/<key>-{900,1800}.{avif,webp,jpg}
// plus og.jpg, apple-touch-icon.png. The MAP below decides which source photo
// backs each key used in build.js; change a filename here to swap a photo.
'use strict';
const fs = require('fs');
const path = require('path');
const sharp = require('sharp');

const ROOT = path.join(__dirname, '..');
const SRC = path.join(ROOT, 'assets', 'img', 'src');
const OUT = path.join(ROOT, 'assets', 'img');

// key -> { file, focus } ; focus = sharp "position" for cropping to 3:2
const MAP = {
  hero:           { file: 'hero-sail.jpg',   ratio: 21 / 9, position: 'centre' },
  statement:      { file: 'interior-4.jpg',  ratio: 16 / 9, position: 'centre' },
  opm:            { file: 'opm-contract.jpg' },
  mitigation:     { file: 'interior-2.jpg', position: 'centre' },
  infrastructure: { file: 'hero-3.jpg' },
  relocation:     { file: 'interior-3.jpg' },
  staffing:       { file: 'interior-1.jpg' },
  hospital:       { file: 'hero-1.jpg' },
  medical:        { file: 'interior-2.jpg' },
  pharma:         { file: 'hero-4.jpg' },
  education:      { file: 'hero-2.jpg' },
};
const WIDTHS = [900, 1800];

async function variant(input, key, w, ratio, position) {
  const h = Math.round(w / ratio);
  const base = sharp(input).rotate().resize(w, h, { fit: 'cover', position: position || 'attention' });
  await base.clone().avif({ quality: 52, effort: 6 }).toFile(path.join(OUT, `${key}-${w}.avif`));
  await base.clone().webp({ quality: 74, effort: 6 }).toFile(path.join(OUT, `${key}-${w}.webp`));
  await base.clone().jpeg({ quality: 80, progressive: true, mozjpeg: true }).toFile(path.join(OUT, `${key}-${w}.jpg`));
}

(async () => {
  let total = 0;
  for (const [key, cfg] of Object.entries(MAP)) {
    const input = path.join(SRC, cfg.file);
    if (!fs.existsSync(input)) { console.warn(`missing source for ${key}: ${cfg.file}`); continue; }
    const ratio = cfg.ratio || 3 / 2;
    for (const w of WIDTHS) await variant(input, key, w, ratio, cfg.position);
    const size = WIDTHS.map(w => fs.statSync(path.join(OUT, `${key}-${w}.avif`)).size).reduce((a, b) => a + b, 0);
    total += size;
    console.log(`${key.padEnd(15)} ← ${cfg.file}  avif total ${(size / 1024).toFixed(0)} kB`);
  }
  // Open Graph card and touch icon
  const hero = path.join(SRC, MAP.hero.file);
  if (fs.existsSync(hero)) {
    await sharp(hero).resize(1200, 630, { fit: 'cover', position: 'centre' }).jpeg({ quality: 82, mozjpeg: true }).toFile(path.join(OUT, 'og.jpg'));
  }
  // Touch icon from the brand favicon (boat mark on navy)
  await sharp(path.join(OUT, 'favicon.svg')).resize(180, 180).png().toFile(path.join(OUT, 'apple-touch-icon.png'));
  console.log(`done. avif payload across all keys: ${(total / 1024).toFixed(0)} kB`);
})().catch(e => { console.error(e); process.exit(1); });
