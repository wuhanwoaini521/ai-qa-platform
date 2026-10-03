import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { RuntimeHeader } from './RuntimeHeader';
import { RuntimeOverview } from './RuntimeOverview';
import { RuntimeFlow } from './RuntimeFlow';
import { RuntimeInspector } from './RuntimeInspector';
import { RuntimeEventStream } from './RuntimeEventStream';
import { RuntimeTrace } from './RuntimeTrace';
import { RuntimeTimeline } from './RuntimeTimeline';
import { RuntimeBrowser } from './RuntimeBrowser';
import { RuntimeArtifacts } from './RuntimeArtifacts';
import { RuntimeTaskActions } from './RuntimeTaskActions';
import { useRuntimeSnapshot } from './useRuntimeSnapshot';
import './runtime.css';

export type RuntimeTab =
  'Overview' | 'Flow' | 'Timeline' | 'Trace' | 'Browser' | 'Artifacts';
const tabs: RuntimeTab[] = [
  'Overview',
  'Flow',
  'Timeline',
  'Trace',
  'Browser',
  'Artifacts',
];
export function RuntimeDetail({
  kind,
  id,
  revision,
  onOpenSource,
}: {
  kind: 'task' | 'run';
  id: string;
  revision?: string;
  onOpenSource?: (path: string, line: number) => void;
}) {
  const { snapshot, error, connection, refresh } = useRuntimeSnapshot(
    kind,
    id,
    revision,
  );
  const [tab, setTab] = useState<RuntimeTab>('Overview');
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [focus, setFocus] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const selectStep = useCallback((id: string) => {
    setSelectedStepId(id);
    setInspectorOpen(true);
  }, []);
  useEffect(() => {
    setSelectedStepId(null);
    setTab('Overview');
    setFocus(false);
    setInspectorOpen(true);
  }, [kind, id]);
  useEffect(() => {
    document.documentElement.classList.toggle('runtime-focus', focus);
    return () => document.documentElement.classList.remove('runtime-focus');
  }, [focus]);
  useEffect(() => {
    if (!focus) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setFocus(false);
    };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [focus]);
  if (!snapshot)
    return (
      <section className="rt-shell rt-empty" role={error ? 'alert' : 'status'}>
        {error || '正在读取真实执行记录…'}
        {error && (
          <button className="btn btn-secondary" onClick={refresh}>
            重试
          </button>
        )}
      </section>
    );
  return (
    <section
      className={`rt-shell${focus ? ' rt-focus' : ''}`}
      aria-label="Runtime Detail"
    >
      <RuntimeHeader snapshot={snapshot} connection={connection} />
      <RuntimeTaskActions snapshot={snapshot} onChanged={refresh} />
      {focus && (
        <button
          className="rt-focus-exit btn btn-secondary btn-sm"
          onClick={() => setFocus(false)}
        >
          退出 Focus · Esc
        </button>
      )}
      {error && (
        <div className="rt-notice" role="alert">
          {error}
          <button className="btn btn-secondary btn-sm" onClick={refresh}>
            重新连接
          </button>
        </div>
      )}
      <nav className="rt-tabs" aria-label="Runtime 视图">
        {tabs.map((key) => (
          <button
            key={key}
            aria-current={key === tab ? 'page' : undefined}
            onClick={() => setTab(key)}
          >
            {key}
          </button>
        ))}
        <button aria-label="刷新执行记录" onClick={refresh}>
          <RefreshCw size={15} />
        </button>
      </nav>
      {selectedStepId && !inspectorOpen && (
        <button
          className="btn btn-secondary btn-sm rt-reopen"
          onClick={() => setInspectorOpen(true)}
        >
          打开 Inspector
        </button>
      )}
      {selectedStepId && (
        <div className="rt-selection">
          <code>
            已选步骤 ·{' '}
            {snapshot.steps.find((step) => step.id === selectedStepId)?.key ??
              selectedStepId}
          </code>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => setSelectedStepId(null)}
          >
            清除步骤筛选
          </button>
        </div>
      )}
      <div
        className={`rt-workspace${selectedStepId && inspectorOpen ? ' is-inspected' : ''}`}
      >
        <div className="rt-content">
          {tab === 'Overview' ? (
            <RuntimeOverview
              snapshot={snapshot}
              onOpenFlow={() => setTab('Flow')}
            />
          ) : tab === 'Artifacts' ? (
            <RuntimeArtifacts snapshot={snapshot} />
          ) : tab === 'Browser' ? (
            <RuntimeBrowser snapshot={snapshot} onOpenSource={onOpenSource} />
          ) : tab === 'Timeline' ? (
            <RuntimeTimeline
              snapshot={snapshot}
              selectedStepId={selectedStepId}
              onSelect={selectStep}
            />
          ) : tab === 'Trace' ? (
            <RuntimeTrace
              snapshot={snapshot}
              selectedStepId={selectedStepId}
              onSelect={selectStep}
            />
          ) : (
            <RuntimeFlow
              snapshot={snapshot}
              selectedStepId={selectedStepId}
              onSelect={selectStep}
              focus={focus}
              onFocus={() => setFocus((value) => !value)}
            />
          )}
        </div>
        {inspectorOpen && selectedStepId && (
          <RuntimeInspector
            snapshot={snapshot}
            selectedStepId={selectedStepId}
            onClose={() => setInspectorOpen(false)}
          />
        )}
      </div>
      <RuntimeEventStream
        events={snapshot.events}
        truncated={snapshot.events_truncated}
        onSelect={selectStep}
      />
    </section>
  );
}
