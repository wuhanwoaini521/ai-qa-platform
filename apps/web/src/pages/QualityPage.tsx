import React, { useEffect, useState } from 'react';
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
} from 'lucide-react';
import {
  ImpactAnalysisResult,
  Project,
  QualityCoverageSummary,
  QualityRiskLevel,
  QualityRiskMatrix,
  Release,
  ReleaseGateReport,
} from '../types';
import { api } from '../api/client';

interface QualityPageProps {
  projects?: Project[];
  selectedProjectId: string | null;
  onNavigateToRuns?: (runId?: string) => void;
}

export const QualityPage: React.FC<QualityPageProps> = ({
  selectedProjectId,
  onNavigateToRuns,
}) => {
  const [activeTab, setActiveTab] = useState<'coverage' | 'risks' | 'impact' | 'releases'>('coverage');

  // Coverage & Risks state
  const [coverage, setCoverage] = useState<QualityCoverageSummary | null>(null);
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

  // Gate Report state
  const [selectedGateReport, setSelectedGateReport] = useState<ReleaseGateReport | null>(null);
  const [evaluatingGateId, setEvaluatingGateId] = useState<string | null>(null);

  const fetchQualityData = async () => {
    if (!selectedProjectId) return;
    try {
      setLoadingMetrics(true);
      const [cov, risks, rels] = await Promise.all([
        api.getQualityCoverage(selectedProjectId),
        api.getQualityRiskMatrix(selectedProjectId),
        api.getReleases(selectedProjectId),
      ]);
      setCoverage(cov);
      setRiskMatrix(risks);
      setReleases(rels);
    } catch (err) {
      console.error('Failed to fetch quality intelligence data', err);
    } finally {
      setLoadingMetrics(false);
    }
  };

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
    } finally {
      setCreatingRelease(false);
    }
  };

  const handleEvaluateGate = async (releaseId: string) => {
    try {
      setEvaluatingGateId(releaseId);
      const report = await api.evaluateReleaseGate(releaseId);
      setSelectedGateReport(report);
      // Refresh releases
      if (selectedProjectId) {
        const rels = await api.getReleases(selectedProjectId);
        setReleases(rels);
      }
    } catch (err) {
      console.error('Failed to evaluate release gate', err);
    } finally {
      setEvaluatingGateId(null);
    }
  };

  const getRiskBadge = (level: QualityRiskLevel) => {
    switch (level) {
      case 'LOW':
        return <span className="status-pill status-pill-passed">Low Risk</span>;
      case 'MEDIUM':
        return <span className="status-pill status-pill-warning">Medium Risk</span>;
      case 'HIGH':
        return <span className="status-pill status-pill-failed">High Risk</span>;
      case 'CRITICAL':
        return <span className="status-pill status-pill-error">Critical Risk</span>;
      default:
        return <span className="status-pill">{level}</span>;
    }
  };

  return (
    <div className="page-container">
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h2>Quality Intelligence & Release Gate</h2>
          <p className="subtitle">
            Multi-dimensional QA coverage, risk matrix, regression impact analysis, and automated release gates.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn btn-secondary" onClick={fetchQualityData} disabled={loadingMetrics}>
            <RefreshCw size={14} className={loadingMetrics ? 'spinning' : ''} />
            <span>Refresh</span>
          </button>
          <button className="btn btn-primary" onClick={() => setShowCreateReleaseModal(true)}>
            <Plus size={14} />
            <span>New Release</span>
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
            <div className="stat-title">Overall Quality Health</div>
            <div className="stat-value">
              {riskMatrix ? `${riskMatrix.overall_quality_score}/100` : '--'}
            </div>
            <div className="stat-subtitle">
              {riskMatrix && getRiskBadge(riskMatrix.overall_risk_level)}
            </div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon" style={{ backgroundColor: 'rgba(16, 185, 129, 0.1)', color: '#10b981' }}>
            <Target size={20} />
          </div>
          <div className="stat-details">
            <div className="stat-title">Requirement Coverage</div>
            <div className="stat-value">
              {coverage ? `${coverage.requirement_coverage_pct}%` : '--'}
            </div>
            <div className="stat-subtitle">
              {coverage ? `${coverage.covered_requirements} / ${coverage.total_requirements} requirements` : '0 covered'}
            </div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon" style={{ backgroundColor: 'rgba(245, 158, 11, 0.1)', color: '#f59e0b' }}>
            <Zap size={20} />
          </div>
          <div className="stat-details">
            <div className="stat-title">Automation Coverage</div>
            <div className="stat-value">
              {coverage ? `${coverage.automation_coverage_pct}%` : '--'}
            </div>
            <div className="stat-subtitle">
              {coverage ? `${coverage.automated_cases} automated / ${coverage.total_test_cases} cases` : '0 cases'}
            </div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon" style={{ backgroundColor: 'rgba(239, 68, 68, 0.1)', color: '#ef4444' }}>
            <AlertTriangle size={20} />
          </div>
          <div className="stat-details">
            <div className="stat-title">High Risk Areas</div>
            <div className="stat-value">
              {riskMatrix ? riskMatrix.high_risk_count : '--'}
            </div>
            <div className="stat-subtitle">
              {riskMatrix ? `${riskMatrix.unautomated_p0_count} P0 unautomated` : '0 risks'}
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
          Requirement Coverage Details
        </button>
        <button
          className={`tab-btn ${activeTab === 'risks' ? 'active' : ''}`}
          onClick={() => setActiveTab('risks')}
        >
          Quality Risk Matrix ({riskMatrix?.risks.length || 0})
        </button>
        <button
          className={`tab-btn ${activeTab === 'impact' ? 'active' : ''}`}
          onClick={() => setActiveTab('impact')}
        >
          Git Impact & Regression Selector
        </button>
        <button
          className={`tab-btn ${activeTab === 'releases' ? 'active' : ''}`}
          onClick={() => setActiveTab('releases')}
        >
          Releases & Gate Reports ({releases.length})
        </button>
      </div>

      {/* Tab 1: Coverage Details */}
      {activeTab === 'coverage' && (
        <div className="card">
          <div className="card-header">
            <h3>Requirement Coverage Breakdown</h3>
            <span className="text-secondary text-sm">
              Coverage computed from test design count, test case count, and automated script bindings.
            </span>
          </div>
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Requirement Title</th>
                  <th>Status</th>
                  <th>Test Designs</th>
                  <th>Total Cases</th>
                  <th>Automated</th>
                  <th>Coverage %</th>
                  <th>Has Automation</th>
                </tr>
              </thead>
              <tbody>
                {coverage && coverage.requirement_details.length > 0 ? (
                  coverage.requirement_details.map((item) => (
                    <tr key={item.requirement_id}>
                      <td style={{ fontWeight: 600 }}>{item.title}</td>
                      <td>
                        <span className={`status-pill status-pill-${item.status.toLowerCase()}`}>
                          {item.status}
                        </span>
                      </td>
                      <td>{item.test_design_count}</td>
                      <td>{item.test_case_count}</td>
                      <td>{item.automated_case_count}</td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <div
                            style={{
                              width: '80px',
                              height: '8px',
                              backgroundColor: 'var(--border-color)',
                              borderRadius: '4px',
                              overflow: 'hidden',
                            }}
                          >
                            <div
                              style={{
                                width: `${item.coverage_percentage}%`,
                                height: '100%',
                                backgroundColor:
                                  item.coverage_percentage >= 70
                                    ? '#10b981'
                                    : item.coverage_percentage >= 40
                                    ? '#f59e0b'
                                    : '#ef4444',
                              }}
                            />
                          </div>
                          <span>{item.coverage_percentage}%</span>
                        </div>
                      </td>
                      <td>
                        {item.has_automation ? (
                          <span className="status-pill status-pill-passed">Yes</span>
                        ) : (
                          <span className="status-pill status-pill-failed">No</span>
                        )}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={7} className="text-center text-secondary py-4">
                      No requirement coverage data available.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 2: Quality Risk Matrix */}
      {activeTab === 'risks' && (
        <div className="card">
          <div className="card-header">
            <h3>Identified Quality Risks</h3>
            <span className="text-secondary text-sm">
              Deterministic risks synthesized from unautomated P0 tests, flaky failure rates, and recurring defects.
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', padding: '1rem' }}>
            {riskMatrix && riskMatrix.risks.length > 0 ? (
              riskMatrix.risks.map((risk) => (
                <div
                  key={risk.id}
                  style={{
                    border: '1px solid var(--border-color)',
                    borderRadius: '8px',
                    padding: '1rem',
                    backgroundColor: 'var(--bg-subtle)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span style={{ fontWeight: 600, fontSize: '1.05rem' }}>{risk.area}</span>
                      {getRiskBadge(risk.risk_level)}
                    </div>
                    <div style={{ fontWeight: 700, color: 'var(--accent-primary)' }}>
                      Risk Score: {risk.score}
                    </div>
                  </div>

                  <div style={{ margin: '8px 0' }}>
                    <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Reasons:</div>
                    <ul style={{ margin: '4px 0 8px 1.2rem', fontSize: '0.9rem' }}>
                      {risk.reasons.map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                  </div>

                  {risk.recommended_actions.length > 0 && (
                    <div style={{ marginTop: '8px', backgroundColor: 'var(--bg-base)', padding: '8px 12px', borderRadius: '6px' }}>
                      <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--accent-primary)', marginBottom: '4px' }}>
                        Recommended Actions:
                      </div>
                      <ul style={{ margin: '0 0 0 1.2rem', fontSize: '0.85rem' }}>
                        {risk.recommended_actions.map((act, i) => (
                          <li key={i}>{act}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ))
            ) : (
              <div className="text-center text-secondary py-4">No risk items identified. System quality is optimal!</div>
            )}
          </div>
        </div>
      )}

      {/* Tab 3: Git Impact & Regression Selector */}
      {activeTab === 'impact' && (
        <div className="card" style={{ padding: '1.5rem' }}>
          <div style={{ marginBottom: '1.5rem' }}>
            <h3>Code Change Impact Analysis & Regression Selector</h3>
            <p className="text-secondary text-sm">
              Input modified file paths to analyze affected requirements and test cases, and automatically select targeted regression suites.
            </p>
          </div>

          <div style={{ marginBottom: '1.5rem' }}>
            <label style={{ display: 'block', fontWeight: 600, marginBottom: '6px', fontSize: '0.9rem' }}>
              Changed File Paths (one per line):
            </label>
            <textarea
              className="form-control"
              rows={4}
              placeholder="e.g.&#10;apps/api/app/api/auth.py&#10;apps/api/app/services/checkout_service.py"
              value={changedFilesText}
              onChange={(e) => setChangedFilesText(e.target.value)}
              style={{ fontFamily: 'monospace', fontSize: '0.85rem', width: '100%' }}
            />
            <div style={{ display: 'flex', gap: '10px', marginTop: '10px' }}>
              <button
                className="btn btn-primary"
                onClick={handleRunImpactAnalysis}
                disabled={loadingImpact}
              >
                <Zap size={14} className={loadingImpact ? 'spinning' : ''} />
                <span>{loadingImpact ? 'Analyzing Impact...' : 'Analyze Impact & Select Tests'}</span>
              </button>
            </div>
          </div>

          {impactResult && (
            <div
              style={{
                border: '1px solid var(--border-color)',
                borderRadius: '8px',
                padding: '1.25rem',
                backgroundColor: 'var(--bg-subtle)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                <h4>Impact Analysis Results</h4>
                <span className="status-pill status-pill-passed">
                  Confidence: {Math.round(impactResult.confidence_score * 100)}%
                </span>
              </div>

              <div style={{ marginBottom: '1rem' }}>
                <div style={{ fontWeight: 600, fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Analysis Rationale:</div>
                <ul style={{ margin: '4px 0 10px 1.2rem', fontSize: '0.9rem' }}>
                  {impactResult.rationale.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div style={{ background: 'var(--bg-base)', padding: '10px', borderRadius: '6px' }}>
                  <div style={{ fontWeight: 600, fontSize: '0.85rem', marginBottom: '6px' }}>
                    Impacted Requirements ({impactResult.impacted_requirements.length})
                  </div>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    {impactResult.impacted_requirements.join(', ') || 'None identified'}
                  </div>
                </div>

                <div style={{ background: 'var(--bg-base)', padding: '10px', borderRadius: '6px' }}>
                  <div style={{ fontWeight: 600, fontSize: '0.85rem', marginBottom: '6px' }}>
                    Impacted Test Cases ({impactResult.impacted_test_cases.length})
                  </div>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    {impactResult.impacted_test_cases.join(', ') || 'None identified'}
                  </div>
                </div>
              </div>

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>
                    Recommended Regression Suite ({impactResult.recommended_regression_tests.length} tests)
                  </div>
                  {onNavigateToRuns && impactResult.recommended_regression_tests.length > 0 && (
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => onNavigateToRuns()}
                    >
                      <PlayCircle size={14} />
                      <span>Execute in Runner</span>
                    </button>
                  )}
                </div>
                <div
                  style={{
                    backgroundColor: 'var(--bg-base)',
                    padding: '10px',
                    borderRadius: '6px',
                    fontFamily: 'monospace',
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
        <div className="card">
          <div className="card-header">
            <h3>Release Pipelines & Gate Evaluations</h3>
            <span className="text-secondary text-sm">
              Deterministic release gates requiring pass rate thresholds, 0 unautomated P0s, and flaky constraints.
            </span>
          </div>
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Version</th>
                  <th>Release Name</th>
                  <th>Status</th>
                  <th>Target Date</th>
                  <th>Pass Rate Threshold</th>
                  <th>Quality Score</th>
                  <th>Blockers</th>
                  <th>Actions</th>
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
                          <span className="status-pill status-pill-failed">{rel.blockers.length} blockers</span>
                        ) : (
                          <span className="status-pill status-pill-passed">0 blockers</span>
                        )}
                      </td>
                      <td>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => handleEvaluateGate(rel.id)}
                          disabled={evaluatingGateId === rel.id}
                        >
                          <ShieldCheck size={14} className={evaluatingGateId === rel.id ? 'spinning' : ''} />
                          <span>{evaluatingGateId === rel.id ? 'Evaluating...' : 'Evaluate Gate'}</span>
                        </button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={8} className="text-center text-secondary py-4">
                      No releases registered yet. Click &quot;New Release&quot; to define a release version.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Modal: Create Release */}
      {showCreateReleaseModal && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: '500px' }}>
            <div className="modal-header">
              <h3>Create New Release</h3>
              <button className="btn-icon" onClick={() => setShowCreateReleaseModal(false)}>
                &times;
              </button>
            </div>
            <form onSubmit={handleCreateRelease}>
              <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div className="form-group">
                  <label>Version Tag (e.g. v1.4.0) *</label>
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
                  <label>Release Name *</label>
                  <input
                    type="text"
                    className="form-control"
                    required
                    placeholder="Q3 Major Release"
                    value={newReleaseName}
                    onChange={(e) => setNewReleaseName(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>Target Release Date</label>
                  <input
                    type="date"
                    className="form-control"
                    value={newReleaseTargetDate}
                    onChange={(e) => setNewReleaseTargetDate(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>Pass Rate Threshold (%)</label>
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
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={creatingRelease}>
                  {creatingRelease ? 'Creating...' : 'Create Release'}
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
                <ShieldCheck size={20} color={selectedGateReport.can_release ? '#10b981' : '#ef4444'} />
                <h3>Release Gate Report: {selectedGateReport.version}</h3>
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
                  borderRadius: '8px',
                  backgroundColor: selectedGateReport.can_release
                    ? 'rgba(16, 185, 129, 0.1)'
                    : 'rgba(239, 68, 68, 0.1)',
                  border: `1px solid ${selectedGateReport.can_release ? '#10b981' : '#ef4444'}`,
                }}
              >
                <div>
                  <div style={{ fontWeight: 700, fontSize: '1.1rem' }}>
                    Gate Verdict: {selectedGateReport.verdict}
                  </div>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    Quality Score: {selectedGateReport.quality_score}/100
                  </div>
                </div>
                <div>
                  {selectedGateReport.can_release ? (
                    <span className="status-pill status-pill-passed" style={{ fontSize: '0.9rem', padding: '4px 10px' }}>
                      READY TO RELEASE
                    </span>
                  ) : (
                    <span className="status-pill status-pill-failed" style={{ fontSize: '0.9rem', padding: '4px 10px' }}>
                      RELEASE BLOCKED
                    </span>
                  )}
                </div>
              </div>

              {/* Gate Checks Breakdown */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>Evaluation Checks:</div>

                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    borderRadius: '6px',
                    backgroundColor: 'var(--bg-subtle)',
                  }}
                >
                  <span>Pass Rate (Actual: {selectedGateReport.pass_rate}%)</span>
                  {selectedGateReport.pass_rate_met ? (
                    <span style={{ color: '#10b981', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <CheckCircle2 size={14} /> Passed
                    </span>
                  ) : (
                    <span style={{ color: '#ef4444', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <XCircle size={14} /> Failed
                    </span>
                  )}
                </div>

                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    borderRadius: '6px',
                    backgroundColor: 'var(--bg-subtle)',
                  }}
                >
                  <span>Flaky Tests Constraint (Found: {selectedGateReport.flaky_count})</span>
                  {selectedGateReport.flaky_met ? (
                    <span style={{ color: '#10b981', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <CheckCircle2 size={14} /> Passed
                    </span>
                  ) : (
                    <span style={{ color: '#ef4444', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <XCircle size={14} /> Failed
                    </span>
                  )}
                </div>

                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    borderRadius: '6px',
                    backgroundColor: 'var(--bg-subtle)',
                  }}
                >
                  <span>Unautomated P0 Tests (Found: {selectedGateReport.unautomated_p0_count})</span>
                  {selectedGateReport.unautomated_p0_met ? (
                    <span style={{ color: '#10b981', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <CheckCircle2 size={14} /> Passed
                    </span>
                  ) : (
                    <span style={{ color: '#ef4444', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <XCircle size={14} /> Failed
                    </span>
                  )}
                </div>
              </div>

              {/* Blockers list */}
              {selectedGateReport.blockers.length > 0 && (
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.9rem', color: '#ef4444', marginBottom: '6px' }}>
                    Blocking Issues ({selectedGateReport.blockers.length}):
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
                Close Report
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
