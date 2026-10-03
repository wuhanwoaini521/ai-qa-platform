import React from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, Inbox } from 'lucide-react';

interface LoadingStateProps {
  label?: string;
}

/** Loading: a quiet, three-line skeleton. It never spins and never jumps the layout. */
export const LoadingState: React.FC<LoadingStateProps> = ({ label }) => {
  const { t } = useTranslation('common');
  return (
    <div className="async-state" role="status" aria-live="polite">
      <div className="skeleton-stack" aria-hidden="true">
        <div className="skeleton skeleton-title" />
        <div className="skeleton skeleton-line" />
        <div className="skeleton skeleton-line" style={{ width: '68%' }} />
      </div>
      <span>{label ?? t('loading')}</span>
    </div>
  );
};

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export const ErrorState: React.FC<ErrorStateProps> = ({ title, message, onRetry }) => {
  const { t } = useTranslation('common');
  return (
    <div className="async-state async-state-error" role="alert">
      <span className="async-state-icon">
        <AlertTriangle size={18} strokeWidth={1.7} aria-hidden="true" />
      </span>
      <div className="async-state-title">{title ?? t('errorTitle')}</div>
      <div className="async-state-message">{message}</div>
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
  title?: string;
  description?: string;
  icon?: React.ReactNode;
  actionLabel?: string;
  onAction?: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  message,
  title,
  description,
  icon,
  actionLabel,
  onAction,
}) => (
  <div className="async-state">
    <span className="async-state-icon">{icon ?? <Inbox size={18} strokeWidth={1.7} />}</span>
    {title && <div className="async-state-title">{title}</div>}
    <div className="async-state-message">{title ? (description ?? message) : message}</div>
    {actionLabel && onAction && (
      <button type="button" className="btn btn-secondary" onClick={onAction}>
        {actionLabel}
      </button>
    )}
  </div>
);
