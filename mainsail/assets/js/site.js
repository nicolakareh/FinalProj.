/* Mainsail Consulting Group — site.js (v5)
   Progressive enhancement only: the site is fully usable without it. */
(() => {
  'use strict';
  const d = document;
  d.documentElement.classList.add('js');
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const $ = (s, r = d) => r.querySelector(s);
  const $$ = (s, r = d) => Array.from(r.querySelectorAll(s));

  /* ---------- Header: soft shadow once the page has scrolled ---------- */
  const header = $('.header');
  let ticking = false;
  const onScroll = () => { header.classList.toggle('is-scrolled', window.scrollY > 8); ticking = false; };
  window.addEventListener('scroll', () => { if (!ticking) { requestAnimationFrame(onScroll); ticking = true; } }, { passive: true });
  onScroll();

  /* ---------- Mobile nav ---------- */
  const toggle = $('.nav-toggle'), nav = $('.nav');
  if (toggle && nav) {
    const setOpen = (open) => {
      toggle.setAttribute('aria-expanded', String(open));
      nav.classList.toggle('is-open', open);
      d.documentElement.style.overflow = open ? 'hidden' : '';
    };
    toggle.addEventListener('click', () => setOpen(toggle.getAttribute('aria-expanded') !== 'true'));
    $$('a', nav).forEach(a => a.addEventListener('click', () => setOpen(false)));
    d.addEventListener('keydown', e => { if (e.key === 'Escape') setOpen(false); });
    window.matchMedia('(min-width: 901px)').addEventListener('change', e => { if (e.matches) setOpen(false); });
  }

  /* ---------- Reveal on scroll ---------- */
  const io = new IntersectionObserver((entries) => {
    entries.forEach(en => { if (!en.isIntersecting) return; en.target.classList.add('is-in'); io.unobserve(en.target); });
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0.05 });
  $$('[data-reveal], .phases').forEach(el => io.observe(el));

  /* ---------- Count-up numbers ---------- */
  const ease = t => 1 - Math.pow(1 - t, 4);
  const countIO = new IntersectionObserver((entries) => {
    entries.forEach(en => {
      if (!en.isIntersecting) return;
      const el = en.target, end = parseFloat(el.dataset.count), dur = reduce ? 0 : 1400, start = performance.now();
      const step = (now) => { const p = dur ? Math.min(1, (now - start) / dur) : 1; el.textContent = Math.round(end * ease(p)).toString(); if (p < 1) requestAnimationFrame(step); };
      requestAnimationFrame(step); countIO.unobserve(el);
    });
  }, { threshold: 0.5 });
  $$('[data-count]').forEach(el => countIO.observe(el));

  /* ---------- Hero video: load after paint, only when it makes sense ---------- */
  const hv = $('.hero__video');
  const saveData = navigator.connection && navigator.connection.saveData;
  if (hv && hv.dataset.mp4 && !reduce && !saveData) {
    const start = () => {
      const webm = hv.canPlayType('video/webm; codecs="vp9"') && hv.dataset.webm;
      let src = webm || hv.dataset.mp4;
      if (window.matchMedia('(max-width: 900px)').matches) src = src.replace('hero.', 'hero-720.');
      hv.src = src; hv.load();
      hv.addEventListener('playing', () => hv.classList.add('is-playing'), { once: true });
      hv.play().catch(() => {});
    };
    (window.requestIdleCallback || ((f) => setTimeout(f, 800)))(start);
    // pause when the hero leaves the viewport
    new IntersectionObserver((en) => { en.forEach(e => { if (!hv.src) return; e.isIntersecting ? hv.play().catch(() => {}) : hv.pause(); }); }, { threshold: 0.05 }).observe(hv);
  }

  /* ---------- Gentle parallax for the full-bleed statement image ---------- */
  const px = $$('[data-parallax]');
  if (px.length && !reduce) {
    const update = () => {
      const vh = window.innerHeight;
      px.forEach(el => { const r = el.parentElement.getBoundingClientRect(); if (r.bottom < 0 || r.top > vh) return; const p = (r.top + r.height / 2 - vh / 2) / vh; el.style.transform = `translate3d(0, ${p * -6}%, 0)`; });
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

  /* ---------- Back to top ---------- */
  $$('.footer__top').forEach(a => a.addEventListener('click', (e) => { e.preventDefault(); window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' }); }));

  $$('[data-year]').forEach(el => { el.textContent = new Date().getFullYear(); });
})();
