import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Drawer,
  DrawerContent,
  DrawerTitle,
  FormField,
  IconButton,
  Input,
  Heading,
  Inline,
  Progress,
  SearchInput,
  Stack,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Table,
  Textarea,
} from '@self/ui-style/react';
import {
  ShieldCheck,
  Target,
  Activity,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Zap,
  Plus,
  PlayCircle,
  ChevronDown,
  Search,
  ArrowRight,
} from 'lucide-react';
import {
  ImpactAnalysisResult,
  Project,
  QualityCoverageSummary,
  QualityRiskLevel,
  QualityRiskMatrix,
  Release,
  ReleaseGateReport,
  TestCase,
} from '../types';
import { api } from '../api/client';
import { APIError } from '../api/errors';
import { buildWorkspaceHref } from '../app/workspaceContext';
import { hasInsufficientQualityEvidence, measuredPercentage } from './qualityMetricsModel';
import './QualityPage.css';

interface QualityPageProps {
  projects?: Project[];
  selectedProjectId: string | null;
  onNavigateToRuns?: (runId?: string) => void;
}

export const QualityPage: React.FC<QualityPageProps> = ({
  projects = [],
  selectedProjectId,
  onNavigateToRuns,
}) => {
  const { t } = useTranslation('quality');
  const getCoverageStatusLabel = (status: string) => {
    if (status === 'READY') return t('coverageStatusReady');
    if (status === 'DRAFT') return t('coverageStatusDraft');
    return status;
  };
  const [activeTab, setActiveTab] = useState<'coverage' | 'risks' | 'impact' | 'releases'>('coverage');
  const [impactError, setImpactError] = useState('');

  // Coverage & Risks state
  const [coverage, setCoverage] = useState<QualityCoverageSummary | null>(null);
  const [testCases, setTestCases] = useState<TestCase[] | null>(null);
  const [coverageQuery, setCoverageQuery] = useState('');
  const [coverageStatus, setCoverageStatus] = useState('ALL');
  const [coverageSort, setCoverageSort] = useState<'title' | 'coverage-desc' | 'coverage-asc'>('coverage-desc');
  const [groupCoverageByStatus, setGroupCoverageByStatus] = useState(false);
  const [expandedCoverageId, setExpandedCoverageId] = useState<string | null>(null);
  const [testCasesSourceError, setTestCasesSourceError] = useState(false);
  const [qualityLoadError, setQualityLoadError] = useState<'forbidden' | 'failed' | null>(null);
  const [riskMatrix, setRiskMatrix] = useState<QualityRiskMatrix | null>(null);
  const [loadingMetrics, setLoadingMetrics] = useState<boolean>(true);
  const qualityRequestVersion = useRef(0);

  // Impact Analysis state
  const [changedFilesText, setChangedFilesText] = useState<string>('');
  const [impactResult, setImpactResult] = useState<ImpactAnalysisResult | null>(null);
  const [loadingImpact, setLoadingImpact] = useState<boolean>(false);

  // Releases state
  const [releases, setReleases] = useState<Release[]>([]);
  const [showCreateReleaseModal, setShowCreateReleaseModal] = useState<boolean>(false);
  const createReleaseTriggerRef = useRef<HTMLButtonElement>(null);
  const [newReleaseVersion, setNewReleaseVersion] = useState<string>('');
  const [newReleaseName, setNewReleaseName] = useState<string>('');
  const [newReleaseTargetDate, setNewReleaseTargetDate] = useState<string>('');
  const [newReleaseThreshold, setNewReleaseThreshold] = useState<number>(95.0);
  const [creatingRelease, setCreatingRelease] = useState<boolean>(false);
  const [releaseActionError, setReleaseActionError] = useState<string | null>(
    null,
  );

  // Gate Report state
  const [selectedGateReport, setSelectedGateReport] = useState<ReleaseGateReport | null>(null);
  const gateEvaluateTriggerRef = useRef<HTMLButtonElement>(null);
  const [evaluatingGateId, setEvaluatingGateId] = useState<string | null>(null);
  const riskCount = riskMatrix?.risks.length ?? t('notAvailable');
  const releaseCount = !selectedProjectId || loadingMetrics || qualityLoadError ? t('notAvailable') : releases.length;
  const qualityTabs = [
    { id: 'coverage' as const, label: t('tabCoverage') },
    { id: 'risks' as const, label: t('tabRisks', { value: riskCount }) },
    { id: 'impact' as const, label: t('tabImpact') },
    { id: 'releases' as const, label: t('tabReleases', { value: releaseCount }) },
  ];

  const fetchQualityData = useCallback(async () => {
    const requestVersion = ++qualityRequestVersion.current;
    setQualityLoadError(null);
    setTestCasesSourceError(false);
    if (!selectedProjectId) {
      setCoverage(null);
      setTestCases(null);
      setRiskMatrix(null);
      setReleases([]);
      setLoadingMetrics(false);
      return;
    }
    setLoadingMetrics(true);
    setCoverage(null);
    setTestCases(null);
    setRiskMatrix(null);
    setReleases([]);
    try {
      const [cov, risks, rels] = await Promise.all([
        api.getQualityCoverage(selectedProjectId),
        api.getQualityRiskMatrix(selectedProjectId),
        api.getReleases(selectedProjectId),
      ]);
      if (requestVersion !== qualityRequestVersion.current) return;
      setCoverage(cov);
      setRiskMatrix(risks);
      setReleases(rels);
      try {
        setTestCases(await api.getTestCases(selectedProjectId));
      } catch (error) {
        if (requestVersion !== qualityRequestVersion.current) return;
        console.error('Failed to fetch test case bindings for quality coverage', error);
        setTestCases(null);
        setTestCasesSourceError(true);
      }
    } catch (err) {
      if (requestVersion !== qualityRequestVersion.current) return;
      console.error('Failed to fetch quality intelligence data', err);
      setCoverage(null);
      setRiskMatrix(null);
      setReleases([]);
      setTestCases(null);
      setQualityLoadError(err instanceof APIError && err.status === 403 ? 'forbidden' : 'failed');
    } finally {
      if (requestVersion === qualityRequestVersion.current) setLoadingMetrics(false);
    }
  }, [selectedProjectId]);

  const coveragePercentageByRequirement = useMemo(
    () => new Map((coverage?.requirement_details ?? []).map((item) => [item.requirement_id, item.coverage_percentage])),
    [coverage?.requirement_details],
  );
  const riskWorkspaceHref = (risk: QualityRiskMatrix['risks'][number]) => {
    const explicitCaseId = risk.id.startsWith('risk_p0_') ? risk.id.slice('risk_p0_'.length) : undefined;
    const linkedCase = testCases?.find((item) => {
      if (item.id === explicitCaseId) return true;
      const nodeid = item.binding?.nodeid;
      return Boolean(nodeid && risk.impacted_nodeids.includes(nodeid));
    });
    if (linkedCase) {
      return buildWorkspaceHref({
        projectId: selectedProjectId ?? undefined,
        requirementId: linkedCase.requirement_id ?? undefined,
        testCaseId: linkedCase.id,
        stage: 'cases',
        view: 'cases',
      });
    }
    if (risk.id.startsWith('risk_fail_')) {
      return buildWorkspaceHref({
        projectId: selectedProjectId ?? undefined,
        failureId: risk.id.slice('risk_fail_'.length),
        stage: 'failure',
        view: 'results',
      });
    }
    return null;
  };
  const testCasesByRequirement = useMemo(() => {
    const grouped = new Map<string, TestCase[]>();
    for (const testCase of testCases ?? []) {
      if (!testCase.requirement_id) continue;
      const group = grouped.get(testCase.requirement_id) ?? [];
      group.push(testCase);
      grouped.set(testCase.requirement_id, group);
    }
    return grouped;
  }, [testCases]);
  const coverageStatuses = useMemo(
    () => [...new Set((coverage?.requirement_details ?? []).map((item) => item.status))].sort(),
    [coverage?.requirement_details],
  );
  const filteredCoverage = useMemo(() => {
    const query = coverageQuery.trim().toLocaleLowerCase();
    const rows = (coverage?.requirement_details ?? []).filter((item) => {
      const matchesQuery = !query || `${item.title} ${item.requirement_id}`.toLocaleLowerCase().includes(query);
      const matchesStatus = coverageStatus === 'ALL' || item.status === coverageStatus;
      return matchesQuery && matchesStatus;
    });
    const percentageFor = (requirementId: string) => coveragePercentageByRequirement.get(requirementId);
    rows.sort((left, right) => {
      if (coverageSort === 'title') return left.title.localeCompare(right.title);
      const leftPercentage = percentageFor(left.requirement_id);
      const rightPercentage = percentageFor(right.requirement_id);
      if (leftPercentage === undefined && rightPercentage === undefined) return left.title.localeCompare(right.title);
      if (leftPercentage === undefined) return 1;
      if (rightPercentage === undefined) return -1;
      const difference = coverageSort === 'coverage-desc'
        ? rightPercentage - leftPercentage
        : leftPercentage - rightPercentage;
      return difference || left.title.localeCompare(right.title);
    });
    return rows;
  }, [coverage?.requirement_details, coveragePercentageByRequirement, coverageQuery, coverageSort, coverageStatus]);
  const coverageGroups = useMemo(() => {
    if (!groupCoverageByStatus) return [{ status: '', items: filteredCoverage }];
    const byStatus = new Map<string, typeof filteredCoverage>();
    for (const item of filteredCoverage) {
      const group = byStatus.get(item.status) ?? [];
      group.push(item);
      byStatus.set(item.status, group);
    }
    return [...byStatus].sort(([left], [right]) => left.localeCompare(right)).map(([status, items]) => ({ status, items }));
  }, [filteredCoverage, groupCoverageByStatus]);
  const currentProject = projects.find((project) => project.id === selectedProjectId) ?? null;
  const evidenceIncomplete = coverage ? hasInsufficientQualityEvidence(coverage) : false;
  const requirementCoverage = coverage ? measuredPercentage(coverage.requirement_coverage_pct, coverage.total_requirements) : null;
  const automationCoverage = coverage ? measuredPercentage(coverage.automation_coverage_pct, coverage.total_test_cases) : null;
  const executionCoverage = coverage ? measuredPercentage(coverage.execution_coverage_pct, coverage.total_test_cases) : null;

  useEffect(() => {
    void fetchQualityData();
    return () => { qualityRequestVersion.current += 1; };
  }, [fetchQualityData]);

  const handleRunImpactAnalysis = async () => {
    if (!selectedProjectId) return;
    try {
      setLoadingImpact(true);
      setImpactError('');
      const files = changedFilesText
        .split('\n')
        .map((l) => l.trim())
        .filter(Boolean);
      const res = await api.analyzeImpact(selectedProjectId, {
        project_id: selectedProjectId,
        changed_files: files,
      });
      setImpactResult(res);
    } catch (err) {
      console.error('Impact analysis failed', err);
      setImpactError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoadingImpact(false);
    }
  };

  const handleCreateRelease = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProjectId || !newReleaseVersion || !newReleaseName) return;
    try {
      setCreatingRelease(true);
      setReleaseActionError(null);
      const created = await api.createRelease({
        project_id: selectedProjectId,
        version: newReleaseVersion,
        name: newReleaseName,
        target_date: newReleaseTargetDate,
        pass_rate_threshold: newReleaseThreshold,
      });
      setReleases([created, ...releases]);
      setShowCreateReleaseModal(false);
      setNewReleaseVersion('');
      setNewReleaseName('');
      setNewReleaseTargetDate('');
    } catch (err) {
      console.error('Failed to create release', err);
      // Keep the modal open, but tell the user why nothing happened.
      setReleaseActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setCreatingRelease(false);
    }
  };

  const handleEvaluateGate = async (releaseId: string) => {
    try {
      setEvaluatingGateId(releaseId);
      setReleaseActionError(null);
      const report = await api.evaluateReleaseGate(releaseId);
      setSelectedGateReport(report);
      // Refresh releases
      if (selectedProjectId) {
        const rels = await api.getReleases(selectedProjectId);
        setReleases(rels);
      }
    } catch (err) {
      console.error('Failed to evaluate release gate', err);
      setReleaseActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setEvaluatingGateId(null);
    }
  };

  const getRiskBadge = (level: QualityRiskLevel, translate: TFunction) => {
    switch (level) {
      case 'LOW':
        return <Badge tone="success"><CheckCircle2 size={12} aria-hidden="true" />{translate('riskLevelLow')}</Badge>;
      case 'MEDIUM':
        return <Badge tone="warn"><ShieldCheck size={12} aria-hidden="true" />{translate('riskLevelMedium')}</Badge>;
      case 'HIGH':
        return <Badge tone="danger"><XCircle size={12} aria-hidden="true" />{translate('riskLevelHigh')}</Badge>;
      case 'CRITICAL':
        return <Badge tone="danger"><XCircle size={12} aria-hidden="true" />{translate('riskLevelCritical')}</Badge>;
      default:
        return <Badge>{level}</Badge>;
    }
  };

  return (
    <Stack className="quality-page" gap={5}>
      <header className="quality-page-header">
        <div>
          <Heading>{t('titles:quality')}</Heading>
          <p className="quality-subtitle">{t('subtitle')}</p>
          {currentProject && <p className="quality-project-context">{t('currentProject', { project: currentProject.name })}</p>}
        </div>
        <Inline className="quality-page-actions">
          <Button variant="secondary" onClick={() => void fetchQualityData()} disabled={loadingMetrics || !selectedProjectId}>
            <RefreshCw size={14} className={loadingMetrics ? 'spinning' : ''} />
            <span>{t('common:refresh')}</span>
          </Button>
          <Button ref={createReleaseTriggerRef} variant="primary" onClick={() => setShowCreateReleaseModal(true)} disabled={!selectedProjectId}>
            <Plus size={14} />
            <span>{t('newRelease')}</span>
          </Button>
        </Inline>
      </header>

      {!selectedProjectId && <Alert className="quality-context-notice">
        <span>{t('noProjectSelected')}</span><Link className="ds-link" to="/projects">{t('goToProjects')}</Link>
      </Alert>}
      {qualityLoadError && <Alert className="quality-data-error" role="alert">
        <span>{t(qualityLoadError === 'forbidden' ? 'qualityLoadForbidden' : 'qualityLoadFailed')}</span>
        <Button type="button" variant="secondary" size="sm" onClick={() => void fetchQualityData()} disabled={loadingMetrics}>{t('common:refresh')}</Button>
      </Alert>}

      <section className="ds-metrics quality-overview" aria-label={t('overviewTitle')} aria-busy={loadingMetrics}>
        <Card className="quality-posture">
          <div className="quality-posture-main">
            <span className="ds-metric-icon" aria-hidden="true">
              <ShieldCheck size={20} />
            </span>
            <div>
              <h3 className="ds-metric-label">{t('metricQualityHealth')}</h3>
              <div className="ds-metric-value">
                {riskMatrix ? <><strong>{riskMatrix.overall_quality_score}</strong><span>/100</span></> : '--'}
              </div>
            </div>
          </div>
          <div className="quality-posture-footer">
            <div className="quality-posture-risk">
              {riskMatrix
                ? evidenceIncomplete ? <Badge tone="warn">{t('evidenceIncompleteShort')}</Badge> : getRiskBadge(riskMatrix.overall_risk_level, t)
                : <span className="quality-risk-unavailable">{loadingMetrics ? t('coverageLoading') : t('notAvailable')}</span>}
              {riskMatrix && (
                <span className="quality-posture-p0">
                  <span aria-hidden="true">{t('p0UnautomatedShort', { value: riskMatrix.unautomated_p0_count })}</span>
                  <span className="quality-coverage-visually-hidden">{t('p0Unautomated', { value: riskMatrix.unautomated_p0_count })}</span>
                </span>
              )}
            </div>
            <div className="quality-posture-high-risk">
              <Badge tone={riskMatrix?.high_risk_count ? 'danger' : 'neutral'}>
                {t('metricHighRiskAreas')} {riskMatrix ? riskMatrix.high_risk_count : '--'}
              </Badge>
            </div>
          </div>
          <div className="quality-posture-actions">
            {riskMatrix?.high_risk_count ? <Button
              className="quality-posture-risk-link"
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setActiveTab('risks')}
            >{t('viewRiskDetails')}<ArrowRight size={13} aria-hidden="true" /></Button> : null}
            {riskMatrix && (
              <details className="quality-score-method">
                <summary>{t('qualityScoreMethod')}</summary>
                <p>{t('metricQualityHealthFormula')}</p>
              </details>
            )}
          </div>
          {riskMatrix && coverage && evidenceIncomplete && <p className="quality-evidence-note" role="note">
            {t('riskEvidenceIncomplete', { requirements: coverage.total_requirements, executed: coverage.executed_cases_recent })}
          </p>}
        </Card>

        <div className="quality-coverage-signals">
          {[
            {
              icon: Target,
              label: t('metricRequirementCoverage'),
              value: coverage ? requirementCoverage === null ? t('notAvailable') : `${requirementCoverage}%` : '--',
              detail: coverage
                ? coverage.total_requirements > 0
                  ? t('requirementsCoverageCount', { covered: coverage.covered_requirements, total: coverage.total_requirements })
                  : t('requirementsCoverageUnavailable')
                : qualityLoadError ? t('qualityLoadFailed') : loadingMetrics ? t('coverageLoading') : t('noProjectSelected'),
            },
            {
              icon: Zap,
              label: t('metricAutomationCoverage'),
              value: coverage ? automationCoverage === null ? t('notAvailable') : `${automationCoverage}%` : '--',
              detail: coverage
                ? coverage.total_test_cases > 0
                  ? t('casesAutomatedCount', { automated: coverage.automated_cases, total: coverage.total_test_cases })
                  : t('casesCoverageUnavailable')
                : qualityLoadError ? t('qualityLoadFailed') : loadingMetrics ? t('coverageLoading') : t('noProjectSelected'),
            },
            {
              icon: Activity,
              label: t('metricExecutionCoverage'),
              value: coverage ? executionCoverage === null ? t('notAvailable') : `${executionCoverage}%` : '--',
              detail: coverage
                ? coverage.total_test_cases > 0
                  ? t('casesExecutedRecent', { executed: coverage.executed_cases_recent, total: coverage.total_test_cases })
                  : t('casesCoverageUnavailable')
                : qualityLoadError ? t('qualityLoadFailed') : loadingMetrics ? t('coverageLoading') : t('noProjectSelected'),
            },
          ].map(({ icon: Icon, label, value, detail }) => (
            <article className="ds-metric quality-coverage-signal" key={label}>
              <span className="ds-metric-icon" aria-hidden="true"><Icon size={18} /></span>
              <span className="ds-metric-label">{label}</span>
              <strong className="ds-metric-value">{value}</strong>
              <span className="ds-metric-note">{detail}</span>
            </article>
          ))}
        </div>
      </section>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as typeof activeTab)}>
        <TabsList className="quality-tabs" aria-label={t('tabsLabel')}>
          {qualityTabs.map((tab) => <TabsTrigger key={tab.id} value={tab.id}>{tab.label}</TabsTrigger>)}
        </TabsList>
        <TabsContent value={activeTab} className="quality-tabpanel">

      {/* Tab 1: Coverage Details */}
      {activeTab === 'coverage' && (
        <Card className="quality-card">
          <div className="ds-card-head quality-card-heading quality-coverage-heading">
            <h3>{t('coverageTitle')}</h3>
            <div className="quality-coverage-heading-meta">
              <span className="quality-coverage-count" role="status">
                {coverage
                  ? t('coverageResultCount', { visible: filteredCoverage.length, total: coverage.requirement_details.length })
                  : loadingMetrics ? t('coverageLoading') : qualityLoadError ? t('qualityLoadFailed') : t('noProjectSelected')}
              </span>
              <details className="quality-coverage-method">
                <summary>{t('coverageScoreMethod')}</summary>
                <p>{t('coverageHint')}</p>
              </details>
            </div>
          </div>
          {testCasesSourceError && (
            <p className="quality-source-status" role="status">
              {t('testCasesSourceUnavailable')}
            </p>
          )}
          <div className="quality-coverage-toolbar" role="search">
            <div className="ds-search quality-coverage-search">
              <SearchInput aria-label={t('coverageSearchLabel')} value={coverageQuery} onChange={(event) => setCoverageQuery(event.target.value)} placeholder={t('coverageSearchPlaceholder')} />
              <Search className="ds-ico" size={15} aria-hidden="true" />
            </div>
            <label className="quality-coverage-control">
              <span>{t('coverageStatusLabel')}</span>
              <Select value={coverageStatus} onValueChange={setCoverageStatus}>
                <SelectTrigger aria-label={t('coverageStatusLabel')}>
                  <SelectValue>{coverageStatus === 'ALL' ? t('coverageAllStatuses') : getCoverageStatusLabel(coverageStatus)}</SelectValue>
                </SelectTrigger>
                <SelectContent className="quality-coverage-menu" position="popper">
                  <SelectItem className="ds-menu-item" value="ALL">{t('coverageAllStatuses')}</SelectItem>
                  {coverageStatuses.map((status) => <SelectItem className="ds-menu-item" key={status} value={status}>{getCoverageStatusLabel(status)}</SelectItem>)}
                </SelectContent>
              </Select>
            </label>
            <label className="quality-coverage-control quality-coverage-sort">
              <span>{t('coverageSortLabel')}</span>
              <Select value={coverageSort} onValueChange={(value) => setCoverageSort(value as typeof coverageSort)}>
                <SelectTrigger aria-label={t('coverageSortLabel')}>
                  <SelectValue>
                    {coverageSort === 'coverage-desc'
                      ? t('coverageSortHighest')
                      : coverageSort === 'coverage-asc' ? t('coverageSortLowest') : t('coverageSortTitle')}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent className="quality-coverage-menu" position="popper">
                  <SelectItem className="ds-menu-item" value="coverage-desc">{t('coverageSortHighest')}</SelectItem>
                  <SelectItem className="ds-menu-item" value="coverage-asc">{t('coverageSortLowest')}</SelectItem>
                  <SelectItem className="ds-menu-item" value="title">{t('coverageSortTitle')}</SelectItem>
                </SelectContent>
              </Select>
            </label>
            <label className="quality-coverage-group-toggle">
              <Checkbox checked={groupCoverageByStatus} aria-label={t('coverageGroupByStatus')} onCheckedChange={(checked) => setGroupCoverageByStatus(checked === true)} />
              <span>{t('coverageGroupByStatus')}</span>
            </label>
          </div>
          <p className="quality-coverage-scroll-hint">{t('coverageScrollHint')}</p>
          <div
            className="table-responsive quality-coverage-scroll"
            role="region"
            aria-label={t('coverageTitle')}
            aria-description={t('coverageScrollHint')}
            tabIndex={0}
          >
          <Table className="quality-coverage-table">
              <thead>
                <tr>
                  <th>{t('colRequirementTitle')}</th>
                  <th>{t('common:status')}</th>
                  <th>{t('colTestDesigns')}</th>
                  <th>{t('colTotalCases')}</th>
                  <th>{t('colAutomated')}</th>
                  <th>{t('colCoveragePct')}</th>
                  <th>{t('colHasAutomation')}</th>
                </tr>
              </thead>
              {filteredCoverage.length === 0 ? (
                <tbody><tr><td colSpan={7} className="text-center text-secondary py-4">
                  {loadingMetrics ? t('coverageLoading')
                    : qualityLoadError ? t(qualityLoadError === 'forbidden' ? 'qualityLoadForbidden' : 'qualityLoadFailed')
                      : !selectedProjectId ? t('noProjectSelected')
                        : coverage?.total_requirements === 0 ? <div className="quality-coverage-empty">
                          <p>{t('coverageEmpty')}</p>
                          <Link to={buildWorkspaceHref({ projectId: selectedProjectId, stage: 'requirement', view: 'requirement' })}>{t('openRequirements')} <ArrowRight size={13} aria-hidden="true" /></Link>
                        </div>
                          : coverage?.requirement_details.length === 0 ? t('coverageDetailsUnavailable') : t('coverageNoMatches')}
                </td></tr></tbody>
              ) : coverageGroups.map(({ status, items }) => (
                <tbody key={status || 'all'}>
                  {status && <tr className="quality-coverage-group-row"><th colSpan={7}>{getCoverageStatusLabel(status)}</th></tr>}
                  {items.map((item) => {
                    const requirementCoverage = coveragePercentageByRequirement.get(item.requirement_id) ?? 0;
                    const linkedCases = testCasesByRequirement.get(item.requirement_id) ?? [];
                    const expanded = expandedCoverageId === item.requirement_id;
                    const detailId = `coverage-detail-${item.requirement_id}`;
                    const requirementHref = buildWorkspaceHref({
                      projectId: selectedProjectId ?? undefined,
                      requirementId: item.requirement_id,
                      stage: 'requirement',
                      view: 'requirement',
                    });
                    return (
                      <React.Fragment key={item.requirement_id}>
                        <tr>
                          <td className="quality-coverage-title-cell">
                            <IconButton
                              className="quality-coverage-expand"
                              variant="ghost"
                              type="button"
                              aria-label={t(expanded ? 'coverageCollapseDetails' : 'coverageExpandDetails', { title: item.title })}
                              aria-expanded={expanded}
                              aria-controls={expanded ? detailId : undefined}
                              onClick={() => setExpandedCoverageId(expanded ? null : item.requirement_id)}
                            >
                              <ChevronDown size={15} aria-hidden="true" />
                            </IconButton>
                            <div>
                              <Link className="quality-coverage-link" to={requirementHref}>{item.title}</Link>
                              <small>{item.requirement_id}</small>
                            </div>
                          </td>
                          <td><Badge>{getCoverageStatusLabel(item.status)}</Badge></td>
                          <td>{item.test_design_count}</td>
                          <td>{coverage ? item.test_case_count : '--'}</td>
                          <td>{coverage ? item.automated_case_count : '--'}</td>
                          <td>
                            <div className="quality-coverage-meter">
                              <Progress value={coverage ? requirementCoverage : 0} label={`${item.title}: ${t('colCoveragePct')}`} />
                              <span>{coverage ? t('coverageScoreValue', { value: requirementCoverage }) : '--'}</span>
                            </div>
                          </td>
                          <td>{coverage
                            ? item.has_automation
                              ? <Badge tone="success"><CheckCircle2 size={12} aria-hidden="true" />{t('common:yes')}</Badge>
                              : <Badge tone="danger"><XCircle size={12} aria-hidden="true" />{t('common:no')}</Badge>
                            : '--'}</td>
                        </tr>
                        {expanded && <tr className="quality-coverage-detail-row"><td colSpan={7}>
                          <section id={detailId} className="quality-coverage-detail">
                            <div className="quality-coverage-detail-summary">
                              <div><span>{t('coverageRequirement')}</span><Link to={requirementHref}>{item.title}</Link></div>
                              <div><span>{t('coverageStatusLabel')}</span><strong>{getCoverageStatusLabel(item.status)}</strong></div>
                              <div><span>{t('coverageLinkedTests', { count: linkedCases.length })}</span><strong>{item.test_case_count}</strong></div>
                            </div>
                            <div className="quality-coverage-linked-tests">
                              <h4>{t('coverageLinkedTestsTitle')}</h4>
                              {testCases === null ? <p className="text-secondary">{t('testCasesSourceUnavailable')}</p>
                                : linkedCases.length === 0 ? <p className="text-secondary">{t('coverageNoCases')}</p>
                                  : <ul>{linkedCases.map((testCase) => {
                                      const status = testCase.binding?.status ?? testCase.automation_status;
                                      const tone = status === 'ACTIVE' ? 'success' : status === 'MANUAL' ? 'warn' : 'neutral';
                                      return (
                                        <li key={testCase.id}>
                                        <Link to={buildWorkspaceHref({
                                          projectId: selectedProjectId ?? undefined,
                                          requirementId: item.requirement_id,
                                          testCaseId: testCase.id,
                                          stage: 'cases',
                                          view: 'cases',
                                        })}>{testCase.title}</Link>
                                        <Badge tone={tone}>{status}</Badge>
                                        </li>
                                      );
                                    })}</ul>}
                            </div>
                          </section>
                        </td></tr>}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              ))}
            </Table>
          </div>
        </Card>
      )}

      {/* Tab 2: Quality Risk List */}
      {activeTab === 'risks' && (
        <Card className="quality-card">
          <div className="ds-card-head quality-card-heading">
            <h3>{t('risksTitle')}</h3>
            <span className="text-secondary text-sm">{t('risksHint')}</span>
          </div>
          <div className="quality-risk-list">
            {loadingMetrics ? <div className="quality-data-message" role="status">{t('coverageLoading')}</div>
              : qualityLoadError ? <div className="quality-data-message" role="status">{t(qualityLoadError === 'forbidden' ? 'qualityLoadForbidden' : 'qualityLoadFailed')}</div>
                : !selectedProjectId ? <div className="quality-data-message" role="status">{t('noProjectSelected')}</div>
                  : riskMatrix && riskMatrix.risks.length > 0 ? (
              riskMatrix.risks.map((risk) => {
                const riskHref = riskWorkspaceHref(risk);
                return (
                <Card key={risk.id} className="quality-risk-card">
                  <div className="quality-risk-heading">
                    <div className="quality-risk-title">
                      {riskHref
                        ? <Link className="quality-risk-link" to={riskHref}>{risk.area}</Link>
                        : <span className="quality-risk-area">{risk.area}</span>}
                      {getRiskBadge(risk.risk_level, t)}
                    </div>
                    <div className="quality-risk-score">
                      {t('riskScore', { value: risk.score })}
                    </div>
                  </div>

                  <div className="quality-risk-section">
                    <div className="quality-risk-label">{t('riskReasons')}</div>
                    <ul>
                      {risk.reasons.map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                  </div>

                  {risk.recommended_actions.length > 0 && (
                    <div className="quality-risk-actions">
                      <div className="quality-risk-label">
                        {t('riskRecommendedActions')}
                      </div>
                      <ul>
                        {risk.recommended_actions.map((act, i) => (
                          <li key={i}>{act}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </Card>
                );
              })
            ) : (
              <div className="text-center text-secondary py-4">{t('risksEmpty')}</div>
            )}
          </div>
        </Card>
      )}

      {/* Tab 3: Git Impact & Regression Selector */}
      {activeTab === 'impact' && (
        <Card className="quality-impact-card">
          <div style={{ marginBottom: '1.5rem' }}>
            <h3>{t('impactTitle')}</h3>
            <p className="text-secondary text-sm">{t('impactHint')}</p>
          </div>

          <div style={{ marginBottom: '1.5rem' }}>
            <label className="quality-impact-label" htmlFor="quality-changed-files">
              {t('impactChangedFilesLabel')}
            </label>
            <Textarea
              id="quality-changed-files"
              className="quality-impact-input"
              rows={4}
              placeholder={t('impactChangedFilesPlaceholder')}
              value={changedFilesText}
              onChange={(e) => setChangedFilesText(e.target.value)}
            />
            <div style={{ display: 'flex', gap: '10px', marginTop: '10px' }}>
              <Button
                type="button"
                variant="primary"
                onClick={handleRunImpactAnalysis}
                disabled={loadingImpact}
              >
                <Zap size={14} className={loadingImpact ? 'spinning' : ''} />
                <span>{loadingImpact ? t('impactAnalyzing') : t('impactAnalyze')}</span>
              </Button>
            </div>
          </div>
          {impactError && <Alert className="quality-action-error" role="alert">{t('impactActionFailed', { message: impactError })}</Alert>}

          {impactResult && (
            <Card>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                <h4>{t('impactResultsTitle')}</h4>
                <Badge tone="info">
                  {t('impactConfidence', { value: Math.round(impactResult.confidence_score * 100) })}
                </Badge>
              </div>

              <div style={{ marginBottom: '1rem' }}>
                <div style={{ fontWeight: 600, fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{t('impactRationale')}</div>
                <ul style={{ margin: '4px 0 10px 1.2rem', fontSize: '0.9rem' }}>
                  {impactResult.rationale.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div style={{ background: 'var(--bg-base)', padding: '10px', borderRadius: 'var(--r-xs)' }}>
                  <div style={{ fontWeight: 600, fontSize: '0.85rem', marginBottom: '6px' }}>
                    {t('impactRequirements', { value: impactResult.impacted_requirements.length })}
                  </div>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    {impactResult.impacted_requirements.join(', ') || t('impactNoneIdentified')}
                  </div>
                </div>

                <div style={{ background: 'var(--bg-base)', padding: '10px', borderRadius: 'var(--r-xs)' }}>
                  <div style={{ fontWeight: 600, fontSize: '0.85rem', marginBottom: '6px' }}>
                    {t('impactTestCases', { value: impactResult.impacted_test_cases.length })}
                  </div>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    {impactResult.impacted_test_cases.join(', ') || t('impactNoneIdentified')}
                  </div>
                </div>
              </div>

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>
                    {t('impactRecommendedSuite', {
                      value: impactResult.recommended_regression_tests.length,
                    })}
                  </div>
                  {onNavigateToRuns && impactResult.recommended_regression_tests.length > 0 && (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => onNavigateToRuns()}
                    >
                      <PlayCircle size={14} />
                      <span>{t('impactExecuteInRunner')}</span>
                    </Button>
                  )}
                </div>
                <div
                  style={{
                    backgroundColor: 'var(--bg-base)',
                    padding: '10px',
                    borderRadius: 'var(--r-xs)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.85rem',
                    maxHeight: '180px',
                    overflowY: 'auto',
                  }}
                >
                  {impactResult.recommended_regression_tests.map((node, i) => (
                    <div key={i} style={{ padding: '2px 0' }}>
                      • {node}
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          )}
        </Card>
      )}

      {/* Tab 4: Releases & Gate Dashboard */}
      {activeTab === 'releases' && (
        <>
          {releaseActionError && (
            <Alert role="alert" className="quality-action-error">
              {t('releaseActionFailed', { message: releaseActionError })}
            </Alert>
          )}
        <Card className="quality-card">
          <div className="ds-card-head quality-card-heading">
            <h3>{t('releasesTitle')}</h3>
            <span className="text-secondary text-sm">{t('releasesHint')}</span>
          </div>
          <div className="table-responsive">
            <Table className="quality-releases-table">
              <thead>
                <tr>
                  <th>{t('colVersion')}</th>
                  <th>{t('colReleaseName')}</th>
                  <th>{t('common:status')}</th>
                  <th>{t('colTargetDate')}</th>
                  <th>{t('colPassRateThreshold')}</th>
                  <th>{t('colQualityScore')}</th>
                  <th>{t('colBlockers')}</th>
                  <th>{t('common:actions')}</th>
                </tr>
              </thead>
              <tbody>
                {releases.length > 0 ? (
                  releases.map((rel) => (
                    <tr key={rel.id}>
                      <td style={{ fontWeight: 600 }}>{rel.version}</td>
                      <td>{rel.name}</td>
                      <td>
                        <Badge tone={rel.status === 'RELEASED' ? 'success' : rel.status === 'BLOCKED' ? 'danger' : 'neutral'}>
                          {rel.status}
                        </Badge>
                      </td>
                      <td>{rel.target_date || '--'}</td>
                      <td>{rel.pass_rate_threshold}%</td>
                      <td>{rel.quality_score > 0 ? `${rel.quality_score}/100` : '--'}</td>
                      <td>
                        {rel.blockers && rel.blockers.length > 0 ? (
                          <Badge tone="danger">
                            {t('blockersCount', { value: rel.blockers.length })}
                          </Badge>
                        ) : (
                          <Badge tone="success">{t('blockersZero')}</Badge>
                        )}
                      </td>
                      <td>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={(event) => {
                            gateEvaluateTriggerRef.current = event.currentTarget;
                            void handleEvaluateGate(rel.id);
                          }}
                          disabled={evaluatingGateId === rel.id}
                        >
                          <ShieldCheck size={14} className={evaluatingGateId === rel.id ? 'spinning' : ''} />
                          <span>{evaluatingGateId === rel.id ? t('gateEvaluating') : t('gateEvaluate')}</span>
                        </Button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={8} className="text-center text-secondary py-4">
                      {t('releasesEmpty', { action: t('newRelease') })}
                    </td>
                  </tr>
                )}
              </tbody>
            </Table>
          </div>
        </Card>
        </>
      )}

        </TabsContent>
      </Tabs>

      <Drawer open={showCreateReleaseModal} onOpenChange={setShowCreateReleaseModal}>
        <DrawerContent
          className="quality-release-drawer"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            createReleaseTriggerRef.current?.focus();
          }}
        >
          <div className="ds-drawer-head">
            <DrawerTitle>{t('createReleaseTitle')}</DrawerTitle>
            <IconButton variant="ghost" aria-label={t('common:cancel')} onClick={() => setShowCreateReleaseModal(false)}>&times;</IconButton>
          </div>
          <form onSubmit={handleCreateRelease}>
            <div className="ds-drawer-body">
              {releaseActionError && <Alert role="alert">{t('releaseActionFailed', { message: releaseActionError })}</Alert>}
              <FormField label={t('createReleaseVersionLabel')} htmlFor="quality-release-version" required>
                <Input id="quality-release-version" type="text" required placeholder="v1.4.0" value={newReleaseVersion} onChange={(e) => setNewReleaseVersion(e.target.value)} />
              </FormField>
              <FormField label={t('createReleaseNameLabel')} htmlFor="quality-release-name" required>
                <Input id="quality-release-name" type="text" required placeholder={t('createReleaseNamePlaceholder')} value={newReleaseName} onChange={(e) => setNewReleaseName(e.target.value)} />
              </FormField>
              <FormField label={t('createReleaseTargetDateLabel')} htmlFor="quality-release-target-date">
                <Input id="quality-release-target-date" type="date" value={newReleaseTargetDate} onChange={(e) => setNewReleaseTargetDate(e.target.value)} />
              </FormField>
              <FormField label={t('createReleaseThresholdLabel')} htmlFor="quality-release-threshold">
                <Input id="quality-release-threshold" type="number" min="0" max="100" step="0.5" value={newReleaseThreshold} onChange={(e) => setNewReleaseThreshold(parseFloat(e.target.value))} />
              </FormField>
            </div>
            <div className="ds-drawer-foot quality-drawer-actions">
              <Button type="button" variant="secondary" onClick={() => setShowCreateReleaseModal(false)}>{t('common:cancel')}</Button>
              <Button type="submit" variant="primary" disabled={creatingRelease}>
                {creatingRelease ? t('createReleaseSubmitting') : t('createReleaseSubmit')}
              </Button>
            </div>
          </form>
        </DrawerContent>
      </Drawer>

      <Drawer
        open={selectedGateReport !== null}
        onOpenChange={(open) => { if (!open) setSelectedGateReport(null); }}
      >
        <DrawerContent
          className="quality-gate-report-drawer"
          onCloseAutoFocus={(event) => {
            const trigger = gateEvaluateTriggerRef.current;
            if (trigger?.isConnected) {
              event.preventDefault();
              trigger.focus();
            }
          }}
        >
          {selectedGateReport && (
            <>
            <div className="ds-drawer-head">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <ShieldCheck size={20} color={selectedGateReport.can_release ? 'var(--accent-green)' : 'var(--accent-red)'} />
                <DrawerTitle>{t('gateReportTitle', { version: selectedGateReport.version })}</DrawerTitle>
              </div>
              <IconButton variant="ghost" aria-label={t('gateCloseReport')} onClick={() => setSelectedGateReport(null)}>&times;</IconButton>
            </div>
            <div className="ds-drawer-body">
              <Alert className="quality-gate-verdict">
                <div>
                  <div style={{ fontWeight: 700, fontSize: '1.1rem' }}>
                    {t('gateVerdict', { verdict: selectedGateReport.verdict })}
                  </div>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    {t('gateQualityScore', { score: selectedGateReport.quality_score })}
                  </div>
                </div>
                <div>
                  {selectedGateReport.can_release ? (
                    <Badge tone="success"><CheckCircle2 size={12} aria-hidden="true" />{t('gateReadyToRelease')}</Badge>
                  ) : (
                    <Badge tone="danger"><XCircle size={12} aria-hidden="true" />{t('gateReleaseBlocked')}</Badge>
                  )}
                </div>
              </Alert>

              {/* Gate Checks Breakdown */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>{t('gateChecks')}</div>

                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    borderRadius: 'var(--r-xs)',
                    backgroundColor: 'var(--bg-subtle)',
                  }}
                >
                  <span>{t('gatePassRate', { value: selectedGateReport.pass_rate })}</span>
                  {selectedGateReport.pass_rate_met ? (
                    <span style={{ color: 'var(--accent-green)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <CheckCircle2 size={14} /> {t('gateCheckPassed')}
                    </span>
                  ) : (
                    <span style={{ color: 'var(--accent-red)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <XCircle size={14} /> {t('gateCheckFailed')}
                    </span>
                  )}
                </div>

                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    borderRadius: 'var(--r-xs)',
                    backgroundColor: 'var(--bg-subtle)',
                  }}
                >
                  <span>{t('gateFlakyConstraint', { value: selectedGateReport.flaky_count })}</span>
                  {selectedGateReport.flaky_met ? (
                    <span style={{ color: 'var(--accent-green)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <CheckCircle2 size={14} /> {t('gateCheckPassed')}
                    </span>
                  ) : (
                    <span style={{ color: 'var(--accent-red)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <XCircle size={14} /> {t('gateCheckFailed')}
                    </span>
                  )}
                </div>

                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    borderRadius: 'var(--r-xs)',
                    backgroundColor: 'var(--bg-subtle)',
                  }}
                >
                  <span>{t('gateP0Constraint', { value: selectedGateReport.unautomated_p0_count })}</span>
                  {selectedGateReport.unautomated_p0_met ? (
                    <span style={{ color: 'var(--accent-green)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <CheckCircle2 size={14} /> {t('gateCheckPassed')}
                    </span>
                  ) : (
                    <span style={{ color: 'var(--accent-red)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <XCircle size={14} /> {t('gateCheckFailed')}
                    </span>
                  )}
                </div>
              </div>

              {/* Blockers list */}
              {selectedGateReport.blockers.length > 0 && (
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--accent-red)', marginBottom: '6px' }}>
                    {t('gateBlockingIssues', { value: selectedGateReport.blockers.length })}
                  </div>
                  <ul style={{ margin: '0 0 0 1.2rem', fontSize: '0.85rem' }}>
                    {selectedGateReport.blockers.map((b, i) => (
                      <li key={i} style={{ color: 'var(--text-primary)', marginBottom: '4px' }}>
                        {b}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
            <div className="ds-drawer-foot quality-drawer-actions">
              <Button variant="primary" onClick={() => setSelectedGateReport(null)}>
                {t('gateCloseReport')}
              </Button>
            </div>
            </>
          )}
        </DrawerContent>
      </Drawer>
    </Stack>
  );
};
