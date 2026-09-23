import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { DashboardStats } from '../types';
import { FolderGit2, FileText, CheckSquare, PlayCircle, Plus } from 'lucide-react';
import { NavTab } from '../components/Navigation';

interface DashboardPageProps {
  onNavigate: (tab: NavTab) => void;
  onOpenCreateProject: () => void;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({ onNavigate, onOpenCreateProject }) => {
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

  return (
    <div>
      {/* Stat Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', marginBottom: '24px' }}>
        <div className="card">
          <div className="card-body" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Projects
              </div>
              <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--text-main)', marginTop: '4px' }}>
                {stats?.total_projects ?? 0}
              </div>
            </div>
            <div style={{ padding: '10px', background: '#eff6ff', borderRadius: '6px', color: '#2563eb' }}>
              <FolderGit2 size={20} />
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-body" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Requirements
              </div>
              <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--text-main)', marginTop: '4px' }}>
                {stats?.total_requirements ?? 0}
              </div>
            </div>
            <div style={{ padding: '10px', background: '#f0fdf4', borderRadius: '6px', color: '#16a34a' }}>
              <FileText size={20} />
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-body" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Test Cases
              </div>
              <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--text-main)', marginTop: '4px' }}>
                {stats?.total_test_cases ?? 0}
              </div>
            </div>
            <div style={{ padding: '10px', background: '#fef3c7', borderRadius: '6px', color: '#d97706' }}>
              <CheckSquare size={20} />
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-body" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Total Runs
              </div>
              <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--text-main)', marginTop: '4px' }}>
                {stats?.total_runs ?? 0}
              </div>
            </div>
            <div style={{ padding: '10px', background: '#f3e8ff', borderRadius: '6px', color: '#9333ea' }}>
              <PlayCircle size={20} />
            </div>
          </div>
        </div>
      </div>

      {/* Quick Actions & Recent Activities */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '20px' }}>
        <div className="card">
          <div className="card-header">
            <span className="card-title">Recent Projects</span>
            <button className="btn btn-primary btn-sm" onClick={onOpenCreateProject}>
              <Plus size={14} /> New Project
            </button>
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            {stats && stats.recent_projects.length > 0 ? (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Project Name</th>
                    <th>Framework</th>
                    <th>Created At</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.recent_projects.map((p) => (
                    <tr key={p.id} style={{ cursor: 'pointer' }} onClick={() => onNavigate('projects')}>
                      <td style={{ fontWeight: 600 }}>{p.name}</td>
                      <td>
                        <span className="badge badge-draft">{p.framework_type}</span>
                      </td>
                      <td style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
                        {new Date(p.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
                No projects created yet. Start by creating a project to bootstrap your QA workspace.
              </div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <span className="card-title">QA Lifecycle Navigation</span>
          </div>
          <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <button className="btn btn-secondary" style={{ justifyContent: 'flex-start' }} onClick={() => onNavigate('requirements')}>
              <FileText size={16} color="#2563eb" /> 1. Define Requirements
            </button>
            <button className="btn btn-secondary" style={{ justifyContent: 'flex-start' }} onClick={() => onNavigate('test_cases')}>
              <CheckSquare size={16} color="#16a34a" /> 2. Manage Test Cases
            </button>
            <button className="btn btn-secondary" style={{ justifyContent: 'flex-start' }} onClick={() => onNavigate('automation')}>
              <PlayCircle size={16} color="#9333ea" /> 3. Open Automation Studio
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
