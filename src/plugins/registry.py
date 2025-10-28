"""
VoxBridge Plugin Registry

Global registry for plugin types (like Flask blueprints).
Plugins self-register using the @plugin decorator.

Usage:
    from src.plugins.registry import plugin

    @plugin("discord")
    class DiscordPlugin(PluginBase):
        ...

    # Plugin is now registered and discoverable
    PluginRegistry.get_plugin("discord")  # Returns DiscordPlugin class
"""

from typing import Dict, List, Type, Optional
import logging

logger = logging.getLogger(__name__)


class PluginRegistry:
    """
    Global registry for VoxBridge plugins.

    Plugins self-register via the @plugin decorator.
    This allows third-party plugins to be added without modifying core code.

    Design Pattern: Similar to Flask blueprints, FastAPI routers, or pytest plugins.
    """

    _plugins: Dict[str, Type] = {}
    _initialized: bool = False

    @classmethod
    def register(cls, plugin_class: Type) -> None:
        """
        Register a plugin type.

        Args:
            plugin_class: Plugin class (must inherit from PluginBase)

        Raises:
            ValueError: If plugin_type already registered or invalid

        Example:
            class DiscordPlugin(PluginBase):
                plugin_type = "discord"
                ...

            PluginRegistry.register(DiscordPlugin)
        """
        # Validate plugin class
        if not hasattr(plugin_class, 'plugin_type'):
            raise ValueError(
                f"Plugin class {plugin_class.__name__} must define 'plugin_type' attribute"
            )

        plugin_type = plugin_class.plugin_type

        # Check for duplicate registration
        if plugin_type in cls._plugins:
            existing_class = cls._plugins[plugin_type]
            if existing_class != plugin_class:
                logger.warning(
                    f"⚠️ Plugin type '{plugin_type}' already registered "
                    f"({existing_class.__name__}), overriding with {plugin_class.__name__}"
                )

        # Register plugin
        cls._plugins[plugin_type] = plugin_class
        logger.info(f"🔌 Registered plugin: {plugin_type} ({plugin_class.__name__})")

    @classmethod
    def unregister(cls, plugin_type: str) -> bool:
        """
        Unregister a plugin type.

        Args:
            plugin_type: Plugin type to unregister

        Returns:
            bool: True if plugin was registered and removed, False otherwise
        """
        if plugin_type in cls._plugins:
            del cls._plugins[plugin_type]
            logger.info(f"🔌 Unregistered plugin: {plugin_type}")
            return True
        return False

    @classmethod
    def get_plugin(cls, plugin_type: str) -> Optional[Type]:
        """
        Get plugin class by type.

        Args:
            plugin_type: Plugin type identifier (e.g., "discord", "n8n")

        Returns:
            Plugin class or None if not found

        Example:
            plugin_class = PluginRegistry.get_plugin("discord")
            if plugin_class:
                plugin = plugin_class()
                config = plugin.validate_config(config_dict)
        """
        return cls._plugins.get(plugin_type)

    @classmethod
    def list_plugins(cls) -> List[str]:
        """
        List all registered plugin types.

        Returns:
            List of plugin type strings

        Example:
            plugins = PluginRegistry.list_plugins()
            # ['discord', 'n8n', 'slack', 'telegram']
        """
        return list(cls._plugins.keys())

    @classmethod
    def get_all_plugins(cls) -> Dict[str, Type]:
        """
        Get all registered plugins.

        Returns:
            Dict mapping plugin_type -> plugin_class

        Example:
            for plugin_type, plugin_class in PluginRegistry.get_all_plugins().items():
                print(f"{plugin_type}: {plugin_class.__name__}")
        """
        return dict(cls._plugins)

    @classmethod
    def is_registered(cls, plugin_type: str) -> bool:
        """
        Check if plugin type is registered.

        Args:
            plugin_type: Plugin type to check

        Returns:
            bool: True if registered, False otherwise
        """
        return plugin_type in cls._plugins

    @classmethod
    def clear(cls) -> None:
        """
        Clear all registered plugins.

        WARNING: This is mainly for testing. Use with caution.
        """
        cls._plugins.clear()
        logger.warning("🔌 Cleared all plugin registrations")


def plugin(plugin_type: str):
    """
    Decorator to register a plugin class.

    This decorator:
    1. Sets the plugin_type attribute on the class
    2. Registers the class in PluginRegistry
    3. Returns the unmodified class

    Args:
        plugin_type: Unique plugin type identifier (e.g., "discord", "n8n")

    Returns:
        Decorator function

    Example:
        @plugin("discord")
        class DiscordPlugin(PluginBase):
            def validate_config(self, config):
                ...

        @plugin("slack")
        class SlackPlugin(PluginBase):
            def validate_config(self, config):
                ...

    The plugin is automatically registered and discoverable:
        PluginRegistry.get_plugin("discord")  # Returns DiscordPlugin class
        PluginRegistry.list_plugins()  # ['discord', 'slack']
    """
    def decorator(cls):
        # Set plugin_type attribute
        cls.plugin_type = plugin_type

        # Register in global registry
        PluginRegistry.register(cls)

        # Return unmodified class (no wrapper)
        return cls

    return decorator


# Auto-discovery helper (optional)
def discover_plugins(package_name: str = "src.plugins") -> int:
    """
    Auto-discover and import plugins from a package.

    This function imports all Python modules in a package, which triggers
    @plugin decorators to register plugins.

    Args:
        package_name: Python package to scan (default: "src.plugins")

    Returns:
        int: Number of plugins discovered

    Example:
        # In your application startup:
        from src.plugins.registry import discover_plugins
        discovered = discover_plugins("src.plugins")
        print(f"Discovered {discovered} plugins")

    Note: This requires plugins to be in separate .py files that can be imported.
    """
    import importlib
    import pkgutil

    try:
        package = importlib.import_module(package_name)
    except ImportError:
        logger.warning(f"⚠️ Could not import package {package_name} for plugin discovery")
        return 0

    before_count = len(PluginRegistry.list_plugins())

    # Import all submodules (triggers @plugin decorators)
    for importer, modname, ispkg in pkgutil.walk_packages(
        path=package.__path__,
        prefix=package.__name__ + ".",
    ):
        try:
            importlib.import_module(modname)
        except Exception as e:
            logger.error(f"❌ Error importing plugin module {modname}: {e}")

    after_count = len(PluginRegistry.list_plugins())
    discovered = after_count - before_count

    if discovered > 0:
        logger.info(f"🔌 Discovered {discovered} plugins in {package_name}")

    return discovered
