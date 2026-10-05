import { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
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
import type { RuntimeSourceOpener } from '../../types/runtime';
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
  projectId,
  onOpenSource,
  onOpenStudio,
}: {
  kind: 'task' | 'run';
  id: string;
  revision?: string;
  projectId?: string;
  onOpenSource?: RuntimeSourceOpener;
  onOpenStudio?: () => void;
}) {
  const { t } = useTranslation('runtime');
  const { snapshot, error, connection, refresh } = useRuntimeSnapshot(
    kind,
    id,
    revision,
  );
  const [tab, setTab] = useState<RuntimeTab>('Flow');
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const [focus, setFocus] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const initialStepResolved = useRef(false);
  const selectStep = useCallback((id: string) => {
    setSelectedStepId(id);
    setInspectorOpen(true);
    setSearchParams((params) => {
      params.set('step', id);
      return params;
    }, { replace: true });
  }, [setSearchParams]);
  const clearStepSelection = useCallback(() => {
    setSelectedStepId(null);
    setSearchParams((params) => { params.delete('step'); return params; }, { replace: true });
  }, [setSearchParams]);
  useEffect(() => {
    setTab('Flow');
    setFocus(false);
    setSelectedStepId(null);
    setInspectorOpen(true);
    initialStepResolved.current = false;
  }, [kind, id]);
  useEffect(() => {
    document.documentElement.classList.toggle('runtime-focus', focus);
    return () => document.documentElement.classList.remove('runtime-focus');
  }, [focus]);
  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        if (focus) setFocus(false);
        else setInspectorOpen(false);
      }
    };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [focus]);
  useEffect(() => {
    if (!snapshot) return;
    const requested = searchParams.get('step');
    if (requested && snapshot.steps.some((step) => step.id === requested)) {
      setSelectedStepId(requested);
      setInspectorOpen(true);
      initialStepResolved.current = true;
      return;
    }
    if (!initialStepResolved.current) {
      initialStepResolved.current = true;
      const initial = snapshot.blocking?.step_id ?? snapshot.summary.active_step_ids[0] ?? null;
      if (initial) {
        setSelectedStepId(initial);
        setInspectorOpen(true);
        setSearchParams((params) => {
          params.set('step', initial);
          return params;
        }, { replace: true });
      }
    }
  }, [snapshot, searchParams, setSearchParams]);
  useEffect(() => {
    if (!snapshot || !selectedStepId) return;
    const handle = (event: KeyboardEvent) => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      const target = event.target as HTMLElement | null;
      if (target?.closest('input,textarea,select,[contenteditable="true"]')) return;
      const index = snapshot.steps.findIndex((step) => step.id === selectedStepId);
      const next = snapshot.steps[index + (event.key === 'ArrowRight' ? 1 : -1)];
      if (next) {
        event.preventDefault();
        selectStep(next.id);
      }
    };
    window.addEventListener('keydown', handle);
    return () => window.removeEventListener('keydown', handle);
  }, [snapshot, selectedStepId, selectStep]);
  if (!snapshot)
    return (
      <section className="rt-shell rt-empty" role={error ? 'alert' : 'status'}>
        {error || t('loadingRuntime')}
        {error && (
          <button className="btn btn-secondary" onClick={refresh}>
            {t('retry')}
          </button>
        )}
      </section>
    );
  return (
      <section
        className={`rt-shell${focus ? ' rt-focus' : ''}`}
        aria-label={t('observatory')}
        data-active-tab={tab}
        data-has-steps={snapshot.steps.length > 0 ? 'true' : 'false'}
      >
      <RuntimeHeader snapshot={snapshot} connection={connection} />
      <RuntimeTaskActions snapshot={snapshot} onChanged={refresh} onInspect={(stepId) => { selectStep(stepId); setTab('Flow'); }} onOpenStudio={onOpenStudio} />
      {focus && (
        <button
          className="rt-focus-exit btn btn-secondary btn-sm"
          onClick={() => setFocus(false)}
        >
          {t('exitFocus')} · Esc
        </button>
      )}
      {error && (
        <div className="rt-notice" role="alert">
          {error}
          <button className="btn btn-secondary btn-sm" onClick={refresh}>
            {t('reconnect')}
          </button>
        </div>
      )}
      <nav className="rt-tabs" aria-label={t('runtimeViews')}>
        {tabs.map((key) => (
          <button
            key={key}
            aria-current={key === tab ? 'page' : undefined}
            onClick={() => setTab(key)}
          >
            {t(key)}
          </button>
        ))}
        <button aria-label={t('forceRefresh')} title={t('forceRefresh')} onClick={refresh}>
          <RefreshCw size={15} />
        </button>
      </nav>
      {selectedStepId && !inspectorOpen && (
        <button
          className="btn btn-secondary btn-sm rt-reopen"
          onClick={() => setInspectorOpen(true)}
        >
          {t('openInspector')}
        </button>
      )}
      {selectedStepId && (
        <div className="rt-selection">
          <code>
            {t('selectedStep')} ·{' '}
            {snapshot.steps.find((step) => step.id === selectedStepId)?.key ??
              selectedStepId}
          </code>
          <button
            className="btn btn-secondary btn-sm"
            onClick={clearStepSelection}
          >
            {t('clearStepFilter')}
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
              onSelectStep={selectStep}
            />
          ) : tab === 'Artifacts' ? (
            <RuntimeArtifacts snapshot={snapshot} />
          ) : tab === 'Browser' ? (
            <RuntimeBrowser snapshot={snapshot} projectId={projectId} onOpenSource={onOpenSource} />
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
              onClearSelection={clearStepSelection}
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
            onOpenSource={onOpenSource}
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
