"""
Memory service wrapping Mem0 for fact extraction, retrieval, and management.
Implements queue-based extraction with retry logic and metrics tracking.
"""
import asyncio
import os
import json
from typing import List, Dict, Optional
from uuid import UUID
from datetime import datetime, timedelta
from mem0 import Memory
from sqlalchemy import select, and_, func
from src.database.models import User, UserFact, ExtractionTask, Agent, SystemSettings, UserAgentMemorySetting
from src.database.session import get_db_session
from src.services.llm_service import LLMService, LLMConfig, ProviderType
from src.services.mem0_compat import Mem0ResponseNormalizer
from src.config.logging_config import get_logger

# Configure logging
logger = get_logger(__name__)


async def get_global_embedding_config() -> Optional[dict]:
    """
    Fetch global embedding config from database.

    Returns:
        dict: Embedding config from database or None if not set

    Example:
        {
            "provider": "local",
            "model": "sentence-transformers/all-mpnet-base-v2",
            "dims": 768
        }
    """
    try:
        async with get_db_session() as db:
            result = await db.execute(
                select(SystemSettings).where(SystemSettings.setting_key == "embedding_config")
            )
            setting = result.scalar_one_or_none()

            if setting:
                logger.debug(f"📊 Retrieved global embedding config from database: {setting.setting_value}")
                return setting.setting_value  # JSONB field already returns dict
            else:
                logger.debug("🌍 No global embedding config in database, will use environment variables")
                return None
    except Exception as e:
        logger.error(f"❌ Failed to fetch global embedding config from database: {e}")
        return None  # Fall back to environment variables


async def get_admin_memory_policy() -> bool:
    """
    Fetch admin memory policy from database with fallback to environment variable.

    TWO-TIER HIERARCHY for agent-specific memory (updated Phase 2):
    1. Admin Global Policy (this function) - Hard constraint
    2. Per-Agent User Preference (UserAgentMemorySetting) - Falls back to Agent.memory_scope

    Returns:
        bool: True if agent-specific memories are allowed globally, False if forced to global

    Priority:
        1. Database (system_settings.admin_memory_policy)
        2. Environment variable (ADMIN_ALLOW_AGENT_SPECIFIC_MEMORY)
        3. Hardcoded default (True - maintains current behavior)
    """
    try:
        async with get_db_session() as db:
            result = await db.execute(
                select(SystemSettings).where(SystemSettings.setting_key == "admin_memory_policy")
            )
            setting = result.scalar_one_or_none()

            if setting:
                policy = setting.setting_value.get("allow_agent_specific_memory_globally", True)
                logger.debug(f"📊 Retrieved admin memory policy from database: {policy}")
                return policy
            else:
                # Fall back to environment variable
                env_policy = os.getenv("ADMIN_ALLOW_AGENT_SPECIFIC_MEMORY", "true").lower() == "true"
                logger.debug(f"🌍 Using admin memory policy from environment/default: {env_policy}")
                return env_policy
    except Exception as e:
        logger.error(f"❌ Failed to fetch admin memory policy from database: {e}")
        # Fall back to safe default (allow agent-specific memory)
        return True


async def resolve_memory_scope(
    user_id: str,
    agent_id: UUID,
    agent: Agent,
    user: Optional[User] = None
) -> tuple[str, Optional[UUID]]:
    """
    Resolve final memory scope using two-tier hierarchy (Phase 2: Per-Agent Memory Preferences).

    TWO-TIER HIERARCHY:
    1. Admin Global Policy - Hard constraint that cannot be overridden
    2. Per-Agent User Preference - User can configure memory scope per agent
       - Falls back to Agent.memory_scope if no preference set
       - BACKWARDS COMPAT: Falls back to User.allow_agent_specific_memory (deprecated)

    Args:
        user_id: User identifier (e.g., "discord:123456789")
        agent_id: Agent UUID
        agent: Agent model instance
        user: Optional User model instance (for backwards compat check)

    Returns:
        tuple[scope, fact_agent_id]:
            - ('global', None) for global scope
            - ('agent', agent_id) for agent-specific scope

    Examples:
        >>> scope, fact_agent_id = await resolve_memory_scope("user:123", agent_id, agent)
        >>> mem_user_id = f"{user_id}:{agent_id}" if scope == 'agent' else user_id
    """
    # Tier 1: Admin Global Policy (hard constraint)
    admin_allows = await get_admin_memory_policy()
    if not admin_allows:
        logger.info("🔒 Admin policy: agent-specific memory disabled globally, forcing facts to global")
        return ('global', None)

    # Tier 2: Per-Agent User Preference
    async with get_db_session() as db:
        # Check for explicit user preference
        result = await db.execute(
            select(UserAgentMemorySetting).where(
                UserAgentMemorySetting.user_id == user_id,
                UserAgentMemorySetting.agent_id == agent_id
            )
        )
        user_pref = result.scalar_one_or_none()

        if user_pref is not None:
            # User has explicitly set preference for this agent
            if user_pref.allow_agent_specific_memory:
                logger.info(f"🎯 User {user_id} preference: agent-specific memory for agent {agent_id}")
                return ('agent', agent_id)
            else:
                logger.info(f"🌍 User {user_id} preference: global memory for agent {agent_id}")
                return ('global', None)

        # BACKWARDS COMPATIBILITY: Check global toggle (deprecated)
        # TODO: Remove after migration period (migration 024)
        if user and not user.allow_agent_specific_memory:
            logger.warning(
                f"⚠️ DEPRECATED: User {user_id} using global toggle (User.allow_agent_specific_memory=False). "
                f"Migrate to per-agent preferences via user_agent_memory_settings table."
            )
            return ('global', None)

        # Fall back to agent default
        if agent.memory_scope == "agent":
            logger.info(f"🎯 Agent {agent_id} default: agent-specific memory")
            return ('agent', agent_id)
        else:
            logger.info(f"🌍 Agent {agent_id} default: global memory")
            return ('global', None)


