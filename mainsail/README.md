# Mainsail Consulting Group — website

Static, dependency-free site: six HTML pages, one stylesheet, one script, self-hosted fonts. No framework, no build step needed to view it.

```
mainsail/
  index.html                 home
  services/*.html            one page per service (5)
  assets/css/site.css        styles — design tokens at the top
  assets/js/site.js          behaviour (nav, smooth scroll, reveals, count-up, card stack, form, transitions)
  assets/js/lenis.min.js     Lenis smooth-scroll library (MIT), vendored
  assets/fonts/              Geist, Geist Mono, Instrument Serif (Latin subsets)
  assets/img/                responsive photography (avif / webp / jpg) + favicon, OG card
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

## Contact form

Out of the box, the form opens the visitor's mail client addressed to info@bymainsail.com. To receive submissions server-side instead, create a free endpoint at Formspree or Basin and put its URL in `formEndpoint` in `build/data.js`, then rebuild.
