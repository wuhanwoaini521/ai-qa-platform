import { useEffect, useRef, useState } from 'react';
import { Activity, Bug, ChevronDown, CircleAlert, Play, RotateCcw, Sparkles, Square, Workflow, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { TestRun } from '../../types';
import { workspaceRunDockPlacement, workspaceRunDockState } from './workspaceRunModel';

export interface WorkspaceRunConfig {
  environment: string;
  region: string;
  browser: string;
  workers: number;
}

interface WorkspaceRunDockProps {
  caseLabel: string;
  caseTitle: string;
  hasAutomation: boolean;
  aiRunLabel?: string;
  run: TestRun | null;
  taskStatus?: string | null;
  taskStep?: string | null;
  busy: boolean;
  error: string;
  config: WorkspaceRunConfig;
  onConfigChange: (value: WorkspaceRunConfig) => void;
  onRun: () => void;
  onAiRun: () => void;
  onStop: () => void;
  onOpen: () => void;
  onViewResult: () => void;
  onViewFailure: () => void;
  onDebug: () => void;
  onRerun: () => void;
  onOpenCode: () => void;
}

export function WorkspaceRunDock({
  caseLabel,
  caseTitle,
  hasAutomation,
  aiRunLabel,
  run,
  taskStatus,
  taskStep,
  busy,
  error,
  config,
  onConfigChange,
  onRun,
  onAiRun,
  onStop,
  onOpen,
  onViewResult,
  onViewFailure,
  onDebug,
  onRerun,
  onOpenCode,
}: WorkspaceRunDockProps) {
  const { t } = useTranslation('workspace');
  const [configOpen, setConfigOpen] = useState(false);
  const [dockOpen, setDockOpen] = useState(false);
  const [dockPlacement, setDockPlacement] = useState<ReturnType<typeof workspaceRunDockPlacement> | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dockRef = useRef<HTMLElement>(null);
  const updateDockPlacement = () => {
    const trigger = triggerRef.current?.getBoundingClientRect();
    if (!trigger) return;
    setDockPlacement(workspaceRunDockPlacement(trigger, {
      width: window.innerWidth,
      height: window.innerHeight,
    }));
  };
  const runStatus = run?.status ?? null;
  const { status, active, failed, passed, taskTerminal } = workspaceRunDockState(runStatus, taskStatus);
  const activeExecution = run?.executions.find((item) => item.status === 'RUNNING');
  const completed = run?.executions.filter((item) => item.finished_at).length ?? 0;
  const total = run?.executions.length || run?.total || 0;
  const hasSavedRunResults = Boolean(run?.executions.length);

  useEffect(() => {
    if (!dockOpen) return;
    const focusable = () => [...(dockRef.current?.querySelectorAll<HTMLElement>(
      'a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
    ) ?? [])].filter((element) => element.getClientRects().length > 0);
    const first = focusable()[0];
    (first ?? dockRef.current)?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setDockOpen(false);
        return;
      }
      if (event.key !== 'Tab') return;
      const items = focusable();
      if (!items.length) {
        event.preventDefault();
        dockRef.current?.focus();
        return;
      }
      const current = document.activeElement;
      if (event.shiftKey && (current === items[0] || !dockRef.current?.contains(current))) {
        event.preventDefault();
        items[items.length - 1].focus();
      } else if (!event.shiftKey && (current === items[items.length - 1] || !dockRef.current?.contains(current))) {
        event.preventDefault();
        items[0].focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      triggerRef.current?.focus();
    };
  }, [dockOpen]);

  const update = (patch: Partial<WorkspaceRunConfig>) => onConfigChange({ ...config, ...patch });

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className={`workspace-run-launcher is-${status}`}
        aria-label={`${t('dock.openControls')} · ${t(`dock.status.${status}`)}${caseLabel ? ` · ${caseLabel}` : ''}`}
        aria-expanded={dockOpen}
        onClick={() => {
          updateDockPlacement();
          setDockOpen(true);
        }}
      >
        <span className="workspace-dock-indicator" aria-hidden="true">
          {failed ? <CircleAlert size={14} /> : active ? <Activity size={14} /> : <Play size={13} />}
        </span>
        <span>{t('dock.openControls')}</span>
        {status !== 'idle' && <small>{t(`dock.status.${status}`)}{caseLabel ? ` · ${caseLabel}` : ''}</small>}
        <ChevronDown size={14} aria-hidden="true" />
      </button>

      {dockOpen && <div className="workspace-run-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) { setDockOpen(false); triggerRef.current?.focus(); } }}>
        <section
          ref={dockRef}
          className={`workspace-run-dock is-${status}`}
          role="dialog"
          aria-modal="true"
          aria-label={t('dock.title')}
          tabIndex={-1}
          style={dockPlacement ? {
            left: dockPlacement.left,
            right: 'auto',
            top: dockPlacement.top ?? 'auto',
            bottom: dockPlacement.bottom ?? 'auto',
            maxHeight: dockPlacement.maxHeight,
          } : undefined}
          onMouseDown={(event) => event.stopPropagation()}
        >
          <header className="workspace-run-dock-heading">
            <div className="workspace-run-dock-status">
              <span className="workspace-dock-indicator" aria-hidden="true">
                {failed ? <CircleAlert size={14} /> : active ? <Activity size={14} /> : <Play size={13} />}
              </span>
              <div>
                <strong>{t(`dock.status.${status}`)}</strong>
                <small>{caseLabel || t('dock.noCase')}</small>
              </div>
            </div>
            <button type="button" className="btn btn-icon btn-sm" aria-label={t('dock.closeControls')} onClick={() => { setDockOpen(false); triggerRef.current?.focus(); }}><X size={15} aria-hidden="true" /></button>
          </header>

          <div className="workspace-run-dock-context">
            <strong title={caseTitle}>{caseTitle || t('dock.chooseCase')}</strong>
            <small>
              {taskStep || activeExecution?.nodeid || (run ? `${run.browser} · ${run.environment?.QA_REGION || config.region}` : t('dock.contextHint', { environment: config.environment, region: config.region, browser: config.browser }))}
            </small>
          </div>

          <div className="workspace-run-dock-progress" aria-live="polite">
            {run ? (
              <>
                <strong>{hasSavedRunResults ? run.passed + '/' + (total || '—') + ' ' + t('dock.passed') : active ? t('dock.status.running') : t('dock.resultUnavailable')}</strong>
                <small>{!hasSavedRunResults ? active ? taskStep || t('dock.preparing') : t('dock.resultUnavailableHint') : run.failed ? t('dock.failedCount', { count: run.failed }) : active ? t('dock.progress', { completed, total: total || '—' }) : t('dock.lastRun')}</small>
              </>
            ) : active ? (
              <>
                <strong>{t('dock.aiPlanRunning')}</strong>
                <small>{taskStep || t('dock.preparing')}</small>
              </>
            ) : taskTerminal ? (
              <>
                <strong>{t(`dock.status.${status}`)}</strong>
                <small>{taskStep || t('dock.taskFinished')}</small>
              </>
            ) : (
              <>
                <strong>{config.environment.toUpperCase()} · {config.region}</strong>
                <small>{config.browser} · {t('dock.workers', { count: config.workers })}</small>
              </>
            )}
          </div>

          <div className="workspace-run-dock-actions">
            {!active && !failed && (
              <>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => setConfigOpen((open) => !open)} aria-expanded={configOpen}>
                  {t('dock.config')} <ChevronDown size={13} aria-hidden="true" />
                </button>
                <button type="button" className="btn btn-secondary btn-sm workspace-ai-run-button" onClick={() => { setDockOpen(false); onAiRun(); }} disabled={busy}>
                  <Sparkles size={14} aria-hidden="true" /> {aiRunLabel ?? t('dock.aiRun')}
                </button>
                <button type="button" className="btn btn-primary btn-sm" onClick={() => { setDockOpen(false); onRun(); }} disabled={!hasAutomation || busy}>
                  <Play size={14} aria-hidden="true" /> {busy ? t('dock.starting') : t('dock.run')}
                </button>
              </>
            )}
            {active && (
              <>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setDockOpen(false); onOpen(); }}>{t('dock.open')}</button>
                <button type="button" className="btn btn-danger btn-sm" onClick={() => { setDockOpen(false); onStop(); }}><Square size={13} aria-hidden="true" /> {t('dock.stop')}</button>
              </>
            )}
            {failed && run && (
              <>
                <button type="button" className="btn btn-primary btn-sm" onClick={() => { setDockOpen(false); onViewFailure(); }}><Sparkles size={14} aria-hidden="true" /> {t('dock.viewFailure')}</button>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setDockOpen(false); onDebug(); }}><Bug size={14} aria-hidden="true" /> {t('dock.debug')}</button>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setDockOpen(false); onRerun(); }}><RotateCcw size={13} aria-hidden="true" /> {t('dock.rerun')}</button>
              </>
            )}
            {taskTerminal && !run && <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setDockOpen(false); onOpen(); }}>{t('dock.viewTask')}</button>}
            {passed && run && <button type="button" className="btn btn-primary btn-sm" onClick={() => { setDockOpen(false); onViewResult(); }}>{t('dock.viewResult')}</button>}
            {!hasAutomation && !active && !failed && (
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setDockOpen(false); onOpenCode(); }}><Workflow size={13} aria-hidden="true" /> {t('dock.addAutomation')}</button>
            )}
          </div>

          {configOpen && !active && (
            <div className="workspace-run-config" role="group" aria-label={t('dock.config')}>
              <label>{t('dock.environment')}
                <select value={config.environment} onChange={(event) => update({ environment: event.target.value })}>
                  <option value="development">Development</option>
                  <option value="staging">Staging</option>
                  <option value="production">Production</option>
                </select>
              </label>
              <label>{t('dock.region')}
                <select value={config.region} onChange={(event) => update({ region: event.target.value })}>
                  <option value="JP">JP</option>
                  <option value="US">US</option>
                  <option value="EU">EU</option>
                  <option value="auto">Auto</option>
                </select>
              </label>
              <label>{t('dock.browser')}
                <select value={config.browser} onChange={(event) => update({ browser: event.target.value })}>
                  <option value="chromium">Chrome</option>
                  <option value="firefox">Firefox</option>
                  <option value="webkit">WebKit</option>
                </select>
              </label>
              <label>{t('dock.workersLabel')}
                <select value={config.workers} onChange={(event) => update({ workers: Number(event.target.value) })}>
                  {[1, 2, 4, 8].map((count) => <option key={count} value={count}>{count}</option>)}
                </select>
              </label>
              <p>{t('dock.aiIndependent')}</p>
            </div>
          )}
          {error && <p className="workspace-run-dock-error" role="alert">{error}</p>}
        </section>
      </div>}
    </>
  );
}
