// Reference-site capture script.
//
// Loads each site at desktop (1440px) and mobile (390px) widths, dismisses cookie
// banners, screenshots the fold, scrolls 700px and screenshots the nav (to see how it
// changes on scroll), scrolls the whole page slowly so scroll-triggered animations
// fire, then takes a full-page screenshot and writes a JSON of structural notes
// (section headings, nav styles before/after scroll, animation libraries, tabs,
// videos, page-builder fingerprints).
//
// Run:   node reference/capture.mjs                 # both reference sites → reference/
//        node reference/capture.mjs --out somewhere  # different output folder
//        CAPTURE_SITES="local=http://127.0.0.1:8123/" node reference/capture.mjs
//
// Needs Playwright + Chromium: `npm i -D playwright && npx playwright install chromium`
// (or a global install). Honors HTTPS_PROXY if set.

import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const DEFAULT_SITES = [
  { name: 'droneshine', url: 'https://droneshine.de/' },
  { name: 'birdeye', url: 'https://birdeye.com/' },
];

const VIEWPORTS = [
  { name: 'desktop', viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 },
  {
    name: 'mobile',
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
    userAgent:
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
  },
];

const KNOWN_LIBS = ['gsap', 'scrolltrigger', 'lottie', 'swiper', 'lenis', 'framer', 'aos', 'locomotive', 'splide', 'three', 'rive', 'motion', 'alpine', 'jquery', 'elementor', 'wp-content', 'divi', 'webflow', 'hubspot', 'wistia', 'vimeo', 'youtube'];

function parseArgs() {
  const args = process.argv.slice(2);
  const outIdx = args.indexOf('--out');
  const out = outIdx >= 0 ? args[outIdx + 1] : 'reference';
  const sites = process.env.CAPTURE_SITES
    ? process.env.CAPTURE_SITES.split(',').map((pair) => {
        const [name, ...rest] = pair.split('=');
        return { name: name.trim(), url: rest.join('=').trim() };
      })
    : DEFAULT_SITES;
  return { out, sites };
}

async function dismissCookies(page) {
  const patterns = [/alle akzeptieren/i, /akzeptieren/i, /accept all/i, /^accept$/i, /agree/i, /got it/i, /allow all/i, /^ok$/i, /zustimmen/i];
  for (const re of patterns) {
    const btn = page.getByRole('button', { name: re }).first();
    try {
      if (await btn.isVisible({ timeout: 800 })) {
        await btn.click({ timeout: 2000 });
        await page.waitForTimeout(500);
        return String(re);
      }
    } catch {
      /* not present */
    }
  }
  return null;
}

async function slowScroll(page, step = 320, pause = 110) {
  await page.evaluate(
    async ({ step, pause }) => {
      const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
      let last = -1;
      for (let y = 0; y < document.documentElement.scrollHeight; y += step) {
        window.scrollTo(0, y);
        await sleep(pause);
        const h = document.documentElement.scrollHeight;
        if (h === last && y > h) break;
        last = h;
      }
      window.scrollTo(0, document.documentElement.scrollHeight);
      await sleep(800);
      window.scrollTo(0, 0);
      await sleep(600);
    },
    { step, pause },
  );
}

async function headerSnapshot(page) {
  return page.evaluate(() => {
    const el = document.querySelector('header, [class*="header"], [class*="navbar"], nav');
    if (!el) return null;
    const cs = getComputedStyle(el);
    return {
      tag: el.tagName.toLowerCase(),
      className: (el.className && String(el.className).slice(0, 200)) || '',
      position: cs.position,
      background: cs.backgroundColor,
      backdropFilter: cs.backdropFilter || cs.webkitBackdropFilter,
      boxShadow: cs.boxShadow,
      height: Math.round(el.getBoundingClientRect().height),
      transition: cs.transition,
    };
  });
}

