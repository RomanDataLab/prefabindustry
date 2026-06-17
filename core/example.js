// Example usage of API Manager
const apiManager = require('../configix/apiManager');

// Example 1: Switch AI provider and use it
console.log('=== Example 1: Switching AI Providers ===');
console.log('Available providers:', apiManager.getAvailableAIProviders());

// Switch to Gemini
apiManager.switchAIProvider('ai_gemini');
const currentAI = apiManager.getCurrentAI();
console.log(`Current AI: ${currentAI.name}`);
console.log(`API Key: ${currentAI.apiKey.substring(0, 20)}...`);

// Switch to Grok
apiManager.switchAIProvider('ai_grok');
console.log(`Current AI: ${apiManager.getCurrentAI().name}`);

// Switch to OpenAI
apiManager.switchAIProvider('ai_openai');
console.log(`Current AI: ${apiManager.getCurrentAI().name}`);

// Example 2: Access specific provider directly
console.log('\n=== Example 2: Direct Provider Access ===');
const geminiConfig = apiManager.getAIProvider('ai_gemini');
console.log(`Gemini API Key: ${geminiConfig.apiKey.substring(0, 20)}...`);

// Example 3: Access Mapbox config
console.log('\n=== Example 3: Mapbox Configuration ===');
const mapboxConfig = apiManager.getMapboxConfig();
console.log('Mapbox Token:', mapboxConfig.MAPBOX_ACCESS_TOKEN.substring(0, 20) + '...');
console.log('Mapbox Style:', mapboxConfig.MAPBOX_STYLE);

// Example 4: Direct access via exported variables
console.log('\n=== Example 4: Direct Variable Access ===');
console.log('OpenAI API Key:', apiManager.ai_openai.apiKey.substring(0, 20) + '...');
console.log('Grok API Key:', apiManager.ai_grok.apiKey.substring(0, 20) + '...');
