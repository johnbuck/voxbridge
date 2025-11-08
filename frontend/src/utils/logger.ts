/**
 * Tiered Logging System for VoxBridge Frontend
 *
 * Provides a flexible logging system with 5 levels:
 * - TRACE (0): Ultra-verbose debugging (raw data, every iteration)
 * - DEBUG (1): Detailed debugging (checkpoints, state changes)
 * - INFO (2): Standard operational messages (connections, completions)
 * - WARN (3): Warnings (recoverable errors, fallbacks)
 * - ERROR (4): Errors (exceptions, failures)
 *
 * Environment Variables (Vite):
 * - VITE_LOG_LEVEL: Global log level [default: INFO]
 * - VITE_LOG_LEVEL_WEBRTC: Override for WebRTC module (useWebRTCAudio hook)
 * - VITE_LOG_LEVEL_WEBSOCKET: Override for WebSocket connections
 * - VITE_LOG_LEVEL_UI: Override for UI components (pages, components)
 * - VITE_LOG_LEVEL_API: Override for API client
 *
 * Example Usage:
 *   import { createLogger } from '@/utils/logger';
 *
 *   const logger = createLogger('useWebRTCAudio');
 *   logger.trace('🔍 Audio chunk:', chunk);
 *   logger.debug('🎙️ Microphone started');
 *   logger.info('✅ Connected to WebSocket');
 *   logger.warn('⚠️ Reconnecting...');
 *   logger.error('❌ Connection failed:', error);
 */

export const LogLevel = {
  TRACE: 0,
  DEBUG: 1,
  INFO: 2,
  WARN: 3,
  ERROR: 4,
} as const;

export type LogLevel = typeof LogLevel[keyof typeof LogLevel];

// Module name mapping: Component name → Logical service name
const MODULE_NAME_MAP: Record<string, string> = {
  'useWebRTCAudio': 'webrtc',
  'VoxbridgePage': 'ui',
  'AgentsPage': 'ui',
  'SettingsPage': 'ui',
  'api': 'api',
  'websocket': 'websocket',
};

/**
 * Parse log level string to enum value
 */
function parseLogLevel(level: string | undefined): LogLevel {
  if (!level) return LogLevel.INFO;

  const levelMap: Record<string, LogLevel> = {
    'TRACE': LogLevel.TRACE,
    'DEBUG': LogLevel.DEBUG,
    'INFO': LogLevel.INFO,
    'WARN': LogLevel.WARN,
    'WARNING': LogLevel.WARN,
    'ERROR': LogLevel.ERROR,
  };

  return levelMap[level.toUpperCase()] ?? LogLevel.INFO;
}

/**
 * Get log level for a module, checking both module-specific and global env vars
 */
function getLogLevel(moduleName: string): LogLevel {
  // Map module name to logical service name
  const logicalName = MODULE_NAME_MAP[moduleName] || moduleName;

  // Check module-specific env var first (e.g., VITE_LOG_LEVEL_WEBRTC)
  const moduleEnvVar = `VITE_LOG_LEVEL_${logicalName.toUpperCase()}`;
  const moduleLevel = import.meta.env[moduleEnvVar];
  if (moduleLevel) {
    return parseLogLevel(moduleLevel);
  }

  // Check global VITE_LOG_LEVEL env var
  const globalLevel = import.meta.env.VITE_LOG_LEVEL;
  if (globalLevel) {
    return parseLogLevel(globalLevel);
  }

  // Default to INFO
  return LogLevel.INFO;
}

/**
 * Logger class with level filtering and console output
 */
export class Logger {
  private moduleName: string;
  private logLevel: LogLevel;

  constructor(moduleName: string) {
    this.moduleName = moduleName;
    this.logLevel = getLogLevel(moduleName);
  }

  /**
   * Check if a log level is enabled
   */
  isEnabledFor(level: LogLevel): boolean {
    return level >= this.logLevel;
  }

  /**
   * Log a TRACE message (most verbose)
   */
  trace(message: string, ...args: any[]): void {
    if (this.isEnabledFor(LogLevel.TRACE)) {
      console.log(`[${this.moduleName}] [TRACE]`, message, ...args);
    }
  }

  /**
   * Log a DEBUG message
   */
  debug(message: string, ...args: any[]): void {
    if (this.isEnabledFor(LogLevel.DEBUG)) {
      console.log(`[${this.moduleName}] [DEBUG]`, message, ...args);
    }
  }

  /**
   * Log an INFO message (default level)
   */
  info(message: string, ...args: any[]): void {
    if (this.isEnabledFor(LogLevel.INFO)) {
      console.info(`[${this.moduleName}] [INFO]`, message, ...args);
    }
  }

  /**
   * Log a WARN message
   */
  warn(message: string, ...args: any[]): void {
    if (this.isEnabledFor(LogLevel.WARN)) {
      console.warn(`[${this.moduleName}] [WARN]`, message, ...args);
    }
  }

  /**
   * Log an ERROR message
   */
  error(message: string, ...args: any[]): void {
    if (this.isEnabledFor(LogLevel.ERROR)) {
      console.error(`[${this.moduleName}] [ERROR]`, message, ...args);
    }
  }

  /**
   * Get current log level for this logger
   */
  getLevel(): LogLevel {
    return this.logLevel;
  }

  /**
   * Get log level name as string
   */
  getLevelName(): string {
    // Create reverse mapping from value to name
    const levelNames: Record<number, string> = {
      [LogLevel.TRACE]: 'TRACE',
      [LogLevel.DEBUG]: 'DEBUG',
      [LogLevel.INFO]: 'INFO',
      [LogLevel.WARN]: 'WARN',
      [LogLevel.ERROR]: 'ERROR',
    };
    return levelNames[this.logLevel] || 'UNKNOWN';
  }
}

/**
 * Create a logger for a module
 *
 * @param moduleName - Name of the module (e.g., 'useWebRTCAudio', 'VoxbridgePage')
 * @returns Logger instance configured for the module
 *
 * @example
 * const logger = createLogger('useWebRTCAudio');
 * logger.debug('🎙️ Microphone started');
 */
export function createLogger(moduleName: string): Logger {
  return new Logger(moduleName);
}

/**
 * Initialize logging system and log configuration
 * Call this once at application startup (e.g., in App.tsx)
 */
export function initializeLogging(): void {
  const globalLevel = import.meta.env.VITE_LOG_LEVEL || 'INFO';
  console.info(`🚀 Frontend logging initialized (global level: ${globalLevel})`);

  // Log module-specific overrides if any
  const overrides: string[] = [];
  for (const [_moduleName, logicalName] of Object.entries(MODULE_NAME_MAP)) {
    const envVar = `VITE_LOG_LEVEL_${logicalName.toUpperCase()}`;
    const override = import.meta.env[envVar];
    if (override) {
      overrides.push(`${logicalName.toUpperCase()}=${override}`);
    }
  }

  if (overrides.length > 0) {
    console.info(`📋 Module overrides: ${overrides.join(', ')}`);
  }
}
