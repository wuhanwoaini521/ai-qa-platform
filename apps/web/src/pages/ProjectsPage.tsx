import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Trans, useTranslation } from 'react-i18next';
import { Project, ProjectCreate, FrameworkType } from '../types';
import { Plus, FolderGit2, Code2, FileText, Search } from 'lucide-react';
import { NavTab } from '../components/Navigation';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import { buildProjectDisplayNames } from '../app/projectSelectionModel';
import { buildProjectManagementHref } from '../app/workspaceContext';
import './ProjectsPage.css';

interface ProjectsPageProps {
  projects: Project[];
  loading: boolean;
  error: string | null;
  selectedProjectId: string | null;
  onRefresh: () => void;
  onCreateProject: (data: ProjectCreate) => Promise<void>;
  onSelectProject: (id: string) => void;
  onNavigate: (tab: NavTab, projectId?: string | null) => void;
}

export const ProjectsPage: React.FC<ProjectsPageProps> = ({
  projects,
  loading,
  error,
  selectedProjectId,
  onCreateProject,
  onSelectProject,
  onRefresh,
  onNavigate,
}) => {
  const { t } = useTranslation('projects');
  const { t: lc } = useTranslation('lifecycle');
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [demoBusy,setDemoBusy]=useState(false);
  const [demoError,setDemoError]=useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(() => searchParams.get('create') === '1');
  const createProjectTriggerRef = useRef<HTMLButtonElement>(null);
  const createProjectDialogRef = useRef<HTMLDivElement>(null);
  const [formData, setFormData] = useState<ProjectCreate>({
    name: '',
    description: '',
    repository_url: '',
    default_branch: 'main',
    framework_type: 'playwright_python',
    bootstrap_workspace: true,
    sut_base_url: '',
    hidden_from_overview: false,
  });
  const [submitting, setSubmitting] = useState(false);
  const [createError, setCreateError] = useState('');
  const projectDisplayNames = buildProjectDisplayNames(projects);
  const currentProject = projects.find((project) => project.id === selectedProjectId) ?? null;
  const normalizedQuery = searchQuery.trim().toLocaleLowerCase();
  const visibleProjects = projects.filter((project) => !normalizedQuery || [project.name, project.description, project.repository_url, project.framework_type].some((value) => value?.toLocaleLowerCase().includes(normalizedQuery)));
  const closeProjectDialog = useCallback(() => {
    setIsModalOpen(false);
    setCreateError('');
    if (searchParams.get('create') === '1') navigate('/projects', { replace: true });
  }, [navigate, searchParams]);

  useEffect(() => {
    if (!isModalOpen) return;
    const dialog = createProjectDialogRef.current;
    const focusableSelector = 'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])';
    const focusable = () => Array.from(dialog?.querySelectorAll<HTMLElement>(focusableSelector) ?? []);
    focusable()[0]?.focus();
    const handleDialogKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        closeProjectDialog();
        return;
      }
      if (event.key !== 'Tab') return;
      const items = focusable();
      const first = items[0];
      const last = items.at(-1);
      if (!first || !last) {
        event.preventDefault();
        dialog?.focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener('keydown', handleDialogKeyDown);
    return () => {
      window.removeEventListener('keydown', handleDialogKeyDown);
      createProjectTriggerRef.current?.focus();
    };
  }, [isModalOpen, closeProjectDialog]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name.trim()) return;
    try {
      setSubmitting(true);
      setCreateError('');
      await onCreateProject(formData);
      closeProjectDialog();
      setFormData({
        name: '',
        description: '',
        repository_url: '',
        default_branch: 'main',
        framework_type: 'playwright_python',
        bootstrap_workspace: true,
        sut_base_url: '',
        hidden_from_overview: false,
      });
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : String(error));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="projects-page">
      <header className="projects-page-header">
        <div>
          <h2>{t('titles:projects')}</h2>
          <p>{t('subtitle')}</p>
        </div>
        <div className="projects-page-actions">
          <Link className="btn btn-secondary" to="/library">{t('assetIndex')}</Link>
          <button className="btn btn-ghost" disabled={demoBusy} onClick={async () => {
            setDemoBusy(true);
            setDemoError('');
            try {
              const result = await api.seedGoldenDemo();
              onSelectProject(result.project_id);
              onRefresh();
              navigate(`/projects/${result.project_id}`);
            } catch (error) {
              setDemoError(String(error));
            } finally {
              setDemoBusy(false);
            }
          }}>{demoBusy ? lc('loading') : lc('openGoldenDemo')}</button>
          <button ref={createProjectTriggerRef} className="btn btn-primary" onClick={() => { setCreateError(''); setIsModalOpen(true); }}>
            <Plus size={16} /> {t('createProject')}
          </button>
        </div>
      </header>
      {demoError && <p role="alert" className="lc-notice lc-error">{demoError}</p>}
      {error && projects.length > 0 && <div className="async-state async-state-warning projects-load-warning" role="status">
        <span>{t('projectLoadFailed')}</span><button type="button" className="btn btn-secondary btn-sm" disabled={loading} onClick={onRefresh}>{t('common:refresh')}</button>
      </div>}

      {!loading && currentProject && <section className="card project-current-workspace" aria-labelledby="current-project-workspace-title">
        <div className="project-current-copy">
          <span>{t('currentProject')}</span>
          <h3 id="current-project-workspace-title">{projectDisplayNames.get(currentProject.id) ?? currentProject.name}</h3>
          <p>{currentProject.repository_url || t('localWorkspace')} · {currentProject.framework_type} · {t('columnBranch')}: <code>{currentProject.default_branch}</code></p>
        </div>
        <div className="project-current-actions">
          <Link className="btn btn-secondary" to={buildProjectManagementHref(currentProject.id)} onClick={() => onSelectProject(currentProject.id)}><FileText size={14} aria-hidden="true" />{t('viewRequirements')}</Link>
          <button type="button" className="btn btn-primary" onClick={() => { onSelectProject(currentProject.id); onNavigate('workspace', currentProject.id); }}><Code2 size={14} aria-hidden="true" />{t('openWorkspace')}</button>
        </div>
      </section>}

      <section className="card project-registry" aria-label={t('titles:projects')}>
        <div className="project-registry-heading">
          <strong>{t('projectCount', { count: projects.length })}</strong>
          {projects.length > 1 && <label className="project-search">
            <Search size={14} aria-hidden="true" />
            <span className="project-search-visually-hidden">{t('searchProjects')}</span>
            <input type="search" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder={t('searchProjects')} />
          </label>}
          <span>{t('registryHint')}</span>
        </div>
        <div className="card-body project-registry-body">
          {loading ? (
            <div className="projects-loading">{t('common:loadingProjects')}</div>
          ) : error && projects.length === 0 ? (
            <div className="projects-empty-state" role="alert">
              <FolderGit2 size={32} aria-hidden="true" />
              <strong>{t('projectLoadFailed')}</strong>
              <button type="button" className="btn btn-secondary" onClick={onRefresh}>{t('common:refresh')}</button>
            </div>
          ) : projects.length === 0 ? (
            <div className="projects-empty-state">
              <FolderGit2 size={36} aria-hidden="true" />
              <div className="projects-empty-title">
                {t('emptyTitle')}
              </div>
              <p className="projects-empty-copy">
                {t('emptyDescription')}
              </p>
              <button ref={createProjectTriggerRef} className="btn btn-primary" onClick={() => { setCreateError(''); setIsModalOpen(true); }}>
                <Plus size={16} /> {t('createProject')}
              </button>
            </div>
          ) : visibleProjects.length === 0 ? (
            <div className="projects-empty-state" role="status">
              <Search size={28} aria-hidden="true" />
              <strong>{t('noProjectsMatch')}</strong>
              <button type="button" className="btn btn-secondary" onClick={() => setSearchQuery('')}>{t('clearSearch')}</button>
            </div>
          ) : (
            <div
              className="table-responsive"
              role="region"
              aria-label={t('titles:projects')}
              aria-description={t('tableScrollHint')}
              tabIndex={0}
              onKeyDown={(event) => {
                if (event.target !== event.currentTarget) return;
                const maxScroll = event.currentTarget.scrollWidth - event.currentTarget.clientWidth;
                if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
                  event.preventDefault();
                  event.currentTarget.scrollLeft = Math.max(0, Math.min(maxScroll, event.currentTarget.scrollLeft + (event.key === 'ArrowRight' ? 80 : -80)));
                } else if (event.key === 'Home' || event.key === 'End') {
                  event.preventDefault();
                  event.currentTarget.scrollLeft = event.key === 'Home' ? 0 : maxScroll;
                }
              }}
            >
              <p className="projects-table-scroll-hint">{t('tableSwipeHint')}</p>
              <table className="data-table project-registry-table">
                <thead>
                  <tr>
                    <th>{t('columnName')}</th>
                    <th>{t('columnFramework')}</th>
                    <th>{t('columnWorkspace')}</th>
                    <th>{t('common:created')}</th>
                    <th className="project-actions-heading">{t('common:actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleProjects.map((p) => (
                    <tr key={p.id} className={p.id === selectedProjectId ? 'is-current-project' : undefined}>
                      <td className="project-name-cell">
                        <Link to={`/projects/${p.id}`} className="project-name" onClick={() => onSelectProject(p.id)}>
                          {projectDisplayNames.get(p.id) ?? p.name}
                        </Link>
                        {p.description && <div className="project-description">{p.description}</div>}
                        {p.sut_base_url && <div className="project-description"><code>{p.sut_base_url}</code></div>}
                        {p.hidden_from_overview && <span className="badge badge-draft">{t('hiddenFromOverview')}</span>}
                      </td>
                      <td><span className="badge badge-draft">{p.framework_type}</span></td>
                      <td>
                        <div className="project-workspace-cell">
                          <span className="project-repository" title={p.repository_url || t('localWorkspace')}>
                            {p.repository_url || t('localWorkspace')}
                          </span>
                          <span className="project-branch">{t('columnBranch')}: <code>{p.default_branch}</code></span>
                        </div>
                      </td>
                      <td className="project-created-date">{new Date(p.created_at).toLocaleDateString()}</td>
                      <td className="project-actions-cell">
                        <div className="project-row-actions">
                          <Link
                            className="btn btn-secondary btn-sm"
                            title={t('viewRequirements')}
                            aria-label={t('viewRequirements')}
                            to={buildProjectManagementHref(p.id)}
                            onClick={() => onSelectProject(p.id)}
                          >
                            <FileText size={13} aria-hidden="true" />
                          </Link>
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm"
                            title={p.hidden_from_overview ? t('showFromOverview') : t('hideFromOverview')}
                            onClick={async () => {
                              await api.updateProject(p.id, { hidden_from_overview: !p.hidden_from_overview });
                              onRefresh();
                            }}
                          >
                            {p.hidden_from_overview ? t('showFromOverview') : t('hideFromOverview')}
                          </button>
                          <button
                            type="button"
                            className="btn btn-primary btn-sm"
                            title={t('openWorkspace')}
                            onClick={() => {
                              onSelectProject(p.id);
                              onNavigate('workspace', p.id);
                            }}
                          >
                            <Code2 size={13} aria-hidden="true" /> {t('openWorkspace')}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {/* Create Project Modal */}
      {isModalOpen && (
        <div className="modal-overlay">
          <div ref={createProjectDialogRef} className="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="create-project-title" tabIndex={-1}>
            <form onSubmit={handleSubmit}>
              <div className="modal-header">
                <h3 id="create-project-title" style={{ fontSize: '15px', fontWeight: 700 }}>{t('modalTitle')}</h3>
                <button
                  type="button"
                  aria-label={t('common:close')}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '16px' }}
                  onClick={closeProjectDialog}
                >
                  ✕
                </button>
              </div>
              <div className="modal-body" style={{ padding: '20px' }}>
                {createError && <div className="async-state async-state-error project-create-error" role="alert">{t('createFailed', { message: createError })}</div>}
                <div className="form-group">
                  <label className="form-label" htmlFor="project-name">{t('modalNameLabel')}</label>
                  <input
                    id="project-name"
                    type="text"
                    required
                    className="form-control"
                    placeholder={t('modalNamePlaceholder')}
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="project-description">{t('common:description')}</label>
                  <textarea
                    id="project-description"
                    rows={2}
                    className="form-control"
                    placeholder={t('modalDescriptionPlaceholder')}
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="project-repository-url">{t('modalRepositoryUrlLabel')}</label>
                  <input
                    id="project-repository-url"
                    type="url"
                    className="form-control"
                    placeholder={t('modalRepositoryUrlPlaceholder')}
                    value={formData.repository_url || ''}
                    onChange={(e) => setFormData({ ...formData, repository_url: e.target.value || null })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="project-sut-url">{t('modalSutUrlLabel')}</label>
                  <input
                    id="project-sut-url"
                    type="url"
                    className="form-control"
                    placeholder={t('modalSutUrlPlaceholder')}
                    value={formData.sut_base_url || ''}
                    onChange={(e) => setFormData({ ...formData, sut_base_url: e.target.value || null })}
                  />
                </div>

                <div className="form-group">
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px' }}>
                    <input
                      type="checkbox"
                      checked={Boolean(formData.hidden_from_overview)}
                      onChange={(e) => setFormData({ ...formData, hidden_from_overview: e.target.checked })}
                    />
                    <span>{t('modalHideFromOverview')}</span>
                  </label>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div className="form-group">
                    <label className="form-label" htmlFor="project-framework-type">{t('modalFrameworkTypeLabel')}</label>
                    <select
                      id="project-framework-type"
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
                    <label className="form-label" htmlFor="project-default-branch">{t('modalDefaultBranchLabel')}</label>
                    <input
                      id="project-default-branch"
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
                  onClick={closeProjectDialog}
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
