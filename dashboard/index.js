// Dashboard: polls the API every 5 s and redraws charts, alerts and processes.
const RANGES = { "1h": { since: "1h", step: 0 }, "24h": { since: "24h", step: 300 } };
const COLORS = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed", "#0891b2"];
let range = "1h";

// interval = seconds between raw samples, used to detect gaps in the line.
const CHARTS = [
  { id: "cpu", title: "CPU %", sub: "Alert if > 85% for 60s", names: ["cpu_total"], interval: 5, max: 100 },
  { id: "mem", title: "RAM / Swap %", sub: "Alert at > 90% RAM", names: ["ram_percent", "swap_percent"], interval: 5, max: 100 },
  { id: "disk", title: "Disk used %", sub: "Alert at > 90% per mount", names: ["disk_percent"], interval: 5, max: 100 },
  {
    id: "net", title: "Network throughput", sub: "Combined upload / download rate", names: ["net_down_Bps", "net_up_Bps"], interval: 5, sum: true,
    labels: { net_down_Bps: "Download", net_up_Bps: "Upload" }
  },
  { id: "lat", title: "Latency (ms)", sub: "DNS / TCP / API (gaps = timeouts)", names: ["dns_ms", "tcp_ms", "api_ms"], interval: 15 },
  { id: "loss", title: "Packet loss %", sub: "Alert if 3 failures in a row (45s)", names: ["gateway_loss", "internet_loss"], interval: 15, max: 100 },
];
const charts = {};

// Friendly legend names for metric names.
const LABELS = {
  cpu_total: "CPU", ram_percent: "RAM", swap_percent: "Swap", disk_percent: "Disk",
  net_down_Bps: "Download", net_up_Bps: "Upload",
  dns_ms: "DNS", tcp_ms: "TCP connect", api_ms: "API",
  gateway_loss: "Gateway loss", internet_loss: "Internet loss",
};

/** GET a JSON endpoint. */
async function api(path) {
  const r = await fetch(path);
  return r.json();
}

/** Format epoch seconds as local date + time with seconds. */
function fmt(ts) {
  return ts ? new Date(ts * 1000).toLocaleString([], { hour12: false }) : "";
}

/** Create one empty Chart.js line chart per CHARTS entry. */
function buildCharts() {
  const root = document.getElementById("charts");
  for (const c of CHARTS) {
    root.insertAdjacentHTML("beforeend", `<div class="card"><div class="card-head"><h3>${c.title}</h3><span class="sub">${c.sub || ""}</span></div><canvas id="c-${c.id}"></canvas></div>`);
    charts[c.id] = new Chart(document.getElementById(`c-${c.id}`), {
      type: "line",
      data: { datasets: [] },
      options: {
        animation: false, responsive: true, maintainAspectRatio: false, spanGaps: false,
        elements: { point: { radius: 0 }, line: { borderWidth: 1.5 } },
        plugins: { legend: { position: "bottom", labels: { boxWidth: 10, font: { size: 11 } } } },
        scales: {
          x: { type: "linear", ticks: { maxTicksLimit: 6, callback: v => new Date(v).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false }) } },
          y: { beginAtZero: true, max: c.max },
        },
      },
    });
  }
}

/** Fetch every metric of a chart and turn them into datasets (one line per name+subject). */
async function updateChart(c) {
  const { since, step } = RANGES[range];
  const gap = Math.max(c.interval, step) * 3 * 1000;   // a longer hole than this is drawn as a break
  const datasets = [];
  for (const name of c.names) {
    const pts = await api(`/metrics?name=${name}&since=${since}&step=${step}`);
    const bySubject = {};
    for (const p of pts) (bySubject[p.subject] ||= []).push(p);
    if (c.sum) {   // collapse all interfaces into one line (keeps the legend short)
      const totals = {};
      for (const p of pts) totals[p.ts] = (totals[p.ts] || 0) + p.value;
      bySubject[""] = Object.entries(totals).map(([ts, value]) => ({ ts: +ts, value }));
      for (const k of Object.keys(bySubject)) if (k) delete bySubject[k];
    }
    for (const [subject, list] of Object.entries(bySubject)) {
      const data = [];
      list.forEach((p, i) => {
        if (i && (p.ts - list[i - 1].ts) * 1000 > gap) data.push({ x: (list[i - 1].ts * 1000) + 1, y: null });
        data.push({ x: p.ts * 1000, y: p.value });
      });
      const color = COLORS[datasets.length % COLORS.length];
      datasets.push({ label: (LABELS[name] || name) + (subject ? ` ${subject}` : ""), data, borderColor: color, backgroundColor: color });
    }
  }
  charts[c.id].data.datasets = datasets;
  charts[c.id].update("none");
}

/** Render a table; `cols` is [header, row => html]. */
function table(id, cols, rows, emptyMsg) {
  const el = document.getElementById(id);
  if (!rows.length) { el.innerHTML = `<tr><td class="empty">${emptyMsg}</td></tr>`; return; }
  el.innerHTML = "<tr>" + cols.map(c => `<th>${c[0]}</th>`).join("") + "</tr>" +
    rows.map(r => "<tr>" + cols.map(c => `<td>${c[1](r)}</td>`).join("") + "</tr>").join("");
}

const alertCols = [
  ["Rule", a => a.rule],
  ["Subject", a => a.subject],
  ["Severity", a => `<span class="sev-${a.severity}">${a.severity}</span>`],
  ["Opened", a => fmt(a.opened_at)],
  ["Closed", a => fmt(a.closed_at) || "—"],
  ["Peak", a => a.peak == null ? "" : a.peak.toFixed(1)],
  ["Detail", a => a.detail || ""],
];
const procCols = [
  ["PID", p => p.pid], ["Name", p => p.name], ["CPU %", p => p.cpu], ["RSS MB", p => p.rss_mb],
  ["FDs", p => p.fds ?? ""], ["State", p => p.status], ["Flags", p => p.flags.join(", ")],
];

/** Refresh badge, alert tables, process table and charts. */
async function refresh() {
  const [health, open, closed, procs] = await Promise.all([
    api("/health"), api("/alerts?open=true"), api("/alerts?open=false&limit=50"), api("/processes?sort=cpu&limit=15"),
  ]);
  const badge = document.getElementById("badge");
  badge.textContent = health.status;
  badge.className = `badge ${health.status}`;
  table("open-alerts", alertCols, open, "No open alerts");
  table("closed-alerts", alertCols, closed, "No closed alerts yet");
  table("procs", procCols, procs, "No data yet");
  await Promise.all(CHARTS.map(updateChart));
}

document.querySelectorAll(".range button").forEach(b => b.addEventListener("click", () => {
  range = b.dataset.range;
  document.querySelectorAll(".range button").forEach(x => x.classList.toggle("active", x === b));
  refresh();
}));

buildCharts();
refresh();
setInterval(refresh, 5000);
