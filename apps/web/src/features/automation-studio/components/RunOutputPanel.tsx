import React from 'react';
import { useTranslation } from 'react-i18next';

interface RunOutputPanelProps {
  lastRunResult: string | null;
  runId?: string | null;
  onNavigateToRuns?: (runId?: string) => void;
}

export const RunOutputPanel: React.FC<RunOutputPanelProps> = ({ lastRunResult, runId, onNavigateToRuns }) => {
  const { t } = useTranslation('studioPanels');

  if (!lastRunResult) return null;

  return (
    <div
      style={{
        padding: '6px 12px',
        background: 'var(--accent-blue-soft)',
        borderTop: '1px solid var(--line-strong)',
        fontSize: '11px',
        color: 'var(--accent-blue)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}
    >
      <span>{lastRunResult}</span>
      {onNavigateToRuns && (
        <button
          className="btn btn-secondary btn-sm"
          style={{ padding: '2px 6px', fontSize: '10px' }}
          onClick={() => onNavigateToRuns(runId ?? undefined)}
        >
          {t('runOutput.viewInPlatform')}
        </button>
      )}
    </div>
  );
};
