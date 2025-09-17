/* global Chart */
(function () {
  const cs = getComputedStyle(document.documentElement);
  const text = cs.getPropertyValue('--chart-text').trim() || '#212529';
  const grid = cs.getPropertyValue('--chart-grid').trim() || 'rgba(0,0,0,.1)';
  Chart.defaults.color = text;
  Chart.defaults.scale.grid.color = grid;
  Chart.defaults.scale.ticks.color = text;
})();

; (function (w) {
  const $ = (id) => document.getElementById(id);

  // ---------- Reusable helpers ----------
  function makeHBar(canvasId, labels, values, { color = "#1f77b4", xTitle = "", legendLabel = "" } = {}) {
    const ctx = $(canvasId)?.getContext?.("2d"); if (!ctx) return null;
    const maxVal = Math.max(1, ...values.map(v => Number(v) || 0));
    const padMax = Math.ceil((maxVal * 1.05) / 5) * 5;
    return new Chart(ctx, {
      type: "bar",
      data: { labels, datasets: [{ label: legendLabel, data: values, backgroundColor: color, borderColor: color, borderWidth: 1 }] },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { display: !!legendLabel, position: "right" } },
        scales: {
          x: { beginAtZero: true, suggestedMax: padMax, ticks: { precision: 0 }, title: { display: !!xTitle, text: xTitle } },
          y: { ticks: { autoSkip: false } }
        }
      }
    });
  }

  function makeCDF(canvasId, points, { color = "#5dade2", xTitle = "Duration (hours)" } = {}) {
    const ctx = $(canvasId)?.getContext?.("2d"); if (!ctx) return null;

    // Fill from the top (0% at top thanks to y.reverse)
    const topBand = points.map(p => ({ x: p.x, y: 0 }));

    return new Chart(ctx, {
      type: "line",
      data: {
        datasets: [
          { data: topBand, borderWidth: 0, pointRadius: 0, fill: false },
          { data: points, fill: "-1", tension: 0.2, borderColor: color, backgroundColor: color }
        ]
      },
      options: {
        parsing: true,
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { type: "linear", title: { display: true, text: xTitle } },
          y: {
            reverse: true, min: 0, max: 100,
            title: { display: true, text: "Percent of flights (≥ x)" },
            ticks: { callback: (v) => `${v}%` }
          }
        }
      }
    });
  }

  // ---- Export helpers for Option B consumers ----
  w.AnalyticsCharts = w.AnalyticsCharts || {};
  w.AnalyticsCharts.helpers = { makeHBar, makeCDF /* makeHStacked is defined globally below and used directly */ };

  // ---------- Chart initializers (inside IIFE) ----------
  function initCumulative(d) {
    const L = d.labels || [], years = d.years || [], dataByYear = d.data || {};
    const totals = d.totals || {}, instr = d.instr || {};
    const currentYear = d.current_year;

    const anchors = { 1: "Jan", 32: "Feb", 60: "Mar", 91: "Apr", 121: "May", 152: "Jun", 182: "Jul", 213: "Aug", 244: "Sep", 274: "Oct", 305: "Nov", 335: "Dec" };
    const colorForYear = (y) => { const base = (y * 9301 + 49297) % 233280; const hue = (base / 233280) * 360; return `hsl(${hue},60%,45%)`; };
    const doyToday = () => { const t = new Date(); return Math.floor((t - new Date(t.getFullYear(), 0, 0)) / 86400000); };
    const todayYear = new Date().getFullYear(), todayDoy = doyToday();

    const datasets = years.map((y) => {
      const c = colorForYear(y), isCurrent = y === currentYear, arr = (dataByYear[String(y)] || []).slice();
      if (isCurrent && y === todayYear) { for (let i = todayDoy; i < arr.length; i++) arr[i] = null; }
      return {
        label: String(y), data: arr, borderColor: c, backgroundColor: c, tension: 0.2,
        borderWidth: isCurrent ? 3 : 1.5, borderDash: isCurrent ? undefined : [5, 4],
        pointRadius: isCurrent ? 3 : 0, pointHoverRadius: isCurrent ? 5 : 3,
        pointBackgroundColor: isCurrent ? "#fff" : undefined, pointBorderColor: isCurrent ? c : undefined, pointBorderWidth: isCurrent ? 2 : 0, spanGaps: false
      };
    });

    const flatMax = datasets.reduce((m, ds) => Math.max(m, Math.max(0, ...(ds.data || []).filter(v => v != null))), 0);
    const yMax = Math.max(10, Math.ceil((flatMax * 1.05) / 50) * 50);

    if (w.cumuChart?.destroy) w.cumuChart.destroy();
    const ctx = $("cumuChart")?.getContext?.("2d"); if (!ctx) return;
    w.cumuChart = new Chart(ctx, {
      type: "line",
      data: { labels: L, datasets },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: "nearest", intersect: false },
        plugins: {
          legend: { position: "left", labels: { boxWidth: 18 } }, tooltip: {
            callbacks: {
              title: (items) => { if (!items.length) return ""; const i = items[0]; const y = Number(i.dataset.label); const doy = L[i.dataIndex]; const dte = new Date(y, 0, doy); const month = dte.toLocaleString(undefined, { month: "short" }); const day = dte.getDate(); return `${y} • Day ${doy} (${month} ${day})`; },
              label: (item) => { const y = String(item.dataset.label); const val = item.parsed.y; const tot = totals[y] ?? val; const ins = instr[y] ?? 0; const pct = tot ? Math.round((ins / tot) * 100) : 0; return ` ${val} flights (total ${tot}, ${ins} instruction • ${pct}%)`; }
            }
          }
        },
        scales: {
          x: {
            title: { display: true, text: "Julian Day (1–365)" }, ticks: { callback: (_, idx) => anchors[L[idx]] || "", maxRotation: 0, autoSkip: false },
            grid: { color: (c) => anchors[L[c.index]] ? undefined : "rgba(0,0,0,0)" }
          },
          y: { beginAtZero: true, max: yMax, ticks: { precision: 0 }, title: { display: true, text: "Cumulative Flights" } }
        }
      }
    });
  }

  function initByAircraft(d) {
    const years = d.years || [], cats = d.cats || [], matrix = d.matrix || {};
    const colorForCategory = (cat, i) =>
      cat === "Private" ? "#BDBDBD" :
        cat === "Other" ? "#9E9E9E" :
          cat === "Unknown" ? "#8E44AD" :
            `hsl(${(i * 137.508) % 360},65%,48%)`;

    const datasets = cats.map((cat, i) => ({
      label: cat, data: (matrix[cat] || []).map(v => Number(v) || 0),
      backgroundColor: colorForCategory(cat, i), borderColor: colorForCategory(cat, i), borderWidth: 1
    }));
    const totals = years.map((_, i) => datasets.reduce((s, ds) => s + (Number(ds.data[i]) || 0), 0));
    const yMax = Math.max(10, Math.ceil((Math.max(0, ...totals) * 1.10) / 50) * 50);

    if (w.byAcftChart?.destroy) w.byAcftChart.destroy();
    const ctx = $("byAcftChart")?.getContext?.("2d"); if (!ctx) return;
    w.byAcftChart = new Chart(ctx, {
      type: "bar",
      data: { labels: years.map(String), datasets },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        plugins: {
          legend: { position: "left" }, tooltip: {
            callbacks: {
              title: (items) => items[0]?.label ?? "", label: (it) => ` ${it.dataset.label}: ${it.formattedValue}`,
              footer: (items) => { const i = items[0]?.dataIndex ?? 0; return `Total: ${totals[i] || 0}`; }
            }
          }
        },
        scales: { x: { stacked: true, title: { display: true, text: "Year" } }, y: { stacked: true, beginAtZero: true, suggestedMax: yMax, title: { display: true, text: "Flights" }, ticks: { precision: 0 } } }
      }
    });
  }

  function initUtilization(d, { canvasId, statusId }) {
    const names = d.names || [], flights = d.flights || [], hours = d.hours || [], avgm = d.avgm || [];
    const C_FLIGHTS = "#e74c3c", C_HOURS = "#3498db", C_AVG = "#8bc34a";
    const xMax = Math.max(1, ...flights.map(Number), ...hours.map(Number), ...avgm.map(Number));
    const padMax = Math.ceil((xMax * 1.05) / 20) * 20;

    if (!names.length) { $(statusId) && ($(statusId).textContent = "No utilization data for the selected period."); return; }
    if (w[canvasId]?.destroy) w[canvasId].destroy();
    const ctx = $(canvasId)?.getContext?.("2d"); if (!ctx) return;

    w[canvasId] = new Chart(ctx, {
      type: "bar",
      data: {
        labels: names, datasets: [
          { label: "Total Flights", data: flights, backgroundColor: C_FLIGHTS, borderColor: C_FLIGHTS, borderWidth: 1 },
          { label: "Total Hours", data: hours, backgroundColor: C_HOURS, borderColor: C_HOURS, borderWidth: 1 },
          { label: "Avg Flight (min)", data: avgm, backgroundColor: C_AVG, borderColor: C_AVG, borderWidth: 1 },
        ]
      },
      options: {
        indexAxis: "y", responsive: true, maintainAspectRatio: false, animation: false,
        plugins: {
          legend: { position: "right" }, tooltip: {
            callbacks: {
              label: (it) => {
                const ds = it.dataset.label; const v = Number(it.formattedValue);
                if (ds === "Total Hours") return ` ${ds}: ${v.toFixed(1)} h`;
                if (ds === "Avg Flight (min)") return ` ${ds}: ${Math.round(v)} min`;
                return ` ${ds}: ${v}`;
              }
            }
          }
        },
        scales: { x: { beginAtZero: true, suggestedMax: padMax, title: { display: true, text: "Flights / Hours / Minutes (scaled)" }, ticks: { precision: 0 } }, y: { ticks: { autoSkip: false } } }
      }
    });
    $(statusId) && ($(statusId).textContent = "");
  }

  function initFlyingDays(d) {
    const names = d.names || [], days = d.days || [], ops = d.ops_total || 0;
    if (!names.length) { $("fdStatus") && ($("fdStatus").textContent = "No flying-day data for the selected period."); return; }
    makeHBar("fdChart", names, days, { color: "#1f3a93", xTitle: "Days with flying activity", legendLabel: "Days" });
    $("fdStatus") && ($("fdStatus").textContent = `Members with ≥2 days. Ops days this period: ${ops}.`);
  }

  function initPilotFlights(d) {
    const names = d.names || [], counts = d.counts || [];
    if (!names.length) { $("pgfStatus") && ($("pgfStatus").textContent = "No pilot-flight data for the selected period."); return; }
    makeHBar("pgfChart", names, counts, { color: "#e74c3c", xTitle: "Flights", legendLabel: "Flights" });
    $("pgfStatus") && ($("pgfStatus").textContent = "Members with ≥2 non-instruction glider flights.");
  }

  function initDuration(d) {
    const pts = Array.isArray(d.points) && d.points.length
      ? d.points
      : (Array.isArray(d.x_hours) ? d.x_hours.map((x, i) => ({ x, y: (d.cdf_pct || [])[i] || 0 })) : []);
    if (!pts.length) { const el = $("durStatus"); if (el) el.textContent = "No duration data for the selected period."; return; }

    if (w.durChart?.destroy) w.durChart.destroy();
    w.durChart = makeCDF("durChart", pts, { color: "#5dade2" });

    const med = d.median_min || 0, p = d.pct_gt || { "1": 0, "2": 0, "3": 0 };
    const s = $("durStatus");
    if (s) s.textContent = `Median = ${med} min • Over 1h: ${p["1"]}% • Over 2h: ${p["2"]}% • Over 3h: ${p["3"]}%`;
  }

  // Public entry: DO NOT overwrite the object (keeps .helpers intact)
  w.AnalyticsCharts.initAll = function (all) {
    if (!all || typeof all !== "object") return;
    initCumulative(all.cumulative || {});
    initByAircraft(all.by_acft || {});
    initUtilization(all.util || {}, { canvasId: "utilChart", statusId: "utilStatus" });
    initUtilization(all.util_priv || {}, { canvasId: "utilPrivChart", statusId: "utilPrivStatus" });
    initFlyingDays(all.fdays || {});
    initPilotFlights(all.pgf || {});
    initDuration(all.duration || {});
    // These two are defined OUTSIDE (Option B); call if available
    if (w.initInstructorByWeekday) w.initInstructorByWeekday(all.instructors || {});
    if (w.initTowByWeekday) w.initTowByWeekday(all.tows || {});
    if (w.initLongFlights3h) w.initLongFlights3h(all.long3h || {});
    if (w.initDutyDays) w.initDutyDays(all.duty || {});
    initTimeOps(all.time_ops || {});
  };

})(window);

