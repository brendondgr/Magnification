// --- MAIN APPLICATION INITIALIZATION ---

// Exposed initialization function
// Exposed initialization function
async function initApp() {
    // Initialize DOM references
    initializeElements();

    // Initialize Theme
    initTheme();

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

// --- THEME LOGIC ---
function initTheme() {
    // Check local storage or system preference
    if (localStorage.theme === 'dark' || (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
        document.documentElement.classList.add('dark');
        updateThemeIcon(true);
    } else {
        document.documentElement.classList.remove('dark');
        updateThemeIcon(false);
    }
}

function toggleTheme() {
    if (document.documentElement.classList.contains('dark')) {
        document.documentElement.classList.remove('dark');
        localStorage.theme = 'light';
        updateThemeIcon(false);
    } else {
        document.documentElement.classList.add('dark');
        localStorage.theme = 'dark';
        updateThemeIcon(true);
    }
}

function updateThemeIcon(isDark) {
    const icon = document.getElementById('theme-toggle-icon');
    if (icon) {
        icon.className = isDark ? 'fa-solid fa-sun text-yellow-500' : 'fa-solid fa-moon text-slate-400';
    }
}

// Expose toggle function globally
window.toggleTheme = toggleTheme;
