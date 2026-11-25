/**
 * EnerTrack Dashboard & Anomaly Investigation Interactivity
 */

async function viewAnomalyDetails(anomalyId) {
  try {
    const res = await fetch(`/anomalies/${anomalyId}/details`);
    if (!res.ok) throw new Error("Could not load anomaly details");
    const a = await res.json();

    // Populate Modal Elements
    document.getElementById("modalAnomalyId").innerText = `#ANM-${a.anomaly_id}`;
    document.getElementById("modalHousehold").innerText = a.household_name || "N/A";
    document.getElementById("modalMeter").innerText = a.meter_number || "N/A";
    document.getElementById("modalTimestamp").innerText = a.detection_timestamp;
    
    document.getElementById("modalObservedKwh").innerText = `${a.energy_kwh} kWh`;
    document.getElementById("modalExpectedKwh").innerText = `${a.expected_kwh} kWh`;
    
    const diffSign = a.diff_kwh >= 0 ? "+" : "";
    document.getElementById("modalDiffKwh").innerText = `${diffSign}${a.diff_kwh} kWh (${a.pct_increase}%)`;
    document.getElementById("modalAnomalyScore").innerText = a.anomaly_score.toFixed(3);
    document.getElementById("modalMethod").innerText = a.method;
    
    // Severity pill
    const sevPill = document.getElementById("modalSeverityPill");
    sevPill.innerText = a.severity;
    sevPill.className = "pill";
    if (a.severity === "High Priority") {
      sevPill.classList.add("pill-high-priority");
    } else if (a.severity === "Unusual") {
      sevPill.classList.add("pill-unusual");
    } else {
      sevPill.classList.add("pill-normal");
    }

    // Explanations list
    const causesList = document.getElementById("modalCausesList");
    causesList.innerHTML = "";
    if (a.possible_causes && a.possible_causes.length > 0) {
      a.possible_causes.forEach(cause => {
        const li = document.createElement("li");
        li.innerText = cause;
        causesList.appendChild(li);
      });
    } else {
      causesList.innerHTML = "<li>No specific automated hypotheses available.</li>";
    }

    // Recommendations list
    const recsList = document.getElementById("modalRecsList");
    recsList.innerHTML = "";
    if (a.recommendations && a.recommendations.length > 0) {
      a.recommendations.forEach(rec => {
        const li = document.createElement("li");
        li.innerText = rec;
        recsList.appendChild(li);
      });
    } else {
      recsList.innerHTML = "<li>No specific actions logged.</li>";
    }

    // Status Form
    const form = document.getElementById("anomalyStatusForm");
    if (form) {
      form.action = `/anomalies/${a.anomaly_id}/status`;
      document.getElementById("statusSelect").value = a.status;
      document.getElementById("statusNotes").value = a.notes || "";
    }

    openModal("anomalyDetailsModal");
  } catch (err) {
    alert("Error fetching anomaly details: " + err.message);
  }
}
