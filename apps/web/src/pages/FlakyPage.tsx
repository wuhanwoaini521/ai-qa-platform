import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Flame,
  Filter,
  CheckCircle2,
  TrendingUp,
  AlertOctagon,
  RefreshCw,
  Search,
} from 'lucide-react';
import { FlakyTestItem, Project, TestHistoryResponse } from '../types';
import { api } from '../api/client';

interface FlakyPageProps {
  projects?: Project[];
  selectedProjectId: string | null;
  onNavigateToRuns?: (runId?: string) => void;
}

export const FlakyPage: React.FC<FlakyPageProps> = ({
  selectedProjectId,
  onNavigateToRuns,
}) => {
  const { t } = useTranslation('flaky');
  const [flakyTests, setFlakyTests] = useState<FlakyTestItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedClassification, setSelectedClassification] = useState<string>('ALL');
  const [minScore, setMinScore] = useState<number>(0.0);
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Execution History Modal state
  const [selectedTestNodeId, setSelectedTestNodeId] = useState<string | null>(null);
  const [testHistory, setTestHistory] = useState<TestHistoryResponse | null>(null);
  const [loadingHistory, setLoadingHistory] = useState<boolean>(false);

  const fetchFlakyTests = async () => {
    try {
      setLoading(true);
      const classification = selectedClassification === 'ALL' ? undefined : selectedClassification;
      const data = await api.getFlakyTests(selectedProjectId || undefined, minScore, classification);
      setFlakyTests(data);
    } catch (err) {
      console.error('Failed to load flaky test intelligence', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFlakyTests();
  }, [selectedProjectId, selectedClassification, minScore]);

  const handleOpenHistory = async (nodeid: string, projectId: string) => {
    try {
      setSelectedTestNodeId(nodeid);
      setLoadingHistory(true);
      const hist = await api.getTestHistory(nodeid, projectId, 20);
      setTestHistory(hist);
    } catch (err) {
      console.error('Failed to fetch test execution history', err);
    } finally {
      setLoadingHistory(false);
    }
  };

  const filteredTests = flakyTests.filter((item) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      item.test_name.toLowerCase().includes(query) ||
      item.nodeid.toLowerCase().includes(query) ||
      (item.flaky_score.main_failure_category || '').toLowerCase().includes(query)
    );
  });

  const getClassificationBadge = (cls: string) => {
    switch (cls) {
      case 'LIKELY_FLAKY':
        return <span className="status-pill status-pill-failed">{t('classificationLikelyFlaky')}</span>;
      case 'PERSISTENT_FAILURE':
        return <span className="status-pill status-pill-error">{t('classificationPersistentFailure')}</span>;
      case 'STABLE':
        return <span className="status-pill status-pill-passed">{t('classificationStable')}</span>;
      case 'INSUFFICIENT_DATA':
      default:
        return <span className="status-pill status-pill-draft">{t('classificationInsufficientData')}</span>;
    }
  };

  return (
    <div className="page-container">
      {/* Header & Metric Cards */}
      <div className="page-header">
        <div>
          <h2>{t('titles:flaky')}</h2>
          <p className="subtitle">{t('subtitle')}</p>
        </div>
        <button className="btn btn-secondary" onClick={fetchFlakyTests} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'spinning' : ''} />
          <span>{t('refreshAnalytics')}</span>
        </button>
      </div>

      {/* Summary KPI Cards */}
      <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)', marginBottom: '1.5rem' }}>
        <div className="stat-card">
          <div className="stat-icon-wrapper blue">
            <TrendingUp size={20} />
          </div>
          <div className="stat-info">
            <span className="stat-label">{t('kpiTotalAnalyzed')}</span>
            <span className="stat-value">{flakyTests.length}</span>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon-wrapper orange">
            <Flame size={20} />
          </div>
          <div className="stat-info">
            <span className="stat-label">{t('kpiLikelyFlaky')}</span>
            <span className="stat-value">
              {flakyTests.filter((item) => item.flaky_score.classification === 'LIKELY_FLAKY').length}
            </span>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon-wrapper red">
            <AlertOctagon size={20} />
          </div>
          <div className="stat-info">
            <span className="stat-label">{t('kpiPersistentFailures')}</span>
            <span className="stat-value">
              {flakyTests.filter((item) => item.flaky_score.classification === 'PERSISTENT_FAILURE').length}
            </span>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon-wrapper green">
            <CheckCircle2 size={20} />
          </div>
          <div className="stat-info">
            <span className="stat-label">{t('kpiStable')}</span>
            <span className="stat-value">
              {flakyTests.filter((item) => item.flaky_score.classification === 'STABLE').length}
            </span>
          </div>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="card" style={{ padding: '1rem', marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: 1, minWidth: '220px' }}>
            <Search size={16} color="var(--text-muted)" />
            <input
              type="text"
              className="form-input"
              placeholder={t('filterPlaceholder')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ margin: 0 }}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Filter size={14} color="var(--text-muted)" />
            <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{t('classificationLabel')}</span>
            <select
              className="form-select"
              value={selectedClassification}
              onChange={(e) => setSelectedClassification(e.target.value)}
              style={{ width: 'auto', margin: 0 }}
            >
              <option value="ALL">{t('classificationAll')}</option>
              <option value="LIKELY_FLAKY">{t('classificationLikelyFlaky')}</option>
              <option value="PERSISTENT_FAILURE">{t('classificationPersistentFailure')}</option>
              <option value="STABLE">{t('classificationStable')}</option>
              <option value="INSUFFICIENT_DATA">{t('classificationInsufficientData')}</option>
            </select>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{t('minScoreLabel')}</span>
            <select
              className="form-select"
              value={minScore}
              onChange={(e) => setMinScore(parseFloat(e.target.value))}
              style={{ width: 'auto', margin: 0 }}
            >
              <option value={0.0}>{t('minScoreAll')}</option>
              <option value={0.2}>&ge; 0.20</option>
              <option value={0.4}>&ge; 0.40</option>
              <option value={0.6}>&ge; 0.60</option>
            </select>
          </div>
        </div>
      </div>

      {/* Flaky Intelligence Table */}
      <div className="card">
        {loading ? (
          <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
            <RefreshCw size={24} className="spinning" style={{ marginBottom: '0.75rem' }} />
            <div>{t('calculating')}</div>
          </div>
        ) : filteredTests.length === 0 ? (
          <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
            <CheckCircle2 size={36} color="var(--color-success)" style={{ marginBottom: '0.75rem' }} />
            <h4>{t('emptyTitle')}</h4>
            <p>{t('emptyDescription')}</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>{t('columnTestIdentifier')}</th>
                <th>{t('columnClassification')}</th>
                <th>{t('flakyScore')}</th>
                <th>{t('columnConfidence')}</th>
                <th>{t('columnSamples')}</th>
                <th>{t('columnFailRate')}</th>
                <th>{t('columnRerunRecover')}</th>
                <th>{t('columnMainFailureRoot')}</th>
                <th>{t('common:actions')}</th>
              </tr>
            </thead>
            <tbody>
              {filteredTests.map((item) => {
                const scorePct = Math.round(item.flaky_score.score * 100);
                const confPct = Math.round(item.flaky_score.confidence * 100);
                const failRatePct = Math.round(item.flaky_score.failure_rate * 100);
                const rerunPct = Math.round(item.flaky_score.rerun_recovery_rate * 100);

                return (
                  <tr key={item.nodeid}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{item.test_name}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        {item.nodeid}
                      </div>
                    </td>
                    <td>{getClassificationBadge(item.flaky_score.classification)}</td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <div
                          style={{
                            width: '60px',
                            height: '6px',
                            backgroundColor: 'var(--border-color)',
                            borderRadius: 'var(--r-xs)',
                            overflow: 'hidden',
                          }}
                        >
                          <div
                            style={{
                              width: `${scorePct}%`,
                              height: '100%',
                              backgroundColor:
                                scorePct > 40
                                  ? 'var(--color-error)'
                                  : scorePct > 20
                                  ? 'var(--color-warning)'
                                  : 'var(--color-success)',
                            }}
                          />
                        </div>
                        <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>{item.flaky_score.score.toFixed(2)}</span>
                      </div>
                    </td>
                    <td>
                      <span style={{ fontSize: '0.85rem' }}>{confPct}%</span>
                    </td>
                    <td>
                      <span style={{ fontSize: '0.85rem', fontWeight: 500 }}>{item.flaky_score.sample_count}</span>
                    </td>
                    <td>
                      <span
                        style={{
                          fontSize: '0.85rem',
                          color: failRatePct > 0 ? 'var(--color-error)' : 'inherit',
                          fontWeight: failRatePct > 0 ? 600 : 400,
                        }}
                      >
                        {failRatePct}%
                      </span>
                    </td>
                    <td>
                      <span style={{ fontSize: '0.85rem' }}>{rerunPct}%</span>
                    </td>
                    <td>
                      <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                        {item.flaky_score.main_failure_category || t('common:none')}
                      </span>
                    </td>
                    <td>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleOpenHistory(item.nodeid, item.project_id)}
                      >
                        {t('history')}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Execution History & Intelligence Modal */}
      {selectedTestNodeId && (
        <div className="modal-overlay">
          <div className="modal-card" style={{ maxWidth: '850px' }}>
            <div className="modal-header">
              <div>
                <h3>{t('modalTitle')}</h3>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                  {selectedTestNodeId}
                </div>
              </div>
              <button className="btn btn-secondary btn-sm" onClick={() => setSelectedTestNodeId(null)}>
                {t('common:close')}
              </button>
            </div>

            <div className="modal-body">
              {loadingHistory ? (
                <div style={{ padding: '2rem', textAlign: 'center' }}>
                  <RefreshCw size={20} className="spinning" />
                </div>
              ) : testHistory ? (
                <div>
                  {/* Trend & Metrics Overview */}
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(4, 1fr)',
                      gap: '0.75rem',
                      marginBottom: '1.25rem',
                    }}
                  >
                    <div style={{ padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--r-xs)' }}>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{t('metricPassFailSkip')}</div>
                      <div style={{ fontWeight: 600, fontSize: '1rem', marginTop: '0.25rem' }}>
                        <span style={{ color: 'var(--color-success)' }}>{testHistory.trend.pass_count}</span> /{' '}
                        <span style={{ color: 'var(--color-error)' }}>{testHistory.trend.fail_count}</span> /{' '}
                        <span>{testHistory.trend.skip_count}</span>
                      </div>
                    </div>

                    <div style={{ padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--r-xs)' }}>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{t('metricAverageDuration')}</div>
                      <div style={{ fontWeight: 600, fontSize: '1rem', marginTop: '0.25rem' }}>
                        {testHistory.trend.average_duration_ms > 1000
                          ? `${(testHistory.trend.average_duration_ms / 1000).toFixed(2)}s`
                          : `${testHistory.trend.average_duration_ms}ms`}
                      </div>
                    </div>

                    <div style={{ padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--r-xs)' }}>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{t('metricP95Duration')}</div>
                      <div style={{ fontWeight: 600, fontSize: '1rem', marginTop: '0.25rem' }}>
                        {testHistory.trend.p95_duration_ms > 1000
                          ? `${(testHistory.trend.p95_duration_ms / 1000).toFixed(2)}s`
                          : `${testHistory.trend.p95_duration_ms}ms`}
                      </div>
                    </div>

                    <div style={{ padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--r-xs)' }}>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{t('flakyScore')}</div>
                      <div style={{ fontWeight: 600, fontSize: '1rem', marginTop: '0.25rem' }}>
                        {testHistory.flaky_score.score.toFixed(2)} ({testHistory.flaky_score.classification})
                      </div>
                    </div>
                  </div>

                  {/* Execution Timeline */}
                  <h4 style={{ marginBottom: '0.75rem' }}>{t('last20Executions')}</h4>
                  {testHistory.executions.length === 0 ? (
                    <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                      {t('noExecutions')}
                    </div>
                  ) : (
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>{t('common:status')}</th>
                          <th>{t('columnRunId')}</th>
                          <th>{t('common:duration')}</th>
                          <th>{t('columnRetries')}</th>
                          <th>{t('columnFailureCategory')}</th>
                          <th>{t('columnErrorReason')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {testHistory.executions.map((e) => (
                          <tr key={e.id}>
                            <td>
                              {e.status === 'PASSED' ? (
                                <span className="status-pill status-pill-passed">PASS</span>
                              ) : e.status === 'FAILED' ? (
                                <span className="status-pill status-pill-failed">FAIL</span>
                              ) : (
                                <span className="status-pill status-pill-draft">{e.status}</span>
                              )}
                            </td>
                            <td>
                              <span
                                style={{
                                  fontFamily: 'var(--font-mono)',
                                  fontSize: '0.8rem',
                                  color: 'var(--color-primary)',
                                  cursor: 'pointer',
                                }}
                                onClick={() => {
                                  setSelectedTestNodeId(null);
                                  if (onNavigateToRuns) onNavigateToRuns(e.run_id);
                                }}
                              >
                                {e.run_id.substring(0, 10)}...
                              </span>
                            </td>
                            <td>{e.duration_ms}ms</td>
                            <td>{e.retry_count}</td>
                            <td>
                              <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                                {e.failure_category || '-'}
                              </span>
                            </td>
                            <td>
                              <span
                                style={{
                                  fontSize: '0.75rem',
                                  fontFamily: 'var(--font-mono)',
                                  color: 'var(--color-error)',
                                }}
                              >
                                {e.error_message ? e.error_message.substring(0, 55) + '...' : '-'}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