async def get_embedding_model_status(model_name: str) -> dict:
    """
    Check if a HuggingFace embedding model is cached locally.

    Args:
        model_name: Model name (e.g., "sentence-transformers/all-mpnet-base-v2")

    Returns:
        dict with cache status:
        {
            "is_cached": bool,
            "cache_size_mb": float,
            "cache_location": str,
            "last_modified": str,
            "files_count": int
        }
    """
    try:
        from huggingface_hub import scan_cache_dir
        from pathlib import Path

        # Scan HuggingFace cache directory
        cache_info = scan_cache_dir()

        # Find the model in cache
        for repo in cache_info.repos:
            if repo.repo_id == model_name:
                # Model is cached
                size_mb = round(repo.size_on_disk / (1024 * 1024), 2)

                # Get last modified time from most recent revision
                last_modified = None
                if repo.revisions:
                    # Get the most recent revision's last modified time
                    latest_revision = max(repo.revisions, key=lambda r: r.last_modified)
                    last_modified = latest_revision.last_modified.isoformat()

                # Count files in cache
                files_count = sum(len(rev.files) for rev in repo.revisions)

                logger.debug(f"📦 Model {model_name} found in cache: {size_mb} MB, {files_count} files")

                return {
                    "is_cached": True,
                    "cache_size_mb": size_mb,
                    "cache_location": str(repo.repo_path),
                    "last_modified": last_modified,
                    "files_count": files_count
                }

        # Model not found in cache
        logger.debug(f"📦 Model {model_name} not found in cache")
        return {
            "is_cached": False,
            "cache_size_mb": 0,
            "cache_location": None,
            "last_modified": None,
            "files_count": 0
        }

    except Exception as e:
        logger.error(f"❌ Failed to check embedding model cache status: {e}")
        return {
            "is_cached": False,
            "error": str(e)
        }


