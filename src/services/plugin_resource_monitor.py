"""
Plugin Resource Monitor

Tracks CPU and memory usage for all active plugins.
Enforces resource limits and kills plugins that exceed thresholds.

Design:
- Background monitoring task (samples every N seconds)
- Per-plugin resource tracking
- Configurable limits (CPU %, memory MB)
- Alert system for limit violations
- Graceful plugin termination

Usage:
    monitor = PluginResourceMonitor(
        cpu_limit_percent=50.0,
        memory_limit_mb=500,
        sample_interval=5.0,
        violation_threshold=3
    )

    await monitor.start()
    monitor.register_plugin(agent_id, plugin_type, plugin_instance)

    # Get stats
    stats = monitor.get_stats()

    await monitor.stop()
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
from uuid import UUID
from dataclasses import dataclass, asdict
from datetime import datetime

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None

logger = logging.getLogger(__name__)


@dataclass
class PluginResourceStats:
    """Resource statistics for a single plugin"""
    agent_id: str
    plugin_type: str
    cpu_percent: float  # Current CPU usage (%)
    memory_mb: float  # Current memory usage (MB)
    cpu_peak: float  # Peak CPU usage (%)
    memory_peak: float  # Peak memory usage (MB)
    cpu_avg: float  # Average CPU usage (%)
    memory_avg: float  # Average memory usage (MB)
    sample_count: int  # Number of samples collected
    violations: int  # Number of limit violations
    last_sample_time: float  # Timestamp of last sample
    started_at: float  # When monitoring started

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            **asdict(self),
            'uptime_seconds': time.time() - self.started_at,
            'last_sample_age_seconds': time.time() - self.last_sample_time,
        }


class PluginResourceMonitor:
    """
    Monitor resource usage for all active plugins.

    Features:
    - Background monitoring task
    - Per-plugin CPU/memory tracking
    - Configurable resource limits
    - Violation counting and alerts
    - Automatic plugin termination on sustained violations
    """

    def __init__(
        self,
        cpu_limit_percent: float = 50.0,
        memory_limit_mb: float = 500,
        sample_interval: float = 5.0,
        violation_threshold: int = 3,
    ):
        """
        Initialize resource monitor.

        Args:
            cpu_limit_percent: Max CPU usage per plugin (%)
            memory_limit_mb: Max memory usage per plugin (MB)
            sample_interval: Seconds between samples
            violation_threshold: Violations before killing plugin
        """
        if not PSUTIL_AVAILABLE:
            logger.warning("⚠️ psutil not available - resource monitoring disabled")

        self.cpu_limit = cpu_limit_percent
        self.memory_limit = memory_limit_mb
        self.sample_interval = sample_interval
        self.violation_threshold = violation_threshold

        # Plugin tracking: {(agent_id, plugin_type): stats}
        self.plugin_stats: Dict[tuple, PluginResourceStats] = {}

        # Plugin instances for termination: {(agent_id, plugin_type): plugin}
        self.plugin_instances: Dict[tuple, Any] = {}

        # Background monitoring task
        self.monitor_task: Optional[asyncio.Task] = None
        self.running = False

        # Process tracking
        self.process = psutil.Process() if PSUTIL_AVAILABLE else None

        logger.info(
            f"🔍 PluginResourceMonitor initialized: "
            f"CPU limit={cpu_limit_percent}%, Memory limit={memory_limit_mb}MB, "
            f"Sample interval={sample_interval}s, Violation threshold={violation_threshold}"
        )

    def register_plugin(self, agent_id: UUID, plugin_type: str, plugin_instance: Any) -> None:
        """
        Register a plugin for monitoring.

        Args:
            agent_id: Agent UUID
            plugin_type: Plugin type (e.g., 'discord', 'n8n')
            plugin_instance: Plugin instance (for termination)
        """
        key = (str(agent_id), plugin_type)

        if key in self.plugin_stats:
            logger.warning(f"⚠️ Plugin {plugin_type} for agent {agent_id} already registered")
            return

        self.plugin_stats[key] = PluginResourceStats(
            agent_id=str(agent_id),
            plugin_type=plugin_type,
            cpu_percent=0.0,
            memory_mb=0.0,
            cpu_peak=0.0,
            memory_peak=0.0,
            cpu_avg=0.0,
            memory_avg=0.0,
            sample_count=0,
            violations=0,
            last_sample_time=time.time(),
            started_at=time.time(),
        )

        self.plugin_instances[key] = plugin_instance

        logger.info(f"✅ Registered plugin {plugin_type} for agent {agent_id} for monitoring")

    def unregister_plugin(self, agent_id: UUID, plugin_type: str) -> None:
        """
        Unregister a plugin from monitoring.

        Args:
            agent_id: Agent UUID
            plugin_type: Plugin type
        """
        key = (str(agent_id), plugin_type)

        if key in self.plugin_stats:
            del self.plugin_stats[key]

        if key in self.plugin_instances:
            del self.plugin_instances[key]

        logger.info(f"✅ Unregistered plugin {plugin_type} for agent {agent_id} from monitoring")

    async def start(self) -> None:
        """Start background monitoring task"""
        if not PSUTIL_AVAILABLE:
            logger.warning("⚠️ Cannot start monitoring - psutil not available")
            return

        if self.running:
            logger.warning("⚠️ Resource monitor already running")
            return

        self.running = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())

        logger.info("✅ PluginResourceMonitor started")

    async def stop(self) -> None:
        """Stop background monitoring task"""
        if not self.running:
            return

        self.running = False

        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass

        logger.info("✅ PluginResourceMonitor stopped")

    async def _monitor_loop(self) -> None:
        """Background task that periodically samples plugin resources"""
        logger.info("🔍 Resource monitoring loop started")

        while self.running:
            try:
                await self._sample_all_plugins()
                await asyncio.sleep(self.sample_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Error in monitoring loop: {e}", exc_info=True)
                await asyncio.sleep(self.sample_interval)

        logger.info("🔍 Resource monitoring loop stopped")

    async def _sample_all_plugins(self) -> None:
        """Sample resource usage for all registered plugins"""
        if not PSUTIL_AVAILABLE or not self.process:
            return

        # Sample current process resources
        # Note: In a real implementation, we'd need to track plugin threads/tasks
        # For now, we'll sample overall process and attribute to plugins proportionally
        try:
            cpu_percent = self.process.cpu_percent(interval=0.1)
            memory_info = self.process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)  # Convert bytes to MB
        except Exception as e:
            logger.error(f"❌ Error sampling process resources: {e}")
            return

        # Distribute resources across plugins (simplified - equal distribution)
        num_plugins = len(self.plugin_stats)
        if num_plugins == 0:
            return

        cpu_per_plugin = cpu_percent / num_plugins
        memory_per_plugin = memory_mb / num_plugins

        for key, stats in self.plugin_stats.items():
            await self._update_plugin_stats(key, stats, cpu_per_plugin, memory_per_plugin)

    async def _update_plugin_stats(
        self,
        key: tuple,
        stats: PluginResourceStats,
        cpu_percent: float,
        memory_mb: float
    ) -> None:
        """
        Update statistics for a single plugin.

        Args:
            key: (agent_id, plugin_type) tuple
            stats: Plugin stats object
            cpu_percent: Current CPU usage
            memory_mb: Current memory usage
        """
        # Update current values
        stats.cpu_percent = cpu_percent
        stats.memory_mb = memory_mb
        stats.last_sample_time = time.time()
        stats.sample_count += 1

        # Update peaks
        if cpu_percent > stats.cpu_peak:
            stats.cpu_peak = cpu_percent

        if memory_mb > stats.memory_peak:
            stats.memory_peak = memory_mb

        # Update averages (rolling average)
        stats.cpu_avg = (stats.cpu_avg * (stats.sample_count - 1) + cpu_percent) / stats.sample_count
        stats.memory_avg = (stats.memory_avg * (stats.sample_count - 1) + memory_mb) / stats.sample_count

        # Check for violations
        violation = False

        if cpu_percent > self.cpu_limit:
            logger.warning(
                f"⚠️ Plugin {stats.plugin_type} (agent {stats.agent_id}) "
                f"CPU usage {cpu_percent:.1f}% exceeds limit {self.cpu_limit}%"
            )
            violation = True

        if memory_mb > self.memory_limit:
            logger.warning(
                f"⚠️ Plugin {stats.plugin_type} (agent {stats.agent_id}) "
                f"memory usage {memory_mb:.1f}MB exceeds limit {self.memory_limit}MB"
            )
            violation = True

        if violation:
            stats.violations += 1

            # Kill plugin if violation threshold exceeded
            if stats.violations >= self.violation_threshold:
                await self._kill_plugin(key, stats)

    async def _kill_plugin(self, key: tuple, stats: PluginResourceStats) -> None:
        """
        Terminate a plugin due to resource limit violations.

        Args:
            key: (agent_id, plugin_type) tuple
            stats: Plugin stats object
        """
        agent_id, plugin_type = key

        logger.error(
            f"❌ Killing plugin {plugin_type} (agent {agent_id}) "
            f"due to {stats.violations} resource limit violations"
        )

        # Get plugin instance
        plugin = self.plugin_instances.get(key)

        if plugin:
            try:
                # Stop plugin
                await plugin.stop()
                logger.info(f"✅ Stopped plugin {plugin_type} (agent {agent_id})")
            except Exception as e:
                logger.error(
                    f"❌ Error stopping plugin {plugin_type} (agent {agent_id}): {e}",
                    exc_info=True
                )

        # Unregister from monitoring
        self.unregister_plugin(UUID(agent_id), plugin_type)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get resource statistics for all plugins.

        Returns:
            Dict with overall stats and per-plugin breakdown
        """
        plugin_stats_list = []

        for stats in self.plugin_stats.values():
            plugin_stats_list.append(stats.to_dict())

        # Calculate overall stats
        total_cpu = sum(s.cpu_percent for s in self.plugin_stats.values())
        total_memory = sum(s.memory_mb for s in self.plugin_stats.values())
        total_violations = sum(s.violations for s in self.plugin_stats.values())

        return {
            'enabled': PSUTIL_AVAILABLE and self.running,
            'psutil_available': PSUTIL_AVAILABLE,
            'total_plugins': len(self.plugin_stats),
            'total_cpu_percent': round(total_cpu, 2),
            'total_memory_mb': round(total_memory, 2),
            'total_violations': total_violations,
            'limits': {
                'cpu_percent': self.cpu_limit,
                'memory_mb': self.memory_limit,
                'violation_threshold': self.violation_threshold,
            },
            'plugins': plugin_stats_list,
        }

    def get_plugin_stats(self, agent_id: UUID, plugin_type: str) -> Optional[Dict[str, Any]]:
        """
        Get statistics for a specific plugin.

        Args:
            agent_id: Agent UUID
            plugin_type: Plugin type

        Returns:
            Plugin stats dict or None if not found
        """
        key = (str(agent_id), plugin_type)
        stats = self.plugin_stats.get(key)

        if stats:
            return stats.to_dict()

        return None


# Singleton instance
_resource_monitor_instance: Optional[PluginResourceMonitor] = None


def get_resource_monitor() -> PluginResourceMonitor:
    """
    Get singleton PluginResourceMonitor instance.

    Returns:
        PluginResourceMonitor: Shared monitor instance

    Example:
        from src.services.plugin_resource_monitor import get_resource_monitor

        monitor = get_resource_monitor()
        await monitor.start()
    """
    global _resource_monitor_instance

    if _resource_monitor_instance is None:
        _resource_monitor_instance = PluginResourceMonitor()
        logger.info("🔍 Created singleton PluginResourceMonitor instance")

    return _resource_monitor_instance
