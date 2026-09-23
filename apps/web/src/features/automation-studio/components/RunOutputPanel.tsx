import React from 'react';

interface RunOutputPanelProps {
  lastRunResult: string | null;
  onNavigateToRuns?: (runId?: string) => void;
}

export const RunOutputPanel: React.FC<RunOutputPanelProps> = ({ lastRunResult, onNavigateToRuns }) => {
  if (!lastRunResult) return null;

  return (
    <div
      style={{
        padding: '6px 12px',
        background: '#eff6ff',
        borderTop: '1px solid #bfdbfe',
        fontSize: '11px',
        color: '#1d4ed8',
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
          onClick={() => onNavigateToRuns()}
        >
          View in Execution Platform
        </button>
      )}
    </div>
  );
};
