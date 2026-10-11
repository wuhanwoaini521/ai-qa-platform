import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Server,
  Activity,
  Cpu,
  Layers,
  Plus,
  RefreshCw,
  Trash2,
  XCircle,
  Clock,
  Radio,
} from 'lucide-react';
import {
  ClusterStatusSummary,
  ExecutionJob,
  Worker,
  WorkerStatus,
} from '../types';
import { api } from '../api/client';

export const WorkersPage: React.FC = () => {
  const { t } = useTranslation('workers');
  const [activeTab, setActiveTab] = useState<'workers' | 'jobs'>('workers');

  // Cluster State
  const [clusterSummary, setClusterSummary] = useState<ClusterStatusSummary | null>(null);
  const [loadingCluster, setLoadingCluster] = useState<boolean>(true);

  // Workers State
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [showRegisterModal, setShowRegisterModal] = useState<boolean>(false);
  const [newHostname, setNewHostname] = useState<string>('');
  const [newIpAddress, setNewIpAddress] = useState<string>('127.0.0.1');
  const [newConcurrency, setNewConcurrency] = useState<number>(4);
  const [registering, setRegistering] = useState<boolean>(false);

  // Jobs State
  const [jobs, setJobs] = useState<ExecutionJob[]>([]);
  const [loadingJobs, setLoadingJobs] = useState<boolean>(false);

  const fetchClusterAndWorkers = async () => {
    try {
      setLoadingCluster(true);
      const summary = await api.getClusterStatus();
      setClusterSummary(summary);
      setWorkers(summary.workers);
    } catch (err) {
      console.error('Failed to load cluster status', err);
    } finally {
      setLoadingCluster(false);
    }
  };

  const fetchJobs = async () => {
    try {
      setLoadingJobs(true);
      const data = await api.getJobs();
      setJobs(data);
    } catch (err) {
      console.error('Failed to load jobs', err);
    } finally {
      setLoadingJobs(false);
    }
  };

  useEffect(() => {
    fetchClusterAndWorkers();
    if (activeTab === 'jobs') {
      fetchJobs();
    }
  }, [activeTab]);

  const handleRegisterWorker = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newHostname) return;
    try {
      setRegistering(true);
      const created = await api.registerWorker({
        hostname: newHostname,
        ip_address: newIpAddress,
        max_concurrency: newConcurrency,
        browsers: ['chromium', 'firefox', 'webkit'],
      });
      setWorkers([created, ...workers]);
      setShowRegisterModal(false);
      setNewHostname('');
      setNewIpAddress('127.0.0.1');
      fetchClusterAndWorkers();
    } catch (err) {
      console.error('Failed to register worker', err);
    } finally {
      setRegistering(false);
    }
  };

  const handleDeleteWorker = async (workerId: string) => {
    try {
      await api.deleteWorker(workerId);
      setWorkers(workers.filter((w) => w.id !== workerId));
      fetchClusterAndWorkers();
    } catch (err) {
      console.error('Failed to deregister worker', err);
    }
  };

  const handleCancelJob = async (jobId: string) => {
    try {
      const updated = await api.cancelJob(jobId);
      setJobs(jobs.map((j) => (j.id === jobId ? updated : j)));
    } catch (err) {
      console.error('Failed to cancel job', err);
    }
  };

  const getWorkerStatusBadge = (status: WorkerStatus) => {
    switch (status) {
      case 'ONLINE':
        return <span className="status-pill status-pill-passed">ONLINE</span>;
      case 'BUSY':
        return <span className="status-pill status-pill-warning">BUSY</span>;
      case 'LOST':
        return <span className="status-pill status-pill-error">LOST</span>;
      case 'OFFLINE':
      default:
        return <span className="status-pill status-pill-draft">OFFLINE</span>;
    }
  };

  const getJobStatusBadge = (status: string) => {
    switch (status) {
      case 'COMPLETED':
        return <span className="status-pill status-pill-passed">COMPLETED</span>;
      case 'RUNNING':
        return <span className="status-pill status-pill-warning">RUNNING</span>;
      case 'ASSIGNED':
        return <span className="status-pill status-pill-draft">ASSIGNED</span>;
      case 'QUEUED':
        return <span className="status-pill status-pill-draft">QUEUED</span>;
      case 'FAILED':
        return <span className="status-pill status-pill-failed">FAILED</span>;
      case 'CANCELLED':
      default:
        return <span className="status-pill status-pill-error">{status}</span>;
    }
  };

  return (
    <div className="page-container">
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h2>{t('title')}</h2>
          <p className="subtitle">{t('subtitle')}</p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn btn-primary" onClick={() => setShowRegisterModal(true)}>
            <Plus size={14} />
            <span>{t('registerWorker')}</span>
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => {
              fetchClusterAndWorkers();
              if (activeTab === 'jobs') fetchJobs();
            }}
          >
            <RefreshCw size={14} className={loadingCluster || loadingJobs ? 'spinning' : ''} />
            <span>{t('common:refresh')}</span>
          </button>
        </div>
      </div>

      {/* Cluster Stats Grid */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon" style={{ backgroundColor: 'rgba(59, 130, 246, 0.1)', color: 'var(--accent-primary)' }}>
            <Server size={20} />
          </div>
          <div className="stat-details">
            <div className="stat-title">{t('statClusterWorkers')}</div>
            <div className="stat-value">
              {clusterSummary ? clusterSummary.total_workers : '--'}
            </div>
            <div className="stat-subtitle">
              {clusterSummary
                ? t('statOnlineBusy', {
                    online: clusterSummary.online_workers,
                    busy: clusterSummary.busy_workers,
                  })
                : t('statZeroWorkers')}
            </div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon" style={{ backgroundColor: 'rgba(16, 185, 129, 0.1)', color: 'var(--accent-green)' }}>
            <Radio size={20} />
          </div>
          <div className="stat-details">
            <div className="stat-title">{t('statOnlineWorkers')}</div>
            <div className="stat-value">
              {clusterSummary ? clusterSummary.online_workers : '--'}
            </div>
            <div className="stat-subtitle">{t('statOnlineWorkersHint')}</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon" style={{ backgroundColor: 'rgba(16, 185, 129, 0.1)', color: 'var(--accent-green)' }}>
            <Cpu size={20} />
          </div>
          <div className="stat-details">
            <div className="stat-title">{t('statConcurrencyCapacity')}</div>
            <div className="stat-value">
              {clusterSummary ? `${clusterSummary.used_concurrency} / ${clusterSummary.total_concurrency_capacity}` : '--'}
            </div>
            <div className="stat-subtitle">
              {clusterSummary && clusterSummary.total_concurrency_capacity > 0
                ? t('statLoadPercent', {
                    percent: Math.round(
                      (clusterSummary.used_concurrency / clusterSummary.total_concurrency_capacity) * 100,
                    ),
                  })
                : t('statZeroLoad')}
            </div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon" style={{ backgroundColor: 'rgba(245, 158, 11, 0.1)', color: 'var(--accent-amber)' }}>
            <Layers size={20} />
          </div>
          <div className="stat-details">
            <div className="stat-title">{t('statQueuedTasks')}</div>
            <div className="stat-value">
              {clusterSummary ? clusterSummary.queued_jobs_count : '--'}
            </div>
            <div className="stat-subtitle">{t('statQueuedTasksHint')}</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon" style={{ backgroundColor: 'rgba(139, 92, 246, 0.1)', color: 'var(--accent-violet)' }}>
            <Activity size={20} />
          </div>
          <div className="stat-details">
            <div className="stat-title">{t('statActiveTasks')}</div>
            <div className="stat-value">
              {clusterSummary ? clusterSummary.running_jobs_count : '--'}
            </div>
            <div className="stat-subtitle">{t('statActiveTasksHint')}</div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="tabs-container" style={{ margin: '1.5rem 0 1rem' }}>
        <button
          className={`tab-btn ${activeTab === 'workers' ? 'active' : ''}`}
          onClick={() => setActiveTab('workers')}
        >
          <Server size={15} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
          {t('tabWorkers', { total: workers.length })}
        </button>
        <button
          className={`tab-btn ${activeTab === 'jobs' ? 'active' : ''}`}
          onClick={() => setActiveTab('jobs')}
        >
          <Layers size={15} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
          {t('tabJobs', { total: jobs.length })}
        </button>
      </div>

      {/* Tab 1: Workers Grid & Table */}
      {activeTab === 'workers' && (
        <div className="card">
          <div className="card-header">
            <h3>{t('workersTitle')}</h3>
            <span className="text-secondary text-sm">{t('workersHint')}</span>
          </div>
          <div className="table-responsive">
            <table className="data-table worker-table">
              <thead>
                <tr>
                  <th>{t('colHostname')}</th>
                  <th>{t('colIpAddress')}</th>
                  <th>{t('common:status')}</th>
                  <th>{t('colConcurrencyLoad')}</th>
                  <th>{t('colSupportedBrowsers')}</th>
                  <th>{t('colOs')}</th>
                  <th>{t('colLastHeartbeat')}</th>
                  <th>{t('common:actions')}</th>
                </tr>
              </thead>
              <tbody>
                {workers.length > 0 ? (
                  workers.map((w) => (
                    <tr key={w.id}>
                      <td style={{ fontWeight: 600 }}>{w.hostname}</td>
                      <td><code>{w.ip_address}</code></td>
                      <td>{getWorkerStatusBadge(w.status)}</td>
                      <td>
                        <div className="worker-load">
                          <div className="worker-load-track" role="img" aria-label={`${w.current_load} / ${w.max_concurrency} slots in use`}>
                            <div
                              className="worker-load-fill"
                              style={{ width: `${w.max_concurrency > 0 ? (w.current_load / w.max_concurrency) * 100 : 0}%` }}
                            />
                          </div>
                          <span>{w.current_load}/{w.max_concurrency}</span>
                        </div>
                      </td>
                      <td>
                        <div className="worker-capabilities">
                          {w.browsers.length > 0 && <span className="status-pill status-pill-runtime">Playwright</span>}
                          {w.browsers.map((b) => (
                            <span key={b} className="status-pill status-pill-draft">
                              {b}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td><span className="status-pill status-pill-draft worker-os">{w.os}</span></td>
                      <td style={{ fontSize: '0.85rem' }}>
                        <div className="worker-heartbeat">
                          <Radio size={12} aria-hidden="true" />
                          <span>{new Date(w.last_heartbeat_at).toLocaleTimeString()}</span>
                        </div>
                      </td>
                      <td>
                        <button
                          className="btn btn-secondary btn-sm"
                          style={{ color: 'var(--accent-red)' }}
                          onClick={() => handleDeleteWorker(w.id)}
                        >
                          <Trash2 size={13} />
                          <span>{t('deregister')}</span>
                        </button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={8} className="text-center text-secondary py-4">
                      {loadingCluster ? t('loadingWorkers') : t('emptyWorkers')}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 2: Distributed Job Queue */}
      {activeTab === 'jobs' && (
        <div className="card">
          <div className="card-header">
            <h3>{t('jobsTitle')}</h3>
            <span className="text-secondary text-sm">{t('jobsHint')}</span>
          </div>
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t('colJobId')}</th>
                  <th>{t('colRunId')}</th>
                  <th>{t('common:priority')}</th>
                  <th>{t('colBrowser')}</th>
                  <th>{t('common:status')}</th>
                  <th>{t('colAssignedWorker')}</th>
                  <th>{t('colTestCount')}</th>
                  <th>{t('common:duration')}</th>
                  <th>{t('common:actions')}</th>
                </tr>
              </thead>
              <tbody>
                {jobs.length > 0 ? (
                  jobs.map((job) => (
                    <tr key={job.id}>
                      <td><code>{job.id.substring(0, 8)}...</code></td>
                      <td><code>{job.run_id.substring(0, 8)}...</code></td>
                      <td>
                        <span className="status-pill status-pill-draft">P{job.priority}</span>
                      </td>
                      <td>{job.browser}</td>
                      <td>{getJobStatusBadge(job.status)}</td>
                      <td>{job.assigned_worker_id ? <code>{job.assigned_worker_id.substring(0, 8)}</code> : '--'}</td>
                      <td>{t('testCount', { total: job.nodeids.length })}</td>
                      <td>
                        {job.duration_ms > 0 ? (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <Clock size={12} />
                            <span>{t('durationSeconds', { value: (job.duration_ms / 1000).toFixed(1) })}</span>
                          </div>
                        ) : (
                          '--'
                        )}
                      </td>
                      <td>
                        {job.status === 'QUEUED' || job.status === 'RUNNING' ? (
                          <button
                            className="btn btn-secondary btn-sm"
                            style={{ color: 'var(--accent-red)' }}
                            onClick={() => handleCancelJob(job.id)}
                          >
                            <XCircle size={13} />
                            <span>{t('common:cancel')}</span>
                          </button>
                        ) : (
                          <span className="text-secondary text-sm">--</span>
                        )}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={9} className="text-center text-secondary py-4">
                      {loadingJobs ? t('loadingJobs') : t('emptyJobs')}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Modal: Register Worker */}
      {showRegisterModal && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: '480px' }}>
            <div className="modal-header">
              <h3>{t('registerTitle')}</h3>
              <button className="btn-icon" onClick={() => setShowRegisterModal(false)}>
                &times;
              </button>
            </div>
            <form onSubmit={handleRegisterWorker}>
              <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div className="form-group">
                  <label>{t('fieldHostname')}</label>
                  <input
                    type="text"
                    className="form-control"
                    required
                    placeholder="worker-node-01.local"
                    value={newHostname}
                    onChange={(e) => setNewHostname(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>{t('fieldIpAddress')}</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="10.0.1.25"
                    value={newIpAddress}
                    onChange={(e) => setNewIpAddress(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>{t('fieldMaxConcurrency')}</label>
                  <input
                    type="number"
                    min="1"
                    max="64"
                    className="form-control"
                    value={newConcurrency}
                    onChange={(e) => setNewConcurrency(parseInt(e.target.value, 10))}
                  />
                </div>
              </div>
              <div className="modal-footer" style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowRegisterModal(false)}>
                  {t('common:cancel')}
                </button>
                <button type="submit" className="btn btn-primary" disabled={registering}>
                  {registering ? t('registering') : t('registerWorker')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
