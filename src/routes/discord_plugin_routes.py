"""
Discord Plugin API Routes

Phase 3: HTTP API for Discord voice control via plugin system.

Provides plugin-scoped endpoints to control Discord voice connections
for individual agents. Routes through PluginManager to access the
correct DiscordPlugin instance.

Endpoints:
- POST /api/plugins/discord/voice/join - Join voice channel for an agent
- POST /api/plugins/discord/voice/leave - Leave voice channel for an agent
- GET /api/plugins/discord/voice/status/{agent_id} - Get voice status for an agent
"""

from typing import Dict, Any, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.services.plugin_manager import get_plugin_manager

router = APIRouter(prefix="/api/plugins/discord", tags=["discord-plugin"])


# ============================================================
# REQUEST/RESPONSE MODELS
# ============================================================

class VoiceJoinRequest(BaseModel):
    """Request to join a Discord voice channel"""
    agent_id: str
    guild_id: int
    channel_id: int
    session_id: Optional[str] = None  # Phase 6.X: Optional session for unified conversation threading


class VoiceLeaveRequest(BaseModel):
    """Request to leave a Discord voice channel"""
    agent_id: str
    guild_id: int


# ============================================================
# VOICE CONTROL ENDPOINTS
# ============================================================

@router.post("/voice/join")
async def join_voice_channel(request: VoiceJoinRequest) -> Dict[str, Any]:
    """
    Join Discord voice channel for an agent.

    Phase 3: Plugin-scoped voice control
    Phase 6.X: Unified Conversation Threading - accepts optional session_id

    Args:
        request: VoiceJoinRequest with agent_id, guild_id, channel_id, session_id (optional)

    Returns:
        Dict with connection status and metadata

    Raises:
        HTTPException 404: If agent or Discord plugin not found
        HTTPException 500: If connection fails
    """
    try:
        plugin_manager = get_plugin_manager()
        agent_id = UUID(request.agent_id)

        result = await plugin_manager.discord_join_voice(
            agent_id,
            request.guild_id,
            request.channel_id,
            request.session_id  # Pass through session_id
        )

        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@router.post("/voice/leave")
async def leave_voice_channel(request: VoiceLeaveRequest) -> Dict[str, Any]:
    """
    Leave Discord voice channel for an agent.

    Phase 3: Plugin-scoped voice control

    Args:
        request: VoiceLeaveRequest with agent_id, guild_id

    Returns:
        Dict with disconnection status and metadata

    Raises:
        HTTPException 404: If agent or Discord plugin not found
        HTTPException 500: If disconnection fails
    """
    try:
        plugin_manager = get_plugin_manager()
        agent_id = UUID(request.agent_id)

        result = await plugin_manager.discord_leave_voice(
            agent_id,
            request.guild_id
        )

        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@router.get("/voice/status/{agent_id}")
async def get_voice_status(agent_id: str) -> Dict[str, Any]:
    """
    Get Discord voice connection status for an agent.

    Phase 3: Plugin-scoped voice status

    Args:
        agent_id: Agent UUID (path parameter)

    Returns:
        Dict with voice connection details (connections, active_sessions)

    Raises:
        HTTPException 404: If agent or Discord plugin not found
    """
    try:
        plugin_manager = get_plugin_manager()
        agent_uuid = UUID(agent_id)

        result = plugin_manager.discord_get_voice_status(agent_uuid)

        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")
