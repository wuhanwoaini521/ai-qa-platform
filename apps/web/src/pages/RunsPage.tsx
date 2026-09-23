import React from 'react';
import { PlayCircle } from 'lucide-react';

export const RunsPage: React.FC = () => {
  return (
    <div>
      <div style={{ marginBottom: '18px' }}>
        <h2 style={{ fontSize: '18px', fontWeight: 700 }}>Test Runs</h2>
        <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
          Suite execution history, test run status, durations, and CI triggers.
        </p>
      </div>

      <div className="card">
        <div className="card-body" style={{ padding: '48px', textAlign: 'center', color: 'var(--text-muted)' }}>
          <PlayCircle size={40} style={{ margin: '0 auto 12px', opacity: 0.4 }} />
          <div style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '4px' }}>
            No Test Runs Executed
          </div>
          <p style={{ fontSize: '13px', maxWidth: '420px', margin: '0 auto' }}>
            Execution Platform and Worker dispatching will be enabled in Phase 4. Test runs triggered via API or Studio will be aggregated here.
          </p>
        </div>
      </div>
    </div>
  );
};
