"""
Lucy Code Services.
"""

from lucy.services.analytics import get_analytics
from lucy.services.compact import auto_compact_if_needed, compact_conversation
from lucy.services.cron_service import get_cron_service
from lucy.services.plugin_service import get_plugin_service
from lucy.services.prompt_suggestion import get_prompt_suggestions
from lucy.services.session_memory import get_session_memory
from lucy.services.tips import get_tips_service

__all__ = [
    "get_analytics",
    "compact_conversation",
    "auto_compact_if_needed",
    "get_cron_service",
    "get_plugin_service",
    "get_prompt_suggestions",
    "get_session_memory",
    "get_tips_service",
]
