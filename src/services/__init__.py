"""
VoxBridge Services Package

This package contains service layer implementations for VoxBridge 2.0:
- agent_service: Agent CRUD operations
- conversation_service: Session and conversation management
- llm_service: LLM provider abstraction (OpenRouter, Local LLM)
- stt_service: Speech-to-Text service (WhisperX)
- tts_service: Text-to-Speech service (Chatterbox)
- rag_client: RAG service HTTP client (document ingestion, search)
- plugin_manager: Plugin lifecycle management
- plugin_resource_monitor: Resource monitoring for plugins
- session_service: Session state management
"""

from .agent_service import AgentService
from .conversation_service import ConversationService
from .llm_service import LLMService, get_llm_service, get_llm_service_for_agent
from .stt_service import STTService, get_stt_service
from .tts_service import TTSService, get_tts_service
from .rag_client import RAGClient, get_rag_client, close_rag_client
from .plugin_manager import PluginManager, get_plugin_manager
from .plugin_resource_monitor import PluginResourceMonitor, get_resource_monitor
from .session_service import SessionService

__all__ = [
    "AgentService",
    "ConversationService",
    "LLMService",
    "get_llm_service",
    "get_llm_service_for_agent",
    "STTService",
    "get_stt_service",
    "TTSService",
    "get_tts_service",
    "RAGClient",
    "get_rag_client",
    "close_rag_client",
    "PluginManager",
    "get_plugin_manager",
    "PluginResourceMonitor",
    "get_resource_monitor",
    "SessionService",
]
