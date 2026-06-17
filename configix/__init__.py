# Configix package initialization
from .apiManager import (
    switch_ai_provider,
    get_current_ai,
    get_ai_provider,
    get_mapbox_config,
    get_available_ai_providers,
    ai_gemini,
    ai_grok,
    ai_openai
)

__all__ = [
    'switch_ai_provider',
    'get_current_ai',
    'get_ai_provider',
    'get_mapbox_config',
    'get_available_ai_providers',
    'ai_gemini',
    'ai_grok',
    'ai_openai'
]
