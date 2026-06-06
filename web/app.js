/* tick/line watchlist — render the rotation board from window.TICKLINE_DATA */
(function () {
  "use strict";
  var DATA = window.TICKLINE_DATA;
  if (!DATA) return;

  var state = { tier: "slow", groups: new Set(DATA.groups) };

  // ── formatting ──────────────────────────────────────────────
  function pct(x, dp) {
    if (x === null || x === undefined) return "—";
    var v = (x * 100).toFixed(dp === undefined ? 0 : dp);
    return (x > 0 ? "+" : "") + v + "%";
  }
  function el(tag, cls, html) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html !== undefined) n.innerHTML = html;
    return n;
  }
  function tierRows() { return DATA.tiers[state.tier].rows; }

  // ── hero: stamp, stats, editorial regime line ───────────────
  function renderMeta() {
    document.getElementById("stamp").textContent = "close " + DATA.as_of;
    document.getElementById("bench").textContent = DATA.benchmark;
    var fd = document.getElementById("foot-date");
    if (fd) fd.textContent = DATA.as_of + (DATA.generated ? " · built " + DATA.generated : "");

    var rows = DATA.tiers.slow.rows;
    var top = rows[0], bot = rows[rows.length - 1];
    document.getElementById("regime").innerHTML =
      '<span class="accent">' + top.label + "</span> out front.<br>" +
      '<span class="accent-down">' + bot.label + "</span> bringing up the rear.";

    var stats = [
      [DATA.tiers.slow.rows.length, "themes"],
      [DATA.n_symbols, "symbols"],
      [DATA.benchmark, "benchmark"],
      [DATA.as_of, "as of"]
    ];
    var dl = document.getElementById("stats");
    stats.forEach(function (s) {
      var d = el("div");
      d.appendChild(el("dd", null, String(s[0])));
      d.appendChild(el("dt", null, s[1]));
      dl.appendChild(d);
    });
  }

  // ── long / short books ──────────────────────────────────────
  function byKey(k) { return tierRows().find(function (r) { return r.key === k; }); }
  function renderBooks() {
    var t = DATA.tiers[state.tier];
    ["leaders", "laggards"].forEach(function (side) {
      var ul = document.getElementById(side);
      ul.innerHTML = "";
      t[side].forEach(function (k) {
        var r = byKey(k); if (!r) return;
        var li = el("li", "book-row");
        li.appendChild(el("span", "book-name", r.label));
        var cls = r.rel >= 0 ? "long" : "short";
        li.appendChild(el("span", "book-val mono " + cls, pct(r.rel)));
        ul.appendChild(li);
      });
    });
  }

  // ── group filter chips ──────────────────────────────────────
  function renderChips() {
    var box = document.getElementById("chips");
    box.innerHTML = "";
    DATA.groups.forEach(function (g) {
      var c = el("button", "chip active", g);
      c.addEventListener("click", function () {
        if (state.groups.has(g)) { state.groups.delete(g); c.classList.replace("active", "off"); }
        else { state.groups.add(g); c.classList.replace("off", "active"); }
        renderTable();
      });
      box.appendChild(c);
    });
  }

  // ── ranked diverging-bar table ──────────────────────────────
  function renderTable() {
    var box = document.getElementById("ranktable");
    box.innerHTML = "";
    var rows = tierRows().filter(function (r) { return state.groups.has(r.group); });
    var maxAbs = rows.reduce(function (m, r) { return Math.max(m, Math.abs(r.rel)); }, 0.01);

    rows.forEach(function (r) {
      var row = el("div", "rank-row");

      var id = el("div", "rank-id");
      id.appendChild(el("div", "rank-name", r.label));
      var meta = el("div", "rank-meta");
      meta.appendChild(el("span", "tag tag-" + r.signal, r.signal));
      meta.appendChild(el("span", "group-label", r.group));
      id.appendChild(meta);
      row.appendChild(id);

      var wrap = el("div", "bar-wrap");
      wrap.appendChild(el("div", "bar-axis"));
      var w = (Math.abs(r.rel) / maxAbs) * 50;
      var bar = el("div", "bar " + (r.rel >= 0 ? "bar-pos" : "bar-neg"));
      if (r.rel >= 0) { bar.style.left = "50%"; bar.style.setProperty("--origin", "left center"); }
      else { bar.style.left = (50 - w) + "%"; bar.style.setProperty("--origin", "right center"); }
      bar.style.width = w + "%";
      wrap.appendChild(bar);
      row.appendChild(wrap);

      var val = el("div", "rank-val");
      val.appendChild(el("div", "rank-rel " + (r.rel >= 0 ? "long" : "short"), pct(r.rel)));
      val.appendChild(el("div", "rank-slope", "slope " + pct(r.slope)));
      row.appendChild(val);

      box.appendChild(row);
    });
  }

  // ── tier toggle ─────────────────────────────────────────────
  function bindTiers() {
    document.querySelectorAll(".seg").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (btn.dataset.tier === state.tier) return;
        state.tier = btn.dataset.tier;
        document.querySelectorAll(".seg").forEach(function (b) {
          var on = b === btn;
          b.classList.toggle("active", on);
          b.setAttribute("aria-selected", on ? "true" : "false");
        });
        renderBooks();
        renderTable();
      });
    });
  }

  // ── init ────────────────────────────────────────────────────
  renderMeta();
  renderChips();
  renderBooks();
  renderTable();
  bindTiers();
  requestAnimationFrame(function () { document.body.classList.add("loaded"); });
})();
