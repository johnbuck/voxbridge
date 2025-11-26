/**
 * useMemoryExtractionStatus Hook
 *
 * Monitors memory extraction task status via WebSocket events.
 * Provides real-time updates for queued, processing, completed, and failed extraction tasks.
 */

import { useEffect, useState, useCallback, useRef } from 'react';

export interface ExtractionTaskStatus {
  task_id: string;
  user_id: string;
  agent_id: string;
  status: 'queued' | 'processing' | 'completed' | 'failed' | 'retrying';
  attempts?: number;
  facts_count?: number;
  error?: string;
  timestamp: number;
}

export interface UseMemoryExtractionStatusOptions {
  /** WebSocket URL (default: ws://localhost:4900/ws/events) */
  wsUrl?: string;
  /** Callback when extraction starts processing */
  onProcessing?: (task: ExtractionTaskStatus) => void;
  /** Callback when extraction completes successfully */
  onCompleted?: (task: ExtractionTaskStatus) => void;
  /** Callback when extraction fails */
  onFailed?: (task: ExtractionTaskStatus) => void;
  /** Auto-reconnect on WebSocket disconnect */
  autoReconnect?: boolean;
  /** Reconnect delay in milliseconds (default: 2000) */
  reconnectDelay?: number;
}

export interface UseMemoryExtractionStatusReturn {
  /** Map of task_id → task status */
  tasks: Map<string, ExtractionTaskStatus>;
  /** Get status of specific task by ID */
  getTaskStatus: (taskId: string) => ExtractionTaskStatus | undefined;
  /** Clear completed tasks from memory */
  clearCompleted: () => void;
  /** Clear all tasks from memory */
  clearAll: () => void;
  /** WebSocket connection status */
  isConnected: boolean;
  /** Last connection error */
  connectionError: string | null;
}

const DEFAULT_WS_URL = 'ws://localhost:4900/ws/events';

export function useMemoryExtractionStatus(
  options: UseMemoryExtractionStatusOptions = {}
): UseMemoryExtractionStatusReturn {
  const {
    wsUrl = DEFAULT_WS_URL,
    onProcessing,
    onCompleted,
    onFailed,
    autoReconnect = true,
    reconnectDelay = 2000
  } = options;

  const [tasks, setTasks] = useState<Map<string, ExtractionTaskStatus>>(new Map());
  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Get task status by ID
  const getTaskStatus = useCallback((taskId: string) => {
    return tasks.get(taskId);
  }, [tasks]);

  // Clear completed tasks
  const clearCompleted = useCallback(() => {
    setTasks((prevTasks) => {
      const newTasks = new Map(prevTasks);
      for (const [taskId, task] of newTasks.entries()) {
        if (task.status === 'completed') {
          newTasks.delete(taskId);
        }
      }
      return newTasks;
    });
  }, []);

  // Clear all tasks
  const clearAll = useCallback(() => {
    setTasks(new Map());
  }, []);

  // Update or add task
  const updateTask = useCallback((taskData: Partial<ExtractionTaskStatus> & { task_id: string }) => {
    setTasks((prevTasks) => {
      const newTasks = new Map(prevTasks);
      const existing = newTasks.get(taskData.task_id);

      const updated: ExtractionTaskStatus = {
        task_id: taskData.task_id,
        user_id: taskData.user_id || existing?.user_id || '',
        agent_id: taskData.agent_id || existing?.agent_id || '',
        status: taskData.status || existing?.status || 'queued',
        attempts: taskData.attempts ?? existing?.attempts,
        facts_count: taskData.facts_count ?? existing?.facts_count,
        error: taskData.error ?? existing?.error,
        timestamp: Date.now()
      };

      newTasks.set(taskData.task_id, updated);

      // Trigger callbacks
      if (updated.status === 'processing' && onProcessing) {
        onProcessing(updated);
      }
      if (updated.status === 'completed' && onCompleted) {
        onCompleted(updated);
      }
      if ((updated.status === 'failed' || updated.status === 'retrying') && onFailed) {
        onFailed(updated);
      }

      return newTasks;
    });
  }, [onProcessing, onCompleted, onFailed]);

  // FIX: Store updateTask in ref to prevent WebSocket reconnections
  const updateTaskRef = useRef(updateTask);

  // Update ref when callback changes (prevents stale closure bug)
  useEffect(() => {
    updateTaskRef.current = updateTask;
  }, [updateTask]);

  // WebSocket connection logic
  useEffect(() => {
    const connect = () => {
      try {
        console.log(`🔌 Connecting to WebSocket: ${wsUrl}`);
        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
          console.log('✅ WebSocket connected');
          setIsConnected(true);
          setConnectionError(null);
        };

        ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            const { event: eventType, data } = message;

            // Handle memory extraction events
            // FIX: Use ref to prevent stale closure and WebSocket reconnections
            if (eventType === 'memory_extraction_queued') {
              console.log(`📋 Memory extraction queued: ${data.task_id}`);
              updateTaskRef.current({
                task_id: data.task_id,
                user_id: data.user_id,
                agent_id: data.agent_id,
                status: 'queued'
              });
            } else if (eventType === 'memory_extraction_processing') {
              console.log(`⚙️ Memory extraction processing: ${data.task_id}`);
              updateTaskRef.current({
                task_id: data.task_id,
                user_id: data.user_id,
                agent_id: data.agent_id,
                status: 'processing',
                attempts: data.attempts
              });
            } else if (eventType === 'memory_extraction_completed') {
              console.log(`✅ Memory extraction completed: ${data.task_id} (${data.facts_count} facts)`);
              updateTaskRef.current({
                task_id: data.task_id,
                user_id: data.user_id,
                agent_id: data.agent_id,
                status: 'completed',
                facts_count: data.facts_count
              });
            } else if (eventType === 'memory_extraction_failed') {
              console.log(`❌ Memory extraction failed: ${data.task_id} (${data.error})`);
              updateTaskRef.current({
                task_id: data.task_id,
                user_id: data.user_id,
                agent_id: data.agent_id,
                status: data.status === 'retrying' ? 'retrying' : 'failed',
                attempts: data.attempts,
                error: data.error
              });
            }
          } catch (error) {
            console.error('❌ Error parsing WebSocket message:', error);
          }
        };

        ws.onerror = (error) => {
          console.error('❌ WebSocket error:', error);
          setConnectionError('WebSocket connection error');
        };

        ws.onclose = () => {
          console.log('🔌 WebSocket disconnected');
          setIsConnected(false);
          wsRef.current = null;

          // Auto-reconnect
          if (autoReconnect) {
            console.log(`🔄 Reconnecting in ${reconnectDelay}ms...`);
            reconnectTimeoutRef.current = setTimeout(connect, reconnectDelay);
          }
        };

        wsRef.current = ws;
      } catch (error) {
        console.error('❌ Error creating WebSocket:', error);
        setConnectionError('Failed to create WebSocket connection');
      }
    };

    connect();

    // Cleanup on unmount
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
    // FIX: Removed updateTask from deps - now using updateTaskRef to prevent reconnections
  }, [wsUrl, autoReconnect, reconnectDelay]);

  return {
    tasks,
    getTaskStatus,
    clearCompleted,
    clearAll,
    isConnected,
    connectionError
  };
}
