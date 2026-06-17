# API Manager - Switch between AI providers and access Mapbox config
import os
import json
import re
from pathlib import Path

# Load configurations
# Handle different workspace paths
config_dir = Path(__file__).parent.parent / 'config'
if not config_dir.exists():
    # Try Windows absolute path
    config_dir = Path('C:/12_CODINGHARD/config')
    if not config_dir.exists():
        # Try alternative relative path
        config_dir = Path(__file__).parent.parent.parent.parent / 'config'

# Verify config directory exists
if not config_dir.exists():
    raise FileNotFoundError(f"Config directory not found. Tried: {config_dir}")

try:
    with open(config_dir / 'config_gemini.json', 'r', encoding='utf-8') as f:
        gemini_config = json.load(f)
    with open(config_dir / 'config_grok.json', 'r', encoding='utf-8') as f:
        grok_config = json.load(f)
    with open(config_dir / 'config_openai.json', 'r', encoding='utf-8') as f:
        openai_config = json.load(f)
except Exception as e:
    raise Exception(f"Error loading config files from {config_dir}: {str(e)}")

# Mapbox config
mapbox_config = None
try:
    with open(config_dir / 'mapboxConfig.js', 'r', encoding='utf-8') as f:
        mapbox_config_content = f.read()
    
    mapbox_token_match = re.search(r"MAPBOX_ACCESS_TOKEN\s*=\s*['\"]([^'\"]+)['\"]", mapbox_config_content)
    mapbox_style_match = re.search(r"MAPBOX_STYLE\s*=\s*['\"]([^'\"]+)['\"]", mapbox_config_content)
    
    mapbox_config = {
        'MAPBOX_ACCESS_TOKEN': mapbox_token_match.group(1) if mapbox_token_match else None,
        'MAPBOX_STYLE': mapbox_style_match.group(1) if mapbox_style_match else None
    }
except Exception as e:
    print(f'Error loading Mapbox config: {e}')

# AI Provider configurations
ai_providers = {
    'ai_gemini': {
        'name': 'Gemini',
        'api_key': gemini_config.get('ITEM'),
        'config': gemini_config
    },
    'ai_grok': {
        'name': 'Grok',
        'api_key': grok_config.get('grok_api_key'),
        'config': grok_config
    },
    'ai_openai': {
        'name': 'OpenAI',
        'api_key': openai_config.get('openai_api_key'),
        'config': openai_config
    }
}

# Current AI provider (default: OpenAI)
current_ai_provider = 'ai_openai'

def switch_ai_provider(provider):
    """Switch AI provider"""
    global current_ai_provider
    if provider in ai_providers:
        current_ai_provider = provider
        return True
    raise ValueError(f"Invalid AI provider: {provider}. Available: {', '.join(ai_providers.keys())}")

def get_current_ai():
    """Get current AI provider config"""
    return ai_providers[current_ai_provider]

def get_ai_provider(provider):
    """Get specific AI provider config"""
    if provider in ai_providers:
        return ai_providers[provider]
    raise ValueError(f"Invalid AI provider: {provider}. Available: {', '.join(ai_providers.keys())}")

def get_mapbox_config():
    """Get Mapbox configuration"""
    return mapbox_config

def get_available_ai_providers():
    """Get all available AI providers"""
    return list(ai_providers.keys())

# OpenRouteService API key file path
ors_api_key_path = str(config_dir / 'openrouteservice.env')

# Load ORS API key from env file if present
ors_api_key = None
try:
    if Path(ors_api_key_path).exists():
        with open(ors_api_key_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('ORS_API_KEY='):
                    ors_api_key = line.split('=', 1)[1].strip() or None
                    break
except Exception as e:
    print(f'Error loading ORS API key: {e}')

# Isochrone GeoJSON output path
iso = str(Path(__file__).parent.parent / 'maps' / 'isochrones.geojson')

# Export for direct access
ai_gemini = ai_providers['ai_gemini']
ai_grok = ai_providers['ai_grok']
ai_openai = ai_providers['ai_openai']