class MemoryService:
    """
    Memory service for VoxBridge conversational memory system.

    Architecture:
    - Wraps Mem0 for fact extraction/retrieval
    - Queue-based extraction (doesn't block voice responses)
    - Error handling with retry logic
    - Metrics tracking for monitoring
    """

    def __init__(self, db_embedding_config: Optional[dict] = None, ws_manager=None):
        """
        Initialize memory service with Mem0.

        Priority for embedding configuration:
        1. Database config (db_embedding_config parameter) - highest priority
        2. Environment variables (EMBEDDING_PROVIDER, AZURE_EMBEDDING_API_KEY)
        3. Hardcoded defaults (local embeddings)

        Args:
            db_embedding_config: Optional database embedding config dict
                {
                    "provider": "azure" | "local",
                    "azure_api_key": "...",
                    "azure_endpoint": "...",
                    "azure_deployment": "...",
                    "model": "sentence-transformers/all-mpnet-base-v2",
                    "dims": 768
                }
            ws_manager: Optional WebSocketManager for broadcasting extraction status events
        """
        self.llm_service = LLMService()
        self.ws_manager = ws_manager

        # Initialize ThreadPoolExecutor for blocking Mem0 calls
        from concurrent.futures import ThreadPoolExecutor
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mem0_extraction")

        # Initialize Mem0 response normalizer for API compatibility
        self.mem0_normalizer = Mem0ResponseNormalizer()

        # Build embedder config with 3-tier prioritization
        if db_embedding_config:
            # Priority 1: Database config (highest)
            embedder_config = self._build_embedder_config_from_db(db_embedding_config)
            provider_name = db_embedding_config.get('provider', 'local')
            # Store original config for fact metadata
            self.embedding_config = {
                "provider": provider_name,
                "model": db_embedding_config.get('model', 'sentence-transformers/all-mpnet-base-v2'),
                "dimensions": db_embedding_config.get('dims', 768)
            }
            logger.info(f"📊 Using database embedding config: {provider_name}")
            logger.info(f"📊 Embedder config for Mem0: {embedder_config}")
        else:
            # Priority 2: Environment variables
            embedder_config = self._build_embedder_config_from_env()
            provider_name = os.getenv("EMBEDDING_PROVIDER", "local")
            # Store original config for fact metadata
            self.embedding_config = {
                "provider": provider_name,
                "model": os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2"),
                "dimensions": int(os.getenv("EMBEDDING_DIMENSIONS", "768"))
            }
            logger.info(f"🌍 Using environment embedding config: {provider_name}")
            logger.info(f"🌍 Embedder config for Mem0: {embedder_config}")

        # Mem0 configuration
        # Note: Ollama native API doesn't use /v1 suffix (only OpenAI-compatible API does)
        ollama_base_url = os.getenv("LOCAL_LLM_BASE_URL", "http://ollama:11434").rstrip("/v1")

        # Memory extraction model - configurable, defaults to gpt-oss:20b for better fact extraction
        memory_model = os.getenv("MEMORY_EXTRACTION_MODEL", "gpt-oss:20b")
        logger.info(f"🧠 Memory extraction model: {memory_model}")

        config = {
            "vector_store": {
                "provider": "pgvector",
                "config": {
                    "dbname": os.getenv("POSTGRES_DB", "voxbridge"),
                    "user": os.getenv("POSTGRES_USER", "voxbridge"),
                    "password": os.getenv("POSTGRES_PASSWORD", "voxbridge_dev_password"),
                    "host": "postgres",
                    "port": 5432,
                    "collection_name": "user_memories"
                }
            },
            "llm": {
                "provider": "ollama",
                "config": {
                    "model": memory_model,
                    "ollama_base_url": ollama_base_url
                }
            },
            "embedder": embedder_config
        }

        self.memory = Memory.from_config(config)
        logger.info(f"✅ MemoryService initialized with {provider_name} embeddings")

    async def queue_extraction(
        self,
        user_id: str,
        agent_id: UUID,
        user_message: str,
        ai_response: str
    ) -> UUID:
        """
        Queue a fact extraction task (non-blocking).

        Returns:
            task_id: UUID of the queued task
        """
        async with get_db_session() as db:
            # Create extraction task in queue
            task = ExtractionTask(
                user_id=user_id,
                agent_id=agent_id,
                user_message=user_message,
                ai_response=ai_response,
                status="pending",
                attempts=0
            )

            db.add(task)
            await db.commit()
            await db.refresh(task)

            logger.info(f"📋 Queued extraction task {task.id} for user {user_id}")
            return task.id

    async def process_extraction_queue(self):
        """
        Background worker to process extraction queue.
        Call this in a separate asyncio task.
        """
        while True:
            try:
                async with get_db_session() as db:
                    # Get pending tasks
                    result = await db.execute(
                        select(ExtractionTask)
                        .where(and_(
                            ExtractionTask.status == "pending",
                            ExtractionTask.attempts < 3
                        ))
                        .order_by(ExtractionTask.created_at)
                        .limit(10)
                    )
                    tasks = result.scalars().all()

                    for task in tasks:
                        try:
                            # Mark as processing
                            task.status = "processing"
                            task.attempts += 1
                            await db.commit()

                            # Broadcast processing event
                            if self.ws_manager:
                                try:
                                    await self.ws_manager.broadcast({
                                        "event": "memory_extraction_processing",
                                        "data": {
                                            "task_id": str(task.id),
                                            "user_id": task.user_id,
                                            "agent_id": str(task.agent_id),
                                            "status": "processing",
                                            "attempts": task.attempts
                                        }
                                    })
                                except Exception as ws_error:
                                    logger.warning(f"⚠️ Failed to broadcast processing event: {ws_error}")

                            # Check if this is a manual fact creation (skip extraction pipeline)
                            if task.user_message.startswith("MANUAL_FACT_CREATION:"):
                                # Parse manual fact data from task
                                import json
                                json_data = task.user_message.replace("MANUAL_FACT_CREATION:", "")
                                manual_data = json.loads(json_data)

                                logger.info(f"📝 Processing manual fact creation: {manual_data['fact_key']} = {manual_data['fact_value']} (scope={manual_data.get('scope', 'agent')})")

                                # Create fact directly (bypassing Mem0 relevance filter)
                                await self._create_manual_fact(
                                    task.user_id,
                                    str(task.agent_id),              # Agent UUID for embedding config
                                    manual_data.get('scope', 'agent'),  # 'global' or 'agent' from frontend
                                    manual_data['fact_key'],
                                    manual_data['fact_value'],
                                    task.ai_response,  # fact_text
                                    manual_data.get('importance', 0.8)
                                )
                            else:
                                # Extract facts from conversation (this will create its own db session)
                                await self._extract_facts_from_turn(
                                    task.user_id,
                                    task.agent_id,
                                    task.user_message,
                                    task.ai_response
                                )

                            # Count facts created for this task
                            # Query UserFact table for facts created in this extraction
                            facts_result = await db.execute(
                                select(UserFact).where(
                                    and_(
                                        UserFact.user_id == (await db.execute(select(User.id).where(User.user_id == task.user_id))).scalar_one_or_none(),
                                        UserFact.created_at >= task.created_at
                                    )
                                ).order_by(UserFact.created_at.desc())
                            )
                            recent_facts = facts_result.scalars().all()
                            facts_count = len(recent_facts)
                            fact_ids = [str(f.id) for f in recent_facts[:5]]  # Limit to 5 most recent

                            # Mark as completed
                            task.status = "completed"
                            task.completed_at = func.now()
                            await db.commit()

                            logger.info(f"✅ Completed extraction task {task.id} ({facts_count} facts)")

                            # Broadcast completed event
                            if self.ws_manager:
                                try:
                                    await self.ws_manager.broadcast({
                                        "event": "memory_extraction_completed",
                                        "data": {
                                            "task_id": str(task.id),
                                            "user_id": task.user_id,
                                            "agent_id": str(task.agent_id),
                                            "status": "completed",
                                            "facts_count": facts_count,
                                            "fact_ids": fact_ids
                                        }
                                    })
                                except Exception as ws_error:
                                    logger.warning(f"⚠️ Failed to broadcast completed event: {ws_error}")

                        except Exception as e:
                            logger.error(f"❌ Extraction task {task.id} failed (attempt {task.attempts}): {e}")
                            task.status = "failed" if task.attempts >= 3 else "pending"
                            task.error = str(e)
                            await db.commit()

                            # Broadcast failed event
                            if self.ws_manager:
                                try:
                                    await self.ws_manager.broadcast({
                                        "event": "memory_extraction_failed",
                                        "data": {
                                            "task_id": str(task.id),
                                            "user_id": task.user_id,
                                            "agent_id": str(task.agent_id),
                                            "status": "retrying" if task.attempts < 3 else "failed",
                                            "attempts": task.attempts,
                                            "error": str(e)
                                        }
                                    })
                                except Exception as ws_error:
                                    logger.warning(f"⚠️ Failed to broadcast failed event: {ws_error}")

                # Sleep before next batch
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"❌ Queue processor error: {e}")
                await asyncio.sleep(10)

    async def _create_manual_fact(
        self,
        user_id: str,
        agent_id: str,
        scope: str,
        fact_key: str,
        fact_value: str,
        fact_text: str,
        importance: float
    ):
        """
        Create a fact directly without Mem0's relevance filter.
        Used for manual fact creation from the UI.

        Args:
            user_id: User identifier
            agent_id: Agent UUID (used for embedding configuration)
            scope: 'global' (agent_id=NULL in DB, shared across agents) or 'agent' (agent_id=UUID, agent-specific)
            fact_key: Fact key (e.g., 'name', 'location')
            fact_value: Fact value (e.g., 'Alice', 'San Francisco')
            fact_text: Natural language representation
            importance: Importance score (0.0-1.0)
        """
        try:
            logger.info(f"📝 [Step 1] Starting manual fact creation for '{fact_key}'...")
            async with get_db_session() as db:
                # Get or create user
                logger.info(f"📝 [Step 2] Getting user '{user_id}'...")
                result = await db.execute(
                    select(User).where(User.user_id == user_id)
                )
                user = result.scalar_one_or_none()
                if not user:
                    logger.info(f"📝 [Step 2a] User not found, creating new user...")
                    user = User(user_id=user_id, memory_extraction_enabled=True)
                    db.add(user)
                    await db.flush()
                logger.info(f"✅ [Step 2] User obtained: {user.id}")

                # Get agent for embedding configuration (always required)
                logger.info(f"📝 [Step 3] Getting agent '{agent_id}' for embedding config...")
                agent_result = await db.execute(
                    select(Agent).where(Agent.id == UUID(agent_id))
                )
                agent = agent_result.scalar_one_or_none()
                if not agent:
                    raise ValueError(f"Agent {agent_id} not found")
                logger.info(f"✅ [Step 3] Agent obtained: {agent.name}")

                # THREE-TIER HIERARCHY: Enforce memory scope policy
                # Tier 1: Check admin global policy (highest priority)
                admin_allows_agent_memory = await get_admin_memory_policy()
                if scope == 'agent' and not admin_allows_agent_memory:
                    logger.warning("⚠️ Admin policy: agent-specific memory disabled globally, forcing to global")
                    scope = 'global'

                # Tier 2: Check user restriction (can further restrict what admin allows)
                elif scope == 'agent' and not user.allow_agent_specific_memory:
                    logger.warning(f"⚠️ User {user_id} has disabled agent-specific memory, forcing to global")
                    scope = 'global'

                # Tier 3: Agent default is already reflected in the scope parameter
                # (no additional check needed here - agent.memory_scope not used in manual creation)

                # Determine memory scope based on final enforced scope
                # - scope='global': shared across all agents (agent_id=NULL, vector=user_id)
                # - scope='agent': agent-specific (agent_id=UUID, vector=user_id:agent_id)
                if scope == 'global':
                    mem_user_id = user_id  # Global vector
                    fact_agent_id_for_db = None  # NULL in database
                    logger.info(f"📝 [Step 4] Memory scope: GLOBAL (vector={mem_user_id}, db_agent_id=NULL)")
                else:  # scope == 'agent'
                    mem_user_id = f"{user_id}:{agent_id}"  # Agent-specific vector
                    fact_agent_id_for_db = UUID(agent_id)  # UUID in database
                    logger.info(f"📝 [Step 4] Memory scope: AGENT-SPECIFIC (vector={mem_user_id}, db_agent_id={agent_id})")

                # Create vector embedding using Mem0 (bypassing relevance filter)
                logger.info(f"📝 [Step 5] Creating vector embedding via Mem0 for text: '{fact_text[:50]}...'")
                logger.info(f"📝 [Step 5a] Using embedding config: {self.embedding_config}")
                logger.info(f"📝 [Step 5b] Calling memory.add() with infer=False to force creation (no relevance filter)")
                loop = asyncio.get_event_loop()
                mem0_result = await loop.run_in_executor(
                    self.executor,
                    lambda: self.memory.add(
                        messages=[{"role": "user", "content": fact_text}],
                        user_id=mem_user_id,
                        infer=False  # CRITICAL: Disable relevance filter for manual facts
                    )
                )
                logger.info(f"📝 [Step 5c] Mem0 result received: {mem0_result}")

                # Normalize Mem0 response using compatibility layer
                normalized = self.mem0_normalizer.normalize_add_response(mem0_result)
                if not normalized:
                    raise ValueError("Mem0 failed to create vector embedding")

                vector_id = normalized[0]["id"]
                logger.info(f"✅ [Step 5] Created vector embedding: {vector_id}")

                # Create fact in database
                logger.info(f"📝 [Step 6] Creating UserFact database record...")
                logger.info(f"📝 [Step 6a] agent_id for fact: {fact_agent_id_for_db} (scope={scope}, user-selected)")

                fact = UserFact(
                    user_id=user.id,
                    agent_id=fact_agent_id_for_db,
                    fact_key=fact_key,
                    fact_value=fact_value,
                    fact_text=fact_text,
                    vector_id=vector_id,
                    importance=importance,
                    embedding_provider=self.embedding_config["provider"],
                    embedding_model=self.embedding_config["model"],
                    validity_start=func.now()
                )

                try:
                    logger.info(f"📝 [Step 7] Committing fact to database...")
                    db.add(fact)
                    await db.commit()
                    await db.refresh(fact)

                    logger.info(f"✅ Created manual fact: {fact_key} = {fact_value} (fact_id={fact.id}, vector_id={vector_id})")

                except Exception as db_error:
                    # COMPENSATING TRANSACTION: Database commit failed after Mem0 vector created
                    # Delete the orphaned vector to maintain consistency
                    logger.error(f"❌ Database commit failed after vector creation: {db_error}")
                    logger.warning(f"🔄 COMPENSATING TRANSACTION: Deleting orphaned vector {vector_id}")

                    try:
                        # Delete the vector from Mem0
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(
                            self.executor,
                            lambda: self.memory.delete(memory_id=vector_id)
                        )
                        logger.info(f"✅ Compensating transaction successful: Deleted orphaned vector {vector_id}")
                    except Exception as compensation_error:
                        logger.error(f"❌ COMPENSATION FAILED: Could not delete orphaned vector {vector_id}: {compensation_error}")
                        logger.error(f"⚠️ Orphaned vector {vector_id} will remain without fact")

                        # Broadcast compensation failure to frontend
                        if self.ws_manager:
                            try:
                                await self.ws_manager.broadcast({
                                    "type": "memory_error",
                                    "message": "Failed to create memory due to database error. Please try again.",
                                    "details": {
                                        "vector_id": vector_id,
                                        "error": str(db_error),
                                        "compensation_failed": True
                                    }
                                })
                            except Exception as ws_error:
                                logger.error(f"❌ WebSocket broadcast failed: {ws_error}")

                    # Re-raise original database error
                    raise db_error

        except Exception as e:
            import traceback
            logger.error(f"❌ Failed to create manual fact: {e}")
            logger.error(f"📋 Exception type: {type(e).__name__}")
            logger.error(f"📋 Full traceback:\n{traceback.format_exc()}")
            raise

    async def _extract_facts_from_turn(
        self,
        user_id: str,
        agent_id: UUID,
        user_message: str,
        ai_response: str
    ):
        """Extract and store facts from a conversation turn using Mem0."""
        # Check relevance filter first
        if not await self._should_extract_facts(user_message, ai_response):
            logger.debug(f"⏭️ Skipping extraction for user {user_id} (not relevant)")
            return

        async with get_db_session() as db:
            # Get or create user
            user = await self._get_or_create_user(user_id, db)

            # Get agent
            agent = await self._get_agent(agent_id, db)

            # TWO-TIER HIERARCHY: Determine memory scope using resolve_memory_scope()
            scope, fact_agent_id = await resolve_memory_scope(user_id, agent_id, agent, user)
            mem_user_id = f"{user_id}:{agent_id}" if scope == 'agent' else user_id

            logger.info(f"📝 Final memory scope: scope={scope}, mem_user_id={mem_user_id}, fact_agent_id={fact_agent_id}")

            # Call Mem0 to extract facts (wrapped in executor to prevent event loop blocking)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor,
                lambda: self.memory.add(
                    messages=[
                        {"role": "user", "content": user_message},
                        {"role": "assistant", "content": ai_response}
                    ],
                    user_id=mem_user_id
                )
            )

            # Store extracted facts in PostgreSQL for relational queries
            # Normalize Mem0 response using compatibility layer
            normalized = self.mem0_normalizer.normalize_add_response(result)
            for memory in normalized:
                # Mem0's add() doesn't return a meaningful score (always 0.0)
                # Use a sensible default for auto-extracted facts:
                # - 0.7 = medium-high importance (Mem0 already filtered for relevance)
                # - Manual facts use user-specified importance (0.0-1.0)
                raw_score = memory.get("score", 0.0)
                importance = raw_score if raw_score > 0.0 else 0.7

                await self._upsert_fact(
                    user=user,
                    agent_id=fact_agent_id,
                    vector_id=memory["id"],
                    fact_text=memory["text"],
                    importance=importance,
                    embedding_provider=self.embedding_config["provider"],
                    embedding_model=self.embedding_config["model"],
                    db=db
                )

            logger.info(f"📝 Extracted {len(normalized)} facts for user {user_id}")

    async def get_user_memory_context(
        self,
        user_id: str,
        agent_id: UUID,
        query: str,
        limit: int = 5
    ) -> str:
        """
        Retrieve relevant user memories for a query (used for context injection).

        Args:
            user_id: User identifier
            agent_id: Agent identifier
            query: Current user message to find relevant memories for
            limit: Maximum number of memories to retrieve

        Returns:
            Formatted memory context string
        """
        try:
            async with get_db_session() as db:
                # Get user for backwards compat check
                user = await self._get_or_create_user(user_id, db)

                # Get agent to determine memory scope
                agent = await self._get_agent(agent_id, db)

                # TWO-TIER HIERARCHY: Determine memory scope using resolve_memory_scope()
                logger.info(
                    f"🔍 Resolving memory scope: "
                    f"user_id={user_id}, "
                    f"agent_id={str(agent_id)[:8]}, "
                    f"agent_name=\"{agent.name if agent else 'N/A'}\""
                )
                scope, _ = await resolve_memory_scope(user_id, agent_id, agent, user)
                mem_user_id = f"{user_id}:{agent_id}" if scope == 'agent' else user_id
                logger.info(
                    f"✅ Memory scope resolved: "
                    f"scope={scope}, "
                    f"mem_user_id=\"{mem_user_id}\", "
                    f"is_scoped={scope == 'agent'}"
                )

            # Search Mem0 for relevant memories
            query_preview = query[:100] + '...' if len(query) > 100 else query
            logger.info(
                f"🔎 Searching memories: "
                f"query=\"{query_preview}\", "
                f"mem_user_id=\"{mem_user_id}\", "
                f"limit={limit}"
            )
            # Wrap Mem0 search in executor to prevent event loop blocking
            loop = asyncio.get_event_loop()
            raw_memories = await loop.run_in_executor(
                self.executor,
                lambda: self.memory.search(
                    query=query,
                    user_id=mem_user_id,
                    limit=limit
                )
            )

            # Normalize Mem0 search response using compatibility layer
            memories = self.mem0_normalizer.normalize_search_response(raw_memories)

            if not memories or len(memories) == 0:
                logger.info(
                    f"🧠 No memories found: "
                    f"user_id={user_id}, "
                    f"scope={scope}, "
                    f"query=\"{query_preview}\""
                )
                return ""

            # Calculate average score from normalized results
            avg_score = sum(m["score"] for m in memories) / len(memories)

            logger.info(
                f"🧠 Found {len(memories)} relevant memories: "
                f"user_id={user_id}, "
                f"scope={scope}, "
                f"avg_score={avg_score:.3f}"
            )

            # Format memories as context (all normalized to same format)
            context_lines = ["<user_memories>"]
            for idx, mem in enumerate(memories):
                memory_text = mem["text"]
                score = mem["score"]
                logger.debug(
                    f"  [{idx + 1}] score={score:.3f}, "
                    f"text=\"{memory_text[:60]}{'...' if len(memory_text) > 60 else ''}\""
                )
                context_lines.append(f"- {memory_text} (relevance: {score:.2f})")
            context_lines.append("</user_memories>")

            context = "\n".join(context_lines)
            logger.info(f"✅ Memory context formatted: length={len(context)}, memories={len(memories)}")
            return context

        except Exception as e:
            logger.error(f"❌ Failed to retrieve memories for user {user_id}: {e}")
            return ""  # Degrade gracefully

    def _build_embedder_config_from_db(self, db_config: dict) -> dict:
        """
        Build Mem0 embedder config from database settings (Priority 1).

        Args:
            db_config: Database embedding config dict

        Returns:
            Mem0 embedder configuration dict
        """
        provider = db_config.get('provider', 'local')

        if provider == 'azure':
            return {
                "provider": "azure_openai",
                "config": {
                    "model": "text-embedding-3-large",
                    "embedding_dims": 3072,
                    "azure_kwargs": {
                        "api_key": db_config.get('azure_api_key'),  # TODO: Decrypt if encrypted
                        "azure_endpoint": db_config.get('azure_endpoint'),
                        "azure_deployment": db_config.get('azure_deployment', 'text-embedding-3-large'),
                        "api_version": db_config.get('azure_api_version', '2024-12-01-preview'),
                    }
                }
            }
        else:  # local
            return {
                "provider": "huggingface",
                "config": {
                    "model": db_config.get('model', 'sentence-transformers/all-mpnet-base-v2'),
                    "embedding_dims": db_config.get('dims', 768)
                }
            }

    def _build_embedder_config_from_env(self) -> dict:
        """
        Build Mem0 embedder config from environment variables (Priority 2).

        Returns:
            Mem0 embedder configuration dict
        """
        # Check provider selection
        embedding_provider = os.getenv("EMBEDDING_PROVIDER", "local")

        # Check if Azure credentials are configured
        azure_api_key = os.getenv("AZURE_EMBEDDING_API_KEY")
        azure_endpoint = os.getenv("AZURE_EMBEDDING_ENDPOINT")

        # Default to local embeddings if Azure credentials not configured
        if embedding_provider == "azure" and (not azure_api_key or not azure_endpoint):
            logger.warning("⚠️ Azure embeddings selected but credentials not configured, falling back to local embeddings")
            embedding_provider = "local"

        if embedding_provider == "azure":
            return {
                "provider": "azure_openai",
                "config": {
                    "model": "text-embedding-3-large",
                    "embedding_dims": 3072,
                    "azure_kwargs": {
                        "api_version": os.getenv("AZURE_EMBEDDING_API_VERSION", "2024-12-01-preview"),
                        "azure_deployment": os.getenv("AZURE_EMBEDDING_DEPLOYMENT", "text-embedding-3-large"),
                        "azure_endpoint": azure_endpoint,
                        "api_key": azure_api_key
                    }
                }
            }
        else:  # local (Priority 3: hardcoded defaults)
            return {
                "provider": "huggingface",
                "config": {
                    "model": os.getenv("LOCAL_EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2"),
                    "embedding_dims": int(os.getenv("LOCAL_EMBEDDING_DIMS", "768"))
                }
            }

    async def _should_extract_facts(self, user_message: str, ai_response: str) -> bool:
        """LLM-based relevance filter to reduce noise."""
        relevance_prompt = f"""
Determine if this conversation contains factual information about the user that should be remembered.

User: {user_message}
Assistant: {ai_response}

Criteria for extraction:
- User shares personal information (name, location, preferences, relationships)
- User mentions goals, habits, or important life events
- Conversation reveals user context useful for future interactions

Do NOT extract if:
- Just casual greetings or small talk
- Technical questions with no personal context
- User is testing the system

Should we extract and store facts from this conversation?
Answer with only "yes" or "no".
"""

        # Create LLM config for relevance check
        # Use LOCAL provider since OpenRouter may not be configured
        config = LLMConfig(
            provider=ProviderType.LOCAL,
            model=os.getenv("LOCAL_LLM_RELEVANCE_MODEL", "gemma3n:latest"),
            temperature=0.3,
        )

        response = await self.llm_service.generate_response(
            session_id="memory_relevance_check",
            messages=[{"role": "system", "content": relevance_prompt}],
            config=config,
            stream=False
        )

        return response.strip().lower() == "yes"

    async def _get_or_create_user(self, user_id: str, db) -> User:
        """Get user from database or create if doesn't exist."""
        result = await db.execute(
            select(User).where(User.user_id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            user = User(user_id=user_id)
            db.add(user)
            await db.commit()
            await db.refresh(user)
            logger.info(f"👤 Created new user: {user_id}")

        return user

    async def _get_agent(self, agent_id: UUID, db) -> Agent:
        """Get agent by ID."""
        result = await db.execute(
            select(Agent).where(Agent.id == agent_id)
        )
        return result.scalar_one()

    def _infer_fact_category(self, fact_text: str) -> str:
        """
        Infer a semantic category/key from fact text using pattern matching.

        Examples:
            "Favorite color is blue" -> "favorite_color"
            "Hometown is Portland" -> "hometown"
            "Likes hot showers" -> "preference_showers"
            "Wants to travel the world" -> "goal_travel"
            "Works at Google" -> "occupation"
            "Has 2 children" -> "family_children"
        """
        import re
        text_lower = fact_text.lower().strip()

        # Pattern rules: (regex, category_template)
        # Use {1}, {2} for capture group substitution
        patterns = [
            # Favorites: "favorite X is Y" or "X is their favorite"
            (r"favorite\s+(\w+)", "favorite_{1}"),
            (r"(\w+)\s+is\s+(?:their|his|her|my)\s+favorite", "favorite_{1}"),

            # Location/Origin
            (r"(?:hometown|home\s*town)\s+(?:is|was)", "hometown"),
            (r"(?:lives?|living)\s+in", "location_residence"),
            (r"(?:from|born\s+in|grew\s+up\s+in)", "location_origin"),
            (r"(?:moved|relocated)\s+to", "location_moved"),

            # Preferences: "likes/loves/enjoys/prefers X"
            (r"(?:likes?|loves?|enjoys?|prefers?)\s+(\w+)", "preference_{1}"),
            (r"(?:doesn't|does\s+not|hates?|dislikes?)\s+(\w+)", "dislike_{1}"),

            # Goals/Aspirations: "wants to X", "dreams of X"
            (r"(?:wants?\s+to|would\s+like\s+to|dreams?\s+of)\s+(\w+)", "goal_{1}"),
            (r"(?:aspires?\s+to|hopes?\s+to)\s+(\w+)", "aspiration_{1}"),

            # Work/Career
            (r"(?:works?\s+(?:at|for)|employed\s+(?:at|by))", "occupation"),
            (r"(?:job|profession|career|occupation)\s+(?:is|was)", "occupation"),
            (r"(?:is\s+a|works?\s+as)\s+(\w+)", "occupation_{1}"),

            # Family
            (r"(?:has|have)\s+(\d+)\s+(?:kids?|children)", "family_children"),
            (r"(?:married|spouse|wife|husband|partner)", "family_relationship"),
            (r"(?:siblings?|brothers?|sisters?)", "family_siblings"),
            (r"(?:pets?|dog|cat|animal)", "family_pets"),

            # Personal attributes
            (r"(?:age|years?\s+old)\s+(?:is)?", "personal_age"),
            (r"(?:birthday|born\s+on)", "personal_birthday"),
            (r"(?:name\s+is|called|named)", "personal_name"),
            (r"(?:speaks?|fluent\s+in)\s+(\w+)", "language_{1}"),

            # Education
            (r"(?:studied|graduated|degree|major)", "education"),
            (r"(?:school|university|college)", "education_institution"),

            # Hobbies/Interests
            (r"(?:hobby|hobbies)\s+(?:is|are|include)", "hobby"),
            (r"(?:plays?|playing)\s+(\w+)", "hobby_{1}"),
            (r"(?:interested\s+in|passion\s+for)\s+(\w+)", "interest_{1}"),

            # Health/Lifestyle
            (r"(?:allergic|allergy)\s+(?:to)?\s*(\w+)?", "health_allergy"),
            (r"(?:diet|vegan|vegetarian|eating)", "health_diet"),

            # Beliefs/Values
            (r"(?:believes?|values?|thinks?)\s+(?:in|that)?", "belief"),
            (r"(?:religion|religious|faith)", "belief_religion"),
        ]

        for pattern, template in patterns:
            match = re.search(pattern, text_lower)
            if match:
                # Substitute capture groups into template
                result = template
                for i, group in enumerate(match.groups(), 1):
                    if group:
                        result = result.replace(f"{{{i}}}", group)
                # Clean up any unmatched placeholders
                result = re.sub(r"\{\d+\}", "", result)
                result = result.strip("_")
                if result:
                    logger.debug(f"🏷️ Inferred fact category: '{fact_text[:50]}...' -> '{result}'")
                    return result

        # Fallback: use first 2-3 meaningful words
        # Skip common words to get to the semantic content
        skip_words = {"is", "are", "was", "were", "has", "have", "had", "the", "a", "an", "their", "his", "her", "my", "they", "he", "she", "it"}
        words = [w for w in text_lower.split() if w not in skip_words][:3]
        if words:
            fallback_key = "_".join(words)
            logger.debug(f"🏷️ Fallback fact category: '{fact_text[:50]}...' -> '{fallback_key}'")
            return fallback_key

        return "fact"

    async def _upsert_fact(
        self,
        user: User,
        agent_id: UUID | None,
        vector_id: str,
        fact_text: str,
        importance: float,
        embedding_provider: str,
        embedding_model: str,
        db
    ):
        """
        Upsert fact to PostgreSQL (for relational queries and metadata).

        Uses vector_id for matching (unique per fact), not fact_key.
        This prevents overwrites when Mem0 extracts facts without colon format.

        Args:
            agent_id: UUID for agent-specific facts, None for global facts
        """
        # Extract fact key and value from text
        # If text has "key: value" format, use it; otherwise infer category
        if ":" in fact_text:
            fact_key = fact_text.split(":")[0].strip().lower().replace(" ", "_")
            fact_value = fact_text.split(":", 1)[1].strip()
        else:
            # Infer semantic category from fact text
            fact_key = self._infer_fact_category(fact_text)
            fact_value = fact_text

        # Use vector_id for matching - each Mem0 fact has a unique vector_id
        # This prevents overwrites when multiple facts have similar semantic keys
        result = await db.execute(
            select(UserFact).where(UserFact.vector_id == vector_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing fact
            existing.fact_value = fact_value
            existing.fact_text = fact_text
            existing.importance = importance
            existing.vector_id = vector_id
            existing.updated_at = func.now()
        else:
            # Create new fact
            fact = UserFact(
                user_id=user.id,
                agent_id=agent_id,
                fact_key=fact_key,
                fact_value=fact_value,
                fact_text=fact_text,
                importance=importance,
                vector_id=vector_id,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model
            )
            db.add(fact)

        try:
            await db.commit()
        except Exception as db_error:
            # COMPENSATING TRANSACTION: Database commit failed after Mem0 vector created
            # Delete the orphaned vector to maintain consistency
            logger.error(f"❌ Database commit failed in _upsert_fact after vector creation: {db_error}")
            logger.warning(f"🔄 COMPENSATING TRANSACTION: Deleting orphaned vector {vector_id}")

            try:
                # Delete the vector from Mem0
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    self.executor,
                    lambda: self.memory.delete(memory_id=vector_id)
                )
                logger.info(f"✅ Compensating transaction successful: Deleted orphaned vector {vector_id}")
            except Exception as compensation_error:
                logger.error(f"❌ COMPENSATION FAILED: Could not delete orphaned vector {vector_id}: {compensation_error}")
                logger.error(f"⚠️ Orphaned vector {vector_id} will remain without fact")

                # Broadcast compensation failure to frontend
                if self.ws_manager:
                    try:
                        await self.ws_manager.broadcast({
                            "type": "memory_error",
                            "message": "Failed to create memory due to database error. Please try again.",
                            "details": {
                                "vector_id": vector_id,
                                "error": str(db_error),
                                "compensation_failed": True
                            }
                        })
                    except Exception as ws_error:
                        logger.error(f"❌ WebSocket broadcast failed: {ws_error}")

            # Re-raise original database error
            raise db_error
