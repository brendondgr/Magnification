// --- MAIN APPLICATION INITIALIZATION ---

// Exposed initialization function
// Exposed initialization function
async function initApp() {
    // Initialize DOM references
    initializeElements();

    // Fetch Data
    await fetchJobs();

    // Initial render
    // Initial render
    renderAll();

    // Initialize Lucide Icons
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
}
