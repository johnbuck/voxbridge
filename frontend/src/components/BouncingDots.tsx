import React from 'react';

interface BouncingDotsProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

/**
 * BouncingDots Component
 *
 * Displays three animated bouncing dots to indicate loading/processing state.
 * Used in speech bubbles to show streaming transcript activity.
 *
 * @param size - Size variant: 'sm' (1.5rem), 'md' (2rem), 'lg' (3rem)
 * @param className - Additional CSS classes for customization
 */
export const BouncingDots: React.FC<BouncingDotsProps> = ({
  size = 'md',
  className = ''
}) => {
  const sizeClasses = {
    sm: 'w-1.5 h-1.5',
    md: 'w-2 h-2',
    lg: 'w-3 h-3'
  };

  const dotClass = `${sizeClasses[size]} rounded-full bg-current`;

  return (
    <div className={`flex items-center gap-1 ${className}`}>
      <div
        className={`${dotClass} animate-bounce`}
        style={{
          animationDelay: '0ms',
          animationDuration: '1s',
          animationIterationCount: 'infinite'
        }}
      />
      <div
        className={`${dotClass} animate-bounce`}
        style={{
          animationDelay: '150ms',
          animationDuration: '1s',
          animationIterationCount: 'infinite'
        }}
      />
      <div
        className={`${dotClass} animate-bounce`}
        style={{
          animationDelay: '300ms',
          animationDuration: '1s',
          animationIterationCount: 'infinite'
        }}
      />
    </div>
  );
};
