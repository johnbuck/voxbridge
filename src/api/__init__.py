"""
VoxBridge API Module

Provides FastAPI server and related components for VoxBridge 2.0.
Extracted from discord_bot.py as part of Phase 6.4.1 - FastAPI Decoupling.
"""

from src.api.server import app, get_ws_manager, get_metrics_tracker, set_bot_bridge

__all__ = ['app', 'get_ws_manager', 'get_metrics_tracker', 'set_bot_bridge']