// ---------- Global helpers used by outside initializers ----------
function makeHStacked(canvasId, names, labels, matrix, colors) {
  const ctx = document.getElementById(canvasId)?.getContext?.("2d"); if (!ctx) return null;
  const datasets = labels.map((lbl, i) => ({
    label: lbl,
    data: (matrix[lbl] || []).map(v => Number(v) || 0),
    backgroundColor: colors[i % colors.length],
    borderColor: colors[i % colors.length],
    borderWidth: 1,
  }));
  const totals = names.map((_, r) => datasets.reduce((s, ds) => s + (Number(ds.data[r]) || 0), 0));
  const xMax = Math.max(1, ...totals);
  const pad = Math.ceil((xMax * 1.08) / 10) * 10;

  return new Chart(ctx, {
    type: "bar",
    data: { labels: names, datasets },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { position: "right" } },
      scales: {
        x: { stacked: true, beginAtZero: true, suggestedMax: pad, ticks: { precision: 0 } },
        y: { stacked: true, ticks: { autoSkip: false } }
      }
    }
  });
}

// ---------- External initializers (Option B) ----------
function initInstructorByWeekday(d) {
  const names = d.names || [], labels = d.labels || [], matrix = d.matrix || {}, instTotal = d.inst_total || 0, allTotal = d.all_total || 0;
  const blues = ["#dbeafe", "#bfdbfe", "#93c5fd", "#60a5fa", "#3b82f6", "#2563eb", "#1d4ed8"];
  const el = document.getElementById("instStatus");
  if (!names.length) { if (el) el.textContent = "No instructor flights in the selected period."; return; }
  if (window.instChart?.destroy) window.instChart.destroy();
  window.instChart = makeHStacked("instChart", names, labels, matrix, blues);
  if (el) el.textContent = `${instTotal.toLocaleString()} instructional flights out of ${allTotal.toLocaleString()} total flights in range.`;
}

