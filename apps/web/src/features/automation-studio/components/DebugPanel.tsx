import React from 'react';
import { useTranslation } from 'react-i18next';
import { DebugBreakpointBinding, DebugStackFrame, DebugState, DebugVariable } from '../hooks/useDebugSession';

interface DebugPanelProps {
  state: DebugState;
  nodeid: string | null;
  error: string;
  frames: DebugStackFrame[];
  locals: DebugVariable[];
  output: string;
  breakpointBindings: DebugBreakpointBinding[];
  hasHitBreakpoint: boolean;
  onSelectFrame: (frame: DebugStackFrame) => void;
}

const stateKey: Record<DebugState, string> = {
  idle: 'idle',
  starting: 'starting',
  running: 'running',
  paused: 'paused',
  finished: 'finished',
  error: 'error',
};

export const DebugPanel: React.FC<DebugPanelProps> = ({
  state,
  nodeid,
  error,
  frames,
  locals,
  output,
  breakpointBindings,
  hasHitBreakpoint,
  onSelectFrame,
}) => {
  const { t } = useTranslation('studioPanels');

  return (
    <section
      aria-label={t('debug.title')}
      style={{
        flex: '0 0 220px',
        minHeight: 150,
        maxHeight: 260,
        display: 'flex',
        flexDirection: 'column',
        borderTop: '1px solid var(--ui-line)',
        background: 'var(--ui-surface-raised)',
        overflow: 'hidden',
      }}
    >
      <header style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 12px', borderBottom: '1px solid var(--ui-line)' }}>
        <strong style={{ fontSize: 12 }}>{t('debug.title')}</strong>
        <span style={{ fontSize: 11, color: state === 'error' ? 'var(--ui-rose)' : 'var(--text-muted)' }}>
          {t(`debug.status.${stateKey[state]}`)}
        </span>
        {nodeid && (
          <code title={nodeid} style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 10, color: 'var(--text-muted)' }}>
            {nodeid}
          </code>
        )}
        {error && <span role="alert" style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', fontSize: 11, color: 'var(--ui-rose)' }}>{error}</span>}
      </header>
      <div role="region" aria-label={t('debug.breakpoints')} style={{ padding: '5px 12px', borderBottom: '1px solid var(--ui-line)', fontSize: 11, maxHeight: 80, overflow: 'auto' }}>
        {nodeid?.includes('::') && <div style={{ color: 'var(--text-muted)' }}>{t('debug.singleCaseScope')}</div>}
        {state === 'finished' && !hasHitBreakpoint && (
          <div role="status" style={{ color: 'var(--ui-amber)' }}>{t('debug.noBreakpointHit')}</div>
        )}
        {!breakpointBindings.length && <div style={{ color: 'var(--text-muted)' }}>{t('debug.noBreakpoints')}</div>}
        {breakpointBindings.map((binding) => (
          <div key={binding.id} title={binding.message} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', padding: '2px 0' }}>
            <code>{binding.path}:{binding.requestedLine}</code>
            <span style={{ color: binding.hit ? 'var(--ui-mint-strong)' : binding.verified === false ? 'var(--ui-rose)' : 'var(--text-muted)' }}>
              {t(binding.hit ? 'debug.breakpointHit' : binding.verified === null ? 'debug.breakpointPending' : binding.verified ? 'debug.breakpointVerified' : 'debug.breakpointRejected')}
            </span>
            {binding.line !== binding.requestedLine && <span>{t('debug.breakpointMoved', { line: binding.line })}</span>}
            {binding.message && <span style={{ color: 'var(--text-muted)' }}>{binding.message}</span>}
          </div>
        ))}
      </div>
      <div style={{ minHeight: 0, flex: 1, display: 'grid', gridTemplateColumns: 'minmax(150px, 1fr) minmax(180px, 1fr) minmax(200px, 1.4fr)' }}>
        <div style={{ minWidth: 0, overflow: 'auto', borderRight: '1px solid var(--ui-line)', padding: '7px 10px' }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', marginBottom: 4 }}>{t('debug.callStack')}</div>
          {frames.length ? frames.map((frame) => (
            <button
              key={frame.id}
              type="button"
              onClick={() => onSelectFrame(frame)}
              title={frame.source?.path}
              style={{ display: 'block', width: '100%', border: 0, background: 'transparent', textAlign: 'left', padding: '3px 2px', cursor: 'pointer', color: 'var(--text-primary)', fontSize: 11 }}
            >
              <span>{frame.name}</span>
              <span style={{ marginLeft: 6, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 10 }}>
                {frame.source?.name}:{frame.line}
              </span>
            </button>
          )) : <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{t('debug.noFrames')}</span>}
        </div>
        <div style={{ minWidth: 0, overflow: 'auto', borderRight: '1px solid var(--ui-line)', padding: '7px 10px' }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', marginBottom: 4 }}>{t('debug.variables')}</div>
          {locals.length ? locals.map((variable) => (
            <div key={variable.name} style={{ display: 'grid', gridTemplateColumns: 'minmax(60px, 0.7fr) minmax(0, 1.3fr)', gap: 6, padding: '2px 0', fontSize: 11 }}>
              <code style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{variable.name}</code>
              <code title={variable.value} style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-muted)' }}>{variable.value}</code>
            </div>
          )) : <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{t('debug.noVariables')}</span>}
        </div>
        <div style={{ minWidth: 0, overflow: 'auto', padding: '7px 10px' }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', marginBottom: 4 }}>{t('debug.output')}</div>
          <pre style={{ margin: 0, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>
            {output || t('debug.noOutput')}
          </pre>
        </div>
      </div>
    </section>
  );
};
