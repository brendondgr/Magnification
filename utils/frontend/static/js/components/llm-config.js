/**
 * Configuration Utilities for LLM Server Control
 * 
 * This module provides helper functions for:
 * - Converting slider values to actual numbers
 * - Default value fallbacks
 * - Configuration object serialization/deserialization
 */

/**
 * Convert slider value to context size (2^(value + 10))
 * Range: 1K (2^10) to 128K (2^17)
 * 
 * @param {number} sliderValue - Slider value (10-17)
 * @returns {number} Context size in tokens
 */
function sliderToContextSize(sliderValue) {
    const value = parseInt(sliderValue);
    const contextSize = Math.pow(2, value);

    // Format with K suffix
    if (contextSize >= 1024) {
        return Math.floor(contextSize / 1024) + 'K';
    }
    return contextSize;
}

/**
 * Convert slider value to max tokens (2^(value + 7))
 * Range: 128 (2^7) to 16K (2^14)
 * 
 * @param {number} sliderValue - Slider value (7-14)
 * @returns {string} Max tokens formatted
 */
function sliderToMaxTokens(sliderValue) {
    const value = parseInt(sliderValue);
    const maxTokens = Math.pow(2, value);

    // Format with K suffix
    if (maxTokens >= 1024) {
        return Math.floor(maxTokens / 1024) + 'K';
    }
    return maxTokens;
}

/**
 * Convert slider value to temperature
 * Direct value (0.0 to 2.0)
 * 
 * @param {number} sliderValue - Slider value
 * @returns {number} Temperature value
 */
function sliderToTemperature(sliderValue) {
    return parseFloat(sliderValue).toFixed(1);
}

/**
 * Convert slider value to repeat penalty
 * Direct value (1.0 to 2.0)
 * 
 * @param {number} sliderValue - Slider value
 * @returns {number} Repeat penalty value
 */
function sliderToRepeatPenalty(sliderValue) {
    return parseFloat(sliderValue).toFixed(1);
}

/**
 * Convert slider value to GPU layers
 * Direct value (0 to 999)
 * 
 * @param {number} sliderValue - Slider value
 * @returns {number} GPU layers
 */
function sliderToGPULayers(sliderValue) {
    return parseInt(sliderValue);
}

/**
 * Get actual context size in tokens from slider value
 * 
 * @param {number} sliderValue - Slider value (10-17)
 * @returns {number} Actual context size in tokens
 */
function getActualContextSize(sliderValue) {
    return Math.pow(2, parseInt(sliderValue));
}

/**
 * Get actual max tokens from slider value
 * 
 * @param {number} sliderValue - Slider value (7-14)
 * @returns {number} Actual max tokens
 */
function getActualMaxTokens(sliderValue) {
    return Math.pow(2, parseInt(sliderValue));
}

/**
 * Serialize configuration from form fields
 * 
 * @returns {object} Configuration object
 */
function serializeConfig() {
    const config = {
        model: document.getElementById('llm-model').value,
        streaming: document.getElementById('llm-streaming').checked,
        context_size: parseInt(document.getElementById('llm-context').value),
        max_tokens: parseInt(document.getElementById('llm-max-tokens').value),
        temperature: parseFloat(document.getElementById('llm-temperature').value),
        repeat_penalty: parseFloat(document.getElementById('llm-repeat-penalty').value),
        host: document.getElementById('llm-host').value,
        port: parseInt(document.getElementById('llm-port').value),
        compute_mode: document.querySelector('input[name="compute-mode"]:checked').value,
        gpu_layers: parseInt(document.getElementById('llm-gpu-layers').value),
        threads: parseInt(document.getElementById('llm-threads').value) || 0,
        advanced_settings_open: !document.getElementById('llm-advanced-settings').classList.contains('hidden')
    };

    return config;
}

/**
 * Deserialize configuration to form fields
 * 
 * @param {object} config - Configuration object
 */
function deserializeConfig(config) {
    if (!config) return;

    // Model selection
    if (config.model !== undefined) {
        const modelSelect = document.getElementById('llm-model');
        if (modelSelect) {
            modelSelect.value = config.model;
        }
    }

    // Streaming
    if (config.streaming !== undefined) {
        document.getElementById('llm-streaming').checked = config.streaming;
    }

    // Context size
    if (config.context_size !== undefined) {
        const contextSlider = document.getElementById('llm-context');
        contextSlider.value = config.context_size;
        updateSliderValue('context-size');
    }

    // Max tokens
    if (config.max_tokens !== undefined) {
        const maxTokensSlider = document.getElementById('llm-max-tokens');
        maxTokensSlider.value = config.max_tokens;
        updateSliderValue('max-tokens');
    }

    // Temperature
    if (config.temperature !== undefined) {
        const tempSlider = document.getElementById('llm-temperature');
        tempSlider.value = config.temperature;
        updateSliderValue('temperature');
    }

    // Repeat penalty
    if (config.repeat_penalty !== undefined) {
        const repeatSlider = document.getElementById('llm-repeat-penalty');
        repeatSlider.value = config.repeat_penalty;
        updateSliderValue('repeat-penalty');
    }

    // Host
    if (config.host !== undefined) {
        document.getElementById('llm-host').value = config.host;
    }

    // Port
    if (config.port !== undefined) {
        document.getElementById('llm-port').value = config.port;
    }

    // Compute mode
    if (config.compute_mode !== undefined) {
        const computeRadio = document.querySelector(`input[name="compute-mode"][value="${config.compute_mode}"]`);
        if (computeRadio) {
            computeRadio.checked = true;
        }
    }

    // GPU layers
    if (config.gpu_layers !== undefined) {
        const gpuLayersSlider = document.getElementById('llm-gpu-layers');
        gpuLayersSlider.value = config.gpu_layers;
        updateSliderValue('gpu-layers');
    }

    // Threads
    if (config.threads !== undefined) {
        document.getElementById('llm-threads').value = config.threads;
    }

    // Advanced settings state
    if (config.advanced_settings_open) {
        const advancedSettings = document.getElementById('llm-advanced-settings');
        if (advancedSettings && advancedSettings.classList.contains('hidden')) {
            toggleAdvancedSettings();
        }
    }
}

/**
 * Get default configuration values
 * 
 * @returns {object} Default configuration
 */
function getDefaultConfig() {
    return {
        model: '',
        streaming: true,
        context_size: 15,
        max_tokens: 13,
        temperature: 0.1,
        repeat_penalty: 1.2,
        host: '127.0.0.1',
        port: 8080,
        compute_mode: 'auto',
        gpu_layers: 999,
        threads: 0,
        advanced_settings_open: false
    };
}

/**
 * Validate configuration object
 * 
 * @param {object} config - Configuration to validate
 * @returns {object} Validation result with valid boolean and errors array
 */
function validateConfig(config) {
    const errors = [];

    // Validate model
    if (!config.model || config.model.trim() === '') {
        errors.push('Please select a model');
    }

    // Validate port
    if (config.port < 1 || config.port > 65535) {
        errors.push('Port must be between 1 and 65535');
    }

    // Validate host
    if (!config.host || config.host.trim() === '') {
        errors.push('Host cannot be empty');
    }

    // Validate GPU layers
    if (config.gpu_layers < 0 || config.gpu_layers > 999) {
        errors.push('GPU layers must be between 0 and 999');
    }

    // Validate threads
    if (config.threads < 0) {
        errors.push('Threads cannot be negative');
    }

    return {
        valid: errors.length === 0,
        errors: errors
    };
}