function initTowByWeekday(d) {
  const names = d.names || [], labels = d.labels || [], matrix = d.matrix || {}, towTotal = d.tow_total || 0;
  const greens = ["#e3f9e5", "#c1eac5", "#a3d9a5", "#7bc47f", "#57ae5b", "#3f9142", "#2f8132"];
  const el = document.getElementById("towStatus");
  if (!names.length) { if (el) el.textContent = "No tow-pilot flights in the selected period."; return; }
  if (window.towChart?.destroy) window.towChart.destroy();
  window.towChart = makeHStacked("towChart", names, labels, matrix, greens);
  if (el) el.textContent = `${towTotal.toLocaleString()} total tows in range.`;
}

function minutesToHMM(mins) {
  const m = Math.max(0, Math.round(mins || 0));
  const h = Math.floor(m / 60);
  const mm = String(m % 60).padStart(2, "0");
  return `${h}:${mm}`;
}

function initLongFlights3h(d) {
  const H = window.AnalyticsCharts?.helpers; if (!H) return;
  const names = d.names || [];
  const counts = d.counts || [];
  const longestMin = d.longest_min || 0;
  const thr = d.threshold_hours || 3;
  const status = document.getElementById("long3hStatus");

  if (!names.length) { if (status) status.textContent = `No flights ≥ ${thr} hours in the selected date range.`; return; }

  if (window.long3hChart?.destroy) window.long3hChart.destroy();
  window.long3hChart = H.makeHBar("long3hChart", names, counts, {
    color: "#6f42c1",
    xTitle: `Flights ≥ ${thr} hours`,
    legendLabel: `Flights ≥ ${thr}h`,
  });

  if (status) {
    const total = counts.reduce((a, b) => a + (Number(b) || 0), 0);
    status.textContent = `${total} long flights across ${names.length} pilots • Longest flight: ${minutesToHMM(longestMin)} (h:mm)`;
  }
}

