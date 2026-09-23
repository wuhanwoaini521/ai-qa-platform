import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { DashboardStats } from '../types';
import {
  FolderGit2,
  FileText,
  CheckSquare,
  PlayCircle,
  Activity,
  AlertTriangle,
  ArrowRight,
  Flame,
  RotateCcw,
  Clock,
  Sparkles,
} from 'lucide-react';
import { NavTab } from '../components/Navigation';

interface DashboardPageProps {
  onNavigate: (tab: NavTab) => void;
  onOpenCreateProject?: () => void;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({
  onNavigate,
}) => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchStats = async () => {
    try {
      setLoading(true);
      const data = await api.getDashboardStats();
      setStats(data);
    } catch (err) {
      console.error('Failed to load dashboard stats', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
  }, []);

  if (loading && !stats) {
    return <div style={{ padding: '20px', color: '#64748b' }}>Loading platform overview...</div>;
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'PASSED':
        return <span className="status-pill status-pill-passed">PASSED</span>;
      case 'FAILED':
        return <span className="status-pill status-pill-failed">FAILED</span>;
      case 'RUNNING':
        return <span className="status-pill status-pill-draft">RUNNING</span>;
      default:
        return <span className="status-pill status-pill-draft">{status}</span>;
    }
  };

  return (
    <div>
      {/* Stat Cards Row 1: Core Quality & Intelligence KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', marginBottom: '16px' }}>
        <div className="card">
          <div className="card-body" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Pass Rate Today
              </div>
              <div style={{ fontSize: '26px', fontWeight: 700, color: '#16a34a', marginTop: '4px' }}>
                {stats?.pass_rate_today !== undefined ? `${stats.pass_rate_today.toFixed(1)}%` : '100%'}
              </div>
            </div>
            <div style={{ padding: '10px', background: '#f0fdf4', borderRadius: '6px', color: '#16a34a' }}>
              <Activity size={20} />
            </div>
          </div>
        </div>

        <div className="card" style={{ cursor: 'pointer' }} onClick={() => onNavigate('flaky')}>
          <div className="card-body" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Likely Flaky Tests
              </div>
              <div style={{ fontSize: '26px', fontWeight: 700, color: '#ea580c', marginTop: '4px' }}>
                {stats?.flaky_tests_count ?? 0}
              </div>
            </div>
            <div style={{ padding: '10px', background: '#fff7ed', borderRadius: '6px', color: '#ea580c' }}>
              <Flame size={20} />
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-body" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Rerun Recoveries
              </div>
              <div style={{ fontSize: '26px', fontWeight: 700, color: '#2563eb', marginTop: '4px' }}>
                {stats?.rerun_recovery_count ?? 0}
              </div>
            </div>
            <div style={{ padding: '10px', background: '#eff6ff', borderRadius: '6px', color: '#2563eb' }}>
              <RotateCcw size={20} />
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-body" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Avg Execution Time
              </div>
              <div style={{ fontSize: '26px', fontWeight: 700, color: 'var(--text-main)', marginTop: '4px' }}>
                {stats?.average_test_duration_ms
                  ? stats.average_test_duration_ms > 1000
                    ? `${(stats.average_test_duration_ms / 1000).toFixed(1)}s`
                    : `${stats.average_test_duration_ms}ms`
                  : '0.0s'}
              </div>
            </div>
            <div style={{ padding: '10px', background: '#f3e8ff', borderRadius: '6px', color: '#9333ea' }}>
              <Clock size={20} />
            </div>
          </div>
        </div>
      </div>

      {/* Stat Cards Row 2: Asset Scale */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', marginBottom: '20px' }}>
        <div className="card">
          <div className="card-body" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                QA Projects
              </div>
              <div style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-main)', marginTop: '4px' }}>
                {stats?.total_projects ?? 0}
              </div>
            </div>
            <FolderGit2 size={18} color="#64748b" />
          </div>
        </div>

        <div className="card">
          <div className="card-body" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Requirements
              </div>
              <div style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-main)', marginTop: '4px' }}>
                {stats?.total_requirements ?? 0}
              </div>
            </div>
            <FileText size={18} color="#64748b" />
          </div>
        </div>

