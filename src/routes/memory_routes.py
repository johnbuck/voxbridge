"""
Memory Management API Routes (VoxBridge 2.0 Phase 2)

Endpoints for managing user facts, memory settings, and GDPR compliance.

User Fact Management:
- GET /api/memory/users/{user_id}/facts - List all facts for a user
- POST /api/memory/users/{user_id}/facts - Manually create a fact
- PUT /api/memory/users/{user_id}/facts/{fact_id} - Update a fact
- DELETE /api/memory/users/{user_id}/facts/{fact_id} - Delete a fact

Memory Settings:
- GET /api/memory/users/{user_id}/settings - Get user memory settings
- PUT /api/memory/users/{user_id}/settings - Update memory settings

GDPR Compliance:
- GET /api/memory/users/{user_id}/export - Export all user data as JSON
- DELETE /api/memory/users/{user_id} - Delete all user data (GDPR right to erasure)

NOTE: These endpoints will be restricted to authenticated users in a future phase.
Currently accessible to all users for development purposes.
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Optional, List, Literal
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, delete as sql_delete, and_, func

from src.database.models import User, UserFact, Agent, ExtractionTask
from src.database.session import get_db_session
from src.services.memory_service import MemoryService, get_global_embedding_config
from src.config.logging_config import get_logger

# Import global memory_service instance
from src.api import server

logger = get_logger(__name__)

router = APIRouter(prefix="/api/memory", tags=["memory"])


# Request/Response Models
class FactCreateRequest(BaseModel):
    """Request model for creating a fact manually."""
    agent_id: UUID = Field(..., description="Agent ID to use for embedding configuration")
    scope: Literal['global', 'agent'] = Field(..., description="'global' = shared across agents (agent_id NULL), 'agent' = agent-specific (agent_id UUID)")
    fact_key: str = Field(..., description="Fact key (e.g., 'name', 'location')")
    fact_value: str = Field(..., description="Fact value (e.g., 'Alice', 'San Francisco')")
    fact_text: Optional[str] = Field(None, description="Natural language representation")
    importance: float = Field(0.8, ge=0.0, le=1.0, description="Importance score (0.0-1.0)")


class FactUpdateRequest(BaseModel):
    """Request model for updating a fact."""
    fact_value: Optional[str] = Field(None, description="Updated fact value")
    fact_text: Optional[str] = Field(None, description="Updated natural language representation")
    importance: Optional[float] = Field(None, ge=0.0, le=1.0, description="Updated importance score")
    validity_end: Optional[datetime] = Field(None, description="Mark fact as invalid after this time")


class FactResponse(BaseModel):
    """Response model for a user fact."""
    id: UUID
    user_id: UUID
    agent_id: Optional[UUID]
    fact_key: str
    fact_value: str
    fact_text: Optional[str]
    importance: float
    vector_id: Optional[str]
    embedding_provider: Optional[str]
    embedding_model: Optional[str]
    validity_start: datetime
    validity_end: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    is_valid: bool  # Computed: validity_end is None or in future

    class Config:
        from_attributes = True


class MemorySettingsResponse(BaseModel):
    """Response model for user memory settings."""
    user_id: str
    display_name: Optional[str]
    embedding_provider: Optional[str]
    memory_extraction_enabled: bool
    allow_agent_specific_memory: bool  # When False: forces all new facts to global, deletes existing agent-specific facts
    last_login_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    total_facts: int  # Computed
    global_facts: int  # Computed
    agent_specific_facts: int  # Computed


class MemorySettingsUpdateRequest(BaseModel):
    """Request model for updating memory settings."""
    display_name: Optional[str] = Field(None, description="User display name")
    memory_extraction_enabled: Optional[bool] = Field(None, description="Enable/disable memory extraction")
    allow_agent_specific_memory: Optional[bool] = Field(None, description="When False: forces all new facts to global AND deletes existing agent-specific facts")


class GDPRExportResponse(BaseModel):
    """Response model for GDPR data export."""
    user_id: str
    display_name: Optional[str]
    exported_at: str
    total_facts: int
    facts: List[FactResponse]


# === User Fact Management ===

@router.get("/users/{user_id}/facts", response_model=List[FactResponse])
async def list_user_facts(
    user_id: str,
    scope: Optional[str] = Query(None, description="Filter by scope: 'global' (agent_id=NULL), 'agent' (agent_id!=NULL), or 'all'"),
    agent_id: Optional[UUID] = Query(None, description="Filter by specific agent ID (overrides scope parameter)"),
    include_invalid: bool = Query(False, description="Include facts with validity_end in the past")
):
    """
    List all facts for a user with optional filtering by scope or agent.

    Args:
        user_id: User identifier (e.g., "discord:123456789")
        scope: Filter by fact scope:
            - 'global': Only global facts (agent_id=NULL, shared across all agents)
            - 'agent': Only agent-specific facts (agent_id!=NULL, scoped to specific agents)
            - 'all' or None: All facts (default)
        agent_id: Filter by specific agent UUID (overrides scope parameter)
        include_invalid: Include facts marked as invalid (validity_end in past)

    Returns:
        List of user facts sorted by creation date (newest first)

    Examples:
        - GET /users/discord:123/facts - All facts (global + agent-specific)
        - GET /users/discord:123/facts?scope=global - Only global facts
        - GET /users/discord:123/facts?scope=agent - Only agent-specific facts
        - GET /users/discord:123/facts?agent_id=uuid - Facts for specific agent only
    """
    try:
        async with get_db_session() as db:
            # Get user
            result = await db.execute(
                select(User).where(User.user_id == user_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                raise HTTPException(status_code=404, detail=f"User {user_id} not found")

            # Build query
            query = select(UserFact).where(UserFact.user_id == user.id)

            # Filter by agent_id or scope
            if agent_id is not None:
                # Specific agent filter (overrides scope)
                query = query.where(UserFact.agent_id == agent_id)
            elif scope == "global":
                # Global facts only (agent_id = NULL)
                query = query.where(UserFact.agent_id.is_(None))
            elif scope == "agent":
                # Agent-specific facts only (agent_id != NULL)
                query = query.where(UserFact.agent_id.isnot(None))

            # Filter out invalid facts if requested
            if not include_invalid:
                query = query.where(
                    (UserFact.validity_end.is_(None)) | (UserFact.validity_end > datetime.utcnow())
                )

            # Sort by created_at descending
            query = query.order_by(UserFact.created_at.desc())

            result = await db.execute(query)
            facts = result.scalars().all()

            # Convert to response models
            fact_responses = []
            for fact in facts:
                is_valid = fact.validity_end is None or fact.validity_end > datetime.utcnow()
                fact_responses.append(
                    FactResponse(
                        id=fact.id,
                        user_id=fact.user_id,
                        agent_id=fact.agent_id,
                        fact_key=fact.fact_key,
                        fact_value=fact.fact_value,
                        fact_text=fact.fact_text,
                        importance=fact.importance,
                        vector_id=fact.vector_id,
                        embedding_provider=fact.embedding_provider,
                        embedding_model=fact.embedding_model,
                        validity_start=fact.validity_start,
                        validity_end=fact.validity_end,
                        created_at=fact.created_at,
                        updated_at=fact.updated_at,
                        is_valid=is_valid
                    )
                )

            logger.info(f"📚 Listed {len(fact_responses)} facts for user {user_id}")
            return fact_responses

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to list facts for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list facts: {str(e)}")


@router.post("/users/{user_id}/facts")
async def create_user_fact(user_id: str, request: FactCreateRequest):
    """
    Queue a fact for background creation.

    This queues the fact creation task for background processing using the
    existing extraction queue system. The fact will be created after Mem0
    generates embeddings (~30-60 seconds).

    Args:
        user_id: User identifier (e.g., "discord:123456789")
        request: Fact creation request

    Returns:
        Task status with task_id for tracking
    """
    try:
        async with get_db_session() as db:
            # Get or create user
            result = await db.execute(
                select(User).where(User.user_id == user_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                # Create user if doesn't exist
                user = User(
                    user_id=user_id,
                    memory_extraction_enabled=True
                )
                db.add(user)
                await db.flush()
                logger.info(f"✨ Created new user: {user_id}")

            # Validate agent exists (used for embedding configuration)
            agent_result = await db.execute(
                select(Agent).where(Agent.id == request.agent_id)
            )
            agent = agent_result.scalar_one_or_none()
            if not agent:
                raise HTTPException(status_code=404, detail=f"Agent {request.agent_id} not found")

            # Pass both agent_id and scope to task queue
            agent_id_for_task = request.agent_id
            scope_for_task = request.scope

            # Generate fact_text if not provided
            fact_text = request.fact_text or f"{request.fact_key}: {request.fact_value}"

            # Create extraction task for background processing
            # Store fact creation details in user_message as JSON for queue worker
            task_data = json.dumps({
                "manual": True,
                "fact_key": request.fact_key,
                "fact_value": request.fact_value,
                "importance": request.importance,
                "agent_id": str(request.agent_id),
                "scope": request.scope  # 'global' or 'agent'
            })

            task = ExtractionTask(
                user_id=user_id,
                agent_id=agent_id_for_task,
                user_message=f"MANUAL_FACT_CREATION:{task_data}",
                ai_response=fact_text,
                status="pending"
            )

            db.add(task)
            await db.commit()
            await db.refresh(task)

            logger.info(f"📋 Queued fact creation task for user {user_id}: {request.fact_key} = {request.fact_value} (task_id={task.id})")

            # Broadcast WebSocket event (reuse existing event system)
            try:
                from src.api.server import ws_manager
                if ws_manager:
                    await ws_manager.broadcast({
                        "event": "memory_extraction_queued",
                        "data": {
                            "task_id": str(task.id),
                            "user_id": user_id,
                            "agent_id": str(request.agent_id) if request.agent_id else None,
                            "status": "queued",
                            "manual": True,
                            "fact_key": request.fact_key,
                            "fact_value": request.fact_value,
                            "fact_text": fact_text,  # Include for placeholder display
                            "importance": request.importance  # Include for placeholder display
                        }
                    })
            except Exception as ws_error:
                logger.warning(f"⚠️ Failed to broadcast WebSocket event: {ws_error}")

            # Return task status immediately (non-blocking)
            return {
                "task_id": str(task.id),
                "status": "queued",
                "message": "Fact queued for background processing. You will receive a notification when indexing completes."
            }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"❌ Failed to queue fact creation for user {user_id}: {e}")
        logger.error(f"❌ Full traceback:\n{error_traceback}")
        raise HTTPException(status_code=500, detail=f"Failed to queue fact creation: {str(e)}")


@router.put("/users/{user_id}/facts/{fact_id}", response_model=FactResponse)
async def update_user_fact(user_id: str, fact_id: UUID, request: FactUpdateRequest):
    """
    Update a user fact.

    Args:
        user_id: User identifier
        fact_id: Fact UUID
        request: Fact update request

    Returns:
        Updated fact
    """
    try:
        async with get_db_session() as db:
            # Get user
            user_result = await db.execute(
                select(User).where(User.user_id == user_id)
            )
            user = user_result.scalar_one_or_none()
            if not user:
                raise HTTPException(status_code=404, detail=f"User {user_id} not found")

            # Get fact
            fact_result = await db.execute(
                select(UserFact).where(
                    and_(UserFact.id == fact_id, UserFact.user_id == user.id)
                )
            )
            fact = fact_result.scalar_one_or_none()
            if not fact:
                raise HTTPException(status_code=404, detail=f"Fact {fact_id} not found")

            # Update fields
            if request.fact_value is not None:
                fact.fact_value = request.fact_value
            if request.fact_text is not None:
                fact.fact_text = request.fact_text
            if request.importance is not None:
                fact.importance = request.importance
            if request.validity_end is not None:
                fact.validity_end = request.validity_end

            fact.updated_at = datetime.utcnow()

            await db.commit()
            await db.refresh(fact)

            logger.info(f"✏️ Updated fact {fact_id} for user {user_id}")

            is_valid = fact.validity_end is None or fact.validity_end > datetime.utcnow()
            return FactResponse(
                id=fact.id,
                user_id=fact.user_id,
                agent_id=fact.agent_id,
                fact_key=fact.fact_key,
                fact_value=fact.fact_value,
                fact_text=fact.fact_text,
                importance=fact.importance,
                vector_id=fact.vector_id,
                embedding_provider=fact.embedding_provider,
                embedding_model=fact.embedding_model,
                validity_start=fact.validity_start,
                validity_end=fact.validity_end,
                created_at=fact.created_at,
                updated_at=fact.updated_at,
                is_valid=is_valid
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to update fact {fact_id} for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update fact: {str(e)}")


@router.delete("/users/{user_id}/facts/{fact_id}")
async def delete_user_fact(user_id: str, fact_id: UUID):
    """
    Delete a user fact and its associated vector.

    ARCHITECTURE: VoxBridge dual-table design cleanup
    - Deletes fact from user_facts (VoxBridge-managed metadata)
    - Deletes vector from user_memories (Mem0-managed vectors)
    - Ensures no orphaned vectors remain

    Args:
        user_id: User identifier
        fact_id: Fact UUID

    Returns:
        Success message
    """
    try:
        async with get_db_session() as db:
            # Get user
            user_result = await db.execute(
                select(User).where(User.user_id == user_id)
            )
            user = user_result.scalar_one_or_none()
            if not user:
                raise HTTPException(status_code=404, detail=f"User {user_id} not found")

            # Get fact (need vector_id before deletion)
            fact_result = await db.execute(
                select(UserFact).where(
                    and_(UserFact.id == fact_id, UserFact.user_id == user.id)
                )
            )
            fact = fact_result.scalar_one_or_none()

            if not fact:
                raise HTTPException(status_code=404, detail=f"Fact {fact_id} not found")

            vector_id = fact.vector_id  # Capture before deletion

            # Delete fact from PostgreSQL
            await db.delete(fact)
            await db.commit()
            logger.info(f"🗑️ Deleted fact {fact_id} from user_facts")

            # Delete vector from Mem0 (if exists)
            if vector_id:
                try:
                    # Import here to avoid circular dependency
                    from src.api.server import memory_service

                    memory_service.memory.delete(memory_id=vector_id)
                    logger.info(f"🗑️ Deleted Mem0 vector {vector_id} from user_memories")
                except Exception as e:
                    # Log warning but don't fail the deletion (fact is already gone)
                    logger.warning(f"⚠️ Failed to delete Mem0 vector {vector_id}: {e}")

            return {"status": "deleted", "fact_id": str(fact_id), "vector_id": vector_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to delete fact {fact_id} for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete fact: {str(e)}")


# === Memory Settings ===

@router.get("/users/{user_id}/settings", response_model=MemorySettingsResponse)
async def get_memory_settings(user_id: str):
    """
    Get memory settings for a user.

    Args:
        user_id: User identifier

    Returns:
        Memory settings with fact counts
    """
    try:
        async with get_db_session() as db:
            # Get user
            result = await db.execute(
                select(User).where(User.user_id == user_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                raise HTTPException(status_code=404, detail=f"User {user_id} not found")

            # Count facts with separate queries
            total_result = await db.execute(
                select(func.count(UserFact.id)).where(UserFact.user_id == user.id)
            )
            total_facts = total_result.scalar() or 0

            global_result = await db.execute(
                select(func.count(UserFact.id)).where(
                    and_(UserFact.user_id == user.id, UserFact.agent_id.is_(None))
                )
            )
            global_facts = global_result.scalar() or 0

            agent_specific_result = await db.execute(
                select(func.count(UserFact.id)).where(
                    and_(UserFact.user_id == user.id, UserFact.agent_id.isnot(None))
                )
            )
            agent_specific_facts = agent_specific_result.scalar() or 0

            logger.info(f"⚙️ Retrieved memory settings for user {user_id}: {total_facts} facts")

            return MemorySettingsResponse(
                user_id=user.user_id,
                display_name=user.display_name,
                embedding_provider=user.embedding_provider,
                memory_extraction_enabled=user.memory_extraction_enabled,
                allow_agent_specific_memory=user.allow_agent_specific_memory,
                last_login_at=user.last_login_at,
                created_at=user.created_at,
                updated_at=user.updated_at,
                total_facts=total_facts,
                global_facts=global_facts,
                agent_specific_facts=agent_specific_facts
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get memory settings for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get settings: {str(e)}")


@router.put("/users/{user_id}/settings", response_model=MemorySettingsResponse)
async def update_memory_settings(user_id: str, request: MemorySettingsUpdateRequest):
    """
    Update memory settings for a user.

    Args:
        user_id: User identifier
        request: Settings update request

    Returns:
        Updated memory settings
    """
    try:
        async with get_db_session() as db:
            # Get user
            result = await db.execute(
                select(User).where(User.user_id == user_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                # Create user if doesn't exist
                user = User(
                    user_id=user_id,
                    display_name=request.display_name,
                    memory_extraction_enabled=request.memory_extraction_enabled if request.memory_extraction_enabled is not None else True
                )
                db.add(user)
                await db.flush()
                logger.info(f"✨ Created new user: {user_id}")
            else:
                # Update existing user
                if request.display_name is not None:
                    user.display_name = request.display_name
                if request.memory_extraction_enabled is not None:
                    user.memory_extraction_enabled = request.memory_extraction_enabled

                # Handle allow_agent_specific_memory toggle
                if request.allow_agent_specific_memory is not None:
                    # If toggling from True to False, delete all agent-specific facts
                    if user.allow_agent_specific_memory and not request.allow_agent_specific_memory:
                        logger.info(f"🗑️ Deleting agent-specific facts for user {user_id} (toggle OFF)")

                        # Get all agent-specific facts before deletion (for Mem0 cleanup)
                        facts_result = await db.execute(
                            select(UserFact).where(
                                and_(UserFact.user_id == user.id, UserFact.agent_id.isnot(None))
                            )
                        )
                        agent_specific_facts_to_delete = facts_result.scalars().all()

                        # Delete from Mem0 vector store (with transaction safety)
                        if not server.memory_service:
                            raise HTTPException(status_code=500, detail="Memory service not initialized")

                        loop = asyncio.get_event_loop()
                        failed_deletions = []

                        for fact in agent_specific_facts_to_delete:
                            if fact.vector_id:
                                try:
                                    # Use proper async executor pattern
                                    await loop.run_in_executor(
                                        server.memory_service.executor,
                                        lambda vid=fact.vector_id: server.memory_service.memory.delete(memory_id=vid)
                                    )
                                    logger.debug(f"🗑️ Deleted vector {fact.vector_id} from Mem0")
                                except Exception as e:
                                    logger.error(f"❌ Failed to delete vector {fact.vector_id} from Mem0: {e}")
                                    failed_deletions.append((fact.vector_id, str(e)))

                        # Abort if any vector deletions failed (transaction safety)
                        if failed_deletions:
                            error_details = "; ".join([f"{vid}: {err}" for vid, err in failed_deletions])
                            raise HTTPException(
                                status_code=500,
                                detail=f"Failed to delete {len(failed_deletions)} vectors from Mem0, aborting operation to prevent data inconsistency. Errors: {error_details}"
                            )

                        # Only delete from database if ALL vectors were successfully deleted
                        delete_result = await db.execute(
                            sql_delete(UserFact).where(
                                and_(UserFact.user_id == user.id, UserFact.agent_id.isnot(None))
                            )
                        )
                        deleted_count = delete_result.rowcount
                        logger.info(f"✅ Deleted {deleted_count} agent-specific facts for user {user_id}")

                    user.allow_agent_specific_memory = request.allow_agent_specific_memory

                user.updated_at = datetime.utcnow()

            await db.commit()
            await db.refresh(user)

            # Count facts with separate queries
            total_result = await db.execute(
                select(func.count(UserFact.id)).where(UserFact.user_id == user.id)
            )
            total_facts = total_result.scalar() or 0

            global_result = await db.execute(
                select(func.count(UserFact.id)).where(
                    and_(UserFact.user_id == user.id, UserFact.agent_id.is_(None))
                )
            )
            global_facts = global_result.scalar() or 0

            agent_specific_result = await db.execute(
                select(func.count(UserFact.id)).where(
                    and_(UserFact.user_id == user.id, UserFact.agent_id.isnot(None))
                )
            )
            agent_specific_facts = agent_specific_result.scalar() or 0

            logger.info(f"✅ Updated memory settings for user {user_id}")

            return MemorySettingsResponse(
                user_id=user.user_id,
                display_name=user.display_name,
                embedding_provider=user.embedding_provider,
                memory_extraction_enabled=user.memory_extraction_enabled,
                allow_agent_specific_memory=user.allow_agent_specific_memory,
                last_login_at=user.last_login_at,
                created_at=user.created_at,
                updated_at=user.updated_at,
                total_facts=total_facts,
                global_facts=global_facts,
                agent_specific_facts=agent_specific_facts
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to update memory settings for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update settings: {str(e)}")


# === GDPR Compliance ===

@router.get("/users/{user_id}/export", response_model=GDPRExportResponse)
async def export_user_data(user_id: str):
    """
    Export all user data (GDPR compliance).

    Returns a complete dump of all facts and metadata for a user.

    Args:
        user_id: User identifier

    Returns:
        Complete user data export
    """
    try:
        async with get_db_session() as db:
            # Get user
            result = await db.execute(
                select(User).where(User.user_id == user_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                raise HTTPException(status_code=404, detail=f"User {user_id} not found")

            # Get all facts for this user
            facts_result = await db.execute(
                select(UserFact).where(UserFact.user_id == user.id)
            )
            facts = facts_result.scalars().all()

            # Convert facts to response models
            fact_responses = []
            for fact in facts:
                is_valid = fact.validity_end is None or fact.validity_end > datetime.utcnow()
                fact_responses.append(
                    FactResponse(
                        id=fact.id,
                        user_id=fact.user_id,
                        agent_id=fact.agent_id,
                        fact_key=fact.fact_key,
                        fact_value=fact.fact_value,
                        fact_text=fact.fact_text,
                        importance=fact.importance,
                        vector_id=fact.vector_id,
                        embedding_provider=fact.embedding_provider,
                        embedding_model=fact.embedding_model,
                        validity_start=fact.validity_start,
                        validity_end=fact.validity_end,
                        created_at=fact.created_at,
                        updated_at=fact.updated_at,
                        is_valid=is_valid
                    )
                )

            logger.info(f"📦 Exported data for user {user_id}: {len(fact_responses)} facts")

            return GDPRExportResponse(
                user_id=user.user_id,
                display_name=user.display_name,
                exported_at=datetime.utcnow().isoformat(),
                total_facts=len(fact_responses),
                facts=fact_responses
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to export data for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export data: {str(e)}")


@router.delete("/users/{user_id}")
async def delete_user_data(user_id: str):
    """
    Delete all user data (GDPR right to erasure).

    WARNING: This is a destructive operation that cannot be undone.
    Deletes:
    - User record
    - All user facts (cascades)
    - Extraction queue tasks (cascades)
    - Vector embeddings (TODO: implement Mem0 cleanup)

    Args:
        user_id: User identifier

    Returns:
        Deletion summary
    """
    try:
        async with get_db_session() as db:
            # Get user
            result = await db.execute(
                select(User).where(User.user_id == user_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                raise HTTPException(status_code=404, detail=f"User {user_id} not found")

            # Count facts with separate async query
            facts_result = await db.execute(
                select(func.count(UserFact.id)).where(UserFact.user_id == user.id)
            )
            facts_count = facts_result.scalar() or 0

            # Delete user (cascades to facts and extraction tasks)
            await db.delete(user)
            await db.commit()

            logger.info(f"🗑️ Deleted user {user_id} and {facts_count} facts (GDPR erasure)")

            # TODO: Delete Mem0 vector embeddings
            # This requires calling Mem0's delete API with vector_ids

            return {
                "status": "deleted",
                "user_id": user_id,
                "facts_deleted": facts_count,
                "note": "Vector embeddings cleanup pending (TODO: implement Mem0 cleanup)"
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to delete user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")
