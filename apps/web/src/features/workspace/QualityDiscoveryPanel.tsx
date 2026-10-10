import { useEffect, useMemo, useRef, useState } from 'react';
import { Activity, ArrowDownRight, ExternalLink, Eye, GitBranch, Pause, Play, RotateCcw, ShieldAlert, Square, Waypoints } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { api } from '../../api/client';
import type { QualityDiscoveryGap, QualityDiscoveryMode, QualityDiscoveryRun, Requirement } from '../../types';
import { gapsForCoverageRow } from './qualityDiscoveryMap';
import './quality-discovery.css';

const terminalStatuses = new Set(['COMPLETED', 'BLOCKED', 'FAILED', 'STOPPED', 'BUDGET_EXHAUSTED']);

export function QualityDiscoveryPanel({
  projectId,
  initialRequirementId,
  onOpenRequirement,
  onOpenCase,
  onOpenAutomation,
  onOpenRun,
}: {
  projectId: string;
  initialRequirementId?: string;
  onOpenRequirement?: (requirementId: string) => void;
  onOpenCase?: (testCaseId: string, requirementId?: string) => void;
  onOpenAutomation?: (testCaseId: string, filePath: string) => void;
  onOpenRun?: (runId: string, testCaseId?: string) => void;
}) {
  const { t } = useTranslation('qualityDiscovery');
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [runs, setRuns] = useState<QualityDiscoveryRun[]>([]);
  const [run, setRun] = useState<QualityDiscoveryRun | null>(null);
  const [url, setUrl] = useState('');
  const [urlTouched, setUrlTouched] = useState(false);
  const [mode, setMode] = useState<QualityDiscoveryMode>('EXPLORE');
  const [requirementId, setRequirementId] = useState('');
  const requirementEdited = useRef(false);
  const [requirementText, setRequirementText] = useState('');
  const [allowedDomainsText, setAllowedDomainsText] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [pollError, setPollError] = useState('');
  const [historyStatus, setHistoryStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [requirementsError, setRequirementsError] = useState(false);
  const [loadVersion, setLoadVersion] = useState(0);
  const [gapFilter, setGapFilter] = useState('ALL');
  const [mapFilter, setMapFilter] = useState('ALL');
  const [mapQuery, setMapQuery] = useState('');
  const [mapSort, setMapSort] = useState('FEATURE');
  const [reportTab, setReportTab] = useState<'map' | 'gaps' | 'features' | 'activity'>('map');
  const [evidenceUrl, setEvidenceUrl] = useState('');
  const [evidenceText, setEvidenceText] = useState('');
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState('');

  useEffect(() => {
    requirementEdited.current = false;
    setRequirementId('');
  }, [projectId]);

  useEffect(() => {
    if (mode !== 'EXPLORE' && !requirementEdited.current) setRequirementId(initialRequirementId ?? '');
  }, [initialRequirementId, mode]);

  useEffect(() => {
    let current = true;
    setHistoryStatus('loading');
    setRequirementsError(false);
    setRequirements([]);
    setRuns([]);
    setRun(null);
    setError('');
    setPollError('');
    void Promise.allSettled([
      api.getRequirements(projectId),
      api.getQualityDiscoveryRuns(projectId),
    ]).then(([requirementsResult, historyResult]) => {
      if (!current) return;
      if (requirementsResult.status === 'fulfilled') setRequirements(requirementsResult.value);
      else {
        setRequirementsError(true);
        requirementEdited.current = true;
        setRequirementId('');
      }
      if (historyResult.status === 'fulfilled') {
        setRuns(historyResult.value);
        const selected = historyResult.value.find((item) => !terminalStatuses.has(item.status)) ?? historyResult.value[0] ?? null;
        setRun(selected);
        setHistoryStatus('ready');
      } else {
        setHistoryStatus('error');
      }
    });
    return () => { current = false; };
  }, [projectId, loadVersion]);

  useEffect(() => {
    if (!run || terminalStatuses.has(run.status)) return;
    let active = true;
    const timer = window.setInterval(() => {
      void api.getQualityDiscoveryRun(run.id).then((next) => {
        if (!active) return;
        setPollError('');
        setRun(next);
        if (terminalStatuses.has(next.status)) {
          void api.getQualityDiscoveryRuns(projectId).then((items) => { if (active) setRuns(items); }).catch(() => undefined);
        }
      }).catch((reason) => {
        if (active) setPollError(reason instanceof Error ? reason.message : String(reason));
      });
    }, 1200);
    return () => { active = false; window.clearInterval(timer); };
  }, [run?.id, run?.status, projectId]);

  useEffect(() => {
    if (!run) return;
    setReportTab(terminalStatuses.has(run.status) ? 'map' : 'activity');
  }, [run?.id, run?.status]);

  useEffect(() => () => {
    if (evidenceUrl) URL.revokeObjectURL(evidenceUrl);
  }, [evidenceUrl]);

  const gaps = run?.result.gaps ?? [];
  const coverage = (run?.result.coverage ?? []) as Array<Record<string, unknown>>;
  const functionalFeatures = run?.result.functional_spec?.features ?? [];
  const journeys = run?.result.journeys ?? [];
  const frontier = run?.result.frontier ?? [];
  const latestRealJevDecision = [...(run?.result.decisions ?? [])]
    .reverse()
    .find((decision) => decision.provider === 'jev' && !decision.fallback_used);
  const latestFallbackJevDecision = [...(run?.result.decisions ?? [])]
    .reverse()
    .find((decision) => decision.fallback_used && decision.attempted_provider);
  const jevProvider = run?.result.jev?.provider === 'fallback'
    ? latestRealJevDecision?.provider ?? run.result.jev.provider
    : run?.result.jev?.provider;
  const jevModel = run?.result.jev?.model ?? latestRealJevDecision?.model;
  const attemptedJev = run?.result.jev?.provider === 'fallback' && !latestRealJevDecision && latestFallbackJevDecision?.attempted_provider
    ? ` · ${t('attempted')}: ${latestFallbackJevDecision.attempted_provider}${latestFallbackJevDecision.attempted_model ? ` / ${latestFallbackJevDecision.attempted_model}` : ''}`
    : '';
  const frontierCounts = useMemo(
    () => frontier.reduce<Record<string, number>>((counts, item) => {
      counts[item.status] = (counts[item.status] ?? 0) + 1;
      return counts;
    }, {}),
    [frontier],
  );
  const pendingFrontierCount = frontierCounts.PENDING ?? 0;
  const blockedFrontierCount = (frontierCounts.BLOCKED ?? 0) + (frontierCounts.BLOCKED_BY_POLICY ?? 0);
  const failedFrontierCount = frontierCounts.FAILED ?? 0;
  const filteredGaps = useMemo(
    () => gapFilter === 'ALL' ? gaps : gaps.filter((gap) => gap.category === gapFilter),
    [gapFilter, gaps],
  );
  const filteredCoverage = useMemo(() => {
    const query = mapQuery.trim().toLocaleLowerCase();
    const rows = coverage.filter((row) => {
      const featureId = String(row.feature_id ?? '');
      const feature = run?.result.features?.find((item) => item.feature_id === featureId);
      const featureGaps = gapsForCoverageRow(row, gaps, feature?.requirement_ids);
      const hasGaps = featureGaps.length > 0;
      const status = String(row.last_run_status ?? feature?.coverage_status ?? '').toUpperCase();
      const matchesFilter = mapFilter === 'ALL'
        || (mapFilter === 'GAPS' && hasGaps)
        || (mapFilter === 'UNCOVERED' && ['NOT_COVERED', 'NOT_VERIFIED', 'NOT_AUTOMATED', 'PARTIAL'].includes(String(row.coverage_status ?? feature?.coverage_status ?? '').toUpperCase()))
        || (mapFilter === 'FAILED' && ['FAILED', 'FAIL', 'ERROR', 'AUTOMATION_FAILING'].includes(status));
      if (!matchesFilter) return false;
      if (!query) return true;
       const linkedRequirements = (feature?.requirement_ids ?? []).map((id) => {
         const requirement = run?.result.requirements?.find((item) => item.id === id);
         return requirement?.title ?? requirement?.feature ?? id;
       });
       return [row.feature, feature?.name, feature?.description, ...linkedRequirements, ...featureGaps.map((gap) => gap.title)]
         .some((value) => String(value ?? '').toLocaleLowerCase().includes(query));
    });
    const riskOrder: Record<string, number> = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 };
    const coverageOrder: Record<string, number> = { AUTOMATION_FAILING: 0, NOT_COVERED: 1, NOT_VERIFIED: 1, NOT_AUTOMATED: 1, PARTIAL: 2, COVERED: 3, VERIFIED: 4, AUTOMATED: 5 };
    return rows.sort((left, right) => {
      if (mapSort === 'RISK') {
        const getRisk = (row: Record<string, unknown>) => {
          const featureId = String(row.feature_id ?? '');
          const feature = run?.result.features?.find((item) => item.feature_id === featureId);
          return Math.max(0, ...gapsForCoverageRow(row, gaps, feature?.requirement_ids).map((gap) => riskOrder[gap.risk] ?? 0));
        };
        return getRisk(right) - getRisk(left) || String(left.feature ?? '').localeCompare(String(right.feature ?? ''));
      }
      if (mapSort === 'COVERAGE') {
        const statusOrder = (row: Record<string, unknown>) => coverageOrder[String(row.coverage_status ?? '').toUpperCase()] ?? 6;
        return statusOrder(left) - statusOrder(right) || String(left.feature ?? '').localeCompare(String(right.feature ?? ''));
      }
      return String(left.feature ?? '').localeCompare(String(right.feature ?? ''), undefined, { sensitivity: 'base' });
    });
  }, [coverage, gaps, mapFilter, mapQuery, mapSort, run?.result.features, run?.result.requirements]);
  const active = Boolean(run && !terminalStatuses.has(run.status));
  const needsRequirement = mode !== 'EXPLORE';
  const startUrlMessage = useMemo(() => {
    if (!url.trim()) return 'startUrlRequiredHelp';
    try {
      const parsed = new URL(url.trim());
      return ['http:', 'https:'].includes(parsed.protocol)
        && Boolean(parsed.hostname)
        && !parsed.username
        && !parsed.password
        && !parsed.search
        && !parsed.hash
        ? 'startUrlHelp'
        : 'startUrlInvalidHelp';
    } catch {
      return 'startUrlInvalidHelp';
    }
  }, [url]);
  const canStartUrl = startUrlMessage === 'startUrlHelp';
  const startUrlInvalid = urlTouched && !canStartUrl;
  const startUrlHelp = canStartUrl ? 'startUrlHelp' : urlTouched ? startUrlMessage : 'startUrlRequiredHelp';

  const start = async () => {
    if (!canStartUrl || (needsRequirement && !requirementId && !requirementText.trim())) return;
    setBusy(true);
    setError('');
    setPollError('');
    setEvidenceUrl('');
    try {
      const created = await api.createQualityDiscoveryRun({
        project_id: projectId,
        start_url: url.trim(),
        mode,
        requirement_id: needsRequirement ? requirementId || undefined : undefined,
        requirement_text: needsRequirement && !requirementId ? requirementText.trim() || undefined : undefined,
        allowed_domains: allowedDomainsText.split(',').map((item) => item.trim()).filter(Boolean),
      });
      setRun(created);
      setRuns((items) => [created, ...items.filter((item) => item.id !== created.id)]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };

  const controlRun = async (operation: 'pause' | 'resume' | 'stop') => {
    if (!run) return;
    setError('');
    try {
      const next = operation === 'pause'
        ? await api.pauseQualityDiscoveryRun(run.id)
        : operation === 'resume'
          ? await api.resumeQualityDiscoveryRun(run.id)
          : await api.stopQualityDiscoveryRun(run.id);
      setRun(next);
      setPollError('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const openEvidence = async (id: string) => {
    setEvidenceLoading(true);
    setError('');
    try {
      const blob = await api.getArtifactBlob(id);
      if (!blob.type.startsWith('image/')) {
        setEvidenceText(await blob.text());
        setEvidenceUrl('');
        setEvidenceLoading(false);
        return;
      }
      setEvidenceText('');
      const nextUrl = URL.createObjectURL(blob);
      setEvidenceUrl((current) => {
        if (current) URL.revokeObjectURL(current);
        return nextUrl;
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setEvidenceLoading(false);
    }
  };

  const selectRun = async (id: string) => {
    try {
      setRun(await api.getQualityDiscoveryRun(id));
      setError('');
      setPollError('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const runGapAction = async (gap: QualityDiscoveryGap, action: 'create_requirement_draft' | 'generate_tests' | 'generate_automation' | 'open_failure') => {
    if (!run) return;
    setActionBusy(`${gap.id}:${action}`);
    setActionError('');
    try {
      const result = await api.actOnQualityDiscoveryGap(run.id, gap.id, action);
      const refreshed = await api.getQualityDiscoveryRun(run.id);
      setRun(refreshed);
      setRuns((items) => items.map((item) => item.id === refreshed.id ? refreshed : item));
      const feature = refreshed.result.features?.find((item) => item.feature_id === gap.item_id);
      if (action === 'create_requirement_draft' && typeof result.requirement_id === 'string') {
        onOpenRequirement?.(result.requirement_id);
      } else if (action === 'generate_tests') {
        const ids = Array.isArray(result.test_case_ids) ? result.test_case_ids : [];
        if (typeof ids[0] === 'string') onOpenCase?.(ids[0], feature?.requirement_ids?.[0]);
      } else if (action === 'generate_automation') {
        const binding = result.binding as { test_case_id?: string; file_path?: string } | undefined;
        if (binding?.test_case_id && binding.file_path) onOpenAutomation?.(binding.test_case_id, binding.file_path);
      } else if (action === 'open_failure') {
        const failedAutomation = result.automation as { test_case_id?: string } | undefined;
        if (typeof result.run_id === 'string') onOpenRun?.(result.run_id, typeof result.test_case_id === 'string' ? result.test_case_id : failedAutomation?.test_case_id);
      }
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setActionBusy(null);
    }
  };

  const featureForGap = (gap: QualityDiscoveryGap) => run?.result.features?.find((item) => item.feature_id === gap.item_id);
  const hasRealRequirement = (feature: NonNullable<ReturnType<typeof featureForGap>>) =>
    feature.requirement_ids?.some((id) => run?.result.requirements?.some((item) => item.id === id && item.source_id !== 'PASTED')) ?? false;

  return (
    <div className={`quality-discovery${!run ? ' is-empty' : ''}`}>
      <section className="qd-launch-card">
        <div className="qd-heading">
          <div className="qd-heading-icon"><Waypoints size={18} aria-hidden="true" /></div>
          <div><span className="qd-eyebrow">{t('eyebrow')}</span><h3>{t('title')}</h3><p>{t('description')}</p></div>
        </div>
        <div className="qd-form-grid">
          <label className="qd-field qd-url-field"><span>{t('startUrl')} <span className="qd-required-mark" aria-hidden="true">*</span></span><input type="url" value={url} onChange={(event) => { setUrlTouched(true); setUrl(event.target.value); }} onBlur={() => setUrlTouched(true)} placeholder={t('startUrlPlaceholder')} aria-label={t('startUrl')} aria-required="true" aria-invalid={startUrlInvalid} aria-describedby="qd-start-url-help" required /><small id="qd-start-url-help" className={`qd-field-hint${startUrlInvalid ? ' is-error' : ''}`}>{t(startUrlHelp)}</small></label>
          <label className="qd-field"><span>{t('mode')}</span><select value={mode} onChange={(event) => setMode(event.target.value as QualityDiscoveryMode)} aria-label={t('mode')}>
            <option value="EXPLORE">{t('modes.EXPLORE')}</option><option value="VALIDATE">{t('modes.VALIDATE')}</option><option value="AUDIT">{t('modes.AUDIT')}</option>
          </select></label>
          {needsRequirement && <label className="qd-field"><span>{t('requirementRequired')} <span className="qd-required-mark" aria-hidden="true">*</span></span><select value={requirementId} onChange={(event) => { requirementEdited.current = true; setRequirementId(event.target.value); setRequirementText(''); }} aria-label={t('requirementRequired')}>
            <option value="">{t('noRequirement')}</option>
            {requirements.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
          </select>{requirementsError && <small className="qd-field-hint is-error" role="status">{t('requirementsLoadError')}</small>}</label>}
        </div>
        {needsRequirement && !requirementId && <label className="qd-field qd-paste-field"><span>{t('pasteRequirementRequired')}</span><textarea value={requirementText} onChange={(event) => setRequirementText(event.target.value)} rows={3} maxLength={20_000} placeholder={t('pastePlaceholder')} required /></label>}
        <details className="qd-advanced" open={showAdvanced} onToggle={(event) => setShowAdvanced(event.currentTarget.open)}>
          <summary>{t('advanced')}</summary>
          <label className="qd-field"><span>{t('allowedDomains')}</span><input value={allowedDomainsText} onChange={(event) => setAllowedDomainsText(event.target.value)} placeholder="docs.example.com, shop.example.com" /></label>
          <p>{t('safeActionsNote')}</p>
        </details>
        <div className="qd-launch-actions">
          <button type="button" className="btn btn-primary" onClick={() => void start()} disabled={historyStatus !== 'ready' || busy || active || !canStartUrl || (needsRequirement && !requirementId && !requirementText.trim())}>
            <Play size={14} aria-hidden="true" />{busy ? t('starting') : t('start')}
          </button>
          {runs.length > 0 && <label className="qd-run-picker"><span>{t('previousRun')}</span><select value={run?.id ?? ''} onChange={(event) => void selectRun(event.target.value)}>{runs.map((item) => <option key={item.id} value={item.id}>{item.mode} · {item.status} · {new Date(item.created_at).toLocaleString()}</option>)}</select></label>}
          {historyStatus === 'loading' && <span className="qd-load-status" role="status">{t('historyLoading')}</span>}
          {historyStatus === 'error' && <div className="qd-load-error" role="alert"><span>{t('historyLoadError')}</span><button type="button" className="btn btn-secondary btn-sm" onClick={() => setLoadVersion((version) => version + 1)}>{t('retryLoad')}</button></div>}
        </div>
        {error && <p className="qd-error" role="alert">{error}</p>}
      </section>

      {historyStatus === 'ready' && !run && <section className="qd-start-empty" aria-label={t('emptyStartTitle')}>
        <div className="qd-empty-mark"><Waypoints size={18} aria-hidden="true" /></div>
        <strong>{t('emptyStartTitle')}</strong>
        <p>{t('emptyStartDescription')}</p>
        <ol><li>{t('emptyStartSteps.url')}</li><li>{t('emptyStartSteps.mode')}</li><li>{t('emptyStartSteps.results')}</li></ol>
      </section>}

      {run && <>
        <section className="qd-run-card" aria-live="polite">
          <div className="qd-run-heading">
            <div><span className="qd-eyebrow">{t('runStatus')}</span><h3>{t(`statuses.${run.status}`, { defaultValue: run.status })}</h3><p>{run.start_url}</p></div>
            <span className={`qd-status-pill is-${run.status.toLowerCase()}`}>{run.status}</span>
          </div>
          <div className="qd-progress-grid">
            <div><strong>{run.progress.states}</strong><span>{t('states')}</span></div>
            <div><strong>{run.progress.actions}</strong><span>{t('actions')}</span></div>
            <div><strong>{run.progress.features}</strong><span>{t('features')}</span></div>
            <div><strong>{gaps.length}</strong><span>{t('gaps')}</span></div>
          </div>
          <div className="qd-current-activity"><span>{t('currentActivity')}</span><strong>{run.result.events?.[run.result.events.length - 1]?.message ?? t(`statuses.${run.status}`, { defaultValue: run.status })}</strong></div>
          {pollError && <p className="qd-error" role="alert">{pollError}</p>}
          <div className="qd-frontier-summary" aria-label={t('frontierSummary')}>
            <span>{t('visitedStates')}: {run.result.states?.length ?? run.progress.states}</span>
            <span>{t('pendingActions')}: {pendingFrontierCount}</span>
            <span>{t('blockedActions')}: {blockedFrontierCount}</span>
            <span>{t('failedActions')}: {failedFrontierCount}</span>
          </div>
          {run.error && <div className="qd-run-error"><ShieldAlert size={15} aria-hidden="true" />{run.error}</div>}
          <div className="qd-run-actions">
            {run.status === 'RUNNING' && <button type="button" className="btn btn-secondary btn-sm" onClick={() => void controlRun('pause')}><Pause size={13} />{t('pause')}</button>}
            {run.status === 'PAUSED' && <button type="button" className="btn btn-secondary btn-sm" onClick={() => void controlRun('resume')}><RotateCcw size={13} />{t('resume')}</button>}
            {active && <button type="button" className="btn btn-secondary btn-sm" onClick={() => void controlRun('stop')}><Square size={12} />{t('stop')}</button>}
            <div className="qd-provider-facts">
              <span>{t('ai')}: {run.result.ai?.provider ?? '—'} / {run.result.ai?.model ?? '—'}</span>
              <span>{t('jev')}: {jevProvider ?? '—'}{jevModel ? ` / ${jevModel}` : ''} / {run.result.jev?.decisions ?? 0}{attemptedJev}{(run.result.jev?.fallbacks ?? 0) > 0 ? ` · ${t('fallbackCount', { count: run.result.jev?.fallbacks })}` : ''}</span>
            </div>
          </div>
        </section>

        <nav className="qd-report-tabs" aria-label={t('reportSections')}>
          <button type="button" aria-current={reportTab === 'map' ? 'page' : undefined} onClick={() => setReportTab('map')}>{t('qualityMap')}<span>{coverage.length}</span></button>
          <button type="button" aria-current={reportTab === 'gaps' ? 'page' : undefined} onClick={() => setReportTab('gaps')}>{t('qualityGaps')}<span>{gaps.length}</span></button>
          <button type="button" aria-current={reportTab === 'features' ? 'page' : undefined} onClick={() => setReportTab('features')}>{t('features')}<span>{functionalFeatures.length}</span></button>
          <button type="button" aria-current={reportTab === 'activity' ? 'page' : undefined} onClick={() => setReportTab('activity')}>{t('recentActivity')}<span>{run.result.events?.length ?? 0}</span></button>
        </nav>

        {reportTab === 'map' && <section className="qd-section qd-quality-map">
          <div className="qd-section-heading"><div><span className="qd-eyebrow">{t('qualityMap')}</span><h3>{t('coverageMap')}</h3></div><div className="qd-map-tools"><label className="qd-map-search"><span className="sr-only">{t('mapSearch')}</span><input type="search" value={mapQuery} onChange={(event) => setMapQuery(event.target.value)} placeholder={t('mapSearch')} /></label><label className="qd-filter"><span>{t('mapFilter')}</span><select value={mapFilter} onChange={(event) => setMapFilter(event.target.value)}><option value="ALL">{t('allFeatures')}</option><option value="GAPS">{t('featuresWithGaps')}</option><option value="UNCOVERED">{t('uncoveredFeatures')}</option><option value="FAILED">{t('failedFeatures')}</option></select></label><label className="qd-filter"><span>{t('mapSort')}</span><select value={mapSort} onChange={(event) => setMapSort(event.target.value)}><option value="FEATURE">{t('sortFeature')}</option><option value="RISK">{t('sortRisk')}</option><option value="COVERAGE">{t('sortCoverage')}</option></select></label></div></div>
          {!coverage.length ? <p className="qd-empty">{t('coveragePending')}</p> : !filteredCoverage.length ? <p className="qd-empty">{t('noMapMatches')}</p> : <div className="qd-table-scroll"><table className="qd-coverage-table">
            <thead><tr><th>{t('mapFeature')}</th><th>{t('mapProduct')}</th><th>{t('mapCoverage')}</th><th>{t('mapTests')}</th><th>{t('mapAutomation')}</th><th>{t('mapLastRun')}</th><th>{t('mapRisk')}</th></tr></thead>
            <tbody>{filteredCoverage.map((row, index) => {
              const featureId = String(row.feature_id ?? '');
              const feature = run.result.features?.find((item) => item.feature_id === featureId);
              const featureGaps = gapsForCoverageRow(row, gaps, feature?.requirement_ids);
              const riskOrder: Record<string, number> = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 };
              const highestRisk = featureGaps.reduce<string>((highest, gap) =>
                (riskOrder[gap.risk] ?? 0) > (riskOrder[highest] ?? 0) ? gap.risk : highest, '');
              const coverageStatus = String(row.coverage_status ?? feature?.coverage_status ?? 'NOT_VERIFIED');
              return <tr key={`${featureId || String(row.feature)}-${index}`}>
                <td><strong>{String(row.feature ?? feature?.name ?? '—')}</strong><details className="qd-row-details">
                  <summary>{t('featureDetails')}</summary>
                  <div>
                    {(feature?.description || feature?.page) && <p>{feature.description || feature.page}</p>}
                    {feature?.requirement_ids?.length ? <section><b>{t('mapRequirement')}</b><ul>{feature.requirement_ids.map((id) => {
                      const requirement = run.result.requirements?.find((item) => item.id === id);
                      return <li key={id}>{String(requirement?.title ?? id)}</li>;
                    })}</ul></section> : <p>{t('noLinkedRequirement')}</p>}
                    {featureGaps.length > 0 && <section><b>{t('mapGaps')}</b><ul>{featureGaps.map((gap) => <li key={gap.id}><span className={`qd-gap-risk is-${gap.risk.toLowerCase()}`}>{gap.risk}</span> {gap.title}</li>)}</ul></section>}
                    {!!feature?.evidence_ids.length && <div className="qd-evidence-row"><Eye size={13} aria-hidden="true" /><span>{t('evidence')}:</span>{feature.evidence_ids.map((id) => <button type="button" key={id} onClick={() => void openEvidence(id)} disabled={evidenceLoading}>{id.slice(0, 10)}</button>)}</div>}
                  </div>
                </details></td>
                <td><span className={`qd-map-state is-${String(row.product_status ?? row.functional_status ?? 'unknown').toLowerCase()}`}>{String(row.product_status ?? row.functional_status ?? '—')}</span></td>
                <td><span className={`qd-map-state is-${coverageStatus.toLowerCase()}`}>{t(`coverageStatuses.${coverageStatus}`, { defaultValue: coverageStatus })}</span></td>
                <td>{String(row.test_status ?? '—')}{Array.isArray(row.test_case_ids) && row.test_case_ids.length > 0 ? ` · ${row.test_case_ids.length}` : ''}</td>
                <td>{String(row.automation_status ?? '—')}</td>
                <td>{String(row.last_run_status ?? '—')}</td>
                <td>{highestRisk ? <span className={`qd-gap-risk is-${highestRisk.toLowerCase()}`}>{highestRisk} · {featureGaps.length}</span> : '—'}</td>
              </tr>;
            })}</tbody>
          </table></div>}
        </section>}

        {reportTab === 'features' && <section className="qd-section">
          <details className="qd-document-details">
            <summary><span>{t('functionalSpecification')}</span><small>{t('functionalSpecificationNote')}</small></summary>
            {!!run.result.functional_spec?.disclaimer && <p>{run.result.functional_spec.disclaimer}</p>}
            <div className="qd-spec-list">{functionalFeatures.map((item, index) => <article key={String(item.feature_id ?? index)}>
              <strong>{String(item.name ?? '—')}</strong><span>{String(item.trust ?? 'INFERRED')}</span>
              <p>{String(item.description ?? '')}</p>
              <small>{t('requirementStatus')}: {String(item.requirement_status ?? '—')} · {t('testCases')}: {Array.isArray(item.test_case_ids) ? item.test_case_ids.length : 0} · {t('automation')}: {String(item.last_run_status ?? '—')}</small>
              {Array.isArray(item.evidence_ids) && item.evidence_ids.length > 0 && <div className="qd-evidence-row"><Eye size={13} aria-hidden="true" />{item.evidence_ids.map((id) => <button type="button" key={String(id)} onClick={() => void openEvidence(String(id))} disabled={evidenceLoading}>{String(id).slice(0, 10)}</button>)}</div>}
            </article>)}</div>
          </details>
          <details className="qd-document-details">
            <summary><span>{t('userJourneys')}</span><small>{journeys.length}</small></summary>
            <div className="qd-journey-list">{journeys.map((journey) => <article key={journey.journey_id}>
              {journey.steps.map((step, index) => <span key={`${step.state_id}-${index}`}>{index > 0 && <ArrowDownRight size={12} aria-hidden="true" />}{step.title}</span>)}
              {journey.steps.flatMap((step) => step.evidence_ids ?? []).map((id) => <button type="button" key={id} onClick={() => void openEvidence(id)} disabled={evidenceLoading}>{t('openEvidence')} · {id.slice(0, 8)}</button>)}
            </article>)}</div>
          </details>
        </section>}

        {reportTab === 'gaps' && <section className="qd-section">
          <div className="qd-section-heading"><div><span className="qd-eyebrow">{t('coverage')}</span><h3>{t('qualityGaps')}</h3></div>
            <label className="qd-filter"><span>{t('filter')}</span><select value={gapFilter} onChange={(event) => setGapFilter(event.target.value)}><option value="ALL">{t('allGaps')}</option>{[...new Set(gaps.map((gap) => gap.category))].map((category) => <option key={category} value={category}>{t(`gapTypes.${category}`, { defaultValue: category })}</option>)}</select></label>
          </div>
          {actionError && <p className="qd-error" role="alert">{actionError}</p>}
          {!filteredGaps.length ? <p className="qd-empty">{t('noGaps')}</p> : <div className="qd-gap-list">
            {filteredGaps.map((gap: QualityDiscoveryGap) => <article className="qd-gap" key={gap.id}>
              <div><span className={`qd-gap-risk is-${gap.risk.toLowerCase()}`}>{gap.risk}</span><span className="qd-gap-type">{t(`gapTypes.${gap.category}`, { defaultValue: gap.category })}</span><strong>{gap.title}</strong></div>
              <p className="qd-gap-confidence">{t('confidence')}: {Math.round(gap.confidence * 100)}% · {t('nextAction')}: {t(`gapActions.${gap.category}`, { defaultValue: gap.suggested_action })}</p>
              <dl className="qd-gap-context">
                <div><dt>{t('gapRequirement')}</dt><dd>{gap.requirement || t('gapNoRequirement')}</dd></div>
                <div><dt>{t('gapExpected')}</dt><dd>{gap.expected?.length ? gap.expected.join('；') : t('gapNoExpected')}</dd></div>
                <div><dt>{t('gapObserved')}</dt><dd>{gap.observed || t('gapNoObserved')}</dd></div>
              </dl>
              {!!gap.evidence_ids.length && <div className="qd-evidence-row"><Eye size={13} aria-hidden="true" /><span>{t('evidence')}:</span>{gap.evidence_ids.map((id) => <button type="button" key={id} onClick={() => void openEvidence(id)} disabled={evidenceLoading}>{id.slice(0, 10)}</button>)}</div>}
              <div className="qd-gap-actions">
                {(gap.category === 'UNDOCUMENTED_FEATURE' || gap.category === 'TEST_MISSING' && featureForGap(gap) && !hasRealRequirement(featureForGap(gap)!)) && <button type="button" className="btn btn-secondary btn-sm" disabled={Boolean(actionBusy)} onClick={() => void runGapAction(gap, 'create_requirement_draft')}>{actionBusy?.startsWith(`${gap.id}:`) ? t('working') : t('createRequirementDraft')}</button>}
                {gap.category === 'TEST_MISSING' && <button type="button" className="btn btn-primary btn-sm" disabled={Boolean(actionBusy) || !featureForGap(gap) || (!hasRealRequirement(featureForGap(gap)!) && !run.result.requirement_drafts?.[featureForGap(gap)!.feature_id])} onClick={() => void runGapAction(gap, 'generate_tests')}>{t('generateTests')}</button>}
                {gap.category === 'AUTOMATION_MISSING' && !!featureForGap(gap)?.test_case_ids?.length && <button type="button" className="btn btn-primary btn-sm" disabled={Boolean(actionBusy)} onClick={() => void runGapAction(gap, 'generate_automation')}>{t('generateAutomation')}</button>}
                {gap.category === 'AUTOMATION_FAILING' && <button type="button" className="btn btn-secondary btn-sm" disabled={Boolean(actionBusy)} onClick={() => void runGapAction(gap, 'open_failure')}>{t('openFailure')}</button>}
                {gap.category === 'UNDOCUMENTED_FEATURE' && !!run.result.gap_actions?.[gap.id]?.create_requirement_draft && typeof run.result.requirement_drafts?.[featureForGap(gap)?.feature_id ?? ''] === 'string' && <button type="button" className="btn btn-secondary btn-sm" onClick={() => onOpenRequirement?.(String(run.result.requirement_drafts?.[featureForGap(gap)?.feature_id ?? '']))}>{t('openRequirement')}</button>}
              </div>
            </article>)}
          </div>}
        </section>}

        {reportTab === 'activity' && <section className="qd-section qd-lower-grid">
          <div><div className="qd-section-heading"><div><span className="qd-eyebrow">{t('observed')}</span><h3>{t('stateGraph')}</h3></div><GitBranch size={16} aria-hidden="true" /></div>
            <div className="qd-state-list">{(run.result.states ?? []).map((state, index) => <div className="qd-state" key={String(state.state_id ?? index)}><span>{index + 1}</span><div><strong>{String(state.title || state.url || state.state_id)}</strong><small>{String(state.url || '')} · {String(state.visible_controls ?? 0)} {t('controls')}</small></div></div>)}</div>
            {(run.result.edges?.length ?? 0) > 0 && <div className="qd-edges">{run.result.edges?.slice(-10).map((edge, index) => <span key={`${String(edge.candidate_id)}-${index}`}><ArrowDownRight size={13} />{String(edge.label || edge.action)}</span>)}</div>}
          </div>
          <div><div className="qd-section-heading"><div><span className="qd-eyebrow">{t('trace')}</span><h3>{t('recentActivity')}</h3></div><Activity size={16} aria-hidden="true" /></div>
            <div className="qd-event-list">{(run.result.events ?? []).slice(-12).reverse().map((event) => <div key={event.id}><i aria-hidden="true" /><span>{event.message}</span><small>{new Date(event.created_at).toLocaleTimeString()}</small></div>)}</div>
            <details className="qd-document-details">
              <summary><span>{t('candidateFrontier')}</span><small>{frontier.length}</small></summary>
              <div className="qd-frontier-summary">{Object.entries(frontierCounts).map(([status, count]) => <span key={status}>{t(`frontierStatuses.${status}`, { defaultValue: status })}: {count}</span>)}</div>
              <div className="qd-frontier-list">{frontier.slice(-30).reverse().map((item) => <article key={`${item.state_id}-${item.candidate_id}`}>
                <strong>{item.target || item.candidate_id}</strong>
                <span>{t(`frontierStatuses.${item.status}`, { defaultValue: item.status })}</span>
                {item.reason && <small>{item.reason}</small>}
              </article>)}</div>
            </details>
          </div>
        </section>}
        {(evidenceUrl || evidenceText) && <section className="qd-section qd-evidence-section"><div className="qd-evidence-viewer"><div><strong>{evidenceText ? t('snapshotPreview') : t('evidencePreview')}</strong><button type="button" className="btn btn-secondary btn-sm" onClick={() => { setEvidenceUrl(''); setEvidenceText(''); }}>{t('close')}</button></div>{evidenceUrl ? <img src={evidenceUrl} alt={t('evidenceAlt')} /> : <pre>{evidenceText}</pre>}</div></section>}
        <a className="qd-api-link" href={`/api/discovery/runs/${encodeURIComponent(run.id)}`} target="_blank" rel="noreferrer"><ExternalLink size={13} />{t('apiView')}</a>
      </>}
    </div>
  );
}
