// instruction_charts.js

(function () {

  // Ensure loader is present
  if (typeof google === 'undefined' || !google.charts) {
    console.error("⚠️ Google Charts loader.js missing or blocked");
    return;
  }

  // Kick off chart package load
  google.charts.load('current', { packages: ['corechart'] });

  // Poll for when ColumnChart is available
  let tries = 0;
  const maxTries = 50;  // ~5 seconds
  const pollInterval = 100; // ms

  const poller = setInterval(() => {
    tries++;
    if (window.google
      && google.visualization
      && typeof google.visualization.ColumnChart === 'function') {
      clearInterval(poller);
      //console.log("✅ google.visualization.ColumnChart ready, drawing charts");
      initInstructionCharts();
    } else if (tries >= maxTries) {
      clearInterval(poller);
      //console.error("❌ Timeout waiting for google.visualization.ColumnChart");
    }
  }, pollInterval);

  function initInstructionCharts() {
    //console.log("▶ initInstructionCharts called");
    const container = document.getElementById('charts-container');
    if (!container) {
      //console.warn("❗ No #charts-container found – aborting");
      return;
    }
    //console.log("raw data-attributes:", container.dataset);

    let dates, solo, rating, anchors;
    try {
      dates = JSON.parse(container.dataset.dates);
      solo = JSON.parse(container.dataset.solo);
      rating = JSON.parse(container.dataset.rating);
      anchors = JSON.parse(container.dataset.anchors);
      //console.log("parsed dates:", dates);
    } catch (err) {
      //console.error("🚨 JSON.parse failed:", err, container.dataset.dates);
      return;
    }

    // Solo chart
    drawColumnChart(
      'solo_chart',
      dates, solo, anchors,
      container.dataset.firstsolo,
      'Solo%', 'color:black', 'color:cyan',
      {
        title: 'Solo Requirements Progress',
        vAxis: {
          title: '% Complete',
          viewWindow: { min: 0, max: 100 }
        },
        hAxis: {
          title: 'Lessons',
          format: 'yyyy',
          textPosition: 'none'
        },
        bar: { groupWidth: '80%' },
        chartArea: { width: '80%', left: 50 }
      }
    );

    // Rating chart
    drawColumnChart(
      'rating_chart',
      dates, rating, anchors,
      null,
      'Rating%', 'color:rgb(35,141,35)', null,
      {
        title: 'Rating-Ready Requirements Progress',
        vAxis: {
          title: '% Complete',
          viewWindow: { min: 0, max: 100 }
        },
        hAxis: {
          title: 'Lessons',
          format: 'yyyy',
          textPosition: 'none'
        },
        bar: { groupWidth: '80%' },
        chartArea: { width: '80%', left: 50 }
      }
    );

  }



  function drawColumnChart(containerId, labels, values, anchors, highlightLabel, seriesLabel, barColor, highlightColor, options) {
    const dt = new google.visualization.DataTable();
    dt.addColumn('string', 'Session');
    dt.addColumn('number', seriesLabel);
    dt.addColumn({ type: 'string', role: 'style' });
    dt.addColumn({ type: 'string', role: 'tooltip' });

    labels.forEach((lbl, i) => {
      const isHighlight = highlightLabel && lbl === highlightLabel;
      const color = isHighlight && highlightColor ? highlightColor : barColor;
      dt.addRow([lbl, values[i], color, `${lbl}: ${values[i]}%`]);
    });

    const chart = new google.visualization.ColumnChart(
      document.getElementById(containerId)
    );
    chart.draw(dt, Object.assign({ legend: 'none', animation: { startup: true, duration: 500 } }, options));

    google.visualization.events.addListener(chart, 'select', () => {
      const sel = chart.getSelection()[0];
      if (sel && anchors && anchors[sel.row]) {
        window.location.hash = anchors[sel.row];
      }
    });
  }

})();
