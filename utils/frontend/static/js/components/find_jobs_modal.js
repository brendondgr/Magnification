const FindJobsModal = {
    _modalElement: null,
    _pollInterval: null,
    _config: {
        search_terms: [],
        job_titles: [], // Will be [[kw1, kw2], [kw3]]
        description_keywords: [], // Will be [[kw1, kw2], [kw3]]
        sites: [],
        hours_old: 24,
        results_wanted: 20,
        location: ''
    },

    hoursOptions: [
        { value: 24, label: "24 hours (1 day)" },
        { value: 48, label: "48 hours (2 days)" },
        { value: 72, label: "72 hours (3 days)" },
        { value: 168, label: "168 hours (7 days)" },
        { value: 336, label: "336 hours (14 days)" },
        { value: 720, label: "720 hours (30 days)" }
    ],

    init() {
        // Pre-load HTML if helpful, or just wait for open()
        // We'll load on first open to ensure DOM is ready and not block init
    },

    async render() {
        if (this._modalElement) return;

        try {
            const response = await fetch('/parts/find_jobs.html');
            if (!response.ok) throw new Error("Failed to load modal template");
            const html = await response.text();

            const container = document.createElement('div');
            container.innerHTML = html;
            this._modalElement = container.firstElementChild;
            document.body.appendChild(this._modalElement);

            // Create Help Backdrop (since we didn't add it to HTML directly)
            const backdrop = document.createElement('div');
            backdrop.id = 'helpBackdrop';
            backdrop.className = 'help-backdrop';
            backdrop.onclick = () => this.toggleHelpPanel(false);
            this._modalElement.appendChild(backdrop); // Append inside modal-overlay so it covers modal-content

            this.renderSitesOptions();
            this.attachEventListeners();
        } catch (e) {
            console.error("Error rendering Find Jobs Modal:", e);
            alert("Failed to load Find Jobs module.");
        }
    },

    renderSitesOptions() {
        if (!this._modalElement) return;
        const sites = ["indeed", "linkedin", "glassdoor", "zip_recruiter", "google"];
        const container = document.getElementById('sitesContainer');
        if (container) {
            container.innerHTML = sites.map(site => `
                <label class="checkbox-item cursor-pointer">
                    <input type="checkbox" name="site" value="${site}" class="w-4 h-4 rounded text-primary-600 focus:ring-primary-500 border-gray-300 dark:border-gray-600 dark:bg-gray-700">
                    <span class="capitalize">${site.replace('_', ' ')}</span>
                </label>
            `).join('');
        }
    },

    attachEventListeners() {
        // Close buttons
        const closeBtns = this._modalElement.querySelectorAll('.modal-close');
        closeBtns.forEach(btn => btn.onclick = () => this.close());

        // Click outside (only if not scraping)
        this._modalElement.onclick = (e) => {
            if (e.target === this._modalElement && !this._pollInterval) this.close();
        };

        // Slider change
        const slider = document.getElementById('hoursOldSlider');
        slider.oninput = (e) => {
            const index = e.target.value;
            const option = this.hoursOptions[index];
            document.getElementById('hoursOldDisplay').innerText = option.label;
            document.getElementById('hoursOldDisplay').dataset.value = option.value;
        };

        // Tag Inputs (Simple List)
        this.setupTagInput('searchTermsInput', 'search_terms');

        // Section Inputs (Nested Lists)
        // We don't attach listener here for sections because they are dynamic.
        // Instead we bind the "Add Section" buttons.
        document.getElementById('addTitleSectionBtn').onclick = () => this.addSection('job_titles', 'jobTitlesSectionsContainer');
        document.getElementById('addDescSectionBtn').onclick = () => this.addSection('description_keywords', 'descKeywordsSectionsContainer');

        // Start Scrape
        document.getElementById('startScrapeBtn').onclick = () => this.saveAndStart();

        // Final Close
        document.getElementById('progressCloseBtn').onclick = () => {
            this.close();
            window.location.reload(); // Refresh to see new jobs
        };

        /* --- Help System Listeners --- */

        // Open Help Panel
        const helpBtn = document.getElementById('helpBtn');
        if (helpBtn) helpBtn.onclick = () => this.toggleHelpPanel(true);

        // Close Help Panel
        const closeHelpBtn = document.getElementById('closeHelpBtn');
        if (closeHelpBtn) closeHelpBtn.onclick = () => this.toggleHelpPanel(false);

        // Info Buttons
        const infoBtns = this._modalElement.querySelectorAll('.info-btn');
        infoBtns.forEach(btn => {
            btn.onclick = (e) => {
                e.stopPropagation(); // Prevent bubbling
                const sectionId = btn.dataset.helpSection;
                this.openHelpSection(sectionId);
            };
        });

        // Accordion Headers
        const accHeaders = this._modalElement.querySelectorAll('.accordion-header');
        accHeaders.forEach(header => {
            header.onclick = () => {
                const item = header.parentElement;
                const content = item.querySelector('.accordion-content');

                // Toggle current
                const isHidden = content.classList.contains('hidden');

                if (isHidden) {
                    // Start opening
                    content.classList.remove('hidden');
                    item.classList.add('active');
                } else {
                    content.classList.add('hidden');
                    item.classList.remove('active');
                }
            };
        });
    },

    /* --- Simple Tag Input (Flat List) --- */
    setupTagInput(containerId, configKey) {
        const container = document.getElementById(containerId);
        if (!container) return;
        const input = container.querySelector('input');

        const createTag = (text) => {
            if (!text || this._config[configKey].includes(text)) return;
            this._config[configKey].push(text);
            renderTags();
        };

        const removeTag = (text) => {
            this._config[configKey] = this._config[configKey].filter(t => t !== text);
            renderTags();
        };

        const renderTags = () => {
            const tags = container.querySelectorAll('.tag-pill');
            tags.forEach(t => t.remove());

            this._config[configKey].forEach(text => {
                const tag = document.createElement('div');
                tag.className = 'tag-pill';
                tag.innerHTML = `${text} <span class="tag-remove">&times;</span>`;
                tag.querySelector('.tag-remove').onclick = () => removeTag(text);
                container.insertBefore(tag, input);
            });
        };

        input.onkeydown = (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                createTag(input.value.trim());
                input.value = '';
            } else if (e.key === 'Backspace' && input.value === '' && this._config[configKey].length > 0) {
                const lastTag = this._config[configKey][this._config[configKey].length - 1];
                removeTag(lastTag);
            }
        };
        // Initial render called by populateForm
    },

    /* --- Nested Section Logic --- */

    // Normalize config to be [[strings]]
    normalizeConfig(key) {
        let val = this._config[key];
        if (!Array.isArray(val)) {
            this._config[key] = [[]];
        } else if (val.length > 0 && typeof val[0] === 'string') {
            // Convert flat list to single group
            this._config[key] = [val];
        } else if (val.length === 0) {
            // Keep empty, renderSections will handle default
        }
    },

    renderSections(containerId, configKey) {
        const container = document.getElementById(containerId);
        if (!container) return;
        container.innerHTML = '';

        // Ensure at least 1 section if empty? No, let user control. 
        // But if completely empty, the user sees nothing.
        // Let's ensure at least one empty section if the array is empty.
        if (this._config[configKey].length === 0) {
            this._config[configKey].push([]);
        }

        this._config[configKey].forEach((sectionParams, index) => {
            const sectionEl = this.createSectionElement(sectionParams, index, configKey, containerId);
            container.appendChild(sectionEl);
        });
    },

    createSectionElement(params, index, configKey, containerId) {
        const sectionDiv = document.createElement('div');
        sectionDiv.className = "p-3 bg-white dark:bg-[#252525] border border-[#cbd5e1] dark:border-[#3a3a3a] rounded-lg relative group";

        // Delete Section Button (Absolute top right)
        const deleteBtn = document.createElement('button');
        deleteBtn.className = "absolute top-2 right-2 text-slate-400 hover:text-red-500 transition-colors opacity-0 group-hover:opacity-100";
        deleteBtn.innerHTML = '<i class="fa-solid fa-trash-can"></i>';
        deleteBtn.onclick = () => {
            this.removeSection(configKey, index, containerId);
        };
        sectionDiv.appendChild(deleteBtn);

        // Label
        const label = document.createElement('div');
        label.className = "text-[10px] font-bold text-slate-400 uppercase mb-2";
        label.innerText = `Group ${index + 1} (OR)`;
        sectionDiv.appendChild(label);

        // Tags Container
        const tagsContainer = document.createElement('div');
        tagsContainer.className = "flex flex-wrap gap-2 items-center";

        // Render Existing Tags
        params.forEach(tagText => {
            const tag = document.createElement('div');
            tag.className = 'tag-pill';
            tag.innerHTML = `${tagText} <span class="tag-remove">&times;</span>`;
            tag.querySelector('.tag-remove').onclick = () => {
                this.removeTagFromSection(configKey, index, tagText, containerId);
            };
            tagsContainer.appendChild(tag);
        });

        // Input
        const input = document.createElement('input');
        input.type = "text";
        input.className = "bg-transparent text-sm min-w-[100px] outline-none text-slate-700 dark:text-gray-300 placeholder:text-slate-400";
        input.placeholder = "Add keyword...";
        input.onkeydown = (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const val = input.value.trim();
                if (val) {
                    this.addTagToSection(configKey, index, val, containerId);
                    // Focus handling is done in renderSections/addTagToSection
                }
            } else if (e.key === 'Backspace' && input.value === '' && params.length > 0) {
                // Remove last tag
                const lastTag = params[params.length - 1];
                this.removeTagFromSection(configKey, index, lastTag, containerId);
            }
        };

        tagsContainer.appendChild(input);
        sectionDiv.appendChild(tagsContainer);

        return sectionDiv;
    },

    addSection(configKey, containerId) {
        this._config[configKey].push([]);
        this.renderSections(containerId, configKey);
    },

    removeSection(configKey, index, containerId) {
        this._config[configKey].splice(index, 1);
        this.renderSections(containerId, configKey);
    },

    addTagToSection(configKey, sectionIndex, text, containerId) {
        if (this._config[configKey][sectionIndex].includes(text)) return;
        this._config[configKey][sectionIndex].push(text);
        this.renderSections(containerId, configKey);

        // Restore focus
        setTimeout(() => {
            const container = document.getElementById(containerId);
            if (container) {
                const inputs = container.querySelectorAll('input');
                if (inputs[sectionIndex]) {
                    inputs[sectionIndex].focus();
                }
            }
        }, 0);
    },

    removeTagFromSection(configKey, sectionIndex, text, containerId) {
        this._config[configKey][sectionIndex] = this._config[configKey][sectionIndex].filter(t => t !== text);
        this.renderSections(containerId, configKey);
    },


    async open() {
        if (!this._modalElement) await this.render();
        await this.loadConfig();
        this.populateForm();
        this.switchView('config');
        this._modalElement.classList.add('active');
    },

    close() {
        if (this._pollInterval) {
            if (!confirm("Scraping in progress. Are you sure you want to stop monitoring? The scrape will continue in the background.")) {
                return;
            }
            clearInterval(this._pollInterval);
            this._pollInterval = null;
        }
        if (this._modalElement) {
            this._modalElement.classList.remove('active');
        }
    },

    switchView(view) {
        if (view === 'config') {
            document.getElementById('modalConfigView').classList.remove('hidden');
            document.getElementById('modalProgressView').classList.add('hidden');
        } else {
            document.getElementById('modalConfigView').classList.add('hidden');
            document.getElementById('modalProgressView').classList.remove('hidden');
            // Reset Progress UI
            document.getElementById('progressPercent').innerText = "0%";
            document.getElementById('progressStage').innerText = "Initializing...";
            document.getElementById('jobsFoundCount').innerText = "0";
            document.getElementById('jobsSavedCount').innerText = "0";
            document.getElementById('progressActions').classList.add('hidden');
        }
    },

    async loadConfig() {
        try {
            const response = await fetch('/api/config/load');
            const data = await response.json();
            this._config = { ...this._config, ...data };

            // Normalize inputs
            this.normalizeConfig('job_titles');
            this.normalizeConfig('description_keywords');

        } catch (error) {
            console.error("Error loading config:", error);
        }
    },

    populateForm() {
        // Tag Inputs (Simple)
        this.renderSimpleTags('searchTermsInput', 'search_terms');

        // Section Inputs (Nested)
        this.renderSections('jobTitlesSectionsContainer', 'job_titles');
        this.renderSections('descKeywordsSectionsContainer', 'description_keywords');

        // Rest of the form
        const slider = document.getElementById('hoursOldSlider');
        const hours = this._config.hours_old || 24;
        let closestIndex = 0;
        this.hoursOptions.forEach((opt, idx) => {
            if (opt.value <= hours) closestIndex = idx;
        });
        slider.value = closestIndex;
        document.getElementById('hoursOldDisplay').innerText = this.hoursOptions[closestIndex].label;

        document.getElementById('resultsWantedInput').value = this._config.results_wanted || 20;

        const locInput = document.getElementById('locationInput');
        if (locInput) locInput.value = this._config.location || '';

        const sitesCheckboxes = document.querySelectorAll('input[name="site"]');
        sitesCheckboxes.forEach(cb => {
            cb.checked = this._config.sites.includes(cb.value);
        });
    },

    renderSimpleTags(containerId, configKey) {
        const container = document.getElementById(containerId);
        if (!container) return;
        const input = container.querySelector('input');
        const tags = container.querySelectorAll('.tag-pill');
        tags.forEach(t => t.remove());

        this._config[configKey].forEach(text => {
            const tag = document.createElement('div');
            tag.className = 'tag-pill';
            tag.innerHTML = `${text} <span class="tag-remove">&times;</span>`;
            tag.querySelector('.tag-remove').onclick = () => {
                this._config[configKey] = this._config[configKey].filter(t => t !== text);
                this.renderSimpleTags(containerId, configKey);
            };
            container.insertBefore(tag, input);
        });
    },

    async saveAndStart() {
        const sites = Array.from(document.querySelectorAll('input[name="site"]:checked')).map(cb => cb.value);
        if (sites.length === 0) return alert("Please select at least one site.");
        if (this._config.search_terms.length === 0) return alert("Please add at least one search term.");

        const sliderIndex = document.getElementById('hoursOldSlider').value;
        const hoursOld = this.hoursOptions[sliderIndex].value;
        const resultsWanted = parseInt(document.getElementById('resultsWantedInput').value);
        const location = document.getElementById('locationInput').value.trim();

        const configToSave = {
            ...this._config,
            sites: sites,
            hours_old: hoursOld,
            results_wanted: resultsWanted,
            location: location
        };

        try {
            const saveRes = await fetch('/api/config/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(configToSave)
            });
            const saveResult = await saveRes.json();

            if (!saveResult.success) {
                alert("Failed to save config: " + saveResult.message);
                return;
            }

            this.switchView('progress');

            // Start Scraping
            const scrapeRes = await fetch('/api/scrape/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ use_config: true })
            });
            const scrapeData = await scrapeRes.json();

            if (scrapeData.success) {
                this.startPolling(scrapeData.job_id);
            } else {
                alert("Failed to start scraping: " + scrapeData.message);
                this.switchView('config');
            }

        } catch (error) {
            console.error(error);
            alert("An error occurred.");
            this.switchView('config');
        }
    },

    startPolling(jobId) {
        this._pollInterval = setInterval(async () => {
            try {
                const res = await fetch(`/api/scrape/status/${jobId}`);
                const data = await res.json();

                this.updateProgressUI(data);

                if (data.status === 'completed' || data.status === 'failed') {
                    clearInterval(this._pollInterval);
                    this._pollInterval = null;
                }
            } catch (e) {
                console.error("Polling error:", e);
            }
        }, 1000); // 1 second interval
    },

    updateProgressUI(data) {
        const stage = data.progress.stage;
        const percent = data.progress.percent || 0;
        const details = data.progress.details || {};

        document.getElementById('progressPercent').innerText = `${Math.round(percent)}%`;
        document.getElementById('progressStage').innerText = this.formatStage(stage);

        if (details.message) {
            document.getElementById('progressMessage').innerText = details.message;
        }

        if (details.jobs_found !== undefined) {
            document.getElementById('jobsFoundCount').innerText = details.jobs_found;
        }

        if (data.status === 'completed') {
            const results = data.results;
            const processed = results.steps?.processing?.processed_count || 0;
            const saved = results.steps?.storage?.stored_count || 0;

            document.getElementById('jobsFoundCount').innerText = processed;
            document.getElementById('jobsSavedCount').innerText = saved;

            document.getElementById('progressActions').classList.remove('hidden');
            document.getElementById('progressStage').innerText = "Scraping Completed";
            document.getElementById('progressMessage').innerText = `Found ${processed} unique jobs. Added ${saved} new jobs.`;
        } else if (data.status === 'failed') {
            document.getElementById('progressStage').innerText = "Scraping Failed";
            document.getElementById('progressStage').classList.add('text-red-500');
            document.getElementById('progressActions').classList.remove('hidden');
            document.getElementById('progressCloseBtn').innerText = "Close";
            document.getElementById('progressCloseBtn').onclick = () => this.close();
        }
    },

    formatStage(stage) {
        if (!stage) return "Processing...";
        return stage.charAt(0).toUpperCase() + stage.slice(1);
    },

    /* --- Help Panel Methods --- */

    toggleHelpPanel(show) {
        const panel = document.getElementById('helpPanel');
        const backdrop = document.getElementById('helpBackdrop');
        if (!panel || !backdrop) return;

        if (show) {
            panel.classList.remove('translate-x-full');
            backdrop.classList.add('active');
        } else {
            panel.classList.add('translate-x-full');
            backdrop.classList.remove('active');
        }
    },

    openHelpSection(sectionId) {
        if (!sectionId) return;
        this.toggleHelpPanel(true);

        // Collapse all first (optional, maybe we want to keep others open? Let's collapse for focus)
        const allItems = document.querySelectorAll('.accordion-item');
        allItems.forEach(item => {
            item.classList.remove('active');
            item.querySelector('.accordion-content').classList.add('hidden');
        });

        // Open target
        const targetDesc = document.getElementById(sectionId);
        if (targetDesc) {
            targetDesc.classList.add('active');
            const content = targetDesc.querySelector('.accordion-content');
            content.classList.remove('hidden');

            // Scroll to it
            setTimeout(() => {
                targetDesc.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 300); // Wait for panel slide
        }
    }
};

// Initiate
document.addEventListener('DOMContentLoaded', () => {
    FindJobsModal.init();
    window.FindJobsModal = FindJobsModal;
});
