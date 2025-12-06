/**
 * Dropdown Functionality for LLM Server Control
 * 
 * This module handles:
 * - Dropdown menu toggle
 * - Loading and saving configuration
 * - Loading models list
 * - Server start/stop actions
 * - Form validation and error handling
 */

// Global state
let isDropdownOpen = false;
let serverStatus = 'idle'; // idle, starting, running, stopping, error

/**
 * Initialize dropdown on page load
 */
/**
 * Initialize dropdown
 * Should be called after HTML content is loaded
 */
function initLLMDropdown() {
    console.log('Initializing LLM Server Control...');

    // Load configuration and models
    loadConfig();
    loadModels();

    // Initialize Lucide icons
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }

    // Set initial slider values
    updateSliderValue('context-size');
    updateSliderValue('max-tokens');
    updateSliderValue('temperature');
    updateSliderValue('repeat-penalty');
    updateSliderValue('gpu-layers');

    // Start polling for server status
    startStatusPolling();

    console.log('Initialization complete');
}


/**
 * Toggle dropdown menu visibility
 */
function toggleLLMDropdown() {
    const dropdown = document.getElementById('llm-dropdown');

    if (isDropdownOpen) {
        dropdown.classList.add('hidden');
        isDropdownOpen = false;
    } else {
        dropdown.classList.remove('hidden');
        isDropdownOpen = true;
    }
}

/**
 * Toggle advanced settings section
 */
function toggleAdvancedSettings() {
    const advancedSettings = document.getElementById('llm-advanced-settings');
    const chevron = document.getElementById('advanced-chevron');

    if (advancedSettings.classList.contains('hidden')) {
        advancedSettings.classList.remove('hidden');
        chevron.classList.add('rotated');
    } else {
        advancedSettings.classList.add('hidden');
        chevron.classList.remove('rotated');
    }
}

/**
 * Update slider display value
 * 
 * @param {string} sliderId - ID of the slider (without 'llm-' prefix)
 */
function updateSliderValue(sliderId) {
    let slider, valueDisplay, formattedValue;

    switch (sliderId) {
        case 'context-size':
            slider = document.getElementById('llm-context');
            valueDisplay = document.getElementById('context-size-value');
            formattedValue = sliderToContextSize(slider.value);
            break;

        case 'max-tokens':
            slider = document.getElementById('llm-max-tokens');
            valueDisplay = document.getElementById('max-tokens-value');
            formattedValue = sliderToMaxTokens(slider.value);
            break;

        case 'temperature':
            slider = document.getElementById('llm-temperature');
            valueDisplay = document.getElementById('temperature-value');
            formattedValue = sliderToTemperature(slider.value);
            break;

        case 'repeat-penalty':
            slider = document.getElementById('llm-repeat-penalty');
            valueDisplay = document.getElementById('repeat-penalty-value');
            formattedValue = sliderToRepeatPenalty(slider.value);
            break;

        case 'gpu-layers':
            slider = document.getElementById('llm-gpu-layers');
            valueDisplay = document.getElementById('gpu-layers-value');
            formattedValue = sliderToGPULayers(slider.value);
            break;

        default:
            console.error('Unknown slider ID:', sliderId);
            return;
    }

    if (valueDisplay) {
        valueDisplay.textContent = formattedValue;
    }
}

/**
 * Load configuration from server
 */
async function loadConfig() {
    try {
        console.log('Loading configuration from server...');

        const response = await fetch('/api/config');

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        // Load frontend_defaults if available
        if (data.frontend_defaults) {
            console.log('Loaded frontend defaults:', data.frontend_defaults);
            deserializeConfig(data.frontend_defaults);
        }

        console.log('Configuration loaded successfully');

    } catch (error) {
        console.error('Failed to load configuration:', error);
        showError('Failed to load configuration: ' + error.message);

        // Use default values
        deserializeConfig(getDefaultConfig());
    }
}

/**
 * Load available models from server
 */
