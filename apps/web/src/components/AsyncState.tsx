import React from 'react';
import { useTranslation } from 'react-i18next';

const blockStyle: React.CSSProperties = {
  padding: '32px',
  textAlign: 'center',
  color: 'var(--text-muted)',
  fontSize: '13px',
};

interface LoadingStateProps {
  label?: string;
}

export const LoadingState: React.FC<LoadingStateProps> = ({ label }) => {
  const { t } = useTranslation('common');
  return <div style={blockStyle}>{label ?? t('loading')}</div>;
};

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export const ErrorState: React.FC<ErrorStateProps> = ({ title, message, onRetry }) => {
  const { t } = useTranslation('common');
  return (
    <div style={{ ...blockStyle, color: 'var(--danger-color, #ef4444)' }}>
      <div style={{ fontWeight: 600, marginBottom: '6px' }}>{title ?? t('errorTitle')}</div>
      <div style={{ marginBottom: onRetry ? '12px' : 0 }}>{message}</div>
      {onRetry && (
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          {t('retry')}
        </button>
      )}
    </div>
  );
};

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
