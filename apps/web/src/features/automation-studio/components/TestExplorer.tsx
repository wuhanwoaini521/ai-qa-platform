import React from 'react';
import { useTranslation } from 'react-i18next';
import { Bug, Play } from 'lucide-react';
import { CollectedTest } from '../../../types';

interface TestExplorerProps {
  tests: CollectedTest[];
  loading: boolean;
  runningTest: boolean;
  onOpenFile: (path: string) => void;
  onRunTest: (nodeid: string) => void;
  onDebugTest: (nodeid: string) => void;
}

export const TestExplorer: React.FC<TestExplorerProps> = ({
  tests,
  loading,
  runningTest,
  onOpenFile,
  onRunTest,
  onDebugTest,
}) => {
  const { t } = useTranslation('studioPanels');

  return (
    <div style={{ padding: '4px' }}>
      {loading ? (
        <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
          {t('testExplorer.collecting')}
        </div>
      ) : tests.length === 0 ? (
        <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
          {t('testExplorer.noTestsPrefix')} <code>tests/</code> {t('testExplorer.noTestsSuffix')}
        </div>
      ) : (
        tests.map((test) => (
          <div
            key={test.nodeid}
            style={{
              padding: '6px 8px',
              borderRadius: 'var(--r-xs)',
              marginBottom: '4px',
              background: 'var(--surface-inset)',
              border: '1px solid var(--border-color)',
              fontSize: '12px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div
                style={{
                  fontWeight: 600,
                  color: 'var(--ink)',
                  cursor: 'pointer',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  maxWidth: '180px',
                }}
                onClick={() => onOpenFile(test.path)}
              >
                {test.name}
              </div>
              <div style={{ display: 'flex', gap: 4 }}>
                <button
                  className="btn btn-secondary btn-sm"
                  style={{ padding: '2px 6px', fontSize: '11px' }}
                  disabled={runningTest}
                  onClick={() => onDebugTest(test.nodeid)}
                  title={t('testExplorer.debugThisTest')}
                >
                  <Bug size={10} /> {t('testExplorer.debug')}
                </button>
                <button
                  className="btn btn-primary btn-sm"
                  style={{ padding: '2px 6px', fontSize: '11px' }}
                  disabled={runningTest}
                  onClick={() => onRunTest(test.nodeid)}
                  title={t('testExplorer.runThisTest')}
                >
                  <Play size={10} /> {t('common:run')}
                </button>
              </div>
            </div>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginTop: '2px' }}>
              {test.path}:{test.line}
            </div>
          </div>
        ))
      )}
    </div>
  );
};
