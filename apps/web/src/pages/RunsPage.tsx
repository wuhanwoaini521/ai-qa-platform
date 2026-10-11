import React, { useEffect, useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Project,
  RunnerProfile,
  RunnerType,
  TestRailPublishPreview,
  TestRailPublishResponse,
  TestRun,
  TestRunCreate,
} from '../types';
import { api } from '../api/client';
import {
  ContextTaskProgress,
  useContextTask,
} from '../components/ContextTaskProgress';
import { RuntimeDetail } from '../features/runtime/RuntimeDetail';
import { useRunStore } from '../features/runs/useRunStore';
import {
  PlayCircle,
  Plus,
  RefreshCw,
  Clock,
  ChevronRight,
  StopCircle,
  Sparkles,
  Cpu,
  ExternalLink,
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
}) => {
  const { t } = useTranslation('runs');
  const currentProjectId = selectedProjectId || projects[0]?.id || null;

  const [runs, setRuns] = useState<TestRun[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(
    initialRunId ?? null,
  );
  const live = useRunStore(selectedRunId);
  const selectedRun = live.run;
  const regressionTask = useContextTask(
    currentProjectId,
    'run',
    selectedRun?.id ?? currentProjectId,
  );
  const [runnerProfiles, setRunnerProfiles] = useState<RunnerProfile[]>([]);
  // New Run Modal State
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [runFormData, setRunFormData] = useState<TestRunCreate>({
    project_id: currentProjectId || '',
    workspace_id: currentProjectId || '',
    nodeids: [],
    requested_by: 'Web UI Manual Trigger',
    runner_type: 'LOCAL',
    runner_profile_id: undefined,
    parallel_workers: 1,
  });
  const [targetNodeidsText, setTargetNodeidsText] = useState<string>('');
  const [triggering, setTriggering] = useState<boolean>(false);

  // TestRail Publish State (Phase 9)
  const [isTestRailModalOpen, setIsTestRailModalOpen] =
    useState<boolean>(false);
  const [testRailPreview, setTestRailPreview] =
    useState<TestRailPublishPreview | null>(null);
  const [loadingTestRailPreview, setLoadingTestRailPreview] =
    useState<boolean>(false);
  const [publishingTestRail, setPublishingTestRail] = useState<boolean>(false);
  const [testRailPublishResult, setTestRailPublishResult] =
    useState<TestRailPublishResponse | null>(null);

  const activeRunIdRef = useRef<string | null>(initialRunId ?? null);
  const listRequestRef = useRef(0);

  const fetchRuns = async () => {
    const requestId = ++listRequestRef.current;
    try {
      setLoading(true);
      const [data, profiles] = await Promise.all([
        api.getTestRuns(currentProjectId || undefined),
        api.getRunnerProfiles(currentProjectId || undefined),
      ]);
      if (requestId !== listRequestRef.current) return;
      setRuns(data);
      setRunnerProfiles(profiles);
      if (initialRunId) {
        const match = data.find((r) => r.id === initialRunId);
        if (match) {
          handleSelectRun(match);
          return;
        }
        // Deep link to a run that is not in the fetched window: load it directly.
        activeRunIdRef.current = initialRunId;
        const linkedRun = await api.getTestRun(initialRunId);
        if (
          requestId === listRequestRef.current &&
          activeRunIdRef.current === initialRunId
        )
          handleSelectRun(linkedRun);
        return;
      }
      if (data.length > 0 && !activeRunIdRef.current) {
        handleSelectRun(data[0]);
      } else if (!data.length) {
        activeRunIdRef.current = null;
        setSelectedRunId(null);
      }
    } catch (err) {
      console.error('Failed to load runs', err);
    } finally {
      if (requestId === listRequestRef.current) setLoading(false);
    }
  };

  const handleSelectRun = (run: TestRun) => {
    activeRunIdRef.current = run.id;
    setSelectedRunId(run.id);
  };

  useEffect(() => {
    activeRunIdRef.current = initialRunId ?? null;
    setSelectedRunId(initialRunId ?? null);
    void fetchRuns();
    return () => {
      listRequestRef.current += 1;
      activeRunIdRef.current = null;
    };
  }, [currentProjectId, initialRunId]);

  useEffect(() => {
    if (live.run)
      setRuns((previous) =>
        previous.map((run) => (run.id === live.run!.id ? live.run! : run)),
      );
  }, [live.run]);

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
        runner_profile_id:
          runFormData.runner_type === 'JENKINS'
            ? runFormData.runner_profile_id
            : undefined,
        parallel_workers:
          runFormData.runner_type === 'LOCAL'
            ? (runFormData.parallel_workers ?? 1)
            : 1,
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

  const handleAiRegression = () => {
    if (!currentProjectId) return;
    void regressionTask.start({
      type: 'RUN_REGRESSION',
      goal: selectedRun
        ? t('aiRegressionRunGoal', { id: selectedRun.id })
        : t('aiRegressionProjectGoal'),
      project_id: currentProjectId,
      workspace_id: currentProjectId,
      inputs: {
        ...(selectedRun
          ? {
              source_run_id: selectedRun.id,
              nodeids: selectedRun.nodeids.length
                ? selectedRun.nodeids
                : selectedRun.executions.map((execution) => execution.nodeid),
              environment: selectedRun.environment,
              browser: selectedRun.browser,
              markers: selectedRun.markers,
              runner_type: selectedRun.runner_type,
              runner_profile_id: selectedRun.runner_profile_id,
            }
          : {}),
      },
    });
  };

  const handleCancelRun = async (runId: string) => {
    try {
      const updated = await api.cancelTestRun(runId);
      if (activeRunIdRef.current === runId) {
        await live.refresh();
      }
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
          <span
            className="badge badge-draft"
            style={{ background: 'var(--accent-blue-soft)', color: 'var(--accent-blue)' }}
          >
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
    <div className="runs-page">
      <div className="page-header runs-page-header">
        <div>
          <h2 style={{ fontSize: '18px', fontWeight: 700 }}>
            {t('pageTitle')}
          </h2>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            {t('pageSubtitle')}
          </p>
        </div>
        <div
          className="runs-page-actions"
          style={{ display: 'flex', gap: '8px' }}
        >
          <button
            className="btn btn-secondary"
            disabled={!currentProjectId || regressionTask.busy}
            onClick={handleAiRegression}
          >
            <Sparkles size={16} />{' '}
            {regressionTask.busy
              ? t('aiRegressionStarting')
              : t('aiRegression')}
          </button>
          <button
            className="btn btn-secondary btn-sm"
            onClick={fetchRuns}
            title={t('refreshRuns')}
          >
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
                parallel_workers: 1,
              });
              setIsModalOpen(true);
            }}
          >
            <Plus size={16} /> {t('newRun')}
          </button>
        </div>
      </div>

      <ContextTaskProgress
        task={regressionTask.task}
        error={regressionTask.error}
      />

      {projects.length === 0 ? (
        <div className="card">
          <div
            className="card-body"
            style={{
              padding: '40px',
              textAlign: 'center',
              color: 'var(--text-muted)',
            }}
          >
            {t('noProject')}
          </div>
        </div>
      ) : (
        <div className="runs-layout-grid">
          {/* Left: Execution Runs List */}
          <div className="card runs-list-card">
            <div className="card-header">
              <span className="card-title">
                {t('listTitle', { count: runs.length })}
              </span>
            </div>
            <div className="card-body runs-list-scroll" style={{ padding: 0 }}>
              {loading ? (
                <div
                  style={{
                    padding: '32px',
                    textAlign: 'center',
                    color: 'var(--text-muted)',
                  }}
                >
                  {t('listLoading')}
                </div>
              ) : runs.length === 0 ? (
                <div
                  style={{
                    padding: '40px',
                    textAlign: 'center',
                    color: 'var(--text-muted)',
                  }}
                >
                  <PlayCircle
                    size={36}
                    style={{ margin: '0 auto 8px', opacity: 0.3 }}
                  />
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
                      <button
                        type="button"
                        key={r.id}
                        onClick={() => handleSelectRun(r)}
                        className={`select-row ${isSelected ? 'is-selected' : ''}`}
                        aria-pressed={isSelected}
                      >
                        <div
                          style={{ minWidth: 0, flex: 1, paddingRight: '8px' }}
                        >
                          <div
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: '8px',
                              marginBottom: '4px',
                            }}
                          >
                            {getStatusBadge(r.status)}
                            <span
                              style={{
                                fontSize: '13px',
                                fontWeight: 600,
                                fontFamily: 'var(--font-mono)',
                              }}
                            >
                              #{r.id.slice(0, 8)}
                            </span>
                            <span
                              className="badge badge-draft"
                              style={{ fontSize: '10px' }}
                            >
                              {r.runner_type || 'LOCAL'}
                            </span>
                            <span
                              style={{
                                fontSize: '11px',
                                color: 'var(--text-muted)',
                              }}
                            >
                              {r.requested_by || r.triggered_by}
                            </span>
                          </div>
                          <div
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: '12px',
                              fontSize: '11px',
                              color: 'var(--ink-muted)',
                            }}
                          >
                            <span>
                              {t('listTotal')}:{' '}
                              <b>{r.total ?? r.total_tests}</b> |{' '}
                              {t('listPassed')}:{' '}
                              <b style={{ color: 'var(--accent-green)' }}>
                                {r.passed !== undefined
                                  ? r.passed
                                  : r.passed_tests}
                              </b>{' '}
                              | {t('listFailed')}:{' '}
                              <b style={{ color: 'var(--accent-red)' }}>
                                {r.failed !== undefined
                                  ? r.failed
                                  : r.failed_tests}
                              </b>
                            </span>
                            <span
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '3px',
                              }}
                            >
                              <Clock size={11} />{' '}
                              {(r.duration_ms / 1000).toFixed(2)}s
                            </span>
                          </div>
                        </div>
                        <ChevronRight
                          size={16}
                          color={isSelected ? 'var(--accent-blue)' : 'var(--ink-faint)'}
                        />
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Right: Selected Run Detail & Live Stream */}
          {selectedRun ? (
            <div
              style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}
            >
              <RuntimeDetail
                key={selectedRun.id}
                kind="run"
                id={selectedRun.id}
              />
              {/* Summary Header */}
              <div className="card">
                <div className="card-header runs-selected-header">
                  <div
                    className="runs-selected-meta"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                    }}
                  >
                    {getStatusBadge(selectedRun.status)}
                    <span
                      className="card-title"
                      style={{ fontFamily: 'var(--font-mono)' }}
                    >
                      {t('runTitle', { id: selectedRun.id })}
                    </span>
                    <span
                      className="badge badge-draft"
                      style={{ fontSize: '11px' }}
                    >
                      {t('runnerLabel', {
                        type: selectedRun.runner_type || 'LOCAL',
                      })}
                    </span>
                  </div>
                  <div
                    className="runs-selected-actions"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                    }}
                  >
                    {selectedRun.status === 'RUNNING' ||
                    selectedRun.status === 'QUEUED' ? (
                      <button
                        className="btn btn-secondary btn-sm"
                        style={{ color: 'var(--accent-red)' }}
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
                        <UploadCloud size={13} color="var(--accent-green)" />{' '}
                        {t('publishToTestRail')}
                      </button>
                    )}
                  </div>
                </div>
                <div className="card-body">
                  {/* Runner metadata banner */}
                  {selectedRun.external_build_url && (
                    <div
                      style={{
                        marginTop: '12px',
                        padding: '10px 14px',
                        background: 'var(--surface-inset)',
                        borderRadius: 'var(--r-xs)',
                        border: '1px solid var(--line-strong)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        fontSize: '12px',
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                        }}
                      >
                        <Cpu size={14} color="var(--ink-muted)" />
                        <span>
                          {t('externalJenkinsJob')}{' '}
                          <b>
                            {selectedRun.external_job_id ||
                              t('jenkinsDefaultJob')}
                          </b>
                        </span>
                        {selectedRun.queue_duration_ms !== undefined && (
                          <span style={{ color: 'var(--text-muted)' }}>
                            {' '}
                            {t('queuedLabel', {
                              seconds: (
                                selectedRun.queue_duration_ms / 1000
                              ).toFixed(1),
                            })}
                          </span>
                        )}
                      </div>
                      <a
                        href={selectedRun.external_build_url}
                        target="_blank"
                        rel="noreferrer"
                        className="btn btn-secondary btn-sm"
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                          textDecoration: 'none',
                        }}
                      >
                        <ExternalLink size={12} /> {t('openInJenkins')}
                      </a>
                    </div>
                  )}
                </div>
              </div>

            </div>
          ) : (
            <div className="card">
              <div
                className="card-body"
                style={{
                  padding: '40px',
                  textAlign: 'center',
                  color: 'var(--text-muted)',
                }}
              >
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
                <h3 style={{ fontSize: '15px', fontWeight: 700 }}>
                  {t('newRunTitle')}
                </h3>
                <button
                  type="button"
                  style={{
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                  }}
                  onClick={() => setIsModalOpen(false)}
                >
                  ✕
                </button>
              </div>
              <div className="modal-body" style={{ padding: '20px' }}>
                <div className="form-group">
                  <label className="form-label" htmlFor="run-project">{t('projectRequired')}</label>
                  <select
                    id="run-project"
                    className="form-control"
                    value={runFormData.project_id}
                    onChange={(e) =>
                      setRunFormData({
                        ...runFormData,
                        project_id: e.target.value,
                      })
                    }
                  >
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: '12px',
                  }}
                >
                  <div className="form-group">
                    <label className="form-label" htmlFor="run-runner-backend">{t('runnerBackend')}</label>
                    <select
                      id="run-runner-backend"
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
                      <option value="WORKER">{t('workerRunner')}</option>
                      <option value="JENKINS">{t('jenkinsRunner')}</option>
                    </select>
                  </div>

                  {runFormData.runner_type === 'JENKINS' && (
                    <div className="form-group">
                      <label className="form-label" htmlFor="run-jenkins-profile">
                        {t('jenkinsProfile')}
                      </label>
                      <select
                        id="run-jenkins-profile"
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
                      setRunFormData({
                        ...runFormData,
                        requested_by: e.target.value,
                      })
                    }
                  />
                </div>

                {runFormData.runner_type === 'LOCAL' && (
                  <div className="form-group">
                    <label className="form-label" htmlFor="parallel-workers">
                      {t('parallelWorkers')}
                    </label>
                    <input
                      id="parallel-workers"
                      className="form-control"
                      type="number"
                      min={1}
                      max={16}
                      step={1}
                      value={runFormData.parallel_workers ?? 1}
                      onChange={(event) =>
                        setRunFormData({
                          ...runFormData,
                          parallel_workers: Math.max(
                            1,
                            Math.min(16, Number(event.target.value) || 1),
                          ),
                        })
                      }
                    />
                  </div>
                )}

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
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={triggering}
                >
                  <PlayCircle size={15} />{' '}
                  {triggering ? t('startingRunner') : t('launchExecution')}
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
              <div
                style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
              >
                <UploadCloud size={18} color="var(--accent-green)" />
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
                <div
                  style={{
                    padding: '40px',
                    textAlign: 'center',
                    color: 'var(--text-muted)',
                  }}
                >
                  <RefreshCw
                    size={24}
                    className="spin"
                    style={{ margin: '0 auto 12px', color: 'var(--accent-green)' }}
                  />
                  <p>{t('testrailMatching')}</p>
                </div>
              ) : testRailPreview ? (
                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '14px',
                  }}
                >
                  {testRailPublishResult && (
                    <div
                      style={{
                        padding: '12px 16px',
                        borderRadius: 'var(--r-xs)',
                        backgroundColor: testRailPublishResult.published
                          ? 'var(--accent-green-soft)'
                          : 'var(--accent-blue-soft)',
                        border: `1px solid ${testRailPublishResult.published ? 'var(--accent-green)' : 'var(--accent-blue)'}`,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                    >
                      <div>
                        <div
                          style={{
                            fontWeight: 600,
                            fontSize: '13px',
                            color: testRailPublishResult.published
                              ? 'var(--accent-green)'
                              : 'var(--accent-blue)',
                          }}
                        >
                          {testRailPublishResult.message}
                        </div>
                        {testRailPublishResult.testrail_run_id && (
                          <div
                            style={{
                              fontSize: '12px',
                              color: 'var(--accent-green)',
                              marginTop: '4px',
                              fontWeight: 600,
                            }}
                          >
                            {t('testrailRunId', {
                              id: testRailPublishResult.testrail_run_id,
                            })}
                          </div>
                        )}
                      </div>
                      <span
                        className="badge badge-ready"
                        style={{ fontSize: '11px' }}
                      >
                        {testRailPublishResult.published
                          ? 'PUBLISHED'
                          : 'DRY_RUN_OK'}
                      </span>
                    </div>
                  )}

                  {/* Summary Metric Cards */}
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(3, 1fr)',
                      gap: '12px',
                      textAlign: 'center',
                    }}
                  >
                    <div
                      style={{
                        background: 'var(--surface-inset)',
                        padding: '10px',
                        borderRadius: 'var(--r-xs)',
                      }}
                    >
                      <div
                        style={{
                          fontSize: '11px',
                          color: 'var(--text-muted)',
                          fontWeight: 600,
                        }}
                      >
                        {t('totalExecuted')}
                      </div>
                      <div style={{ fontSize: '18px', fontWeight: 700 }}>
                        {testRailPreview.total_tests}
                      </div>
                    </div>
                    <div
                      style={{
                        background: 'var(--accent-green-soft)',
                        padding: '10px',
                        borderRadius: 'var(--r-xs)',
                      }}
                    >
                      <div
                        style={{
                          fontSize: '11px',
                          color: 'var(--accent-green)',
                          fontWeight: 600,
                        }}
                      >
                        {t('mappedToTestRail')}
                      </div>
                      <div
                        style={{
                          fontSize: '18px',
                          fontWeight: 700,
                          color: 'var(--accent-green)',
                        }}
                      >
                        {testRailPreview.mapped_tests}
                      </div>
                    </div>
                    <div
                      style={{
                        background: 'var(--accent-amber-soft)',
                        padding: '10px',
                        borderRadius: 'var(--r-xs)',
                      }}
                    >
                      <div
                        style={{
                          fontSize: '11px',
                          color: 'var(--accent-amber)',
                          fontWeight: 600,
                        }}
                      >
                        {t('unmappedTests')}
                      </div>
                      <div
                        style={{
                          fontSize: '18px',
                          fontWeight: 700,
                          color: 'var(--accent-amber)',
                        }}
                      >
                        {testRailPreview.unmapped_tests}
                      </div>
                    </div>
                  </div>

                  {/* Status Mapping Table */}
                  <div
                    style={{
                      maxHeight: '280px',
                      overflowY: 'auto',
                      border: '1px solid var(--border-color)',
                      borderRadius: 'var(--r-xs)',
                    }}
                  >
                    <div className="table-responsive">
                      <table
                        className="data-table"
                        style={{ fontSize: '12px' }}
                      >
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
                              <td
                                style={{
                                  fontFamily: 'var(--font-mono)',
                                  fontSize: '11px',
                                }}
                              >
                                {item.test_name}
                              </td>
                              <td>
                                {item.external_case_id ? (
                                  <span
                                    style={{
                                      fontWeight: 700,
                                      color: 'var(--accent-green)',
                                      background: 'var(--accent-green-soft)',
                                      padding: '2px 6px',
                                      borderRadius: 'var(--r-xs)',
                                      fontSize: '11px',
                                    }}
                                  >
                                    {item.external_case_id}
                                  </span>
                                ) : (
                                  <span
                                    style={{
                                      color: 'var(--text-muted)',
                                      fontSize: '11px',
                                    }}
                                  >
                                    {t('unmappedValue')}
                                  </span>
                                )}
                              </td>
                              <td>
                                <span
                                  className={`badge badge-${item.pytest_status.toLowerCase() === 'passed' ? 'ready' : item.pytest_status.toLowerCase() === 'failed' ? 'p0' : 'draft'}`}
                                  style={{ fontSize: '10px' }}
                                >
                                  {item.pytest_status}
                                </span>
                              </td>
                              <td>
                                <span
                                  style={{
                                    fontWeight: 600,
                                    color:
                                      item.mapped_testrail_status === 'Passed'
                                        ? 'var(--accent-green)'
                                        : item.mapped_testrail_status ===
                                            'Failed'
                                          ? 'var(--accent-red)'
                                          : 'var(--ink-muted)',
                                  }}
                                >
                                  {item.mapped_testrail_status}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              ) : (
                <div
                  style={{
                    padding: '30px',
                    textAlign: 'center',
                    color: 'var(--text-muted)',
                  }}
                >
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
