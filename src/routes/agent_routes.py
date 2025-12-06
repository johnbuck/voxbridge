"""
Agent API Routes

FastAPI routes for managing AI agents in VoxBridge 2.0.
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from src.services.agent_service import AgentService
from src.database.session import get_db_session
from src.database.models import UserAgentMemorySetting

# WebSocket manager will be set by discord_bot.py
_ws_manager = None

def set_websocket_manager(manager):
    """Set the WebSocket manager for broadcasting agent events"""
    global _ws_manager
    _ws_manager = manager

async def broadcast_agent_event(event_type: str, agent_data: dict):
    """Broadcast agent CRUD events to WebSocket clients"""
    if _ws_manager:
        await _ws_manager.broadcast({
            "event": f"agent_{event_type}",
            "data": agent_data
        })


# ============================================================================
# Request/Response Models
# ============================================================================

class AgentCreateRequest(BaseModel):
    """Request body for creating an agent"""

    name: str = Field(..., min_length=1, max_length=100, description="Agent display name")
    system_prompt: str = Field(..., min_length=1, max_length=10000, description="System prompt for the agent")
    temperature: float = Field(0.7, ge=0.0, le=1.0, description="LLM temperature")
    llm_provider: str = Field("openrouter", description="LLM provider (openrouter or local)")
    llm_model: str = Field("anthropic/claude-3.5-sonnet", description="Model identifier")
    use_n8n: bool = Field(False, description="Use n8n webhook instead of direct LLM")
    n8n_webhook_url: Optional[str] = Field(None, max_length=500, description="Per-agent n8n webhook URL")
    is_default: bool = Field(False, description="Mark as default agent")
    tts_voice: Optional[str] = Field(None, description="TTS voice ID")
    tts_exaggeration: float = Field(1.0, ge=0.25, le=2.0, description="TTS emotion intensity (0.25-2.0)")
    tts_cfg_weight: float = Field(0.7, ge=0.0, le=1.0, description="TTS speech pace (0.0-1.0)")
    tts_temperature: float = Field(0.3, ge=0.05, le=5.0, description="TTS voice sampling (0.05-5.0)")
    tts_language: str = Field("en", description="TTS language code (e.g., 'en', 'es', 'fr')")
    filter_actions_for_tts: bool = Field(False, description="Remove roleplay actions (*text*) before TTS synthesis")
    plugins: Optional[dict] = Field(None, description="Plugin configurations (e.g., discord plugin)")


class AgentUpdateRequest(BaseModel):
    """Request body for updating an agent"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    system_prompt: Optional[str] = Field(None, min_length=1, max_length=10000)
    temperature: Optional[float] = Field(None, ge=0.0, le=1.0)
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    use_n8n: Optional[bool] = None
    n8n_webhook_url: Optional[str] = Field(None, max_length=500)
    is_default: Optional[bool] = None
    tts_voice: Optional[str] = None
    tts_exaggeration: Optional[float] = Field(None, ge=0.25, le=2.0)
    tts_cfg_weight: Optional[float] = Field(None, ge=0.0, le=1.0)
    tts_temperature: Optional[float] = Field(None, ge=0.05, le=5.0)
    tts_language: Optional[str] = None
    filter_actions_for_tts: Optional[bool] = Field(None, description="Remove roleplay actions (*text*) before TTS synthesis")
    memory_scope: Optional[str] = Field(None, description="Memory scope: 'global' or 'agent'")
    plugins: Optional[dict] = Field(None, description="Plugin configurations (e.g., discord plugin)")


class AgentResponse(BaseModel):
    """Response model for agent data"""

    id: str
    name: str
    system_prompt: str
    temperature: float
    llm_provider: str
    llm_model: str
    use_n8n: bool
    n8n_webhook_url: Optional[str]
    is_default: bool
    memory_scope: str = Field('global', description="Default memory scope (global or agent)")
    tts_voice: Optional[str]
    tts_exaggeration: float
    tts_cfg_weight: float
    tts_temperature: float
    tts_language: str
    filter_actions_for_tts: bool
    plugins: Optional[dict] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True  # Allows conversion from SQLAlchemy models


class UserAgentMemoryPreferenceRequest(BaseModel):
    """Request body for setting per-agent memory preference"""

    user_id: str = Field(..., description="User identifier (e.g., 'discord:123456789')")
    allow_agent_specific_memory: bool = Field(..., description="Enable agent-specific memory for this user-agent pair")


