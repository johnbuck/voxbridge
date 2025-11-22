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
from src.database.models import User, UserFact, ExtractionTask, Agent
from src.database.session import get_db_session
from src.services.llm_service import LLMService
from src.config.logging_config import get_logger

# Configure logging
logger = get_logger(__name__)


class MemoryService:
    """
    Memory service for VoxBridge conversational memory system.

    Architecture:
    - Wraps Mem0 for fact extraction/retrieval
    - Queue-based extraction (doesn't block voice responses)
    - Error handling with retry logic
    - Metrics tracking for monitoring
    """

    def __init__(self):
        """Initialize memory service with Mem0."""
        self.llm_service = LLMService()

        # Initialize Mem0 based on environment config
        embedding_provider = os.getenv("EMBEDDING_PROVIDER", "local")

        # Check if Azure credentials are configured
        azure_api_key = os.getenv("AZURE_EMBEDDING_API_KEY")
        azure_endpoint = os.getenv("AZURE_EMBEDDING_ENDPOINT")

        # Default to local embeddings if Azure credentials not configured
        if embedding_provider == "azure" and (not azure_api_key or not azure_endpoint):
            logger.warning("⚠️ Azure embeddings selected but credentials not configured, falling back to local embeddings")
            embedding_provider = "local"

        if embedding_provider == "azure":
            embedder_config = {
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
        else:  # local
            embedder_config = {
                "provider": "huggingface",
                "config": {
                    "model": os.getenv("LOCAL_EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2"),
                    "embedding_dims": int(os.getenv("LOCAL_EMBEDDING_DIMS", "768"))
                }
            }

        # Mem0 configuration
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
                "provider": "openai",
                "config": {
                    "model": "gpt-4o-mini",
                    "api_key": os.getenv("OPENROUTER_API_KEY") or "dummy-key"  # OpenRouter API key for fact extraction
                }
            },
            "embedder": embedder_config
        }

        self.memory = Memory.from_config(config)
        logger.info(f"✅ MemoryService initialized with {embedding_provider} embeddings")

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

                            # Extract facts (this will create its own db session)
                            await self._extract_facts_from_turn(
                                task.user_id,
                                task.agent_id,
                                task.user_message,
                                task.ai_response
                            )

                            # Mark as completed
                            task.status = "completed"
                            task.completed_at = func.now()
                            await db.commit()

                            logger.info(f"✅ Completed extraction task {task.id}")

                        except Exception as e:
                            logger.error(f"❌ Extraction task {task.id} failed (attempt {task.attempts}): {e}")
                            task.status = "failed" if task.attempts >= 3 else "pending"
                            task.error = str(e)
                            await db.commit()

                # Sleep before next batch
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"❌ Queue processor error: {e}")
                await asyncio.sleep(10)

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

            # Determine memory scope
            if agent.memory_scope == "global":
                mem_user_id = user_id  # Global memory across all agents
            else:
                mem_user_id = f"{user_id}:{agent_id}"  # Agent-specific memory

            # Call Mem0 to extract facts
            result = self.memory.add(
                messages=[
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": ai_response}
                ],
                user_id=mem_user_id
            )

            # Store extracted facts in PostgreSQL for relational queries
            if result and "memories" in result:
                for memory in result["memories"]:
                    await self._upsert_fact(
                        user=user,
                        agent_id=agent_id,
                        vector_id=memory["id"],
                        fact_text=memory["memory"],
                        importance=memory.get("score", 0.5),
                        embedding_provider=os.getenv("EMBEDDING_PROVIDER", "azure"),
                        embedding_model=memory.get("metadata", {}).get("model", "unknown"),
                        db=db
                    )

            logger.info(f"📝 Extracted {len(result.get('memories', []))} facts for user {user_id}")

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
                # Get agent to determine memory scope
                agent = await self._get_agent(agent_id, db)

                # Determine memory scope
                if agent.memory_scope == "global":
                    mem_user_id = user_id  # Global memory across all agents
                else:
                    mem_user_id = f"{user_id}:{agent_id}"  # Agent-specific memory

            # Search Mem0 for relevant memories
            memories = self.memory.search(
                query=query,
                user_id=mem_user_id,
                limit=limit
            )

            if not memories or len(memories) == 0:
                return ""

            # Format memories as context
            context_lines = ["<user_memories>"]
            for mem in memories:
                # Include relevance score for debugging
                score = mem.get("score", 0.0)
                memory_text = mem.get("memory", "")
                context_lines.append(f"- {memory_text} (relevance: {score:.2f})")
            context_lines.append("</user_memories>")

            context = "\n".join(context_lines)
            logger.debug(f"🧠 Retrieved {len(memories)} memories for user {user_id}: {context}")
            return context

        except Exception as e:
            logger.error(f"❌ Failed to retrieve memories for user {user_id}: {e}")
            return ""  # Degrade gracefully

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

        response = await self.llm_service.generate(
            messages=[{"role": "system", "content": relevance_prompt}],
            model_override="gpt-4o-mini"
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

    async def _upsert_fact(
        self,
        user: User,
        agent_id: UUID,
        vector_id: str,
        fact_text: str,
        importance: float,
        embedding_provider: str,
        embedding_model: str,
        db
    ):
        """
        Upsert fact to PostgreSQL (for relational queries and metadata).
        """
        # Extract fact key from text (e.g., "name", "location")
        fact_key = fact_text.split(":")[0].strip().lower() if ":" in fact_text else "general"
        fact_value = fact_text.split(":", 1)[1].strip() if ":" in fact_text else fact_text

        # Check if fact exists
        result = await db.execute(
            select(UserFact).where(and_(
                UserFact.user_id == user.id,
                UserFact.fact_key == fact_key,
                UserFact.agent_id == agent_id
            ))
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

        await db.commit()
