"""
Agent Service Layer

Business logic for managing AI agents in VoxBridge 2.0.
Provides CRUD operations with validation and database interaction.
"""

import logging
from typing import List, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Agent
from src.database.session import get_db_session
from src.plugins.encryption import PluginEncryption, PluginEncryptionError

logger = logging.getLogger(__name__)


class AgentService:
    """Service for managing AI agents"""

    @staticmethod
    async def create_agent(
        name: str,
        system_prompt: str,
        temperature: float = 0.7,
        llm_provider: str = "openrouter",
        llm_model: str = "anthropic/claude-3.5-sonnet",
        use_n8n: bool = False,
        n8n_webhook_url: Optional[str] = None,
        is_default: bool = False,
        tts_voice: Optional[str] = None,
        tts_exaggeration: float = 1.0,
        tts_cfg_weight: float = 0.7,
        tts_temperature: float = 0.3,
        tts_language: str = "en",
        filter_actions_for_tts: bool = False,
        plugins: Optional[dict] = None,
    ) -> Agent:
        """
        Create a new agent.

        Args:
            name: Agent display name
            system_prompt: System prompt for the agent
            temperature: LLM temperature (0.0-1.0)
            llm_provider: LLM provider ('openrouter' or 'local')
            llm_model: Model identifier
            use_n8n: Use n8n webhook instead of direct LLM (DEPRECATED - use plugins)
            n8n_webhook_url: Per-agent n8n webhook URL (DEPRECATED - use plugins)
            is_default: Mark as default agent
            tts_voice: TTS voice ID (optional)
            tts_exaggeration: TTS emotion intensity (0.25-2.0)
            tts_cfg_weight: TTS speech pace (0.0-1.0)
            tts_temperature: TTS voice sampling (0.05-5.0)
            tts_language: TTS language code (e.g., 'en', 'es', 'fr')
            plugins: Plugin configurations (dict mapping plugin_type -> config)

        Returns:
            Created Agent instance

        Raises:
            ValueError: If validation fails
        """
        # Validation
        if not name or len(name) > 100:
            raise ValueError("Agent name must be 1-100 characters")
        if not system_prompt or len(system_prompt) > 10000:
            raise ValueError("System prompt must be 1-10000 characters")
        if not 0.0 <= temperature <= 1.0:
            raise ValueError("Temperature must be between 0.0 and 1.0")
        if llm_provider not in ["openrouter", "local"]:
            raise ValueError("LLM provider must be 'openrouter' or 'local'")
        if not 0.25 <= tts_exaggeration <= 2.0:
            raise ValueError("TTS exaggeration must be between 0.25 and 2.0")
        if not 0.0 <= tts_cfg_weight <= 1.0:
            raise ValueError("TTS cfg_weight must be between 0.0 and 1.0")
        if not 0.05 <= tts_temperature <= 5.0:
            raise ValueError("TTS temperature must be between 0.05 and 5.0")

        # Encrypt sensitive plugin fields
        encrypted_plugins = {}
        if plugins:
            for plugin_type, plugin_config in plugins.items():
                try:
                    encrypted_plugins[plugin_type] = PluginEncryption.encrypt_config(
                        plugin_type, plugin_config
                    )
                except PluginEncryptionError as e:
                    logger.warning(f"⚠️ Could not encrypt {plugin_type} plugin config: {e}")
                    # Fall back to unencrypted if encryption fails (e.g., key not configured)
                    encrypted_plugins[plugin_type] = plugin_config

        async with get_db_session() as session:
            # If setting as default, unset any existing default
            if is_default:
                result = await session.execute(
                    select(Agent).where(Agent.is_default == True)
                )
                existing_defaults = result.scalars().all()
                for existing_default in existing_defaults:
                    existing_default.is_default = False

            # Create agent with encrypted plugins
            agent = Agent(
                name=name,
                system_prompt=system_prompt,
                temperature=temperature,
                llm_provider=llm_provider,
                llm_model=llm_model,
                use_n8n=use_n8n,
                n8n_webhook_url=n8n_webhook_url,
                is_default=is_default,
                tts_voice=tts_voice,
                tts_exaggeration=tts_exaggeration,
                tts_cfg_weight=tts_cfg_weight,
                tts_temperature=tts_temperature,
                tts_language=tts_language,
                filter_actions_for_tts=filter_actions_for_tts,
                plugins=encrypted_plugins,
            )

            session.add(agent)
            await session.commit()
            await session.refresh(agent)

        # NEW Phase 4 Batch 1: Initialize plugins if enabled
        if plugins:
            logger.info(f"🔌 Initializing plugins for new agent '{agent.name}'...")
            from src.services.plugin_manager import get_plugin_manager

            plugin_manager = get_plugin_manager()

            try:
                results = await plugin_manager.initialize_agent_plugins(agent)

                for plugin_type, success in results.items():
                    status = "✅" if success else "❌"
                    logger.info(f"  {status} {plugin_type}: {'Success' if success else 'Failed'}")

                # Invalidate default agent cache
                plugin_manager.invalidate_agent_cache()

            except Exception as e:
                logger.error(f"❌ Plugin initialization failed for agent '{agent.name}': {e}", exc_info=True)
                # Don't rollback agent creation - plugins can be initialized later

        logger.info(f"✅ Created agent: {agent.name} (ID: {agent.id})")

        return agent

    @staticmethod
    async def get_all_agents() -> List[Agent]:
        """
        Get all agents.

        Returns:
            List of all Agent instances
        """
        async with get_db_session() as session:
            result = await session.execute(select(Agent).order_by(Agent.created_at))
            agents = result.scalars().all()
            return list(agents)

    @staticmethod
    async def get_agent(agent_id: UUID) -> Optional[Agent]:
        """
        Get agent by ID.

        Args:
            agent_id: Agent UUID

        Returns:
            Agent instance or None if not found
        """
        async with get_db_session() as session:
            result = await session.execute(select(Agent).where(Agent.id == agent_id))
            agent = result.scalar_one_or_none()
            return agent

    @staticmethod
    async def get_agent_by_name(name: str) -> Optional[Agent]:
        """
        Get agent by name.

        Args:
            name: Agent name

        Returns:
            Agent instance or None if not found
        """
        async with get_db_session() as session:
            result = await session.execute(select(Agent).where(Agent.name == name))
            agent = result.scalar_one_or_none()
            return agent

    @staticmethod
    async def update_agent(
        agent_id: UUID,
        name: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        use_n8n: Optional[bool] = None,
        n8n_webhook_url: Optional[str] = None,
        is_default: Optional[bool] = None,
        tts_voice: Optional[str] = None,
        tts_exaggeration: Optional[float] = None,
        tts_cfg_weight: Optional[float] = None,
        tts_temperature: Optional[float] = None,
        tts_language: Optional[str] = None,
        filter_actions_for_tts: Optional[bool] = None,
        memory_scope: Optional[str] = None,
        plugins: Optional[dict] = None,
    ) -> Optional[Agent]:
        """
        Update agent fields.

        Phase 4 Batch 1: Restarts plugins if plugin config changed

        Args:
            agent_id: Agent UUID
            name: New agent name (optional)
            system_prompt: New system prompt (optional)
            temperature: New temperature (optional)
            llm_provider: New LLM provider (optional)
            llm_model: New LLM model (optional)
            tts_voice: New TTS voice (optional)
            tts_exaggeration: New TTS exaggeration (optional)
            tts_cfg_weight: New TTS cfg_weight (optional)
            tts_temperature: New TTS temperature (optional)
            tts_language: New TTS language (optional)
            memory_scope: New memory scope ('global' or 'agent') (optional)
            plugins: New plugin configurations (optional)

        Returns:
            Updated Agent instance or None if not found

        Raises:
            ValueError: If validation fails
        """
        async with get_db_session() as session:
            result = await session.execute(select(Agent).where(Agent.id == agent_id))
            agent = result.scalar_one_or_none()

            if not agent:
                return None

            # Update fields with validation
            if name is not None:
                if not name or len(name) > 100:
                    raise ValueError("Agent name must be 1-100 characters")
                agent.name = name

            if system_prompt is not None:
                if not system_prompt or len(system_prompt) > 10000:
                    raise ValueError("System prompt must be 1-10000 characters")
                agent.system_prompt = system_prompt

            if temperature is not None:
                if not 0.0 <= temperature <= 1.0:
                    raise ValueError("Temperature must be between 0.0 and 1.0")
                agent.temperature = temperature

            if llm_provider is not None:
                if llm_provider not in ["openrouter", "local"]:
                    raise ValueError("LLM provider must be 'openrouter' or 'local'")
                agent.llm_provider = llm_provider

            if llm_model is not None:
                agent.llm_model = llm_model

            if use_n8n is not None:
                agent.use_n8n = use_n8n

            if n8n_webhook_url is not None:
                agent.n8n_webhook_url = n8n_webhook_url

            if is_default is not None:
                # If setting as default, unset any existing default
                if is_default:
                    result = await session.execute(
                        select(Agent).where(Agent.is_default == True, Agent.id != agent_id)
                    )
                    existing_defaults = result.scalars().all()
                    for existing_default in existing_defaults:
                        existing_default.is_default = False
                agent.is_default = is_default

            if tts_voice is not None:
                agent.tts_voice = tts_voice

            if tts_exaggeration is not None:
                if not 0.25 <= tts_exaggeration <= 2.0:
                    raise ValueError("TTS exaggeration must be between 0.25 and 2.0")
                agent.tts_exaggeration = tts_exaggeration

            if tts_cfg_weight is not None:
                if not 0.0 <= tts_cfg_weight <= 1.0:
                    raise ValueError("TTS cfg_weight must be between 0.0 and 1.0")
                agent.tts_cfg_weight = tts_cfg_weight

            if tts_temperature is not None:
                if not 0.05 <= tts_temperature <= 5.0:
                    raise ValueError("TTS temperature must be between 0.05 and 5.0")
                agent.tts_temperature = tts_temperature

            if tts_language is not None:
                agent.tts_language = tts_language

            if filter_actions_for_tts is not None:
                agent.filter_actions_for_tts = filter_actions_for_tts

            if memory_scope is not None:
                if memory_scope not in ["global", "agent"]:
                    raise ValueError("Memory scope must be 'global' or 'agent'")
                agent.memory_scope = memory_scope

            # NEW Phase 4 Batch 1: Handle plugin config updates
            plugins_changed = False
            if plugins is not None:
                # Encrypt sensitive plugin fields before updating
                encrypted_plugins = {}
                for plugin_type, plugin_config in plugins.items():
                    try:
                        encrypted_plugins[plugin_type] = PluginEncryption.encrypt_config(
                            plugin_type, plugin_config
                        )
                    except PluginEncryptionError as e:
                        logger.warning(f"⚠️ Could not encrypt {plugin_type} plugin config: {e}")
                        # Fall back to unencrypted if encryption fails
                        encrypted_plugins[plugin_type] = plugin_config

                agent.plugins = encrypted_plugins
                plugins_changed = True

            await session.commit()
            await session.refresh(agent)

        # NEW Phase 4 Batch 1: Restart plugins if config changed
        if plugins_changed:
            logger.info(f"🔄 Plugin config changed for agent '{agent.name}' - restarting plugins...")
            from src.services.plugin_manager import get_plugin_manager

            plugin_manager = get_plugin_manager()

            try:
                # Stop existing plugins
                stop_results = await plugin_manager.stop_agent_plugins(agent.id)
                for plugin_type, success in stop_results.items():
                    logger.info(f"  🛑 Stopped {plugin_type}: {'Success' if success else 'Failed'}")

                # Reinitialize with new config
                init_results = await plugin_manager.initialize_agent_plugins(agent)
                for plugin_type, success in init_results.items():
                    status = "✅" if success else "❌"
                    logger.info(f"  {status} Restarted {plugin_type}: {'Success' if success else 'Failed'}")

                # Invalidate default agent cache
                plugin_manager.invalidate_agent_cache()

            except Exception as e:
                logger.error(f"❌ Plugin restart failed for agent '{agent.name}': {e}", exc_info=True)

        return agent

    @staticmethod
    async def get_default_agent() -> Optional[Agent]:
        """
        Get the default agent.

        Returns:
            Default Agent instance or None if no default set
        """
        async with get_db_session() as session:
            result = await session.execute(select(Agent).where(Agent.is_default == True))
            agent = result.scalar_one_or_none()
            return agent

    @staticmethod
    async def set_default_agent(agent_id: UUID) -> Optional[Agent]:
        """
        Mark agent as default (unsets any existing default).

        Args:
            agent_id: Agent UUID to set as default

        Returns:
            Updated Agent instance or None if not found
        """
        async with get_db_session() as session:
            # Get the agent to set as default
            result = await session.execute(select(Agent).where(Agent.id == agent_id))
            agent = result.scalar_one_or_none()

            if not agent:
                return None

            # Unset any existing defaults
            result = await session.execute(
                select(Agent).where(Agent.is_default == True, Agent.id != agent_id)
            )
            existing_defaults = result.scalars().all()
            for existing_default in existing_defaults:
                existing_default.is_default = False

            # Set this agent as default
            agent.is_default = True

            await session.commit()
            await session.refresh(agent)

            return agent

    @staticmethod
    async def delete_agent(agent_id: UUID) -> bool:
        """
        Delete agent by ID.

        Phase 4 Batch 1: Invalidates default agent cache

        Args:
            agent_id: Agent UUID

        Returns:
            True if deleted, False if not found
        """
        async with get_db_session() as session:
            result = await session.execute(select(Agent).where(Agent.id == agent_id))
            agent = result.scalar_one_or_none()

            if not agent:
                return False

            await session.delete(agent)
            await session.commit()

        # NEW Phase 4 Batch 1: Invalidate default agent cache after deletion
        from src.services.plugin_manager import get_plugin_manager

        plugin_manager = get_plugin_manager()
        plugin_manager.invalidate_agent_cache()

        return True
