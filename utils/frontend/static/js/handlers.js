// --- EVENT HANDLERS AND INTERACTION LOGIC ---

// Drag and Drop Logic
function allowDrop(ev) {
    ev.preventDefault();
    const col = ev.target.closest('.kanban-col');
    if (col) {
        // Visual feedback (optional)
    }
}

function drop(ev, targetStatusCategory) {
    ev.preventDefault();
    const jobId = parseInt(ev.dataTransfer.getData("text/plain"));
    const job = jobsData.find(j => j.id === jobId);

    if (!job) return;

    // Logic: Update status based on dropped column
    // We reset statuses and check the appropriate ones based on the drop target

    if (targetStatusCategory === 'Applied') {
        // Reset all except Applied
        job.statuses.forEach(s => {
            s.checked = (s.status === "Applied") ? 1 : 0;
            if (s.checked) s.date_reached = new Date().toISOString().split('T')[0];
        });
    } else if (targetStatusCategory === 'Interview 1') {
        // Ensure Applied is checked, set Interview 1
        const applied = job.statuses.find(s => s.status === 'Applied');
        applied.checked = 1;

        // If it was already interviewing, we don't want to reset forward progress necessarily, 
        // but for simple drag/drop grouping, let's set it to at least Interview 1
        const int1 = job.statuses.find(s => s.status === 'Interview 1');
        if (int1.checked === 0) {
            int1.checked = 1;
            int1.date_reached = new Date().toISOString().split('T')[0];
        }

        // Uncheck terminal states
        job.statuses.forEach(s => {
            if (["Offer", "Accepted", "Rejected", "Ignored/Ghosted"].includes(s.status)) {
                s.checked = 0;
            }
        });

    } else if (targetStatusCategory === 'Offer') {
        // Set Offer
        const offer = job.statuses.find(s => s.status === 'Offer');
        offer.checked = 1;
        offer.date_reached = new Date().toISOString().split('T')[0];

        // Uncheck Rejected
        job.statuses.forEach(s => {
            if (["Rejected", "Ignored/Ghosted"].includes(s.status)) s.checked = 0;
        });

    } else if (targetStatusCategory === 'Rejected') {
        // Set Rejected
        const rej = job.statuses.find(s => s.status === 'Rejected');
        rej.checked = 1;
        rej.date_reached = new Date().toISOString().split('T')[0];

        // Uncheck Offer/Accepted
        job.statuses.forEach(s => {
            if (["Offer", "Accepted"].includes(s.status)) s.checked = 0;
        });
    }

    renderAll();
}

// Job Actions
function applyJob(id) {
    const job = jobsData.find(j => j.id === id);
    job.statuses[0].checked = 1;
    job.statuses[0].date_reached = new Date().toISOString().split('T')[0];
    renderAll();
}

function ignoreJob(id) {
    const job = jobsData.find(j => j.id === id);
    if (!job) return;

    // Update locally first for immediate feedback
    job.ignore = 1;
    renderAll();

    // Send request to backend to persist the change
    fetch(`/api/jobs/${id}/ignore`, {
        method: 'PATCH',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ ignore: 1 })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Failed to ignore job');
        }
        return response.json();
    })
    .catch(error => {
        console.error('Error ignoring job:', error);
        // Revert the local change if the request fails
        job.ignore = 0;
        renderAll();
        alert('Failed to ignore job. Please try again.');
    });
}

// Tab Switching
function switchTab(tabName) {
    const jobsView = document.getElementById('view-jobs');
    const trackerView = document.getElementById('view-tracker');

    // Desktop Buttons
    const btnJobs = document.getElementById('nav-jobs');
    const btnTracker = document.getElementById('nav-tracker');

    // Mobile Buttons
    const mobJobs = document.getElementById('mob-nav-jobs');
    const mobTracker = document.getElementById('mob-nav-tracker');

    if (tabName === 'jobs') {
        jobsView.classList.remove('hidden');
        trackerView.classList.add('hidden');

        // Styles
        btnJobs.className = "px-4 py-1.5 rounded-md text-sm font-medium bg-white text-primary-700 shadow-sm transition-all";
        btnTracker.className = "px-4 py-1.5 rounded-md text-sm font-medium text-slate-600 hover:text-slate-900 transition-all";

        mobJobs.classList.replace('text-slate-400', 'text-primary-600');
        mobTracker.classList.replace('text-primary-600', 'text-slate-400');
    } else {
        jobsView.classList.add('hidden');
        trackerView.classList.remove('hidden');

        // Styles
        btnTracker.className = "px-4 py-1.5 rounded-md text-sm font-medium bg-white text-primary-700 shadow-sm transition-all";
        btnJobs.className = "px-4 py-1.5 rounded-md text-sm font-medium text-slate-600 hover:text-slate-900 transition-all";

        mobTracker.classList.replace('text-slate-400', 'text-primary-600');
        mobJobs.classList.replace('text-primary-600', 'text-slate-400');
    }
}

// Detail Panel Logic
function openJobDetails(job) {
    const panel = document.getElementById('jobDetailPanel');
    const backdrop = document.getElementById('panelBackdrop');

    document.getElementById('detailTitle').innerText = job.title;
    document.getElementById('detailCompany').innerText = job.company;
    document.getElementById('detailComp').innerText = job.compensation || "Not specified";
    document.getElementById('detailLoc').innerText = job.location;
    document.getElementById('detailDesc').innerText = job.description;

    renderTimeline(job.statuses, job.id);

    backdrop.classList.remove('hidden');
    setTimeout(() => {
        backdrop.classList.remove('opacity-0');
        panel.classList.remove('translate-x-full');
    }, 10);
}

function closePanel() {
    const panel = document.getElementById('jobDetailPanel');
    const backdrop = document.getElementById('panelBackdrop');

    panel.classList.add('translate-x-full');
    backdrop.classList.add('opacity-0');
    setTimeout(() => {
        backdrop.classList.add('hidden');
    }, 300);
}

function toggleStatus(jobId, statusIndex) {
    const job = jobsData.find(j => j.id === jobId);
    if (!job) return;

    const currentStatusState = job.statuses[statusIndex].checked;

    if (currentStatusState === 0) {
        job.statuses[statusIndex].checked = 1;
        job.statuses[statusIndex].date_reached = new Date().toISOString().split('T')[0];
    } else {
        job.statuses[statusIndex].checked = 0;
        job.statuses[statusIndex].date_reached = null;
    }

    renderTimeline(job.statuses, jobId);
    renderAll();
}

// --- SIDEBAR TOGGLE ---
function toggleSidebar() {
    const sidebar = document.getElementById('filters-sidebar');
    sidebar.classList.toggle('sidebar-hidden');
}