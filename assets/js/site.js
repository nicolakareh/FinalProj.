/* ==========================================================================
   Fruit Center Marketplace — site.js
   Progressive enhancement only: every page works without this file.
   ========================================================================== */
(() => {
  'use strict';

  const doc = document;
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- Sticky header shadow ---------- */
  const header = doc.querySelector('.site-header');
  const onScroll = () => { if (header) header.classList.toggle('is-scrolled', window.scrollY > 8); };
  onScroll();
  window.addEventListener('scroll', onScroll, { passive: true });

  /* ---------- Mobile navigation ---------- */
  const toggle = doc.querySelector('.nav-toggle');
  const nav = doc.getElementById('site-nav');
  if (toggle && nav) {
    const setOpen = (open) => {
      toggle.setAttribute('aria-expanded', String(open));
      toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
      nav.classList.toggle('is-open', open);
      doc.documentElement.classList.toggle('nav-open', open);
    };
    toggle.addEventListener('click', () => setOpen(toggle.getAttribute('aria-expanded') !== 'true'));
    doc.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && nav.classList.contains('is-open')) { setOpen(false); toggle.focus(); }
    });
    nav.querySelectorAll('a').forEach((a) => a.addEventListener('click', () => setOpen(false)));
    const mq = window.matchMedia('(min-width: 1024px)');
    mq.addEventListener('change', (e) => { if (e.matches) setOpen(false); });
  }

  /* ---------- Scroll reveal ---------- */
  const revealEls = doc.querySelectorAll('[data-reveal]');
  if (revealEls.length && 'IntersectionObserver' in window && !reduceMotion) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting) { en.target.classList.add('is-visible'); io.unobserve(en.target); }
      });
    }, { rootMargin: '0px 0px -6% 0px', threshold: 0.08 });
    revealEls.forEach((el) => io.observe(el));
  } else {
    revealEls.forEach((el) => el.classList.add('is-visible'));
  }

  /* ---------- Store hours & live "open now" status ----------
     Both stores: 8:00 am – 7:00 pm, seven days a week (Eastern Time). */
  const HOURS = { open: 8 * 60, close: 19 * 60 };

  function nowEastern() {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/New_York', hour: 'numeric', minute: 'numeric', hour12: false, weekday: 'long'
    }).formatToParts(new Date());
    const get = (t) => (parts.find((p) => p.type === t) || {}).value;
    let h = parseInt(get('hour'), 10); if (h === 24) h = 0;
    return { minutes: h * 60 + parseInt(get('minute'), 10), weekday: get('weekday') };
  }
  function fmtTime(min) {
    const h = Math.floor(min / 60), m = min % 60;
    const suffix = h >= 12 ? 'pm' : 'am';
    const hh = ((h + 11) % 12) + 1;
    return m ? `${hh}:${String(m).padStart(2, '0')} ${suffix}` : `${hh} ${suffix}`;
  }
  function renderStatus() {
    const els = doc.querySelectorAll('[data-open-status]');
    if (!els.length) return;
    const { minutes } = nowEastern();
    const open = minutes >= HOURS.open && minutes < HOURS.close;
    let label, sub;
    if (open) {
      const left = HOURS.close - minutes;
      label = 'Open now';
      sub = left <= 60 ? `closes in ${left} min` : `until ${fmtTime(HOURS.close)}`;
    } else {
      label = 'Closed';
      sub = minutes < HOURS.open ? `opens at ${fmtTime(HOURS.open)}` : `opens tomorrow at ${fmtTime(HOURS.open)}`;
    }
    els.forEach((el) => {
      el.classList.toggle('pill--open', open);
      el.classList.toggle('pill--closed', !open);
      el.innerHTML = `<span class="pill__dot" aria-hidden="true"></span>${label} <span class="pill__sub">· ${sub}</span>`;
    });
  }
  renderStatus();
  setInterval(renderStatus, 60 * 1000);

  /* ---------- Hero parallax (pointer devices only) ---------- */
  const stage = doc.querySelector('[data-parallax]');
  if (stage && !reduceMotion && window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
    let raf = 0, tx = 0, ty = 0;
    window.addEventListener('pointermove', (e) => {
      const r = stage.getBoundingClientRect();
      if (!r.width) return;
      tx = ((e.clientX - (r.left + r.width / 2)) / r.width) * 22;
      ty = ((e.clientY - (r.top + r.height / 2)) / r.height) * 22;
      if (!raf) raf = requestAnimationFrame(() => {
        stage.style.setProperty('--mx', tx.toFixed(2));
        stage.style.setProperty('--my', ty.toFixed(2));
        raf = 0;
      });
    }, { passive: true });
  }

  /* ---------- Animated counters ---------- */
  const counters = doc.querySelectorAll('[data-count]');
  if (counters.length) {
    const run = (el) => {
      const target = parseFloat(el.dataset.count);
      const prefix = el.dataset.prefix || '';
      const suffix = el.dataset.suffix || '';
      if (reduceMotion || Number.isNaN(target)) { el.textContent = prefix + target + suffix; return; }
      const dur = 1400, start = performance.now();
      const tick = (now) => {
        const p = Math.min(1, (now - start) / dur);
        const eased = 1 - Math.pow(1 - p, 3);
        el.textContent = prefix + Math.round(target * eased) + suffix;
        if (p < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    };
    if ('IntersectionObserver' in window) {
      const io = new IntersectionObserver((entries) => entries.forEach((en) => {
        if (en.isIntersecting) { run(en.target); io.unobserve(en.target); }
      }), { threshold: 0.4 });
      counters.forEach((el) => io.observe(el));
    } else {
      counters.forEach(run);
    }
  }

  /* ---------- Sub-navigation scroll spy ---------- */
  const spy = doc.querySelector('[data-spy]');
  if (spy && 'IntersectionObserver' in window) {
    const links = [...spy.querySelectorAll('a[href^="#"]')];
    const targets = links.map((a) => doc.getElementById(a.getAttribute('href').slice(1))).filter(Boolean);
    const setActive = (id) => links.forEach((a) => a.classList.toggle('is-active', a.getAttribute('href') === '#' + id));
    const update = () => {
      const line = window.innerHeight * 0.38;
      let current = '';
      for (const t of targets) { if (t.getBoundingClientRect().top <= line) current = t.id; }
      setActive(current);
    };
    let ticking = false;
    window.addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(() => { update(); ticking = false; }); } }, { passive: true });
    update();
  }

  /* ---------- Seasonal produce guide ----------
     A New England produce calendar. "local" marks items that are grown in
     Massachusetts or nearby when in season. Months are 1–12. */
  const SEASON = [
    { name: 'Strawberries', icon: 'i-strawberry', months: [5, 6, 7], peak: [6], local: true, note: 'Local berries arrive in June and go fast.' },
    { name: 'Blueberries', icon: 'i-blueberry', months: [6, 7, 8], peak: [7, 8], local: true, note: 'New England highbush, sweetest in late July.' },
    { name: 'Raspberries', icon: 'i-cherries', months: [6, 7, 8, 9], peak: [7], local: true, note: 'A short, fragrant window in July.' },
    { name: 'Cherries', icon: 'i-cherries', months: [6, 7], peak: [7], local: false, note: 'Dark, sweet, and gone by August.' },
    { name: 'Peaches', icon: 'i-peach', months: [7, 8, 9], peak: [8], local: true, note: 'Tree-ripened; eat over the sink.' },
    { name: 'Nectarines & plums', icon: 'i-peach', months: [7, 8, 9], peak: [8], local: false, note: 'Stone-fruit season at full tilt.' },
    { name: 'Sweet corn', icon: 'i-corn', months: [7, 8, 9], peak: [8], local: true, note: 'Picked in the morning, in the bin by noon.' },
    { name: 'Tomatoes', icon: 'i-tomato', months: [7, 8, 9, 10], peak: [8, 9], local: true, note: 'Heirlooms, beefsteaks, and cherry tomatoes at their best.' },
    { name: 'Summer squash', icon: 'i-pepper', months: [6, 7, 8, 9], peak: [7, 8], local: true, note: 'Zucchini and yellow squash, all summer long.' },
    { name: 'Cucumbers', icon: 'i-pepper', months: [7, 8, 9], peak: [8], local: true, note: 'Crisp and cool, straight from local fields.' },
    { name: 'Peppers', icon: 'i-pepper', months: [8, 9, 10], peak: [9], local: true, note: 'Bells and sweet peppers ripen with the late sun.' },
    { name: 'Melons', icon: 'i-melon', months: [7, 8, 9], peak: [8], local: true, note: 'Watermelon and cantaloupe, heavy for their size.' },
    { name: 'Asparagus', icon: 'i-asparagus', months: [4, 5, 6], peak: [5], local: true, note: 'The first true sign of spring on the South Shore.' },
    { name: 'Rhubarb', icon: 'i-asparagus', months: [4, 5, 6], peak: [5], local: true, note: 'Tart stalks for pies and compotes.' },
    { name: 'Fiddleheads & ramps', icon: 'i-leaf', months: [4, 5], peak: [5], local: true, note: 'Foraged New England specialties, here for a few weeks.' },
    { name: 'Peas', icon: 'i-leaf', months: [6, 7], peak: [6], local: true, note: 'Shell, snap, and snow peas.' },
    { name: 'Salad greens', icon: 'i-leaf', months: [4, 5, 6, 7, 8, 9, 10], peak: [5, 6, 9], local: true, note: 'Tender lettuces and spring mixes from nearby farms.' },
    { name: 'Spinach & kale', icon: 'i-leaf', months: [4, 5, 6, 9, 10, 11, 12], peak: [5, 10], local: true, note: 'Sweeter after the first frost.' },
    { name: 'Radishes', icon: 'i-radish', months: [5, 6, 9, 10], peak: [5], local: true, note: 'Peppery, crunchy, and quick.' },
    { name: 'Broccoli & cauliflower', icon: 'i-broccoli', months: [6, 7, 9, 10, 11], peak: [10], local: true, note: 'Tight heads from cool autumn fields.' },
    { name: 'Brussels sprouts', icon: 'i-broccoli', months: [10, 11, 12], peak: [11], local: true, note: 'Best still on the stalk.' },
    { name: 'Apples', icon: 'i-apple', months: [9, 10, 11, 12, 1, 2], peak: [9, 10], local: true, note: 'Macoun, Honeycrisp, Cortland: New England orchard season.' },
    { name: 'Pears', icon: 'i-pear', months: [9, 10, 11, 12], peak: [10], local: true, note: 'Bartlett and Bosc, ripened at home.' },
    { name: 'Concord grapes', icon: 'i-grapes', months: [9, 10], peak: [9], local: true, note: 'A Massachusetts original, first grown in Concord.' },
    { name: 'Table grapes', icon: 'i-grapes', months: [8, 9, 10, 11], peak: [9, 10], local: false, note: 'Crisp and seedless through the fall.' },
    { name: 'Cranberries', icon: 'i-cherries', months: [9, 10, 11], peak: [10, 11], local: true, note: 'Fresh from Massachusetts bogs for the holidays.' },
    { name: 'Winter squash & pumpkins', icon: 'i-pumpkin', months: [9, 10, 11, 12], peak: [10], local: true, note: 'Butternut, acorn, delicata, and sugar pumpkins.' },
    { name: 'Sweet potatoes', icon: 'i-potato', months: [10, 11, 12, 1], peak: [11], local: false, note: 'Thanksgiving essentials.' },
    { name: 'Potatoes', icon: 'i-potato', months: [8, 9, 10, 11, 12, 1, 2], peak: [9, 10], local: true, note: 'New potatoes in late summer, storage crops through winter.' },
    { name: 'Root vegetables', icon: 'i-carrot', months: [9, 10, 11, 12, 1, 2, 3], peak: [10, 11], local: true, note: 'Carrots, beets, parsnips, and turnips.' },
    { name: 'Leeks & onions', icon: 'i-leaf', months: [8, 9, 10, 11, 12], peak: [10], local: true, note: 'The base of every fall soup.' },
    { name: 'Figs', icon: 'i-plum', months: [8, 9, 10], peak: [9], local: false, note: 'Fragile and worth it.' },
    { name: 'Pomegranates', icon: 'i-plum', months: [10, 11, 12, 1], peak: [11, 12], local: false, note: 'Jewel-red arils for winter salads.' },
    { name: 'Clementines', icon: 'i-orange', months: [11, 12, 1, 2], peak: [12, 1], local: false, note: 'Crates of easy-peelers all winter.' },
    { name: 'Navel oranges', icon: 'i-orange', months: [11, 12, 1, 2, 3, 4], peak: [12, 1, 2], local: false, note: 'Citrus season is winter’s bright spot.' },
    { name: 'Blood oranges', icon: 'i-orange', months: [1, 2, 3], peak: [2], local: false, note: 'Berry-tinged and short-lived.' },
    { name: 'Grapefruit', icon: 'i-orange', months: [11, 12, 1, 2, 3, 4], peak: [1, 2], local: false, note: 'Ruby red at its juiciest.' },
    { name: 'Meyer lemons', icon: 'i-lemon', months: [12, 1, 2, 3], peak: [1, 2], local: false, note: 'Sweeter, thinner-skinned, a little floral.' },
    { name: 'Artichokes', icon: 'i-leaf', months: [3, 4, 5], peak: [4], local: false, note: 'Spring’s slowest, most rewarding vegetable.' },
    { name: 'Mangoes', icon: 'i-peach', months: [3, 4, 5, 6, 7], peak: [5, 6], local: false, note: 'Honey mangoes at their sweetest in late spring.' },
    { name: 'Pineapple', icon: 'i-lemon', months: [3, 4, 5, 6], peak: [4, 5], local: false, note: 'Golden and fragrant in spring.' },
    { name: 'Avocados', icon: 'i-pear', months: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], peak: [2, 3, 4], local: false, note: 'Year-round; we ripen them in-store.' },
    { name: 'Bananas', icon: 'i-lemon', months: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], peak: [], local: false, note: 'Every day of the year.' },
    { name: 'Mushrooms', icon: 'i-potato', months: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], peak: [10, 11], local: true, note: 'Local growers, year-round.' }
  ];
  const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

  const icon = (id, cls = '') => `<svg class="${cls}" aria-hidden="true" focusable="false"><use href="#${id}"></use></svg>`;

  doc.querySelectorAll('[data-season]').forEach((root) => {
    const monthsEl = root.querySelector('[data-season-months]');
    const gridEl = root.querySelector('[data-season-grid]');
    const summaryEl = root.querySelector('[data-season-summary]');
    const limit = parseInt(root.dataset.seasonLimit || '0', 10);
    if (!gridEl) return;

    let current = new Date().getMonth() + 1;

    const render = () => {
      const items = SEASON
        .filter((it) => it.months.includes(current))
        .sort((a, b) => {
          const ap = a.peak.includes(current) ? 0 : 1, bp = b.peak.includes(current) ? 0 : 1;
          if (ap !== bp) return ap - bp;
          if (a.local !== b.local) return a.local ? -1 : 1;
          return 0;
        });
      const shown = limit ? items.slice(0, limit) : items;
      const peakCount = items.filter((it) => it.peak.includes(current)).length;
      const localCount = items.filter((it) => it.local).length;

      gridEl.innerHTML = shown.map((it, i) => {
        const isPeak = it.peak.includes(current);
        const tags = [
          isPeak ? '<span class="tag tag--peak">Peak</span>' : '',
          it.local ? '<span class="tag tag--local">Local</span>' : ''
        ].join('');
        return `<article class="produce-tile" style="--i:${i}">
          ${icon(it.icon)}
          <div>
            <div class="produce-tile__name">${it.name}</div>
            <div class="produce-tile__note">${it.note}</div>
          </div>
          ${tags ? `<div class="produce-tile__tags">${tags}</div>` : ''}
        </article>`;
      }).join('') || '<p class="season__empty">Nothing to show for this month yet.</p>';

      if (summaryEl) {
        const names = items.filter((it) => it.peak.includes(current)).slice(0, 3).map((it) => it.name.toLowerCase());
        const lead = names.length
          ? `In <strong>${MONTHS[current - 1]}</strong>, ${peakCount} things are at their peak, including ${names.join(', ')}.`
          : `In <strong>${MONTHS[current - 1]}</strong>, ${items.length} things are in their season.`;
        summaryEl.innerHTML = `${lead} ${localCount ? `${localCount} of them can be grown right here in New England.` : ''}`;
      }
      if (monthsEl) {
        monthsEl.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(parseInt(b.dataset.month, 10) === current)));
      }
    };

    if (monthsEl) {
      monthsEl.innerHTML = MONTHS.map((m, i) =>
        `<button type="button" class="chip" data-month="${i + 1}" aria-pressed="false">${m.slice(0, 3)}</button>`).join('');
      monthsEl.addEventListener('click', (e) => {
        const b = e.target.closest('button[data-month]');
        if (!b) return;
        current = parseInt(b.dataset.month, 10);
        render();
      });
    }
    render();
  });

  /* ---------- Footer year ---------- */
  doc.querySelectorAll('[data-year]').forEach((el) => { el.textContent = String(new Date().getFullYear()); });
})();
