import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { ArrowUpRight, ChevronDown, ChevronRight, FileText, ListChecks, Network, RefreshCw, Search } from 'lucide-react';
import { APIError } from '../../api/errors';
import { api } from '../../api/client';
import { useProjectScope, useRouteProjectScope } from '../../app/ProjectScope';
import { buildWorkspaceHref } from '../../app/workspaceContext';
import type { Requirement, TestCase } from '../../types';
import { AUTOMATION_STATUSES, canChangeCaseRequirement, countIndependentCases, filterRequirements, filterTestCases, getCaseDisplayId, getProjectScopedCount, getRequirementDisplayId, INDEPENDENT_CASES_FILTER, normalizeAutomationStatus, normalizePriority, normalizeRequirementStatus, PRIORITIES, REQUIREMENT_STATUSES, type ManagementTab } from './managementModel';
import './ProjectManagementPage.css';
import './ProjectManagementMatrix.css';

function getTab(value: string | null): ManagementTab {
  if (value === 'cases' || value === 'traceability') return value;
  return 'requirements';
}

export function ProjectManagementPage() {
  const { projectId = '' } = useParams();
  const activeProjectIdRef = useRef(projectId);
  activeProjectIdRef.current = projectId;
  const { t } = useTranslation('projectManagement');
  const { t: common } = useTranslation('common');
  const [searchParams, setSearchParams] = useSearchParams();
  const { projects, loading: projectsLoading } = useProjectScope();
  useRouteProjectScope(projectId);
  const project = projects.find((item) => item.id === projectId) ?? null;
  const tab = getTab(searchParams.get('tab'));
  const query = searchParams.get('q') ?? '';
  const status = searchParams.get('status') ?? '';
  const requirementStatus = normalizeRequirementStatus(status);
  const automationStatus = normalizeAutomationStatus(status);
  const priority = searchParams.get('priority') ?? '';
  const casePriority = normalizePriority(priority);
  const requirementFilter = searchParams.get('requirement') ?? '';
  const requestedGapFilter = searchParams.get('gap') ?? '';
  const gapFilter = requestedGapFilter === 'unlinked' || requestedGapFilter === 'linked' ? requestedGapFilter : '';
  const traceRequirementId = searchParams.get('trace') ?? '';
  const sort = searchParams.get('sort') ?? 'updated';
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<'forbidden' | 'failed' | null>(null);
  const [reloadVersion, setReloadVersion] = useState(0);
  const [loadedProjectId, setLoadedProjectId] = useState<string | null>(null);
  const [associationSavingId, setAssociationSavingId] = useState<string | null>(null);
  const [associationFeedback, setAssociationFeedback] = useState<{ caseId: string; message: string; failed: boolean } | null>(null);
  const caseCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of testCases) {
      if (item.requirement_id) counts.set(item.requirement_id, (counts.get(item.requirement_id) ?? 0) + 1);
    }
    return counts;
  }, [testCases]);
  const unlinkedRequirementIds = useMemo(() => new Set(
    requirements.filter((item) => !caseCounts.get(item.id)).map((item) => item.id),
  ), [requirements, caseCounts]);
  const selectedRequirementFilter = requirementFilter === INDEPENDENT_CASES_FILTER || requirements.some((item) => item.id === requirementFilter)
    ? requirementFilter
    : '';
  const traceRequirement = requirements.find((item) => item.id === traceRequirementId) ?? null;

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setLoadedProjectId(null);
    setRequirements([]);
    setTestCases([]);
    setAssociationSavingId(null);
    setAssociationFeedback(null);
    Promise.all([api.getRequirements(projectId), api.getTestCases(projectId)]).then(([nextRequirements, nextCases]) => {
      if (!active) return;
      setRequirements(nextRequirements);
      setTestCases(nextCases);
      setLoadedProjectId(projectId);
    }).catch((reason: unknown) => {
      if (!active) return;
      setError(reason instanceof APIError && reason.status === 403 ? 'forbidden' : 'failed');
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [projectId, reloadVersion]);

  const updateQuery = (patch: Record<string, string>, replace = true) => {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(patch)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    setSearchParams(next, { replace });
  };

  const switchTab = (nextTab: ManagementTab) => {
    updateQuery({
      tab: nextTab,
      status: '',
      priority: '',
      gap: '',
      trace: '',
      requirement: nextTab === 'cases' && tab === 'cases' ? requirementFilter : '',
      sort: 'updated',
    }, false);
  };

  const visibleRequirements = useMemo(() => filterRequirements(requirements, {
    query,
    status: tab === 'cases' ? '' : requirementStatus,
    onlyUnlinked: tab !== 'cases' && gapFilter === 'unlinked',
    onlyLinked: tab !== 'cases' && gapFilter === 'linked',
    sort: sort === 'title' || sort === 'status' ? sort : 'updated',
  }, unlinkedRequirementIds), [requirements, query, requirementStatus, sort, tab, gapFilter, unlinkedRequirementIds]);
  const visibleCases = useMemo(() => filterTestCases(testCases, {
    query,
    automationStatus: tab === 'cases' ? automationStatus : '',
    priority: tab === 'cases' ? casePriority : '',
    requirementId: tab === 'cases' ? selectedRequirementFilter : '',
    sort: sort === 'title' || sort === 'priority' ? sort : 'updated',
  }), [testCases, query, automationStatus, casePriority, selectedRequirementFilter, sort, tab]);

  if (projectsLoading) return <div className="page-loading" role="status" aria-busy="true">{common('loading')}</div>;
  if (!project) return <div className="page-container"><div className="async-state async-state-error" role="alert">{t('projectUnavailable')} <Link to="/projects">{t('backToProjects')}</Link></div></div>;

  const formatDate = (value: string) => {
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? '—' : date.toLocaleDateString();
  };
  const workspaceHref = (item: Requirement | TestCase) => 'acceptance_criteria' in item
    ? buildWorkspaceHref({ projectId, requirementId: item.id, stage: 'requirement', view: 'requirement' })
    : buildWorkspaceHref({ projectId, testCaseId: item.id, stage: 'cases', view: 'cases' });
  const managementHref = (nextTab: ManagementTab, params: Record<string, string> = {}) => {
    const next = new URLSearchParams();
    next.set('tab', nextTab);
    Object.entries(params).forEach(([key, value]) => { if (value) next.set(key, value); });
    return `/projects/${encodeURIComponent(projectId)}/management?${next.toString()}`;
  };
  const dataReady = !loading && !error && loadedProjectId === projectId;
  const independentCount = dataReady ? countIndependentCases(testCases) : null;

  const saveCaseRequirement = async (caseId: string, requirementId: string) => {
    const savingProjectId = projectId;
    setAssociationSavingId(caseId);
    setAssociationFeedback(null);
    try {
      const updatedCase = await api.updateTestCase(caseId, { requirement_id: requirementId || null });
      if (activeProjectIdRef.current !== savingProjectId) return;
      setTestCases((items) => items.map((item) => item.id === caseId ? updatedCase : item));
      setAssociationFeedback({ caseId, message: t('associationSaved'), failed: false });
    } catch {
      if (activeProjectIdRef.current === savingProjectId) {
        setAssociationFeedback({ caseId, message: t('associationFailed'), failed: true });
      }
    } finally {
      if (activeProjectIdRef.current === savingProjectId) setAssociationSavingId(null);
    }
  };

  const renderCaseRows = (items: TestCase[]) => items.map((item) => {
    const linkedRequirement = requirements.find((requirement) => requirement.id === item.requirement_id);
    const feedback = associationFeedback?.caseId === item.id ? associationFeedback : null;
    const canChangeRequirement = canChangeCaseRequirement(item);
    return <tr key={item.id}>
      <td className="management-matrix-identity"><Link className="project-management-item-link" to={workspaceHref(item)}><span className="management-matrix-id">{getCaseDisplayId(item)}</span><strong>{item.title}<ArrowUpRight size={14} aria-hidden="true" /></strong></Link>{item.tags.length > 0 && <small>{item.tags.join(' · ')}</small>}</td>
      <td className="project-management-relation-cell">
        {linkedRequirement
          ? <Link className="management-relation-link" to={managementHref('traceability', { trace: linkedRequirement.id })}>{getRequirementDisplayId(linkedRequirement)} · {linkedRequirement.title}</Link>
          : item.requirement_id
            ? <span className="management-relation-unknown">{t('unavailableRequirement')}</span>
            : <span className="is-independent">{t('independentCase')}</span>}
        <label className="project-management-association-control"><span className="project-management-visually-hidden">{t('changeRequirementForCase', { case: item.title })}</span>
          <select value={linkedRequirement?.id ?? ''} disabled={!canChangeRequirement || associationSavingId !== null} onChange={(event) => void saveCaseRequirement(item.id, event.target.value)} aria-describedby={!canChangeRequirement ? `case-requirement-locked-${item.id}` : undefined} className="ds-select">
            <option value="">{t('independentCase')}</option>{requirements.map((requirement) => <option key={requirement.id} value={requirement.id}>{getRequirementDisplayId(requirement)} · {requirement.title}</option>)}
          </select>
        </label>
        {!canChangeRequirement && <small id={`case-requirement-locked-${item.id}`} className="project-management-association-note">{t('testDesignAssociationLocked')}</small>}
        {associationSavingId === item.id && <small role="status">{t('savingAssociation')}</small>}
        {feedback && <small className={feedback.failed ? 'is-error' : 'is-success'} role={feedback.failed ? 'alert' : 'status'}>{feedback.message}</small>}
      </td>
      <td><span className="project-management-priority">{item.priority}</span></td>
      <td><span className="project-management-status">{t(`automationStatus.${item.automation_status}`, { defaultValue: item.automation_status })}</span></td>
      <td>{formatDate(item.updated_at)}</td>
      <td><Link className="ds-btn ds-btn-sm btn btn-secondary btn-sm" to={workspaceHref(item)}>{t('openWorkspace')}</Link></td>
    </tr>;
  });

  return <div className="page-container project-management-page">
    <nav className="project-management-breadcrumb" aria-label={common('breadcrumb')}>
      <Link to="/projects">{t('projects')}</Link><span aria-hidden="true">/</span>
      <Link to={`/projects/${encodeURIComponent(projectId)}`}>{project.name}</Link><span aria-hidden="true">/</span>
      <span>{t('title')}</span>
    </nav>
    <header className="page-header project-management-header">
      <div><p className="project-management-eyebrow">{t('projectScope', { project: project.name })}</p>
        <h2>{t('title')}</h2><p className="subtitle">{t('subtitle')}</p></div>
      <button type="button" className="ds-btn btn btn-secondary" disabled={loading} onClick={() => setReloadVersion((value) => value + 1)}>
        <RefreshCw size={15} aria-hidden="true" />{t('refresh')}
      </button>
    </header>

    <div className="management-matrix-summary" aria-label={t('relationshipSummary')}>
      <div><span>{t('requirementsTab')}</span><strong>{getProjectScopedCount(requirements.length, loadedProjectId, projectId) ?? '—'}</strong></div>
      <div><span>{t('casesTab')}</span><strong>{getProjectScopedCount(testCases.length, loadedProjectId, projectId) ?? '—'}</strong></div>
      <Link to={managementHref('cases', { requirement: INDEPENDENT_CASES_FILTER })}>
        <span>{t('independentCases')}</span><strong>{independentCount ?? '—'}</strong><small>{t('viewIndependentCases')}</small>
      </Link>
      <Link to={managementHref('requirements', { gap: 'unlinked' })}>
        <span>{t('requirementsWithoutCases')}</span><strong>{dataReady ? unlinkedRequirementIds.size : '—'}</strong><small>{t('viewUnlinkedRequirements')}</small>
      </Link>
    </div>

    <nav className="project-management-tabs management-matrix-tabs" role="tablist" aria-label={t('lists')}>
      <button id="management-tab-requirements" type="button" role="tab" aria-selected={tab === 'requirements'} aria-controls="management-panel" className={["ds-btn", (tab === 'requirements' ? 'selected' : '')].filter(Boolean).join(' ')}
        onKeyDown={(event) => { if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') { event.preventDefault(); const nextTab = tab === 'requirements' ? 'cases' : tab === 'cases' ? 'traceability' : 'requirements'; switchTab(nextTab); document.getElementById(`management-tab-${nextTab}`)?.focus(); } }} onClick={() => switchTab('requirements')}>
        <FileText size={16} aria-hidden="true" />{t('requirementsTab')}<span>{getProjectScopedCount(requirements.length, loadedProjectId, projectId) ?? '—'}</span>
      </button>
      <button id="management-tab-cases" type="button" role="tab" aria-selected={tab === 'cases'} aria-controls="management-panel" className={["ds-btn", (tab === 'cases' ? 'selected' : '')].filter(Boolean).join(' ')}
        onKeyDown={(event) => { if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') { event.preventDefault(); const nextTab = tab === 'requirements' ? 'cases' : tab === 'cases' ? 'traceability' : 'requirements'; switchTab(nextTab); document.getElementById(`management-tab-${nextTab}`)?.focus(); } }} onClick={() => switchTab('cases')}>
        <ListChecks size={16} aria-hidden="true" />{t('casesTab')}<span>{getProjectScopedCount(testCases.length, loadedProjectId, projectId) ?? '—'}</span>
      </button>
      <button id="management-tab-traceability" type="button" role="tab" aria-selected={tab === 'traceability'} aria-controls="management-panel" className={["ds-btn", (tab === 'traceability' ? 'selected' : '')].filter(Boolean).join(' ')}
        onKeyDown={(event) => { if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') { event.preventDefault(); const nextTab = tab === 'requirements' ? 'cases' : tab === 'cases' ? 'traceability' : 'requirements'; switchTab(nextTab); document.getElementById(`management-tab-${nextTab}`)?.focus(); } }} onClick={() => switchTab('traceability')}>
        <Network size={16} aria-hidden="true" />{t('traceabilityTab')}
      </button>
    </nav>

    <section id="management-panel" role="tabpanel" aria-labelledby={`management-tab-${tab}`} className="ds-card card project-management-panel" aria-busy={loading}>
      <div className="project-management-toolbar">
        <label className="project-management-search">
          <Search size={16} aria-hidden="true" /><span className="project-management-visually-hidden">{t('searchLabel')}</span>
          <input type="search" value={query} onChange={(event) => updateQuery({ q: event.target.value })} placeholder={t('searchPlaceholder')} className="ds-input" />
        </label>
        {tab === 'cases' ? <>
          <label className="project-management-filter"><span>{common('status')}</span><select value={automationStatus} onChange={(event) => updateQuery({ status: event.target.value })} className="ds-select">
            <option value="">{t('allStatuses')}</option>{AUTOMATION_STATUSES.map((value) => <option key={value} value={value}>{t(`automationStatus.${value}`)}</option>)}
          </select></label>
          <label className="project-management-filter"><span>{common('priority')}</span><select value={casePriority} onChange={(event) => updateQuery({ priority: event.target.value })} className="ds-select">
            <option value="">{t('allPriorities')}</option>{PRIORITIES.map((value) => <option key={value} value={value}>{value}</option>)}
          </select></label>
          <label className="project-management-filter"><span>{t('requirementColumn')}</span><select value={selectedRequirementFilter} onChange={(event) => updateQuery({ requirement: event.target.value })} className="ds-select">
            <option value="">{t('allRequirements')}</option><option value={INDEPENDENT_CASES_FILTER}>{t('independentCases')}</option>{requirements.map((item) => <option key={item.id} value={item.id}>{getRequirementDisplayId(item)} · {item.title}</option>)}
          </select></label>
          <label className="project-management-filter"><span>{t('sortBy')}</span><select value={['updated', 'title', 'priority'].includes(sort) ? sort : 'updated'} onChange={(event) => updateQuery({ sort: event.target.value })} className="ds-select">
            <option value="updated">{t('sortUpdated')}</option><option value="title">{t('sortTitle')}</option><option value="priority">{t('sortPriority')}</option>
          </select></label>
        </> : <>
          <label className="project-management-filter"><span>{common('status')}</span><select value={requirementStatus} onChange={(event) => updateQuery({ status: event.target.value })} className="ds-select">
            <option value="">{t('allStatuses')}</option>{REQUIREMENT_STATUSES.map((value) => <option key={value} value={value}>{t(`requirementStatus.${value}`)}</option>)}
          </select></label>
          <label className="project-management-filter"><span>{t('relationshipFilter')}</span><select value={gapFilter} onChange={(event) => updateQuery({ gap: event.target.value, trace: '' })} className="ds-select">
            <option value="">{t('allRequirements')}</option><option value="unlinked">{t('requirementsWithoutCases')}</option><option value="linked">{t('requirementsWithCases')}</option>
          </select></label>
          <label className="project-management-filter"><span>{t('sortBy')}</span><select value={['updated', 'title', 'status'].includes(sort) ? sort : 'updated'} onChange={(event) => updateQuery({ sort: event.target.value })} className="ds-select">
            <option value="updated">{t('sortUpdated')}</option><option value="title">{t('sortTitle')}</option><option value="status">{t('sortStatus')}</option>
          </select></label>
        </>}
      </div>
      <p className="project-management-relationship-hint">{tab === 'cases' ? t('caseRelationHint') : tab === 'traceability' ? t('traceabilityHint') : t('requirementRelationHint')}</p>

      {loading && <div className="project-management-state" role="status" aria-busy="true">{t('loading')}</div>}
      {!loading && error && <div className="project-management-state async-state-error" role="alert">
        <span>{t(error === 'forbidden' ? 'forbidden' : 'loadFailed')}</span>
        <button type="button" className="ds-btn ds-btn-sm btn btn-secondary btn-sm" onClick={() => setReloadVersion((value) => value + 1)}>{t('retry')}</button>
      </div>}
      {dataReady && tab !== 'cases' && (requirements.length === 0
        ? <div className="project-management-state"><strong>{t('emptyRequirements')}</strong><p>{t('emptyRequirementsHint')}</p></div>
        : visibleRequirements.length === 0
          ? <div className="project-management-state" role="status">{t('noMatches')} <button type="button" className="ds-btn ds-btn-sm btn btn-secondary btn-sm" onClick={() => updateQuery({ q: '', status: '', gap: '' })}>{t('clearFilters')}</button></div>
          : tab === 'requirements'
            ? <div className="table-responsive project-management-table-wrap"><table className="ds-table data-table project-management-table management-matrix-table">
              <thead><tr><th>{t('idColumn')}</th><th>{t('nameColumn')}</th><th>{common('status')}</th><th>{t('linkedCasesColumn')}</th><th>{t('updatedColumn')}</th><th>{common('actions')}</th></tr></thead>
              <tbody>{visibleRequirements.map((item) => {
                const linkedCaseCount = caseCounts.get(item.id) ?? 0;
                return <tr key={item.id}>
                  <td><code className="management-matrix-id">{getRequirementDisplayId(item)}</code></td>
                  <td><Link className="project-management-item-link project-management-requirement-link" to={workspaceHref(item)}><span className="project-management-requirement-title">{item.title}</span><ArrowUpRight size={14} aria-hidden="true" /></Link>{item.external_id && <small>{item.external_id}</small>}</td>
                  <td><span className="project-management-status">{t(`requirementStatus.${item.status}`, { defaultValue: item.status })}</span></td>
                  <td className="project-management-relation-cell"><span className={linkedCaseCount === 0 ? 'management-gap-label' : ''}>{linkedCaseCount === 0 ? t('noLinkedCases') : t('linkedCaseCount', { count: linkedCaseCount })}</span>
                    <Link className="project-management-inline-action" to={managementHref('cases', { requirement: item.id })}>{t('manageCases')}</Link>
                  </td>
                  <td>{formatDate(item.updated_at)}</td>
                  <td><Link className="ds-btn ds-btn-sm btn btn-secondary btn-sm" to={workspaceHref(item)}>{t('openWorkspace')}</Link></td>
                </tr>;
              })}</tbody>
            </table></div>
            : <div className="table-responsive project-management-table-wrap"><table className="ds-table data-table project-management-table management-matrix-table management-trace-table">
              <thead><tr><th>{t('traceColumn')}</th><th>{t('idColumn')}</th><th>{t('nameColumn')}</th><th>{common('status')}</th><th>{t('linkedCasesColumn')}</th></tr></thead>
              <tbody>{visibleRequirements.map((item) => {
                const linkedCaseCount = caseCounts.get(item.id) ?? 0;
                const expanded = item.id === traceRequirementId;
                const linkedCases = testCases.filter((testCase) => testCase.requirement_id === item.id);
                return <Fragment key={item.id}>
                  <tr>
                    <td><button type="button" className="ds-btn management-trace-toggle" aria-expanded={expanded} aria-label={t(expanded ? 'collapseRequirement' : 'expandRequirement', { requirement: getRequirementDisplayId(item) })} onClick={() => updateQuery({ trace: expanded ? '' : item.id }, false)}>{expanded ? <ChevronDown size={16} aria-hidden="true" /> : <ChevronRight size={16} aria-hidden="true" />}</button></td>
                    <td><code className="management-matrix-id">{getRequirementDisplayId(item)}</code></td>
                    <td><Link className="project-management-item-link project-management-requirement-link" to={workspaceHref(item)}><span className="project-management-requirement-title">{item.title}</span><ArrowUpRight size={14} aria-hidden="true" /></Link></td>
                    <td><span className="project-management-status">{t(`requirementStatus.${item.status}`, { defaultValue: item.status })}</span></td>
                    <td className="project-management-relation-cell"><span className={linkedCaseCount === 0 ? 'management-gap-label' : ''}>{linkedCaseCount === 0 ? t('noLinkedCases') : t('linkedCaseCount', { count: linkedCaseCount })}</span><Link className="project-management-inline-action" to={managementHref('cases', { requirement: item.id })}>{t('openCases')}</Link></td>
                  </tr>
                  {expanded && <tr key={`${item.id}-expanded`} className="management-trace-expanded-row"><td colSpan={5}>
                    {linkedCases.length > 0
                      ? <ul className="management-trace-case-list">{linkedCases.map((testCase) => <li key={testCase.id}><Link to={workspaceHref(testCase)}><code>{getCaseDisplayId(testCase)}</code><strong>{testCase.title}</strong></Link><span className="project-management-status">{t(`automationStatus.${testCase.automation_status}`, { defaultValue: testCase.automation_status })}</span>{testCase.test_design_id && <span className="management-design-lock">{t('designLinked')}</span>}</li>)}</ul>
                      : <div className="management-trace-empty"><span>{t('noLinkedCases')}</span><Link className="ds-btn ds-btn-sm btn btn-secondary btn-sm" to={managementHref('cases', { requirement: item.id })}>{t('linkCases')}</Link></div>}
                  </td></tr>}
                </Fragment>;
              })}</tbody>
            </table></div>)}
      {dataReady && tab === 'cases' && (testCases.length === 0
        ? <div className="project-management-state"><strong>{t('emptyCases')}</strong><p>{t('emptyCasesHint')}</p></div>
        : visibleCases.length === 0
          ? <div className="project-management-state" role="status">{t('noMatches')} <button type="button" className="ds-btn ds-btn-sm btn btn-secondary btn-sm" onClick={() => updateQuery({ q: '', status: '', priority: '', requirement: '' })}>{t('clearFilters')}</button></div>
          : <div className="table-responsive project-management-table-wrap"><table className="ds-table data-table project-management-table management-matrix-table">
            <thead><tr><th>{t('idColumn')}</th><th>{t('nameColumn')}</th><th>{t('requirementColumn')}</th><th>{common('priority')}</th><th>{t('automationColumn')}</th><th>{t('updatedColumn')}</th><th>{common('actions')}</th></tr></thead>
            <tbody>{renderCaseRows(visibleCases)}</tbody>
          </table></div>)}
    </section>
    {dataReady && traceRequirement && tab === 'traceability' && <p className="management-trace-focus" role="status">{t('expandedRequirement', { requirement: getRequirementDisplayId(traceRequirement) })}</p>}
    <p className="project-management-footnote">{t('dataScope', { count: tab === 'requirements' ? visibleRequirements.length : tab === 'traceability' ? visibleRequirements.length : visibleCases.length })}</p>
  </div>;
}
