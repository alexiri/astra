(function () {
  function renderElectionTurnoutChart() {
    // This log is intentionally very early so we can confirm the script executes at all.
    console.log('[turnout-chart] script loaded');

    var dataEl = document.getElementById('election-turnout-chart-data');
    var canvasEl = document.getElementById('election-turnout-chart');

    if (!dataEl) {
      console.warn('[turnout-chart] JSON payload element missing');
      return;
    }
    if (!canvasEl) {
      console.warn('[turnout-chart] canvas element missing');
      return;
    }
    if (!window.Chart) {
      console.warn('[turnout-chart] Chart.js not loaded (window.Chart missing)');
      return;
    }

    var payload = {};
    try {
      payload = JSON.parse(String(dataEl.textContent || '{}'));
    } catch (_e) {
      payload = {};
    }
    console.log('[turnout-chart] payload:', payload);

    var labels = Array.isArray(payload.labels) ? payload.labels : [];
    var counts = Array.isArray(payload.counts) ? payload.counts : [];

    var ctx = canvasEl.getContext('2d');
    if (!ctx) {
      console.warn('[turnout-chart] unable to get 2d context from canvas');
      return;
    }

    // If the user navigates away/back with bfcache, avoid double-rendering.
    if (canvasEl.dataset.turnoutChartRendered === '1') return;
    canvasEl.dataset.turnoutChartRendered = '1';

    new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Ballots submitted',
            backgroundColor: 'rgba(60,141,188,0.9)',
            borderColor: 'rgba(60,141,188,0.8)',
            data: counts,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              precision: 0,
            },
          },
        },
        plugins: {
          legend: {
            display: false,
          },
        }
      },
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderElectionTurnoutChart);
  } else {
    renderElectionTurnoutChart();
  }
})();