async function collectNotes(page) {
  return page.evaluate((KNOWN_LIBS) => {
    const text = (el) => (el.textContent || '').replace(/\s+/g, ' ').trim();
    const headings = [...document.querySelectorAll('h1, h2, h3')]
      .map((h) => ({ tag: h.tagName.toLowerCase(), text: text(h).slice(0, 140) }))
      .filter((h) => h.text)
      .slice(0, 80);
    const navLinks = [...document.querySelectorAll('header a, nav a')]
      .map((a) => text(a))
      .filter(Boolean)
      .slice(0, 40);
    const buttons = [...document.querySelectorAll('a.btn, a[class*="button"], button, a[class*="cta"]')]
      .map((b) => text(b))
      .filter((t) => t && t.length < 40)
      .slice(0, 40);
    const scripts = [...document.scripts].map((s) => s.src).filter(Boolean);
    const libs = [...new Set(KNOWN_LIBS.filter((lib) => scripts.some((s) => s.toLowerCase().includes(lib)) || document.documentElement.outerHTML.toLowerCase().includes(lib)))];
    const videos = [...document.querySelectorAll('video')].map((v) => ({
      src: v.currentSrc || v.src || (v.querySelector('source') || {}).src || '',
      autoplay: v.autoplay,
      loop: v.loop,
      muted: v.muted,
    }));
    const revealSelectors = ['[data-aos]', '.aos-init', '[class*="reveal"]', '[class*="fade"]', '[class*="animate"]', '[class*="in-view"]', '[class*="inview"]', '[data-scroll]', '[class*="motion"]'];
    const reveals = Object.fromEntries(revealSelectors.map((s) => [s, document.querySelectorAll(s).length]).filter(([, n]) => n > 0));
    const tabs = {
      tablists: document.querySelectorAll('[role="tablist"]').length,
      tabs: [...document.querySelectorAll('[role="tab"], [class*="tab-"] button, [class*="tabs"] button')].map((t) => text(t)).filter(Boolean).slice(0, 30),
    };
    const generator = (document.querySelector('meta[name="generator"]') || {}).content || null;
    const bodyClass = (document.body.className || '').slice(0, 300);
    const builderHints = ['elementor', 'wp-content', 'divi', 'et_pb', 'vc_row', 'wpb_', 'webflow', 'w-container', 'squarespace', 'wix', 'hs-', 'jet-', 'uk-'].filter((k) => document.documentElement.outerHTML.includes(k));
    const fonts = [...new Set([...document.querySelectorAll('h1, h2, p, a, body')].map((el) => getComputedStyle(el).fontFamily))].slice(0, 8);
    const colors = [...new Set([...document.querySelectorAll('a, button, h1, h2, section, body')].flatMap((el) => [getComputedStyle(el).color, getComputedStyle(el).backgroundColor]))].filter((c) => c && c !== 'rgba(0, 0, 0, 0)').slice(0, 24);
    const transitions = [...new Set([...document.querySelectorAll('a, button, [class*="card"]')].map((el) => getComputedStyle(el).transition).filter((t) => t && t !== 'all 0s ease 0s' && t !== 'none'))].slice(0, 12);
    return {
      title: document.title,
      generator,
      bodyClass,
      builderHints,
      wordCount: text(document.body).split(' ').length,
      images: document.images.length,
      svgs: document.querySelectorAll('svg').length,
      videos,
      headings,
      navLinks,
      buttons,
      libs,
      reveals,
      tabs,
      fonts,
      colors,
      transitions,
      scrollHeight: document.documentElement.scrollHeight,
    };
  }, KNOWN_LIBS);
}

async function captureSite(browser, site, vp, outDir) {
  const context = await browser.newContext({
    viewport: vp.viewport,
    deviceScaleFactor: vp.deviceScaleFactor,
    isMobile: vp.isMobile || false,
    hasTouch: vp.hasTouch || false,
    userAgent: vp.userAgent,
    locale: 'en-US',
  });
  const page = await context.newPage();
  const prefix = path.join(outDir, `${site.name}-${vp.name}`);
  const notes = { site: site.url, viewport: vp.name, capturedAt: new Date().toISOString() };
  try {
    try {
      await page.goto(site.url, { waitUntil: 'networkidle', timeout: 60000 });
    } catch {
      await page.goto(site.url, { waitUntil: 'load', timeout: 60000 });
    }
    await page.waitForTimeout(1500);
    notes.cookieBannerDismissed = await dismissCookies(page);
    await page.screenshot({ path: `${prefix}-01-fold.png` });
    notes.headerAtTop = await headerSnapshot(page);

    await page.evaluate(() => window.scrollTo({ top: 700, behavior: 'instant' }));
    await page.waitForTimeout(700);
    notes.headerAfterScroll = await headerSnapshot(page);
    await page.screenshot({ path: `${prefix}-02-nav-scrolled.png`, clip: { x: 0, y: 0, width: vp.viewport.width, height: 220 } });

    await slowScroll(page);
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${prefix}-03-full.jpg`, fullPage: true, type: 'jpeg', quality: 78 });

    // Hover the first nav link and the first prominent button, to catch micro-interactions.
    if (vp.name === 'desktop') {
      const hoverTargets = [page.locator('header a, nav a').first(), page.locator('a.btn, a[class*="button"], button').first()];
      let i = 0;
      for (const t of hoverTargets) {
        try {
          await t.scrollIntoViewIfNeeded({ timeout: 2000 });
          await t.hover({ timeout: 2000 });
          await page.waitForTimeout(450);
          await page.screenshot({ path: `${prefix}-04-hover-${i++}.png` });
        } catch {
          /* skip */
        }
      }
    }
    Object.assign(notes, await collectNotes(page));
  } catch (err) {
    notes.error = String(err && err.message ? err.message : err);
  }
  await writeFile(`${prefix}-notes.json`, JSON.stringify(notes, null, 2));
  await context.close();
  console.log(`${site.name} @ ${vp.name}: ${notes.error ? 'FAILED ' + notes.error : 'ok'}`);
}

const { out, sites } = parseArgs();
await mkdir(out, { recursive: true });
// Playwright forces loopback traffic through a configured proxy unless this flag is set,
// which breaks local dev-server captures behind a corporate/agent proxy.
process.env.PLAYWRIGHT_DISABLE_FORCED_CHROMIUM_PROXIED_LOOPBACK ??= '1';
const bypass = ['localhost', '127.0.0.1', '::1', ...(process.env.NO_PROXY || '').split(',')].map((s) => s.trim()).filter(Boolean).join(',');
const browser = await chromium.launch({
  proxy: process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY, bypass } : undefined,
});
for (const site of sites) {
  for (const vp of VIEWPORTS) {
    await captureSite(browser, site, vp, out);
  }
}
await browser.close();
