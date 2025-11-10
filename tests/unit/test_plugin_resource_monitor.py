"""
Unit tests for PluginResourceMonitor

Tests resource monitoring, CPU/memory tracking, violation detection,
plugin termination, and statistics reporting.
"""
from __future__ import annotations

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from uuid import uuid4
from dataclasses import asdict

# Import monitor components
from src.services.plugin_resource_monitor import (
    PluginResourceMonitor,
    PluginResourceStats,
    PSUTIL_AVAILABLE,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def agent_id():
    """Generate a test agent UUID"""
    return uuid4()


@pytest.fixture
def plugin_type():
    """Default plugin type for testing"""
    return "discord"


@pytest.fixture
def mock_plugin():
    """Mock plugin instance with stop() method"""
    plugin = MagicMock()
    plugin.stop = AsyncMock()
    plugin.running = True
    return plugin


@pytest.fixture
def mock_process():
    """Mock psutil.Process for resource sampling"""
    process = MagicMock()

    # Mock cpu_percent() method
    process.cpu_percent = MagicMock(return_value=25.5)

    # Mock memory_info() method
    memory_info = MagicMock()
    memory_info.rss = 100 * 1024 * 1024  # 100 MB in bytes
    process.memory_info = MagicMock(return_value=memory_info)

    return process


@pytest.fixture
def monitor(mock_process):
    """Create PluginResourceMonitor with default settings"""
    with patch('src.services.plugin_resource_monitor.psutil') as mock_psutil:
        mock_psutil.Process = MagicMock(return_value=mock_process)

        # Force PSUTIL_AVAILABLE to True for testing
        with patch('src.services.plugin_resource_monitor.PSUTIL_AVAILABLE', True):
            monitor = PluginResourceMonitor(
                cpu_limit_percent=50.0,
                memory_limit_mb=500,
                sample_interval=0.1,  # Fast sampling for tests
                violation_threshold=3,
            )
            yield monitor


@pytest.fixture
def monitor_without_psutil():
    """Create PluginResourceMonitor without psutil available"""
    with patch('src.services.plugin_resource_monitor.PSUTIL_AVAILABLE', False):
        monitor = PluginResourceMonitor()
        yield monitor


# ============================================================
# Test Initialization
# ============================================================

class TestInitialization:
    """Test monitor initialization with various configurations"""

    @pytest.mark.unit
    def test_init_with_default_parameters(self, mock_process):
        """Test monitor initialization with default parameters"""
        with patch('src.services.plugin_resource_monitor.psutil') as mock_psutil:
            mock_psutil.Process = MagicMock(return_value=mock_process)

            with patch('src.services.plugin_resource_monitor.PSUTIL_AVAILABLE', True):
                monitor = PluginResourceMonitor()

                # Verify default values
                assert monitor.cpu_limit == 50.0
                assert monitor.memory_limit == 500
                assert monitor.sample_interval == 5.0
                assert monitor.violation_threshold == 3
                assert monitor.running is False
                assert monitor.monitor_task is None
                assert len(monitor.plugin_stats) == 0
                assert len(monitor.plugin_instances) == 0

    @pytest.mark.unit
    def test_init_with_custom_parameters(self, mock_process):
        """Test monitor initialization with custom parameters"""
        with patch('src.services.plugin_resource_monitor.psutil') as mock_psutil:
            mock_psutil.Process = MagicMock(return_value=mock_process)

            with patch('src.services.plugin_resource_monitor.PSUTIL_AVAILABLE', True):
                monitor = PluginResourceMonitor(
                    cpu_limit_percent=75.0,
                    memory_limit_mb=1000,
                    sample_interval=10.0,
                    violation_threshold=5,
                )

                # Verify custom values
                assert monitor.cpu_limit == 75.0
                assert monitor.memory_limit == 1000
                assert monitor.sample_interval == 10.0
                assert monitor.violation_threshold == 5

    @pytest.mark.unit
    def test_init_without_psutil(self, monitor_without_psutil):
        """Test monitor initialization without psutil available"""
        monitor = monitor_without_psutil

        # Verify psutil-related attributes
        assert monitor.process is None
        assert monitor.running is False

        # Monitor should still initialize successfully (graceful degradation)
        assert monitor.cpu_limit == 50.0
        assert monitor.memory_limit == 500


# ============================================================
# Test Plugin Registration
# ============================================================

class TestPluginRegistration:
    """Test plugin registration and unregistration"""

    @pytest.mark.unit
    def test_register_plugin_adds_to_tracking(self, monitor, agent_id, plugin_type, mock_plugin):
        """Test register_plugin() adds plugin to tracking"""
        monitor.register_plugin(agent_id, plugin_type, mock_plugin)

        key = (str(agent_id), plugin_type)

        # Verify plugin is tracked
        assert key in monitor.plugin_stats
        assert key in monitor.plugin_instances
        assert monitor.plugin_instances[key] is mock_plugin

        # Verify stats initialized
        stats = monitor.plugin_stats[key]
        assert stats.agent_id == str(agent_id)
        assert stats.plugin_type == plugin_type
        assert stats.cpu_percent == 0.0
        assert stats.memory_mb == 0.0
        assert stats.cpu_peak == 0.0
        assert stats.memory_peak == 0.0
        assert stats.cpu_avg == 0.0
        assert stats.memory_avg == 0.0
        assert stats.sample_count == 0
        assert stats.violations == 0

    @pytest.mark.unit
    def test_unregister_plugin_removes_from_tracking(self, monitor, agent_id, plugin_type, mock_plugin):
        """Test unregister_plugin() removes plugin from tracking"""
        # First register
        monitor.register_plugin(agent_id, plugin_type, mock_plugin)

        key = (str(agent_id), plugin_type)
        assert key in monitor.plugin_stats

        # Then unregister
        monitor.unregister_plugin(agent_id, plugin_type)

        # Verify removed
        assert key not in monitor.plugin_stats
        assert key not in monitor.plugin_instances

    @pytest.mark.unit
    def test_register_same_plugin_twice_warns(self, monitor, agent_id, plugin_type, mock_plugin, caplog):
        """Test registering same plugin twice logs warning"""
        # Register once
        monitor.register_plugin(agent_id, plugin_type, mock_plugin)

        # Register again
        with caplog.at_level('WARNING'):
            monitor.register_plugin(agent_id, plugin_type, mock_plugin)

        # Verify warning logged
        assert "already registered" in caplog.text

    @pytest.mark.unit
    def test_register_multiple_plugins(self, monitor, mock_plugin):
        """Test registering multiple plugins"""
        agent1 = uuid4()
        agent2 = uuid4()

        monitor.register_plugin(agent1, "discord", mock_plugin)
        monitor.register_plugin(agent2, "n8n", mock_plugin)
        monitor.register_plugin(agent1, "slack", mock_plugin)

        # Verify all tracked
        assert len(monitor.plugin_stats) == 3
        assert (str(agent1), "discord") in monitor.plugin_stats
        assert (str(agent2), "n8n") in monitor.plugin_stats
        assert (str(agent1), "slack") in monitor.plugin_stats


# ============================================================
# Test Monitoring Lifecycle
# ============================================================

class TestMonitoringLifecycle:
    """Test start/stop monitoring lifecycle"""

    @pytest.mark.asyncio
    async def test_start_creates_monitoring_task(self, monitor):
        """Test start() starts background monitoring task"""
        await monitor.start()

        # Verify monitor is running
        assert monitor.running is True
        assert monitor.monitor_task is not None
        assert not monitor.monitor_task.done()

        # Cleanup
        await monitor.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_monitoring_task(self, monitor):
        """Test stop() stops background monitoring task"""
        await monitor.start()
        assert monitor.running is True

        await monitor.stop()

        # Verify monitor stopped
        assert monitor.running is False

        # Task should be cancelled
        if monitor.monitor_task:
            assert monitor.monitor_task.cancelled() or monitor.monitor_task.done()

    @pytest.mark.asyncio
    async def test_start_when_already_running_warns(self, monitor, caplog):
        """Test start() when already running logs warning"""
        await monitor.start()

        # Try to start again
        with caplog.at_level('WARNING'):
            await monitor.start()

        # Verify warning logged
        assert "already running" in caplog.text

        # Cleanup
        await monitor.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_running_is_safe(self, monitor):
        """Test stop() when not running is safe (no error)"""
        # Stop without starting (should be safe)
        await monitor.stop()

        # Verify no error and state is correct
        assert monitor.running is False

    @pytest.mark.asyncio
    async def test_start_without_psutil_warns(self, monitor_without_psutil, caplog):
        """Test start() without psutil available logs warning"""
        with caplog.at_level('WARNING'):
            await monitor_without_psutil.start()

        # Verify warning logged
        assert "psutil not available" in caplog.text
        assert monitor_without_psutil.running is False


# ============================================================
# Test Resource Sampling
# ============================================================

class TestResourceSampling:
    """Test resource sampling and statistics updates"""

    @pytest.mark.asyncio
    async def test_sample_all_plugins_collects_stats(self, monitor, agent_id, plugin_type, mock_plugin, mock_process):
        """Test _sample_all_plugins() collects CPU/memory stats"""
        # Register plugin
        monitor.register_plugin(agent_id, plugin_type, mock_plugin)

        # Mock process to return specific values
        mock_process.cpu_percent.return_value = 30.5
        memory_info = MagicMock()
        memory_info.rss = 200 * 1024 * 1024  # 200 MB
        mock_process.memory_info.return_value = memory_info

        # Sample resources
        await monitor._sample_all_plugins()

        # Verify stats updated
        key = (str(agent_id), plugin_type)
        stats = monitor.plugin_stats[key]

        assert stats.sample_count == 1
        assert stats.cpu_percent == 30.5
        assert stats.memory_mb == 200.0
        assert stats.cpu_peak == 30.5
        assert stats.memory_peak == 200.0

    @pytest.mark.asyncio
    async def test_update_plugin_stats_calculates_averages(self, monitor, agent_id, plugin_type, mock_plugin):
        """Test _update_plugin_stats() updates current/peak/average values"""
        # Register plugin
        monitor.register_plugin(agent_id, plugin_type, mock_plugin)

        key = (str(agent_id), plugin_type)
        stats = monitor.plugin_stats[key]

        # Simulate multiple samples
        await monitor._update_plugin_stats(key, stats, 20.0, 100.0)
        await monitor._update_plugin_stats(key, stats, 40.0, 150.0)
        await monitor._update_plugin_stats(key, stats, 30.0, 125.0)

        # Verify current values
        assert stats.cpu_percent == 30.0
        assert stats.memory_mb == 125.0

        # Verify peak values
        assert stats.cpu_peak == 40.0
        assert stats.memory_peak == 150.0

        # Verify average values
        assert stats.cpu_avg == pytest.approx(30.0, rel=0.01)  # (20+40+30)/3
        assert stats.memory_avg == pytest.approx(125.0, rel=0.01)  # (100+150+125)/3

        # Verify sample count
        assert stats.sample_count == 3

    @pytest.mark.asyncio
    async def test_cpu_violation_detection(self, monitor, agent_id, plugin_type, mock_plugin, caplog):
        """Test resource limit violation detection (CPU)"""
        # Register plugin
        monitor.register_plugin(agent_id, plugin_type, mock_plugin)

        key = (str(agent_id), plugin_type)
        stats = monitor.plugin_stats[key]

        # CPU exceeds limit (50%)
        with caplog.at_level('WARNING'):
            await monitor._update_plugin_stats(key, stats, 75.0, 100.0)

        # Verify violation logged and counted
        assert "CPU usage" in caplog.text
        assert "exceeds limit" in caplog.text
        assert stats.violations == 1

    @pytest.mark.asyncio
    async def test_memory_violation_detection(self, monitor, agent_id, plugin_type, mock_plugin, caplog):
        """Test resource limit violation detection (memory)"""
        # Register plugin
        monitor.register_plugin(agent_id, plugin_type, mock_plugin)

        key = (str(agent_id), plugin_type)
        stats = monitor.plugin_stats[key]

        # Memory exceeds limit (500 MB)
        with caplog.at_level('WARNING'):
            await monitor._update_plugin_stats(key, stats, 25.0, 750.0)

        # Verify violation logged and counted
        assert "memory usage" in caplog.text
        assert "exceeds limit" in caplog.text
        assert stats.violations == 1

    @pytest.mark.asyncio
    async def test_violation_counting(self, monitor, agent_id, plugin_type, mock_plugin):
        """Test violation counting over multiple samples"""
        # Register plugin
        monitor.register_plugin(agent_id, plugin_type, mock_plugin)

        key = (str(agent_id), plugin_type)
        stats = monitor.plugin_stats[key]

        # Multiple violations
        await monitor._update_plugin_stats(key, stats, 75.0, 100.0)  # CPU violation
        await monitor._update_plugin_stats(key, stats, 80.0, 600.0)  # Both violations

        # Verify violations counted
        assert stats.violations == 3  # 1 CPU + 2 (CPU + memory)

    @pytest.mark.asyncio
    async def test_sampling_with_no_plugins(self, monitor, mock_process):
        """Test monitoring with no plugins registered"""
        # Sample with no plugins (should not error)
        await monitor._sample_all_plugins()

        # Verify no stats created
        assert len(monitor.plugin_stats) == 0

    @pytest.mark.asyncio
    async def test_sampling_with_multiple_plugins(self, monitor, mock_plugin, mock_process):
        """Test monitoring with multiple plugins"""
        agent1 = uuid4()
        agent2 = uuid4()

        # Register multiple plugins
        monitor.register_plugin(agent1, "discord", mock_plugin)
        monitor.register_plugin(agent2, "n8n", mock_plugin)

        # Mock process resources
        mock_process.cpu_percent.return_value = 60.0
        memory_info = MagicMock()
        memory_info.rss = 400 * 1024 * 1024  # 400 MB
        mock_process.memory_info.return_value = memory_info

        # Sample resources
        await monitor._sample_all_plugins()

        # Verify resources distributed across plugins
        key1 = (str(agent1), "discord")
        key2 = (str(agent2), "n8n")

        stats1 = monitor.plugin_stats[key1]
        stats2 = monitor.plugin_stats[key2]

        # Each plugin gets half (2 plugins)
        assert stats1.cpu_percent == 30.0  # 60 / 2
        assert stats1.memory_mb == 200.0   # 400 / 2
        assert stats2.cpu_percent == 30.0
        assert stats2.memory_mb == 200.0


# ============================================================
# Test Plugin Termination
# ============================================================

class TestPluginTermination:
    """Test plugin termination due to violations"""

    @pytest.mark.asyncio
    async def test_kill_plugin_after_threshold_violations(self, monitor, agent_id, plugin_type, mock_plugin, caplog):
        """Test _kill_plugin() stops plugin after threshold violations"""
        # Register plugin
        monitor.register_plugin(agent_id, plugin_type, mock_plugin)

        key = (str(agent_id), plugin_type)
        stats = monitor.plugin_stats[key]

        # Trigger violations until threshold (3)
        await monitor._update_plugin_stats(key, stats, 100.0, 1000.0)
        await monitor._update_plugin_stats(key, stats, 100.0, 1000.0)

        # Verify not killed yet
        assert key in monitor.plugin_stats
        assert mock_plugin.stop.call_count == 0

        # One more violation triggers kill
        with caplog.at_level('ERROR'):
            await monitor._update_plugin_stats(key, stats, 100.0, 1000.0)

        # Verify plugin killed
        assert "Killing plugin" in caplog.text
        assert mock_plugin.stop.call_count == 1

        # Verify unregistered
        assert key not in monitor.plugin_stats
        assert key not in monitor.plugin_instances

    @pytest.mark.asyncio
    async def test_plugin_unregistration_after_being_killed(self, monitor, agent_id, plugin_type, mock_plugin):
        """Test plugin unregistration after being killed"""
        # Register plugin
        monitor.register_plugin(agent_id, plugin_type, mock_plugin)

        key = (str(agent_id), plugin_type)
        stats = monitor.plugin_stats[key]

        # Set violations to threshold
        stats.violations = 3

        # Trigger kill
        await monitor._kill_plugin(key, stats)

        # Verify plugin removed from tracking
        assert key not in monitor.plugin_stats
        assert key not in monitor.plugin_instances

    @pytest.mark.asyncio
    async def test_error_handling_when_stopping_plugin_fails(self, monitor, agent_id, plugin_type, caplog):
        """Test error handling when stopping plugin fails"""
        # Create plugin with failing stop()
        failing_plugin = MagicMock()
        failing_plugin.stop = AsyncMock(side_effect=Exception("Stop failed"))

        # Register plugin
        monitor.register_plugin(agent_id, plugin_type, failing_plugin)

        key = (str(agent_id), plugin_type)
        stats = monitor.plugin_stats[key]

        # Trigger kill
        with caplog.at_level('ERROR'):
            await monitor._kill_plugin(key, stats)

        # Verify error logged
        assert "Error stopping plugin" in caplog.text
        assert "Stop failed" in caplog.text

        # Verify plugin still unregistered despite error
        assert key not in monitor.plugin_stats
        assert key not in monitor.plugin_instances


# ============================================================
# Test Statistics
# ============================================================

class TestStatistics:
    """Test statistics reporting"""

    @pytest.mark.asyncio
    async def test_get_stats_returns_overall_statistics(self, monitor, agent_id, plugin_type, mock_plugin):
        """Test get_stats() returns correct overall statistics"""
        # Register plugin
        monitor.register_plugin(agent_id, plugin_type, mock_plugin)

        key = (str(agent_id), plugin_type)
        stats = monitor.plugin_stats[key]

        # Update stats
        await monitor._update_plugin_stats(key, stats, 30.0, 200.0)

        # Get overall stats
        overall = monitor.get_stats()

        # Verify structure
        assert 'enabled' in overall
        assert 'psutil_available' in overall
        assert 'total_plugins' in overall
        assert 'total_cpu_percent' in overall
        assert 'total_memory_mb' in overall
        assert 'total_violations' in overall
        assert 'limits' in overall
        assert 'plugins' in overall

        # Verify values
        assert overall['total_plugins'] == 1
        assert overall['total_cpu_percent'] == 30.0
        assert overall['total_memory_mb'] == 200.0
        assert overall['total_violations'] == 0

        # Verify limits
        assert overall['limits']['cpu_percent'] == 50.0
        assert overall['limits']['memory_mb'] == 500
        assert overall['limits']['violation_threshold'] == 3

    @pytest.mark.asyncio
    async def test_get_plugin_stats_returns_per_plugin_statistics(self, monitor, agent_id, plugin_type, mock_plugin):
        """Test get_plugin_stats() returns per-plugin statistics"""
        # Register plugin
        monitor.register_plugin(agent_id, plugin_type, mock_plugin)

        key = (str(agent_id), plugin_type)
        stats = monitor.plugin_stats[key]

        # Update stats
        await monitor._update_plugin_stats(key, stats, 30.0, 200.0)

        # Get plugin-specific stats
        plugin_stats = monitor.get_plugin_stats(agent_id, plugin_type)

        # Verify structure
        assert plugin_stats is not None
        assert 'agent_id' in plugin_stats
        assert 'plugin_type' in plugin_stats
        assert 'cpu_percent' in plugin_stats
        assert 'memory_mb' in plugin_stats
        assert 'cpu_peak' in plugin_stats
        assert 'memory_peak' in plugin_stats
        assert 'cpu_avg' in plugin_stats
        assert 'memory_avg' in plugin_stats
        assert 'sample_count' in plugin_stats
        assert 'violations' in plugin_stats
        assert 'uptime_seconds' in plugin_stats
        assert 'last_sample_age_seconds' in plugin_stats

        # Verify values
        assert plugin_stats['agent_id'] == str(agent_id)
        assert plugin_stats['plugin_type'] == plugin_type
        assert plugin_stats['cpu_percent'] == 30.0
        assert plugin_stats['memory_mb'] == 200.0

    @pytest.mark.unit
    def test_get_plugin_stats_returns_none_for_unknown_plugin(self, monitor):
        """Test get_plugin_stats() returns None for unknown plugin"""
        unknown_agent = uuid4()

        stats = monitor.get_plugin_stats(unknown_agent, "unknown_plugin")

        assert stats is None

    @pytest.mark.asyncio
    async def test_stats_calculation_with_multiple_plugins(self, monitor, mock_plugin):
        """Test stats calculation (totals, averages, etc.) with multiple plugins"""
        agent1 = uuid4()
        agent2 = uuid4()

        # Register multiple plugins
        monitor.register_plugin(agent1, "discord", mock_plugin)
        monitor.register_plugin(agent2, "n8n", mock_plugin)

        # Update stats
        key1 = (str(agent1), "discord")
        key2 = (str(agent2), "n8n")

        stats1 = monitor.plugin_stats[key1]
        stats2 = monitor.plugin_stats[key2]

        await monitor._update_plugin_stats(key1, stats1, 30.0, 200.0)
        await monitor._update_plugin_stats(key2, stats2, 20.0, 150.0)

        # Trigger violations on one plugin
        stats1.violations = 2

        # Get overall stats
        overall = monitor.get_stats()

        # Verify totals
        assert overall['total_plugins'] == 2
        assert overall['total_cpu_percent'] == 50.0  # 30 + 20
        assert overall['total_memory_mb'] == 350.0   # 200 + 150
        assert overall['total_violations'] == 2

        # Verify per-plugin stats in list
        assert len(overall['plugins']) == 2


# ============================================================
# Test Edge Cases
# ============================================================

class TestEdgeCases:
    """Test edge cases and special scenarios"""

    @pytest.mark.unit
    def test_plugin_resource_stats_to_dict_serialization(self):
        """Test PluginResourceStats.to_dict() serialization"""
        stats = PluginResourceStats(
            agent_id="test-agent-id",
            plugin_type="discord",
            cpu_percent=30.5,
            memory_mb=200.0,
            cpu_peak=45.0,
            memory_peak=250.0,
            cpu_avg=35.0,
            memory_avg=220.0,
            sample_count=10,
            violations=2,
            last_sample_time=time.time() - 5.0,  # 5 seconds ago
            started_at=time.time() - 60.0,  # 60 seconds ago
        )

        stats_dict = stats.to_dict()

        # Verify all fields present
        assert 'agent_id' in stats_dict
        assert 'plugin_type' in stats_dict
        assert 'cpu_percent' in stats_dict
        assert 'memory_mb' in stats_dict
        assert 'cpu_peak' in stats_dict
        assert 'memory_peak' in stats_dict
        assert 'cpu_avg' in stats_dict
        assert 'memory_avg' in stats_dict
        assert 'sample_count' in stats_dict
        assert 'violations' in stats_dict
        assert 'last_sample_time' in stats_dict
        assert 'started_at' in stats_dict

        # Verify calculated fields
        assert 'uptime_seconds' in stats_dict
        assert 'last_sample_age_seconds' in stats_dict

        # Verify values
        assert stats_dict['agent_id'] == "test-agent-id"
        assert stats_dict['plugin_type'] == "discord"
        assert stats_dict['cpu_percent'] == 30.5
        assert stats_dict['sample_count'] == 10

        # Verify calculated values are reasonable
        assert stats_dict['uptime_seconds'] >= 60.0
        assert stats_dict['last_sample_age_seconds'] >= 5.0

    @pytest.mark.unit
    def test_uptime_and_last_sample_age_calculations(self):
        """Test uptime and last_sample_age calculations"""
        now = time.time()

        stats = PluginResourceStats(
            agent_id="test-agent",
            plugin_type="discord",
            cpu_percent=0.0,
            memory_mb=0.0,
            cpu_peak=0.0,
            memory_peak=0.0,
            cpu_avg=0.0,
            memory_avg=0.0,
            sample_count=0,
            violations=0,
            last_sample_time=now - 10.0,  # 10 seconds ago
            started_at=now - 120.0,  # 2 minutes ago
        )

        stats_dict = stats.to_dict()

        # Verify uptime is approximately 2 minutes (within 1 second tolerance)
        assert 119.0 <= stats_dict['uptime_seconds'] <= 121.0

        # Verify last_sample_age is approximately 10 seconds (within 1 second tolerance)
        assert 9.0 <= stats_dict['last_sample_age_seconds'] <= 11.0

    @pytest.mark.asyncio
    async def test_monitoring_loop_handles_cancelled_error(self, monitor):
        """Test monitoring loop handles CancelledError gracefully"""
        await monitor.start()

        # Let it run briefly
        await asyncio.sleep(0.2)

        # Stop should cancel task without error
        await monitor.stop()

        # Verify stopped cleanly
        assert monitor.running is False

    @pytest.mark.asyncio
    async def test_monitoring_loop_handles_exceptions(self, monitor, agent_id, plugin_type, mock_plugin, caplog, mock_process):
        """Test monitoring loop handles exceptions and continues"""
        # Register plugin
        monitor.register_plugin(agent_id, plugin_type, mock_plugin)

        # Mock process to raise exception once, then work
        call_count = [0]

        def cpu_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Temporary error")
            return 25.0

        mock_process.cpu_percent.side_effect = cpu_side_effect

        # Start monitoring
        await monitor.start()

        # Let it run and hit the error
        await asyncio.sleep(0.3)

        # Stop monitoring
        with caplog.at_level('ERROR'):
            await monitor.stop()

        # Verify error was logged but monitoring continued
        assert "Error in monitoring loop" in caplog.text or call_count[0] > 1

    @pytest.mark.asyncio
    async def test_sample_all_plugins_without_process(self, monitor_without_psutil):
        """Test _sample_all_plugins() without psutil process (graceful skip)"""
        # Register plugin
        agent_id = uuid4()
        mock_plugin = MagicMock()

        monitor_without_psutil.register_plugin(agent_id, "discord", mock_plugin)

        # Sample without process (should not error)
        await monitor_without_psutil._sample_all_plugins()

        # Verify stats not updated (sample_count still 0)
        key = (str(agent_id), "discord")
        stats = monitor_without_psutil.plugin_stats[key]
        assert stats.sample_count == 0


# ============================================================
# Test Integration Scenarios
# ============================================================

class TestIntegrationScenarios:
    """Test complete integration scenarios"""

    @pytest.mark.asyncio
    async def test_full_monitoring_cycle(self, monitor, agent_id, plugin_type, mock_plugin, mock_process):
        """Test complete monitoring cycle: start -> sample -> stop"""
        # Register plugin
        monitor.register_plugin(agent_id, plugin_type, mock_plugin)

        # Mock process resources
        mock_process.cpu_percent.return_value = 25.0
        memory_info = MagicMock()
        memory_info.rss = 150 * 1024 * 1024  # 150 MB
        mock_process.memory_info.return_value = memory_info

        # Start monitoring
        await monitor.start()

        # Let it sample a few times
        await asyncio.sleep(0.3)

        # Stop monitoring
        await monitor.stop()

        # Verify stats collected
        key = (str(agent_id), plugin_type)
        stats = monitor.plugin_stats[key]

        # Should have sampled at least once
        assert stats.sample_count > 0
        assert stats.cpu_percent > 0 or stats.memory_mb > 0

    @pytest.mark.asyncio
    async def test_violation_and_termination_scenario(self, monitor, agent_id, plugin_type, mock_plugin):
        """Test violation detection and plugin termination scenario"""
        # Register plugin
        monitor.register_plugin(agent_id, plugin_type, mock_plugin)

        key = (str(agent_id), plugin_type)
        stats = monitor.plugin_stats[key]

        # Simulate sustained violations
        for i in range(3):
            await monitor._update_plugin_stats(key, stats, 100.0, 1000.0)

        # Verify plugin was killed
        assert mock_plugin.stop.call_count == 1
        assert key not in monitor.plugin_stats

    @pytest.mark.asyncio
    async def test_multiple_plugins_with_different_violation_rates(self, monitor, mock_plugin):
        """Test multiple plugins with different violation rates"""
        agent1 = uuid4()
        agent2 = uuid4()

        # Register two plugins
        plugin1 = MagicMock()
        plugin1.stop = AsyncMock()
        plugin2 = MagicMock()
        plugin2.stop = AsyncMock()

        monitor.register_plugin(agent1, "discord", plugin1)
        monitor.register_plugin(agent2, "n8n", plugin2)

        key1 = (str(agent1), "discord")
        key2 = (str(agent2), "n8n")

        stats1 = monitor.plugin_stats[key1]
        stats2 = monitor.plugin_stats[key2]

        # Plugin 1: Sustained violations (should be killed)
        for i in range(3):
            await monitor._update_plugin_stats(key1, stats1, 100.0, 1000.0)

        # Plugin 2: Normal usage (should survive)
        for i in range(3):
            await monitor._update_plugin_stats(key2, stats2, 25.0, 150.0)

        # Verify plugin1 killed, plugin2 alive
        assert plugin1.stop.call_count == 1
        assert plugin2.stop.call_count == 0
        assert key1 not in monitor.plugin_stats
        assert key2 in monitor.plugin_stats
