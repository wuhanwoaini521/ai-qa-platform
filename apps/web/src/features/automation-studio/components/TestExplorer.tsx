import React from 'react';
import { useTranslation } from 'react-i18next';
import { AlertCircle, Bug, LoaderCircle, Play, RefreshCw } from 'lucide-react';
import { CollectedTest } from '../../../types';

interface TestExplorerProps {
  tests: CollectedTest[];
  loading: boolean;
  hasCollected: boolean;
  collectionFailed: boolean;
  runningTest: boolean;
  onCollect: () => void;
  onOpenFile: (path: string, line?: number) => void;
  onRunTest: (nodeid: string) => void;
  onDebugTest: (nodeid: string) => void;
}

export const TestExplorer: React.FC<TestExplorerProps> = ({
  tests,
  loading,
  hasCollected,
  collectionFailed,
  runningTest,
  onCollect,
  onOpenFile,
  onRunTest,
  onDebugTest,
}) => {
  const { t } = useTranslation('studioPanels');

  return (
    <div style={{ padding: '4px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '4px 8px 8px', color: 'var(--ink-muted)', fontSize: '11px' }}>
        <strong>{t('testExplorer.title')}</strong>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onCollect} disabled={loading} aria-label={t(collectionFailed ? 'testExplorer.retry' : hasCollected ? 'testExplorer.refresh' : 'testExplorer.discover')} title={t(collectionFailed ? 'testExplorer.retry' : hasCollected ? 'testExplorer.refresh' : 'testExplorer.discover')}>
          <RefreshCw size={13} aria-hidden="true" />
          {t(collectionFailed ? 'testExplorer.retry' : hasCollected ? 'testExplorer.refresh' : 'testExplorer.discover')}
        </button>
      </div>
      {loading && <div role="status" aria-live="polite" style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '16px', color: 'var(--text-muted)', fontSize: '12px' }}><LoaderCircle size={14} aria-hidden="true" />{t('testExplorer.collecting')}</div>}
      {collectionFailed && !loading && <div role="alert" style={{ display: 'grid', gap: '8px', padding: '16px', color: 'var(--text-muted)', fontSize: '12px' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: '7px', color: 'var(--ui-rose-strong)' }}><AlertCircle size={14} aria-hidden="true" />{t('testExplorer.collectionFailed')}</span>
      </div>}
      {!loading && !collectionFailed && tests.length === 0 && <div style={{ display: 'grid', justifyItems: 'start', gap: '8px', padding: '16px', color: 'var(--text-muted)', fontSize: '12px' }}>
        <span>{t(hasCollected ? 'testExplorer.noTests' : 'testExplorer.notCollected')}</span>
      </div>}
      {!loading && !collectionFailed && tests.length > 0 && tests.map((test) => (
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
              <button
                type="button"
                aria-label={t('testExplorer.openTest', { name: test.name })}
                title={test.nodeid}
                style={{
                  fontWeight: 600,
                  color: 'var(--ink)',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  maxWidth: '180px',
                  border: 0,
                  padding: 0,
                  background: 'transparent',
                  font: 'inherit',
                  textAlign: 'left',
                  cursor: 'pointer',
                }}
                onClick={() => onOpenFile(test.path, test.line)}
              >
                {test.name}
              </button>
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
        ))}
    </div>
  );
};
