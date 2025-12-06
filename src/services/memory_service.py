"""
Memory service wrapping Mem0 for fact extraction, retrieval, and management.
Implements queue-based extraction with retry logic and metrics tracking.
"""
import asyncio
import os
import json
import time
from collections import deque
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
from src.utils.encryption import decrypt_api_key

# Configure logging
logger = get_logger(__name__)


class ErrorGuard:
    """
    Phase 6: Error Guards - Circuit breaker for memory operations.

    Temporarily disables memory features if error rates spike to prevent cascade failures.
    Auto-resets after cooldown period to allow recovery.
    """

    def __init__(
        self,
        threshold: int = 5,
        window_seconds: int = 600,
        cooldown_seconds: int = 300
    ):
        """
        Initialize error guard.

        Args:
            threshold: Number of errors within window to trigger guard
            window_seconds: Time window for counting errors (default 10 minutes)
            cooldown_seconds: Time to keep guard active before auto-reset (default 5 minutes)
        """
        self.threshold = threshold
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds

        self.error_timestamps: deque = deque()
        self.guard_active = False
        self.guard_activated_at: float = 0
        self.total_activations = 0

    def record_error(self, error_type: str = "unknown") -> bool:
        """
        Record an error and check if guard should activate.

        Args:
            error_type: Type of error for logging

        Returns:
            True if guard was activated by this error, False otherwise
        """
        now = time.time()
        self.error_timestamps.append(now)

        # Clean old timestamps outside the window
        while self.error_timestamps and self.error_timestamps[0] < now - self.window_seconds:
            self.error_timestamps.popleft()

        # Check if threshold exceeded
        if len(self.error_timestamps) >= self.threshold and not self.guard_active:
            self.guard_active = True
            self.guard_activated_at = now
            self.total_activations += 1
            logger.warning(
                f"🛡️ Error guard ACTIVATED - {len(self.error_timestamps)} errors in "
                f"{self.window_seconds}s (threshold: {self.threshold}). "
                f"Memory features temporarily disabled for {self.cooldown_seconds}s. "
                f"Total activations: {self.total_activations}"
            )
            return True

        return False

    def is_active(self) -> bool:
        """
        Check if error guard is currently active.

        Returns:
            True if guard is active (memory features should be skipped)
        """
        if not self.guard_active:
            return False

        # Auto-deactivate after cooldown
        elapsed = time.time() - self.guard_activated_at
        if elapsed > self.cooldown_seconds:
            self.guard_active = False
            self.error_timestamps.clear()  # Reset error count
            logger.info(
                f"🛡️ Error guard DEACTIVATED after {elapsed:.1f}s cooldown. "
                f"Memory features re-enabled."
            )
            return False

        return True

    def get_status(self) -> dict:
        """Get current error guard status for metrics."""
        now = time.time()
        # Clean old timestamps for accurate count
        while self.error_timestamps and self.error_timestamps[0] < now - self.window_seconds:
            self.error_timestamps.popleft()

        return {
            "active": self.guard_active,
            "errors_in_window": len(self.error_timestamps),
            "threshold": self.threshold,
            "window_seconds": self.window_seconds,
            "cooldown_seconds": self.cooldown_seconds,
            "cooldown_remaining": max(0, self.cooldown_seconds - (now - self.guard_activated_at)) if self.guard_active else 0,
            "total_activations": self.total_activations
        }

    def force_reset(self):
        """Manually reset the error guard (for admin use)."""
        self.guard_active = False
        self.error_timestamps.clear()
        logger.info("🛡️ Error guard manually reset by admin")


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
    agent: Optional[Agent],
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
        agent: Agent model instance (can be None if agent was deleted)
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

        # Fall back to agent default (if agent still exists)
        if agent is None:
            logger.warning(f"⚠️ Agent {agent_id} not found (deleted?), falling back to global scope")
            return ('global', None)

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

        # Per-user locks to prevent concurrent extraction race conditions (Issue 5 fix)
        self._user_extraction_locks: dict[str, asyncio.Lock] = {}

        # Initialize Mem0 response normalizer for API compatibility
        self.mem0_normalizer = Mem0ResponseNormalizer()

        # Pruning configuration
        self.max_memories_per_user = int(os.getenv("MAX_MEMORIES_PER_USER", "1000"))
        self.pruning_strategy = os.getenv("PRUNING_STRATEGY", "fifo")  # fifo, lru, least_relevant
        self.pruning_batch_size = int(os.getenv("PRUNING_BATCH_SIZE", "10"))
        self.pruning_enabled = os.getenv("PRUNING_ENABLED", "true").lower() == "true"
        logger.info(f"✂️ Pruning config: max={self.max_memories_per_user}, strategy={self.pruning_strategy}, batch={self.pruning_batch_size}, enabled={self.pruning_enabled}")

        # LLM Optimization configuration (Phase 5)
        # Retrieval optimization - filter by confidence threshold
        self.vector_similarity_threshold = float(os.getenv("VECTOR_SIMILARITY_THRESHOLD", "0.5"))  # Min score to include
        self.high_confidence_threshold = float(os.getenv("HIGH_CONFIDENCE_THRESHOLD", "0.85"))  # Score for "confident" match

        # Extraction shortcuts - skip full LLM for obvious preferences
        self.enable_extraction_shortcuts = os.getenv("ENABLE_EXTRACTION_SHORTCUTS", "true").lower() == "true"
        self.shortcut_max_length = int(os.getenv("SHORTCUT_MAX_LENGTH", "80"))  # Max message length for shortcut
        self.preference_keywords = ["favorite", "love", "like", "enjoy", "prefer", "hate", "dislike", "allergic", "can't stand"]

        # Optimization metrics (counters)
        self.metrics = {
            "retrieval_total": 0,
            "retrieval_filtered": 0,  # Low-confidence results filtered out
            "extraction_total": 0,
            "extraction_shortcuts": 0,  # Shortcuts used (LLM skipped)
            "extraction_full": 0,  # Full LLM extraction used
            "duplicates_detected": 0,  # Phase 7: Duplicates prevented
            "duplicates_embedding": 0,  # Detected via embedding similarity
            "duplicates_text": 0,  # Detected via text similarity fallback
        }
        logger.info(f"⚡ LLM Optimization config: shortcuts={self.enable_extraction_shortcuts}, shortcut_max_len={self.shortcut_max_length}, similarity_threshold={self.vector_similarity_threshold}")

        # Deduplication configuration (Phase 7)
        self.enable_deduplication = os.getenv("ENABLE_DEDUPLICATION", "true").lower() == "true"
        self.use_embeddings_for_dedup = os.getenv("USE_EMBEDDINGS_FOR_DEDUP", "true").lower() == "true"
        self.embedding_similarity_threshold = float(os.getenv("EMBEDDING_SIMILARITY_THRESHOLD", "0.95"))  # Very high for duplicates
        self.text_similarity_threshold = float(os.getenv("TEXT_SIMILARITY_THRESHOLD", "0.90"))  # Fallback threshold
        logger.info(f"🔍 Deduplication config: enabled={self.enable_deduplication}, embeddings={self.use_embeddings_for_dedup}, embed_threshold={self.embedding_similarity_threshold}, text_threshold={self.text_similarity_threshold}")

        # Summarization configuration (Phase 3)
        self.enable_summarization = os.getenv("ENABLE_SUMMARIZATION", "true").lower() == "true"
        self.summarization_interval_hours = int(os.getenv("SUMMARIZATION_INTERVAL_HOURS", "24"))  # Run daily
        self.summarization_min_age_days = int(os.getenv("SUMMARIZATION_MIN_AGE_DAYS", "7"))  # Only summarize old memories
        self.summarization_min_cluster_size = int(os.getenv("SUMMARIZATION_MIN_CLUSTER_SIZE", "3"))
        self.summarization_max_cluster_size = int(os.getenv("SUMMARIZATION_MAX_CLUSTER_SIZE", "8"))
        self.summarization_similarity_threshold = float(os.getenv("SUMMARIZATION_SIMILARITY_THRESHOLD", "0.75"))  # Cluster similarity
        self.summarization_llm_provider = os.getenv("SUMMARIZATION_LLM_PROVIDER", "openrouter")  # or "local"
        self.summarization_llm_model = os.getenv("SUMMARIZATION_LLM_MODEL", "openai/gpt-4o-mini")
        logger.info(f"📦 Summarization config: enabled={self.enable_summarization}, interval={self.summarization_interval_hours}h, min_age={self.summarization_min_age_days}d, cluster_size={self.summarization_min_cluster_size}-{self.summarization_max_cluster_size}")

        # Summarization metrics
        self.metrics["summaries_created"] = 0
        self.metrics["facts_summarized"] = 0
        self.metrics["clusters_found"] = 0

        # Error Guard configuration (Phase 6)
        self.enable_error_guard = os.getenv("ENABLE_ERROR_GUARD", "true").lower() == "true"
        error_guard_threshold = int(os.getenv("ERROR_GUARD_THRESHOLD", "5"))
        error_guard_window = int(os.getenv("ERROR_GUARD_WINDOW_SECONDS", "600"))  # 10 minutes
        error_guard_cooldown = int(os.getenv("ERROR_GUARD_COOLDOWN_SECONDS", "300"))  # 5 minutes

        self.error_guard = ErrorGuard(
            threshold=error_guard_threshold,
            window_seconds=error_guard_window,
            cooldown_seconds=error_guard_cooldown
        )
        logger.info(f"🛡️ Error guard config: enabled={self.enable_error_guard}, threshold={error_guard_threshold}, window={error_guard_window}s, cooldown={error_guard_cooldown}s")

        # Error guard metrics
        self.metrics["error_guard_skips"] = 0  # Extractions skipped due to active guard

        # Temporal Detection configuration (Phase 8)
        self.enable_temporal_detection = os.getenv("ENABLE_TEMPORAL_DETECTION", "true").lower() == "true"
        self.temporal_llm_fallback = os.getenv("TEMPORAL_LLM_FALLBACK", "true").lower() == "true"
        self.temporal_default_days = int(os.getenv("TEMPORAL_DEFAULT_DAYS", "7"))
        logger.info(f"⏰ Temporal detection config: enabled={self.enable_temporal_detection}, llm_fallback={self.temporal_llm_fallback}, default_days={self.temporal_default_days}")

        # Temporal detection metrics
        self.metrics["temporal_regex_detected"] = 0
        self.metrics["temporal_llm_detected"] = 0
        self.metrics["temporal_permanent"] = 0

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

        # Enhanced extraction prompt for better fact quality (Phase 4)
        # This guides the LLM to extract only user-specific, persistent facts
        # Updated to include memory bank categorization hints
        custom_prompt = """
You are a Personal Information Organizer specialized in extracting user-specific, persistent facts from conversations.

**YOUR TASK:**
Analyze the conversation and extract ONLY facts that are:
1. About the USER specifically (not general knowledge)
2. Persistent (not temporary states like "I'm tired today")
3. Worth remembering for future conversations

**MEMORY CATEGORIES (extract by category):**

PERSONAL - Identity, background, personal preferences:
- Name, age, location, hometown, nationality
- Appearance, physical characteristics
- Favorite color, food, music, movies
- Personal habits, routines

WORK - Professional and career information:
- Job title, occupation, employer, industry
- Work skills, expertise, certifications
- Career goals, professional aspirations
- Work relationships (boss, coworkers)

RELATIONSHIPS - Social connections:
- Family members (spouse, children, parents, siblings)
- Friends, romantic partners
- Pets and their names
- Social dynamics, relationship status

HEALTH - Physical and mental wellbeing:
- Medical conditions, allergies, dietary restrictions
- Medications, treatments
- Exercise habits, fitness goals
- Mental health, therapy, stress management

INTERESTS - Hobbies and entertainment:
- Hobbies, sports, games
- Books, shows, podcasts they enjoy
- Creative pursuits, collections
- Travel preferences, places visited

EVENTS - Significant happenings:
- Upcoming plans (trips, appointments, deadlines)
- Recent experiences, milestones
- Birthdays, anniversaries, celebrations

GENERAL - Other persistent facts:
- Possessions, things they own
- Opinions, beliefs, values
- Miscellaneous preferences

**DO NOT EXTRACT:**
- General knowledge or trivia
- AI commands or meta-requests ("tell me about...", "what is...")
- Temporary states ("I'm tired", "I'm busy today")
- Opinions about external topics (politics, news)
- Anything the assistant said (only extract USER information)

**OUTPUT FORMAT:**
For each fact, output a concise statement in third person:
- "User's name is John"
- "User loves Italian food"
- "User works as a software engineer"
- "User has a dog named Max"
- "User is planning a trip to Japan next month"
- "User is allergic to peanuts"

Only extract facts that are explicitly stated or strongly implied by the user.
If no user-specific facts are found, extract nothing.
"""

        config = {
            "custom_prompt": custom_prompt,
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

    def get_error_guard_status(self) -> dict:
        """
        Get current error guard status for monitoring/metrics.

        Returns:
            dict with error guard state including active status, error counts, and cooldown info
        """
        return {
            "enabled": self.enable_error_guard,
            **self.error_guard.get_status()
        }

    def reset_error_guard(self):
        """Manually reset the error guard (admin operation)."""
        self.error_guard.force_reset()

    def _get_user_lock(self, user_id: str) -> asyncio.Lock:
        """
        Get or create an asyncio.Lock for the given user.

        This prevents concurrent extraction race conditions where two
        extractions for the same user could both create duplicate vectors
        before either checks for duplicates.
        """
        if user_id not in self._user_extraction_locks:
            self._user_extraction_locks[user_id] = asyncio.Lock()
        return self._user_extraction_locks[user_id]

    def __del__(self):
        """Cleanup ThreadPoolExecutor on service destruction."""
        if hasattr(self, 'executor') and self.executor:
            try:
                self.executor.shutdown(wait=True)
                logger.info("🧹 MemoryService executor shutdown complete")
            except Exception as e:
                logger.warning(f"⚠️ Failed to shutdown executor: {e}")

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

                                logger.info(f"📝 Processing manual fact creation: {manual_data['fact_key']} = {manual_data['fact_value']} (scope={manual_data.get('scope', 'agent')}, bank={manual_data.get('memory_bank', 'General')})")

                                # Create fact directly (bypassing Mem0 relevance filter)
                                await self._create_manual_fact(
                                    task.user_id,
                                    str(task.agent_id),              # Agent UUID for embedding config
                                    manual_data.get('scope', 'agent'),  # 'global' or 'agent' from frontend
                                    manual_data['fact_key'],
                                    manual_data['fact_value'],
                                    task.ai_response,  # fact_text
                                    manual_data.get('importance', 0.8),
                                    manual_data.get('memory_bank', 'General')  # Memory bank from frontend
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
                            # Use a FRESH session to see commits from _extract_facts_from_turn's inner session
                            async with get_db_session() as count_db:
                                # Get user ID for the query
                                user_result = await count_db.execute(
                                    select(User.id).where(User.user_id == task.user_id)
                                )
                                user_uuid = user_result.scalar_one_or_none()

                                if user_uuid:
                                    facts_result = await count_db.execute(
                                        select(UserFact).where(
                                            and_(
                                                UserFact.user_id == user_uuid,
                                                UserFact.created_at >= task.created_at
                                            )
                                        ).order_by(UserFact.created_at.desc())
                                    )
                                    recent_facts = facts_result.scalars().all()
                                    facts_count = len(recent_facts)
                                    fact_ids = [str(f.id) for f in recent_facts[:5]]  # Limit to 5 most recent
                                else:
                                    facts_count = 0
                                    fact_ids = []

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

                            # Phase 6: Record error for circuit breaker
                            if self.enable_error_guard:
                                self.error_guard.record_error(error_type=type(e).__name__)

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
        importance: float,
        memory_bank: str = "General"
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
            memory_bank: Memory bank category (Personal, Work, General)
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
                    memory_bank=memory_bank,
                    embedding_provider=self.embedding_config["provider"],
                    embedding_model=self.embedding_config["model"],
                    validity_start=func.now(),
                    is_protected=True  # Manual facts are protected from pruning
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
        # Track extraction metric
        self.metrics["extraction_total"] += 1

        # Phase 6: Check error guard before extraction
        if self.enable_error_guard and self.error_guard.is_active():
            self.metrics["error_guard_skips"] += 1
            logger.debug(f"🛡️ Memory extraction skipped - error guard active (skips: {self.metrics['error_guard_skips']})")
            return

        # Phase 5 Optimization: Check for simple preference shortcut first
        if self._is_simple_preference(user_message):
            success = await self._extract_preference_shortcut(user_id, agent_id, user_message)
            if success:
                logger.info(f"⚡ Used shortcut extraction for user {user_id} (skipped LLM relevance check)")
                return
            # Fall through to full extraction if shortcut failed

        # Check relevance filter (requires LLM call)
        if not await self._should_extract_facts(user_message, ai_response):
            logger.debug(f"⏭️ Skipping extraction for user {user_id} (not relevant)")
            return

        # Track full extraction metric
        self.metrics["extraction_full"] += 1

        # Acquire per-user lock to prevent concurrent extraction race conditions
        # This ensures deduplication checks see all prior extractions
        user_lock = self._get_user_lock(user_id)
        async with user_lock:
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

                # Enforce memory limit before adding new facts (pruning if needed)
                if normalized:
                    pruned = await self._enforce_memory_limit(user, db)
                    if pruned > 0:
                        logger.info(f"✂️ Pre-extraction pruning: {pruned} facts removed to make room")

                saved_count = 0
                skipped_duplicates = 0

                for memory in normalized:
                    fact_text = memory["text"]
                    vector_id = memory["id"]

                    # Phase 7: Check for duplicates before saving
                    is_dupe = await self._is_duplicate(fact_text, user.id, mem_user_id, db)
                    if is_dupe:
                        # Duplicate detected - delete the vector that was just created
                        logger.info(f"🔍 Skipping duplicate fact (deleting vector {vector_id}): \"{fact_text[:50]}...\"")
                        try:
                            loop = asyncio.get_event_loop()
                            await loop.run_in_executor(
                                self.executor,
                                lambda vid=vector_id: self.memory.delete(vid)
                            )
                        except Exception as del_err:
                            logger.warning(f"⚠️ Failed to delete duplicate vector {vector_id}: {del_err}")
                        skipped_duplicates += 1
                        continue

                    # Infer fact_key for categorization (used by importance and bank inference)
                    fact_key = self._infer_fact_category(fact_text)

                    # Infer importance based on fact content
                    # - Uses pattern matching to assign 1.0 (critical), 0.8 (important), 0.6 (medium), 0.7 (default)
                    raw_score = memory.get("score", 0.0)
                    importance = raw_score if raw_score > 0.0 else self._infer_importance(fact_text, fact_key)

                    # Infer memory bank based on fact content
                    memory_bank = self._infer_memory_bank(fact_text, fact_key)

                    # Infer validity period for temporal facts (Phase 8)
                    validity_end = None
                    if self.enable_temporal_detection:
                        validity_end = await self._infer_validity_period(fact_text, memory_bank)

                    await self._upsert_fact(
                        user=user,
                        agent_id=fact_agent_id,
                        vector_id=vector_id,
                        fact_text=fact_text,
                        importance=importance,
                        embedding_provider=self.embedding_config["provider"],
                        embedding_model=self.embedding_config["model"],
                        db=db,
                        memory_bank=memory_bank,
                        validity_end=validity_end
                    )
                    saved_count += 1

                if skipped_duplicates > 0:
                    logger.info(f"🔍 Deduplication: skipped {skipped_duplicates} duplicates, saved {saved_count} facts")
                else:
                    logger.info(f"📝 Extracted {saved_count} facts for user {user_id}")

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

            # Track retrieval metrics
            self.metrics["retrieval_total"] += 1
            original_count = len(memories) if memories else 0

            # Apply confidence threshold filtering (Phase 5 optimization)
            if memories:
                filtered_memories = [m for m in memories if m.get("score", 0) >= self.vector_similarity_threshold]
                filtered_count = original_count - len(filtered_memories)

                if filtered_count > 0:
                    self.metrics["retrieval_filtered"] += filtered_count
                    logger.info(
                        f"⚡ Retrieval optimization: filtered {filtered_count}/{original_count} "
                        f"low-confidence results (threshold={self.vector_similarity_threshold:.2f})"
                    )
                    memories = filtered_memories

                # Log high-confidence matches
                high_conf_count = sum(1 for m in memories if m.get("score", 0) >= self.high_confidence_threshold)
                if high_conf_count > 0:
                    logger.debug(f"⚡ High-confidence matches: {high_conf_count}/{len(memories)} (threshold={self.high_confidence_threshold:.2f})")

            # Update last_accessed_at for LRU tracking
            if memories:
                vector_ids = [m["id"] for m in memories if m.get("id")]
                if vector_ids:
                    async with get_db_session() as update_db:
                        # Find facts by vector_id and update last_accessed_at
                        from sqlalchemy import update
                        await update_db.execute(
                            update(UserFact)
                            .where(UserFact.vector_id.in_(vector_ids))
                            .values(last_accessed_at=func.now())
                        )
                        await update_db.commit()
                        logger.debug(f"📊 Updated last_accessed_at for {len(vector_ids)} retrieved memories")

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
            # Decrypt the API key (handles both encrypted and legacy plaintext values)
            encrypted_key = db_config.get('azure_api_key', '')
            decrypted_key = decrypt_api_key(encrypted_key) if encrypted_key else ''

            return {
                "provider": "azure_openai",
                "config": {
                    "model": "text-embedding-3-large",
                    "embedding_dims": 3072,
                    "azure_kwargs": {
                        "api_key": decrypted_key,
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

    def _is_simple_preference(self, message: str) -> bool:
        """
        Check if message is a simple preference statement that can use shortcut extraction.

        Shortcut conditions:
        1. Message is short (under shortcut_max_length)
        2. Contains preference keywords ("I love", "I hate", "my favorite", etc.)
        3. First-person statement

        Args:
            message: User message to check

        Returns:
            True if message qualifies for shortcut extraction
        """
        if not self.enable_extraction_shortcuts:
            return False

        if len(message) > self.shortcut_max_length:
            return False

        message_lower = message.lower()

        # Check for first-person preference patterns
        first_person_patterns = [
            r"\bi\s+(love|hate|like|enjoy|prefer|dislike)\b",
            r"\bmy\s+favorite\b",
            r"\bi'm\s+(allergic|intolerant)\b",
            r"\bi\s+can't\s+stand\b",
            r"\bi\s+(always|never)\b",
        ]

        import re
        for pattern in first_person_patterns:
            if re.search(pattern, message_lower):
                logger.debug(f"⚡ Simple preference detected: \"{message[:50]}...\" (pattern: {pattern})")
                return True

        return False

    async def _extract_preference_shortcut(
        self,
        user_id: str,
        agent_id: UUID,
        user_message: str
    ) -> bool:
        """
        Extract a simple preference directly without full LLM extraction.

        This is a performance optimization for obvious preference statements like
        "I love coffee" or "My favorite color is blue".

        Args:
            user_id: User identifier
            agent_id: Agent identifier
            user_message: The user's preference statement

        Returns:
            True if shortcut was used successfully, False otherwise
        """
        try:
            # Track metric
            self.metrics["extraction_shortcuts"] += 1

            async with get_db_session() as db:
                # Get user and agent
                user = await self._get_or_create_user(user_id, db)
                agent = await self._get_agent(agent_id, db)

                # Determine memory scope
                scope, fact_agent_id = await resolve_memory_scope(user_id, agent_id, agent, user)
                mem_user_id = f"{user_id}:{agent_id}" if scope == 'agent' else user_id

                # Convert first-person to third-person for storage
                fact_text = self._convert_to_third_person(user_message)

                # Infer fact metadata
                fact_key = self._infer_fact_category(fact_text)
                importance = self._infer_importance(fact_text, fact_key)
                memory_bank = self._infer_memory_bank(fact_text, fact_key)

                # Infer validity period for temporal facts (Phase 8)
                validity_end = None
                if self.enable_temporal_detection:
                    validity_end = await self._infer_validity_period(fact_text, memory_bank)

                # Enforce memory limit before adding
                pruned = await self._enforce_memory_limit(user, db)
                if pruned > 0:
                    logger.info(f"✂️ Pre-shortcut pruning: {pruned} facts removed")

                # Call Mem0 to add the fact (still need embedding)
                # Wrap in executor to prevent event loop blocking
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    self.executor,
                    lambda: self.memory.add(
                        messages=[{"role": "user", "content": fact_text}],
                        user_id=mem_user_id
                    )
                )

                # Normalize and store
                normalized = self.mem0_normalizer.normalize_add_response(result)

                saved_count = 0
                for memory in normalized:
                    mem_fact_text = memory["text"]
                    vector_id = memory["id"]

                    # Phase 7: Check for duplicates before saving
                    is_dupe = await self._is_duplicate(mem_fact_text, user.id, db)
                    if is_dupe:
                        # Duplicate detected - delete the vector that was just created
                        logger.info(f"🔍 Skipping duplicate (shortcut): \"{mem_fact_text[:50]}...\"")
                        try:
                            loop = asyncio.get_event_loop()
                            await loop.run_in_executor(
                                self.executor,
                                lambda vid=vector_id: self.memory.delete(vid)
                            )
                        except Exception as del_err:
                            logger.warning(f"⚠️ Failed to delete duplicate vector {vector_id}: {del_err}")
                        continue

                    await self._upsert_fact(
                        user=user,
                        agent_id=fact_agent_id,
                        vector_id=vector_id,
                        fact_text=mem_fact_text,
                        importance=importance,
                        embedding_provider=self.embedding_config["provider"],
                        embedding_model=self.embedding_config["model"],
                        db=db,
                        memory_bank=memory_bank,
                        validity_end=validity_end
                    )
                    saved_count += 1

                if saved_count > 0:
                    expiry_info = f", expires={validity_end.strftime('%Y-%m-%d')}" if validity_end else ""
                    logger.info(
                        f"⚡ Shortcut extraction: saved \"{fact_text[:50]}...\" "
                        f"(bank={memory_bank}, importance={importance:.2f}{expiry_info})"
                    )
                else:
                    logger.info(f"🔍 Shortcut extraction: all facts were duplicates, nothing saved")

                return saved_count > 0

        except Exception as e:
            logger.error(f"❌ Shortcut extraction failed: {e}")
            return False

    def _convert_to_third_person(self, message: str) -> str:
        """
        Convert first-person statement to third-person for storage.

        Examples:
            "I love coffee" -> "User loves coffee"
            "My favorite color is blue" -> "User's favorite color is blue"
            "I'm allergic to peanuts" -> "User is allergic to peanuts"
        """
        import re

        # Replacements (order matters - more specific first)
        replacements = [
            (r"\bI'm\b", "User is"),
            (r"\bi'm\b", "User is"),
            (r"\bI am\b", "User is"),
            (r"\bi am\b", "User is"),
            (r"\bI have\b", "User has"),
            (r"\bi have\b", "User has"),
            (r"\bI've\b", "User has"),
            (r"\bi've\b", "User has"),
            (r"\bI\b", "User"),
            (r"\bi\b", "User"),
            (r"\bMy\b", "User's"),
            (r"\bmy\b", "User's"),
            (r"\bMe\b", "User"),
            (r"\bme\b", "User"),
        ]

        result = message
        for pattern, replacement in replacements:
            result = re.sub(pattern, replacement, result)

        return result

    async def _is_duplicate(
        self,
        fact_text: str,
        user_id: UUID,
        mem_user_id: str,
        db
    ) -> bool:
        """
        Check if a fact is a duplicate of an existing fact.

        Uses embedding similarity or text similarity based on configuration.
        Returns True if duplicate detected, False otherwise.

        Phase 7: Deduplication Improvements

        Args:
            fact_text: The fact text to check
            user_id: User UUID (for PostgreSQL queries)
            mem_user_id: User identifier for Mem0 (e.g., "user123" or "user123:agent456")
            db: Database session

        Returns:
            True if duplicate detected, False otherwise
        """
        if not self.enable_deduplication:
            return False

        try:
            # Get existing facts for this user
            result = await db.execute(
                select(UserFact).where(
                    and_(
                        UserFact.user_id == user_id,
                        UserFact.validity_end.is_(None)  # Only valid facts
                    )
                )
            )
            existing_facts = result.scalars().all()

            if not existing_facts:
                return False

            if self.use_embeddings_for_dedup:
                # Embedding-based deduplication
                # Search Mem0 for similar memories within the same user scope
                loop = asyncio.get_event_loop()

                similar_memories = await loop.run_in_executor(
                    self.executor,
                    lambda uid=mem_user_id: self.memory.search(
                        query=fact_text,
                        user_id=uid,  # Filter by user to avoid cross-user false positives
                        limit=5  # Check top 5 similar
                    )
                )

                # Normalize response
                normalized = self.mem0_normalizer.normalize_search_response(similar_memories)

                # Check if any result exceeds similarity threshold
                for mem in normalized:
                    score = mem.get("score", 0)
                    if score >= self.embedding_similarity_threshold:
                        existing_text = mem.get("text", "")
                        self.metrics["duplicates_detected"] += 1
                        self.metrics["duplicates_embedding"] += 1
                        logger.info(
                            f"🔍 Duplicate detected (embedding): "
                            f"score={score:.3f} >= {self.embedding_similarity_threshold:.3f}, "
                            f"new=\"{fact_text[:40]}...\", "
                            f"existing=\"{existing_text[:40]}...\""
                        )
                        return True

            # Text-based fallback (or primary if embeddings disabled)
            from difflib import SequenceMatcher

            fact_text_lower = fact_text.lower().strip()
            for existing in existing_facts:
                existing_text = (existing.fact_text or "").lower().strip()
                if not existing_text:
                    continue

                # Calculate text similarity
                similarity = SequenceMatcher(None, fact_text_lower, existing_text).ratio()

                if similarity >= self.text_similarity_threshold:
                    self.metrics["duplicates_detected"] += 1
                    self.metrics["duplicates_text"] += 1
                    logger.info(
                        f"🔍 Duplicate detected (text): "
                        f"similarity={similarity:.3f} >= {self.text_similarity_threshold:.3f}, "
                        f"new=\"{fact_text[:40]}...\", "
                        f"existing=\"{existing_text[:40]}...\""
                    )
                    return True

            return False

        except Exception as e:
            logger.error(f"❌ Deduplication check failed: {e}")
            # On error, allow the fact to be saved (fail open)
            return False

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

    async def _get_agent(self, agent_id: UUID, db) -> Optional[Agent]:
        """
        Get agent by ID.

        Returns None if agent doesn't exist (e.g., deleted between task creation and processing).
        """
        result = await db.execute(
            select(Agent).where(Agent.id == agent_id)
        )
        return result.scalar_one_or_none()

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

            # Preferences: "likes/loves/enjoys/prefers X" (skip filler words: to, the, a, an)
            (r"(?:likes?|loves?|enjoys?|prefers?)\s+(?:to\s+)?(?:the\s+|a\s+|an\s+)?(\w+)", "preference_{1}"),
            (r"(?:doesn't|does\s+not|hates?|dislikes?)\s+(?:to\s+)?(?:the\s+|a\s+|an\s+)?(\w+)", "dislike_{1}"),

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

    def _infer_memory_bank(self, fact_text: str, fact_key: str) -> str:
        """
        Infer memory bank from fact text and key using pattern matching.

        Memory Banks:
        - Personal: Personal preferences, identity, background
        - Work: Professional info, job skills, work relationships, career goals
        - Relationships: Family, friends, romantic partners, social connections
        - Health: Mental, physical, and spiritual health
        - Interests: Hobbies, entertainment preferences, activities
        - Events: Significant events, current events, upcoming events
        - General: Facts that don't clearly fit elsewhere (default)

        Args:
            fact_text: The natural language fact text
            fact_key: The inferred fact key (e.g., 'favorite_color', 'occupation')

        Returns:
            Memory bank name
        """
        import re
        text_lower = fact_text.lower()
        key_lower = fact_key.lower()

        # Events patterns (check first - most specific time-based facts)
        events_patterns = [
            r"(?:event|occasion|celebration|ceremony|anniversary)",
            r"(?:wedding|funeral|graduation|birthday\s+party|reunion)",
            r"(?:concert|festival|conference|convention|meetup)",
            r"(?:appointment|scheduled|upcoming|planned|will\s+(?:be|happen|occur))",
            r"(?:happened|occurred|took\s+place|was\s+born|died|passed\s+away)",
            r"(?:tomorrow|next\s+(?:week|month|year)|this\s+(?:weekend|week))",
            r"(?:last\s+(?:week|month|year)|yesterday|recently|just\s+(?:happened|occurred))",
            r"(?:news|current\s+events?|breaking|headline)",
            r"(?:election|vote|voting|political\s+event)",
            r"(?:milestone|achievement|accomplishment|won|awarded)",
        ]
        events_keys = [
            "event", "appointment", "schedule", "upcoming", "planned",
            "happened", "occurred", "milestone", "anniversary", "ceremony",
            "graduation", "wedding", "funeral", "concert", "festival"
        ]

        # Health patterns (mental, physical, spiritual)
        health_patterns = [
            r"(?:health|healthy|unhealthy|wellness|wellbeing|well-being)",
            r"(?:doctor|physician|therapist|counselor|psychiatrist|psychologist)",
            r"(?:medication|medicine|drug|prescription|supplement|vitamin)",
            r"(?:allergy|allergic|intolerant|sensitivity)",
            r"(?:diet|nutrition|eating|weight|calories|fasting)",
            r"(?:exercise|workout|fitness|gym|running|yoga|pilates)",
            r"(?:sleep|insomnia|rest|fatigue|tired|energy)",
            r"(?:anxiety|depression|stress|mental\s+health|therapy)",
            r"(?:meditation|mindfulness|spiritual|prayer|faith|belief)",
            r"(?:chronic|condition|disease|illness|symptom|diagnosis)",
            r"(?:surgery|hospital|treatment|recovery|healing)",
            r"(?:blood\s+pressure|cholesterol|diabetes|heart)",
            r"(?:pain|ache|hurt|sore|injury|injured)",
        ]
        health_keys = [
            "health", "medical", "doctor", "medication", "allergy",
            "diet", "exercise", "fitness", "sleep", "anxiety",
            "depression", "therapy", "meditation", "spiritual", "wellness",
            "condition", "symptom", "treatment", "pain", "injury"
        ]

        # Relationships patterns (family, friends, romantic, social)
        relationships_patterns = [
            r"(?:family|mother|father|mom|dad|parent|sibling|brother|sister)",
            r"(?:child|kid|son|daughter|grandchild|grandparent|grandmother|grandfather)",
            r"(?:wife|husband|spouse|partner|boyfriend|girlfriend|fiance|fiancee)",
            r"(?:married|engaged|dating|relationship|romantic|couple)",
            r"(?:friend|friendship|best\s+friend|buddy|pal|acquaintance)",
            r"(?:ex-(?:wife|husband|boyfriend|girlfriend|partner))",
            r"(?:aunt|uncle|cousin|niece|nephew|in-law)",
            r"(?:roommate|housemate|neighbor|neighbour)",
            r"(?:social|socializing|hangout|get\s+together)",
        ]
        relationships_keys = [
            "family", "mother", "father", "parent", "sibling", "brother",
            "sister", "child", "son", "daughter", "spouse", "wife", "husband",
            "partner", "boyfriend", "girlfriend", "friend", "relationship",
            "married", "dating", "engaged", "ex", "roommate", "neighbor"
        ]

        # Interests patterns (hobbies, entertainment, activities)
        interests_patterns = [
            r"(?:hobby|hobbies|pastime|leisure|recreation)",
            r"(?:favorite|love|enjoy|prefer|like|into)\s+(?:movie|film|show|series|book|music|song|band|artist|game|sport)",
            r"(?:watch(?:ing|es)?|play(?:ing|s)?|read(?:ing|s)?|listen(?:ing|s)?)\s+(?:to\s+)?(?:movie|film|show|series|book|music|song|game)",
            r"(?:gaming|video\s+game|board\s+game|card\s+game)",
            r"(?:cooking|baking|gardening|crafting|painting|drawing|photography)",
            r"(?:sports?|football|basketball|soccer|tennis|golf|swimming)",
            r"(?:hiking|camping|fishing|hunting|climbing|surfing)",
            r"(?:collect(?:ing|s)?|collection)",
            r"(?:fan\s+of|interested\s+in|passionate\s+about)",
            r"(?:music|musical|instrument|guitar|piano|drums|singing)",
            r"(?:art|artistic|creative|craft)",
            r"(?:anime|manga|comics|superhero)",
        ]
        interests_keys = [
            "hobby", "interest", "favorite", "passion", "entertainment",
            "movie", "film", "show", "book", "music", "game", "sport",
            "cooking", "gardening", "photography", "art", "craft",
            "collection", "fan", "gaming", "anime", "manga"
        ]

        # Work-related patterns
        work_patterns = [
            r"(?:work|job|career|profession|occupation|employed|office|company|business)",
            r"(?:colleague|coworker|boss|manager|client|customer)",
            r"(?:salary|income|promotion|deadline|meeting|project)",
            r"(?:skill|expertise|experience|qualification|resume|cv)",
            r"(?:industry|startup|corporation|freelance|entrepreneur)",
        ]
        work_keys = [
            "occupation", "job", "career", "work", "company", "employer",
            "profession", "role", "title", "colleague", "client", "skill"
        ]

        # Personal patterns (identity, preferences, background - not covered by other banks)
        personal_patterns = [
            r"(?:name\s+is|called|known\s+as|goes\s+by)",
            r"(?:born\s+in|from|live\s+in|moved\s+to|hometown)",
            r"(?:age|years\s+old|birthday)",
            r"(?:pet|dog|cat|animal)",
            r"(?:home|house|apartment|neighborhood)",
            r"(?:prefer|preference|dislike|hate|can't\s+stand)",
            r"(?:personality|introvert|extrovert|shy|outgoing)",
            r"(?:language|speak|fluent|native)",
            r"(?:education|school|college|university|degree|major)",
            r"(?:vacation|travel|trip|holiday|visited)",
        ]
        personal_keys = [
            "name", "age", "birthday", "location", "hometown", "home",
            "pet", "preference", "dislike", "personality", "language",
            "education", "school", "degree", "travel", "visited"
        ]

        # Check Events patterns first (most time-specific)
        for pattern in events_patterns:
            if re.search(pattern, text_lower):
                logger.debug(f"🏦 Inferred memory bank: '{fact_text[:40]}...' -> 'Events' (pattern match)")
                return "Events"
        for key in events_keys:
            if key in key_lower:
                logger.debug(f"🏦 Inferred memory bank: '{fact_text[:40]}...' -> 'Events' (key match)")
                return "Events"

        # Check Health patterns
        for pattern in health_patterns:
            if re.search(pattern, text_lower):
                logger.debug(f"🏦 Inferred memory bank: '{fact_text[:40]}...' -> 'Health' (pattern match)")
                return "Health"
        for key in health_keys:
            if key in key_lower:
                logger.debug(f"🏦 Inferred memory bank: '{fact_text[:40]}...' -> 'Health' (key match)")
                return "Health"

        # Check Relationships patterns
        for pattern in relationships_patterns:
            if re.search(pattern, text_lower):
                logger.debug(f"🏦 Inferred memory bank: '{fact_text[:40]}...' -> 'Relationships' (pattern match)")
                return "Relationships"
        for key in relationships_keys:
            if key in key_lower:
                logger.debug(f"🏦 Inferred memory bank: '{fact_text[:40]}...' -> 'Relationships' (key match)")
                return "Relationships"

        # Check Interests patterns
        for pattern in interests_patterns:
            if re.search(pattern, text_lower):
                logger.debug(f"🏦 Inferred memory bank: '{fact_text[:40]}...' -> 'Interests' (pattern match)")
                return "Interests"
        for key in interests_keys:
            if key in key_lower:
                logger.debug(f"🏦 Inferred memory bank: '{fact_text[:40]}...' -> 'Interests' (key match)")
                return "Interests"

        # Check Work patterns
        for pattern in work_patterns:
            if re.search(pattern, text_lower):
                logger.debug(f"🏦 Inferred memory bank: '{fact_text[:40]}...' -> 'Work' (pattern match)")
                return "Work"
        for key in work_keys:
            if key in key_lower:
                logger.debug(f"🏦 Inferred memory bank: '{fact_text[:40]}...' -> 'Work' (key match)")
                return "Work"

        # Check Personal patterns
        for pattern in personal_patterns:
            if re.search(pattern, text_lower):
                logger.debug(f"🏦 Inferred memory bank: '{fact_text[:40]}...' -> 'Personal' (pattern match)")
                return "Personal"
        for key in personal_keys:
            if key in key_lower:
                logger.debug(f"🏦 Inferred memory bank: '{fact_text[:40]}...' -> 'Personal' (key match)")
                return "Personal"

        # Default to General
        logger.debug(f"🏦 Inferred memory bank: '{fact_text[:40]}...' -> 'General' (default)")
        return "General"

    async def _infer_validity_period(
        self,
        fact_text: str,
        memory_bank: str
    ) -> Optional[datetime]:
        """
        Infer validity_end date for temporal facts (Phase 8: Temporal Detection).

        Uses hybrid approach:
        1. Regex patterns for obvious temporal indicators
        2. LLM fallback for ambiguous cases

        Args:
            fact_text: The natural language fact text
            memory_bank: The inferred memory bank category

        Returns:
            datetime if fact is temporary, None if permanent
        """
        import re

        text_lower = fact_text.lower()
        now = datetime.utcnow()

        # === PERMANENT PATTERNS (return None - no expiration) ===
        permanent_patterns = [
            r"birthday\s+(?:is|on|falls)",      # "birthday is December 25"
            r"anniversary",                      # anniversaries are recurring
            r"(?:was|were)\s+born",             # birth dates
            r"always\s+(?:has|does|is|likes?)", # habitual facts
            r"every\s+(?:year|month|week|day)", # recurring events
            r"annual(?:ly)?",                   # annual events
            r"(?:favorite|favourite)\s+\w+\s+is", # preferences are permanent
        ]

        for pattern in permanent_patterns:
            if re.search(pattern, text_lower):
                logger.debug(f"⏰ Temporal: '{fact_text[:40]}...' -> PERMANENT (pattern: {pattern})")
                self.metrics["temporal_permanent"] += 1
                return None

        # === TEMPORAL PATTERNS WITH FIXED DURATIONS ===
        fixed_temporal_patterns = [
            # (pattern, days_to_add, description)
            (r"\btomorrow\b", 2, "tomorrow"),
            (r"\btoday\b", 1, "today"),
            (r"\btonight\b", 1, "tonight"),
            (r"\bthis\s+week\b", 7, "this week"),
            (r"\bnext\s+week\b", 14, "next week"),
            (r"\bthis\s+weekend\b", 4, "this weekend"),
            (r"\bnext\s+month\b", 45, "next month"),
            (r"\bthis\s+month\b", 30, "this month"),
            (r"\bnext\s+year\b", 400, "next year"),
            (r"\b(?:appointment|doctor'?s?\s+(?:appointment|visit))\b", 2, "appointment"),
            (r"\b(?:meeting|interview|call)\b", 2, "meeting/interview"),
            (r"\b(?:vacation|holiday|trip|travel(?:ing|s)?)\b", 21, "vacation/trip"),
            (r"\bvisiting\b", 10, "visiting"),
            (r"\b(?:deadline|due)\b", 7, "deadline"),
            (r"\b(?:exam|test|quiz)\b", 3, "exam"),
            (r"\b(?:party|celebration|event)\b", 3, "event"),
        ]

        for pattern, days, desc in fixed_temporal_patterns:
            if re.search(pattern, text_lower):
                validity_end = now + timedelta(days=days)
                logger.info(f"⏰ Temporal: '{fact_text[:40]}...' -> expires in {days} days ({desc})")
                self.metrics["temporal_regex_detected"] += 1
                return validity_end

        # === DYNAMIC PATTERNS (parse number from text) ===
        # "in N days/weeks/months"
        in_n_days = re.search(r"\bin\s+(\d+)\s+days?\b", text_lower)
        if in_n_days:
            days = int(in_n_days.group(1))
            validity_end = now + timedelta(days=days + 1)  # +1 buffer
            logger.info(f"⏰ Temporal: '{fact_text[:40]}...' -> expires in {days} days (dynamic)")
            self.metrics["temporal_regex_detected"] += 1
            return validity_end

        in_n_weeks = re.search(r"\bin\s+(\d+)\s+weeks?\b", text_lower)
        if in_n_weeks:
            weeks = int(in_n_weeks.group(1))
            validity_end = now + timedelta(weeks=weeks, days=2)  # +2 days buffer
            logger.info(f"⏰ Temporal: '{fact_text[:40]}...' -> expires in {weeks} weeks (dynamic)")
            self.metrics["temporal_regex_detected"] += 1
            return validity_end

        in_n_months = re.search(r"\bin\s+(\d+)\s+months?\b", text_lower)
        if in_n_months:
            months = int(in_n_months.group(1))
            validity_end = now + timedelta(days=months * 32)  # ~32 days per month + buffer
            logger.info(f"⏰ Temporal: '{fact_text[:40]}...' -> expires in {months} months (dynamic)")
            self.metrics["temporal_regex_detected"] += 1
            return validity_end

        # "until [day of week]"
        until_day = re.search(r"\buntil\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", text_lower)
        if until_day:
            target_day = until_day.group(1)
            days_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
            target_weekday = days_map[target_day]
            current_weekday = now.weekday()
            days_until = (target_weekday - current_weekday) % 7
            if days_until == 0:
                days_until = 7  # Next occurrence if same day
            validity_end = now + timedelta(days=days_until + 1)  # +1 day buffer
            logger.info(f"⏰ Temporal: '{fact_text[:40]}...' -> expires on {target_day} ({days_until} days)")
            self.metrics["temporal_regex_detected"] += 1
            return validity_end

        # === LLM FALLBACK FOR AMBIGUOUS CASES ===
        # Trigger LLM if: Events bank with no pattern match, or contains ambiguous temporal words
        ambiguous_triggers = ["soon", "later", "upcoming", "planned", "planning", "going to", "will be", "about to"]
        has_ambiguous = any(trigger in text_lower for trigger in ambiguous_triggers)

        if self.temporal_llm_fallback and (memory_bank == "Events" or has_ambiguous):
            try:
                validity_end = await self._temporal_llm_analysis(fact_text)
                if validity_end:
                    self.metrics["temporal_llm_detected"] += 1
                    return validity_end
            except Exception as e:
                logger.warning(f"⚠️ LLM temporal analysis failed: {e}")
                # Fall through to default behavior

        # No temporal indicators detected - permanent fact
        return None

    async def _temporal_llm_analysis(self, fact_text: str) -> Optional[datetime]:
        """
        Use LLM to analyze if fact is temporary and estimate expiration.

        Args:
            fact_text: The fact to analyze

        Returns:
            datetime if temporary, None if permanent
        """
        prompt = f"""Analyze this fact and determine if it's temporary or permanent:

Fact: "{fact_text}"

Is this fact:
1. PERMANENT - A lasting characteristic, preference, recurring event, or identity info
2. TEMPORARY - A one-time event, current state, or time-limited situation

If TEMPORARY, estimate how many days until this fact expires (1-365).

Respond ONLY with JSON, no other text:
{{"type": "permanent"}} or {{"type": "temporary", "days": 7}}"""

        try:
            # Use local LLM for cost efficiency
            config = LLMConfig(
                provider=ProviderType.LOCAL,
                model=os.getenv("LOCAL_LLM_RELEVANCE_MODEL", "gemma3n:latest"),
                temperature=0.1,
                max_tokens=50
            )

            response_text = ""
            async for chunk in self.llm_service.generate_stream(prompt, config):
                response_text += chunk

            # Parse JSON response
            import json
            # Extract JSON from response (handle potential markdown wrapping)
            json_match = re.search(r'\{[^}]+\}', response_text)
            if json_match:
                result = json.loads(json_match.group())
                if result.get("type") == "temporary":
                    days = result.get("days", self.temporal_default_days)
                    validity_end = datetime.utcnow() + timedelta(days=days)
                    logger.info(f"⏰ LLM Temporal: '{fact_text[:40]}...' -> expires in {days} days")
                    return validity_end
                else:
                    logger.debug(f"⏰ LLM Temporal: '{fact_text[:40]}...' -> PERMANENT")
                    return None

        except Exception as e:
            logger.warning(f"⚠️ Failed to parse LLM temporal response: {e}")

        return None

    def _infer_importance(self, fact_text: str, fact_key: str) -> float:
        """
        Infer importance score from fact text and key using pattern matching.

        Importance Levels:
        - 1.0: Critical identity facts (name, location, occupation)
        - 0.8: Strong preferences, important relationships, health info
        - 0.6: General interests, hobbies, casual preferences
        - 0.4: Minor details, context-dependent info
        - 0.2: Trivial mentions

        Args:
            fact_text: The natural language fact text
            fact_key: The inferred fact key

        Returns:
            Importance score (0.0-1.0)
        """
        import re
        text_lower = fact_text.lower()
        key_lower = fact_key.lower()

        # Critical identity facts (1.0)
        critical_patterns = [
            r"(?:name\s+is|called|named)\s+\w+",
            r"(?:live[sd]?\s+in|from|located\s+in)\s+\w+",
            r"(?:work[s]?\s+(?:as|at|for)|job\s+is|occupation\s+is|profession\s+is)",
            r"(?:born\s+(?:on|in)|birthday\s+is|age\s+is|\d+\s+years?\s+old)",
        ]
        critical_keys = ["name", "location", "occupation", "profession", "age", "birthday", "hometown"]

        # Important facts (0.8)
        important_patterns = [
            r"(?:married|spouse|wife|husband|partner|girlfriend|boyfriend)",
            r"(?:child|son|daughter|parent|mother|father|sibling|brother|sister)",
            r"(?:allerg|medication|health\s+condition|disease|illness)",
            r"(?:love[s]?\s+\w+|hate[s]?\s+\w+|favorite\s+\w+\s+is)",
        ]
        important_keys = ["spouse", "child", "parent", "sibling", "family", "allergy", "health", "favorite", "love", "hate"]

        # Medium importance (0.6)
        medium_patterns = [
            r"(?:hobby|hobbies|enjoy[s]?\s+\w+ing|like[s]?\s+\w+ing)",
            r"(?:pet|dog|cat|animal)",
            r"(?:interest|interested\s+in)",
            r"(?:prefer[s]?\s+\w+|rather\s+\w+)",
        ]
        medium_keys = ["hobby", "interest", "pet", "preference", "enjoy"]

        # Check critical patterns (1.0)
        for pattern in critical_patterns:
            if re.search(pattern, text_lower):
                logger.debug(f"⭐ Inferred importance: '{fact_text[:40]}...' -> 1.0 (critical pattern)")
                return 1.0
        for key in critical_keys:
            if key in key_lower:
                logger.debug(f"⭐ Inferred importance: '{fact_text[:40]}...' -> 1.0 (critical key)")
                return 1.0

        # Check important patterns (0.8)
        for pattern in important_patterns:
            if re.search(pattern, text_lower):
                logger.debug(f"⭐ Inferred importance: '{fact_text[:40]}...' -> 0.8 (important pattern)")
                return 0.8
        for key in important_keys:
            if key in key_lower:
                logger.debug(f"⭐ Inferred importance: '{fact_text[:40]}...' -> 0.8 (important key)")
                return 0.8

        # Check medium patterns (0.6)
        for pattern in medium_patterns:
            if re.search(pattern, text_lower):
                logger.debug(f"⭐ Inferred importance: '{fact_text[:40]}...' -> 0.6 (medium pattern)")
                return 0.6
        for key in medium_keys:
            if key in key_lower:
                logger.debug(f"⭐ Inferred importance: '{fact_text[:40]}...' -> 0.6 (medium key)")
                return 0.6

        # Default to 0.7 (medium-high, since Mem0 already filtered for relevance)
        logger.debug(f"⭐ Inferred importance: '{fact_text[:40]}...' -> 0.7 (default)")
        return 0.7

    # ==================== PRUNING METHODS ====================

    async def _get_user_fact_count(self, user_id: UUID, db) -> int:
        """Get the total number of facts for a user."""
        result = await db.execute(
            select(func.count(UserFact.id)).where(
                and_(
                    UserFact.user_id == user_id,
                    UserFact.validity_end.is_(None)  # Only count valid facts
                )
            )
        )
        return result.scalar() or 0

    async def _enforce_memory_limit(self, user: User, db) -> int:
        """
        Check memory limit and prune if needed BEFORE adding new facts.

        Returns:
            Number of facts pruned
        """
        if not self.pruning_enabled:
            return 0

        current_count = await self._get_user_fact_count(user.id, db)

        # Check if we need to prune (leave room for at least 1 new fact)
        if current_count < self.max_memories_per_user:
            return 0

        # Calculate how many to prune
        to_prune = (current_count - self.max_memories_per_user) + self.pruning_batch_size
        to_prune = min(to_prune, current_count)  # Don't prune more than we have

        logger.info(f"✂️ Memory limit reached for user {user.user_id or str(user.id)}: {current_count}/{self.max_memories_per_user}")
        logger.info(f"✂️ Pruning {to_prune} facts using '{self.pruning_strategy}' strategy")

        if self.pruning_strategy == "fifo":
            pruned = await self._prune_fifo(user.id, to_prune, db)
        elif self.pruning_strategy == "lru":
            pruned = await self._prune_lru(user.id, to_prune, db)
        else:
            logger.warning(f"⚠️ Unknown pruning strategy '{self.pruning_strategy}', using FIFO")
            pruned = await self._prune_fifo(user.id, to_prune, db)

        return pruned

    async def _prune_fifo(self, user_id: UUID, count: int, db) -> int:
        """
        Prune oldest facts (First In, First Out).

        Deletes facts with oldest created_at timestamps.
        Also deletes corresponding vectors from Mem0.
        Protected facts (is_protected=True) are never pruned.
        """
        # Get oldest unprotected facts to prune
        result = await db.execute(
            select(UserFact)
            .where(
                and_(
                    UserFact.user_id == user_id,
                    UserFact.validity_end.is_(None),
                    UserFact.is_protected == False  # Never prune protected facts
                )
            )
            .order_by(UserFact.created_at.asc())
            .limit(count)
        )
        facts_to_prune = result.scalars().all()

        pruned_count = 0
        for fact in facts_to_prune:
            try:
                # Delete vector from Mem0 FIRST (compensating transaction pattern)
                if fact.vector_id:
                    loop = asyncio.get_event_loop()
                    try:
                        await loop.run_in_executor(
                            self.executor,
                            lambda vid=fact.vector_id: self.memory.delete(vid)
                        )
                    except Exception as vec_err:
                        # If vector deletion fails, skip this fact to avoid orphaned vectors
                        logger.warning(f"⚠️ Failed to delete vector {fact.vector_id}, skipping fact deletion: {vec_err}")
                        continue

                # Delete fact from database only if vector deletion succeeded
                await db.delete(fact)
                pruned_count += 1
                logger.debug(f"✂️ Pruned fact: {fact.fact_key} (created: {fact.created_at})")

            except Exception as e:
                logger.error(f"❌ Failed to prune fact {fact.id}: {e}")

        await db.commit()
        logger.info(f"✂️ FIFO pruning complete: {pruned_count} facts deleted")
        return pruned_count

    async def _prune_lru(self, user_id: UUID, count: int, db) -> int:
        """
        Prune least recently used facts (LRU).

        Deletes facts with oldest last_accessed_at timestamps.
        Falls back to created_at if last_accessed_at is NULL.
        Also deletes corresponding vectors from Mem0.
        Protected facts (is_protected=True) are never pruned.
        """
        # Get least recently accessed unprotected facts to prune
        # Use COALESCE to fallback to created_at if last_accessed_at is NULL
        result = await db.execute(
            select(UserFact)
            .where(
                and_(
                    UserFact.user_id == user_id,
                    UserFact.validity_end.is_(None),
                    UserFact.is_protected == False  # Never prune protected facts
                )
            )
            .order_by(func.coalesce(UserFact.last_accessed_at, UserFact.created_at).asc())
            .limit(count)
        )
        facts_to_prune = result.scalars().all()

        pruned_count = 0
        for fact in facts_to_prune:
            try:
                # Delete vector from Mem0 FIRST (compensating transaction pattern)
                if fact.vector_id:
                    loop = asyncio.get_event_loop()
                    try:
                        await loop.run_in_executor(
                            self.executor,
                            lambda vid=fact.vector_id: self.memory.delete(vid)
                        )
                    except Exception as vec_err:
                        # If vector deletion fails, skip this fact to avoid orphaned vectors
                        logger.warning(f"⚠️ Failed to delete vector {fact.vector_id}, skipping fact deletion: {vec_err}")
                        continue

                # Delete fact from database only if vector deletion succeeded
                await db.delete(fact)
                pruned_count += 1
                logger.debug(f"✂️ Pruned fact: {fact.fact_key} (last_accessed: {fact.last_accessed_at})")

            except Exception as e:
                logger.error(f"❌ Failed to prune fact {fact.id}: {e}")

        await db.commit()
        logger.info(f"✂️ LRU pruning complete: {pruned_count} facts deleted")
        return pruned_count

    async def _update_last_accessed(self, fact_ids: list[UUID], db):
        """Update last_accessed_at for retrieved facts."""
        if not fact_ids:
            return

        from sqlalchemy import update
        await db.execute(
            update(UserFact)
            .where(UserFact.id.in_(fact_ids))
            .values(last_accessed_at=func.now())
        )
        await db.commit()
        logger.debug(f"📊 Updated last_accessed_at for {len(fact_ids)} facts")

    # ==================== END PRUNING METHODS ====================

    async def _upsert_fact(
        self,
        user: User,
        agent_id: UUID | None,
        vector_id: str,
        fact_text: str,
        importance: float,
        embedding_provider: str,
        embedding_model: str,
        db,
        memory_bank: str | None = None,
        validity_end: datetime | None = None
    ):
        """
        Upsert fact to PostgreSQL (for relational queries and metadata).

        Uses vector_id for matching (unique per fact), not fact_key.
        This prevents overwrites when Mem0 extracts facts without colon format.

        Args:
            agent_id: UUID for agent-specific facts, None for global facts
            memory_bank: Optional memory bank (Personal, Work, General). Auto-inferred if not provided.
            validity_end: Optional expiration datetime for temporal facts (Phase 8). None = permanent.
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

        # Infer memory bank if not provided
        if memory_bank is None:
            memory_bank = self._infer_memory_bank(fact_text, fact_key)

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
            existing.memory_bank = memory_bank
            existing.updated_at = func.now()
            # Only update validity_end if provided (don't overwrite manual overrides)
            if validity_end is not None:
                existing.validity_end = validity_end
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
                embedding_model=embedding_model,
                memory_bank=memory_bank,
                validity_end=validity_end  # Phase 8: Temporal detection
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

    # ==================== SUMMARIZATION METHODS (Phase 3) ====================

    async def run_summarization_cycle(self) -> dict:
        """
        Run a single summarization cycle for all users with old memories.

        Returns:
            dict with summarization statistics
        """
        if not self.enable_summarization:
            logger.debug("📦 Summarization disabled, skipping cycle")
            return {"skipped": True, "reason": "disabled"}

        logger.info("📦 Starting summarization cycle...")
        stats = {
            "users_processed": 0,
            "clusters_found": 0,
            "summaries_created": 0,
            "facts_summarized": 0,
            "errors": 0
        }

        try:
            async with get_db_session() as db:
                # Find users with old memories eligible for summarization
                cutoff_date = datetime.utcnow() - timedelta(days=self.summarization_min_age_days)

                # Query for distinct users with old, non-summarized, non-protected facts
                result = await db.execute(
                    select(UserFact.user_id)
                    .where(
                        and_(
                            UserFact.validity_end.is_(None),
                            UserFact.created_at < cutoff_date,
                            UserFact.is_summarized == False,
                            UserFact.is_protected == False
                        )
                    )
                    .distinct()
                )
                user_ids = [row[0] for row in result.fetchall()]

                logger.info(f"📦 Found {len(user_ids)} users with old memories to summarize")

                for user_id in user_ids:
                    try:
                        user_stats = await self._summarize_user_memories(user_id, cutoff_date, db)
                        stats["users_processed"] += 1
                        stats["clusters_found"] += user_stats.get("clusters_found", 0)
                        stats["summaries_created"] += user_stats.get("summaries_created", 0)
                        stats["facts_summarized"] += user_stats.get("facts_summarized", 0)
                    except Exception as e:
                        logger.error(f"❌ Summarization failed for user {user_id}: {e}")
                        stats["errors"] += 1

            # Update global metrics
            self.metrics["summaries_created"] += stats["summaries_created"]
            self.metrics["facts_summarized"] += stats["facts_summarized"]
            self.metrics["clusters_found"] += stats["clusters_found"]

            logger.info(
                f"📦 Summarization cycle complete: "
                f"{stats['users_processed']} users, "
                f"{stats['clusters_found']} clusters, "
                f"{stats['summaries_created']} summaries, "
                f"{stats['facts_summarized']} facts summarized"
            )

        except Exception as e:
            logger.error(f"❌ Summarization cycle failed: {e}")
            stats["error"] = str(e)

        return stats

    async def _summarize_user_memories(
        self,
        user_id: UUID,
        cutoff_date: datetime,
        db
    ) -> dict:
        """
        Find and summarize memory clusters for a specific user.

        Args:
            user_id: User's UUID
            cutoff_date: Only consider facts older than this
            db: Database session

        Returns:
            dict with user-specific summarization stats
        """
        stats = {"clusters_found": 0, "summaries_created": 0, "facts_summarized": 0}

        # Get old, non-summarized, non-protected facts for this user
        result = await db.execute(
            select(UserFact)
            .where(
                and_(
                    UserFact.user_id == user_id,
                    UserFact.validity_end.is_(None),
                    UserFact.created_at < cutoff_date,
                    UserFact.is_summarized == False,
                    UserFact.is_protected == False
                )
            )
            .order_by(UserFact.created_at.asc())
        )
        facts = result.scalars().all()

        if len(facts) < self.summarization_min_cluster_size:
            logger.debug(f"📦 User {user_id}: Only {len(facts)} old facts, need at least {self.summarization_min_cluster_size}")
            return stats

        logger.info(f"📦 User {user_id}: Found {len(facts)} old facts to cluster")

        # Get string user_id for Mem0 search (Mem0 uses string IDs)
        user_result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        mem_user_id = (user.user_id or str(user.id)) if user else str(user_id)

        # Find clusters using embedding similarity
        clusters = await self._find_memory_clusters(facts, mem_user_id)
        stats["clusters_found"] = len(clusters)

        for cluster in clusters:
            if len(cluster) >= self.summarization_min_cluster_size:
                try:
                    summary_created = await self._summarize_cluster(cluster, user_id, db)
                    if summary_created:
                        stats["summaries_created"] += 1
                        stats["facts_summarized"] += len(cluster)
                except Exception as e:
                    logger.error(f"❌ Failed to summarize cluster: {e}")

        return stats

    async def _find_memory_clusters(self, facts: list, mem_user_id: str) -> list:
        """
        Group facts into clusters based on embedding similarity.

        Uses a simple greedy clustering approach:
        1. Start with first unassigned fact as cluster seed
        2. Add facts with similarity >= threshold
        3. Repeat until all facts assigned or checked

        Args:
            facts: List of UserFact objects
            mem_user_id: String user ID for Mem0 search filtering

        Returns:
            List of clusters (each cluster is a list of UserFact objects)
        """
        if not facts:
            return []

        # Build fact text list for embedding search
        fact_texts = [(f.id, f.fact_text or "") for f in facts]
        fact_map = {f.id: f for f in facts}

        clusters = []
        assigned = set()

        for fact_id, fact_text in fact_texts:
            if fact_id in assigned:
                continue

            # Start new cluster with this fact
            cluster = [fact_map[fact_id]]
            assigned.add(fact_id)

            # Search for similar facts using Mem0 (filtered by user)
            try:
                loop = asyncio.get_event_loop()
                similar = await loop.run_in_executor(
                    self.executor,
                    lambda ft=fact_text, uid=mem_user_id: self.memory.search(
                        query=ft,
                        user_id=uid,
                        limit=self.summarization_max_cluster_size
                    )
                )

                normalized = self.mem0_normalizer.normalize_search_response(similar)
                logger.debug(f"📦 Mem0 search for '{fact_text[:30]}...' returned {len(normalized)} results")

                for mem in normalized:
                    score = mem.get("score", 0)
                    logger.debug(f"📦   - score={score:.3f}, id={mem.get('id', 'N/A')[:8]}...")
                    if score >= self.summarization_similarity_threshold:
                        # Find the matching fact by vector_id
                        vector_id = mem.get("id")
                        for fid, f in fact_map.items():
                            if f.vector_id == vector_id and fid not in assigned:
                                cluster.append(f)
                                assigned.add(fid)
                                if len(cluster) >= self.summarization_max_cluster_size:
                                    break

            except Exception as e:
                logger.error(f"❌ Cluster search failed: {e}")

            if len(cluster) >= self.summarization_min_cluster_size:
                clusters.append(cluster)
            else:
                # Remove from assigned if cluster too small (will be checked again)
                for f in cluster:
                    assigned.discard(f.id)

        logger.info(f"📦 Found {len(clusters)} valid clusters from {len(facts)} facts")
        return clusters

    async def _summarize_cluster(
        self,
        cluster: list,
        user_id: UUID,
        db
    ) -> bool:
        """
        Summarize a cluster of related facts into a single fact.

        Args:
            cluster: List of UserFact objects to summarize
            user_id: User's UUID
            db: Database session

        Returns:
            True if summary was created successfully
        """
        # Build the summarization prompt
        memory_texts = []
        for i, fact in enumerate(cluster, 1):
            memory_texts.append(f"{i}. {fact.fact_text}")

        memories_str = "\n".join(memory_texts)

        prompt = f"""You are a memory consolidation assistant. Combine these related memories about a user into a single concise summary.

Rules:
1. Preserve all key information
2. Resolve contradictions (prefer newer information)
3. Remove redundancy
4. Maintain specific details when important
5. Keep the summary under 100 words
6. Write in third person (e.g., "The user likes..." not "I like...")

Memories to summarize:
{memories_str}

Output a single paragraph summary."""

        try:
            # Call LLM for summarization
            summary_text = await self._call_summarization_llm(prompt)

            if not summary_text:
                logger.warning("📦 LLM returned empty summary")
                return False

            # Determine memory bank (use most common bank from cluster)
            bank_counts = {}
            for fact in cluster:
                bank = fact.memory_bank or "General"
                bank_counts[bank] = bank_counts.get(bank, 0) + 1
            most_common_bank = max(bank_counts, key=bank_counts.get)

            # Calculate average importance
            avg_importance = sum(f.importance or 0.5 for f in cluster) / len(cluster)

            # Get user object
            user_result = await db.execute(
                select(User).where(User.id == user_id)
            )
            user = user_result.scalar_one_or_none()
            if not user:
                logger.error(f"❌ User {user_id} not found")
                return False

            # Create embedding for summary via Mem0
            loop = asyncio.get_event_loop()
            mem_user_id = user.user_id or str(user.id)  # Use string user_id for Mem0

            result = await loop.run_in_executor(
                self.executor,
                lambda: self.memory.add(
                    messages=[{"role": "user", "content": summary_text}],
                    user_id=mem_user_id
                )
            )

            normalized = self.mem0_normalizer.normalize_add_response(result)
            if not normalized:
                logger.error("📦 Mem0 returned no vector for summary")
                return False

            vector_id = normalized[0]["id"]

            # Create summary fact
            original_fact_ids = [str(f.id) for f in cluster]
            summary_fact = UserFact(
                user_id=user_id,
                agent_id=cluster[0].agent_id,  # Use first fact's agent_id
                fact_key="summary",
                fact_value=summary_text[:200],  # Truncate for value field
                fact_text=summary_text,
                vector_id=vector_id,
                importance=avg_importance,
                memory_bank=most_common_bank,
                embedding_provider=self.embedding_config["provider"],
                embedding_model=self.embedding_config["model"],
                is_summarized=True,
                summarized_from=original_fact_ids,
                is_protected=True  # Summaries are protected from pruning
            )

            db.add(summary_fact)

            # Delete original facts and their vectors
            for fact in cluster:
                # Delete vector from Mem0
                if fact.vector_id:
                    try:
                        await loop.run_in_executor(
                            self.executor,
                            lambda vid=fact.vector_id: self.memory.delete(vid)
                        )
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to delete vector {fact.vector_id}: {e}")

                # Delete fact from database
                await db.delete(fact)

            await db.commit()

            logger.info(
                f"📦 Created summary from {len(cluster)} facts: "
                f"\"{summary_text[:50]}...\" (bank={most_common_bank})"
            )

            return True

        except Exception as e:
            logger.error(f"❌ Summarization failed: {e}")
            await db.rollback()
            raise  # Re-raise so caller knows summarization failed

    async def _call_summarization_llm(self, prompt: str) -> str:
        """
        Call the LLM for summarization.

        Uses configured provider (OpenRouter or local).

        Args:
            prompt: The summarization prompt

        Returns:
            Summary text or empty string on failure
        """
        import httpx

        try:
            if self.summarization_llm_provider == "openrouter":
                api_key = os.getenv("OPENROUTER_API_KEY")
                if not api_key:
                    logger.error("❌ OPENROUTER_API_KEY not set for summarization")
                    return ""

                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": self.summarization_llm_model,
                            "messages": [
                                {"role": "user", "content": prompt}
                            ],
                            "max_tokens": 200,
                            "temperature": 0.3
                        }
                    )

                    if response.status_code == 200:
                        data = response.json()
                        return data["choices"][0]["message"]["content"].strip()
                    else:
                        logger.error(f"❌ OpenRouter API error: {response.status_code} - {response.text}")
                        return ""

            elif self.summarization_llm_provider == "local":
                local_url = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")

                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        f"{local_url}/chat/completions",
                        json={
                            "model": self.summarization_llm_model,
                            "messages": [
                                {"role": "user", "content": prompt}
                            ],
                            "max_tokens": 200,
                            "temperature": 0.3
                        }
                    )

                    if response.status_code == 200:
                        data = response.json()
                        return data["choices"][0]["message"]["content"].strip()
                    else:
                        logger.error(f"❌ Local LLM API error: {response.status_code} - {response.text}")
                        return ""

            else:
                logger.error(f"❌ Unknown LLM provider: {self.summarization_llm_provider}")
                return ""

        except Exception as e:
            logger.error(f"❌ LLM call failed: {e}")
            return ""
