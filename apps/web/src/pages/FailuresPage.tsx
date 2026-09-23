import React from 'react';
import { AlertTriangle, Sparkles } from 'lucide-react';

export const FailuresPage: React.FC = () => {
  return (
    <div>
      <div style={{ marginBottom: '18px' }}>
        <h2 style={{ fontSize: '18px', fontWeight: 700 }}>Failure Intelligence & Flaky Tracking</h2>
        <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
          Automated failure categorization, root-cause diagnosis, and flaky test analysis.
        </p>
      </div>

      <div className="card">
        <div className="card-body" style={{ padding: '48px', textAlign: 'center', color: 'var(--text-muted)' }}>
          <AlertTriangle size={40} style={{ margin: '0 auto 12px', color: '#d97706', opacity: 0.6 }} />
          <div style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '4px' }}>
            Failure Intelligence Engine Ready
          </div>
          <p style={{ fontSize: '13px', maxWidth: '440px', margin: '0 auto 16px' }}>
            Contracts and taxonomy abstractions are configured in <code>qa-core</code>. Real-time diagnosis reports will automatically populate here upon test failures.
          </p>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#2563eb', background: '#eff6ff', padding: '6px 12px', borderRadius: '4px' }}>
            <Sparkles size={14} /> Powered by qa-core FailureAnalyzer & LocatorHealer
          </div>
        </div>
      </div>
    </div>
  );
};