async function loadModels() {
    try {
        console.log('Loading models from server...');

        const response = await fetch('/api/models');

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const models = await response.json();

        if (models.error) {
            throw new Error(models.error);
        }

        // Populate model dropdown
        const modelSelect = document.getElementById('llm-model');
        const currentSelection = modelSelect.value;
        modelSelect.innerHTML = '';

        // Add placeholder option
        const placeholderOption = document.createElement('option');
        placeholderOption.value = '';
        placeholderOption.textContent = 'Select a model...';
        modelSelect.appendChild(placeholderOption);

        // Add model options
        models.forEach(model => {
            const option = document.createElement('option');
            option.value = model.file_name;
            option.textContent = `${model.nickname} (${model.parameters_billions}B)`;
            modelSelect.appendChild(option);
        });

        // Restore selection if valid
        if (currentSelection) {
            const exists = models.some(m => m.file_name === currentSelection);
            if (exists) {
                modelSelect.value = currentSelection;
            }
        }

        console.log(`Loaded ${models.length} models`);

    } catch (error) {
        console.error('Failed to load models:', error);
        showError('Failed to load models: ' + error.message);
    }
}

/**
 * Save configuration to server
 */
async function saveLLMConfig() {
    try {
        console.log('Saving configuration...');

        // Serialize current form values
        const config = serializeConfig();

        // Validate configuration
        const validation = validateConfig(config);
        if (!validation.valid) {
            showError(validation.errors.join(', '));
            return;
        }

        // Send to server
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(config)
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();

        if (result.error) {
            throw new Error(result.error);
        }

        console.log('Configuration saved successfully');
        showSuccess('Configuration saved successfully!');

    } catch (error) {
        console.error('Failed to save configuration:', error);
        showError('Failed to save configuration: ' + error.message);
    }
}

/**
 * Start LLM server
 */
async function startLLMServer() {
    console.log('Starting LLM server...');

    // Validate configuration first
    const config = serializeConfig();
    const validation = validateConfig(config);

    if (!validation.valid) {
        showError(validation.errors.join(', '));
        return;
    }

    // Update status locally immediately for better UX
    setServerStatus('starting');

    try {
        const response = await fetch('/api/server/start', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(config)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || `HTTP error! status: ${response.status}`);
        }

        const result = await response.json();
        console.log('Server start request sent:', result);
        showSuccess('Server starting...');

        // Start polling for status
        startStatusPolling();

    } catch (error) {
        console.error('Failed to start server:', error);
        showError('Failed to start server: ' + error.message);
        setServerStatus('error');
    }
}

/**
 * Stop LLM server
 */
async function stopLLMServer() {
    console.log('Stopping LLM server...');

    // Update status
    setServerStatus('stopping');

    try {
        const response = await fetch('/api/server/stop', {
            method: 'POST'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || `HTTP error! status: ${response.status}`);
        }

        const result = await response.json();
        console.log('Server stop request sent:', result);
        showSuccess('Server stopped');

    } catch (error) {
        console.error('Failed to stop server:', error);
        showError('Failed to stop server: ' + error.message);
        // Don't change status to error here, as we might still be running or stopped
        // Let polling sort it out
    }
}

// Polling interval ID
let statusPollInterval = null;

/**
 * Start polling for server status
 */
function startStatusPolling() {
    if (statusPollInterval) clearInterval(statusPollInterval);

    // Poll every 2 seconds
    statusPollInterval = setInterval(checkServerStatus, 2000);
}

/**
 * Check server status from backend
 */
async function checkServerStatus() {
    try {
        const response = await fetch('/api/server/status');
        if (response.ok) {
            const data = await response.json();
            if (data.status !== serverStatus) {
                setServerStatus(data.status);
            }
        }
    } catch (error) {
        console.error('Error checking server status:', error);
    }
}

/**
 * Set server status and update UI
 * 
 * @param {string} status - Status: idle, starting, running, stopping, error, stopped
 */
