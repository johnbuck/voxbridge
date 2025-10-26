"""
VoxBridge 2.0 - Database Seed Data

Creates example agents for testing and demonstration.

Usage:
    python -m src.database.seed
"""

import asyncio
import uuid
from sqlalchemy import select

from src.database.models import Agent
from src.database.session import get_db_session, init_db


EXAMPLE_AGENTS = [
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
        "name": "Auren (Default)",
        "description": "Friendly and helpful AI assistant with a warm personality",
        "system_prompt": """You are Auren, a friendly and helpful AI assistant. You have a warm, conversational personality and enjoy helping people with their questions and tasks. You speak naturally and can engage in casual conversation while remaining helpful and informative.

Key traits:
- Warm and approachable
- Clear and concise communication
- Helpful and patient
- Knowledgeable across many topics
- Adaptable to user's communication style""",
        "llm_provider": "openrouter",
        "llm_model": "anthropic/claude-3.5-sonnet",
        "temperature": 0.7,
        "tts_voice": "auren_voice",
        "tts_rate": 1.0,
        "tts_pitch": 1.0,
        "is_active": True,
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000002"),
        "name": "TechSupport",
        "description": "Technical support specialist for troubleshooting and debugging",
        "system_prompt": """You are a technical support specialist. You help users troubleshoot technical issues, debug code, and explain complex technical concepts in simple terms. You ask clarifying questions to understand the problem and provide step-by-step solutions.

Key traits:
- Patient and methodical
- Asks diagnostic questions
- Provides clear step-by-step instructions
- Explains technical concepts simply
- Verifies understanding before moving on""",
        "llm_provider": "openrouter",
        "llm_model": "anthropic/claude-3.5-sonnet",
        "temperature": 0.5,  # Lower temperature for more consistent technical answers
        "tts_voice": "auren_voice",
        "tts_rate": 0.95,  # Slightly slower for technical content
        "tts_pitch": 1.0,
        "is_active": True,
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000003"),
        "name": "Creative Writer",
        "description": "Creative writing assistant for stories, poetry, and brainstorming",
        "system_prompt": """You are a creative writing assistant. You help users brainstorm ideas, write stories, poems, and other creative content. You're imaginative, encouraging, and provide constructive feedback. You can adapt your style to match different genres and tones.

Key traits:
- Imaginative and creative
- Encouraging and supportive
- Adaptable to different genres
- Provides specific, actionable feedback
- Asks questions to spark creativity""",
        "llm_provider": "openrouter",
        "llm_model": "anthropic/claude-3.5-sonnet",
        "temperature": 0.9,  # Higher temperature for more creative responses
        "tts_voice": "auren_voice",
        "tts_rate": 1.05,  # Slightly faster for storytelling
        "tts_pitch": 1.0,
        "is_active": True,
    },
]


async def seed_agents():
    """
    Seed the database with example agents.

    This will:
    1. Check if agents already exist
    2. Create agents if they don't exist
    3. Skip if agents already exist (idempotent)
    """
    print("🌱 Seeding database with example agents...")

    # Initialize database schema
    await init_db()

    async with get_db_session() as session:
        # Check if any agents exist
        result = await session.execute(select(Agent))
        existing_agents = result.scalars().all()

        if existing_agents:
            print(f"⚠️  Database already has {len(existing_agents)} agents. Skipping seed.")
            print("   Existing agents:")
            for agent in existing_agents:
                print(f"   - {agent.name} (ID: {agent.id})")
            return

        # Create example agents
        for agent_data in EXAMPLE_AGENTS:
            agent = Agent(**agent_data)
            session.add(agent)
            print(f"✅ Created agent: {agent.name} (ID: {agent.id})")

        # Commit will happen automatically via context manager
        print(f"\n🎉 Successfully seeded {len(EXAMPLE_AGENTS)} agents!")


async def clear_agents():
    """
    Clear all agents from database.

    WARNING: This will delete all agents and their associated sessions/conversations!
    """
    print("⚠️  Clearing all agents from database...")

    async with get_db_session() as session:
        result = await session.execute(select(Agent))
        agents = result.scalars().all()

        if not agents:
            print("   No agents to delete.")
            return

        for agent in agents:
            await session.delete(agent)
            print(f"🗑️  Deleted agent: {agent.name}")

        print(f"\n✅ Cleared {len(agents)} agents from database")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--clear":
        asyncio.run(clear_agents())
    else:
        asyncio.run(seed_agents())
