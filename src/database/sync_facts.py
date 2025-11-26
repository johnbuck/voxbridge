"""
Sync Orphaned Facts Script (VoxBridge 2.0 Memory System)

Purpose: Re-embed facts that exist in user_facts but have no corresponding
         vectors in user_memories (orphaned metadata).

ARCHITECTURE CONTEXT:
- user_facts (VoxBridge): Relational metadata for CRUD/frontend
- user_memories (Mem0): Vector embeddings for semantic search
- Relationship: 1:1 (each fact should have exactly ONE vector)

This script fixes sync issues where facts were created before Mem0 was
properly configured, or where vector deletion failed.

Usage:
    docker exec voxbridge-api python -m src.database.sync_facts
    docker exec voxbridge-api python -m src.database.sync_facts --dry-run
"""

import asyncio
import argparse
from sqlalchemy import select

from src.database.models import UserFact, Agent, User
from src.database.session import get_db_session
from src.services.memory_service import MemoryService, get_global_embedding_config
from src.config.logging_config import get_logger

logger = get_logger(__name__)


async def sync_orphaned_facts(dry_run: bool = False):
    """
    Re-embed facts that have no corresponding vectors.

    Args:
        dry_run: If True, only report what would be done without making changes
    """
    # Initialize memory service with database embedding config
    db_embedding_config = await get_global_embedding_config()
    memory_service = MemoryService(db_embedding_config=db_embedding_config)

    async with get_db_session() as db:
        # Find facts with missing vectors (vector_id IS NULL)
        result = await db.execute(
            select(UserFact)
            .where(UserFact.vector_id.is_(None))
            .order_by(UserFact.created_at)
        )
        orphaned_facts = result.scalars().all()

        if not orphaned_facts:
            logger.info("✅ No orphaned facts found! user_facts and user_memories are in sync.")
            return

        logger.info(f"🔍 Found {len(orphaned_facts)} orphaned facts (no vector_id)")

        if dry_run:
            logger.info("🔬 DRY RUN MODE - No changes will be made")
            logger.info("\nOrphaned facts that would be re-embedded:")
            for fact in orphaned_facts:
                logger.info(f"  • {fact.fact_key}: {fact.fact_value} (fact_id={fact.id})")
            return

        # Re-embed each orphaned fact
        synced_count = 0
        failed_count = 0

        for fact in orphaned_facts:
            try:
                # Get user and agent for memory scope
                user = await db.get(User, fact.user_id)
                agent = await db.get(Agent, fact.agent_id) if fact.agent_id else None

                if not user:
                    logger.warning(f"⚠️ Skipping fact {fact.id}: User {fact.user_id} not found")
                    failed_count += 1
                    continue

                # Determine memory scope
                if agent and agent.memory_scope == "global":
                    mem_user_id = user.user_id  # Global memory across all agents
                else:
                    mem_user_id = f"{user.user_id}:{fact.agent_id}"  # Agent-specific memory

                # Re-create vector using fact_text
                fact_text = fact.fact_text or f"{fact.fact_key}: {fact.fact_value}"

                # Add memory to Mem0 (creates new vector)
                memory_result = memory_service.memory.add(
                    messages=[{"role": "user", "content": fact_text}],
                    user_id=mem_user_id
                )

                if memory_result and "memories" in memory_result and len(memory_result["memories"]) > 0:
                    # Update fact with new vector_id
                    new_vector_id = memory_result["memories"][0]["id"]
                    fact.vector_id = new_vector_id
                    await db.commit()

                    logger.info(
                        f"✅ Re-embedded fact: {fact.fact_key} "
                        f"(fact_id={fact.id}, vector_id={new_vector_id})"
                    )
                    synced_count += 1
                else:
                    logger.warning(f"⚠️ Failed to create vector for fact {fact.id}: Mem0 returned no memories")
                    failed_count += 1

            except Exception as e:
                logger.error(f"❌ Failed to re-embed fact {fact.id}: {e}")
                failed_count += 1

        logger.info(
            f"\n📊 Sync complete: {synced_count} facts re-embedded, "
            f"{failed_count} failures"
        )


async def main():
    """Main entry point for sync script."""
    parser = argparse.ArgumentParser(description="Sync orphaned facts with Mem0 vectors")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    args = parser.parse_args()

    logger.info("🔄 Starting orphaned facts sync...")
    await sync_orphaned_facts(dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
