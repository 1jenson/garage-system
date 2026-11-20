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
  document.body.appendChild(b);
})();
