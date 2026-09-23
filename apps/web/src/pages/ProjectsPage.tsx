import React, { useState } from 'react';
import { Project, ProjectCreate, FrameworkType } from '../types';
import { Plus, FolderGit2, Code2, FileText } from 'lucide-react';
import { NavTab } from '../components/Navigation';

interface ProjectsPageProps {
  projects: Project[];
  loading: boolean;
  onRefresh: () => void;
  onCreateProject: (data: ProjectCreate) => Promise<void>;
  onSelectProject: (id: string) => void;
  onNavigate: (tab: NavTab) => void;
}

export const ProjectsPage: React.FC<ProjectsPageProps> = ({
  projects,
  loading,
  onCreateProject,
  onSelectProject,
  onNavigate,
}) => {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [formData, setFormData] = useState<ProjectCreate>({
    name: '',
    description: '',
    repository_url: '',
    default_branch: 'main',
    framework_type: 'playwright_python',
    bootstrap_workspace: true,
  });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name.trim()) return;
    try {
      setSubmitting(true);
      await onCreateProject(formData);
      setIsModalOpen(false);
      setFormData({
        name: '',
        description: '',
        repository_url: '',
        default_branch: 'main',
        framework_type: 'playwright_python',
        bootstrap_workspace: true,
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
        <div>
          <h2 style={{ fontSize: '18px', fontWeight: 700 }}>QA Projects</h2>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            Manage test projects, workspace repositories, and automation frameworks.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setIsModalOpen(true)}>
          <Plus size={16} /> Create Project
        </button>
      </div>

      <div className="card">
        <div className="card-body" style={{ padding: 0 }}>
          {loading ? (
            <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
              Loading projects...
            </div>
          ) : projects.length === 0 ? (
            <div style={{ padding: '48px', textAlign: 'center', color: 'var(--text-muted)' }}>
              <FolderGit2 size={36} style={{ margin: '0 auto 12px', opacity: 0.4 }} />
              <div style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '4px' }}>
                No projects found
              </div>
              <p style={{ fontSize: '13px', maxWidth: '400px', margin: '0 auto 16px' }}>
                Create your first project to configure a Playwright or Pytest test suite with an automated workspace.
              </p>
              <button className="btn btn-primary" onClick={() => setIsModalOpen(true)}>
                <Plus size={16} /> Create Project
              </button>
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Project Name</th>
                  <th>Framework</th>
                  <th>Repository URL</th>
                  <th>Branch</th>
                  <th>Created</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {projects.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <div style={{ fontWeight: 600, color: 'var(--text-main)' }}>{p.name}</div>
                      {p.description && (
                        <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                          {p.description}
                        </div>
                      )}
                    </td>
                    <td>
                      <span className="badge badge-draft">{p.framework_type}</span>
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                      {p.repository_url || <span style={{ color: 'var(--text-muted)' }}>Local Workspace</span>}
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}>{p.default_branch}</td>
                    <td style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
                      {new Date(p.created_at).toLocaleDateString()}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: '6px' }}>
                        <button
                          className="btn btn-secondary btn-sm"
                          title="View Requirements"
                          onClick={() => {
                            onSelectProject(p.id);
                            onNavigate('requirements');
                          }}
                        >
                          <FileText size={13} />
                        </button>
                        <button
                          className="btn btn-primary btn-sm"
                          title="Open in Automation Studio"
                          onClick={() => {
                            onSelectProject(p.id);
                            onNavigate('automation');
                          }}
                        >
                          <Code2 size={13} /> Studio
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Create Project Modal */}
      {isModalOpen && (
        <div className="modal-overlay">
          <div className="modal-dialog">
            <form onSubmit={handleSubmit}>
              <div className="modal-header">
                <h3 style={{ fontSize: '15px', fontWeight: 700 }}>Create New QA Project</h3>
                <button
                  type="button"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '16px' }}
                  onClick={() => setIsModalOpen(false)}
                >
                  ✕
                </button>
              </div>
              <div className="modal-body" style={{ padding: '20px' }}>
                <div className="form-group">
                  <label className="form-label">Project Name *</label>
                  <input
                    type="text"
                    required
                    className="form-control"
                    placeholder="e.g. Web E-Commerce Regression"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Description</label>
                  <textarea
                    rows={2}
                    className="form-control"
                    placeholder="Describe the test scope and applications under test..."
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Repository URL (Optional)</label>
                  <input
                    type="url"
                    className="form-control"
                    placeholder="https://github.com/org/repo (leave blank for local project)"
                    value={formData.repository_url || ''}
                    onChange={(e) => setFormData({ ...formData, repository_url: e.target.value || null })}
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div className="form-group">
                    <label className="form-label">Framework Type</label>
                    <select
                      className="form-control"
                      value={formData.framework_type}
                      onChange={(e) =>
                        setFormData({ ...formData, framework_type: e.target.value as FrameworkType })
                      }
                    >
                      <option value="playwright_python">Playwright (Python)</option>
                      <option value="pytest_api">Pytest (API Suite)</option>
                      <option value="custom">Custom Framework</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Default Branch</label>
                    <input
                      type="text"
                      className="form-control"
                      value={formData.default_branch}
                      onChange={(e) => setFormData({ ...formData, default_branch: e.target.value })}
                    />
                  </div>
                </div>

                <div className="form-group" style={{ marginTop: '8px' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px' }}>
                    <input
                      type="checkbox"
                      checked={formData.bootstrap_workspace}
                      onChange={(e) =>
                        setFormData({ ...formData, bootstrap_workspace: e.target.checked })
                      }
                    />
                    <span>
                      <strong>Bootstrap Blank QA Project</strong> (Creates <code>tests/</code>, <code>pages/</code>, <code>flows/</code>, <code>components/</code> workspace structure)
                    </span>
                  </label>
                </div>
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsModalOpen(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={submitting}>
                  {submitting ? 'Creating...' : 'Create Project'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