class UserAgentMemoryPreferenceResponse(BaseModel):
    """Response model for per-agent memory preference"""

    id: str
    user_id: str
    agent_id: str
    allow_agent_specific_memory: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


# ============================================================================
# Router Setup
# ============================================================================

router = APIRouter(prefix="/api/agents", tags=["agents"])


# ============================================================================
# Routes
# ============================================================================

@router.post(
    "",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Agent",
    description="Create a new AI agent with specified configuration"
)
async def create_agent(request: AgentCreateRequest):
    """
    Create a new agent.

    Returns the created agent with generated ID and timestamps.
    """
    try:
        agent = await AgentService.create_agent(
            name=request.name,
            system_prompt=request.system_prompt,
            temperature=request.temperature,
            llm_provider=request.llm_provider,
            llm_model=request.llm_model,
            use_n8n=request.use_n8n,
            n8n_webhook_url=request.n8n_webhook_url,
            is_default=request.is_default,
            tts_voice=request.tts_voice,
            tts_exaggeration=request.tts_exaggeration,
            tts_cfg_weight=request.tts_cfg_weight,
            tts_temperature=request.tts_temperature,
            tts_language=request.tts_language,
            filter_actions_for_tts=request.filter_actions_for_tts,
            plugins=request.plugins,
        )

        response = AgentResponse(
            id=str(agent.id),
            name=agent.name,
            system_prompt=agent.system_prompt,
            temperature=agent.temperature,
            llm_provider=agent.llm_provider,
            llm_model=agent.llm_model,
            use_n8n=agent.use_n8n,
            n8n_webhook_url=agent.n8n_webhook_url,
            is_default=agent.is_default,
            memory_scope=agent.memory_scope,
            tts_voice=agent.tts_voice,
            tts_exaggeration=agent.tts_exaggeration,
            tts_cfg_weight=agent.tts_cfg_weight,
            tts_temperature=agent.tts_temperature,
            tts_language=agent.tts_language,
            filter_actions_for_tts=agent.filter_actions_for_tts,
            plugins=agent.plugins,
            created_at=agent.created_at.isoformat(),
            updated_at=agent.updated_at.isoformat(),
        )

        # Broadcast agent creation event
        await broadcast_agent_event("created", response.model_dump())

        return response
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create agent: {str(e)}"
        )


@router.get(
    "",
    response_model=List[AgentResponse],
    summary="List Agents",
    description="Get all AI agents"
)
async def list_agents():
    """
    Get all agents.

    Returns a list of all agents ordered by creation date.
    """
    try:
        agents = await AgentService.get_all_agents()

        return [
            AgentResponse(
                id=str(agent.id),
                name=agent.name,
                system_prompt=agent.system_prompt,
                temperature=agent.temperature,
                llm_provider=agent.llm_provider,
                llm_model=agent.llm_model,
                use_n8n=agent.use_n8n,
                n8n_webhook_url=agent.n8n_webhook_url,
                is_default=agent.is_default,
                memory_scope=agent.memory_scope,
                tts_voice=agent.tts_voice,
                tts_exaggeration=agent.tts_exaggeration,
                tts_cfg_weight=agent.tts_cfg_weight,
                tts_temperature=agent.tts_temperature,
                tts_language=agent.tts_language,
                filter_actions_for_tts=agent.filter_actions_for_tts,
                plugins=agent.plugins,
                created_at=agent.created_at.isoformat(),
                updated_at=agent.updated_at.isoformat(),
            )
            for agent in agents
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch agents: {str(e)}"
        )


@router.get(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="Get Agent",
    description="Get a specific agent by ID"
)
async def get_agent(agent_id: UUID):
    """
    Get agent by ID.

    Args:
        agent_id: Agent UUID

    Returns:
        Agent data

    Raises:
        404: Agent not found
    """
    try:
        agent = await AgentService.get_agent(agent_id)

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent with ID {agent_id} not found"
            )

        return AgentResponse(
            id=str(agent.id),
            name=agent.name,
            system_prompt=agent.system_prompt,
            temperature=agent.temperature,
            llm_provider=agent.llm_provider,
            llm_model=agent.llm_model,
            use_n8n=agent.use_n8n,
            n8n_webhook_url=agent.n8n_webhook_url,
            is_default=agent.is_default,
            memory_scope=agent.memory_scope,
            tts_voice=agent.tts_voice,
            tts_exaggeration=agent.tts_exaggeration,
            tts_cfg_weight=agent.tts_cfg_weight,
            tts_temperature=agent.tts_temperature,
            tts_language=agent.tts_language,
            filter_actions_for_tts=agent.filter_actions_for_tts,
            plugins=agent.plugins,
            created_at=agent.created_at.isoformat(),
            updated_at=agent.updated_at.isoformat(),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch agent: {str(e)}"
        )


