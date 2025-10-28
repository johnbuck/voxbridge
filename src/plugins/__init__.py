"""
VoxBridge Plugin System

Lightweight, extensible plugin architecture for agent capabilities.

Quick Start:
    # 1. Create a plugin
    from src.plugins import PluginBase, plugin

    @plugin("myservice")
    class MyServicePlugin(PluginBase):
        def validate_config(self, config):
            return {'api_key': config['api_key']}

        async def initialize(self, agent, config):
            self.agent = agent
            self.config = config

        async def start(self):
            # Connect to service
            pass

        async def stop(self):
            # Disconnect from service
            pass

    # 2. Plugin is auto-registered and ready to use!

For more details, see:
- base.py: PluginBase abstract class
- registry.py: PluginRegistry and @plugin decorator
- Plugin examples: discord_plugin.py, n8n_plugin.py
"""

from src.plugins.base import PluginBase
from src.plugins.registry import PluginRegistry, plugin, discover_plugins

__all__ = [
    "PluginBase",
    "PluginRegistry",
    "plugin",
    "discover_plugins",
]
