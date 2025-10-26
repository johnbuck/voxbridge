"""
Agent API Routes

FastAPI routes for managing AI agents in VoxBridge 2.0.
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.services.agent_service import AgentService

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
    tts_voice: Optional[str] = Field(None, description="TTS voice ID")
    tts_rate: float = Field(1.0, ge=0.5, le=2.0, description="TTS speech rate")
    tts_pitch: float = Field(1.0, ge=0.5, le=2.0, description="TTS pitch adjustment")


class AgentUpdateRequest(BaseModel):
    """Request body for updating an agent"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    system_prompt: Optional[str] = Field(None, min_length=1, max_length=10000)
    temperature: Optional[float] = Field(None, ge=0.0, le=1.0)
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    tts_voice: Optional[str] = None
    tts_rate: Optional[float] = Field(None, ge=0.5, le=2.0)
    tts_pitch: Optional[float] = Field(None, ge=0.5, le=2.0)


class AgentResponse(BaseModel):
    """Response model for agent data"""

    id: str
    name: str
    system_prompt: str
    temperature: float
    llm_provider: str
    llm_model: str
    tts_voice: Optional[str]
    tts_rate: float
    tts_pitch: float
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True  # Allows conversion from SQLAlchemy models


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
            tts_voice=request.tts_voice,
            tts_rate=request.tts_rate,
            tts_pitch=request.tts_pitch,
        )

        response = AgentResponse(
            id=str(agent.id),
            name=agent.name,
            system_prompt=agent.system_prompt,
            temperature=agent.temperature,
            llm_provider=agent.llm_provider,
            llm_model=agent.llm_model,
            tts_voice=agent.tts_voice,
            tts_rate=agent.tts_rate,
            tts_pitch=agent.tts_pitch,
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
                tts_voice=agent.tts_voice,
                tts_rate=agent.tts_rate,
                tts_pitch=agent.tts_pitch,
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
            tts_voice=agent.tts_voice,
            tts_rate=agent.tts_rate,
            tts_pitch=agent.tts_pitch,
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
            tts_voice=request.tts_voice,
            tts_rate=request.tts_rate,
            tts_pitch=request.tts_pitch,
        )

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
            tts_voice=agent.tts_voice,
            tts_rate=agent.tts_rate,
            tts_pitch=agent.tts_pitch,
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
