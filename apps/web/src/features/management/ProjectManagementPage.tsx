import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import type { FormEvent, KeyboardEvent as ReactKeyboardEvent } from 'react';
import { ArrowUpRight, ChevronDown, ChevronRight, FileText, ListChecks, Network, Plus, RefreshCw, Search, X } from 'lucide-react';
import { APIError } from '../../api/errors';
import { api } from '../../api/client';
import { useProjectScope, useRouteProjectScope } from '../../app/ProjectScope';
import { buildWorkspaceHref } from '../../app/workspaceContext';
import type { Requirement, TestCase } from '../../types';
import { RequirementFormModal, useRequirementFormModal } from '../requirements/components/RequirementFormModal';
import { TestCaseFormModal, useTestCaseFormModal } from '../test-cases/components/TestCaseFormModal';
import { criteriaTextFor, requirementDocumentWithCriteria } from '../lifecycle/requirementCriteria';
import { AUTOMATION_STATUSES, canChangeCaseRequirement, clearedFilterPatch, countIndependentCases, filterRequirements, filterTestCases, getCaseDisplayId, getProjectScopedCount, getRequirementDisplayId, INDEPENDENT_CASES_FILTER, normalizeAutomationStatus, normalizePriority, normalizeRequirementStatus, PRIORITIES, REQUIREMENT_STATUSES, type ManagementTab } from './managementModel';
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
  const detailRef = useRef<HTMLElement | null>(null);
  const lastTriggerRef = useRef<HTMLElement | null>(null);
  const [criteriaEditing, setCriteriaEditing] = useState(false);
  const [criteriaDraft, setCriteriaDraft] = useState('');
  const [criteriaSaving, setCriteriaSaving] = useState(false);
  const [criteriaFeedback, setCriteriaFeedback] = useState<{ message: string; failed: boolean } | null>(null);
  const [linkCaseId, setLinkCaseId] = useState('');
  const [linkSaving, setLinkSaving] = useState(false);
  const [linkFeedback, setLinkFeedback] = useState<{ message: string; failed: boolean } | null>(null);
  const [createError, setCreateError] = useState('');
  // A ref, not state: two submits dispatched in one tick both read the pre-render closure,
  // so a state guard still fires two POSTs. The ref flips synchronously.
  const creatingRef = useRef(false);
  const detailRequirementId = searchParams.get('detail') ?? '';
  const detailRequirement = requirements.find((item) => item.id === detailRequirementId) ?? null;
  const requirementForm = useRequirementFormModal(projectId);
  const caseForm = useTestCaseFormModal(projectId, detailRequirement?.id ?? null);
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
  const detailCriteria = detailRequirement ? criteriaTextFor(detailRequirement) : '';
  const detailLinkedCases = detailRequirement
    ? testCases.filter((item) => item.requirement_id === detailRequirement.id)
    : [];
  const detailUnlinkedCases = testCases.filter((item) => !item.requirement_id && canChangeCaseRequirement(item));

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

  const detailCriteriaRef = useRef(detailCriteria);
  detailCriteriaRef.current = detailCriteria;
  useEffect(() => {
    setCriteriaEditing(false);
    setCriteriaDraft(detailCriteriaRef.current);
    setCriteriaFeedback(null);
    setLinkCaseId('');
    setLinkFeedback(null);
    if (detailRequirementId) detailRef.current?.focus();
    else lastTriggerRef.current?.focus();
  }, [detailRequirementId]);

  useEffect(() => {
    if (!detailRequirementId) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      const next = new URLSearchParams(searchParams);
      next.delete('detail');
      setSearchParams(next, { replace: false });
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [detailRequirementId, searchParams, setSearchParams]);

  const updateQuery = (patch: Record<string, string>, replace = true) => {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(patch)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    setSearchParams(next, { replace });
  };

  const openDetail = (id: string) => {
    lastTriggerRef.current = document.activeElement as HTMLElement | null;
    updateQuery({ detail: id }, false);
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

  const moveTab = (event: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
    event.preventDefault();
    const order: ManagementTab[] = ['requirements', 'cases', 'traceability'];
    const nextTab = order[(order.indexOf(tab) + (event.key === 'ArrowRight' ? 1 : -1) + order.length) % order.length];
    switchTab(nextTab);
    document.getElementById(`management-tab-${nextTab}`)?.focus();
  };

  const saveCriteria = async () => {
    if (!detailRequirement) return;
    const descriptions = criteriaDraft.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
    setCriteriaSaving(true);
    setCriteriaFeedback(null);
    try {
      const updated = await api.updateRequirement(detailRequirement.id, {
        acceptance_criteria: descriptions.join('\n'),
        qa_model: requirementDocumentWithCriteria(detailRequirement, descriptions),
      });
      setRequirements((items) => items.map((item) => (item.id === updated.id ? updated : item)));
      setCriteriaEditing(false);
      setCriteriaFeedback({ message: t('criteriaSaved'), failed: false });
    } catch {
      setCriteriaFeedback({ message: t('criteriaSaveFailed'), failed: true });
    } finally {
      setCriteriaSaving(false);
    }
  };

  const linkCase = async () => {
    if (!detailRequirement || !linkCaseId) return;
    setLinkSaving(true);
    setLinkFeedback(null);
    try {
      const updatedCase = await api.updateTestCase(linkCaseId, { requirement_id: detailRequirement.id });
      setTestCases((items) => items.map((item) => (item.id === updatedCase.id ? updatedCase : item)));
      setLinkCaseId('');
      setLinkFeedback({ message: t('caseLinked'), failed: false });
    } catch {
      setLinkFeedback({ message: t('caseLinkFailed'), failed: true });
    } finally {
      setLinkSaving(false);
    }
  };

  const createRequirement = async (event: FormEvent) => {
    event.preventDefault();
    // Guard re-entrancy: the submit button stays enabled while the POST is in flight.
    if (creatingRef.current || !requirementForm.formData.title.trim()) return;
    creatingRef.current = true;
    setCreateError('');
    try {
      const created = await api.createRequirement(requirementForm.formData);
      setRequirements((items) => [created, ...items]);
      requirementForm.close();
      requirementForm.reset();
    } catch {
      setCreateError(t('createFailed'));
    } finally {
      creatingRef.current = false;
    }
  };

  const createTestCase = async (event: FormEvent) => {
    event.preventDefault();
    if (creatingRef.current || !caseForm.formData.title.trim()) return;
    creatingRef.current = true;
    setCreateError('');
    try {
      const created = await api.createTestCase({
        ...caseForm.formData,
        steps: caseForm.stepsText.split('\n').map((item) => item.trim()).filter(Boolean),
        tags: caseForm.tagsText.split(',').map((item) => item.trim()).filter(Boolean),
      });
      setTestCases((items) => [created, ...items]);
      caseForm.close();
      caseForm.reset();
    } catch {
      setCreateError(t('createFailed'));
    } finally {
      creatingRef.current = false;
    }
  };

  const renderCaseRows = (items: TestCase[]) => items.map((item) => {
    const linkedRequirement = requirements.find((requirement) => requirement.id === item.requirement_id);
    const feedback = associationFeedback?.caseId === item.id ? associationFeedback : null;
    const canChangeRequirement = canChangeCaseRequirement(item);
    return <tr key={item.id}>
      <td><code className="management-matrix-id">{getCaseDisplayId(item)}</code></td>
      <td><Link className="project-management-item-link" to={workspaceHref(item)}>{item.title}<ArrowUpRight size={14} aria-hidden="true" /></Link>{item.tags.length > 0 && <small>{item.tags.join(' · ')}</small>}</td>
      <td className="project-management-relation-cell">
        {linkedRequirement
          ? <Link className="management-relation-link" to={managementHref('traceability', { trace: linkedRequirement.id })}>{getRequirementDisplayId(linkedRequirement)} · {linkedRequirement.title}</Link>
          : item.requirement_id
            ? <span className="management-relation-unknown">{t('unavailableRequirement')}</span>
            : <span className="is-independent">{t('independentCase')}</span>}
        <label className="project-management-association-control"><span className="project-management-visually-hidden">{t('changeRequirementForCase', { case: item.title })}</span>
          <select value={linkedRequirement?.id ?? ''} disabled={!canChangeRequirement || associationSavingId !== null} onChange={(event) => void saveCaseRequirement(item.id, event.target.value)} aria-describedby={!canChangeRequirement ? `case-requirement-locked-${item.id}` : undefined}>
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
      <td><Link className="btn btn-secondary btn-sm" to={workspaceHref(item)}>{t('openWorkspace')}</Link></td>
    </tr>;
  });

  const visibleCount = tab === 'cases' ? visibleCases.length : visibleRequirements.length;
  const totalCount = tab === 'cases' ? testCases.length : requirements.length;
  const criteriaList = detailCriteria.split('\n').map((item) => item.trim()).filter(Boolean);
  const requirementFilterItem = requirements.find((item) => item.id === selectedRequirementFilter);
  const activeFilters: Array<{ key: string; label: string; clear: Record<string, string> }> = [];
  if (query) activeFilters.push({ key: 'q', label: `${t('searchLabel')}: ${query}`, clear: { q: '' } });
  if (tab === 'cases') {
    if (automationStatus) activeFilters.push({ key: 'status', label: `${t('automationColumn')}: ${t(`automationStatus.${automationStatus}`)}`, clear: { status: '' } });
    if (casePriority) activeFilters.push({ key: 'priority', label: `${common('priority')}: ${casePriority}`, clear: { priority: '' } });
    if (selectedRequirementFilter) activeFilters.push({ key: 'requirement', label: `${t('requirementColumn')}: ${requirementFilterItem ? getRequirementDisplayId(requirementFilterItem) : t('independentCases')}`, clear: { requirement: '' } });
  } else {
    if (requirementStatus) activeFilters.push({ key: 'status', label: `${t('requirementStatusLabel')}: ${t(`requirementStatus.${requirementStatus}`)}`, clear: { status: '' } });
    if (gapFilter) activeFilters.push({ key: 'gap', label: t(gapFilter === 'unlinked' ? 'requirementsWithoutCases' : 'requirementsWithCases'), clear: { gap: '', trace: '' } });
  }

  return <div className="page-container project-management-page">
    <nav className="project-management-breadcrumb" aria-label={common('breadcrumb')}>
      <Link to="/projects">{t('projects')}</Link><span aria-hidden="true">/</span>
      <Link to={`/projects/${encodeURIComponent(projectId)}`}>{project.name}</Link><span aria-hidden="true">/</span>
      <span>{t('title')}</span>
    </nav>
    <header className="page-header project-management-header">
      <div><p className="project-management-eyebrow">{t('projectScope', { project: project.name })}</p>
        <h2>{t('title')}</h2><p className="subtitle">{t('subtitle')}</p></div>
      <div className="project-management-header-actions">
        <button type="button" className="btn btn-primary" onClick={() => {
          setCreateError('');
          if (tab === 'cases') caseForm.open(projectId);
          else requirementForm.open(projectId);
        }}>
          <Plus size={15} aria-hidden="true" />{tab === 'cases' ? t('newCase') : t('newRequirement')}
        </button>
        <button type="button" className="btn btn-secondary" disabled={loading} onClick={() => setReloadVersion((value) => value + 1)}>
          <RefreshCw size={15} aria-hidden="true" />{t('refresh')}
        </button>
      </div>
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
      <button id="management-tab-requirements" type="button" role="tab" aria-selected={tab === 'requirements'} aria-controls="management-panel" className={tab === 'requirements' ? 'selected' : ''}
        onKeyDown={moveTab} onClick={() => switchTab('requirements')}>
        <FileText size={16} aria-hidden="true" />{t('requirementsTab')}<span>{getProjectScopedCount(requirements.length, loadedProjectId, projectId) ?? '—'}</span>
      </button>
      <button id="management-tab-cases" type="button" role="tab" aria-selected={tab === 'cases'} aria-controls="management-panel" className={tab === 'cases' ? 'selected' : ''}
        onKeyDown={moveTab} onClick={() => switchTab('cases')}>
        <ListChecks size={16} aria-hidden="true" />{t('casesTab')}<span>{getProjectScopedCount(testCases.length, loadedProjectId, projectId) ?? '—'}</span>
      </button>
      <button id="management-tab-traceability" type="button" role="tab" aria-selected={tab === 'traceability'} aria-controls="management-panel" className={tab === 'traceability' ? 'selected' : ''}
        onKeyDown={moveTab} onClick={() => switchTab('traceability')}>
        <Network size={16} aria-hidden="true" />{t('traceabilityTab')}
      </button>
    </nav>

    <section id="management-panel" role="tabpanel" aria-labelledby={`management-tab-${tab}`} className="card project-management-panel" aria-busy={loading}>
      <div className="project-management-toolbar">
        <label className="project-management-search">
          <Search size={16} aria-hidden="true" /><span className="project-management-visually-hidden">{t('searchLabel')}</span>
          <input type="search" value={query} onChange={(event) => updateQuery({ q: event.target.value })} placeholder={t('searchPlaceholder')} />
        </label>
        {tab === 'cases' ? <>
          <label className="project-management-filter"><span>{t('automationColumn')}</span><select value={automationStatus} onChange={(event) => updateQuery({ status: event.target.value })}>
            <option value="">{t('allStatuses')}</option>{AUTOMATION_STATUSES.map((value) => <option key={value} value={value}>{t(`automationStatus.${value}`)}</option>)}
          </select></label>
          <label className="project-management-filter"><span>{common('priority')}</span><select value={casePriority} onChange={(event) => updateQuery({ priority: event.target.value })}>
            <option value="">{t('allPriorities')}</option>{PRIORITIES.map((value) => <option key={value} value={value}>{value}</option>)}
          </select></label>
          <label className="project-management-filter"><span>{t('requirementColumn')}</span><select value={selectedRequirementFilter} onChange={(event) => updateQuery({ requirement: event.target.value })}>
            <option value="">{t('allRequirements')}</option><option value={INDEPENDENT_CASES_FILTER}>{t('independentCases')}</option>{requirements.map((item) => <option key={item.id} value={item.id}>{getRequirementDisplayId(item)} · {item.title}</option>)}
          </select></label>
          <label className="project-management-filter"><span>{t('sortBy')}</span><select value={['updated', 'title', 'priority'].includes(sort) ? sort : 'updated'} onChange={(event) => updateQuery({ sort: event.target.value })}>
            <option value="updated">{t('sortUpdated')}</option><option value="title">{t('sortTitle')}</option><option value="priority">{t('sortPriority')}</option>
          </select></label>
        </> : <>
          <label className="project-management-filter"><span>{t('requirementStatusLabel')}</span><select value={requirementStatus} onChange={(event) => updateQuery({ status: event.target.value })}>
            <option value="">{t('allStatuses')}</option>{REQUIREMENT_STATUSES.map((value) => <option key={value} value={value}>{t(`requirementStatus.${value}`)}</option>)}
          </select></label>
          <label className="project-management-filter"><span>{t('relationshipFilter')}</span><select value={gapFilter} onChange={(event) => updateQuery({ gap: event.target.value, trace: '' })}>
            <option value="">{t('allRequirements')}</option><option value="unlinked">{t('requirementsWithoutCases')}</option><option value="linked">{t('requirementsWithCases')}</option>
          </select></label>
          <label className="project-management-filter"><span>{t('sortBy')}</span><select value={['updated', 'title', 'status'].includes(sort) ? sort : 'updated'} onChange={(event) => updateQuery({ sort: event.target.value })}>
            <option value="updated">{t('sortUpdated')}</option><option value="title">{t('sortTitle')}</option><option value="status">{t('sortStatus')}</option>
          </select></label>
        </>}
      </div>
      <p className="project-management-relationship-hint">{tab === 'cases' ? t('caseRelationHint') : tab === 'traceability' ? t('traceabilityHint') : t('requirementRelationHint')}</p>
      {dataReady && <div className="project-management-filter-summary">
        <span role="status">{t('dataScope', { count: visibleCount, total: totalCount })}</span>
        {activeFilters.map((filter) => <button key={filter.key} type="button" className="management-filter-chip" onClick={() => updateQuery(filter.clear)} aria-label={t('removeFilter', { filter: filter.label })}>{filter.label}<X size={12} aria-hidden="true" /></button>)}
        {activeFilters.length > 0 && visibleCount > 0 && <button type="button" className="project-management-inline-action" onClick={() => updateQuery(clearedFilterPatch(tab))}>{t('clearFilters')}</button>}
      </div>}

      {loading && <div className="project-management-state" role="status" aria-busy="true">{t('loading')}</div>}
      {!loading && error && <div className="project-management-state async-state-error" role="alert">
        <span>{t(error === 'forbidden' ? 'forbidden' : 'loadFailed')}</span>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setReloadVersion((value) => value + 1)}>{t('retry')}</button>
      </div>}
      {dataReady && tab !== 'cases' && (requirements.length === 0
        ? <div className="project-management-state"><strong>{t('emptyRequirements')}</strong><p>{t('emptyRequirementsHint')}</p></div>
        : visibleRequirements.length === 0
          ? <div className="project-management-state" role="status">{t('noMatches')} <button type="button" className="btn btn-secondary btn-sm" onClick={() => updateQuery(clearedFilterPatch(tab))}>{t('clearFilters')}</button></div>
          : tab === 'requirements'
            ? <div className="table-responsive project-management-table-wrap"><table className="data-table project-management-table management-matrix-table">
              <thead><tr><th>{t('idColumn')}</th><th>{t('nameColumn')}</th><th>{t('requirementStatusLabel')}</th><th>{t('linkedCasesColumn')}</th><th>{t('updatedColumn')}</th><th>{common('actions')}</th></tr></thead>
              <tbody>{visibleRequirements.map((item) => {
                const linkedCaseCount = caseCounts.get(item.id) ?? 0;
                return <tr key={item.id}>
                  <td><code className="management-matrix-id">{getRequirementDisplayId(item)}</code></td>
                  <td><Link className="project-management-item-link" to={workspaceHref(item)}>{item.title}<ArrowUpRight size={14} aria-hidden="true" /></Link>{item.external_id && <small>{item.external_id}</small>}</td>
                  <td><span className="project-management-status">{t(`requirementStatus.${item.status}`, { defaultValue: item.status })}</span></td>
                  <td className="project-management-relation-cell"><span className={linkedCaseCount === 0 ? 'management-gap-label' : ''}>{linkedCaseCount === 0 ? t('noLinkedCases') : t('linkedCaseCount', { count: linkedCaseCount })}</span>
                    <Link className="project-management-inline-action" to={managementHref('cases', { requirement: item.id })}>{t('manageCases')}</Link>
                  </td>
                  <td>{formatDate(item.updated_at)}</td>
                  <td><div className="project-management-row-actions"><button type="button" className="btn btn-secondary btn-sm" onClick={() => openDetail(item.id)}>{t('details')}</button><Link className="btn btn-secondary btn-sm" to={workspaceHref(item)}>{t('openWorkspace')}</Link></div></td>
                </tr>;
              })}</tbody>
            </table></div>
            : <div className="table-responsive project-management-table-wrap"><table className="data-table project-management-table management-matrix-table management-trace-table">
              <thead><tr><th>{t('traceColumn')}</th><th>{t('idColumn')}</th><th>{t('nameColumn')}</th><th>{t('requirementStatusLabel')}</th><th>{t('linkedCasesColumn')}</th></tr></thead>
              <tbody>{visibleRequirements.map((item) => {
                const linkedCaseCount = caseCounts.get(item.id) ?? 0;
                const expanded = item.id === traceRequirementId;
                const linkedCases = testCases.filter((testCase) => testCase.requirement_id === item.id);
                return <Fragment key={item.id}>
                  <tr>
                    <td><button type="button" className="management-trace-toggle" aria-expanded={expanded} aria-label={t(expanded ? 'collapseRequirement' : 'expandRequirement', { requirement: getRequirementDisplayId(item) })} onClick={() => updateQuery({ trace: expanded ? '' : item.id }, false)}>{expanded ? <ChevronDown size={16} aria-hidden="true" /> : <ChevronRight size={16} aria-hidden="true" />}</button></td>
                    <td><code className="management-matrix-id">{getRequirementDisplayId(item)}</code></td>
                    <td><Link className="project-management-item-link" to={workspaceHref(item)}>{item.title}<ArrowUpRight size={14} aria-hidden="true" /></Link></td>
                    <td><span className="project-management-status">{t(`requirementStatus.${item.status}`, { defaultValue: item.status })}</span></td>
                    <td className="project-management-relation-cell"><span className={linkedCaseCount === 0 ? 'management-gap-label' : ''}>{linkedCaseCount === 0 ? t('noLinkedCases') : t('linkedCaseCount', { count: linkedCaseCount })}</span><Link className="project-management-inline-action" to={managementHref('cases', { requirement: item.id })}>{t('openCases')}</Link></td>
                  </tr>
                  {expanded && <tr key={`${item.id}-expanded`} className="management-trace-expanded-row"><td colSpan={5}>
                    {linkedCases.length > 0
                      ? <ul className="management-trace-case-list">{linkedCases.map((testCase) => <li key={testCase.id}><Link to={workspaceHref(testCase)}><code>{getCaseDisplayId(testCase)}</code><strong>{testCase.title}</strong></Link><span className="project-management-status">{t(`automationStatus.${testCase.automation_status}`, { defaultValue: testCase.automation_status })}</span>{testCase.test_design_id && <span className="management-design-lock">{t('designLinked')}</span>}</li>)}</ul>
                      : <div className="management-trace-empty"><span>{t('noLinkedCases')}</span><Link className="btn btn-secondary btn-sm" to={managementHref('cases', { requirement: item.id })}>{t('linkCases')}</Link></div>}
                  </td></tr>}
                </Fragment>;
              })}</tbody>
            </table></div>)}
      {dataReady && tab === 'cases' && (testCases.length === 0
        ? <div className="project-management-state"><strong>{t('emptyCases')}</strong><p>{t('emptyCasesHint')}</p></div>
        : visibleCases.length === 0
          ? <div className="project-management-state" role="status">{t('noMatches')} <button type="button" className="btn btn-secondary btn-sm" onClick={() => updateQuery(clearedFilterPatch(tab))}>{t('clearFilters')}</button></div>
          : <div className="table-responsive project-management-table-wrap"><table className="data-table project-management-table management-matrix-table management-cases-table">
            <thead><tr><th>{t('idColumn')}</th><th>{t('nameColumn')}</th><th>{t('requirementColumn')}</th><th>{common('priority')}</th><th>{t('automationColumn')}</th><th>{t('updatedColumn')}</th><th>{common('actions')}</th></tr></thead>
            <tbody>{renderCaseRows(visibleCases)}</tbody>
          </table></div>)}
    </section>
    {dataReady && traceRequirement && tab === 'traceability' && <p className="management-trace-focus" role="status">{t('expandedRequirement', { requirement: getRequirementDisplayId(traceRequirement) })}</p>}

    {detailRequirement && <>
      <div className="management-detail-backdrop" onClick={() => updateQuery({ detail: '' }, false)} aria-hidden="true" />
      <aside ref={detailRef} tabIndex={-1} role="dialog" aria-modal="false" aria-labelledby="management-detail-title" className="management-detail-drawer">
        <header className="management-detail-header">
          <div>
            <p className="management-detail-eyebrow">{getRequirementDisplayId(detailRequirement)} · {t('requirementDetails')}</p>
            <h3 id="management-detail-title">{detailRequirement.title}</h3>
          </div>
          <button type="button" className="btn btn-secondary btn-sm" aria-label={t('closeDetails')} onClick={() => updateQuery({ detail: '' }, false)}><X size={15} aria-hidden="true" /></button>
        </header>
        <dl className="management-detail-facts">
          <div><dt>{t('requirementStatusLabel')}</dt><dd><span className="project-management-status">{t(`requirementStatus.${detailRequirement.status}`, { defaultValue: detailRequirement.status })}</span></dd></div>
          <div><dt>{t('relationshipFilter')}</dt><dd>{detailLinkedCases.length === 0 ? t('noLinkedCases') : t('linkedCaseCount', { count: detailLinkedCases.length })}</dd></div>
          <div><dt>{t('updatedAt')}</dt><dd>{formatDate(detailRequirement.updated_at)}</dd></div>
          {(detailRequirement.external_system || detailRequirement.external_id || detailRequirement.external_url) && <div><dt>{t('sourceHeading')}</dt><dd>
            {[detailRequirement.external_system, detailRequirement.external_id].filter(Boolean).join(' · ') || '—'}
            {detailRequirement.external_url && <> · <a href={detailRequirement.external_url} target="_blank" rel="noreferrer noopener">{detailRequirement.external_url}</a></>}
          </dd></div>}
        </dl>
        <section className="management-detail-section">
          <h4>{common('description')}</h4>
          <p>{detailRequirement.description?.trim() || t('noDescription')}</p>
        </section>
        <section className="management-detail-section">
          <div className="management-detail-section-head">
            <h4>{t('acceptanceCriteria')}</h4>
            {!criteriaEditing && <button type="button" className="btn btn-secondary btn-sm" onClick={() => setCriteriaEditing(true)}>{t('editAcceptanceCriteria')}</button>}
          </div>
          {criteriaEditing
            ? <>
              <label className="management-detail-label"><span>{t('criteriaEditorLabel')}</span>
                <textarea className="form-textarea" rows={5} value={criteriaDraft} onChange={(event) => setCriteriaDraft(event.target.value)} />
              </label>
              <div className="management-detail-actions">
                <button type="button" className="btn btn-primary btn-sm" disabled={criteriaSaving} onClick={() => void saveCriteria()}>{t('saveAcceptanceCriteria')}</button>
                <button type="button" className="btn btn-secondary btn-sm" disabled={criteriaSaving} onClick={() => { setCriteriaEditing(false); setCriteriaDraft(detailCriteria); setCriteriaFeedback(null); }}>{common('cancel')}</button>
              </div>
            </>
            : <ol className="management-detail-criteria">{criteriaList.length > 0
              ? criteriaList.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)
              : <li className="is-empty">{t('criteriaEmpty')}</li>}</ol>}
          {criteriaFeedback && <p className={criteriaFeedback.failed ? 'management-detail-feedback is-error' : 'management-detail-feedback is-success'} role={criteriaFeedback.failed ? 'alert' : 'status'}>{criteriaFeedback.message}</p>}
        </section>
        <section className="management-detail-section">
          <div className="management-detail-section-head">
            <h4>{t('linkedCasesColumn')}</h4>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setCreateError(''); caseForm.open(projectId); }}><Plus size={14} aria-hidden="true" />{t('newCase')}</button>
          </div>
          {detailLinkedCases.length === 0
            ? <p>{t('noLinkedCases')}</p>
            : <ul className="management-detail-case-list">{detailLinkedCases.map((item) => <li key={item.id}>
              <Link to={workspaceHref(item)}><code>{getCaseDisplayId(item)}</code>{item.title}</Link>
              <span className="project-management-status">{t(`automationStatus.${item.automation_status}`, { defaultValue: item.automation_status })}</span>
            </li>)}</ul>}
        </section>
        <section className="management-detail-section">
          <h4>{t('linkExistingCase')}</h4>
          {detailUnlinkedCases.length === 0
            ? <p>{t('noUnlinkedCases')}</p>
            : <>
              <label className="management-detail-label"><span>{t('selectCaseLabel')}</span>
                <select className="form-select" value={linkCaseId} disabled={linkSaving} onChange={(event) => setLinkCaseId(event.target.value)}>
                  <option value="">{t('selectCasePlaceholder')}</option>
                  {detailUnlinkedCases.map((item) => <option key={item.id} value={item.id}>{getCaseDisplayId(item)} · {item.title}</option>)}
                </select>
              </label>
              <div className="management-detail-actions">
                <button type="button" className="btn btn-primary btn-sm" disabled={!linkCaseId || linkSaving} onClick={() => void linkCase()}>{t('linkCaseAction')}</button>
              </div>
            </>}
          {linkFeedback && <p className={linkFeedback.failed ? 'management-detail-feedback is-error' : 'management-detail-feedback is-success'} role={linkFeedback.failed ? 'alert' : 'status'}>{linkFeedback.message}</p>}
        </section>
      </aside>
    </>}

    <RequirementFormModal
      isOpen={requirementForm.isOpen}
      projects={projects}
      formData={requirementForm.formData}
      setFormData={requirementForm.setFormData}
      onSubmit={createRequirement}
      onClose={requirementForm.close}
      error={createError}
    />
    <TestCaseFormModal
      isOpen={caseForm.isOpen}
      projects={projects}
      formData={caseForm.formData}
      setFormData={caseForm.setFormData}
      stepsText={caseForm.stepsText}
      setStepsText={caseForm.setStepsText}
      tagsText={caseForm.tagsText}
      setTagsText={caseForm.setTagsText}
      onSubmit={createTestCase}
      onClose={caseForm.close}
      error={createError}
    />
  </div>;
}
