"""
Backfill Facts from Orphaned Vectors (VoxBridge 2.0 Memory System)

Purpose: Create user_facts entries for vectors that exist in user_memories
         but have no corresponding facts (orphaned vectors).

ARCHITECTURE CONTEXT:
- user_facts (VoxBridge): Relational metadata for CRUD/frontend
- user_memories (Mem0): Vector embeddings for semantic search
- Relationship: 1:1 (each vector should have exactly ONE fact)

This script fixes sync issues where vectors were created manually (via UI)
before the automatic extraction system was working, or where fact creation failed.

Usage:
    docker exec voxbridge-api python -m src.database.backfill_facts_from_vectors
    docker exec voxbridge-api python -m src.database.backfill_facts_from_vectors --dry-run
"""

import asyncio
import argparse
import uuid
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import UserFact, User, Agent
from src.database.session import get_db_session
from src.config.logging_config import get_logger

logger = get_logger(__name__)


async def backfill_orphaned_vectors(dry_run: bool = False):
    """
    Create user_facts entries for vectors that have no corresponding facts.

    Args:
        dry_run: If True, only report what would be done without making changes
    """
    async with get_db_session() as db:
        # Find vectors with no corresponding facts using LEFT JOIN
        # This query finds all user_memories rows where NO user_fact has that vector_id
        # Note: Cast um.id to TEXT for comparison since vector_id is stored as string
        query = text("""
            SELECT
                um.id::TEXT AS vector_id,
                um.payload->>'data' AS fact_text,
                um.payload->>'user_id' AS mem_user_id,
                (um.payload->>'created_at')::timestamp AS vector_created_at
            FROM user_memories um
            LEFT JOIN user_facts uf ON uf.vector_id = um.id::TEXT
            WHERE uf.id IS NULL
            ORDER BY um.id
        """)

        result = await db.execute(query)
        orphaned_vectors = result.fetchall()

        if not orphaned_vectors:
            logger.info("✅ No orphaned vectors found! user_memories and user_facts are in sync.")
            return

        logger.info(f"🔍 Found {len(orphaned_vectors)} orphaned vectors (no corresponding user_facts)")

        if dry_run:
            logger.info("🔬 DRY RUN MODE - No changes will be made")
            logger.info("\nOrphaned vectors that would be backfilled:")
            for vec in orphaned_vectors:
                fact_text = vec.fact_text or "(no data field)"
                logger.info(f"  • vector_id={vec.vector_id[:8]}... text=\"{fact_text[:60]}...\"")
            return

        # Create user_facts entries for each orphaned vector
        created_count = 0
        failed_count = 0

        for vec in orphaned_vectors:
            try:
                # Parse memory user_id to extract user and agent
                # Format: "user_id" (global) or "user_id:agent_id" (agent-specific)
                mem_user_id = vec.mem_user_id
                if not mem_user_id:
                    logger.warning(f"⚠️ Skipping vector {vec.vector_id}: No user_id in payload")
                    failed_count += 1
                    continue

                # Split user_id:agent_id
                if ":" in mem_user_id:
                    user_id_str, agent_id_str = mem_user_id.split(":", 1)
                else:
                    user_id_str = mem_user_id
                    agent_id_str = None

                # Look up user by user_id (Discord ID, etc.)
                user_result = await db.execute(
                    text("SELECT id FROM users WHERE user_id = :user_id"),
                    {"user_id": user_id_str}
                )
                user_row = user_result.fetchone()

                if not user_row:
                    logger.warning(f"⚠️ Skipping vector {vec.vector_id}: User '{user_id_str}' not found in database")
                    failed_count += 1
                    continue

                user_uuid = user_row.id

                # Look up agent if agent_id is present
                agent_uuid = None
                if agent_id_str:
                    try:
                        agent_uuid = uuid.UUID(agent_id_str)
                        # Verify agent exists
                        agent_result = await db.execute(
                            text("SELECT id FROM agents WHERE id = :agent_id"),
                            {"agent_id": str(agent_uuid)}
                        )
                        if not agent_result.fetchone():
                            logger.warning(f"⚠️ Agent {agent_id_str} not found, using NULL")
                            agent_uuid = None
                    except ValueError:
                        logger.warning(f"⚠️ Invalid agent UUID {agent_id_str}, using NULL")
                        agent_uuid = None

                # Extract fact text from payload "data" field
                fact_text = vec.fact_text or ""
                if not fact_text:
                    logger.warning(f"⚠️ Skipping vector {vec.vector_id}: No 'data' field in payload")
                    failed_count += 1
                    continue

                # Create user_fact entry
                # Since we don't have the original fact_key/fact_value breakdown,
                # use generic values and store the full text
                new_fact = UserFact(
                    id=uuid.uuid4(),
                    user_id=user_uuid,
                    agent_id=agent_uuid,
                    vector_id=vec.vector_id,
                    fact_key="backfilled_fact",  # Generic key for backfilled facts
                    fact_value=fact_text[:200],  # Truncate for fact_value (preview)
                    fact_text=fact_text,  # Full text
                    importance=0.5,  # Default importance
                    embedding_provider="local",  # Assume local provider
                    embedding_model="BAAI/bge-large-en-v1.5",  # Default model
                    validity_start=vec.vector_created_at,  # Use vector creation time
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )

                db.add(new_fact)
                await db.commit()

                logger.info(
                    f"✅ Created fact for vector: vector_id={vec.vector_id[:8]}... "
                    f"fact_id={new_fact.id}, user={user_id_str}, text=\"{fact_text[:60]}...\""
                )
                created_count += 1

            except Exception as e:
                logger.error(f"❌ Failed to create fact for vector {vec.vector_id}: {e}")
                failed_count += 1
                await db.rollback()

        logger.info(
            f"\n📊 Backfill complete: {created_count} facts created, "
            f"{failed_count} failures"
        )


async def main():
    """Main entry point for backfill script."""
    parser = argparse.ArgumentParser(description="Backfill user_facts from orphaned Mem0 vectors")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    args = parser.parse_args()

    logger.info("🔄 Starting orphaned vectors backfill...")
    await backfill_orphaned_vectors(dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
