# Fruit Center Marketplace — website

A fast, dependency-free website for [Fruit Center Marketplace](https://www.fruitcentermarketplace.com/), the family-owned market in Hingham and Milton, Massachusetts. Six pages, one stylesheet, one script, no build tools required to view it.

**Pages**

| File | What it is |
| --- | --- |
| `index.html` | Home: hero, live "open now" status for both stores, the eleven departments, what's in season this month, story, catering, community numbers |
| `departments.html` | Every department, counter by counter, with partners (Kinnealey Meats, Rocky Neck Fish, Mike's Fresh Sushi) and order-ahead links |
| `seasonal.html` | Interactive month-by-month New England produce guide |
| `catering.html` | Catering menu categories, how ordering works, gift baskets, FAQ |
| `our-story.html` | The Mignosa family timeline from 1889, the people, community and environment |
| `locations.html` | Both stores with maps, directions, phone, hours, and a FAQ |

## Run it locally

Open `index.html` in a browser, or serve the folder so the fonts preload cleanly:

```bash
python3 -m http.server 8000
# then visit http://localhost:8000
```

## Deploy

The site is plain static files, so any host works. For GitHub Pages: Settings → Pages → *Deploy from a branch* → pick this branch and the `/ (root)` folder.

## Editing

The six root HTML files are **generated** from `site-src/`, so the header, footer, and icon sprite live in one place:

```
site-src/
  build.js          # assembles pages → repo root  (node site-src/build.js)
  partials/         # head, header, footer, JSON-LD, SVG sprite
  pages/            # one file per page; the <!--META …--> comment sets title, description, slug
```

Edit a page or partial, then run `node site-src/build.js` (Node 18+). Styles are in `assets/css/site.css` (design tokens are at the top), behavior in `assets/js/site.js`.

### Design notes

- **Type**: Fraunces (display) and Instrument Sans (text), loaded from Google Fonts in `site-src/partials/head.html`. To self-host, download the variable woff2 files (`@fontsource-variable/fraunces` and `@fontsource-variable/instrument-sans` on npm) into `assets/fonts/` and add matching `@font-face` rules at the top of `site.css`.
- **Palette**: paper backgrounds, deep market green, tomato red for actions, lemon highlights; each department has its own accent.
- **Illustration**: every icon is an original inline SVG in `site-src/partials/sprite.html`. There are no photographs yet; drop store photography into any `.art-block` or `.hero__art` container when it's available.
- **Motion**: scroll reveals, a marquee, a slow rotating badge, and a pointer parallax on the hero. Everything respects `prefers-reduced-motion`.
- **Live status**: `site.js` computes open/closed from store hours (8 am – 7 pm daily, Eastern) and updates every minute. Change the `HOURS` constant if hours change.
- **Seasonal guide**: the produce calendar is the `SEASON` array in `site.js`; add or edit entries there.

Store facts on the site (addresses, phones, hours, partners, history) were compiled from the market's own site and local press coverage. Verify anything time-sensitive, like holiday hours, before publishing.

---

## Farmers Markets Explorer (CS230 final project)

`KarehProgramFinal.py` is a separate Streamlit app that explores the USDA Farmers Markets Directory (`farmersmarket_2026.csv`).

```bash
pip install -r requirements.txt
streamlit run KarehProgramFinal.py
```
