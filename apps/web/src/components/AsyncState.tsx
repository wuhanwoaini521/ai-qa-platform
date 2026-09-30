import React from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, Inbox, LoaderCircle } from 'lucide-react';

interface LoadingStateProps {
  label?: string;
}

export const LoadingState: React.FC<LoadingStateProps> = ({ label }) => {
  const { t } = useTranslation('common');
  return (
    <div className="async-state" role="status" aria-live="polite">
      <LoaderCircle className="spin" size={20} aria-hidden="true" />
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
      <AlertTriangle size={20} aria-hidden="true" />
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
  actionLabel?: string;
  onAction?: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({ message, actionLabel, onAction }) => (
  <div className="async-state">
    <Inbox size={22} aria-hidden="true" />
    <div className="async-state-message">{message}</div>
    {actionLabel && onAction && (
      <button type="button" className="btn btn-secondary" onClick={onAction}>
        {actionLabel}
      </button>
    )}
  </div>
);