@router.put(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="Update Agent",
    description="Update an existing agent's configuration"
)
async def update_agent(agent_id: UUID, request: AgentUpdateRequest):
    """
    Update agent.

    Args:
        agent_id: Agent UUID
        request: Fields to update (all optional)

    Returns:
        Updated agent data

    Raises:
        404: Agent not found
        400: Validation error
    """
    try:
        agent = await AgentService.update_agent(
            agent_id=agent_id,
            name=request.name,
            system_prompt=request.system_prompt,
            temperature=request.temperature,
            llm_provider=request.llm_provider,
            llm_model=request.llm_model,
            use_n8n=request.use_n8n,
            n8n_webhook_url=request.n8n_webhook_url,
            is_default=request.is_default,
            tts_voice=request.tts_voice,
            tts_exaggeration=request.tts_exaggeration,
            tts_cfg_weight=request.tts_cfg_weight,
            tts_temperature=request.tts_temperature,
            tts_language=request.tts_language,
            filter_actions_for_tts=request.filter_actions_for_tts,
            memory_scope=request.memory_scope,
            plugins=request.plugins,
        )

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent with ID {agent_id} not found"
            )

        response = AgentResponse(
            id=str(agent.id),
            name=agent.name,
            system_prompt=agent.system_prompt,
            temperature=agent.temperature,
            llm_provider=agent.llm_provider,
            llm_model=agent.llm_model,
            use_n8n=agent.use_n8n,
            n8n_webhook_url=agent.n8n_webhook_url,
            is_default=agent.is_default,
            memory_scope=agent.memory_scope,
            tts_voice=agent.tts_voice,
            tts_exaggeration=agent.tts_exaggeration,
            tts_cfg_weight=agent.tts_cfg_weight,
            tts_temperature=agent.tts_temperature,
            tts_language=agent.tts_language,
            filter_actions_for_tts=agent.filter_actions_for_tts,
            plugins=agent.plugins,
            created_at=agent.created_at.isoformat(),
            updated_at=agent.updated_at.isoformat(),
        )

        # Broadcast agent update event
        await broadcast_agent_event("updated", response.model_dump())

        return response
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update agent: {str(e)}"
        )


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Agent",
    description="Delete an agent by ID"
)
async def delete_agent(agent_id: UUID):
    """
    Delete agent.

    Args:
        agent_id: Agent UUID

    Raises:
        404: Agent not found
    """
    try:
        deleted = await AgentService.delete_agent(agent_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent with ID {agent_id} not found"
            )

        # Broadcast agent deletion event
        await broadcast_agent_event("deleted", {"id": str(agent_id)})

        return None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete agent: {str(e)}"
        )


@router.put(
    "/{agent_id}/set-default",
    response_model=AgentResponse,
    summary="Set Default Agent",
    description="Mark an agent as the default agent (unsets any existing default)"
)
async def set_default_agent(agent_id: UUID):
    """
    Set agent as default.

    This will unset any existing default agent and mark the specified agent as default.

    Args:
        agent_id: Agent UUID to set as default

    Returns:
        Updated agent data with is_default=True

    Raises:
        404: Agent not found
    """
    try:
        agent = await AgentService.set_default_agent(agent_id)

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent with ID {agent_id} not found"
            )

        response = AgentResponse(
            id=str(agent.id),
            name=agent.name,
            system_prompt=agent.system_prompt,
            temperature=agent.temperature,
            llm_provider=agent.llm_provider,
            llm_model=agent.llm_model,
            use_n8n=agent.use_n8n,
            n8n_webhook_url=agent.n8n_webhook_url,
            is_default=agent.is_default,
            memory_scope=agent.memory_scope,
            tts_voice=agent.tts_voice,
            tts_exaggeration=agent.tts_exaggeration,
            tts_cfg_weight=agent.tts_cfg_weight,
            tts_temperature=agent.tts_temperature,
            tts_language=agent.tts_language,
            filter_actions_for_tts=agent.filter_actions_for_tts,
            plugins=agent.plugins,
            created_at=agent.created_at.isoformat(),
            updated_at=agent.updated_at.isoformat(),
        )

        # Broadcast agent update event
        await broadcast_agent_event("updated", response.model_dump())

        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set default agent: {str(e)}"
        )


