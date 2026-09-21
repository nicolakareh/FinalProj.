/* Mainsail Consulting Group — site.js
   Progressive enhancement only: the site is fully usable without it. */
(() => {
  'use strict';
  const d = document;
  d.documentElement.classList.add('js');
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const $ = (s, r = d) => r.querySelector(s);
  const $$ = (s, r = d) => Array.from(r.querySelectorAll(s));

  /* ---------- Header: blur on scroll, hide on scroll down ---------- */
  const header = $('.header');
  let lastY = window.scrollY, ticking = false;
  const onScroll = () => {
    const y = window.scrollY;
    header.classList.toggle('is-scrolled', y > 24);
    if (!header.classList.contains('menu-open')) {
      header.classList.toggle('is-hidden', y > lastY && y > 320);
    }
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

  /* ---------- Reveal on scroll ---------- */
  const io = new IntersectionObserver((entries) => {
    entries.forEach(en => {
      if (en.isIntersecting) { en.target.classList.add('is-in'); io.unobserve(en.target); }
    });
  }, { rootMargin: '0px 0px -10% 0px', threshold: 0.08 });
  $$('[data-reveal], .lines, .phases').forEach(el => io.observe(el));

  /* ---------- Count-up numbers ---------- */
  const ease = t => 1 - Math.pow(1 - t, 4);
  const countIO = new IntersectionObserver((entries) => {
    entries.forEach(en => {
      if (!en.isIntersecting) return;
      const el = en.target, end = parseFloat(el.dataset.count), dur = reduce ? 0 : 1600;
      const start = performance.now();
      const step = (now) => {
        const p = dur ? Math.min(1, (now - start) / dur) : 1;
        el.textContent = Math.round(end * ease(p)).toString();
        if (p < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
      countIO.unobserve(el);
    });
  }, { threshold: 0.6 });
  $$('[data-count]').forEach(el => countIO.observe(el));

  /* ---------- Services: floating image follows the cursor ---------- */
  const list = $('.svc-list'), float = $('.svc-float');
  if (list && float && window.matchMedia('(hover: hover) and (pointer: fine)').matches && !reduce) {
    const imgs = $$('img', float);
    let x = 0, y = 0, tx = 0, ty = 0, raf = null;
    const loop = () => {
      x += (tx - x) * 0.12; y += (ty - y) * 0.12;
      float.style.left = x + 'px'; float.style.top = y + 'px';
      if (Math.abs(tx - x) > 0.2 || Math.abs(ty - y) > 0.2) raf = requestAnimationFrame(loop); else raf = null;
    };
    list.addEventListener('pointermove', e => {
      tx = e.clientX + 210; ty = e.clientY - 30;
      if (!raf) { if (!float.classList.contains('is-on')) { x = tx; y = ty; } raf = requestAnimationFrame(loop); }
    });
    $$('.svc', list).forEach(row => {
      row.addEventListener('pointerenter', () => {
        const key = row.dataset.img;
        imgs.forEach(i => i.classList.toggle('is-active', i.dataset.key === key));
        float.classList.add('is-on');
      });
    });
    list.addEventListener('pointerleave', () => float.classList.remove('is-on'));
  }

  /* ---------- Subtle parallax for full-bleed media ---------- */
  const px = $$('[data-parallax]');
  if (px.length && !reduce) {
    const update = () => {
      const vh = window.innerHeight;
      px.forEach(el => {
        const r = el.parentElement.getBoundingClientRect();
        if (r.bottom < 0 || r.top > vh) return;
        const p = (r.top + r.height / 2 - vh / 2) / vh;      // -1 … 1
        el.style.transform = `translate3d(0, ${p * -8}%, 0)`;
      });
    };
    window.addEventListener('scroll', () => requestAnimationFrame(update), { passive: true });
    update();
  }

  /* ---------- Marquee: duplicate content for a seamless loop ---------- */
  $$('.marquee__track').forEach(track => {
    const group = $('.marquee__group', track);
    if (group && track.children.length === 1) track.appendChild(group.cloneNode(true));
  });

  /* ---------- Contact form ---------- */
  const form = $('.form');
  if (form) {
    const status = $('.form__status', form);
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if ($('.hp input', form) && $('.hp input', form).value) return; // honeypot
      const data = Object.fromEntries(new FormData(form).entries());
      const endpoint = form.dataset.endpoint;
      const btn = $('button[type="submit"]', form);
      btn.disabled = true; status.textContent = 'Sending…';
      try {
        if (endpoint) {
          const res = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' }, body: JSON.stringify(data) });
          if (!res.ok) throw new Error('Request failed');
          status.textContent = 'Thanks for submitting! We will be in touch shortly.';
          form.reset();
        } else {
          // No endpoint configured yet: hand off to the visitor's mail client.
          const subject = encodeURIComponent(`Project enquiry from ${data.firstName || ''} ${data.lastName || ''}`.trim());
          const body = encodeURIComponent(`${data.message || ''}\n\n— ${data.firstName || ''} ${data.lastName || ''}\n${data.email || ''}`);
          window.location.href = `mailto:info@bymainsail.com?subject=${subject}&body=${body}`;
          status.textContent = 'Opening your email client… If nothing happens, write to info@bymainsail.com.';
        }
      } catch (err) {
        status.textContent = 'Something went wrong. Please email info@bymainsail.com directly.';
      } finally { btn.disabled = false; }
    });
  }

  /* ---------- Page transitions (internal links) ---------- */
  const veil = $('.veil');
  if (veil && !reduce) {
    requestAnimationFrame(() => veil.classList.add('is-in'));
    d.addEventListener('click', (e) => {
      const a = e.target.closest('a[href]');
      if (!a || a.target === '_blank' || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const url = new URL(a.href, location.href);
      if (url.origin !== location.origin || url.pathname === location.pathname || url.protocol === 'mailto:') return;
      if (a.hash && url.pathname === location.pathname) return;
      e.preventDefault();
      veil.classList.remove('is-in'); veil.classList.add('is-out');
      setTimeout(() => { location.href = url.href; }, 520);
    });
    window.addEventListener('pageshow', (e) => { if (e.persisted) { veil.classList.remove('is-out'); veil.classList.add('is-in'); } });
  }

  /* ---------- Current year ---------- */
  $$('[data-year]').forEach(el => { el.textContent = new Date().getFullYear(); });
})();
