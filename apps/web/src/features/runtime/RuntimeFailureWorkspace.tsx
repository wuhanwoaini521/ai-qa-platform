import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent, MouseEvent, WheelEvent } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Check, Clipboard, Code2, Crosshair, Globe, Sparkles, X } from 'lucide-react';
import { AIExecutionTimeline } from '../../components/AIExecutionTimeline';
import { api, getRecorderSocketUrl } from '../../api/client';
import type { AITraceEvent, AIFailureDiagnosisResponse, FailureRecord } from '../../types';
import type { RuntimeSnapshot, RuntimeSourceOpener } from '../../types/runtime';

type RuntimeFailure = RuntimeSnapshot['failures'][number];
type LocatorCandidate = {
  candidate_id?: string;
  kind?: string;
  value?: string;
  name?: string | null;
  locator?: string;
  strategy?: string;
  confidence?: number;
  static_score?: number;
  reason?: string;
};
type LocatorDecision = {
  engine?: string;
  model?: string | null;
  candidate_id?: string | null;
  candidate_count?: number;
  selected_locator?: string | null;
  confidence?: number | null;
  verified?: boolean;
  fallback_reason?: string | null;
};
type PickedElement = {
  tag?: string;
  role?: string | null;
  name?: string;
  text?: string;
  frame_path?: string[];
  ranked_candidates?: LocatorCandidate[];
  selection?: {
    ranked_candidates?: LocatorCandidate[];
    selected_candidate?: LocatorCandidate | null;
    summary?: LocatorDecision;
    verification?: { verified?: boolean };
  } | null;
};
type RecorderFrame = {
  type: string;
  image?: string;
  url?: string;
  state?: string;
  picked?: PickedElement | null;
  message?: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function getAnalysisCandidates(events: AITraceEvent[]): LocatorCandidate[] {
  const inspection = [...events].reverse().find(
    (event) => event.stage === 'inspection' && Array.isArray(event.metadata.candidates),
  );
  return Array.isArray(inspection?.metadata.candidates)
    ? inspection.metadata.candidates.filter(isRecord) as LocatorCandidate[]
    : [];
}

function getCandidateKey(candidate: LocatorCandidate): string {
  return candidate.candidate_id ?? `${candidate.kind ?? ''}:${candidate.value ?? candidate.locator ?? ''}:${candidate.name ?? ''}`;
}

function candidateExpression(candidate: LocatorCandidate): string {
  if (candidate.locator) return candidate.locator;
  const value = JSON.stringify(candidate.value ?? '');
  if (candidate.kind === 'role') return `get_by_role(${value}, name=${JSON.stringify(candidate.name ?? '')})`;
  if (candidate.kind === 'test_id') return `get_by_test_id(${value})`;
  if (candidate.kind === 'label') return `get_by_label(${value})`;
  if (candidate.kind === 'placeholder') return `get_by_placeholder(${value})`;
  if (candidate.kind === 'text') return `get_by_text(${value})`;
  if (candidate.kind === 'id') return `locator('[id=${value}]')`;
  if (candidate.kind === 'name') return `locator('[name=${value}]')`;
  return `locator(${value})`;
}

function locatorExpression(candidate: LocatorCandidate, framePath: string[] = []): string {
  const expression = candidate.locator ?? candidateExpression(candidate);
  const root = framePath.reduce(
    (current, selector) => `${current}.frame_locator(${JSON.stringify(selector)})`,
    'page',
  );
  return `${root}.${expression.startsWith('page.') ? expression.slice(5) : expression}`;
}

export function RuntimeFailureWorkspace({
  failure,
  projectId,
  pageUrl,
  onOpenSource,
}: {
  failure: RuntimeFailure;
  projectId?: string;
  pageUrl?: string;
  onOpenSource?: RuntimeSourceOpener;
}) {
  const { t } = useTranslation('runtime');
  const [record, setRecord] = useState<FailureRecord | null>(null);
  const [resolvedProjectId, setResolvedProjectId] = useState(projectId ?? '');
  const [events, setEvents] = useState<AITraceEvent[]>([]);
  const [diagnosis, setDiagnosis] = useState<AIFailureDiagnosisResponse | null>(null);
  const [decision, setDecision] = useState<LocatorDecision | null>(null);
  const [analysisError, setAnalysisError] = useState('');
  const [pickerSessionId, setPickerSessionId] = useState<string | null>(null);
  const [pickerFrame, setPickerFrame] = useState<RecorderFrame | null>(null);
  const [pickerStatus, setPickerStatus] = useState<'idle' | 'connecting' | 'connected' | 'failed'>('idle');
  const [pickerError, setPickerError] = useState('');
  const [waitingForPick, setWaitingForPick] = useState(false);
  const [pickedElement, setPickedElement] = useState<PickedElement | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState('');
  const [copied, setCopied] = useState(false);
  const pickerSocket = useRef<WebSocket | null>(null);
  const pickerStartSequence = useRef(0);

  useEffect(() => {
    let active = true;
    setRecord(null);
    setEvents([]);
    setDiagnosis(null);
    setDecision(null);
    setAnalysisError('');
    setResolvedProjectId(projectId ?? '');
    void api.getFailure(failure.id).then((value) => {
      if (active) setRecord(value);
    }).catch((error: unknown) => {
      if (active) setAnalysisError(error instanceof Error ? error.message : String(error));
    });
    if (!projectId) {
      void api.getTestRun(failure.test_run_id).then((run) => {
        if (active) setResolvedProjectId(run.project_id);
      }).catch(() => undefined);
    }
    void api.getFailureAnalyses(failure.id).then((rows) => {
      if (!active) return;
      const latest = rows.find((item) => item.result.diagnosis) ?? rows[0];
      if (latest) {
        setEvents(latest.events);
        setDiagnosis(latest.result.diagnosis ?? null);
        setDecision(isRecord(latest.result.selection) ? latest.result.selection as LocatorDecision : null);
      }
    }).catch(() => undefined);
    return () => {
      active = false;
      pickerStartSequence.current += 1;
    };
  }, [failure.id, failure.test_run_id, projectId]);

  useEffect(() => {
    if (!pickerSessionId) return;
    let active = true;
    let socket: WebSocket | null = null;
    setPickerStatus('connecting');
    setPickerError('');
    void Promise.all([
      getRecorderSocketUrl(pickerSessionId),
      api.createStreamTicket('recorder', pickerSessionId),
    ]).then(([url, ticket]) => {
      if (!active) return;
      socket = new WebSocket(url);
      pickerSocket.current = socket;
      socket.onopen = () => {
        socket?.send(JSON.stringify({ type: 'auth', stream_ticket: ticket }));
        setPickerStatus('connected');
      };
      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as RecorderFrame;
          if (data.type === 'frame') {
            setPickerFrame(data);
            if (data.picked) {
              setPickedElement(data.picked);
              const choice = data.picked.selection?.selected_candidate;
              const choiceId = choice ? getCandidateKey(choice) : data.picked.selection?.summary?.candidate_id;
              const first = data.picked.selection?.ranked_candidates?.[0] ?? data.picked.ranked_candidates?.[0];
              setSelectedCandidateId(choiceId ?? (first ? getCandidateKey(first) : ''));
              setWaitingForPick(false);
            }
          } else if (data.type === 'error') {
            setPickerError(data.message ?? t('failureWorkspace.pickerError'));
          }
        } catch {
          setPickerError(t('failureWorkspace.pickerInvalidFrame'));
        }
      };
      socket.onerror = () => {
        if (active) {
          setPickerStatus('failed');
          setPickerError(t('failureWorkspace.pickerConnectionFailed'));
        }
      };
      socket.onclose = () => {
        if (active) setPickerStatus('idle');
      };
    }).catch((error: unknown) => {
      if (active) {
        setPickerStatus('failed');
        setPickerError(error instanceof Error ? error.message : String(error));
      }
    });
    return () => {
      active = false;
      socket?.close(1000, 'failure locator picker closed');
      if (pickerSocket.current === socket) pickerSocket.current = null;
      void api.closeRecorderSession(pickerSessionId).catch(() => undefined);
    };
  }, [pickerSessionId, t]);

  const analysisCandidates = useMemo(() => getAnalysisCandidates(events), [events]);
  const pickedCandidates = pickedElement?.selection?.ranked_candidates ?? pickedElement?.ranked_candidates ?? [];
  const selectedPickedCandidate = pickedCandidates.find((candidate) => getCandidateKey(candidate) === selectedCandidateId)
    ?? pickedElement?.selection?.selected_candidate
    ?? null;
  const targetUrl = pageUrl || (typeof record?.evidence_bundle?.page_url === 'string' ? record.evidence_bundle.page_url : '');
  const sourcePath = record?.test_nodeid.split('::')[0] ?? '';

  const startPicker = async () => {
    if (!resolvedProjectId) {
      setPickerError(t('failureWorkspace.projectUnavailable'));
      return;
    }
    if (!/^https?:\/\//i.test(targetUrl)) {
      setPickerError(t('failureWorkspace.pageUnavailable'));
      return;
    }
    setPickerError('');
    setPickedElement(null);
    setPickerFrame(null);
    const requestSequence = ++pickerStartSequence.current;
    try {
      const session = await api.createRecorderSession(resolvedProjectId, targetUrl);
      if (requestSequence !== pickerStartSequence.current) {
        void api.closeRecorderSession(session.id).catch(() => undefined);
        return;
      }
      setPickerSessionId(session.id);
      if (session.navigation_error) setPickerError(session.navigation_error);
    } catch (error) {
      if (requestSequence === pickerStartSequence.current) {
        setPickerError(error instanceof Error ? error.message : String(error));
      }
    }
  };

  const sendPickerCommand = (action: string, payload: Record<string, unknown> = {}) => {
    const socket = pickerSocket.current;
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ action, ...payload }));
  };

  const pickElement = () => {
    setPickedElement(null);
    setWaitingForPick(true);
    sendPickerCommand('pick_element');
  };

  const clickBrowser = (event: MouseEvent<HTMLDivElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const scale = Math.min(bounds.width / 1280, bounds.height / 720);
    if (!scale) return;
    const offsetX = (bounds.width - 1280 * scale) / 2;
    const offsetY = (bounds.height - 720 * scale) / 2;
    sendPickerCommand('click', {
      x: (event.clientX - bounds.left - offsetX) / scale,
      y: (event.clientY - bounds.top - offsetY) / scale,
    });
    event.currentTarget.focus();
  };

  const handleBrowserKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      sendPickerCommand('type', { text: event.key });
    } else if (['Enter', 'Tab', 'Escape', 'Backspace', 'Delete', 'ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight', ' '].includes(event.key)) {
      event.preventDefault();
      sendPickerCommand('press', { key: event.key === ' ' ? 'Space' : event.key });
    }
  };

  const handleBrowserWheel = (event: WheelEvent<HTMLDivElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const scale = Math.min(bounds.width / 1280, bounds.height / 720);
    if (scale) sendPickerCommand('wheel', { delta_x: event.deltaX / scale, delta_y: event.deltaY / scale });
  };

  const copyAndOpenSource = async () => {
    const expression = selectedPickedCandidate
      ? locatorExpression(selectedPickedCandidate, pickedElement?.frame_path)
      : decision?.selected_locator;
    if (!expression) return;
    try {
      await navigator.clipboard.writeText(expression);
      setCopied(true);
    } catch {
      setPickerError(t('failureWorkspace.copyFailed'));
    }
    if (sourcePath && onOpenSource) {
      onOpenSource(sourcePath, 1, {
        nodeId: record?.test_nodeid,
        failureId: failure.id,
        runId: failure.test_run_id,
      });
    }
  };

  return (
    <section className="rt-failure-workspace rt-block" aria-label={t('failureWorkspace.title')}>
      <div className="rt-failure-workspace-heading">
        <div>
          <span className="rt-eyebrow"><Sparkles size={13} aria-hidden="true" />{t('failureWorkspace.title')}</span>
          <strong>{record?.test_name || failure.title}</strong>
          <p>{record?.error_message || failure.message}</p>
          {record?.failing_locator && <code className="rt-failure-workspace-old-locator">{record.failing_locator}</code>}
        </div>
        <div className="rt-failure-workspace-actions">
          <Link className="btn btn-primary btn-sm" to={`/failures/${encodeURIComponent(failure.id)}`}>
            <Sparkles size={14} aria-hidden="true" />
            {diagnosis ? t('failureWorkspace.reanalyze') : t('failureWorkspace.analyze')}
          </Link>
        </div>
      </div>

      {analysisError && <p className="rt-notice" role="alert">{analysisError}</p>}
      {diagnosis && (
        <div className="rt-failure-diagnosis">
          <div className="rt-failure-diagnosis-primary">
            <div><span>{t('failureWorkspace.rootCause')}</span><p>{diagnosis.root_cause}</p></div>
            {diagnosis.recommended_actions[0] && <div><span>{t('failureWorkspace.nextStep')}</span><p>{diagnosis.recommended_actions[0]}</p></div>}
          </div>
          <details className="rt-failure-analysis-details">
            <summary>{t('failureWorkspace.fullAnalysis')}</summary>
            <div>
              <div><span>{t('failureWorkspace.rootCause')}</span><p>{diagnosis.root_cause}</p></div>
              {diagnosis.hypotheses.length > 0 && <div><span>{t('failureWorkspace.hypotheses')}</span><ul>{diagnosis.hypotheses.map((item, index) => <li key={`${index}:${item}`}>{item}</li>)}</ul></div>}
              {diagnosis.recommended_actions.length > 0 && <div><span>{t('failureWorkspace.recommendations')}</span><ul>{diagnosis.recommended_actions.map((item, index) => <li key={`${index}:${item}`}>{item}</li>)}</ul></div>}
            </div>
          </details>
        </div>
      )}
      {decision && (
        <div className="rt-failure-decision" role="status">
          <strong>{decision.engine === 'Jev' ? t('failureWorkspace.jevSelected') : t('failureWorkspace.localSelected')}</strong>
          {decision.model && <span>{decision.model}</span>}
          {decision.selected_locator && <code>{decision.selected_locator}</code>}
          {typeof decision.candidate_count === 'number' && <span>{t('failureWorkspace.candidateCount', { count: decision.candidate_count })}</span>}
        </div>
      )}
      {analysisCandidates.length > 0 && (
        <details className="rt-failure-candidates">
          <summary>{t('failureWorkspace.analysisCandidates', { count: analysisCandidates.length })}</summary>
          <ol>{analysisCandidates.map((candidate) => <li key={getCandidateKey(candidate)}><code>{locatorExpression(candidate)}</code><span>{candidate.strategy || candidate.kind || t('unknown')}{typeof candidate.confidence === 'number' ? ` · ${Math.round(candidate.confidence * 100)}%` : ''}</span>{candidate.reason && <small>{candidate.reason}</small>}</li>)}</ol>
        </details>
      )}
      <AIExecutionTimeline events={events} running={false} workflowMode />

      <div className="rt-failure-picker">
        <div className="rt-failure-picker-heading">
          <div><strong><Globe size={15} aria-hidden="true" />{t('failureWorkspace.browserPicker')}</strong><span>{targetUrl || t('failureWorkspace.noPageUrl')}</span></div>
          {pickerSessionId ? (
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setPickerSessionId(null)}><X size={14} aria-hidden="true" />{t('failureWorkspace.closePicker')}</button>
          ) : (
            <button type="button" className="btn btn-secondary btn-sm" disabled={!targetUrl || !resolvedProjectId} onClick={() => void startPicker()}><Globe size={14} aria-hidden="true" />{t('failureWorkspace.openPicker')}</button>
          )}
        </div>
        {pickerError && <p className="rt-notice" role="alert">{pickerError}</p>}
        {pickerSessionId && (
          <>
            <div className="rt-failure-picker-controls">
              <span role="status">{t(`failureWorkspace.pickerStatus.${pickerStatus}`)}</span>
              <button type="button" className="btn btn-primary btn-sm" disabled={pickerStatus !== 'connected'} aria-pressed={waitingForPick} onClick={pickElement}><Crosshair size={14} aria-hidden="true" />{waitingForPick ? t('failureWorkspace.pickNow') : t('failureWorkspace.pickElement')}</button>
            </div>
            <div className="rt-failure-picker-viewport" tabIndex={0} aria-label={t('failureWorkspace.browserView')} onClick={clickBrowser} onKeyDown={handleBrowserKeyDown} onWheel={handleBrowserWheel}>
              {pickerFrame?.image ? <img src={`data:image/jpeg;base64,${pickerFrame.image}`} alt={t('failureWorkspace.browserView')} draggable={false} /> : <span>{t('failureWorkspace.waitingForFrame')}</span>}
            </div>
            {pickedElement && (
              <div className="rt-picked-element">
                <div><strong>{pickedElement.role || pickedElement.tag || t('failureWorkspace.pickedElement')}</strong>{pickedElement.name && <span>{pickedElement.name}</span>}{pickedElement.text && <small>{pickedElement.text}</small>}</div>
                {pickedElement.selection?.summary && <p className="rt-picked-decision">{pickedElement.selection.summary.engine === 'Jev' ? t('failureWorkspace.jevSelected') : t('failureWorkspace.localSelected')}{pickedElement.selection.summary.model ? ` · ${pickedElement.selection.summary.model}` : ''}{pickedElement.selection.summary.verified === true ? ` · ${t('failureWorkspace.verified')}` : ` · ${t('failureWorkspace.needsReview')}`}</p>}
                {pickedCandidates.length > 0 ? (
                  <ol className="rt-picked-candidates">
                    {pickedCandidates.map((candidate) => {
                      const candidateId = getCandidateKey(candidate);
                      const jevSelected = candidateId === (pickedElement.selection?.selected_candidate ? getCandidateKey(pickedElement.selection.selected_candidate) : pickedElement.selection?.summary?.candidate_id);
                      const selected = candidateId === selectedCandidateId;
                      return <li key={candidateId}>
                        <button type="button" className={selected ? 'is-selected' : ''} aria-pressed={selected} onClick={() => { setSelectedCandidateId(candidateId); setCopied(false); }}>
                          <span>{locatorExpression(candidate, pickedElement.frame_path)}</span>
                          <small>{candidate.strategy || candidate.kind || t('unknown')}{typeof candidate.static_score === 'number' ? ` · ${Math.round(candidate.static_score * 100)}%` : ''}{jevSelected ? ` · ${t('failureWorkspace.jevRecommendation')}` : ''}</small>
                        </button>
                      </li>;
                    })}
                  </ol>
                ) : <p className="rt-muted">{t('failureWorkspace.noCandidates')}</p>}
                {selectedPickedCandidate && <button type="button" className="btn btn-secondary btn-sm" onClick={() => void copyAndOpenSource()}><Code2 size={14} aria-hidden="true" />{copied ? <><Check size={13} aria-hidden="true" />{t('failureWorkspace.copiedAndOpen')}</> : <><Clipboard size={13} aria-hidden="true" />{t('failureWorkspace.copyAndOpen')}</>}</button>}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