function setServerStatus(status) {
    // Normalize status (backend might return 'stopped' instead of 'idle')
    if (status === 'idle') status = 'stopped';

    serverStatus = status;

    const statusIndicator = document.getElementById('llm-header-status');
    const startBtn = document.getElementById('llm-start-btn');
    const stopBtn = document.getElementById('llm-stop-btn');

    // Update Dropdown Status Indicator
    statusIndicator.className = 'w-3 h-3 rounded-full transition-colors duration-300'; // Reset classes

    // Update Header Button Status (if it exists)
    const headerStatusDot = document.getElementById('header-btn-status-dot');

    switch (status) {
        case 'stopped':
            statusIndicator.classList.add('bg-slate-500'); // Gray
            if (headerStatusDot) {
                headerStatusDot.classList.remove('bg-emerald-500', 'animate-pulse', 'bg-amber-500', 'bg-red-500');
                headerStatusDot.classList.add('bg-red-500');
            }

            startBtn.disabled = false;
            stopBtn.disabled = true;
            break;

        case 'starting':
            statusIndicator.classList.add('bg-amber-500', 'animate-pulse'); // Amber pulse
            if (headerStatusDot) {
                headerStatusDot.classList.remove('bg-emerald-500', 'bg-red-500', 'bg-amber-500');
                headerStatusDot.classList.add('bg-amber-500', 'animate-pulse');
            }

            startBtn.disabled = true;
            stopBtn.disabled = true;
            break;

        case 'running':
            statusIndicator.classList.add('bg-emerald-500'); // Green
            if (headerStatusDot) {
                headerStatusDot.classList.remove('bg-red-500', 'bg-amber-500', 'bg-emerald-500');
                headerStatusDot.classList.add('bg-emerald-500', 'animate-pulse');
            }

            startBtn.disabled = true;
            stopBtn.disabled = false;
            break;

        case 'stopping':
            statusIndicator.classList.add('bg-amber-500', 'animate-pulse'); // Amber pulse
            if (headerStatusDot) {
                headerStatusDot.classList.remove('bg-emerald-500', 'bg-red-500', 'bg-amber-500');
                headerStatusDot.classList.add('bg-amber-500', 'animate-pulse');
            }

            startBtn.disabled = true;
            stopBtn.disabled = true;
            break;

        case 'error':
            statusIndicator.classList.add('bg-red-500'); // Red
            if (headerStatusDot) {
                headerStatusDot.classList.remove('bg-emerald-500', 'animate-pulse', 'bg-amber-500', 'bg-red-500');
                headerStatusDot.classList.add('bg-red-500');
            }

            startBtn.disabled = false;
            stopBtn.disabled = true;
            break;
    }

    console.log('Server status updated to:', status);
}

/**
 * Show error message
 * 
 * @param {string} message - Error message to display
 */
function showError(message) {
    const errorElement = document.getElementById('llm-error-message');
    errorElement.textContent = message;
    errorElement.classList.remove('hidden');
    errorElement.classList.add('text-red-400');
    errorElement.classList.remove('text-green-400');

    // Auto-hide after 5 seconds
    setTimeout(() => {
        errorElement.classList.add('hidden');
    }, 5000);
}

/**
 * Show success message
 * 
 * @param {string} message - Success message to display
 */
function showSuccess(message) {
    const errorElement = document.getElementById('llm-error-message');
    errorElement.textContent = message;
    errorElement.classList.remove('hidden');
    errorElement.classList.add('text-green-400');
    errorElement.classList.remove('text-red-400');

    // Auto-hide after 3 seconds
    setTimeout(() => {
        errorElement.classList.add('hidden');
    }, 3000);
}

/**
 * Close dropdown when clicking outside
 */
document.addEventListener('click', function (event) {
    const dropdown = document.getElementById('llm-dropdown');
    const toggleButton = event.target.closest('button[onclick="toggleLLMDropdown()"]');

    if (isDropdownOpen && !dropdown.contains(event.target) && !toggleButton) {
        toggleLLMDropdown();
    }
});

/**
 * Close dropdown on Escape key
 */
document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && isDropdownOpen) {
        toggleLLMDropdown();
    }
});

/**
 * Side Panel Functions
 */

function toggleSidePanel() {
    const sidePanel = document.getElementById('llm-side-panel');
    if (sidePanel.classList.contains('w-0')) {
        sidePanel.classList.remove('w-0');
        sidePanel.classList.add('w-80');
        sidePanel.classList.remove('border-slate-200/0');
        sidePanel.classList.remove('dark:border-neon-border/0');
        sidePanel.classList.add('border-slate-200');
        sidePanel.classList.add('dark:border-neon-border');
        loadSidePanelData();
    } else {
        sidePanel.classList.add('w-0');
        sidePanel.classList.remove('w-80');
        sidePanel.classList.add('border-slate-200/0');
        sidePanel.classList.add('dark:border-neon-border/0');
        sidePanel.classList.remove('border-slate-200');
        sidePanel.classList.remove('dark:border-neon-border');
    }
}

