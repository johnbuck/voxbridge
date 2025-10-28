"""
Example: Creating an agent with Discord plugin

This example demonstrates how to create an agent with Discord bot plugin configured.

Usage:
    python examples/discord_plugin_example.py

Requirements:
    - DISCORD_TOKEN_AGENT1 in environment (your Discord bot token)
    - PLUGIN_ENCRYPTION_KEY in environment (for encrypting the token)
"""

import asyncio
import os
from src.services.agent_service import AgentService
from src.services.plugin_manager import get_plugin_manager

async def main():
    """Create an agent with Discord plugin and test initialization"""

    # Get Discord bot token from environment
    bot_token = os.getenv('DISCORD_TOKEN_AGENT1')
    if not bot_token:
        print("❌ DISCORD_TOKEN_AGENT1 environment variable not set")
        print("   Set it to your Discord bot token")
        return

    print("Creating agent with Discord plugin...")

    # Create agent with Discord plugin configuration
    agent = await AgentService.create_agent(
        name="Discord Test Agent",
        system_prompt="You are a helpful Discord voice assistant.",
        temperature=0.7,
        llm_provider="openrouter",
        llm_model="anthropic/claude-3.5-sonnet",
        plugins={
            "discord": {
                "enabled": True,
                "bot_token": bot_token,  # Will be encrypted automatically
                "channels": [],  # Empty = all channels allowed
                "auto_join": True,  # Auto-join voice channels
                "command_prefix": "!"
            }
        }
    )

    print(f"✅ Created agent: {agent.name} (ID: {agent.id})")
    print(f"   Plugins: {list(agent.plugins.keys())}")

    # Initialize plugins for the agent
    plugin_manager = get_plugin_manager()
    results = await plugin_manager.initialize_agent_plugins(agent)

    print(f"\n📊 Plugin initialization results:")
    for plugin_type, success in results.items():
        status = "✅" if success else "❌"
        print(f"   {status} {plugin_type}: {'Success' if success else 'Failed'}")

    # Check if Discord plugin is running
    discord_plugin = plugin_manager.get_plugin(agent.id, "discord")
    if discord_plugin:
        print(f"\n🤖 Discord Plugin Status:")
        bot_info = discord_plugin.get_bot_info()
        print(f"   Connected: {bot_info['connected']}")
        print(f"   Ready: {bot_info['ready']}")
        print(f"   Guilds: {bot_info['guilds']}")
        if bot_info['guild_names']:
            for guild_name in bot_info['guild_names']:
                print(f"     - {guild_name}")

    # Wait a moment for bot to fully connect
    print("\n⏳ Waiting 10 seconds for bot to connect...")
    await asyncio.sleep(10)

    # Check status again
    if discord_plugin:
        bot_info = discord_plugin.get_bot_info()
        print(f"\n🤖 Discord Plugin Status (after 10s):")
        print(f"   Connected: {bot_info['connected']}")
        print(f"   Ready: {bot_info['ready']}")
        print(f"   Guilds: {bot_info['guilds']}")
        print(f"   Voice connections: {bot_info['voice_connections']}")

    # Cleanup
    print("\n🛑 Stopping plugins...")
    await plugin_manager.stop_agent_plugins(agent.id)

    print("✅ Example complete!")


if __name__ == "__main__":
    asyncio.run(main())
