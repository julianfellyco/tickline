/* tick/line · simple — render the Trend & Crowd board */
(function () {
  "use strict";
  var D = window.SIMPLE_DATA;
  if (!D) return;

  function pct(x) {
    if (x === null || x === undefined) return "—";
    return (x > 0 ? "+" : "") + Math.round(x * 100) + "%";
  }
  var TREND = {
    up: ['<span class="badge up">▲ Uptrend</span>', "up"],
    sideways: ['<span class="badge side">▬ Sideways</span>', "side"],
    down: ['<span class="badge down">▼ Downtrend</span>', "down"]
  };

  document.getElementById("stamp").textContent =
    "Market close " + D.as_of + " · " + D.themes.length + " themes";
  document.getElementById("count").textContent = "Themes (" + D.themes.length + ")";
  var foot = document.getElementById("foot");
  if (foot) foot.textContent = "Updated " + (D.generated || D.as_of) + ".";

  var grid = document.getElementById("grid");

  // a company chip: trend dot (its own 200-day line) + symbol -> chart
  function chip(sym) {
    var info = (D.stock_info || {})[sym] || {};
    var a = document.createElement("a");
    a.className = "stk-chip";
    if (info.trend) {
      var dot = document.createElement("span");
      dot.className = "stk-dot stk-" + info.trend;
      a.appendChild(dot);
    }
    a.appendChild(document.createTextNode(sym));
    if (info.ret3mo != null) {
      var rr = document.createElement("span");
      rr.className = "stk-ret " + (info.ret3mo >= 0 ? "up" : "down");
      rr.textContent = pct(info.ret3mo);
      a.appendChild(rr);
    }
    a.href = "https://finance.yahoo.com/quote/" + encodeURIComponent(sym);
    a.target = "_blank"; a.rel = "noopener";
    a.title = sym + " — click for analyst & fundamentals briefing";
    a.addEventListener("click", function (e) {
      if (e.metaKey || e.ctrlKey || e.button === 1) { e.stopPropagation(); return; }
      e.preventDefault(); e.stopPropagation(); openModal(sym);
    });
    return a;
  }

  // ── in-page company briefing modal ──────────────────────────
  var overlay = document.createElement("div");
  overlay.className = "modal-overlay"; overlay.hidden = true;
  overlay.innerHTML = '<div class="modal" role="dialog" aria-modal="true">' +
    '<button class="modal-x" aria-label="Close">×</button><div class="modal-body"></div></div>';
  document.body.appendChild(overlay);
  var mbody = overlay.querySelector(".modal-body");
  overlay.addEventListener("click", function (e) { if (e.target === overlay) closeModal(); });
  overlay.querySelector(".modal-x").addEventListener("click", closeModal);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeModal(); });
  function closeModal() { overlay.hidden = true; document.body.style.overflow = ""; }
  function openModal(sym) {
    mbody.innerHTML = renderBrief(sym);
    overlay.hidden = false; overlay.scrollTop = 0;
    document.body.style.overflow = "hidden";
  }

  function money(v) {
    if (v == null) return "—";
    var a = Math.abs(v);
    if (a >= 1e12) return "$" + (v / 1e12).toFixed(2) + "T";
    if (a >= 1e9) return "$" + (v / 1e9).toFixed(1) + "B";
    if (a >= 1e6) return "$" + (v / 1e6).toFixed(0) + "M";
    return "$" + v;
  }
  function metric(label, val, signed) {
    var cls = signed == null ? "" : (signed >= 0 ? "up" : "down");
    return '<div class="md-metric"><div class="md-mlabel">' + label +
      '</div><div class="md-mval ' + cls + '">' + val + "</div></div>";
  }
  var RECO = { strong_buy: "Strong Buy", buy: "Buy", outperform: "Outperform",
    hold: "Hold", underperform: "Underperform", sell: "Sell", strong_sell: "Strong Sell" };

  function renderBrief(sym) {
    var c = (D.company_info || {})[sym], ti = (D.stock_info || {})[sym] || {};
    if (!c) return "<h2>" + sym + '</h2><p class="md-dim">No briefing available.</p>';
    var up = (c.tgtMean != null && c.price) ? (c.tgtMean / c.price - 1) : null;
    var reco = RECO[c.reco] || (c.reco || "—");
    var pos = (c.w52h > c.w52l) ? Math.max(2, Math.min(98, (c.price - c.w52l) / (c.w52h - c.w52l) * 100)) : 50;
    return '' +
      '<div class="md-head"><div><h2>' + c.name + ' <span class="md-tk">' + sym + "</span></h2>" +
        '<div class="md-sub">' + (c.sector || "") + (c.industry ? " · " + c.industry : "") + "</div></div>" +
        '<div class="md-price"><span class="stk-dot stk-' + (ti.trend || "flat") + '"></span>$' + c.price + "</div></div>" +
      '<div class="md-sec"><h3>Analyst view</h3>' +
        '<div class="md-row"><span class="md-rate rate-' + (c.reco || "na") + '">' + reco + "</span>" +
        '<span class="md-dim">' + (c.nAnalysts ? c.nAnalysts + " analysts" : "no coverage") + "</span></div>" +
        (c.tgtMean != null
          ? '<div class="md-row"><b>Price target $' + c.tgtMean + '</b> <span class="' + (up >= 0 ? "up" : "down") +
            '">' + pct(up) + " vs now</span></div><div class=\"md-dim\">range $" + (c.tgtLow != null ? c.tgtLow : "—") +
            " – $" + (c.tgtHigh != null ? c.tgtHigh : "—") + "</div>"
          : '<div class="md-dim">No published price targets.</div>') +
      "</div>" +
      '<div class="md-sec"><h3>Fundamentals</h3><div class="md-grid">' +
        metric("Market cap", money(c.mcap)) +
        metric("P/E", c.pe != null ? c.pe : "—") +
        metric("Fwd P/E", c.fpe != null ? c.fpe : "—") +
        metric("EPS", c.eps != null ? "$" + c.eps : "—") +
        metric("Profit margin", c.margin != null ? Math.round(c.margin * 100) + "%" : "—") +
        metric("Beta", c.beta != null ? c.beta : "—") +
        metric("Div yield", c.divY != null ? c.divY.toFixed(2) + "%" : "—") +
        metric("Employees", c.employees != null ? c.employees.toLocaleString() : "—") +
      "</div></div>" +
      '<div class="md-sec"><h3>Price action</h3>' +
        '<div class="md-52"><span class="md-dim">$' + c.w52l + '</span>' +
        '<div class="md-bar"><span style="left:' + pos + '%"></span></div>' +
        '<span class="md-dim">$' + c.w52h + "</span></div>" +
        '<div class="md-dim md-center">52-week range</div>' +
        '<div class="md-grid md-rets">' +
          metric("1 month", pct(c.r1m), c.r1m) + metric("3 month", pct(c.r3m), c.r3m) +
          metric("6 month", pct(c.r6m), c.r6m) +
        "</div></div>" +
      (c.summary ? '<div class="md-sec"><h3>Company briefing</h3><p class="md-summary">' + c.summary + "</p></div>" : "") +
      '<a class="md-link" href="https://finance.yahoo.com/quote/' + encodeURIComponent(sym) +
      '" target="_blank" rel="noopener">Full chart &amp; financials on Yahoo ↗</a>';
  }

  D.themes.forEach(function (t) {
    var card = document.createElement("article");
    card.className = "card clickable " + t.light;
    var beatCls = (t.vs_spy || 0) >= 0 ? "up" : "down";
    var beatTxt = (t.vs_spy >= 0 ? "beating" : "lagging") + " S&P by " +
      pct(Math.abs(t.vs_spy || 0)).replace("+", "");
    var med = D.buzz_median || 0;
    var crowd = (t.crowd === "loud" ? "🗣 Loud" : "Quiet") +
      " · " + t.buzz + " stories vs ~" + med + " typical";
    // screen: rank the companies by 3-month return, strongest first
    var SI = D.stock_info || {};
    function r3(s) { var v = (SI[s] || {}).ret3mo; return v == null ? -999 : v; }
    var stocks = (t.stocks || []).slice().sort(function (a, b) { return r3(b) - r3(a); });
    var n = stocks.length;
    var upN = stocks.filter(function (s) { return (SI[s] || {}).above_ma; }).length;

    card.innerHTML =
      '<div class="chead"><span class="em">' + t.emoji + '</span>' +
      "<h3>" + t.label + '</h3><span class="etf">' + t.etf + "</span></div>" +
      '<div class="metrics">' + TREND[t.trend][0] +
      '<span class="badge ' + (t.ret3mo >= 0 ? "up" : "down") + '">' + pct(t.ret3mo) + " (3mo)</span>" +
      '<span class="dim ' + beatCls + '">' + beatTxt + "</span>" +
      '<span class="dim">' + crowd + "</span></div>" +
      '<p class="verdict">' + t.verdict + "</p>" +
      '<div class="card-foot"><span class="caret">▸</span> ' +
      '<span class="up">' + upN + "</span> of " + n + " companies trending up</div>";

    var detail = document.createElement("div");
    detail.className = "card-stocks";
    stocks.forEach(function (s) { detail.appendChild(chip(s)); });
    if (!n) detail.appendChild(document.createTextNode("—"));
    card.appendChild(detail);

    card.setAttribute("role", "button");
    card.setAttribute("tabindex", "0");
    function toggle() { card.classList.toggle("open"); }
    card.addEventListener("click", toggle);
    card.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); }
    });

    grid.appendChild(card);
  });
})();
