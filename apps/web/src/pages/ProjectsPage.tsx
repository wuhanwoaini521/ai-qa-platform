import React, { useState } from 'react';
import { Trans, useTranslation } from 'react-i18next';
import { Project, ProjectCreate, FrameworkType } from '../types';
import { Plus, FolderGit2, Code2, FileText } from 'lucide-react';
import { NavTab } from '../components/Navigation';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api/client';

interface ProjectsPageProps {
  projects: Project[];
  loading: boolean;
  onRefresh: () => void;
  onCreateProject: (data: ProjectCreate) => Promise<void>;
  onSelectProject: (id: string) => void;
  onNavigate: (tab: NavTab, projectId?: string | null) => void;
}

export const ProjectsPage: React.FC<ProjectsPageProps> = ({
  projects,
  loading,
  onCreateProject,
  onSelectProject,
  onRefresh,
  onNavigate,
}) => {
  const { t } = useTranslation('projects');
  const { t: lc } = useTranslation('lifecycle');
  const navigate = useNavigate();
  const [demoBusy,setDemoBusy]=useState(false);
  const [demoError,setDemoError]=useState('');
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
          <h2 style={{ fontSize: '18px', fontWeight: 700 }}>{t('titles:projects')}</h2>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>{t('subtitle')}</p>
        </div>
        <div style={{display:'flex',gap:8,flexWrap:'wrap'}}><button className="btn btn-secondary" disabled={demoBusy} onClick={async()=>{setDemoBusy(true);setDemoError('');try{const result=await api.seedGoldenDemo();onSelectProject(result.project_id);onRefresh();navigate(`/projects/${result.project_id}`);}catch(error){setDemoError(String(error));}finally{setDemoBusy(false);}}}>{demoBusy?lc('loading'):lc('openGoldenDemo')}</button><button className="btn btn-primary" onClick={() => setIsModalOpen(true)}>
          <Plus size={16} /> {t('createProject')}
        </button></div>
      </div>
      {demoError&&<p role="alert" className="lc-notice lc-error">{demoError}</p>}

      <div className="card">
        <div className="card-body" style={{ padding: 0 }}>
          {loading ? (
            <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
              {t('common:loadingProjects')}
            </div>
          ) : projects.length === 0 ? (
            <div style={{ padding: '48px', textAlign: 'center', color: 'var(--text-muted)' }}>
              <FolderGit2 size={36} style={{ margin: '0 auto 12px', opacity: 0.4 }} />
              <div style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '4px' }}>
                {t('emptyTitle')}
              </div>
              <p style={{ fontSize: '13px', maxWidth: '400px', margin: '0 auto 16px' }}>
                {t('emptyDescription')}
              </p>
              <button className="btn btn-primary" onClick={() => setIsModalOpen(true)}>
                <Plus size={16} /> {t('createProject')}
              </button>
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t('columnName')}</th>
                  <th>{t('columnFramework')}</th>
                  <th>{t('columnRepositoryUrl')}</th>
                  <th>{t('columnBranch')}</th>
                  <th>{t('common:created')}</th>
                  <th style={{ textAlign: 'right' }}>{t('common:actions')}</th>
                </tr>
              </thead>
              <tbody>
                {projects.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <Link to={`/projects/${p.id}`} onClick={()=>onSelectProject(p.id)} style={{ fontWeight: 600, color: 'var(--text-main)' }}>{p.name}</Link>
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
                      {p.repository_url || <span style={{ color: 'var(--text-muted)' }}>{t('localWorkspace')}</span>}
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}>{p.default_branch}</td>
                    <td style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
                      {new Date(p.created_at).toLocaleDateString()}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: '6px' }}>
                        <button
                          className="btn btn-secondary btn-sm"
                          title={t('viewRequirements')}
                          onClick={() => {
                            onSelectProject(p.id);
                            onNavigate('requirements', p.id);
                          }}
                        >
                          <FileText size={13} />
                        </button>
                        <button
                          className="btn btn-primary btn-sm"
                          title={t('openInAutomationStudio')}
                          onClick={() => {
                            onSelectProject(p.id);
                            onNavigate('automation', p.id);
                          }}
                        >
                          <Code2 size={13} /> {t('studio')}
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
                <h3 style={{ fontSize: '15px', fontWeight: 700 }}>{t('modalTitle')}</h3>
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
                  <label className="form-label">{t('modalNameLabel')}</label>
                  <input
                    type="text"
                    required
                    className="form-control"
                    placeholder={t('modalNamePlaceholder')}
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">{t('common:description')}</label>
                  <textarea
                    rows={2}
                    className="form-control"
                    placeholder={t('modalDescriptionPlaceholder')}
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">{t('modalRepositoryUrlLabel')}</label>
                  <input
                    type="url"
                    className="form-control"
                    placeholder={t('modalRepositoryUrlPlaceholder')}
                    value={formData.repository_url || ''}
                    onChange={(e) => setFormData({ ...formData, repository_url: e.target.value || null })}
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div className="form-group">
                    <label className="form-label">{t('modalFrameworkTypeLabel')}</label>
                    <select
                      className="form-control"
                      value={formData.framework_type}
                      onChange={(e) =>
                        setFormData({ ...formData, framework_type: e.target.value as FrameworkType })
                      }
                    >
                      <option value="playwright_python">{t('frameworkPlaywrightPython')}</option>
                      <option value="pytest_api">{t('frameworkPytestApi')}</option>
                      <option value="custom">{t('frameworkCustom')}</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label">{t('modalDefaultBranchLabel')}</label>
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
                      <Trans
                        ns="projects"
                        i18nKey="modalBootstrapHint"
                        components={{ strong: <strong />, code: <code /> }}
                      />
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
                  {t('common:cancel')}
                </button>
                <button type="submit" className="btn btn-primary" disabled={submitting}>
                  {submitting ? t('creating') : t('createProject')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
