/**
 * Service Status Indicator Component
 * VoxBridge 2.0 - Frontend Error Handling
 *
 * Displays real-time health status for backend services.
 */

import { AlertCircle, CheckCircle, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';

export type ServiceStatus = 'healthy' | 'warning' | 'error';

export interface ServiceStatusIndicatorProps {
  serviceName: string;
  status: ServiceStatus;
  lastError?: string;
  className?: string;
  showText?: boolean;
}

export function ServiceStatusIndicator({
  serviceName,
  status,
  lastError,
  className,
  showText = true,
}: ServiceStatusIndicatorProps) {
  const getStatusConfig = () => {
    switch (status) {
      case 'healthy':
        return {
          icon: CheckCircle,
          color: 'text-green-500',
          bgColor: 'bg-green-500/10',
          borderColor: 'border-green-500/20',
          statusText: 'Operational',
        };
      case 'warning':
        return {
          icon: AlertTriangle,
          color: 'text-yellow-500',
          bgColor: 'bg-yellow-500/10',
          borderColor: 'border-yellow-500/20',
          statusText: 'Degraded',
        };
      case 'error':
        return {
          icon: AlertCircle,
          color: 'text-red-500',
          bgColor: 'bg-red-500/10',
          borderColor: 'border-red-500/20',
          statusText: 'Error',
        };
    }
  };

  const config = getStatusConfig();
  const Icon = config.icon;

  return (
    <div
      className={cn(
        'inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 transition-colors',
        config.bgColor,
        config.borderColor,
        className
      )}
      title={lastError || `${serviceName} - ${config.statusText}`}
    >
      <Icon className={cn('h-4 w-4', config.color)} />

      {showText && (
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{serviceName}</span>

          {lastError && (
            <span className="text-xs text-muted-foreground truncate max-w-[120px]">
              {lastError}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

// Mini variant for compact displays
export function ServiceStatusDot({
  status,
  className,
  size = 'sm',
}: {
  status: ServiceStatus;
  className?: string;
  size?: 'xs' | 'sm' | 'md';
}) {
  const sizeClasses = {
    xs: 'h-2 w-2',
    sm: 'h-3 w-3',
    md: 'h-4 w-4',
  };

  const colorClasses = {
    healthy: 'bg-green-500',
    warning: 'bg-yellow-500',
    error: 'bg-red-500',
  };

  return (
    <div
      className={cn(
        'rounded-full',
        sizeClasses[size],
        colorClasses[status],
        status !== 'healthy' && 'animate-pulse',
        className
      )}
    />
  );
}