        <div className="card">
          <div className="card-body" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Test Cases
              </div>
              <div style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-main)', marginTop: '4px' }}>
                {stats?.total_test_cases ?? 0}
              </div>
            </div>
            <CheckSquare size={18} color="#64748b" />
          </div>
        </div>

        <div className="card">
          <div className="card-body" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Total Executions
              </div>
              <div style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-main)', marginTop: '4px' }}>
                {stats?.total_runs ?? 0}
              </div>
            </div>
            <PlayCircle size={18} color="#64748b" />
          </div>
        </div>
      </div>

      {/* Main Grid: Recent Runs & QA Lifecycle Navigation */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1.2fr', gap: '20px' }}>
        {/* Recent Execution Runs */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Recent Execution Runs</span>
            <button className="btn btn-secondary btn-sm" onClick={() => onNavigate('runs')}>
              View All <ArrowRight size={13} />
            </button>
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            {stats && stats.recent_runs && stats.recent_runs.length > 0 ? (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Status</th>
                    <th>Run ID</th>
                    <th>Runner</th>
                    <th>Total</th>
                    <th>Duration</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.recent_runs.map((r) => (
                    <tr
                      key={r.id}
                      style={{ cursor: 'pointer' }}
                      onClick={() => onNavigate('runs')}
                    >
                      <td>{getStatusBadge(r.status)}</td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                        #{r.id.slice(0, 8)}
                      </td>
                      <td style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                        {r.runner_type || 'LOCAL'}
                      </td>
                      <td style={{ fontSize: '12px' }}>
                        <span style={{ color: '#16a34a', fontWeight: 600 }}>{r.passed}</span> /{' '}
                        <span style={{ color: '#dc2626', fontWeight: 600 }}>{r.failed}</span>
                      </td>
                      <td style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                        {(r.duration_ms / 1000).toFixed(2)}s
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
                No recent execution runs. Launch a test from Automation Studio or Test Cases to start tracking.
              </div>
            )}
          </div>
        </div>

        {/* QA Engineering Lifecycle Quick Access */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">QA Intelligence Architecture</span>
          </div>
          <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <button
              className="btn btn-secondary"
              style={{ justifyContent: 'space-between', padding: '10px 14px' }}
              onClick={() => onNavigate('requirements')}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <Sparkles size={16} color="#2563eb" />
                <div style={{ textAlign: 'left' }}>
                  <div style={{ fontSize: '13px', fontWeight: 600 }}>1. AI Requirement & Design</div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Risk analysis & test dimensional designs</div>
                </div>
              </div>
              <ArrowRight size={14} color="#94a3b8" />
            </button>

            <button
              className="btn btn-secondary"
              style={{ justifyContent: 'space-between', padding: '10px 14px' }}
              onClick={() => onNavigate('automation')}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <PlayCircle size={16} color="#9333ea" />
                <div style={{ textAlign: 'left' }}>
                  <div style={{ fontSize: '13px', fontWeight: 600 }}>2. Automation Studio V2</div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>AST validation, live runner & sidecar</div>
                </div>
              </div>
              <ArrowRight size={14} color="#94a3b8" />
            </button>

            <button
              className="btn btn-secondary"
              style={{ justifyContent: 'space-between', padding: '10px 14px' }}
              onClick={() => onNavigate('flaky')}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <Flame size={16} color="#ea580c" />
                <div style={{ textAlign: 'left' }}>
                  <div style={{ fontSize: '13px', fontWeight: 600 }}>3. Flaky Test Intelligence</div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Deterministic scoring & transition analysis</div>
                </div>
              </div>
              <ArrowRight size={14} color="#94a3b8" />
            </button>

            <button
              className="btn btn-secondary"
              style={{ justifyContent: 'space-between', padding: '10px 14px' }}
              onClick={() => onNavigate('failures')}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <AlertTriangle size={16} color="#dc2626" />
                <div style={{ textAlign: 'left' }}>
                  <div style={{ fontSize: '13px', fontWeight: 600 }}>4. Failure AI & Self-Healing</div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Root-cause diagnosis & semantic review</div>
                </div>
              </div>
              <ArrowRight size={14} color="#94a3b8" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
