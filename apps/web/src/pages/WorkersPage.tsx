import React, { useEffect, useState } from 'react';
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
          <h2>Distributed Execution Cluster</h2>
          <p className="subtitle">
            Autonomous multi-node workers, containerized execution engines, priority job queues, and artifact stores.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn btn-primary" onClick={() => setShowRegisterModal(true)}>
            <Plus size={14} />
            <span>Register Worker</span>
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => {
              fetchClusterAndWorkers();
              if (activeTab === 'jobs') fetchJobs();
            }}
          >
            <RefreshCw size={14} className={loadingCluster || loadingJobs ? 'spinning' : ''} />
            <span>Refresh</span>
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
            <div className="stat-title">Cluster Workers</div>
            <div className="stat-value">
              {clusterSummary ? clusterSummary.total_workers : '--'}
            </div>
            <div className="stat-subtitle">
              {clusterSummary ? `${clusterSummary.online_workers} online / ${clusterSummary.busy_workers} busy` : '0 workers'}
            </div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon" style={{ backgroundColor: 'rgba(16, 185, 129, 0.1)', color: '#10b981' }}>
            <Cpu size={20} />
          </div>
          <div className="stat-details">
            <div className="stat-title">Concurrency Capacity</div>
            <div className="stat-value">
              {clusterSummary ? `${clusterSummary.used_concurrency} / ${clusterSummary.total_concurrency_capacity}` : '--'}
            </div>
            <div className="stat-subtitle">
              {clusterSummary && clusterSummary.total_concurrency_capacity > 0
                ? `${Math.round((clusterSummary.used_concurrency / clusterSummary.total_concurrency_capacity) * 100)}% load`
                : '0% load'}
            </div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon" style={{ backgroundColor: 'rgba(245, 158, 11, 0.1)', color: '#f59e0b' }}>
            <Layers size={20} />
          </div>
          <div className="stat-details">
            <div className="stat-title">Queued Tasks</div>
            <div className="stat-value">
              {clusterSummary ? clusterSummary.queued_jobs_count : '--'}
            </div>
            <div className="stat-subtitle">Waiting for worker dispatch</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon" style={{ backgroundColor: 'rgba(139, 92, 246, 0.1)', color: '#8b5cf6' }}>
            <Activity size={20} />
          </div>
          <div className="stat-details">
            <div className="stat-title">Active Running Tasks</div>
            <div className="stat-value">
              {clusterSummary ? clusterSummary.running_jobs_count : '--'}
            </div>
            <div className="stat-subtitle">Currently executing</div>
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
          Cluster Workers ({workers.length})
        </button>
        <button
          className={`tab-btn ${activeTab === 'jobs' ? 'active' : ''}`}
          onClick={() => setActiveTab('jobs')}
        >
          <Layers size={15} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
          Distributed Job Queue ({jobs.length})
        </button>
      </div>

      {/* Tab 1: Workers Grid & Table */}
      {activeTab === 'workers' && (
        <div className="card">
          <div className="card-header">
            <h3>Registered Runner Nodes</h3>
            <span className="text-secondary text-sm">
              Live heartbeat protocol monitors worker health and automatically quarantines lost runners.
            </span>
          </div>
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Hostname</th>
                  <th>IP Address</th>
                  <th>Status</th>
                  <th>Concurrency Load</th>
                  <th>Supported Browsers</th>
                  <th>OS</th>
                  <th>Last Heartbeat</th>
                  <th>Actions</th>
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
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <div
                            style={{
                              width: '60px',
                              height: '6px',
                              backgroundColor: 'var(--border-color)',
                              borderRadius: '3px',
                              overflow: 'hidden',
                            }}
                          >
                            <div
                              style={{
                                width: `${w.max_concurrency > 0 ? (w.current_load / w.max_concurrency) * 100 : 0}%`,
                                height: '100%',
                                backgroundColor: 'var(--accent-primary)',
                              }}
                            />
                          </div>
                          <span style={{ fontSize: '0.85rem' }}>{w.current_load}/{w.max_concurrency}</span>
                        </div>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '4px' }}>
                          {w.browsers.map((b) => (
                            <span key={b} className="status-pill status-pill-draft" style={{ fontSize: '0.75rem', padding: '2px 6px' }}>
                              {b}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td style={{ textTransform: 'capitalize' }}>{w.os}</td>
                      <td style={{ fontSize: '0.85rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <Radio size={12} color="#10b981" />
                          <span>{new Date(w.last_heartbeat_at).toLocaleTimeString()}</span>
                        </div>
                      </td>
                      <td>
                        <button
                          className="btn btn-secondary btn-sm"
                          style={{ color: '#ef4444' }}
                          onClick={() => handleDeleteWorker(w.id)}
                        >
                          <Trash2 size={13} />
                          <span>Deregister</span>
                        </button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={8} className="text-center text-secondary py-4">
                      {loadingCluster ? 'Loading worker nodes...' : 'No workers registered yet. Click "Register Worker" to add a node.'}
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
            <h3>Distributed Execution Tasks</h3>
            <span className="text-secondary text-sm">
              Priority-based distributed task queue dispatching tests across available worker capacity.
            </span>
          </div>
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Job ID</th>
                  <th>Run ID</th>
                  <th>Priority</th>
                  <th>Browser</th>
                  <th>Status</th>
                  <th>Assigned Worker</th>
                  <th>Test Count</th>
                  <th>Duration</th>
                  <th>Actions</th>
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
                      <td>{job.nodeids.length} tests</td>
                      <td>
                        {job.duration_ms > 0 ? (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <Clock size={12} />
                            <span>{(job.duration_ms / 1000).toFixed(1)}s</span>
                          </div>
                        ) : (
                          '--'
                        )}
                      </td>
                      <td>
                        {job.status === 'QUEUED' || job.status === 'RUNNING' ? (
                          <button
                            className="btn btn-secondary btn-sm"
                            style={{ color: '#ef4444' }}
                            onClick={() => handleCancelJob(job.id)}
                          >
                            <XCircle size={13} />
                            <span>Cancel</span>
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
                      {loadingJobs ? 'Loading jobs...' : 'No jobs queued or executing.'}
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
              <h3>Register Worker Node</h3>
              <button className="btn-icon" onClick={() => setShowRegisterModal(false)}>
                &times;
              </button>
            </div>
            <form onSubmit={handleRegisterWorker}>
              <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div className="form-group">
                  <label>Node Hostname *</label>
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
                  <label>IP Address</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="10.0.1.25"
                    value={newIpAddress}
                    onChange={(e) => setNewIpAddress(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>Max Concurrency Capacity</label>
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
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={registering}>
                  {registering ? 'Registering...' : 'Register Worker'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
