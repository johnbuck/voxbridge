"""
Configure Default Agent with Discord Plugin

Adds Discord plugin configuration to the "Auren (Default)" agent.
"""
import asyncio
import os
from src.database import get_async_session, Agent

async def configure_discord_plugin():
    """Add Discord plugin configuration to default agent"""

    # Plugin configuration
    discord_config = {
        "discord": {
            "enabled": True,
            "bot_token": os.getenv("DISCORD_TOKEN"),  # Read from environment
            "auto_join": False,
            "channels": [],
            "command_prefix": "!"
        }
    }

    async with get_async_session() as session:
        # Find default agent
        from sqlalchemy import select
        result = await session.execute(
            select(Agent).where(Agent.name == "Auren (Default)")
        )
        agent = result.scalar_one_or_none()

        if not agent:
            print("❌ Default agent 'Auren (Default)' not found")
            return

        # Update plugins
        agent.plugins = discord_config
        await session.commit()
        await session.refresh(agent)

        print(f"✅ Configured Discord plugin for agent: {agent.name}")
        print(f"   Agent ID: {agent.id}")
        print(f"   Plugins: {agent.plugins}")

if __name__ == "__main__":
    asyncio.run(configure_discord_plugin())
