# Mainsail Consulting Group — website

Static, dependency-free site: six HTML pages, one stylesheet, one script, self-hosted fonts. No framework, no build step needed to view it.

```
mainsail/
  index.html                 home
  services/*.html            one page per service (5)
  assets/css/site.css        styles — design tokens at the top
  assets/js/site.js          behaviour (nav, reveals, count-up, hover images, form, transitions)
  assets/fonts/              Geist, Geist Mono, Instrument Serif (Latin subsets)
  assets/img/                responsive photography (avif / webp / jpg at 900 / 1800 / 2600 px) + favicon, OG card
  assets/video/              hero loop: hero.webm / hero.mp4 plus 720p phone versions (Higgsfield Kling, from the hero still)
  assets/img/src/            2400px source photos the variants are generated from
  build/data.js              ALL SITE COPY lives here
  build/build.js             generates the HTML pages from data.js
  build/images.js            generates the responsive image variants from assets/img/src
```

## Preview locally

```bash
cd mainsail && python3 -m http.server 8000   # then open http://localhost:8000
```

## Deploy on Vercel

Import the repository and set **Root Directory** to `mainsail`. No build command, no output directory: Vercel serves the folder as-is (`vercel.json` turns on clean URLs and long-lived caching for `/assets`). GitHub Pages or Netlify work the same way.

## Editing copy

Edit `build/data.js`, then run:

```bash
node mainsail/build/build.js
```

Every page is regenerated. The header, footer, metadata and JSON-LD are shared, so nothing has to be changed twice.

## Swapping photography

Drop a photo into `assets/img/src/`, point the matching key in `build/images.js` at it, then:

```bash
cd mainsail/build && npm install && npm run images
```

## Hero video

The loop only loads after the page has painted, never on reduced-motion or data-saver settings, and pauses when scrolled out of view. The still image is always the poster and the fallback. To swap it, replace the four files in `assets/video/` (WebM and MP4, full and 720p).

## Contact form

Out of the box, the form opens the visitor's mail client addressed to info@bymainsail.com. To receive submissions server-side instead, create a free endpoint at Formspree or Basin and put its URL in `formEndpoint` in `build/data.js`, then rebuild.
