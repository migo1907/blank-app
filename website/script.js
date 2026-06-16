/* =========================================================
   Global Markets — script.js
   Lightweight, dependency-free interactivity.
   (Quotes are simulated for demo; wire to a real feed later.)
   ========================================================= */
(function () {
  'use strict';

  /* ---------- Footer year ---------- */
  var yr = document.getElementById('year');
  if (yr) yr.textContent = new Date().getFullYear();

  /* ---------- Sticky header shadow ---------- */
  var header = document.querySelector('.site-header');
  var onScroll = function () {
    if (header) header.classList.toggle('scrolled', window.scrollY > 8);
    var toTop = document.getElementById('to-top');
    if (toTop) toTop.classList.toggle('show', window.scrollY > 500);
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  /* ---------- Mobile nav ---------- */
  var toggle = document.getElementById('nav-toggle');
  var links = document.getElementById('nav-links');
  if (toggle && links) {
    toggle.addEventListener('click', function () {
      var open = links.classList.toggle('open');
      toggle.setAttribute('aria-expanded', String(open));
      toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    });
    links.addEventListener('click', function (e) {
      if (e.target.tagName === 'A') {
        links.classList.remove('open');
        toggle.setAttribute('aria-expanded', 'false');
      }
    });
  }

  /* ---------- Scroll reveal + chart draw (IntersectionObserver) ---------- */
  var revealEls = document.querySelectorAll('.reveal, .split-media');
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('in-view');
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15, rootMargin: '0px 0px -40px 0px' });
    revealEls.forEach(function (el) { io.observe(el); });
  } else {
    revealEls.forEach(function (el) { el.classList.add('in-view'); });
  }

  /* ---------- Count-up stats ---------- */
  var counters = document.querySelectorAll('.stat-num');
  var animateCount = function (el) {
    var target = parseFloat(el.getAttribute('data-count')) || 0;
    var dur = 1600, start = null;
    var fmt = function (n) { return Math.round(n).toLocaleString('en-US'); };
    var step = function (ts) {
      if (!start) start = ts;
      var p = Math.min((ts - start) / dur, 1);
      var eased = 1 - Math.pow(1 - p, 3); // easeOutCubic
      el.textContent = fmt(target * eased);
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };
  if ('IntersectionObserver' in window) {
    var cio = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) { animateCount(entry.target); cio.unobserve(entry.target); }
      });
    }, { threshold: 0.6 });
    counters.forEach(function (c) { cio.observe(c); });
  } else {
    counters.forEach(function (c) { c.textContent = (parseFloat(c.getAttribute('data-count')) || 0).toLocaleString('en-US'); });
  }

  /* ---------- Market data (simulated demo feed) ---------- */
  var instruments = [
    { sym: 'XAUUSD', price: 3287.40, dp: 2 },
    { sym: 'EURUSD', price: 1.0842, dp: 4 },
    { sym: 'GBPUSD', price: 1.2710, dp: 4 },
    { sym: 'USDJPY', price: 157.32, dp: 2 },
    { sym: 'BTCUSD', price: 67310, dp: 0 },
    { sym: 'ETHUSD', price: 3512, dp: 0 },
    { sym: 'NAS100', price: 19480, dp: 1 },
    { sym: 'US500', price: 5421.6, dp: 1 },
    { sym: 'WTI',    price: 78.45, dp: 2 },
    { sym: 'GER40',  price: 18230, dp: 1 }
  ];
  instruments.forEach(function (it) { it.base = it.price; it.chg = (Math.random() * 2 - 1); });

  var fmtPrice = function (it) {
    return it.price.toLocaleString('en-US', { minimumFractionDigits: it.dp, maximumFractionDigits: it.dp });
  };

  /* Build live quote list (hero card) */
  var quoteList = document.getElementById('quote-list');
  var quoteRows = {};
  if (quoteList) {
    instruments.slice(0, 6).forEach(function (it) {
      var li = document.createElement('li');
      li.className = 'quote-row';
      li.innerHTML =
        '<span class="quote-sym">' + it.sym + '</span>' +
        '<span class="quote-price">' + fmtPrice(it) + '</span>' +
        '<span class="quote-chg ' + (it.chg >= 0 ? 'up' : 'down') + '">' +
          (it.chg >= 0 ? '+' : '') + it.chg.toFixed(2) + '%</span>';
      quoteList.appendChild(li);
      quoteRows[it.sym] = li;
    });
  }

  /* Build ticker (duplicated for seamless loop) */
  var tickerTrack = document.getElementById('ticker-track');
  var buildTicker = function () {
    if (!tickerTrack) return;
    var html = instruments.map(function (it) {
      return '<span class="ticker-item"><b>' + it.sym + '</b> ' + fmtPrice(it) +
        ' <span class="' + (it.chg >= 0 ? 'up' : 'down') + '">' +
        (it.chg >= 0 ? '▲' : '▼') + ' ' + Math.abs(it.chg).toFixed(2) + '%</span></span>';
    }).join('');
    tickerTrack.innerHTML = html + html; // duplicate => seamless marquee
  };
  buildTicker();

  /* Tick: nudge prices, update DOM, flash on change */
  var tick = function () {
    instruments.forEach(function (it) {
      var vol = it.base * 0.0006;
      it.price = Math.max(0, it.price + (Math.random() * 2 - 1) * vol);
      it.chg = ((it.price - it.base) / it.base) * 100;

      var row = quoteRows[it.sym];
      if (row) {
        var priceEl = row.querySelector('.quote-price');
        var chgEl = row.querySelector('.quote-chg');
        priceEl.textContent = fmtPrice(it);
        chgEl.textContent = (it.chg >= 0 ? '+' : '') + it.chg.toFixed(2) + '%';
        chgEl.className = 'quote-chg ' + (it.chg >= 0 ? 'up' : 'down');
        var cls = it.chg >= 0 ? 'flash-up' : 'flash-down';
        chgEl.classList.remove('flash-up', 'flash-down');
        void chgEl.offsetWidth; // restart animation
        chgEl.classList.add(cls);
      }
    });
    buildTicker();
  };

  // Only run the live sim when the tab is visible (saves CPU/battery).
  var timer = null;
  var startTicks = function () { if (!timer) timer = setInterval(tick, 2000); };
  var stopTicks = function () { if (timer) { clearInterval(timer); timer = null; } };
  document.addEventListener('visibilitychange', function () {
    document.hidden ? stopTicks() : startTicks();
  });
  startTicks();

  /* ---------- Contact form (client-side validation demo) ---------- */
  var form = document.getElementById('contact-form');
  var status = document.getElementById('form-status');
  if (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var name = form.name.value.trim();
      var email = form.email.value.trim();
      var msg = form.message.value.trim();
      var emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);

      if (!name || !emailOk || !msg) {
        status.textContent = 'Please fill in all fields with a valid email.';
        status.className = 'form-status err';
        return;
      }
      // No backend yet — wire this to your endpoint / email service.
      status.textContent = 'Thanks, ' + name + '! Your message has been queued. We\'ll reply by email.';
      status.className = 'form-status ok';
      form.reset();
    });
  }
})();
