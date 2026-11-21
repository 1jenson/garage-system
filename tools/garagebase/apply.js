// Injected by serve.py after the mock's own script has run.  Replaces the demo
// seed arrays/objects in place with window.__localData (real GarageBase data
// served from private/local-data) and re-renders.  Contains no data itself.
(function () {
  var D = window.__localData;
  if (!D) { console.warn('local-data: nothing to apply'); return; }
  var t0 = performance.now();
  function fillArr(a, src) { a.length = 0; for (var i = 0; i < src.length; i++) a.push(src[i]); }
  function fillObj(o, src) { Object.keys(o).forEach(function (k) { delete o[k]; }); Object.assign(o, src); }
  function tryDo(label, fn) { try { fn(); } catch (e) { console.warn('local-data: ' + label + ' skipped: ' + e.message); } }

  // The mock hard-codes a few of its demo regs inside screen templates (home
  // "recent vehicles", tyre diary, bookings...).  Remember every reg the demo
  // seed knew about, and while a screen renders give any that has no real
  // vehicle a harmless placeholder so veh(reg).make etc. never throws.
  var demoRegs = {};
  tryDo('demo regs', function () {
    vehicles.forEach(function (v) { demoRegs[v.reg] = 1; });
    Object.keys(legacy).forEach(function (r) { demoRegs[r] = 1; });
    (JOBS || []).forEach(function (j) { demoRegs[j.r] = 1; });
    (QUOTES || []).forEach(function (q) { demoRegs[q.r] = 1; });
    (WL || []).forEach(function (w) { if (w.reg) demoRegs[w.reg] = 1; });
    Object.keys(BK || {}).forEach(function (d) { (BK[d] || []).forEach(function (b) { if (b.reg) demoRegs[b.reg] = 1; }); });
    Object.keys(TY || {}).forEach(function (d) { (TY[d] || []).forEach(function (b) { if (b.reg) demoRegs[b.reg] = 1; }); });
  });

  tryDo('customers', function () { fillArr(customers, D.customers); });
  tryDo('CX', function () { fillObj(CX, D.CX); });
  tryDo('vehicles', function () { fillArr(vehicles, D.vehicles); });
  tryDo('VX', function () { fillObj(VX, D.VX); });
  tryDo('invoices', function () { fillArr(invoices, D.invoices); });
  tryDo('legacy', function () { fillObj(legacy, D.legacy); });
  tryDo('QUOTES', function () { fillArr(QUOTES, D.QUOTES); });
  tryDo('JOBS', function () { fillArr(JOBS, D.JOBS); });
  tryDo('REMS', function () { fillArr(REMS, D.REMS); });
  // derived lists the mock computed from the demo seed
  tryDo('owed', function () { fillArr(owed, invoices.filter(function (i) { return i.status === 'owed'; })); });
  tryDo('dueSoon', function () { fillArr(dueSoon, vehicles.filter(function (v) { return v.mot && daysTo(v.mot) <= 30; })); });
  // demo-only structures that point at demo regs or customers
  tryDo('BK', function () { fillObj(BK, {}); });
  tryDo('NOTES', function () { fillObj(NOTES, {}); });
  tryDo('PROMISE', function () { fillObj(PROMISE, {}); });
  tryDo('SVC', function () { fillObj(SVC, {}); });
  tryDo('dropgo', function () { fillArr(dropgo, []); });
  tryDo('ringbacks', function () { fillArr(ringbacks, []); });
  tryDo('XPAYS', function () { fillArr(XPAYS, []); });
  tryDo('WL', function () { fillArr(WL, []); });
  tryDo('AUD', function () { fillArr(AUD, []); });
  tryDo('TY', function () { fillObj(TY, {}); });
  tryDo('CFSEED', function () { fillObj(CFSEED, {}); });

  var stubs = Object.keys(demoRegs).filter(function (r) { return r && !vehicles.some(function (v) { return v.reg === r; }); })
    .map(function (r) { return { reg: r, make: '(demo slot, no real vehicle)', year: '', cust: '', miles: 0, mot: '', fuel: '', colour: '' }; });
  tryDo('wrap screens', function () {
    Object.keys(S).forEach(function (k) {
      var orig = S[k];
      if (typeof orig !== 'function') return;
      S[k] = function () {
        var n = vehicles.length;
        stubs.forEach(function (v) { vehicles.push(v); });
        try { return orig.apply(this, arguments); }
        finally { vehicles.length = n; }
      };
    });
  });

  // The invoice list renders every row (24k for five years, 78k for all) and
  // takes seconds.  With no search text and the "All" tab, show only the
  // newest ROWS and say so; any search or tab filter still runs over everything.
  var ROWS = 1000;
  tryDo('invoice list cap', function () {
    var orig = window.invTable;
    window.invTable = function () {
      if ((invQ || '').trim() || invF !== 'all' || invoices.length <= ROWS) return orig.apply(this, arguments);
      var all = invoices.slice();
      var keep = all.slice().sort(function (a, b) { return b.n.localeCompare(a.n); }).slice(0, ROWS);
      fillArr(invoices, keep);
      try {
        return orig.apply(this, arguments).replace('</tbody>', '<tr><td colspan="6" class="muted small">Showing the newest ' +
          ROWS.toLocaleString() + ' of ' + all.length.toLocaleString() + ' invoices in view. Type a number, name or reg to search all of them.</td></tr></tbody>');
      } finally { fillArr(invoices, all); }
    };
  });

  // ---- Wents Diary mirror (read-only; tools/wentsdiary/README.md) ----
  // window.__localDiary = {BK, NOTES, SLOTS (per day), meta} built by wd.py
  // from the cached day sheets.  Bookings go into the mock's BK, day notes
  // into NOTES, and the day's MOT slot times into SLOTS just before the Diary
  // or its A4 sheet renders (the mock has one fixed slot list; the diary has
  // one per day).  The week strip and "next MOT slot" are hard-coded to the
  // demo week in the mock, so they are replaced here.
  var WD = window.__localDiary || { BK: {}, NOTES: {}, SLOTS: {}, meta: {} };
  var defSlots = SLOTS.slice();
  var wdSt = null, wdPolling = false;
  function applyDiary(d) {
    WD = d;
    tryDo('diary BK', function () { fillObj(BK, d.BK || {}); });
    tryDo('diary NOTES', function () { fillObj(NOTES, d.NOTES || {}); });
  }
  function slotsFor(d) { var s = WD.SLOTS && WD.SLOTS[d]; fillArr(SLOTS, s && s.length ? s : defSlots); }
  function dnum(d) { return new Date(d + 'T12:00:00').getDate(); }
  function dow(d) { return (new Date(d + 'T12:00:00').getDay() + 6) % 7; } // 0 = Monday
  function weekday(d) { var w = dow(d); return w > 4 ? addD(d, 7 - w) : d; } // closed Sat/Sun: next Monday
  function weekStrip(d) {
    var mon = addD(d, -dow(d)), b = [];
    b.push('<button onclick="day=\'' + addD(mon, -7) + '\';go()" title="Previous week">&lsaquo;<b>wk</b>back</button>');
    for (var i = 0; i < 5; i++) {
      var dd = addD(mon, i), n = (BK[dd] || []).length, known = !!(WD.SLOTS && WD.SLOTS[dd]) || n > 0;
      b.push('<button class="' + (dd === day ? 'on' : '') + '" onclick="day=\'' + dd + '\';go()">' + fmt(dd, { weekday: 'short' }) +
        '<b>' + dnum(dd) + '</b>' + (n ? n + ' cars' : known ? '&ndash; cars' : 'not fetched') + '</button>');
    }
    b.push('<button onclick="day=\'' + addD(mon, 7) + '\';go()" title="Next week">&rsaquo;<b>wk</b>next</button>');
    return '<div class="week">' + b.join('') + '</div>';
  }
  tryDo('diary who', function () { WHO.wd = { n: 'Wents', c: '#8A94A6' }; });
  applyDiary(WD);
  tryDo('diary today', function () { if (WD.meta && WD.meta.today) { day = weekday(WD.meta.today); slotsFor(day); } });
  tryDo('diary screen', function () {
    var orig = S.diary;
    S.diary = function () {
      day = weekday(day);
      slotsFor(day);
      return orig.apply(this, arguments)
        .replace(/<div class="week">[\s\S]*?<\/div>/, weekStrip(day))
        .replace(/<span class="whotag"[^>]*title="Wents is on it">[\s\S]*?<\/span>/g, '')
        .replace(/ &middot; tester [A-Za-z]+<\/p>| · tester [A-Za-z]+<\/p>/, ' · mirrored from the Wents Diary</p>');
    };
  });
  tryDo('diary paper', function () {
    var orig = S.doc;
    S.doc = function (arg) { var m = /^diaryday\/(\d{4}-\d\d-\d\d)/.exec(arg || ''); if (m) slotsFor(m[1]); return orig.apply(this, arguments); };
  });
  tryDo('diary next slot', function () {
    window.nextSlot = function () {
      var t0 = (WD.meta && WD.meta.today) || day;
      for (var i = 0; i < 120; i++) {
        var d = addD(t0, i), s = WD.SLOTS && WD.SLOTS[d];
        if (!s || dow(d) > 4) continue;
        var free = s.filter(function (t) { return !(BK[d] || []).some(function (b) { return b.k === 'mot' && b.t === t; }); })[0];
        if (free) { day = d; dTab = 'mot'; slotsFor(d); toast('Next free MOT: ' + fmt(d, { weekday: 'short', day: 'numeric', month: 'short' }) + ' at ' + free); go(); return; }
      }
      toast('No free MOT slot in the fetched diary');
    };
  });
  function wdFetch(url, cb) { fetch(url, { cache: 'no-store' }).then(function (r) { return r.json(); }).then(cb).catch(function () {}); }
  function wdBanner() {
    var el = document.getElementById('local-diary'); if (!el) return;
    var m = WD.meta || {}, s = wdSt || {}, f = s.fetch || {};
    var txt = m.days ? 'Diary: ' + m.days + ' days cached (' + fmtS(m.from) + ' to ' + fmtS(m.to) + '), ' + (m.mot + m.svc) + ' bookings' +
      (m.fetchedAt ? ', fetched ' + new Date(m.fetchedAt).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '') : 'Diary: nothing fetched yet';
    if (f.running) txt += ' · fetching ' + f.done + '/' + f.total + '…';
    else if (f.error) txt += ' · last fetch stopped: ' + f.error;
    var act = f.running ? '' : s.signedIn ? '<button onclick="window.__wdRefresh()">Refresh diary</button>' :
      '<a href="/wd/login">Sign in to the Wents Diary</a>' + (s.hasToken ? ' (sign-in expired)' : '');
    el.innerHTML = txt + (act ? ' · ' + act : '');
  }
  function wdPoll() {
    wdFetch('/wd/status', function (s) {
      wdSt = s; wdBanner();
      if (s.fetch && s.fetch.running) { wdPolling = true; setTimeout(wdPoll, 1500); }
      else if (wdPolling) { wdPolling = false; wdFetch('/wd/diary.json', function (d) { applyDiary(d); slotsFor(day); wdBanner(); go(); }); }
    });
  }
  window.__wdRefresh = function () { wdFetch('/wd/refresh', function () { wdPolling = true; wdPoll(); }); };

  window.__localMeta = D.meta;
  tryDo('render', function () { go(); });
  document.documentElement.classList.remove('local-loading');
  var m = D.meta || {};
  console.log('local-data: applied in ' + Math.round(performance.now() - t0) + ' ms', m);
  // small banner so nobody mistakes this for the public demo
  var b = document.createElement('div');
  b.id = 'local-banner';
  b.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:9999;font:12px/1.4 system-ui,sans-serif;background:#173E70;color:#fff;padding:4px 10px;text-align:center;opacity:.92;pointer-events:none';
  b.textContent = 'LOCAL · real GarageBase data · ' + (m.invoicesFull || 0).toLocaleString() + ' invoices in view' +
    (m.years ? ' (last ' + m.years + ' years; add ?years=all for everything)' : ' (all years)') +
    ' · ' + (m.invoicesLegacy || 0).toLocaleString() + ' older as history · owed ' + (typeof gbp === 'function' ? gbp(m.owedTotal || 0) : m.owedTotal);
  var dv = document.createElement('div');
  dv.id = 'local-diary';
  dv.style.cssText = 'pointer-events:auto;margin-top:2px';
  b.appendChild(dv);
  document.body.appendChild(b);
  var css = document.createElement('style');
  css.textContent = '#local-diary button,#local-diary a{font:inherit;font-weight:600;color:#fff;background:rgba(255,255,255,.18);border:0;border-radius:6px;padding:1px 8px;cursor:pointer;text-decoration:none}';
  document.head.appendChild(css);
  wdBanner(); wdPoll();
})();
