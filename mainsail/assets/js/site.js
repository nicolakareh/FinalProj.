/* Mainsail Consulting Group — site.js (v3)
   Progressive enhancement only: the site is fully usable without it. */
(() => {
  'use strict';
  const d = document;
  d.documentElement.classList.add('js');
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const fine = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  const $ = (s, r = d) => r.querySelector(s);
  const $$ = (s, r = d) => Array.from(r.querySelectorAll(s));

  /* ---------- Header: blur on scroll, hide on scroll down ---------- */
  const header = $('.header');
  let lastY = window.scrollY, ticking = false;
  const onScroll = () => {
    const y = window.scrollY;
    header.classList.toggle('is-scrolled', y > 24);
    if (!header.classList.contains('menu-open')) header.classList.toggle('is-hidden', y > lastY && y > 360);
    lastY = y; ticking = false;
  };
  window.addEventListener('scroll', () => { if (!ticking) { requestAnimationFrame(onScroll); ticking = true; } }, { passive: true });
  onScroll();

  /* ---------- Mobile nav ---------- */
  const toggle = $('.nav-toggle'), nav = $('.nav');
  if (toggle && nav) {
    const setOpen = (open) => {
      toggle.setAttribute('aria-expanded', String(open));
      nav.classList.toggle('is-open', open);
      header.classList.toggle('menu-open', open);
      d.documentElement.style.overflow = open ? 'hidden' : '';
      if (open) header.classList.remove('is-hidden');
    };
    toggle.addEventListener('click', () => setOpen(toggle.getAttribute('aria-expanded') !== 'true'));
    $$('a', nav).forEach(a => a.addEventListener('click', () => setOpen(false)));
    d.addEventListener('keydown', e => { if (e.key === 'Escape') setOpen(false); });
  }

  /* ---------- Reveal on scroll (text, images, hairlines, timeline) ---------- */
  const io = new IntersectionObserver((entries) => {
    entries.forEach(en => {
      if (!en.isIntersecting) return;
      en.target.classList.add('is-in');
      $$('.reveal-img', en.target).forEach(c => c.classList.add('is-in')); // masked images inside
      io.unobserve(en.target);
    });
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0.06 });
  $$('[data-reveal], .lines, .phases, .rule[data-draw]').forEach(el => io.observe(el));
  // a fully clipped element never intersects, so masked images are driven by their parent
  $$('.reveal-img').forEach(el => io.observe(el.parentElement));

  /* ---------- Count-up numbers ---------- */
  const ease = t => 1 - Math.pow(1 - t, 4);
  const countIO = new IntersectionObserver((entries) => {
    entries.forEach(en => {
      if (!en.isIntersecting) return;
      const el = en.target, end = parseFloat(el.dataset.count), dur = reduce ? 0 : 1600, start = performance.now();
      const step = (now) => { const p = dur ? Math.min(1, (now - start) / dur) : 1; el.textContent = Math.round(end * ease(p)).toString(); if (p < 1) requestAnimationFrame(step); };
      requestAnimationFrame(step); countIO.unobserve(el);
    });
  }, { threshold: 0.6 });
  $$('[data-count]').forEach(el => countIO.observe(el));

  /* ---------- Services: sticky preview follows hover (desktop) or scroll (touch) ---------- */
  const list = $('.svc-list'), preview = $('.preview');
  if (list && preview) {
    const pics = $$('picture[data-key]', preview), cap = $('[data-cap]', preview), rows = $$('.svc', list);
    const show = (key, title) => {
      pics.forEach(p => p.classList.toggle('is-active', p.dataset.key === key));
      if (cap && title) cap.textContent = title;
    };
    if (fine) {
      rows.forEach(row => row.addEventListener('pointerenter', () => show(row.dataset.img, $('.svc__title', row).textContent)));
    }
    // while scrolling, the row nearest the middle of the viewport drives the preview
    let raf = null;
    const track = () => {
      raf = null;
      const mid = window.innerHeight * 0.5; let best = null, bestD = Infinity;
      rows.forEach(r => { const b = r.getBoundingClientRect(); const c = b.top + b.height / 2; const dd = Math.abs(c - mid); if (dd < bestD) { bestD = dd; best = r; } });
      if (best && !list.matches(':hover')) show(best.dataset.img, $('.svc__title', best).textContent);
    };
    window.addEventListener('scroll', () => { if (!raf) raf = requestAnimationFrame(track); }, { passive: true });
  }

  /* ---------- Hero video: load after paint, only when it makes sense ---------- */
  const hv = $('.hero__video');
  const saveData = navigator.connection && navigator.connection.saveData;
  if (hv && hv.dataset.src && !reduce && !saveData) {
    const start = () => {
      hv.src = window.matchMedia('(max-width: 900px)').matches ? hv.dataset.src.replace('hero.mp4', 'hero-720.mp4') : hv.dataset.src; hv.load();
      hv.addEventListener('playing', () => hv.classList.add('is-playing'), { once: true });
      hv.play().catch(() => {});
    };
    (window.requestIdleCallback || ((f) => setTimeout(f, 800)))(start);
    // pause when the hero leaves the viewport
    new IntersectionObserver((en) => { en.forEach(e => { if (!hv.src) return; e.isIntersecting ? hv.play().catch(() => {}) : hv.pause(); }); }, { threshold: 0.05 }).observe(hv);
  }

  /* ---------- Parallax for full-bleed media ---------- */
  const px = $$('[data-parallax]');
  if (px.length && !reduce) {
    const update = () => {
      const vh = window.innerHeight;
      px.forEach(el => { const r = el.parentElement.getBoundingClientRect(); if (r.bottom < 0 || r.top > vh) return; const p = (r.top + r.height / 2 - vh / 2) / vh; el.style.transform = `translate3d(0, ${p * -8}%, 0)`; });
    };
    window.addEventListener('scroll', () => requestAnimationFrame(update), { passive: true });
    update();
  }

  /* ---------- Contact form ---------- */
  const form = $('.form');
  if (form) {
    const status = $('.form__status', form);
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const hp = $('.hp input', form); if (hp && hp.value) return;
      const data = Object.fromEntries(new FormData(form).entries());
      const endpoint = form.dataset.endpoint, btn = $('button[type="submit"]', form);
      btn.disabled = true; status.textContent = 'Sending…';
      try {
        if (endpoint) {
          const res = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' }, body: JSON.stringify(data) });
          if (!res.ok) throw new Error('Request failed');
          status.textContent = 'Thanks for submitting! We will be in touch shortly.'; form.reset();
        } else {
          const subject = encodeURIComponent(`Project enquiry from ${data.firstName || ''} ${data.lastName || ''}`.trim());
          const body = encodeURIComponent(`${data.message || ''}\n\n— ${data.firstName || ''} ${data.lastName || ''}\n${data.email || ''}`);
          window.location.href = `mailto:info@bymainsail.com?subject=${subject}&body=${body}`;
          status.textContent = 'Opening your email client… If nothing happens, write to info@bymainsail.com.';
        }
      } catch (err) { status.textContent = 'Something went wrong. Please email info@bymainsail.com directly.'; }
      finally { btn.disabled = false; }
    });
  }

  /* ---------- Page transitions ---------- */
  const veil = $('.veil');
  if (veil && !reduce) {
    requestAnimationFrame(() => veil.classList.add('is-in'));
    d.addEventListener('click', (e) => {
      const a = e.target.closest('a[href]');
      if (!a || a.target === '_blank' || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const url = new URL(a.href, location.href);
      if (url.origin !== location.origin || url.protocol === 'mailto:' || url.pathname === location.pathname) return;
      e.preventDefault(); veil.classList.remove('is-in'); veil.classList.add('is-out');
      setTimeout(() => { location.href = url.href; }, 520);
    });
    window.addEventListener('pageshow', (e) => { if (e.persisted) { veil.classList.remove('is-out'); veil.classList.add('is-in'); } });
  }

  $$('[data-year]').forEach(el => { el.textContent = new Date().getFullYear(); });
})();
