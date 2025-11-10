"""
Data Migration: Encrypt Existing Plugin Configurations

This script encrypts sensitive fields in existing plugin configurations.
Run this ONCE after deploying the plugin encryption system.

Usage:
    python -m src.database.migrate_encrypt_plugins

Safety:
    - Dry-run mode by default (shows what would be encrypted)
    - Use --apply flag to actually update database
    - Backups are recommended before running with --apply
"""

import asyncio
import logging
import sys
from typing import Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Agent
from src.database.session import get_db_session
from src.plugins.encryption import PluginEncryption, PluginEncryptionError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def check_encryption_key() -> bool:
    """
    Verify PLUGIN_ENCRYPTION_KEY is configured.

    Returns:
        bool: True if key is configured, False otherwise
    """
    try:
        PluginEncryption._get_fernet()
        logger.info("✅ PLUGIN_ENCRYPTION_KEY is configured")
        return True
    except PluginEncryptionError as e:
        logger.error(f"❌ PLUGIN_ENCRYPTION_KEY not configured: {e}")
        logger.error("Set PLUGIN_ENCRYPTION_KEY in .env before running this migration")
        return False


async def migrate_agent_plugins(agent: Agent, dry_run: bool = True) -> Dict[str, Any]:
    """
    Encrypt plugin configurations for a single agent.

    Args:
        agent: Agent model instance
        dry_run: If True, only show what would be encrypted (don't update DB)

    Returns:
        Dict with migration stats for this agent
    """
    stats = {
        'agent_id': str(agent.id),
        'agent_name': agent.name,
        'plugins_found': 0,
        'plugins_encrypted': 0,
        'already_encrypted': 0,
        'errors': [],
    }

    if not agent.plugins:
        logger.info(f"  Agent '{agent.name}' has no plugins - skipping")
        return stats

    stats['plugins_found'] = len(agent.plugins)
    logger.info(f"  Agent '{agent.name}' has {stats['plugins_found']} plugin(s): {list(agent.plugins.keys())}")

    encrypted_plugins = {}

    for plugin_type, plugin_config in agent.plugins.items():
        try:
            # Check if already encrypted
            sensitive_fields = PluginEncryption.SENSITIVE_FIELDS.get(plugin_type, set())
            is_encrypted = False

            for field in sensitive_fields:
                if field in plugin_config:
                    value = plugin_config[field]
                    if PluginEncryption.is_field_encrypted(plugin_type, field, value):
                        is_encrypted = True
                        break

            if is_encrypted:
                logger.info(f"    ✓ Plugin '{plugin_type}' already encrypted")
                stats['already_encrypted'] += 1
                encrypted_plugins[plugin_type] = plugin_config
                continue

            # Encrypt the config
            encrypted_config = PluginEncryption.encrypt_config(plugin_type, plugin_config)
            encrypted_plugins[plugin_type] = encrypted_config

            # Show what was encrypted
            encrypted_fields = []
            for field in sensitive_fields:
                if field in encrypted_config:
                    encrypted_fields.append(field)

            if encrypted_fields:
                logger.info(f"    🔒 Plugin '{plugin_type}' - encrypted fields: {encrypted_fields}")
                stats['plugins_encrypted'] += 1
            else:
                logger.info(f"    ⚠️  Plugin '{plugin_type}' - no sensitive fields found")

        except PluginEncryptionError as e:
            error_msg = f"Failed to encrypt {plugin_type}: {e}"
            logger.error(f"    ❌ {error_msg}")
            stats['errors'].append(error_msg)
            # Keep unencrypted on error
            encrypted_plugins[plugin_type] = plugin_config

    # Update agent if not dry run
    if not dry_run and stats['plugins_encrypted'] > 0:
        agent.plugins = encrypted_plugins
        logger.info(f"    💾 Updated agent '{agent.name}' in database")

    return stats


async def migrate_all_agents(dry_run: bool = True) -> Dict[str, Any]:
    """
    Migrate all agents to use encrypted plugin configurations.

    Args:
        dry_run: If True, only show what would be encrypted (don't update DB)

    Returns:
        Dict with overall migration stats
    """
    overall_stats = {
        'total_agents': 0,
        'agents_with_plugins': 0,
        'total_plugins_encrypted': 0,
        'total_already_encrypted': 0,
        'total_errors': 0,
        'agent_details': [],
    }

    async with get_db_session() as session:
        # Get all agents
        result = await session.execute(select(Agent))
        agents = result.scalars().all()

        overall_stats['total_agents'] = len(agents)
        logger.info(f"📊 Found {len(agents)} agent(s) in database")
        logger.info("")

        if not agents:
            logger.info("No agents found - nothing to migrate")
            return overall_stats

        # Migrate each agent
        for agent in agents:
            agent_stats = await migrate_agent_plugins(agent, dry_run=dry_run)

            if agent_stats['plugins_found'] > 0:
                overall_stats['agents_with_plugins'] += 1
                overall_stats['total_plugins_encrypted'] += agent_stats['plugins_encrypted']
                overall_stats['total_already_encrypted'] += agent_stats['already_encrypted']
                overall_stats['total_errors'] += len(agent_stats['errors'])
                overall_stats['agent_details'].append(agent_stats)

        # Commit changes if not dry run
        if not dry_run:
            await session.commit()
            logger.info("")
            logger.info("✅ Database changes committed")

    return overall_stats


async def main():
    """Main migration entry point"""
    # Check for --apply flag
    dry_run = '--apply' not in sys.argv

    if dry_run:
        logger.info("=" * 80)
        logger.info("🔍 DRY RUN MODE - No database changes will be made")
        logger.info("   Use --apply flag to actually update the database")
        logger.info("=" * 80)
        logger.info("")
    else:
        logger.info("=" * 80)
        logger.info("⚠️  APPLY MODE - Database WILL be updated!")
        logger.info("=" * 80)
        logger.info("")

    # Verify encryption key is configured
    if not await check_encryption_key():
        logger.error("❌ Migration aborted - encryption key not configured")
        sys.exit(1)

    logger.info("")

    # Run migration
    stats = await migrate_all_agents(dry_run=dry_run)

    # Print summary
    logger.info("")
    logger.info("=" * 80)
    logger.info("📊 MIGRATION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total agents: {stats['total_agents']}")
    logger.info(f"Agents with plugins: {stats['agents_with_plugins']}")
    logger.info(f"Plugins encrypted: {stats['total_plugins_encrypted']}")
    logger.info(f"Already encrypted: {stats['total_already_encrypted']}")
    logger.info(f"Errors: {stats['total_errors']}")

    if dry_run and stats['total_plugins_encrypted'] > 0:
        logger.info("")
        logger.info("💡 To apply these changes, run:")
        logger.info("   python -m src.database.migrate_encrypt_plugins --apply")

    if stats['total_errors'] > 0:
        logger.error("")
        logger.error("⚠️  Some plugins failed to encrypt - review errors above")
        sys.exit(1)

    logger.info("=" * 80)


if __name__ == '__main__':
    asyncio.run(main())