async function loadSidePanelData() {
    try {
        const response = await fetch('/api/config');
        const config = await response.json();

        if (config.model_directories) {
            document.getElementById('dir-language').value = config.model_directories.language || '';
            document.getElementById('dir-voice').value = config.model_directories.voice || '';
        }

        refreshModels();
    } catch (error) {
        console.error('Error loading side panel data:', error);
    }
}

async function saveDirectories() {
    const language = document.getElementById('dir-language').value;
    const voice = document.getElementById('dir-voice').value;

    try {
        const response = await fetch('/api/config/directories', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ language, voice })
        });
        const result = await response.json();
        if (result.success) {
            showSuccess('Directories saved!');
            refreshModels();
        } else {
            showError('Error: ' + result.error);
        }
    } catch (error) {
        console.error('Error saving directories:', error);
        showError('Error saving directories');
    }
}

async function refreshModels() {
    try {
        const response = await fetch('/api/models/refresh');
        const data = await response.json();

        renderModelList('language', data.language);
        renderModelList('voice', data.voice);

        // Also update the main dropdown
        await loadModels();
    } catch (error) {
        console.error('Error refreshing models:', error);
    }
}

function renderModelList(type, models) {
    const container = document.getElementById(`list-${type}-models`);
    container.innerHTML = '';

    models.forEach(model => {
        const div = document.createElement('div');
        div.className = 'flex items-center justify-between bg-slate-50 dark:bg-neon-black/50 p-2 rounded border border-slate-200 dark:border-neon-border/50';

        const statusColor = model.exists ? 'bg-green-500 dark:bg-neon-green' : 'bg-red-500 dark:bg-neon-pink';
        const statusTitle = model.exists ? 'File exists' : 'File not found';

        div.innerHTML = `
            <div class="flex items-center gap-2 overflow-hidden">
                <div class="w-2 h-2 rounded-full ${statusColor}" title="${statusTitle}"></div>
                <div class="flex-1 min-w-0">
                    <div class="text-xs font-medium text-slate-800 dark:text-gray-200 truncate" title="${model.nickname}">${model.nickname}</div>
                    <div class="text-[10px] text-slate-500 dark:text-gray-400 truncate" title="${model.file_name}">${model.file_name}</div>
                </div>
            </div>
            <button onclick="removeModel('${type}', '${model.file_name}')" class="text-slate-400 hover:text-red-500 dark:hover:text-neon-pink ml-2">
                <i data-lucide="trash-2" class="w-3 h-3"></i>
            </button>
        `;
        container.appendChild(div);
    });

    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
}

async function addNewModel(type) {
    const prefix = type === 'language' ? 'new-model' : 'new-voice';
    const fileName = document.getElementById(`${prefix}-file`).value;
    const nickname = document.getElementById(`${prefix}-name`).value;
    const params = type === 'language' ? parseFloat(document.getElementById(`${prefix}-params`).value || 0) : 0;

    if (!fileName || !nickname) {
        showError('Please fill in filename and nickname');
        return;
    }

    const data = {
        file_name: fileName,
        nickname: nickname,
        parameters_billions: params
    };

    try {
        const response = await fetch('/api/models/manage', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'add',
                type: type,
                data: data
            })
        });
        const result = await response.json();
        if (result.success) {
            document.getElementById(`${prefix}-file`).value = '';
            document.getElementById(`${prefix}-name`).value = '';
            if (type === 'language') document.getElementById(`${prefix}-params`).value = '';

            refreshModels();
            showSuccess('Model added!');
        } else {
            showError('Error: ' + result.error);
        }
    } catch (error) {
        console.error('Error adding model:', error);
        showError('Error adding model');
    }
}

async function removeModel(type, fileName) {
    if (!confirm(`Are you sure you want to remove ${fileName}?`)) return;

    try {
        const response = await fetch('/api/models/manage', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'remove',
                type: type,
                data: { file_name: fileName }
            })
        });
        const result = await response.json();
        if (result.success) {
            refreshModels();
            showSuccess('Model removed!');
        } else {
            showError('Error: ' + result.error);
        }
    } catch (error) {
        console.error('Error removing model:', error);
        showError('Error removing model');
    }
}
