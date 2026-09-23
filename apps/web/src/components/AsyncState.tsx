import React from 'react';

const blockStyle: React.CSSProperties = {
  padding: '32px',
  textAlign: 'center',
  color: 'var(--text-muted)',
  fontSize: '13px',
};

interface LoadingStateProps {
  label?: string;
}

export const LoadingState: React.FC<LoadingStateProps> = ({ label = 'Loading...' }) => (
  <div style={blockStyle}>{label}</div>
);

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export const ErrorState: React.FC<ErrorStateProps> = ({ title = 'Something went wrong', message, onRetry }) => (
  <div style={{ ...blockStyle, color: 'var(--danger-color, #ef4444)' }}>
    <div style={{ fontWeight: 600, marginBottom: '6px' }}>{title}</div>
    <div style={{ marginBottom: onRetry ? '12px' : 0 }}>{message}</div>
    {onRetry && (
      <button type="button" className="btn btn-secondary" onClick={onRetry}>
        Retry
      </button>
    )}
  </div>
);

interface EmptyStateProps {
  message: string;
  actionLabel?: string;
  onAction?: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({ message, actionLabel, onAction }) => (
  <div style={blockStyle}>
    <div style={{ marginBottom: actionLabel ? '12px' : 0 }}>{message}</div>
    {actionLabel && onAction && (
      <button type="button" className="btn btn-secondary" onClick={onAction}>
        {actionLabel}
      </button>
    )}
  </div>
);
