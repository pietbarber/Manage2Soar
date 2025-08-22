/* global Chart */
;(function (w) {
  const $ = (id) => document.getElementById(id);
  const parseBlob = (id) => {
    const el = $(id); if (!el) return {};
    try { return JSON.parse(el.textContent || "{}"); } catch { return {}; }
  };

  // ----- helpers -----
  function makeHBar(canvasId, labels, values, { color="#1f77b4", xTitle="", legendLabel="" }={}) {
    const ctx = $(canvasId)?.getContext?.("2d"); if (!ctx) return null;
    const maxVal = Math.max(1, ...values.map(v => Number(v)||0));
    const padMax = Math.ceil((maxVal*1.05)/5)*5;
    return new Chart(ctx, {
      type: "bar",
      data: { labels, datasets: [{ label: legendLabel, data: values, backgroundColor: color, borderColor: color, borderWidth: 1 }]},
      options: {
        indexAxis: "y", responsive: true, maintainAspectRatio: false, animation: false,
        plugins: { legend: { display: !!legendLabel, position: "right" } },
        scales: {
          x: { beginAtZero: true, suggestedMax: padMax, ticks: { precision: 0 }, title: { display: !!xTitle, text: xTitle }},
          y: { ticks: { autoSkip: false } }
        }
      }
    });
  }

  function makeCDF(canvasId, points, { color="#5dade2", xTitle="Duration (hours)" } = {}) {
    const ctx = document.getElementById(canvasId)?.getContext?.("2d");
    if (!ctx) return null;
  
    const topBand = points.map(p => ({ x: p.x, y: 0 }));     // now: fill down from 0%

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
            reverse: true,       // 0% at top, 100% at bottom
            min: 0, max: 100,
            title: { display: true, text: "Percent of flights (≥ x)" },
            ticks: { callback: (v) => `${v}%` }
          }
        }
      }
    });
  }


  // ----- chart initializers -----
  function initCumulative(d) {
    const L = d.labels || [], years = d.years || [], dataByYear = d.data || {};
    const totals = d.totals || {}, instr = d.instr || {};
    const currentYear = d.current_year;

    const anchors = {1:"Jan",32:"Feb",60:"Mar",91:"Apr",121:"May",152:"Jun",182:"Jul",213:"Aug",244:"Sep",274:"Oct",305:"Nov",335:"Dec"};
    const colorForYear = (y) => { const base=(y*9301+49297)%233280; const hue=(base/233280)*360; return `hsl(${hue},60%,45%)`; };
    const doyToday = () => { const t=new Date(); return Math.floor((t - new Date(t.getFullYear(),0,0))/86400000); };
    const todayYear = new Date().getFullYear(), todayDoy = doyToday();

    const datasets = years.map((y) => {
      const c=colorForYear(y), isCurrent=y===currentYear, arr=(dataByYear[String(y)]||[]).slice();
      if (isCurrent && y===todayYear) { for (let i=todayDoy;i<arr.length;i++) arr[i]=null; }
      return {
        label:String(y), data:arr, borderColor:c, backgroundColor:c, tension:0.2,
        borderWidth:isCurrent?3:1.5, borderDash:isCurrent?undefined:[5,4],
        pointRadius:isCurrent?3:0, pointHoverRadius:isCurrent?5:3,
        pointBackgroundColor:isCurrent?"#fff":undefined, pointBorderColor:isCurrent?c:undefined, pointBorderWidth:isCurrent?2:0, spanGaps:false
      };
    });

    const flatMax = datasets.reduce((m,ds)=>Math.max(m, Math.max(0,...(ds.data||[]).filter(v=>v!=null))), 0);
    const yMax = Math.max(10, Math.ceil((flatMax*1.05)/50)*50);

    if (w.cumuChart?.destroy) w.cumuChart.destroy();
    const ctx = $("cumuChart")?.getContext?.("2d"); if (!ctx) return;
    w.cumuChart = new Chart(ctx, {
      type:"line",
      data:{ labels:L, datasets },
      options:{
        responsive:true, maintainAspectRatio:false, animation:false, interaction:{mode:"nearest",intersect:false},
        plugins:{ legend:{position:"left",labels:{boxWidth:18}}, tooltip:{ callbacks:{
          title:(items)=>{ if(!items.length) return ""; const i=items[0]; const y=Number(i.dataset.label); const doy=L[i.dataIndex]; const dte=new Date(y,0,doy); const month=dte.toLocaleString(undefined,{month:"short"}); const day=dte.getDate(); return `${y} • Day ${doy} (${month} ${day})`; },
          label:(item)=>{ const y=String(item.dataset.label); const val=item.parsed.y; const tot=totals[y]??val; const ins=instr[y]??0; const pct=tot?Math.round((ins/tot)*100):0; return ` ${val} flights (total ${tot}, ${ins} instruction • ${pct}%)`; }
        }}},
        scales:{
          x:{ title:{display:true,text:"Julian Day (1–365)"}, ticks:{ callback:(_,idx)=>anchors[L[idx]]||"", maxRotation:0, autoSkip:false },
              grid:{ color:(c)=> anchors[L[c.index]] ? undefined : "rgba(0,0,0,0)" } },
          y:{ beginAtZero:true, max:yMax, ticks:{precision:0}, title:{display:true,text:"Cumulative Flights"} }
        }
      }
    });
  }

  function initByAircraft(d) {
    const years = d.years||[], cats=d.cats||[], matrix=d.matrix||{};
    const colorForCategory = (cat, i) => cat==="Private" ? "#BDBDBD" : cat==="Other" ? "#9E9E9E" : cat==="Unknown" ? "#8E44AD" : `hsl(${(i*137.508)%360},65%,48%)`;
    const datasets = cats.map((cat,i)=>({ label:cat, data:(matrix[cat]||[]).map(v=>Number(v)||0), backgroundColor:colorForCategory(cat,i), borderColor:colorForCategory(cat,i), borderWidth:1 }));
    const totals = years.map((_,i)=>datasets.reduce((s,ds)=>s+(Number(ds.data[i])||0),0));
    const yMax = Math.max(10, Math.ceil((Math.max(0,...totals)*1.10)/50)*50);

    if (w.byAcftChart?.destroy) w.byAcftChart.destroy();
    const ctx = $("byAcftChart")?.getContext?.("2d"); if (!ctx) return;
    w.byAcftChart = new Chart(ctx, {
      type:"bar",
      data:{ labels: years.map(String), datasets },
      options:{
        responsive:true, maintainAspectRatio:false, animation:false,
        plugins:{ legend:{position:"left"}, tooltip:{ callbacks:{
          title:(items)=> items[0]?.label ?? "", label:(it)=>` ${it.dataset.label}: ${it.formattedValue}`,
          footer:(items)=>{ const i=items[0]?.dataIndex??0; return `Total: ${totals[i]||0}`; }
        }}},
        scales:{ x:{stacked:true,title:{display:true,text:"Year"}}, y:{stacked:true,beginAtZero:true,suggestedMax:yMax,title:{display:true,text:"Flights"},ticks:{precision:0}} }
      }
    });
  }

  function initUtilization(d, {canvasId, statusId}) {
    const names=d.names||[], flights=d.flights||[], hours=d.hours||[], avgm=d.avgm||[];
    const C_FLIGHTS="#e74c3c", C_HOURS="#3498db", C_AVG="#8bc34a";
    const xMax = Math.max(1, ...flights.map(Number), ...hours.map(Number), ...avgm.map(Number));
    const padMax = Math.ceil((xMax*1.05)/20)*20;

    if (!names.length) { $(statusId)&&($(statusId).textContent="No utilization data for the selected period."); return; }
    if (w[canvasId]?.destroy) w[canvasId].destroy();
    const ctx = $(canvasId)?.getContext?.("2d"); if(!ctx) return;

    w[canvasId] = new Chart(ctx, {
      type:"bar",
      data:{ labels:names, datasets:[
        { label:"Total Flights", data:flights, backgroundColor:C_FLIGHTS, borderColor:C_FLIGHTS, borderWidth:1 },
        { label:"Total Hours",   data:hours,   backgroundColor:C_HOURS,   borderColor:C_HOURS,   borderWidth:1 },
        { label:"Avg Flight (min)", data:avgm, backgroundColor:C_AVG, borderColor:C_AVG, borderWidth:1 },
      ]},
      options:{
        indexAxis:"y", responsive:true, maintainAspectRatio:false, animation:false,
        plugins:{ legend:{position:"right"}, tooltip:{ callbacks:{
          label:(it)=>{ const ds=it.dataset.label; const v=Number(it.formattedValue); if(ds==="Total Hours") return ` ${ds}: ${v.toFixed(1)} h`; if(ds==="Avg Flight (min)") return ` ${ds}: ${Math.round(v)} min`; return ` ${ds}: ${v}`; }
        }}},
        scales:{ x:{beginAtZero:true,suggestedMax:padMax,title:{display:true,text:"Flights / Hours / Minutes (scaled)"},ticks:{precision:0}}, y:{ticks:{autoSkip:false}} }
      }
    });
    $(statusId)&&($(statusId).textContent="");
  }

  function initFlyingDays(d) {
    const names=d.names||[], days=d.days||[], ops=d.ops_total||0;
    if (!names.length) { $("fdStatus") && ( $("fdStatus").textContent = "No flying-day data for the selected period." ); return; }
    makeHBar("fdChart", names, days, { color:"#1f3a93", xTitle:"Days with flying activity", legendLabel:"Days" });
    $("fdStatus") && ( $("fdStatus").textContent = `Members with ≥2 days. Ops days this period: ${ops}.` );
  }

  function initPilotFlights(d) {
    const names=d.names||[], counts=d.counts||[];
    if (!names.length) { $("pgfStatus") && ( $("pgfStatus").textContent = "No pilot-flight data for the selected period." ); return; }
    makeHBar("pgfChart", names, counts, { color:"#e74c3c", xTitle:"Flights", legendLabel:"Flights" });
    $("pgfStatus") && ( $("pgfStatus").textContent = "Members with ≥2 non-instruction glider flights." );
  }

  function initDuration(d) {
    const pts = Array.isArray(d.points) && d.points.length
      ? d.points
      : (Array.isArray(d.x_hours) ? d.x_hours.map((x,i)=>({x, y:(d.cdf_pct||[])[i]||0})) : []);
  
    if (!pts.length) { const el=document.getElementById("durStatus"); if(el) el.textContent="No duration data for the selected period."; return; }
  
    if (window.durChart?.destroy) window.durChart.destroy();
    window.durChart = makeCDF("durChart", pts, { color:"#5dade2" });
  
    const med = d.median_min || 0, p = d.pct_gt || {"1":0,"2":0,"3":0};
    const s = document.getElementById("durStatus");
    if (s) s.textContent = `Median = ${med} min • Over 1h: ${p["1"]}% • Over 2h: ${p["2"]}% • Over 3h: ${p["3"]}%`;
  }

  // public
  w.AnalyticsCharts = {
    initAll(all) {
      if (!all || typeof all !== "object") return;
      initCumulative(all.cumulative || {});
      initByAircraft(all.by_acft || {});
      initUtilization(all.util || {},      {canvasId:"utilChart",    statusId:"utilStatus"});
      initUtilization(all.util_priv || {}, {canvasId:"utilPrivChart", statusId:"utilPrivStatus"});
      initFlyingDays(all.fdays || {});
      initPilotFlights(all.pgf || {});
      initDuration(all.duration || {});
    }
  };
})(window);