@router.get(
    "/{agent_id}/memory-preference",
    response_model=Optional[UserAgentMemoryPreferenceResponse],
    summary="Get Memory Preference",
    description="Get user's memory preference for a specific agent (per-agent memory settings)"
)
async def get_memory_preference(
    agent_id: UUID,
    user_id: str = Query(..., description="User identifier (e.g., 'discord:123456789')")
):
    """
    Get user's memory preference for a specific agent.

    Args:
        agent_id: Agent UUID
        user_id: User identifier

    Returns:
        Memory preference settings if user has set an explicit preference, None otherwise

    Raises:
        404: No preference set (user falls back to agent default)
    """
    try:
        async with get_db_session() as db:
            result = await db.execute(
                select(UserAgentMemorySetting).where(
                    UserAgentMemorySetting.user_id == user_id,
                    UserAgentMemorySetting.agent_id == agent_id
                )
            )
            setting = result.scalar_one_or_none()

            if setting is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No memory preference set for user {user_id} and agent {agent_id}"
                )

            return UserAgentMemoryPreferenceResponse(
                id=str(setting.id),
                user_id=setting.user_id,
                agent_id=str(setting.agent_id),
                allow_agent_specific_memory=setting.allow_agent_specific_memory,
                created_at=setting.created_at.isoformat(),
                updated_at=setting.updated_at.isoformat(),
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get memory preference: {str(e)}"
        )


@router.put(
    "/{agent_id}/memory-preference",
    response_model=UserAgentMemoryPreferenceResponse,
    summary="Set Memory Preference",
    description="Set user's memory preference for a specific agent (create or update)"
)
async def set_memory_preference(
    agent_id: UUID,
    request: UserAgentMemoryPreferenceRequest
):
    """
    Set user's memory preference for a specific agent.

    Creates a new preference or updates existing preference.

    Args:
        agent_id: Agent UUID
        request: Memory preference settings (user_id, allow_agent_specific_memory)

    Returns:
        Updated memory preference settings

    Raises:
        404: Agent not found
        400: Validation error
    """
    try:
        # Verify agent exists
        agent = await AgentService.get_agent(agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent with ID {agent_id} not found"
            )

        async with get_db_session() as db:
            # Check if preference exists
            result = await db.execute(
                select(UserAgentMemorySetting).where(
                    UserAgentMemorySetting.user_id == request.user_id,
                    UserAgentMemorySetting.agent_id == agent_id
                )
            )
            setting = result.scalar_one_or_none()

            if setting:
                # Update existing
                setting.allow_agent_specific_memory = request.allow_agent_specific_memory
                setting.updated_at = func.now()
            else:
                # Create new
                setting = UserAgentMemorySetting(
                    user_id=request.user_id,
                    agent_id=agent_id,
                    allow_agent_specific_memory=request.allow_agent_specific_memory
                )
                db.add(setting)

            await db.commit()
            await db.refresh(setting)

            return UserAgentMemoryPreferenceResponse(
                id=str(setting.id),
                user_id=setting.user_id,
                agent_id=str(setting.agent_id),
                allow_agent_specific_memory=setting.allow_agent_specific_memory,
                created_at=setting.created_at.isoformat(),
                updated_at=setting.updated_at.isoformat(),
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set memory preference: {str(e)}"
        )


@router.delete(
    "/{agent_id}/memory-preference",
    status_code=status.HTTP_200_OK,
    summary="Delete Memory Preference",
    description="Delete user's memory preference for a specific agent (reset to agent default)"
)
async def delete_memory_preference(
    agent_id: UUID,
    user_id: str = Query(..., description="User identifier (e.g., 'discord:123456789')")
):
    """
    Delete user's memory preference for a specific agent.

    This resets the user's preference to use the agent's default memory scope.

    Args:
        agent_id: Agent UUID
        user_id: User identifier

    Returns:
        Success message

    Raises:
        404: No preference to delete
    """
    try:
        async with get_db_session() as db:
            result = await db.execute(
                select(UserAgentMemorySetting).where(
                    UserAgentMemorySetting.user_id == user_id,
                    UserAgentMemorySetting.agent_id == agent_id
                )
            )
            setting = result.scalar_one_or_none()

            if setting is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No memory preference to delete for user {user_id} and agent {agent_id}"
                )

            await db.delete(setting)
            await db.commit()

            return {"message": "Memory preference deleted, reverted to agent default"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete memory preference: {str(e)}"
        )
