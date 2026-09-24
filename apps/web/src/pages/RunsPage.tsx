import React, { useEffect, useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { ExternalArtifactReference, Project, RunnerProfile, RunnerType, TestRailPublishPreview, TestRailPublishResponse, TestRun, TestRunCreate } from '../types';
import { TestExecution } from '../types';
import { api } from '../api/client';
import {
  PlayCircle,
  Plus,
  RefreshCw,
  Clock,
  Terminal,
  ChevronRight,
  StopCircle,
  Sparkles,
  Cpu,
  ExternalLink,
  FileCheck,
  UploadCloud,
} from 'lucide-react';

interface RunsPageProps {
  projects: Project[];
  selectedProjectId: string | null;
  initialRunId?: string | null;
  onNavigateToFailures?: (failureId?: string) => void;
}

export const RunsPage: React.FC<RunsPageProps> = ({
  projects,
  selectedProjectId,
  initialRunId,
  onNavigateToFailures,
}) => {
  const { t } = useTranslation('runs');
  const currentProjectId = selectedProjectId || projects[0]?.id || null;

  const [runs, setRuns] = useState<TestRun[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedRun, setSelectedRun] = useState<TestRun | null>(null);
  const [runnerProfiles, setRunnerProfiles] = useState<RunnerProfile[]>([]);
  const [externalArtifacts, setExternalArtifacts] = useState<ExternalArtifactReference[]>([]);

  // New Run Modal State
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [runFormData, setRunFormData] = useState<TestRunCreate>({
    project_id: currentProjectId || '',
    workspace_id: currentProjectId || '',
    nodeids: [],
    requested_by: 'Web UI Manual Trigger',
    runner_type: 'LOCAL',
    runner_profile_id: undefined,
  });
  const [targetNodeidsText, setTargetNodeidsText] = useState<string>('');
  const [triggering, setTriggering] = useState<boolean>(false);

  // TestRail Publish State (Phase 9)
  const [isTestRailModalOpen, setIsTestRailModalOpen] = useState<boolean>(false);
  const [testRailPreview, setTestRailPreview] = useState<TestRailPublishPreview | null>(null);
  const [loadingTestRailPreview, setLoadingTestRailPreview] = useState<boolean>(false);
  const [publishingTestRail, setPublishingTestRail] = useState<boolean>(false);
  const [testRailPublishResult, setTestRailPublishResult] = useState<TestRailPublishResponse | null>(null);

  // Live SSE streaming ref
  const unsubscribeSSERef = useRef<(() => void) | null>(null);
  const terminalLogRef = useRef<HTMLDivElement | null>(null);

  const fetchRuns = async () => {
    try {
      setLoading(true);
      const [data, profiles] = await Promise.all([
        api.getTestRuns(currentProjectId || undefined),
        api.getRunnerProfiles(currentProjectId || undefined),
      ]);
      setRuns(data);
      setRunnerProfiles(profiles);
      if (!selectedRun && initialRunId) {
        const match = data.find((r) => r.id === initialRunId);
        if (match) {
          handleSelectRun(match);
          return;
        }
        // Deep link to a run that is not in the fetched window: load it directly.
        await fetchRunDetail(initialRunId);
        return;
      }
      if (data.length > 0 && !selectedRun) {
        handleSelectRun(data[0]);
      }
    } catch (err) {
      console.error('Failed to load runs', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchRunDetail = async (runId: string) => {
    try {
      const [run, artifacts] = await Promise.all([
        api.getTestRun(runId),
        api.getExternalArtifacts(runId).catch(() => [] as ExternalArtifactReference[]),
      ]);
      setSelectedRun(run);
      setExternalArtifacts(artifacts);
      // Update in list
      setRuns((prev) => prev.map((r) => (r.id === run.id ? run : r)));
    } catch (err) {
      console.error(`Failed to fetch run detail for ${runId}`, err);
    }
  };

  const handleSelectRun = (run: TestRun) => {
    setSelectedRun(run);
    fetchRunDetail(run.id);

    // Clean up previous SSE
    if (unsubscribeSSERef.current) {
      unsubscribeSSERef.current();
      unsubscribeSSERef.current = null;
    }

    // Connect SSE if run is still active
    if (run.status === 'RUNNING' || run.status === 'QUEUED') {
      const unsub = api.streamRunEvents(
        run.id,
        (event) => {
          // Event names and payloads are the ones the API publishes (see test_run_service):
          // RUN_STARTED / TEST_FINISHED / LOG_STREAM / RUN_FINISHED / RUN_ERROR / RUN_CANCELLED.
          switch (event.type) {
            case 'RUN_STARTED':
              setSelectedRun((prev) => (prev ? { ...prev, status: 'RUNNING' } : prev));
              break;
            case 'TEST_FINISHED':
              setSelectedRun((prev) => {
                if (!prev) return prev;
                const existing = prev.executions.find((e) => e.nodeid === event.nodeid);
                const nextExecutions = existing
                  ? prev.executions.map((e) =>
                      e.nodeid === event.nodeid
                        ? { ...e, status: event.status, duration_ms: event.duration_ms }
                        : e
                    )
                  : [
                      ...prev.executions,
                      {
                        id: `live_${event.nodeid}`,
                        run_id: prev.id,
                        nodeid: event.nodeid,
                        status: event.status,
                        duration_ms: event.duration_ms,
                        retry_count: 0,
                        error_message: null,
                        stack_trace: null,
                        failure_category: null,
                        artifact_paths: [],
                        started_at: new Date().toISOString(),
                        finished_at: new Date().toISOString(),
                      } as TestExecution,
                    ];
                return { ...prev, executions: nextExecutions };
              });
              break;
            case 'LOG_STREAM':
              setSelectedRun((prev) =>
                prev ? { ...prev, log_output: (prev.log_output || '') + (event.log ?? '') } : prev
              );
              break;
            case 'RUN_FINISHED':
              setSelectedRun((prev) =>
                prev
                  ? {
                      ...prev,
                      status: event.status,
                      passed: event.passed ?? prev.passed,
                      failed: event.failed ?? prev.failed,
                      duration_ms: event.duration_ms ?? prev.duration_ms,
                    }
                  : prev
              );
              fetchRunDetail(run.id);
              break;
            case 'RUN_ERROR':
            case 'RUN_CANCELLED':
              fetchRunDetail(run.id);
              break;
            default:
              break;
          }
        },
        () => {
          // On error, poll once
          fetchRunDetail(run.id);
        }
      );
      unsubscribeSSERef.current = unsub;
    }
  };

  useEffect(() => {
    fetchRuns();
    return () => {
      if (unsubscribeSSERef.current) {
        unsubscribeSSERef.current();
      }
    };
  }, [currentProjectId]);

  // Auto-scroll terminal log
  useEffect(() => {
    if (terminalLogRef.current) {
      terminalLogRef.current.scrollTop = terminalLogRef.current.scrollHeight;
    }
  }, [selectedRun?.log_output]);

  const handleCreateRun = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setTriggering(true);
      const parsedTargets = targetNodeidsText
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean);

      const projectId = currentProjectId || runFormData.project_id;
      const newRun = await api.createTestRun({
        project_id: projectId,
        workspace_id: projectId,
        nodeids: parsedTargets,
        requested_by: runFormData.requested_by || 'Web UI Manual Trigger',
        runner_type: runFormData.runner_type,
        runner_profile_id: runFormData.runner_type === 'JENKINS' ? runFormData.runner_profile_id : undefined,
      });

      setRuns([newRun, ...runs]);
      setIsModalOpen(false);
      setTargetNodeidsText('');
      handleSelectRun(newRun);
    } catch (err: any) {
      alert(t('triggerFailed', { message: err.message || err }));
    } finally {
      setTriggering(false);
    }
  };

  const handleCancelRun = async (runId: string) => {
    try {
      const updated = await api.cancelTestRun(runId);
      setSelectedRun(updated);
      setRuns(runs.map((r) => (r.id === runId ? updated : r)));
    } catch (err: any) {
      alert(t('cancelFailed', { message: err.message || err }));
    }
  };

  const handleOpenTestRailModal = async () => {
    if (!selectedRun) return;
    setIsTestRailModalOpen(true);
    setLoadingTestRailPreview(true);
    setTestRailPublishResult(null);
    try {
      const preview = await api.previewTestRailPublish(selectedRun.id, 'S101');
      setTestRailPreview(preview);
    } catch (err) {
      console.error('Failed to preview TestRail publish', err);
    } finally {
      setLoadingTestRailPreview(false);
    }
  };

  const handlePublishTestRail = async (confirmPublish: boolean) => {
    if (!selectedRun) return;
    setPublishingTestRail(true);
    try {
      const res = await api.publishTestRailResults({
        run_id: selectedRun.id,
        suite_id: 'S101',
        confirm_publish: confirmPublish,
      });
      setTestRailPublishResult(res);
    } catch (err) {
      console.error('Failed to publish to TestRail', err);
    } finally {
      setPublishingTestRail(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'PASSED':
        return <span className="badge badge-ready">PASSED</span>;
      case 'FAILED':
        return <span className="badge badge-p0">FAILED</span>;
      case 'RUNNING':
        return (
          <span className="badge badge-draft" style={{ background: '#dbeafe', color: '#1d4ed8' }}>
            ● RUNNING
          </span>
        );
      case 'QUEUED':
        return <span className="badge badge-p2">QUEUED</span>;
      case 'ERROR':
        return <span className="status-pill status-pill-error">{status}</span>;
      case 'CANCELLED':
        return <span className="badge badge-p3">CANCELLED</span>;
      default:
        return <span className="badge badge-draft">{status}</span>;
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
        <div>
          <h2 style={{ fontSize: '18px', fontWeight: 700 }}>{t('pageTitle')}</h2>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>{t('pageSubtitle')}</p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn btn-secondary btn-sm" onClick={fetchRuns} title={t('refreshRuns')}>
            <RefreshCw size={14} /> {t('common:refresh')}
          </button>
          <button
            className="btn btn-primary"
            disabled={projects.length === 0}
            onClick={() => {
              const targetProjectId = currentProjectId || projects[0]?.id || '';
              setRunFormData({
                project_id: targetProjectId,
                workspace_id: targetProjectId,
                nodeids: [],
                requested_by: 'Web UI Manual Trigger',
                runner_type: 'LOCAL',
                runner_profile_id: runnerProfiles[0]?.id,
              });
              setIsModalOpen(true);
            }}
          >
            <Plus size={16} /> {t('newRun')}
          </button>
        </div>
      </div>

      {projects.length === 0 ? (
        <div className="card">
          <div className="card-body" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
            {t('noProject')}
          </div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 2fr', gap: '20px' }}>
          {/* Left: Execution Runs List */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">{t('listTitle', { count: runs.length })}</span>
            </div>
            <div className="card-body" style={{ padding: 0 }}>
              {loading ? (
                <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  {t('listLoading')}
                </div>
              ) : runs.length === 0 ? (
                <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  <PlayCircle size={36} style={{ margin: '0 auto 8px', opacity: 0.3 }} />
                  <p style={{ fontSize: '13px' }}>{t('listEmpty')}</p>
                  <button
                    className="btn btn-primary btn-sm"
                    style={{ marginTop: '10px' }}
                    onClick={() => setIsModalOpen(true)}
                  >
                    {t('listTriggerFirst')}
                  </button>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  {runs.map((r) => {
                    const isSelected = selectedRun?.id === r.id;
                    return (
                      <div
                        key={r.id}
                        onClick={() => handleSelectRun(r)}
                        style={{
                          padding: '12px 16px',
                          borderBottom: '1px solid var(--border-color)',
                          cursor: 'pointer',
                          backgroundColor: isSelected ? '#eff6ff' : 'transparent',
                          borderLeft: isSelected ? '3px solid var(--primary)' : '3px solid transparent',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                        }}
                      >
                        <div style={{ minWidth: 0, flex: 1, paddingRight: '8px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                            {getStatusBadge(r.status)}
                            <span style={{ fontSize: '13px', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                              #{r.id.slice(0, 8)}
                            </span>
                            <span className="badge badge-draft" style={{ fontSize: '10px' }}>
                              {r.runner_type || 'LOCAL'}
                            </span>
                            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                              {r.requested_by || r.triggered_by}
                            </span>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: '11px', color: '#475569' }}>
                            <span>
                              {t('listTotal')}: <b>{r.total || r.total_tests}</b> | {t('listPassed')}:{' '}
                              <b style={{ color: '#16a34a' }}>{r.passed !== undefined ? r.passed : r.passed_tests}</b> | {t('listFailed')}:{' '}
                              <b style={{ color: '#dc2626' }}>{r.failed !== undefined ? r.failed : r.failed_tests}</b>
                            </span>
                            <span style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
                              <Clock size={11} /> {(r.duration_ms / 1000).toFixed(2)}s
                            </span>
                          </div>
                        </div>
                        <ChevronRight size={16} color={isSelected ? '#2563eb' : '#94a3b8'} />
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Right: Selected Run Detail & Live Stream */}
          {selectedRun ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {/* Summary Header */}
              <div className="card">
                <div className="card-header">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {getStatusBadge(selectedRun.status)}
                    <span className="card-title" style={{ fontFamily: 'var(--font-mono)' }}>
                      {t('runTitle', { id: selectedRun.id })}
                    </span>
                    <span className="badge badge-draft" style={{ fontSize: '11px' }}>
                      {t('runnerLabel', { type: selectedRun.runner_type || 'LOCAL' })}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {(selectedRun.status === 'RUNNING' || selectedRun.status === 'QUEUED') ? (
                      <button
                        className="btn btn-secondary btn-sm"
                        style={{ color: '#dc2626' }}
                        onClick={() => handleCancelRun(selectedRun.id)}
                      >
                        <StopCircle size={13} /> {t('cancelRun')}
                      </button>
                    ) : (
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={handleOpenTestRailModal}
                        title={t('publishTooltip')}
                      >
                        <UploadCloud size={13} color="#047857" /> {t('publishToTestRail')}
                      </button>
                    )}
                  </div>
                </div>
                <div className="card-body">
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', textAlign: 'center' }}>
                    <div style={{ background: '#f8fafc', padding: '10px', borderRadius: '6px' }}>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600 }}>{t('totalTests')}</div>
                      <div style={{ fontSize: '20px', fontWeight: 700, marginTop: '2px' }}>{selectedRun.total !== undefined ? selectedRun.total : selectedRun.total_tests}</div>
                    </div>
                    <div style={{ background: '#f0fdf4', padding: '10px', borderRadius: '6px' }}>
                      <div style={{ fontSize: '11px', color: '#16a34a', fontWeight: 600 }}>{t('detailPassed')}</div>
                      <div style={{ fontSize: '20px', fontWeight: 700, color: '#16a34a', marginTop: '2px' }}>{selectedRun.passed !== undefined ? selectedRun.passed : selectedRun.passed_tests}</div>
                    </div>
                    <div style={{ background: '#fef2f2', padding: '10px', borderRadius: '6px' }}>
                      <div style={{ fontSize: '11px', color: '#dc2626', fontWeight: 600 }}>{t('detailFailed')}</div>
                      <div style={{ fontSize: '20px', fontWeight: 700, color: '#dc2626', marginTop: '2px' }}>{selectedRun.failed !== undefined ? selectedRun.failed : selectedRun.failed_tests}</div>
                    </div>
                    <div style={{ background: '#eff6ff', padding: '10px', borderRadius: '6px' }}>
                      <div style={{ fontSize: '11px', color: '#2563eb', fontWeight: 600 }}>{t('common:duration')}</div>
                      <div style={{ fontSize: '20px', fontWeight: 700, color: '#2563eb', marginTop: '2px' }}>{(selectedRun.duration_ms / 1000).toFixed(2)}s</div>
                    </div>
                  </div>

                  {/* Runner metadata banner */}
                  {selectedRun.external_build_url && (
                    <div style={{ marginTop: '12px', padding: '10px 14px', background: '#f8fafc', borderRadius: '6px', border: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Cpu size={14} color="#64748b" />
                        <span>{t('externalJenkinsJob')} <b>{selectedRun.external_job_id || t('jenkinsDefaultJob')}</b></span>
                        {selectedRun.queue_duration_ms !== undefined && (
                          <span style={{ color: 'var(--text-muted)' }}> {t('queuedLabel', { seconds: (selectedRun.queue_duration_ms / 1000).toFixed(1) })}</span>
                        )}
                      </div>
                      <a
                        href={selectedRun.external_build_url}
                        target="_blank"
                        rel="noreferrer"
                        className="btn btn-secondary btn-sm"
                        style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', textDecoration: 'none' }}
                      >
                        <ExternalLink size={12} /> {t('openInJenkins')}
                      </a>
                    </div>
                  )}
                </div>
              </div>

              {/* External Artifacts References Card */}
              {externalArtifacts.length > 0 && (
                <div className="card">
                  <div className="card-header">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <FileCheck size={16} color="#16a34a" />
                      <span className="card-title">{t('artifactsTitle', { count: externalArtifacts.length })}</span>
                    </div>
                  </div>
                  <div className="card-body" style={{ padding: '12px' }}>
                    <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                      {externalArtifacts.map((art) => (
                        <a
                          key={art.id}
                          href={art.url}
                          target="_blank"
                          rel="noreferrer"
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            padding: '8px 12px',
                            background: '#f8fafc',
                            border: '1px solid #e2e8f0',
                            borderRadius: '6px',
                            textDecoration: 'none',
                            color: '#0f172a',
                            fontSize: '12px',
                            fontWeight: 600,
                          }}
                        >
                          <ExternalLink size={13} color="#2563eb" />
                          <span>{art.name} ({art.type})</span>
                        </a>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Individual Test Executions Table */}
              <div className="card">
                <div className="card-header">
                  <span className="card-title">{t('outcomesTitle', { count: selectedRun.executions.length })}</span>
                  {((selectedRun.failed ?? selectedRun.failed_tests ?? 0) > 0) && onNavigateToFailures && (
                    <button
                      className="btn btn-secondary btn-sm"
                      style={{ fontSize: '11px' }}
                      onClick={() => onNavigateToFailures()}
                    >
                      <Sparkles size={12} color="#9333ea" /> {t('viewFailures')}
                    </button>
                  )}
                </div>
                <div className="card-body" style={{ padding: 0 }}>
                  {selectedRun.executions.length === 0 ? (
                    <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
                      {selectedRun.status === 'RUNNING' || selectedRun.status === 'QUEUED'
                        ? t('waitingExecutions')
                        : t('noExecutions')}
                    </div>
                  ) : (
                    <table className="data-table" style={{ fontSize: '12px' }}>
                      <thead>
                        <tr>
                          <th style={{ padding: '8px 12px' }}>{t('common:status')}</th>
                          <th style={{ padding: '8px 12px' }}>{t('pytestNodeId')}</th>
                          <th style={{ padding: '8px 12px' }}>{t('common:duration')}</th>
                          <th style={{ padding: '8px 12px' }}>{t('errorDetails')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedRun.executions.map((e) => (
                          <tr key={e.id}>
                            <td style={{ padding: '8px 12px' }}>{getStatusBadge(e.status)}</td>
                            <td style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                              {e.nodeid}
                            </td>
                            <td style={{ padding: '8px 12px' }}>{(e.duration_ms / 1000).toFixed(2)}s</td>
                            <td style={{ padding: '8px 12px', color: e.error_message ? '#dc2626' : 'var(--text-muted)' }}>
                              {e.error_message || '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>

              {/* Terminal-Style Realtime Log Viewer */}
              <div className="card">
                <div className="card-header" style={{ background: '#0f172a', borderBottom: '1px solid #1e293b' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#f8fafc' }}>
                    <Terminal size={14} color="#38bdf8" />
                    <span style={{ fontSize: '12px', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                      {t('terminalTitle')}
                    </span>
                  </div>
                  {selectedRun.status === 'RUNNING' && (
                    <span style={{ fontSize: '11px', color: '#38bdf8', animation: 'pulse 1.5s infinite' }}>
                      {t('liveStreaming')}
                    </span>
                  )}
                </div>
                <div
                  ref={terminalLogRef}
                  style={{
                    background: '#090d16',
                    color: '#e2e8f0',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '12px',
                    padding: '16px',
                    maxHeight: '300px',
                    overflowY: 'auto',
                    whiteSpace: 'pre-wrap',
                    lineHeight: 1.6,
                  }}
                >
                  {selectedRun.log_output ||
                    (selectedRun.status === 'RUNNING' || selectedRun.status === 'QUEUED'
                      ? t('awaitingStream')
                      : t('noConsoleOutput'))}
                </div>
              </div>
            </div>
          ) : (
            <div className="card">
              <div className="card-body" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
                {t('emptySelection')}
              </div>
            </div>
          )}
        </div>
      )}

      {/* New Test Run Modal */}
      {isModalOpen && (
        <div className="modal-overlay">
          <div className="modal-dialog">
            <form onSubmit={handleCreateRun}>
              <div className="modal-header">
                <h3 style={{ fontSize: '15px', fontWeight: 700 }}>{t('newRunTitle')}</h3>
                <button
                  type="button"
                  style={{ background: 'none', border: 'none', cursor: 'pointer' }}
                  onClick={() => setIsModalOpen(false)}
                >
                  ✕
                </button>
              </div>
              <div className="modal-body" style={{ padding: '20px' }}>
                <div className="form-group">
                  <label className="form-label">{t('projectRequired')}</label>
                  <select
                    className="form-control"
                    value={runFormData.project_id}
                    onChange={(e) => setRunFormData({ ...runFormData, project_id: e.target.value })}
                  >
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div className="form-group">
                    <label className="form-label">{t('runnerBackend')}</label>
                    <select
                      className="form-control"
                      value={runFormData.runner_type}
                      onChange={(e) =>
                        setRunFormData({
                          ...runFormData,
                          runner_type: e.target.value as RunnerType,
                        })
                      }
                    >
                      <option value="LOCAL">{t('localRunner')}</option>
                      <option value="JENKINS">{t('jenkinsRunner')}</option>
                    </select>
                  </div>

                  {runFormData.runner_type === 'JENKINS' && (
                    <div className="form-group">
                      <label className="form-label">{t('jenkinsProfile')}</label>
                      <select
                        className="form-control"
                        value={runFormData.runner_profile_id || ''}
                        onChange={(e) =>
                          setRunFormData({
                            ...runFormData,
                            runner_profile_id: e.target.value || undefined,
                          })
                        }
                      >
                        <option value="">{t('defaultJenkinsRunner')}</option>
                        {runnerProfiles.map((prof) => (
                          <option key={prof.id} value={prof.id}>
                            {prof.name} ({prof.type})
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>

                <div className="form-group">
                  <label className="form-label">{t('triggeredBy')}</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder={t('triggeredByPlaceholder')}
                    value={runFormData.requested_by}
                    onChange={(e) =>
                      setRunFormData({ ...runFormData, requested_by: e.target.value })
                    }
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">{t('targetNodeIds')}</label>
                  <textarea
                    rows={4}
                    className="form-control"
                    placeholder="tests/test_cart.py&#10;tests/test_checkout.py::test_coupon_calculation"
                    value={targetNodeidsText}
                    onChange={(e) => setTargetNodeidsText(e.target.value)}
                  />
                </div>
              </div>
              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsModalOpen(false)}
                >
                  {t('common:cancel')}
                </button>
                <button type="submit" className="btn btn-primary" disabled={triggering}>
                  <PlayCircle size={15} /> {triggering ? t('startingRunner') : t('launchExecution')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* TestRail Publish Preview Modal (Phase 9) */}
      {isTestRailModalOpen && (
        <div className="modal-backdrop">
          <div className="modal" style={{ maxWidth: '800px', width: '90%' }}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <UploadCloud size={18} color="#047857" />
                <h3 className="modal-title">{t('testrailTitle')}</h3>
              </div>
              <button
                className="btn btn-icon"
                onClick={() => setIsTestRailModalOpen(false)}
                style={{ padding: '4px' }}
              >
                ✕
              </button>
            </div>

            <div className="modal-body">
              {loadingTestRailPreview ? (
                <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  <RefreshCw size={24} className="spin" style={{ margin: '0 auto 12px', color: '#047857' }} />
                  <p>{t('testrailMatching')}</p>
                </div>
              ) : testRailPreview ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  {testRailPublishResult && (
                    <div
                      style={{
                        padding: '12px 16px',
                        borderRadius: '6px',
                        backgroundColor: testRailPublishResult.published ? '#f0fdf4' : '#eff6ff',
                        border: `1px solid ${testRailPublishResult.published ? '#86efac' : '#93c5fd'}`,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                    >
                      <div>
                        <div style={{ fontWeight: 600, fontSize: '13px', color: testRailPublishResult.published ? '#166534' : '#1e40af' }}>
                          {testRailPublishResult.message}
                        </div>
                        {testRailPublishResult.testrail_run_id && (
                          <div style={{ fontSize: '12px', color: '#047857', marginTop: '4px', fontWeight: 600 }}>
                            {t('testrailRunId', { id: testRailPublishResult.testrail_run_id })}
                          </div>
                        )}
                      </div>
                      <span className="badge badge-ready" style={{ fontSize: '11px' }}>
                        {testRailPublishResult.published ? 'PUBLISHED' : 'DRY_RUN_OK'}
                      </span>
                    </div>
                  )}

                  {/* Summary Metric Cards */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', textAlign: 'center' }}>
                    <div style={{ background: '#f8fafc', padding: '10px', borderRadius: '6px' }}>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600 }}>{t('totalExecuted')}</div>
                      <div style={{ fontSize: '18px', fontWeight: 700 }}>{testRailPreview.total_tests}</div>
                    </div>
                    <div style={{ background: '#ecfdf5', padding: '10px', borderRadius: '6px' }}>
                      <div style={{ fontSize: '11px', color: '#047857', fontWeight: 600 }}>{t('mappedToTestRail')}</div>
                      <div style={{ fontSize: '18px', fontWeight: 700, color: '#047857' }}>{testRailPreview.mapped_tests}</div>
                    </div>
                    <div style={{ background: '#fef3c7', padding: '10px', borderRadius: '6px' }}>
                      <div style={{ fontSize: '11px', color: '#b45309', fontWeight: 600 }}>{t('unmappedTests')}</div>
                      <div style={{ fontSize: '18px', fontWeight: 700, color: '#b45309' }}>{testRailPreview.unmapped_tests}</div>
                    </div>
                  </div>

                  {/* Status Mapping Table */}
                  <div style={{ maxHeight: '280px', overflowY: 'auto', border: '1px solid var(--border-color)', borderRadius: '6px' }}>
                    <table className="data-table" style={{ fontSize: '12px' }}>
                      <thead>
                        <tr>
                          <th>{t('testNode')}</th>
                          <th>{t('testrailId')}</th>
                          <th>{t('pytestStatus')}</th>
                          <th>{t('mappedTrStatus')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {testRailPreview.items.map((item, idx) => (
                          <tr key={idx}>
                            <td style={{ fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
                              {item.test_name}
                            </td>
                            <td>
                              {item.external_case_id ? (
                                <span style={{ fontWeight: 700, color: '#047857', background: '#ecfdf5', padding: '2px 6px', borderRadius: '4px', fontSize: '11px' }}>
                                  {item.external_case_id}
                                </span>
                              ) : (
                                <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>{t('unmappedValue')}</span>
                              )}
                            </td>
                            <td>
                              <span className={`badge badge-${item.pytest_status.toLowerCase() === 'passed' ? 'ready' : (item.pytest_status.toLowerCase() === 'failed' ? 'p0' : 'draft')}`} style={{ fontSize: '10px' }}>
                                {item.pytest_status}
                              </span>
                            </td>
                            <td>
                              <span style={{ fontWeight: 600, color: item.mapped_testrail_status === 'Passed' ? '#16a34a' : (item.mapped_testrail_status === 'Failed' ? '#dc2626' : '#64748b') }}>
                                {item.mapped_testrail_status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <div style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  {t('previewFailed')}
                </div>
              )}
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setIsTestRailModalOpen(false)}
              >
                {t('common:close')}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={!testRailPreview || publishingTestRail}
                onClick={() => handlePublishTestRail(false)}
              >
                {t('dryRunPreview')}
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={!testRailPreview || publishingTestRail}
                onClick={() => handlePublishTestRail(true)}
              >
                {publishingTestRail ? t('publishing') : t('confirmPublish')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
