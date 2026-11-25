/**
 * EnerTrack Interactive Chart Engine (Chart.js)
 * Visualizes smart-meter telemetry trends, 24h diurnal profiles, anomaly distributions,
 * and multi-household comparative load analytics.
 */

// Global Chart.js Dark Theme Configuration
if (typeof Chart !== "undefined") {
  Chart.defaults.color = "#94A3B8";
  Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";
  Chart.defaults.plugins.tooltip.backgroundColor = "#0F172A";
  Chart.defaults.plugins.tooltip.titleColor = "#F8FAFC";
  Chart.defaults.plugins.tooltip.bodyColor = "#94A3B8";
  Chart.defaults.plugins.tooltip.borderColor = "rgba(56, 189, 248, 0.3)";
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 6;
}

let trendChartInstance = null;
let hourlyChartInstance = null;
let distributionChartInstance = null;
let householdCompChartInstance = null;

/**
 * 1. Daily Consumption Trend Line Chart
 */
async function loadConsumptionTrendChart(canvasId, householdId = null, days = 30) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  try {
    let url = `/api/charts/consumption-trend?days=${days}`;
    if (householdId) url += `&household_id=${householdId}`;

    const res = await fetch(url);
    if (!res.ok) throw new Error("Failed to load trend data");
    const data = await res.json();

    if (trendChartInstance) {
      trendChartInstance.destroy();
    }

    const ctx = canvas.getContext("2d");
    
    // Create subtle vertical gradient for line fill
    const gradient = ctx.createLinearGradient(0, 0, 0, 280);
    gradient.addColorStop(0, "rgba(56, 189, 248, 0.28)");
    gradient.addColorStop(1, "rgba(56, 189, 248, 0.0)");

    if (data.datasets && data.datasets[0]) {
      data.datasets[0].backgroundColor = gradient;
    }

    trendChartInstance = new Chart(ctx, {
      type: "line",
      data: data,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: true,
            position: "top",
            labels: { boxWidth: 12, boxHeight: 12, usePointStyle: true, pointStyle: "circle" }
          }
        },
        scales: {
          x: {
            grid: { color: "rgba(255, 255, 255, 0.05)" },
            ticks: { maxRotation: 45, minRotation: 0, autoSkip: true, maxTicksLimit: 12 }
          },
          y: {
            grid: { color: "rgba(255, 255, 255, 0.06)" },
            title: { display: true, text: "Energy (kWh)", color: "#64748B" },
            beginAtZero: true
          }
        }
      }
    });
  } catch (err) {
    console.error("Error rendering consumption trend chart:", err);
  }
}

/**
 * 2. Hourly Diurnal Usage Profile Chart (24-Hour Cycle)
 */
async function loadHourlyPatternChart(canvasId, householdId = null) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  try {
    let url = `/api/charts/hourly-pattern`;
    if (householdId) url += `?household_id=${householdId}`;

    const res = await fetch(url);
    if (!res.ok) throw new Error("Failed to load hourly pattern data");
    const data = await res.json();

    if (hourlyChartInstance) {
      hourlyChartInstance.destroy();
    }

    const ctx = canvas.getContext("2d");
    hourlyChartInstance = new Chart(ctx, {
      type: "bar",
      data: data,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: true,
            position: "top",
            labels: { boxWidth: 12, boxHeight: 12, usePointStyle: true }
          }
        },
        scales: {
          x: {
            grid: { display: false }
          },
          y: {
            grid: { color: "rgba(255, 255, 255, 0.06)" },
            title: { display: true, text: "kWh / Hour", color: "#64748B" },
            beginAtZero: true
          }
        }
      }
    });
  } catch (err) {
    console.error("Error rendering hourly pattern chart:", err);
  }
}

/**
 * 3. Anomaly Severity Distribution Doughnut Chart
 */
async function loadAnomalyDistributionChart(canvasId, householdId = null) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  try {
    let url = `/api/charts/anomaly-distribution`;
    if (householdId) url += `?household_id=${householdId}`;

    const res = await fetch(url);
    if (!res.ok) throw new Error("Failed to load anomaly distribution data");
    const data = await res.json();

    if (distributionChartInstance) {
      distributionChartInstance.destroy();
    }

    const ctx = canvas.getContext("2d");
    distributionChartInstance = new Chart(ctx, {
      type: "doughnut",
      data: data,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "70%",
        plugins: {
          legend: {
            position: "bottom",
            labels: { boxWidth: 12, padding: 16 }
          }
        }
      }
    });
  } catch (err) {
    console.error("Error rendering anomaly distribution chart:", err);
  }
}

/**
 * 4. Multi-Household Comparison Chart
 */
async function loadHouseholdComparisonChart(canvasId) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  try {
    const res = await fetch("/api/charts/household-comparison");
    if (!res.ok) throw new Error("Failed to load comparison data");
    const data = await res.json();

    if (householdCompChartInstance) {
      householdCompChartInstance.destroy();
    }

    const ctx = canvas.getContext("2d");
    householdCompChartInstance = new Chart(ctx, {
      type: "bar",
      data: data,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: "y", // Horizontal Bar
        plugins: {
          legend: { display: false }
        },
        scales: {
          x: {
            grid: { color: "rgba(255, 255, 255, 0.06)" },
            title: { display: true, text: "Total Lifetime Consumption (kWh)", color: "#64748B" },
            beginAtZero: true
          },
          y: {
            grid: { display: false }
          }
        }
      }
    });
  } catch (err) {
    console.error("Error rendering household comparison chart:", err);
  }
}

// Auto-initialize charts if elements exist on current page
document.addEventListener("DOMContentLoaded", function () {
  const params = new URLSearchParams(window.location.search);
  const householdId = params.get("household_id");

  if (document.getElementById("consumptionTrendChart")) {
    loadConsumptionTrendChart("consumptionTrendChart", householdId, 30);
  }
  if (document.getElementById("hourlyPatternChart")) {
    loadHourlyPatternChart("hourlyPatternChart", householdId);
  }
  if (document.getElementById("anomalyDistributionChart")) {
    loadAnomalyDistributionChart("anomalyDistributionChart", householdId);
  }
  if (document.getElementById("householdComparisonChart")) {
    loadHouseholdComparisonChart("householdComparisonChart");
  }
});
