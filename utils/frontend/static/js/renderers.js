// --- RENDER FUNCTIONS ---
let currentPage = 1;
const itemsPerPage = 50;

window.changePage = function (page) {
    currentPage = page;
    renderAll();
    // Scroll to top of main container
    const mainContainer = document.getElementById('mainContainer');
    if (mainContainer) {
        mainContainer.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

// --- HELPER FUNCTIONS ---

// Format date from datetime string to YYYY-MM-DD
function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toISOString().split('T')[0]; // YYYY-MM-DD
}

// Validate and format compensation
function formatCompensation(comp) {
    if (!comp || comp === 'nan' || comp.toLowerCase().includes('nan') || comp === 'NaN') {
        return 'Not Listed';
    }
    return comp;
}

// Process description HTML
function formatDescription(desc) {
    // Return null for empty, null, or undefined descriptions
    if (!desc) return null;

    // Trim and check if it's actually empty
    const trimmed = desc.trim();
    if (trimmed === '' || trimmed.length === 0) return null;

    let formatted = trimmed;

    // Remove escaped backslashes (e.g., \- becomes -)
    formatted = formatted.replace(/\\(.)/g, '$1');

    // Convert markdown-style bold to HTML
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

    // Clean up excessive blank lines (3+ newlines become 2)
    formatted = formatted.replace(/\n{3,}/g, '\n\n');

    // Convert markdown headings to HTML (must be done before list processing)
    // Process from most specific (####) to least specific (#) to avoid conflicts
    formatted = formatted.replace(/^####\s+(.+)$/gm, '<h4 class="font-bold text-base text-slate-800 dark:text-white mt-4 mb-2">$1</h4>');
    formatted = formatted.replace(/^###\s+(.+)$/gm, '<h3 class="font-bold text-lg text-slate-800 dark:text-white mt-4 mb-2">$1</h3>');
    formatted = formatted.replace(/^##\s+(.+)$/gm, '<h2 class="font-bold text-xl text-slate-800 dark:text-white mt-4 mb-2">$1</h2>');
    formatted = formatted.replace(/^#\s+(.+)$/gm, '<h1 class="font-bold text-2xl text-slate-800 dark:text-white mt-4 mb-2">$1</h1>');

    // Convert bullet lists to HTML
    // Match lines starting with * or - (with optional whitespace)
    const lines = formatted.split('\n');
    let inList = false;
    const processedLines = [];

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const isBullet = /^\s*[\*\-]\s+(.+)/.test(line);

        if (isBullet) {
            const content = line.replace(/^\s*[\*\-]\s+/, '');
            if (!inList) {
                processedLines.push('<ul class="list-disc list-inside space-y-1 my-2">');
                inList = true;
            }
            processedLines.push(`<li class="ml-2">${content}</li>`);
        } else {
            if (inList) {
                processedLines.push('</ul>');
                inList = false;
            }
            processedLines.push(line);
        }
    }

    // Close list if still open
    if (inList) {
        processedLines.push('</ul>');
    }

    formatted = processedLines.join('\n');

    // Convert remaining newlines to <br> tags (but not inside lists or headings)
    formatted = formatted.replace(/\n(?![<\/]?ul|[<\/]?li|[<\/]?h[1-6])/g, '<br>');

    // Clean up any double <br> tags that might have been created
    formatted = formatted.replace(/(<br>\s*){3,}/g, '<br><br>');

    return formatted;
}

// Get color classes for source site tags
function getSiteColorClasses(site) {
    if (!site) return 'bg-slate-100 text-slate-500 border-slate-200';

    const s = site.toLowerCase();
    if (s.includes('linkedin')) {
        return 'bg-[#dbeafe] text-[#1e3a8a] border-[#3b82f6]'; // Blue
    } else if (s.includes('indeed')) {
        return 'bg-[#f3e8ff] text-[#581c87] border-[#a855f7]'; // Purple
    } else if (s.includes('glassdoor')) {
        return 'bg-[#d1fae5] text-[#064e3b] border-[#10b981]'; // Green
    } else if (s.includes('zip_recruiter') || s.includes('ziprecruiter')) {
        return 'bg-[#ccfbf1] text-[#134e4a] border-[#14b8a6]'; // Teal
    } else if (s.includes('google')) {
        return 'bg-[#fef3c7] text-[#78350f] border-[#f59e0b]'; // Yellow Orange
    }

    return 'bg-slate-100 text-slate-500 border-slate-200';
}

let newJobContainer;

// Kanban Columns (will be initialized after DOM loads)
let colApplied, colInterview, colOffer, colArchived;

function initializeElements() {
    newJobContainer = document.getElementById('newJobsGrid');
    colApplied = document.getElementById('col-applied');
    colInterview = document.getElementById('col-interview');
    colOffer = document.getElementById('col-offer');
    colArchived = document.getElementById('col-archived');
}

// State for rendering
let showIgnored = false;

function toggleShowIgnored() {
    showIgnored = !showIgnored;
    currentPage = 1; // Reset to page 1 when toggling view
    renderAll();
}

function renderAll() {
    // Clear all containers
    newJobContainer.innerHTML = "";
    colApplied.innerHTML = "";
    colInterview.innerHTML = "";
    colOffer.innerHTML = "";
    colArchived.innerHTML = "";

    let counts = { new: 0, applied: 0, interview: 0, offer: 0, archived: 0, ignored: 0 };
    let newJobsList = [];

    jobsData.forEach(job => {
        if (job.ignore === 1) {
            counts.ignored++;
            // Only render ignored jobs if toggle is on
            if (showIgnored) {
                newJobsList.push({ job, isIgnored: true });
            }
            // Ignored jobs don't go to Kanban and are not counted as 'new' unless user wants to count them?
            // Original code: if ignored -> return. So they are never 'new' or 'kanban'.
            // They are just 'ignored'.
            return;
        }

        if (isJobNew(job)) {
            counts.new++;
            newJobsList.push({ job, isIgnored: false });
        } else {
            const status = getCurrentStatus(job);
            let targetCol = colApplied; // Default

            // Determine Column
            if (status.includes("Interview")) {
                targetCol = colInterview;
                counts.interview++;
            } else if (status === "Offer" || status === "Accepted") {
                targetCol = colOffer;
                counts.offer++;
            } else if (status === "Rejected" || status === "Ghosted") {
                targetCol = colArchived;
                counts.archived++;
            } else {
                // Applied
                counts.applied++;
            }

            renderKanbanCard(job, targetCol);
        }
    });

    // --- Pagination Logic ---
    const totalItems = newJobsList.length;
    const totalPages = Math.ceil(totalItems / itemsPerPage);

    // Ensure currentPage is valid
    if (currentPage > totalPages) currentPage = totalPages || 1;
    if (currentPage < 1) currentPage = 1;

    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = Math.min(startIndex + itemsPerPage, totalItems);

    const jobsToShow = newJobsList.slice(startIndex, endIndex);

    // Render current page jobs
    jobsToShow.forEach(item => {
        renderNewJobCard(item.job, item.isIgnored);
    });

    // Render Pagination Controls
    if (totalPages > 1) {
        renderPagination(totalPages);
    }

    // Update Counts
    let newJobText = counts.new;

    // Header controls container
    const countContainer = document.getElementById('newJobCount').parentElement;

    // Rebuild the header controls slightly to accommodate the button
    // This is a bit hacky, but robust enough for this context
    if (counts.ignored > 0) {
        newJobText += ` <span class="text-xs text-slate-400 font-normal">(${counts.ignored} hidden)</span>`;

        let toggle = document.getElementById('ignoredToggleBtn');
        if (!toggle) {
            toggle = document.createElement('button');
            toggle.id = 'ignoredToggleBtn';
            toggle.className = "ml-3 px-2 py-1 text-xs font-medium rounded-md border transition-all";
            toggle.onclick = toggleShowIgnored;
            countContainer.appendChild(toggle); // Add it if not there
        }

        // Update button state
        toggle.className = showIgnored
            ? "ml-3 text-primary-600 dark:text-neon-blue bg-primary-50 dark:bg-neon-blue/10 border-primary-200 dark:border-neon-blue/30 hover:bg-primary-100"
            : "ml-3 text-slate-400 hover:text-slate-600 dark:text-gray-500 dark:hover:text-gray-300 border-transparent hover:bg-slate-100 dark:hover:bg-white/5";

        toggle.innerHTML = showIgnored
            ? '<i class="fa-solid fa-eye mr-1"></i> Hide'
            : '<i class="fa-solid fa-eye-slash mr-1"></i> Show';

    } else {
        // Remove button if no ignored jobs
        const toggle = document.getElementById('ignoredToggleBtn');
        if (toggle) toggle.remove();
    }

    document.getElementById('newJobCount').innerHTML = newJobText;

    document.getElementById('count-applied').innerText = counts.applied;
    document.getElementById('count-interview').innerText = counts.interview;
    document.getElementById('count-offer').innerText = counts.offer;
    document.getElementById('count-archived').innerText = counts.archived;
}

function renderPagination(totalPages) {
    const paginationContainer = document.createElement('div');
    // Span full width in grid (col-span-full for tailwind/css grid)
    paginationContainer.className = "col-span-full flex justify-center items-center space-x-2 mt-8 py-4";

    // Prev Button
    const prevBtn = document.createElement('button');
    prevBtn.innerHTML = '<i class="fa-solid fa-chevron-left"></i>';
    prevBtn.className = `p-2 rounded-md ${currentPage === 1 ? 'text-slate-300 cursor-not-allowed' : 'text-slate-600 hover:bg-slate-100 hover:text-primary-600 dark:text-gray-400 dark:hover:bg-white/5 dark:hover:text-neon-blue transition-all'}`;
    prevBtn.disabled = currentPage === 1;
    prevBtn.onclick = () => changePage(currentPage - 1);

    // Page Info
    const pageInfo = document.createElement('span');
    pageInfo.className = "text-sm font-medium text-slate-500 dark:text-gray-400 mx-4";
    pageInfo.innerText = `Page ${currentPage} of ${totalPages}`;

    // Next Button
    const nextBtn = document.createElement('button');
    nextBtn.innerHTML = '<i class="fa-solid fa-chevron-right"></i>';
    nextBtn.className = `p-2 rounded-md ${currentPage === totalPages ? 'text-slate-300 cursor-not-allowed' : 'text-slate-600 hover:bg-slate-100 hover:text-primary-600 dark:text-gray-400 dark:hover:bg-white/5 dark:hover:text-neon-blue transition-all'}`;
    nextBtn.disabled = currentPage === totalPages;
    nextBtn.onclick = () => changePage(currentPage + 1);

    paginationContainer.appendChild(prevBtn);
    paginationContainer.appendChild(pageInfo);
    paginationContainer.appendChild(nextBtn);

    newJobContainer.appendChild(paginationContainer);
}

function renderNewJobCard(job, isIgnored = false) {
    // Format data using helper functions
    const formattedDate = formatDate(job.created_at);
    const formattedCompensation = formatCompensation(job.compensation);
    const formattedDescription = formatDescription(job.description);

    // Card Container
    const card = document.createElement('div');
    // Add fixed height for cards with descriptions, auto height for those without
    const cardHeight = formattedDescription ? "h-[450px]" : "";

    // Check if ignored and add styling
    const opacityClass = isIgnored ? "opacity-60 grayscale hover:grayscale-0 hover:opacity-100 ring-2 ring-red-100" : "";

    card.className = `bg-white rounded-2xl border border-slate-200 shadow-sm hover:shadow-lg hover:border-slate-300 transition-all flex flex-col ${cardHeight} group relative overflow-hidden duration-300 hover-lift ${opacityClass}`;

    // Prevent card click when clicking interactive elements
    card.onclick = (e) => {
        if (e.target.closest('button') || e.target.closest('a')) return;
        openJobDetails(job);
    };

    // Build the description section only if there's content
    const descriptionSection = formattedDescription ? `
        <!-- Scrolling Description Area -->
        <div class="flex-1 p-5 overflow-y-auto bg-white text-sm text-slate-600 leading-relaxed custom-scrollbar relative">
            ${formattedDescription}
        </div>
    ` : '';

    card.innerHTML = `
        <!-- Header Section -->
        <div class="px-5 py-4 bg-slate-50/50 border-b border-slate-100">
            <!-- Full Width Title -->
            <h3 class="text-lg font-bold text-slate-900 leading-tight mb-2 group-hover:text-primary transition-colors font-heading">${job.title}</h3>
            
            <!-- Company and Date Row -->
            <div class="flex justify-between items-center mb-3">
                <div class="flex items-center gap-2">
                    <div class="font-bold text-slate-700 text-sm font-body">${job.company}</div>
                    ${job.site ? `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${getSiteColorClasses(job.site)}">${job.site}</span>` : ''}
                </div>
                <span class="text-[10px] font-bold tracking-wide text-slate-500 bg-white px-2 py-1 rounded-md border border-slate-100 shadow-sm font-mono">${formattedDate}</span>
            </div>
            
            <!-- Quick Info Tags -->
            <div class="flex flex-wrap gap-2 text-xs">
                <span class="flex items-center px-2 py-1 rounded-md bg-white border border-slate-200 text-slate-600 font-medium shadow-sm">
                    <i class="fa-solid fa-location-dot mr-1.5 text-slate-400"></i>${job.location}
                </span>
                <span class="flex items-center px-2 py-1 rounded-md bg-white border border-slate-200 text-slate-600 font-medium shadow-sm">
                     <i class="fa-solid fa-sack-dollar mr-1.5 text-slate-400"></i>${formattedCompensation}
                </span>
            </div>
        </div>
        
        ${descriptionSection}

        <!-- Action Buttons Footer -->
        <div class="p-4 bg-slate-50/80 border-t border-slate-100 grid grid-cols-3 gap-3 backdrop-blur-sm">
            <button onclick="ignoreJob(${job.id})" class="flex items-center justify-center gap-2 px-3 py-2 rounded-xl text-sm font-bold text-slate-500 hover:text-red-600 hover:bg-white hover:shadow-sm border border-transparent hover:border-slate-200 transition-all" title="${isIgnored ? 'Unignore' : 'Ignore'}">
                <i class="fa-regular ${isIgnored ? 'fa-eye' : 'fa-eye-slash'}"></i> <span class="hidden sm:inline">${isIgnored ? 'Unignore' : 'Ignore'}</span>
            </button>
            
            <a href="${job.link || '#'}" target="_blank" class="flex items-center justify-center gap-2 px-3 py-2 rounded-xl text-sm font-bold text-slate-600 hover:text-primary hover:bg-white hover:shadow-sm border border-transparent hover:border-slate-200 transition-all" title="External Link">
                <i class="fa-solid fa-external-link-alt"></i> <span class="hidden sm:inline">Link</span>
            </a>

            <button onclick="applyJob(${job.id})" class="flex items-center justify-center gap-2 px-3 py-2 rounded-xl text-sm font-bold bg-primary text-white hover:bg-primary-600 shadow-md hover:shadow-lg hover:shadow-primary/30 border border-transparent transition-all">
                Applied <i class="fa-solid fa-check"></i>
            </button>
        </div>
    `;
    newJobContainer.appendChild(card);
}

function renderKanbanCard(job, container) {
    const card = document.createElement('div');
    card.className = "draggable-card bg-white p-4 rounded-xl border border-slate-200 shadow-sm hover:shadow-md hover:border-primary/50 mb-3 transition-all active:cursor-grabbing group duration-200 hover-lift";
    card.setAttribute("draggable", "true");
    card.setAttribute("data-id", job.id);

    // Drag Events
    card.addEventListener('dragstart', (e) => {
        e.dataTransfer.setData("text/plain", job.id);
        e.target.classList.add('dragging');
    });

    card.addEventListener('dragend', (e) => {
        e.target.classList.remove('dragging');
    });

    // Click Event (Details)
    card.onclick = (e) => {
        openJobDetails(job);
    };

    const status = getCurrentStatus(job);

    card.innerHTML = `
        <div class="flex justify-between items-start mb-2">
            <h4 class="font-bold text-slate-900 text-sm leading-tight group-hover:text-primary transition-colors font-heading">${job.title}</h4>
        </div>
        <div class="flex items-center gap-2 mb-3">
            <p class="text-xs text-slate-600 font-bold font-body">${job.company}</p>
            ${job.site ? `<span class="px-1 py-0.5 rounded text-[8px] font-bold uppercase tracking-tight border ${getSiteColorClasses(job.site)}">${job.site}</span>` : ''}
        </div>
        <div class="flex items-center justify-between mt-2 pt-2 border-t border-slate-100">
            <span class="text-[10px] font-bold tracking-wide text-slate-500 bg-slate-50 px-2 py-1 rounded border border-slate-200 font-mono">${status}</span>
            <i class="fa-solid fa-grip-lines text-slate-300 group-hover:text-slate-500 cursor-grab"></i>
        </div>
    `;
    container.appendChild(card);
}

function renderTimeline(statuses, jobId) {
    const detailTimeline = document.getElementById('detailTimeline');
    detailTimeline.innerHTML = "";

    statuses.forEach((statusItem, index) => {
        const isActive = statusItem.checked === 1;
        const isRejected = isActive && (statusItem.status.includes('Rejected') || statusItem.status.includes('Ghosted'));
        const isOffer = isActive && (statusItem.status.includes('Offer') || statusItem.status.includes('Accepted'));

        let dotColor = isActive ? "bg-primary border-primary shadow-lg shadow-primary/30" : "bg-white border-slate-200 shadow-sm";
        let textColor = isActive ? "text-slate-900 font-bold" : "text-slate-400";
        let ringColor = isActive ? "ring-4 ring-primary/10" : "ring-0";

        if (isRejected) {
            dotColor = "bg-red-500 border-red-500 shadow-lg shadow-red-500/30";
            textColor = "text-red-600 font-bold";
            ringColor = "ring-4 ring-red-500/10";
        } else if (isOffer) {
            dotColor = "bg-tertiary border-tertiary shadow-lg shadow-tertiary/30";
            textColor = "text-tertiary font-bold";
            ringColor = "ring-4 ring-tertiary/10";
        }

        const item = document.createElement('div');
        item.className = "relative flex gap-6 pb-10 last:pb-0 group";

        item.innerHTML = `
            <div class="relative z-10 flex-none w-7 h-7 rounded-lg border-2 ${dotColor} ${ringColor} flex items-center justify-center transition-all mt-0.5">
                ${isActive ? '<i class="fa-solid fa-check text-white text-xs"></i>' : ''}
            </div>
            <div class="flex-1 -mt-1">
                <div class="flex justify-between items-center mb-1 cursor-pointer p-3 rounded-xl hover:bg-slate-50 transition-all border border-transparent hover:border-slate-100" onclick="toggleStatus(${jobId}, ${index})">
                    <span class="${textColor} text-sm font-heading transition-colors">${statusItem.status}</span>
                    <span class="text-[10px] bg-slate-100 text-slate-500 px-2 py-1 rounded-md font-mono font-bold">${statusItem.date_reached || 'PENDING'}</span>
                </div>
            </div>
        `;
        detailTimeline.appendChild(item);
    });
}