function initDutyDays(d) {
  const names = d.names || [];
  const labels = d.labels || ["DO", "ADO"];
  const matrix = d.matrix || { "DO": [], "ADO": [] };
  const doTotal = d.do_total || 0;
  const adoTotal = d.ado_total || 0;
  const opsDays = d.ops_days_total || 0;
  const status = document.getElementById("dutyStatus");

  if (!names.length) { if (status) status.textContent = "No DO/ADO assignments in the selected date range."; return; }

  const colors = ["#f59e0b", "#14b8a6"]; // amber, teal
  const stackedMatrix = { [labels[0]]: matrix[labels[0]] || [], [labels[1]]: matrix[labels[1]] || [] };

  if (window.dutyChart?.destroy) window.dutyChart.destroy();
  window.dutyChart = makeHStacked("dutyChart", names, labels, stackedMatrix, colors);

  if (status) status.textContent =
    `Total assignment days: ${doTotal + adoTotal} (DO ${doTotal}, ADO ${adoTotal}) • Ops days in range: ${opsDays}`;
}

function initTimeOps(d) {
  const takeoffPoints = d.takeoff_points || [];
  const landingPoints = d.landing_points || [];
  const meanEarliestTakeoff = d.mean_earliest_takeoff || [];
  const meanLatestLanding = d.mean_latest_landing || [];
  const totalFlightDays = d.total_flight_days || 0;
  const status = document.getElementById("timeOpsStatus");

  if (!takeoffPoints.length && !landingPoints.length) {
    if (status) status.textContent = "No flight time data for the selected period.";
    return;
  }

  const ctx = document.getElementById("timeOpsChart")?.getContext?.("2d");
  if (!ctx) return;

  if (window.timeOpsChart?.destroy) window.timeOpsChart.destroy();

  // Helper function to format time decimal back to time string for tooltips
  const formatTime = (decimalHours) => {
    const hours = Math.floor(decimalHours);
    const minutes = Math.round((decimalHours - hours) * 60);
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
  };

  window.timeOpsChart = new Chart(ctx, {
    type: "scatter",
    data: {
      labels: [], // Defensive: Chart.js expects this sometimes
      datasets: [
        {
          label: "Earliest Takeoffs",
          data: takeoffPoints,
          backgroundColor: "#3498db", // Blue
          borderColor: "#3498db",
          pointRadius: 3,
          pointHoverRadius: 5,
        },
        {
          label: "Latest Landings",
          data: landingPoints,
          backgroundColor: "#27ae60", // Green
          borderColor: "#27ae60",
          pointRadius: 3,
          pointHoverRadius: 5,
        },
        {
          label: "Mean Earliest Takeoff",
          data: meanEarliestTakeoff,
          backgroundColor: "rgba(52, 152, 219, 0.3)", // Light blue
          borderColor: "#3498db",
          borderWidth: 2,
          pointRadius: 0,
          type: "line",
          fill: false,
          tension: 0.4, // More smoothing
        },
        {
          label: "Mean Latest Landing",
          data: meanLatestLanding,
          backgroundColor: "rgba(39, 174, 96, 0.3)", // Light green
          borderColor: "#27ae60",
          borderWidth: 2,
          pointRadius: 0,
          type: "line",
          fill: false,
          tension: 0.4, // More smoothing
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "nearest", intersect: false },
      plugins: {
        legend: { position: "right", labels: { boxWidth: 18 } },
        tooltip: {
          callbacks: {
            title: (items) => {
              if (!items.length) return "";
              const day = items[0].parsed.x;
              // Convert Julian day to approximate date for context
              const date = new Date(2024, 0, day); // Using 2024 as reference year
              const month = date.toLocaleDateString(undefined, { month: "short" });
              const dayOfMonth = date.getDate();
              return `Day ${day} (≈${month} ${dayOfMonth})`;
            },
            label: (item) => {
              const time = formatTime(item.parsed.y);
              return ` ${item.dataset.label}: ${time}`;
            }
          }
        }
      },
      scales: {
        x: {
          type: "linear",
          position: "bottom",
          title: { display: true, text: "Julian Day" },
          min: 1,
          max: 365,
          ticks: {
            stepSize: 30,
            callback: function (value) {
              // Show month labels at key points
              if ([1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335].includes(value)) {
                const date = new Date(2024, 0, value);
                return date.toLocaleDateString(undefined, { month: "short" });
              }
              return value;
            }
          }
        },
        y: {
          type: "linear",
          title: { display: true, text: "Time of Day" },
          min: 6,  // 6 AM
          max: 21, // 9 PM
          ticks: {
            stepSize: 2,
            callback: function (value) {
              return formatTime(value);
            }
          }
        }
      }
    }
  });

  if (status) {
    status.textContent = `Flight data from ${totalFlightDays} operational days • Blue: earliest takeoffs • Green: latest landings • Lines: mean times`;
  }
}

// ---------- Download buttons (PNG/SVG/CSV) ----------
function blobDownload(filename, mime, content) {
  const blob = content instanceof Blob ? content : new Blob([content], { type: mime });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 200);
}

