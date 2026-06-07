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
    a.href = "https://finance.yahoo.com/quote/" + encodeURIComponent(sym);
    a.target = "_blank"; a.rel = "noopener";
    a.title = sym + (info.ret3mo != null
      ? " · " + (info.above_ma ? "uptrend" : "downtrend") + " · 3-mo " + pct(info.ret3mo) + " — chart"
      : " — open chart");
    a.addEventListener("click", function (e) { e.stopPropagation(); });
    return a;
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
    var n = (t.stocks || []).length;
    card.innerHTML =
      '<div class="chead"><span class="em">' + t.emoji + '</span>' +
      "<h3>" + t.label + '</h3><span class="etf">' + t.etf + "</span></div>" +
      '<div class="metrics">' + TREND[t.trend][0] +
      '<span class="badge ' + (t.ret3mo >= 0 ? "up" : "down") + '">' + pct(t.ret3mo) + " (3mo)</span>" +
      '<span class="dim ' + beatCls + '">' + beatTxt + "</span>" +
      '<span class="dim">' + crowd + "</span></div>" +
      '<p class="verdict">' + t.verdict + "</p>" +
      '<div class="card-foot"><span class="caret">▸</span> ' + n + " companies</div>";

    var detail = document.createElement("div");
    detail.className = "card-stocks";
    (t.stocks || []).forEach(function (s) { detail.appendChild(chip(s)); });
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
