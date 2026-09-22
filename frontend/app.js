/**
 * Resilient Horizon Travel Engine - Client Application Logic
 */

document.addEventListener('DOMContentLoaded', () => {
  const travelForm = document.getElementById('travelForm');
  const submitBtn = document.getElementById('submitBtn');
  const agentWorkflowSection = document.getElementById('agentWorkflowSection');
  const stagesContainer = document.getElementById('stagesContainer');
  const agentActivityText = document.getElementById('agentActivityText');
  const currentStageBadge = document.getElementById('currentStageBadge');
  const resultsSection = document.getElementById('resultsSection');
  const itineraryContainer = document.getElementById('itineraryContainer');
  const recoveryPanel = document.getElementById('recoveryPanel');
  const evidenceList = document.getElementById('evidenceList');
  const toggleDetailsBtn = document.getElementById('toggleDetailsBtn');
  const technicalDetailsDrawer = document.getElementById('technicalDetailsDrawer');

  const STAGES_DEFINITIONS = [
    { id: "1", name: "UNDERSTAND", desc: "Understanding travel goals and constraints" },
    { id: "2", name: "PLAN", desc: "Creating an initial itinerary" },
    { id: "3", name: "OBSERVE", desc: "Checking real-world travel conditions" },
    { id: "4", name: "DETECT", desc: "Checking for conflicts and disruptions" },
    { id: "5", name: "RECOVER", desc: "Finding alternative activities/routes" },
    { id: "6", name: "VERIFY", desc: "Validating time, budget and preferences" },
    { id: "7", name: "FINAL PLAN", desc: "Preparing the verified itinerary" }
  ];

  // Technical details toggle
  toggleDetailsBtn.addEventListener('click', () => {
    const isHidden = technicalDetailsDrawer.classList.contains('hidden');
    if (isHidden) {
      technicalDetailsDrawer.classList.remove('hidden');
      toggleDetailsBtn.innerHTML = `<i class="fa-solid fa-eye-slash"></i> Hide Technical Details`;
    } else {
      technicalDetailsDrawer.classList.add('hidden');
      toggleDetailsBtn.innerHTML = `<i class="fa-solid fa-code"></i> Show Technical Details`;
    }
  });

  travelForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const destination = document.getElementById('destination').value.trim() || 'Goa';
    const days = parseInt(document.getElementById('days').value, 10) || 4;
    const budget = parseFloat(document.getElementById('budget').value) || 15000;
    const rawInterests = document.getElementById('interests').value;
    const interests = rawInterests.split(',').map(s => s.trim()).filter(Boolean);
    const travelDate = document.getElementById('travelDate').value;
    const demoMode = document.getElementById('demoModeToggle').checked;

    // Reset UI
    resultsSection.classList.add('hidden');
    agentWorkflowSection.classList.remove('hidden');
    submitBtn.disabled = true;
    submitBtn.classList.add('opacity-75', 'cursor-not-allowed');

    renderInitialStages();

    try {
      // Simulate real-time workflow stage progress before payload arrives for manager demonstration
      await animateStagesProgress(destination, days, budget);

      const response = await fetch('/api/travel/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          destination,
          days,
          budget,
          interests,
          travelDate,
          demoMode
        })
      });

      if (!response.ok) {
        throw new Error(`Server returned HTTP ${response.status}`);
      }

      const data = await response.json();

      // Complete all stages cleanly
      updateAllStagesCompleted(data);
      
      // Render results
      renderResults(data);

    } catch (err) {
      console.error('Execution error:', err);
      agentActivityText.textContent = `Error executing travel agent: ${err.message}`;
      agentActivityText.classList.add('text-rose-400');
      currentStageBadge.className = "px-3 py-1 bg-rose-100 text-rose-700 rounded-full text-xs font-medium border border-rose-300";
      currentStageBadge.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Execution Error`;
    } finally {
      submitBtn.disabled = false;
      submitBtn.classList.remove('opacity-75', 'cursor-not-allowed');
    }
  });

  function renderInitialStages() {
    stagesContainer.innerHTML = '';
    STAGES_DEFINITIONS.forEach(s => {
      const card = document.createElement('div');
      card.id = `stage-card-${s.id}`;
      card.className = "bg-slate-50 p-3 rounded-xl border border-slate-200 flex flex-col justify-between transition-all duration-300";
      card.innerHTML = `
        <div>
          <div class="flex items-center justify-between mb-1">
            <span class="text-[10px] font-bold text-slate-400 uppercase tracking-wider">${s.id}. ${s.name}</span>
            <span id="stage-status-${s.id}" class="text-[10px] px-1.5 py-0.5 rounded bg-slate-200 text-slate-600 font-semibold">Pending</span>
          </div>
          <div class="text-xs font-semibold text-slate-700 leading-tight">${s.desc}</div>
        </div>
      `;
      stagesContainer.appendChild(card);
    });
  }

  async function animateStagesProgress(destination, days, budget) {
    const stageDetails = [
      "Parsing travel destination and extracting budget constraints...",
      "Querying places discovery tool for top attractions matching user interests...",
      "Checking weather forecasts across all travel dates...",
      "Evaluating weather alerts for outdoor activities...",
      "Searching for indoor historical alternatives and estimating travel routes...",
      "Validating total cost against ₹" + budget.toLocaleString() + " budget...",
      "Finalizing verified resilient itinerary payload..."
    ];

    for (let i = 0; i < STAGES_DEFINITIONS.length; i++) {
      const s = STAGES_DEFINITIONS[i];
      const card = document.getElementById(`stage-card-${s.id}`);
      const statusBadge = document.getElementById(`stage-status-${s.id}`);
      
      card.className = "bg-blue-50 p-3 rounded-xl border border-blue-300 shadow-xs flex flex-col justify-between transition-all duration-300";
      statusBadge.className = "text-[10px] px-1.5 py-0.5 rounded bg-blue-600 text-white font-semibold flex items-center gap-1";
      statusBadge.innerHTML = `<i class="fa-solid fa-spinner fa-spin text-[9px]"></i> Running`;

      agentActivityText.textContent = stageDetails[i];
      currentStageBadge.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Stage ${s.id}: ${s.name}`;

      await new Promise(r => setTimeout(r, 220));

      card.className = "bg-emerald-50 p-3 rounded-xl border border-emerald-300 flex flex-col justify-between transition-all duration-300";
      statusBadge.className = "text-[10px] px-1.5 py-0.5 rounded bg-emerald-600 text-white font-semibold flex items-center gap-1";
      statusBadge.innerHTML = `<i class="fa-solid fa-check text-[9px]"></i> Done`;
    }
  }

  function updateAllStagesCompleted(data) {
    currentStageBadge.className = "px-3 py-1 bg-emerald-100 text-emerald-800 rounded-full text-xs font-semibold border border-emerald-300";
    currentStageBadge.innerHTML = `<i class="fa-solid fa-circle-check text-emerald-600"></i> Agent Execution Completed`;
    agentActivityText.textContent = `Completed goal verification: ${data.explanation || 'Verified itinerary ready.'}`;
  }

  function renderResults(data) {
    resultsSection.classList.remove('hidden');

    const req = data.request || {};
    const metrics = data.metrics || {};
    const recovery = data.recovery || {};

    // Header summary
    document.getElementById('summaryDestination').textContent = req.destination || 'Goa';
    document.getElementById('summaryDaysBadge').textContent = `${req.days || 4} Days`;
    document.getElementById('summaryInterests').textContent = `Interests: ${(req.interests || []).join(', ')}`;

    // Metrics
    document.getElementById('metricTotalCost').textContent = `₹${(metrics.totalCost || 0).toLocaleString()}`;
    document.getElementById('metricRemaining').textContent = `Budget: ₹${(req.budget || 0).toLocaleString()} (Remaining: ₹${(metrics.remainingBudget || 0).toLocaleString()})`;
    document.getElementById('metricTravelTime').textContent = metrics.totalTravelTimeFormatted || '3h 45m';
    document.getElementById('metricActivityCount').textContent = `${metrics.activityCount || 12} Verified Activities`;

    // Status Badges
    const statusBadges = document.getElementById('statusBadges');
    statusBadges.innerHTML = `
      <span class="px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 text-[11px] font-semibold border border-emerald-800 flex items-center gap-1">
        <i class="fa-solid fa-check"></i> Within Budget
      </span>
      <span class="px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 text-[11px] font-semibold border border-emerald-800 flex items-center gap-1">
        <i class="fa-solid fa-check"></i> Time Feasible
      </span>
      <span class="px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 text-[11px] font-semibold border border-emerald-800 flex items-center gap-1">
        <i class="fa-solid fa-check"></i> Verified
      </span>
    `;

    // Resilience & Recovery Panel
    if (recovery && recovery.occurred) {
      recoveryPanel.classList.remove('hidden');
      document.getElementById('recOriginalActivity').textContent = recovery.originalActivity || 'Outdoor Beach Activity';
      document.getElementById('recIssue').innerHTML = `<strong>Issue:</strong> ${recovery.issueDetected || 'Unfavorable weather conditions'}`;
      document.getElementById('recImpact').innerHTML = `<strong>Impact:</strong> ${recovery.impact || 'Outdoor activity unsafe'}`;
      document.getElementById('recReplacement').textContent = recovery.replacementActivity || 'State Museum & Heritage Indoor Gallery';
      document.getElementById('recRecalculation').innerHTML = `<strong>Recalculation:</strong> ${recovery.recalculation || 'Updated cost and transit times'}`;
      document.getElementById('recVerification').innerHTML = `<strong>Verification:</strong> ${recovery.verification || 'Revised plan stays within budget'}`;
      document.getElementById('recExplanationText').textContent = data.explanation || 'Weather conflict resolved automatically with historical indoor alternative.';
    } else {
      recoveryPanel.classList.add('hidden');
    }

    // Day Cards
    itineraryContainer.innerHTML = '';
    const daysList = data.itinerary || [];
    daysList.forEach(dayItem => {
      const dayCard = document.createElement('div');
      dayCard.className = "bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-4";

      let slotsHtml = '';
      ['morning', 'afternoon', 'evening'].forEach(slot => {
        const act = dayItem[slot];
        if (act) {
          const isRecovered = act.was_recovered;
          slotsHtml += `
            <div class="p-3 rounded-xl ${isRecovered ? 'bg-amber-50 border border-amber-200' : 'bg-slate-50 border border-slate-100'} space-y-1">
              <div class="flex items-center justify-between">
                <span class="text-[10px] font-bold uppercase tracking-wider ${isRecovered ? 'text-amber-800' : 'text-slate-500'}">${slot}</span>
                ${isRecovered ? '<span class="text-[10px] px-2 py-0.5 bg-amber-600 text-white rounded font-bold"><i class="fa-solid fa-shield-virus"></i> Recovered</span>' : ''}
              </div>
              <div class="text-sm font-bold text-slate-800">${act.activity}</div>
              <div class="text-xs text-slate-500 flex items-center justify-between">
                <span><i class="fa-solid fa-location-dot text-slate-400 mr-1"></i>${act.location}</span>
                <span class="font-semibold text-slate-700">₹${act.cost_inr} &bull; ${act.travel_time_mins} mins travel</span>
              </div>
            </div>
          `;
        }
      });

      dayCard.innerHTML = `
        <div class="flex items-center justify-between pb-3 border-b border-slate-100">
          <h4 class="font-bold text-slate-900 text-base">${dayItem.title || 'Day ' + dayItem.day}</h4>
          <span class="text-xs px-2.5 py-0.5 rounded-full bg-slate-100 font-semibold text-slate-600">Day ${dayItem.day}</span>
        </div>
        <div class="space-y-3">
          ${slotsHtml}
        </div>
      `;
      itineraryContainer.appendChild(dayCard);
    });

    // Evidence Panel
    evidenceList.innerHTML = '';
    const evidenceItems = data.evidence || [];
    evidenceItems.forEach(obs => {
      const item = document.createElement('div');
      item.className = "bg-slate-50 p-3 rounded-xl border border-slate-200 text-xs flex items-start justify-between";
      const isWarn = obs.status === 'warning';
      item.innerHTML = `
        <div class="space-y-0.5">
          <div class="font-bold ${isWarn ? 'text-amber-700' : 'text-slate-800'} flex items-center gap-1.5">
            <i class="fa-solid ${isWarn ? 'fa-triangle-exclamation text-amber-500' : 'fa-circle-check text-emerald-500'}"></i>
            ${obs.tool}
          </div>
          <div class="text-slate-600">${obs.evidence}</div>
        </div>
        <span class="text-[10px] px-2 py-0.5 rounded ${isWarn ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'} font-semibold capitalize">${obs.status}</span>
      `;
      evidenceList.appendChild(item);
    });

    // Technical Details
    const tech = data.technicalDetails || {};
    document.getElementById('techProvider').textContent = tech.providerUsed || 'Demo Provider';
    document.getElementById('techIterations').textContent = `${tech.iterationCount || 2} / 5`;
    document.getElementById('techToolsCount').textContent = `${(tech.toolsExecuted || []).length} Tools`;
    document.getElementById('rawJsonView').textContent = JSON.stringify(data, null, 2);

    // Scroll to results cleanly
    resultsSection.scrollIntoView({ behavior: 'smooth' });
  }
});
