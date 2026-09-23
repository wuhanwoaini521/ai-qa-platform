import React from 'react';
import { Play } from 'lucide-react';
import { CollectedTest } from '../../../types';

interface TestExplorerProps {
  tests: CollectedTest[];
  loading: boolean;
  runningTest: boolean;
  onOpenFile: (path: string) => void;
  onRunTest: (nodeid: string) => void;
}

export const TestExplorer: React.FC<TestExplorerProps> = ({
  tests,
  loading,
  runningTest,
  onOpenFile,
  onRunTest,
}) => (
  <div style={{ padding: '4px' }}>
    {loading ? (
      <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
        Collecting pytest tests...
      </div>
    ) : tests.length === 0 ? (
      <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
        No tests detected in <code>tests/</code> directory.
      </div>
    ) : (
      tests.map((t) => (
        <div
          key={t.nodeid}
          style={{
            padding: '6px 8px',
            borderRadius: '4px',
            marginBottom: '4px',
            background: '#f8fafc',
            border: '1px solid var(--border-color)',
            fontSize: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div
              style={{
                fontWeight: 600,
                color: '#0f172a',
                cursor: 'pointer',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                maxWidth: '180px',
              }}
              onClick={() => onOpenFile(t.path)}
            >
              {t.name}
            </div>
            <button
              className="btn btn-primary btn-sm"
              style={{ padding: '2px 6px', fontSize: '11px' }}
              disabled={runningTest}
              onClick={() => onRunTest(t.nodeid)}
              title="Run this test"
            >
              <Play size={10} /> Run
            </button>
          </div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginTop: '2px' }}>
            {t.path}:{t.line}
          </div>
        </div>
      ))
    )}
  </div>
);
