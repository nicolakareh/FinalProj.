/* Flag Pharmacy — small, dependency-free behaviors. */
(function () {
  'use strict';

  // Mobile nav
  var header = document.querySelector('.site-header');
  var toggle = document.querySelector('.nav-toggle');
  if (toggle && header) {
    toggle.addEventListener('click', function () {
      var open = header.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', String(open));
    });
  }
  // Dropdown groups (click to open; hover handled in CSS on desktop)
  document.querySelectorAll('.has-menu').forEach(function (li) {
    var btn = li.querySelector('.site-nav__group');
    btn.addEventListener('click', function () {
      var open = li.classList.toggle('is-open');
      btn.setAttribute('aria-expanded', String(open));
    });
    if (li.hasAttribute('data-active') && window.matchMedia('(max-width: 979px)').matches) {
      li.classList.add('is-open'); btn.setAttribute('aria-expanded', 'true');
    }
  });
  document.addEventListener('click', function (e) {
    if (!e.target.closest('.has-menu')) {
      document.querySelectorAll('.has-menu.is-open').forEach(function (li) {
        if (window.matchMedia('(min-width: 980px)').matches) {
          li.classList.remove('is-open');
          li.querySelector('.site-nav__group').setAttribute('aria-expanded', 'false');
        }
      });
    }
  });

  // Open / closed status, computed in Eastern time. Edit HOURS if hours change.
  // Hours: [open, close] in 24h, by weekday (0 = Sunday). null = closed.
  var HOURS = {
    lynn:    [null, [9, 19], [9, 19], [9, 19], [9, 19], [9, 19], [9, 17]],
    chelsea: [null, [9, 19], [9, 19], [9, 19], [9, 19], [9, 19], [9, 17]]
  };
  var DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  function nowEastern() {
    var parts = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', weekday: 'short', hour: 'numeric', minute: 'numeric', hour12: false }).formatToParts(new Date());
    var o = {}; parts.forEach(function (p) { o[p.type] = p.value; });
    var wd = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].indexOf(o.weekday);
    return { day: wd, mins: (parseInt(o.hour, 10) % 24) * 60 + parseInt(o.minute, 10) };
  }
  function fmt(h) { var ap = h >= 12 ? 'pm' : 'am'; var hh = h % 12 || 12; return hh + ' ' + ap; }
  function status(store) {
    var t = nowEastern(), today = HOURS[store][t.day];
    if (today && t.mins >= today[0] * 60 && t.mins < today[1] * 60) return { open: true, text: 'Open now · closes ' + fmt(today[1]) };
    // find next opening
    for (var i = 0; i < 7; i++) {
      var d = (t.day + i) % 7, h = HOURS[store][d];
      if (!h) continue;
      if (i === 0 && t.mins < h[0] * 60) return { open: false, text: 'Closed · opens today at ' + fmt(h[0]) };
      if (i > 0) return { open: false, text: 'Closed · opens ' + (i === 1 ? 'tomorrow' : DAYS[d]) + ' at ' + fmt(h[0]) };
    }
    return { open: false, text: 'Closed' };
  }
  function paint() {
    document.querySelectorAll('[data-open-status]').forEach(function (el) {
      var s = status(el.getAttribute('data-store') || 'lynn');
      el.textContent = s.text; el.hidden = false;
      el.classList.toggle('is-open', s.open); el.classList.toggle('is-closed', !s.open);
    });
    var d = nowEastern().day;
    document.querySelectorAll('.hours li[data-day]').forEach(function (li) {
      li.classList.toggle('today', li.getAttribute('data-day').split(',').indexOf(String(d)) > -1);
    });
  }
  try { paint(); setInterval(paint, 60000); } catch (e) { /* leave static text */ }

  // Footer year
  document.querySelectorAll('[data-year]').forEach(function (el) { el.textContent = new Date().getFullYear(); });

  // Scroll reveal
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add('is-in'); io.unobserve(en.target); } });
    }, { rootMargin: '0px 0px -8% 0px' });
    document.querySelectorAll('[data-reveal]').forEach(function (el) { io.observe(el); });
  } else {
    document.querySelectorAll('[data-reveal]').forEach(function (el) { el.classList.add('is-in'); });
  }

  // Contact / ask-the-pharmacist forms: open the user's mail client (static site, no backend).
  document.querySelectorAll('form[data-mailto]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var fd = new FormData(form), body = [];
      fd.forEach(function (v, k) { if (k !== 'subject') body.push(k.replace(/_/g, ' ') + ': ' + v); });
      var subject = fd.get('subject') || form.getAttribute('data-subject') || 'Website message';
      window.location.href = 'mailto:' + form.getAttribute('data-mailto') + '?subject=' + encodeURIComponent(subject) + '&body=' + encodeURIComponent(body.join('\n'));
    });
  });
})();
