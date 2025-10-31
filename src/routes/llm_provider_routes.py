"""
LLM Provider API Routes

FastAPI routes for managing LLM providers in VoxBridge 2.0.

Phase 6.5.4: LLM Provider Management System
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.services.llm_provider_service import LLMProviderService

# WebSocket manager will be set by server.py
_ws_manager = None


def set_websocket_manager(manager):
    """Set the WebSocket manager for broadcasting provider events"""
    global _ws_manager
    _ws_manager = manager


async def broadcast_provider_event(event_type: str, provider_data: dict):
    """Broadcast provider CRUD events to WebSocket clients"""
    if _ws_manager:
        await _ws_manager.broadcast({
            "event": f"llm_provider_{event_type}",
            "data": provider_data
        })


# ============================================================================
# Request/Response Models
# ============================================================================

class LLMProviderCreateRequest(BaseModel):
    """Request body for creating an LLM provider"""

    name: str = Field(..., min_length=1, max_length=255, description="Provider display name")
    base_url: str = Field(..., min_length=1, max_length=512, description="OpenAI-compatible API base URL")
    api_key: Optional[str] = Field(None, description="API key for authentication (will be encrypted)")
    provider_type: Optional[str] = Field(None, max_length=50, description="Provider type (openrouter, ollama, openai, vllm, custom)")
    default_model: Optional[str] = Field(None, max_length=255, description="Default model identifier")
    is_active: bool = Field(True, description="Whether provider is active")


class LLMProviderUpdateRequest(BaseModel):
    """Request body for updating an LLM provider"""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    base_url: Optional[str] = Field(None, min_length=1, max_length=512)
    api_key: Optional[str] = Field(None, description="New API key (will be re-encrypted)")
    provider_type: Optional[str] = Field(None, max_length=50)
    default_model: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None


class LLMProviderResponse(BaseModel):
    """Response model for LLM provider data (API key is never exposed)"""

    id: str
    name: str
    base_url: str
    has_api_key: bool  # Boolean flag instead of actual key
    provider_type: Optional[str]
    models: List[str]
    default_model: Optional[str]
    is_active: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class ConnectionTestResponse(BaseModel):
    """Response model for connection test"""

    success: bool
    models_count: Optional[int] = None
    error: Optional[str] = None
    response_time_ms: Optional[float] = None


class ModelFetchResponse(BaseModel):
    """Response model for model fetch"""

    success: bool
    models_count: Optional[int] = None
    models: Optional[List[str]] = None
    error: Optional[str] = None


# ============================================================================
# Router Setup
# ============================================================================

router = APIRouter(prefix="/api/settings/llm-providers", tags=["llm-providers"])


# ============================================================================
# Routes
# ============================================================================

@router.post(
    "",
    response_model=LLMProviderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create LLM Provider",
    description="Create a new OpenAI-compatible LLM provider configuration"
)
async def create_provider(request: LLMProviderCreateRequest):
    """
    Create a new LLM provider.

    API key will be encrypted before storing in database.

    Returns the created provider with generated ID and timestamps.
    """
    try:
        provider = await LLMProviderService.create_provider(
            name=request.name,
            base_url=request.base_url,
            api_key=request.api_key,
            provider_type=request.provider_type,
            default_model=request.default_model,
            is_active=request.is_active,
        )

        response = LLMProviderResponse(
            id=str(provider.id),
            name=provider.name,
            base_url=provider.base_url,
            has_api_key=bool(provider.api_key_encrypted),
            provider_type=provider.provider_type,
            models=provider.models or [],
            default_model=provider.default_model,
            is_active=provider.is_active,
            created_at=provider.created_at.isoformat(),
            updated_at=provider.updated_at.isoformat(),
        )

        # Broadcast provider creation event
        await broadcast_provider_event("created", response.model_dump())

        return response
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create provider: {str(e)}"
        )


@router.get(
    "",
    response_model=List[LLMProviderResponse],
    summary="List LLM Providers",
    description="Get all LLM provider configurations"
)
async def list_providers():
    """
    Get all LLM providers.

    Returns a list of all providers ordered by creation date.
    API keys are never exposed in the response.
    """
    try:
        providers = await LLMProviderService.get_all_providers()

        return [
            LLMProviderResponse(
                id=str(provider.id),
                name=provider.name,
                base_url=provider.base_url,
                has_api_key=bool(provider.api_key_encrypted),
                provider_type=provider.provider_type,
                models=provider.models or [],
                default_model=provider.default_model,
                is_active=provider.is_active,
                created_at=provider.created_at.isoformat(),
                updated_at=provider.updated_at.isoformat(),
            )
            for provider in providers
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch providers: {str(e)}"
        )


@router.get(
    "/{provider_id}",
    response_model=LLMProviderResponse,
    summary="Get LLM Provider",
    description="Get a specific LLM provider by ID"
)
async def get_provider(provider_id: UUID):
    """
    Get LLM provider by ID.

    Args:
        provider_id: Provider UUID

    Returns:
        Provider data (API key is never exposed)

    Raises:
        404: Provider not found
    """
    try:
        provider = await LLMProviderService.get_provider(provider_id)

        if not provider:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Provider with ID {provider_id} not found"
            )

        return LLMProviderResponse(
            id=str(provider.id),
            name=provider.name,
            base_url=provider.base_url,
            has_api_key=bool(provider.api_key_encrypted),
            provider_type=provider.provider_type,
            models=provider.models or [],
            default_model=provider.default_model,
            is_active=provider.is_active,
            created_at=provider.created_at.isoformat(),
            updated_at=provider.updated_at.isoformat(),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch provider: {str(e)}"
        )


@router.put(
    "/{provider_id}",
    response_model=LLMProviderResponse,
    summary="Update LLM Provider",
    description="Update an existing LLM provider's configuration"
)
async def update_provider(provider_id: UUID, request: LLMProviderUpdateRequest):
    """
    Update LLM provider.

    API key will be re-encrypted if changed.

    Args:
        provider_id: Provider UUID
        request: Fields to update (all optional)

    Returns:
        Updated provider data

    Raises:
        404: Provider not found
        400: Validation error
    """
    try:
        provider = await LLMProviderService.update_provider(
            provider_id=provider_id,
            name=request.name,
            base_url=request.base_url,
            api_key=request.api_key,
            provider_type=request.provider_type,
            default_model=request.default_model,
            is_active=request.is_active,
        )

        if not provider:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Provider with ID {provider_id} not found"
            )

        response = LLMProviderResponse(
            id=str(provider.id),
            name=provider.name,
            base_url=provider.base_url,
            has_api_key=bool(provider.api_key_encrypted),
            provider_type=provider.provider_type,
            models=provider.models or [],
            default_model=provider.default_model,
            is_active=provider.is_active,
            created_at=provider.created_at.isoformat(),
            updated_at=provider.updated_at.isoformat(),
        )

        # Broadcast provider update event
        await broadcast_provider_event("updated", response.model_dump())

        return response
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update provider: {str(e)}"
        )


@router.delete(
    "/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete LLM Provider",
    description="Delete an LLM provider by ID"
)
async def delete_provider(provider_id: UUID):
    """
    Delete LLM provider.

    Args:
        provider_id: Provider UUID

    Raises:
        404: Provider not found
    """
    try:
        deleted = await LLMProviderService.delete_provider(provider_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Provider with ID {provider_id} not found"
            )

        # Broadcast provider deletion event
        await broadcast_provider_event("deleted", {"id": str(provider_id)})

        return None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete provider: {str(e)}"
        )


@router.post(
    "/{provider_id}/test",
    response_model=ConnectionTestResponse,
    summary="Test Connection",
    description="Test connection to LLM provider's /v1/models endpoint"
)
async def test_connection(provider_id: UUID):
    """
    Test connection to LLM provider.

    Calls the provider's /v1/models endpoint to verify connectivity and authentication.

    Args:
        provider_id: Provider UUID

    Returns:
        Connection test results with model count and response time

    Raises:
        404: Provider not found
    """
    try:
        result = await LLMProviderService.test_connection(provider_id)

        if not result.get("success") and "not found" in result.get("error", ""):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result.get("error")
            )

        return ConnectionTestResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to test connection: {str(e)}"
        )


@router.post(
    "/{provider_id}/fetch-models",
    response_model=ModelFetchResponse,
    summary="Fetch Models",
    description="Fetch available models from provider and update database"
)
async def fetch_models(provider_id: UUID):
    """
    Fetch available models from LLM provider.

    Calls the provider's /v1/models endpoint, extracts model IDs, and updates the database.

    Args:
        provider_id: Provider UUID

    Returns:
        Fetch results with model list

    Raises:
        404: Provider not found
    """
    try:
        result = await LLMProviderService.fetch_models(provider_id)

        if not result.get("success") and "not found" in result.get("error", ""):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result.get("error")
            )

        # Broadcast provider update event (models changed)
        if result.get("success"):
            provider = await LLMProviderService.get_provider(provider_id)
            if provider:
                response = LLMProviderResponse(
                    id=str(provider.id),
                    name=provider.name,
                    base_url=provider.base_url,
                    has_api_key=bool(provider.api_key_encrypted),
                    provider_type=provider.provider_type,
                    models=provider.models or [],
                    default_model=provider.default_model,
                    is_active=provider.is_active,
                    created_at=provider.created_at.isoformat(),
                    updated_at=provider.updated_at.isoformat(),
                )
                await broadcast_provider_event("updated", response.model_dump())

        return ModelFetchResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch models: {str(e)}"
        )