function exportPNG(canvasId, name) {
  const chart = Chart.getChart ? Chart.getChart(canvasId) : null;
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const url = chart && typeof chart.toBase64Image === "function"
    ? chart.toBase64Image()
    : (canvas.toDataURL ? canvas.toDataURL("image/png") : null);
  if (!url) return;
  fetch(url).then(r => r.blob()).then(b => blobDownload(`${name}.png`, "image/png", b));
}

function exportSVG(canvasId, name) {
  const chart = Chart.getChart ? Chart.getChart(canvasId) : null;
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const w = canvas.width, h = canvas.height;
  const url = chart && typeof chart.toBase64Image === "function"
    ? chart.toBase64Image()
    : (canvas.toDataURL ? canvas.toDataURL("image/png") : null);
  if (!url) return;
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
  <image href="${url}" x="0" y="0" width="${w}" height="${h}" />
</svg>`;
  blobDownload(`${name}.svg`, "image/svg+xml", svg);
}

function csvEscape(v) {
  const s = String(v ?? "");
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function chartToCSV(canvasId) {
  const chart = Chart.getChart ? Chart.getChart(canvasId) : null;
  if (!chart) return "";
  const cfg = chart.config || {};
  const type = cfg.type || (cfg._config && cfg._config.type);
  const data = chart.data || (cfg.data ?? {});
  const labels = Array.isArray(data.labels) ? data.labels : [];
  const datasets = Array.isArray(data.datasets) ? data.datasets : [];

  // XY line (duration)
  if ((type === "line" || type === "scatter") && datasets.length >= 1 && datasets[0].data && typeof datasets[0].data[0] === "object") {
    // For scatter/line charts with multiple datasets of {x, y}
    const allX = new Set();
    datasets.forEach(ds => (ds.data || []).forEach(p => allX.add(p.x)));
    const sortedX = Array.from(allX).sort((a, b) => a - b);
    const header = ["x", ...datasets.map(ds => ds.label || "Series")];
    const rows = [header];
    for (const x of sortedX) {
      const row = [x];
      for (const ds of datasets) {
        const pt = (ds.data || []).find(p => p.x === x);
        row.push(pt ? pt.y : "");
      }
      rows.push(row);
    }
    return rows.map(r => r.map(csvEscape).join(",")).join("\n");
  }

  // Generic (bar/stacked)
  const header = ["Label", ...datasets.map(ds => ds.label || "Series")];
  const len = Math.max(labels.length, ...datasets.map(ds => (ds.data || []).length));
  const rows = [header];
  for (let i = 0; i < len; i++) {
    const row = [labels[i] ?? i];
    for (const ds of datasets) {
      const v = (ds.data || [])[i];
      row.push(typeof v === "object" && v !== null ? (v.y ?? "") : (v ?? ""));
    }
    rows.push(row);
  }
  return rows.map(r => r.map(csvEscape).join(",")).join("\n");
}

function exportCSV(canvasId, name) {
  const csv = chartToCSV(canvasId);
  if (!csv) return;
  blobDownload(`${name}.csv`, "text/csv;charset=utf-8", csv);
}

function attachChartDownloads() {
  document.querySelectorAll(".chart-tools").forEach((group) => {
    const canvasId = group.dataset.canvas;
    const name = group.dataset.name || canvasId || "chart";
    group.querySelectorAll(".chart-dl").forEach((btn) => {
      const type = btn.dataset.type;
      btn.onclick = () => {
        if (type === "png") return exportPNG(canvasId, name);
        if (type === "svg") return exportSVG(canvasId, name);
        if (type === "csv") return exportCSV(canvasId, name);
      };
    });
  });
}

// After charts render, bind downloads
if (window.AnalyticsCharts && window.AnalyticsCharts.initAll) {
  (function (orig) {
    window.AnalyticsCharts.initAll = function (all) {
      orig(all);
      attachChartDownloads();
    };
  })(window.AnalyticsCharts.initAll);
}
