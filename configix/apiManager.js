// API Manager - Switch between AI providers and access Mapbox config
const path = require('path');
const fs = require('fs');

// Load configurations
// Handle different workspace paths
let configDir = path.join(__dirname, '..', '..', 'config');
if (!fs.existsSync(configDir)) {
  // Try Windows absolute path
  configDir = 'C:\\12_CODINGHARD\\config';
  if (!fs.existsSync(configDir)) {
    // Try alternative relative path
    configDir = path.join(__dirname, '..', '..', '..', '..', 'config');
  }
}

// Verify config directory exists
if (!fs.existsSync(configDir)) {
  throw new Error(`Config directory not found. Tried: ${configDir}`);
}

let geminiConfig, grokConfig, openaiConfig, isochroneConfig, scrapeflyConfig, anisConfig;
try {
  geminiConfig = JSON.parse(fs.readFileSync(path.join(configDir, 'config_gemini.json'), 'utf8'));
  grokConfig = JSON.parse(fs.readFileSync(path.join(configDir, 'config_grok.json'), 'utf8'));
  openaiConfig = JSON.parse(fs.readFileSync(path.join(configDir, 'config_openai.json'), 'utf8'));
} catch (error) {
  throw new Error(`Error loading AI config files from ${configDir}: ${error.message}`);
}

// Load additional service configs (non-critical — warn but don't throw)
try {
  isochroneConfig = JSON.parse(fs.readFileSync(path.join(configDir, 'config_isochrone.json'), 'utf8'));
} catch (error) {
  console.warn('Warning: config_isochrone.json not loaded:', error.message);
  isochroneConfig = {};
}

try {
  scrapeflyConfig = JSON.parse(fs.readFileSync(path.join(configDir, 'config_scrapefly.json'), 'utf8'));
} catch (error) {
  console.warn('Warning: config_scrapefly.json not loaded:', error.message);
  scrapeflyConfig = {};
}

try {
  anisConfig = JSON.parse(fs.readFileSync(path.join(configDir, 'config_anis.json'), 'utf8'));
} catch (error) {
  console.warn('Warning: config_anis.json not loaded:', error.message);
  anisConfig = {};
}

// Also try to load ORS key from .env file as fallback
let orsEnvKey = null;
try {
  const envContent = fs.readFileSync(path.join(configDir, 'openrouteservice.env'), 'utf8');
  const match = envContent.match(/ORS_API_KEY\s*=\s*(.+)/);
  if (match) orsEnvKey = match[1].trim();
} catch (_) {
  // .env file optional
}

// Mapbox config (requires dynamic import for ES modules)
let mapboxConfig = null;
try {
  // For Node.js, we'll read and parse the JS file manually
  const mapboxConfigContent = fs.readFileSync(path.join(configDir, 'mapboxConfig.js'), 'utf8');
  const mapboxTokenMatch = mapboxConfigContent.match(/MAPBOX_ACCESS_TOKEN\s*=\s*['"]([^'"]+)['"]/);
  const mapboxStyleMatch = mapboxConfigContent.match(/MAPBOX_STYLE\s*=\s*['"]([^'"]+)['"]/);
  
  mapboxConfig = {
    MAPBOX_ACCESS_TOKEN: mapboxTokenMatch ? mapboxTokenMatch[1] : null,
    MAPBOX_STYLE: mapboxStyleMatch ? mapboxStyleMatch[1] : null
  };
} catch (error) {
  console.error('Error loading Mapbox config:', error);
}

// AI Provider configurations
const aiProviders = {
  ai_gemini: {
    name: 'Gemini',
    apiKey: geminiConfig.ITEM,
    config: geminiConfig
  },
  ai_grok: {
    name: 'Grok',
    apiKey: grokConfig.grok_api_key,
    config: grokConfig
  },
  ai_openai: {
    name: 'OpenAI',
    apiKey: openaiConfig.openai_api_key,
    config: openaiConfig
  }
};

// Current AI provider (default: OpenAI)
let currentAIProvider = 'ai_openai';

/**
 * Switch AI provider
 * @param {string} provider - Provider name with prefix (e.g., 'ai_gemini', 'ai_grok', 'ai_openai')
 */
function switchAIProvider(provider) {
  if (aiProviders[provider]) {
    currentAIProvider = provider;
    return true;
  }
  throw new Error(`Invalid AI provider: ${provider}. Available: ${Object.keys(aiProviders).join(', ')}`);
}

/**
 * Get current AI provider config
 * @returns {Object} Current AI provider configuration
 */
function getCurrentAI() {
  return aiProviders[currentAIProvider];
}

/**
 * Get specific AI provider config
 * @param {string} provider - Provider name with prefix (e.g., 'ai_gemini', 'ai_grok', 'ai_openai')
 * @returns {Object} AI provider configuration
 */
function getAIProvider(provider) {
  if (aiProviders[provider]) {
    return aiProviders[provider];
  }
  throw new Error(`Invalid AI provider: ${provider}. Available: ${Object.keys(aiProviders).join(', ')}`);
}

/**
 * Get Mapbox configuration
 * @returns {Object} Mapbox configuration
 */
function getMapboxConfig() {
  return mapboxConfig;
}

/**
 * Get all available AI providers
 * @returns {Array<string>} List of available AI provider keys
 */
function getAvailableAIProviders() {
  return Object.keys(aiProviders);
}

/**
 * Get OpenRouteService (isochrone) API key
 * @returns {string|null} ORS API key
 */
function getOrsApiKey() {
  return isochroneConfig?.ors_api_key || orsEnvKey || null;
}

/**
 * Get isochrone/ORS configuration
 * @returns {Object} Isochrone configuration
 */
function getIsochroneConfig() {
  return {
    ors_api_key: getOrsApiKey(),
    ...isochroneConfig
  };
}

/**
 * Get Scrapefly configuration
 * @returns {Object} Scrapefly configuration
 */
function getScrapeflyConfig() {
  return scrapeflyConfig;
}

/**
 * Get Anis (Anthropic) configuration
 * @returns {Object} Anis configuration
 */
function getAnisConfig() {
  return anisConfig;
}

module.exports = {
  // AI Provider switching
  switchAIProvider,
  getCurrentAI,
  getAIProvider,
  getAvailableAIProviders,

  // Mapbox
  getMapboxConfig,

  // OpenRouteService / Isochrone
  getOrsApiKey,
  getIsochroneConfig,

  // Scrapefly
  getScrapeflyConfig,

  // Anis (Anthropic)
  getAnisConfig,

  // Direct access to providers
  ai_gemini: aiProviders.ai_gemini,
  ai_grok: aiProviders.ai_grok,
  ai_openai: aiProviders.ai_openai,

  // Current provider reference
  currentAIProvider: () => currentAIProvider
};
