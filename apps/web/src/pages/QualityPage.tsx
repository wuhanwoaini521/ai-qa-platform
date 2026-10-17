import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import {
  ShieldCheck,
  Target,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Zap,
  Plus,
  PlayCircle,
  ChevronDown,
  Search,
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
import { summarizeAutomationCoverage } from '../features/quality/coverageModel';
import { buildWorkspaceHref } from '../app/workspaceContext';
import './QualityPage.css';

interface QualityPageProps {
  projects?: Project[];
  selectedProjectId: string | null;
  onNavigateToRuns?: (runId?: string) => void;
}

export const QualityPage: React.FC<QualityPageProps> = ({
  selectedProjectId,
  onNavigateToRuns,
}) => {
  const { t } = useTranslation('quality');
  const [activeTab, setActiveTab] = useState<'coverage' | 'risks' | 'impact' | 'releases'>('coverage');

  // Coverage & Risks state
  const [coverage, setCoverage] = useState<QualityCoverageSummary | null>(null);
  const [testCases, setTestCases] = useState<TestCase[] | null>(null);
  const [coverageQuery, setCoverageQuery] = useState('');
  const [coverageStatus, setCoverageStatus] = useState('ALL');
  const [coverageSort, setCoverageSort] = useState<'title' | 'coverage-desc' | 'coverage-asc'>('coverage-desc');
  const [groupCoverageByStatus, setGroupCoverageByStatus] = useState(false);
  const [expandedCoverageId, setExpandedCoverageId] = useState<string | null>(null);
  const [coverageSourceError, setCoverageSourceError] = useState(false);
  const [riskMatrix, setRiskMatrix] = useState<QualityRiskMatrix | null>(null);
  const [loadingMetrics, setLoadingMetrics] = useState<boolean>(true);

  // Impact Analysis state
  const [changedFilesText, setChangedFilesText] = useState<string>('');
  const [impactResult, setImpactResult] = useState<ImpactAnalysisResult | null>(null);
  const [loadingImpact, setLoadingImpact] = useState<boolean>(false);

  // Releases state
  const [releases, setReleases] = useState<Release[]>([]);
  const [showCreateReleaseModal, setShowCreateReleaseModal] = useState<boolean>(false);
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
  const [evaluatingGateId, setEvaluatingGateId] = useState<string | null>(null);

  const fetchQualityData = async () => {
    if (!selectedProjectId) {
      setCoverage(null);
      setTestCases(null);
      setRiskMatrix(null);
      setReleases([]);
      setCoverageSourceError(false);
      setLoadingMetrics(false);
      return;
    }
    try {
      setLoadingMetrics(true);
      setCoverage(null);
      setTestCases(null);
      setCoverageSourceError(false);
      const [cov, risks, rels] = await Promise.all([
        api.getQualityCoverage(selectedProjectId),
        api.getQualityRiskMatrix(selectedProjectId),
        api.getReleases(selectedProjectId),
      ]);
      setCoverage(cov);
      setRiskMatrix(risks);
      setReleases(rels);
      try {
        setTestCases(await api.getTestCases(selectedProjectId));
      } catch (error) {
        console.error('Failed to fetch test case bindings for quality coverage', error);
        setTestCases(null);
        setCoverageSourceError(true);
      }
    } catch (err) {
      console.error('Failed to fetch quality intelligence data', err);
      setCoverage(null);
      setRiskMatrix(null);
      setReleases([]);
      setTestCases(null);
      setCoverageSourceError(true);
    } finally {
      setLoadingMetrics(false);
    }
  };

  const automationCoverage = useMemo(
    () => testCases ? summarizeAutomationCoverage(testCases) : null,
    [testCases],
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
    const percentageFor = (requirementId: string) => automationCoverage?.byRequirement.get(requirementId)?.percentage;
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
  }, [automationCoverage, coverage?.requirement_details, coverageQuery, coverageSort, coverageStatus]);
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

  useEffect(() => {
    fetchQualityData();
  }, [selectedProjectId]);

  const handleRunImpactAnalysis = async () => {
    if (!selectedProjectId) return;
    try {
      setLoadingImpact(true);
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
        return <span className="status-pill status-pill-passed">{translate('riskLevelLow')}</span>;
      case 'MEDIUM':
        return <span className="status-pill status-pill-warning">{translate('riskLevelMedium')}</span>;
      case 'HIGH':
        return <span className="status-pill status-pill-failed">{translate('riskLevelHigh')}</span>;
      case 'CRITICAL':
        return <span className="status-pill status-pill-error">{translate('riskLevelCritical')}</span>;
      default:
        return <span className="status-pill">{level}</span>;
    }
  };

  return (
    <div className="page-container">
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h2>{t('titles:quality')}</h2>
          <p className="subtitle">{t('subtitle')}</p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn btn-secondary" onClick={fetchQualityData} disabled={loadingMetrics}>
            <RefreshCw size={14} className={loadingMetrics ? 'spinning' : ''} />
            <span>{t('common:refresh')}</span>
          </button>
          <button className="btn btn-primary" onClick={() => setShowCreateReleaseModal(true)}>
            <Plus size={14} />
            <span>{t('newRelease')}</span>
          </button>
        </div>
      </div>

      {/* Top Metric Cards */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon" style={{ backgroundColor: 'rgba(59, 130, 246, 0.1)', color: 'var(--accent-primary)' }}>
            <ShieldCheck size={20} />
          </div>
          <div className="stat-details">
            <div className="stat-title">{t('metricQualityHealth')}</div>
            <div className="stat-value">
              {riskMatrix ? `${riskMatrix.overall_quality_score}/100` : '--'}
            </div>
            <div className="stat-subtitle">
              {riskMatrix && <>
                {getRiskBadge(riskMatrix.overall_risk_level, t)}
                <small className="quality-score-formula">{t('metricQualityHealthFormula')}</small>
              </>}
            </div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon" style={{ backgroundColor: 'rgba(16, 185, 129, 0.1)', color: 'var(--accent-green)' }}>
            <Target size={20} />
          </div>
          <div className="stat-details">
            <div className="stat-title">{t('metricRequirementCoverage')}</div>
            <div className="stat-value">
              {coverage ? `${coverage.requirement_coverage_pct}%` : '--'}
            </div>
            <div className="stat-subtitle">
              {coverage
                ? t('requirementsCoverageCount', {
                    covered: coverage.covered_requirements,
                    total: coverage.total_requirements,
                  })
                : t('requirementsCoveredZero')}
            </div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon" style={{ backgroundColor: 'rgba(245, 158, 11, 0.1)', color: 'var(--accent-amber)' }}>
            <Zap size={20} />
          </div>
          <div className="stat-details">
            <div className="stat-title">{t('metricAutomationCoverage')}</div>
            <div className="stat-value">
              {automationCoverage ? `${automationCoverage.percentage}%` : '--'}
            </div>
            <div className="stat-subtitle">
              {automationCoverage
                ? t('casesAutomatedCount', {
                    automated: automationCoverage.automated,
                    total: automationCoverage.total,
                  })
                : coverageSourceError
                  ? t('coverageSourceUnavailable')
                  : loadingMetrics ? t('coverageLoading') : t('casesZero')}
            </div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon" style={{ backgroundColor: 'rgba(239, 68, 68, 0.1)', color: 'var(--accent-red)' }}>
            <AlertTriangle size={20} />
          </div>
          <div className="stat-details">
            <div className="stat-title">{t('metricHighRiskAreas')}</div>
            <div className="stat-value">
              {riskMatrix ? riskMatrix.high_risk_count : '--'}
            </div>
            <div className="stat-subtitle">
              {riskMatrix
                ? t('p0Unautomated', { value: riskMatrix.unautomated_p0_count })
                : t('risksZero')}
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="tabs-container" style={{ margin: '1.5rem 0 1rem' }}>
        <button
          className={`tab-btn ${activeTab === 'coverage' ? 'active' : ''}`}
          onClick={() => setActiveTab('coverage')}
        >
          {t('tabCoverage')}
        </button>
        <button
          className={`tab-btn ${activeTab === 'risks' ? 'active' : ''}`}
          onClick={() => setActiveTab('risks')}
        >
          {t('tabRisks', { value: riskMatrix?.risks.length || 0 })}
        </button>
        <button
          className={`tab-btn ${activeTab === 'impact' ? 'active' : ''}`}
          onClick={() => setActiveTab('impact')}
        >
          {t('tabImpact')}
        </button>
        <button
          className={`tab-btn ${activeTab === 'releases' ? 'active' : ''}`}
          onClick={() => setActiveTab('releases')}
        >
          {t('tabReleases', { value: releases.length })}
        </button>
      </div>

      {/* Tab 1: Coverage Details */}
      {activeTab === 'coverage' && (
        <div className="card">
          <div className="card-header">
            <h3>{t('coverageTitle')}</h3>
            <span className="text-secondary text-sm">{t('coverageHint')}</span>
          </div>
          {coverageSourceError && (
            <p className="text-secondary text-sm" role="status" style={{ padding: '0 16px 12px' }}>
              {t('coverageSourceUnavailable')}
            </p>
          )}
          <div className="quality-coverage-toolbar" role="search">
            <label className="quality-coverage-search">
              <Search size={15} aria-hidden="true" />
              <span className="quality-coverage-visually-hidden">{t('coverageSearchLabel')}</span>
              <input type="search" value={coverageQuery} onChange={(event) => setCoverageQuery(event.target.value)} placeholder={t('coverageSearchPlaceholder')} />
            </label>
            <label className="quality-coverage-control">
              <span>{t('coverageStatusLabel')}</span>
              <select value={coverageStatus} onChange={(event) => setCoverageStatus(event.target.value)}>
                <option value="ALL">{t('coverageAllStatuses')}</option>
                {coverageStatuses.map((status) => <option key={status} value={status}>{status}</option>)}
              </select>
            </label>
            <label className="quality-coverage-control">
              <span>{t('coverageSortLabel')}</span>
              <select value={coverageSort} onChange={(event) => setCoverageSort(event.target.value as typeof coverageSort)}>
                <option value="coverage-desc">{t('coverageSortHighest')}</option>
                <option value="coverage-asc">{t('coverageSortLowest')}</option>
                <option value="title">{t('coverageSortTitle')}</option>
              </select>
            </label>
            <label className="quality-coverage-group-toggle">
              <input type="checkbox" checked={groupCoverageByStatus} onChange={(event) => setGroupCoverageByStatus(event.target.checked)} />
              <span>{t('coverageGroupByStatus')}</span>
            </label>
          </div>
          <div className="quality-coverage-count" role="status">
            {t('coverageResultCount', { visible: filteredCoverage.length, total: coverage?.requirement_details.length ?? 0 })}
          </div>
          <div className="table-responsive quality-coverage-scroll">
            <table className="data-table quality-coverage-table">
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
                  {coverage?.requirement_details.length ? t('coverageNoMatches') : t('coverageEmpty')}
                </td></tr></tbody>
              ) : coverageGroups.map(({ status, items }) => (
                <tbody key={status || 'all'}>
                  {status && <tr className="quality-coverage-group-row"><th colSpan={7}>{status}</th></tr>}
                  {items.map((item) => {
                    const requirementCoverage = automationCoverage?.byRequirement.get(item.requirement_id);
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
                            <button
                              className="quality-coverage-expand"
                              type="button"
                              aria-label={t(expanded ? 'coverageCollapseDetails' : 'coverageExpandDetails', { title: item.title })}
                              aria-expanded={expanded}
                              aria-controls={expanded ? detailId : undefined}
                              onClick={() => setExpandedCoverageId(expanded ? null : item.requirement_id)}
                            >
                              <ChevronDown size={15} aria-hidden="true" />
                            </button>
                            <div>
                              <Link className="quality-coverage-link" to={requirementHref}>{item.title}</Link>
                              <small>{item.requirement_id}</small>
                            </div>
                          </td>
                          <td><span className={`status-pill status-pill-${item.status.toLowerCase()}`}>{item.status}</span></td>
                          <td>{item.test_design_count}</td>
                          <td>{requirementCoverage ? requirementCoverage.total : testCases ? 0 : '--'}</td>
                          <td>{requirementCoverage ? requirementCoverage.automated : testCases ? 0 : '--'}</td>
                          <td>
                            <div className="quality-coverage-meter">
                              <div className="quality-coverage-meter-track">
                                <div
                                  className="quality-coverage-meter-value"
                                  style={{
                                    width: `${testCases ? requirementCoverage?.percentage ?? 0 : 0}%`,
                                    backgroundColor: (requirementCoverage?.percentage ?? 0) >= 70
                                      ? 'var(--accent-green)'
                                      : (requirementCoverage?.percentage ?? 0) >= 40
                                        ? 'var(--accent-amber)'
                                        : 'var(--accent-red)',
                                  }}
                                />
                              </div>
                              <span>{testCases ? `${requirementCoverage?.percentage ?? 0}%` : '--'}</span>
                            </div>
                          </td>
                          <td>{testCases
                            ? (requirementCoverage?.automated ?? 0) > 0
                              ? <span className="status-pill status-pill-passed">{t('common:yes')}</span>
                              : <span className="status-pill status-pill-failed">{t('common:no')}</span>
                            : '--'}</td>
                        </tr>
                        {expanded && <tr className="quality-coverage-detail-row"><td colSpan={7}>
                          <section id={detailId} className="quality-coverage-detail">
                            <div className="quality-coverage-detail-summary">
                              <div><span>{t('coverageRequirement')}</span><Link to={requirementHref}>{item.title}</Link></div>
                              <div><span>{t('coverageStatusLabel')}</span><strong>{item.status}</strong></div>
                              <div><span>{t('coverageLinkedTests', { count: linkedCases.length })}</span><strong>{item.test_case_count}</strong></div>
                            </div>
                            <div className="quality-coverage-linked-tests">
                              <h4>{t('coverageLinkedTestsTitle')}</h4>
                              {testCases === null ? <p className="text-secondary">{t('coverageSourceUnavailable')}</p>
                                : linkedCases.length === 0 ? <p className="text-secondary">{t('coverageNoCases')}</p>
                                  : <ul>{linkedCases.map((testCase) => (
                                    <li key={testCase.id}>
                                      <Link to={buildWorkspaceHref({
                                        projectId: selectedProjectId ?? undefined,
                                        requirementId: item.requirement_id,
                                        testCaseId: testCase.id,
                                        stage: 'cases',
                                        view: 'cases',
                                      })}>{testCase.title}</Link>
                                      <span>{testCase.binding?.status ?? testCase.automation_status}</span>
                                    </li>
                                  ))}</ul>}
                            </div>
                          </section>
                        </td></tr>}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              ))}
            </table>
          </div>
        </div>
      )}

      {/* Tab 2: Quality Risk List */}
      {activeTab === 'risks' && (
        <div className="card">
          <div className="card-header">
            <h3>{t('risksTitle')}</h3>
            <span className="text-secondary text-sm">{t('risksHint')}</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', padding: '1rem' }}>
            {riskMatrix && riskMatrix.risks.length > 0 ? (
              riskMatrix.risks.map((risk) => {
                const riskHref = riskWorkspaceHref(risk);
                return (
                <div
                  key={risk.id}
                  style={{
                    border: '1px solid var(--border-color)',
                    borderRadius: 'var(--r-sm)',
                    padding: '1rem',
                    backgroundColor: 'var(--bg-subtle)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      {riskHref
                        ? <Link className="quality-risk-link" to={riskHref}>{risk.area}</Link>
                        : <span style={{ fontWeight: 600, fontSize: '1.05rem' }}>{risk.area}</span>}
                      {getRiskBadge(risk.risk_level, t)}
                    </div>
                    <div style={{ fontWeight: 700, color: 'var(--accent-primary)' }}>
                      {t('riskScore', { value: risk.score })}
                    </div>
                  </div>

                  <div style={{ margin: '8px 0' }}>
                    <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>{t('riskReasons')}</div>
                    <ul style={{ margin: '4px 0 8px 1.2rem', fontSize: '0.9rem' }}>
                      {risk.reasons.map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                  </div>

                  {risk.recommended_actions.length > 0 && (
                    <div style={{ marginTop: '8px', backgroundColor: 'var(--bg-base)', padding: '8px 12px', borderRadius: 'var(--r-xs)' }}>
                      <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--accent-primary)', marginBottom: '4px' }}>
                        {t('riskRecommendedActions')}
                      </div>
                      <ul style={{ margin: '0 0 0 1.2rem', fontSize: '0.85rem' }}>
                        {risk.recommended_actions.map((act, i) => (
                          <li key={i}>{act}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
                );
              })
            ) : (
              <div className="text-center text-secondary py-4">{t('risksEmpty')}</div>
            )}
          </div>
        </div>
      )}

      {/* Tab 3: Git Impact & Regression Selector */}
      {activeTab === 'impact' && (
        <div className="card" style={{ padding: '1.5rem' }}>
          <div style={{ marginBottom: '1.5rem' }}>
            <h3>{t('impactTitle')}</h3>
            <p className="text-secondary text-sm">{t('impactHint')}</p>
          </div>

          <div style={{ marginBottom: '1.5rem' }}>
            <label style={{ display: 'block', fontWeight: 600, marginBottom: '6px', fontSize: '0.9rem' }}>
              {t('impactChangedFilesLabel')}
            </label>
            <textarea
              className="form-control"
              rows={4}
              placeholder={t('impactChangedFilesPlaceholder')}
              value={changedFilesText}
              onChange={(e) => setChangedFilesText(e.target.value)}
              style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem', width: '100%' }}
            />
            <div style={{ display: 'flex', gap: '10px', marginTop: '10px' }}>
              <button
                className="btn btn-primary"
                onClick={handleRunImpactAnalysis}
                disabled={loadingImpact}
              >
                <Zap size={14} className={loadingImpact ? 'spinning' : ''} />
                <span>{loadingImpact ? t('impactAnalyzing') : t('impactAnalyze')}</span>
              </button>
            </div>
          </div>

          {impactResult && (
            <div
              style={{
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--r-sm)',
                padding: '1.25rem',
                backgroundColor: 'var(--bg-subtle)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                <h4>{t('impactResultsTitle')}</h4>
                <span className="status-pill status-pill-passed">
                  {t('impactConfidence', { value: Math.round(impactResult.confidence_score * 100) })}
                </span>
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
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => onNavigateToRuns()}
                    >
                      <PlayCircle size={14} />
                      <span>{t('impactExecuteInRunner')}</span>
                    </button>
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
            </div>
          )}
        </div>
      )}

      {/* Tab 4: Releases & Gate Dashboard */}
      {activeTab === 'releases' && (
        <>
          {releaseActionError && (
            <div
              className="async-state async-state-error"
              role="alert"
              style={{ marginBottom: '1rem' }}
            >
              {t('releaseActionFailed', { message: releaseActionError })}
            </div>
          )}
        <div className="card">
          <div className="card-header">
            <h3>{t('releasesTitle')}</h3>
            <span className="text-secondary text-sm">{t('releasesHint')}</span>
          </div>
          <div className="table-responsive">
            <table className="data-table">
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
                        <span
                          className={`status-pill ${
                            rel.status === 'RELEASED'
                              ? 'status-pill-passed'
                              : rel.status === 'BLOCKED'
                              ? 'status-pill-failed'
                              : 'status-pill-draft'
                          }`}
                        >
                          {rel.status}
                        </span>
                      </td>
                      <td>{rel.target_date || '--'}</td>
                      <td>{rel.pass_rate_threshold}%</td>
                      <td>{rel.quality_score > 0 ? `${rel.quality_score}/100` : '--'}</td>
                      <td>
                        {rel.blockers && rel.blockers.length > 0 ? (
                          <span className="status-pill status-pill-failed">
                            {t('blockersCount', { value: rel.blockers.length })}
                          </span>
                        ) : (
                          <span className="status-pill status-pill-passed">{t('blockersZero')}</span>
                        )}
                      </td>
                      <td>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => handleEvaluateGate(rel.id)}
                          disabled={evaluatingGateId === rel.id}
                        >
                          <ShieldCheck size={14} className={evaluatingGateId === rel.id ? 'spinning' : ''} />
                          <span>{evaluatingGateId === rel.id ? t('gateEvaluating') : t('gateEvaluate')}</span>
                        </button>
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
            </table>
          </div>
        </div>
        </>
      )}

      {/* Modal: Create Release */}
      {showCreateReleaseModal && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: '500px' }}>
            <div className="modal-header">
              <h3>{t('createReleaseTitle')}</h3>
              <button className="btn-icon" onClick={() => setShowCreateReleaseModal(false)}>
                &times;
              </button>
            </div>
            <form onSubmit={handleCreateRelease}>
              <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {releaseActionError && (
                  <div className="async-state async-state-error" role="alert">
                    {t('releaseActionFailed', { message: releaseActionError })}
                  </div>
                )}
                <div className="form-group">
                  <label>{t('createReleaseVersionLabel')}</label>
                  <input
                    type="text"
                    className="form-control"
                    required
                    placeholder="v1.4.0"
                    value={newReleaseVersion}
                    onChange={(e) => setNewReleaseVersion(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>{t('createReleaseNameLabel')}</label>
                  <input
                    type="text"
                    className="form-control"
                    required
                    placeholder={t('createReleaseNamePlaceholder')}
                    value={newReleaseName}
                    onChange={(e) => setNewReleaseName(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>{t('createReleaseTargetDateLabel')}</label>
                  <input
                    type="date"
                    className="form-control"
                    value={newReleaseTargetDate}
                    onChange={(e) => setNewReleaseTargetDate(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>{t('createReleaseThresholdLabel')}</label>
                  <input
                    type="number"
                    min="0"
                    max="100"
                    step="0.5"
                    className="form-control"
                    value={newReleaseThreshold}
                    onChange={(e) => setNewReleaseThreshold(parseFloat(e.target.value))}
                  />
                </div>
              </div>
              <div className="modal-footer" style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowCreateReleaseModal(false)}>
                  {t('common:cancel')}
                </button>
                <button type="submit" className="btn btn-primary" disabled={creatingRelease}>
                  {creatingRelease ? t('createReleaseSubmitting') : t('createReleaseSubmit')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Gate Report Detail */}
      {selectedGateReport && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: '600px' }}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <ShieldCheck size={20} color={selectedGateReport.can_release ? 'var(--accent-green)' : 'var(--accent-red)'} />
                <h3>{t('gateReportTitle', { version: selectedGateReport.version })}</h3>
              </div>
              <button className="btn-icon" onClick={() => setSelectedGateReport(null)}>
                &times;
              </button>
            </div>
            <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '12px 16px',
                  borderRadius: 'var(--r-sm)',
                  backgroundColor: selectedGateReport.can_release
                    ? 'rgba(16, 185, 129, 0.1)'
                    : 'rgba(239, 68, 68, 0.1)',
                  border: `1px solid ${selectedGateReport.can_release ? 'var(--accent-green)' : 'var(--accent-red)'}`,
                }}
              >
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
                    <span className="status-pill status-pill-passed" style={{ fontSize: '0.9rem', padding: '4px 10px' }}>
                      {t('gateReadyToRelease')}
                    </span>
                  ) : (
                    <span className="status-pill status-pill-failed" style={{ fontSize: '0.9rem', padding: '4px 10px' }}>
                      {t('gateReleaseBlocked')}
                    </span>
                  )}
                </div>
              </div>

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
            <div className="modal-footer" style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button className="btn btn-primary" onClick={() => setSelectedGateReport(null)}>
                {t('gateCloseReport')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
