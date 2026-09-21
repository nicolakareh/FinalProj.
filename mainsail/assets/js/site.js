/* Mainsail Consulting Group — site.js (v2)
   Progressive enhancement only: the site is fully usable without it. */
(() => {
  'use strict';
  const d = document;
  d.documentElement.classList.add('js');
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const fine = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  const $ = (s, r = d) => r.querySelector(s);
  const $$ = (s, r = d) => Array.from(r.querySelectorAll(s));

  /* ---------- Smooth scrolling (Lenis, vendored) ---------- */
  let lenis = null;
  if (window.Lenis && !reduce && fine) {
    lenis = new window.Lenis({ lerp: 0.09, wheelMultiplier: 1, smoothWheel: true });
    const raf = (t) => { lenis.raf(t); requestAnimationFrame(raf); };
    requestAnimationFrame(raf);
  }
  const scrollTo = (target) => {
    if (lenis) lenis.scrollTo(target, { offset: -24, duration: 1.4 });
    else target.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  };
  // in-page anchors
  $$('a[href^="#"], a[href*="index.html#"]').forEach(a => {
    a.addEventListener('click', (e) => {
      const hash = a.getAttribute('href').split('#')[1];
      const path = a.getAttribute('href').split('#')[0];
      if (!hash || (path && !location.pathname.endsWith(path.replace('../', '')))) return;
      const el = d.getElementById(hash);
      if (!el) return;
      e.preventDefault(); scrollTo(el); history.replaceState(null, '', '#' + hash);
    });
  });

  /* ---------- Floating header: hide on scroll down, adapt to light sections ---------- */
  const header = $('.header');
  const darkZones = $$('.hero, .page-hero, .statement, .approach, .footer');
  let lastY = window.scrollY, ticking = false;
  const onScroll = () => {
    const y = window.scrollY;
    if (!header.classList.contains('menu-open')) header.classList.toggle('is-hidden', y > lastY && y > 400);
    const probe = 40; // y-position of the nav centre
    const onDark = darkZones.some(z => { const r = z.getBoundingClientRect(); return r.top <= probe && r.bottom >= probe; });
    header.classList.toggle('on-light', !onDark);
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
      if (lenis) open ? lenis.stop() : lenis.start();
      if (open) header.classList.remove('is-hidden');
    };
    toggle.addEventListener('click', () => setOpen(toggle.getAttribute('aria-expanded') !== 'true'));
    $$('a', nav).forEach(a => a.addEventListener('click', () => setOpen(false)));
    d.addEventListener('keydown', e => { if (e.key === 'Escape') setOpen(false); });
  }

  /* ---------- Reveal on scroll ---------- */
  const io = new IntersectionObserver((entries) => {
    entries.forEach(en => { if (en.isIntersecting) { en.target.classList.add('is-in'); io.unobserve(en.target); } });
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0.06 });
  $$('[data-reveal], .lines, .phases').forEach(el => io.observe(el));

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

  /* ---------- Sticky stack: scale cards as the next one covers them ---------- */
  const cards = $$('.stack .card');
  if (cards.length && !reduce && window.matchMedia('(min-width: 901px)').matches) {
    const update = () => {
      const top = parseFloat(getComputedStyle(cards[0]).top) || 100;
      cards.forEach((c, i) => {
        const next = cards[i + 1]; if (!next) return;
        const r = next.getBoundingClientRect();
        const p = Math.min(1, Math.max(0, 1 - (r.top - top) / (window.innerHeight * 0.8)));
        c.style.transform = `scale(${1 - p * 0.05 * (1)}) translateY(${-p * 10}px)`;
        c.style.filter = `brightness(${1 - p * 0.12})`;
      });
    };
    window.addEventListener('scroll', () => requestAnimationFrame(update), { passive: true });
    update();
  }

  /* ---------- Parallax for full-bleed media ---------- */
  const px = $$('[data-parallax]');
  if (px.length && !reduce) {
    const update = () => {
      const vh = window.innerHeight;
      px.forEach(el => { const r = el.parentElement.getBoundingClientRect(); if (r.bottom < 0 || r.top > vh) return; const p = (r.top + r.height / 2 - vh / 2) / vh; el.style.transform = `translate3d(0, ${p * -9}%, 0)`; });
    };
    window.addEventListener('scroll', () => requestAnimationFrame(update), { passive: true });
    update();
  }

  /* ---------- Magnetic buttons ---------- */
  if (fine && !reduce) {
    $$('.btn').forEach(btn => {
      btn.addEventListener('pointermove', (e) => {
        const r = btn.getBoundingClientRect();
        const x = (e.clientX - (r.left + r.width / 2)) / r.width, y = (e.clientY - (r.top + r.height / 2)) / r.height;
        btn.style.transform = `translate(${x * 10}px, ${y * 8}px)`;
      });
      btn.addEventListener('pointerleave', () => { btn.style.transform = ''; });
    });
  }

  /* ---------- Marquee: duplicate content for a seamless loop ---------- */
  $$('.marquee__track').forEach(track => { const g = $('.marquee__group', track); if (g && track.children.length === 1) track.appendChild(g.cloneNode(true)); });

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
      if (url.origin !== location.origin || url.protocol === 'mailto:' || (url.pathname === location.pathname)) return;
      e.preventDefault(); veil.classList.remove('is-in'); veil.classList.add('is-out');
      setTimeout(() => { location.href = url.href; }, 520);
    });
    window.addEventListener('pageshow', (e) => { if (e.persisted) { veil.classList.remove('is-out'); veil.classList.add('is-in'); } });
  }

  $$('[data-year]').forEach(el => { el.textContent = new Date().getFullYear(); });
})();
