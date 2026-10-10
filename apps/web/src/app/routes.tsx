import React, { lazy } from 'react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from 'react-router-dom';
import { DashboardPage } from '../pages/DashboardPage';
import { ProjectsPage } from '../pages/ProjectsPage';
import { AppLayout } from './AppLayout';
import { useProjectScope, useRouteProjectScope } from './ProjectScope';
import { useAppNavigation } from './navigation';
import { EmptyState } from '../components/AsyncState';
import { buildWorkflowHref, buildWorkspaceHref, readWorkspaceContext } from './workspaceContext';
import { api } from '../api/client';

const RunsPage = lazy(() =>
  import('../pages/RunsPage').then((m) => ({ default: m.RunsPage })),
);
const FlakyPage = lazy(() =>
  import('../pages/FlakyPage').then((m) => ({ default: m.FlakyPage })),
);
const QualityPage = lazy(() =>
  import('../pages/QualityPage').then((m) => ({ default: m.QualityPage })),
);
const SecurityPage = lazy(() =>
  import('../pages/SecurityPage').then((m) => ({ default: m.SecurityPage })),
);
const WorkersPage = lazy(() =>
  import('../pages/WorkersPage').then((m) => ({ default: m.WorkersPage })),
);
const SettingsPage = lazy(() =>
  import('../pages/SettingsPage').then((m) => ({ default: m.SettingsPage })),
);
const ProjectOverviewPage = lazy(() =>
  import('../features/lifecycle/ProjectOverviewPage').then((m) => ({
    default: m.ProjectOverviewPage,
  })),
);
const WorkspacePage = lazy(() =>
  import('../features/workspace/WorkspacePage').then((m) => ({
    default: m.WorkspacePage,
  })),
);
const WorkflowPage = lazy(() =>
  import('../features/workflow/WorkflowPage').then((m) => ({
    default: m.WorkflowPage,
  })),
);
const LibraryPage = lazy(() =>
  import('../pages/LibraryPage').then((m) => ({
    default: m.LibraryPage,
  })),
);

const DashboardRoute: React.FC = () => {
  const nav = useAppNavigation();
  const navigate = useNavigate();
  return (
    <DashboardPage
      onNavigate={nav.toTab}
      onOpenTask={(id) => navigate(`/tasks?taskId=${encodeURIComponent(id)}`)}
      onOpenRun={nav.toRun}
      onOpenCreateProject={() => nav.toTab('projects')}
    />
  );
};

const ProjectsRoute: React.FC = () => {
  const { projectId } = useParams();
  const nav = useAppNavigation();
  const { projects, loading, refresh, createProject, selectProject } =
    useProjectScope();
  useRouteProjectScope(projectId);

  return (
    <ProjectsPage
      projects={projects}
      loading={loading}
      onRefresh={refresh}
      onCreateProject={async (data) => {
        await createProject(data);
      }}
      onSelectProject={selectProject}
      onNavigate={nav.toTab}
    />
  );
};

const WorkspaceObjectRoute: React.FC<{ view: 'requirement' | 'cases' }> = ({ view }) => {
  const { projectId: routeProjectId, requirementId, testCaseId } = useParams();
  const { search } = useLocation();
  const { loading, selectedProjectId } = useProjectScope();
  const query = new URLSearchParams(search);
  const projectId = routeProjectId ?? query.get('projectId') ?? selectedProjectId;

  if (!projectId && loading) return <div className="page-loading" aria-busy="true">Loading workspace…</div>;
  if (!projectId) return <Navigate replace to="/projects" />;

  const context = readWorkspaceContext(query, projectId);
  return <Navigate replace to={buildWorkspaceHref({
    ...context,
    projectId,
    requirementId: requirementId ?? context.requirementId,
    testCaseId: testCaseId ?? context.testCaseId,
    stage: view,
    view,
  })} />;
};

const RequirementsRoute: React.FC = () => <WorkspaceObjectRoute view="requirement" />;
const TestCasesRoute: React.FC = () => <WorkspaceObjectRoute view="cases" />;

const StudioRoute: React.FC = () => {
  const { projectId, '*': filePath } = useParams();
  const location = useLocation();
  if (!projectId) return <Navigate replace to="/projects" />;
  const query = new URLSearchParams(location.search);
  const recorderMode = query.get('mode') === 'recorder';
  query.delete('mode');
  query.set('view', recorderMode ? 'browser' : query.has('failureId') ? 'debug' : 'code');
  if (filePath) query.set('file', filePath);
  return <Navigate replace to={`/workspace/${encodeURIComponent(projectId)}?${query.toString()}`} />;
};

const RunsRoute: React.FC = () => {
  const { runId } = useParams();
  const nav = useAppNavigation();
  const { projects, selectedProjectId } = useProjectScope();

  return (
    <RunsPage
      projects={projects}
      selectedProjectId={selectedProjectId}
      initialRunId={runId ?? null}
      onNavigateToFailures={nav.toFailures}
    />
  );
};

const LegacyTasksRoute: React.FC = () => {
  const { search, hash } = useLocation();
  return <Navigate replace to={`/workflow${search}${hash}`} />;
};

const WorkflowRoute: React.FC = () => {
  const { search } = useLocation();
  const { selectedProjectId } = useProjectScope();
  const context = readWorkspaceContext(search, selectedProjectId);
  if (context.projectId && (context.taskId || context.runId)) {
    return <Navigate replace to={buildWorkflowHref(context)} />;
  }
  return <WorkflowPage />;
};

const RecorderRoute: React.FC = () => {
  const { selectedProjectId } = useProjectScope();
  const location = useLocation();
  // Keep existing task origins and bookmarks as a compatibility redirect.
  if (!selectedProjectId) return <Navigate replace to="/projects" />;
  const query = new URLSearchParams(location.search);
  query.set('view', 'browser');
  return <Navigate replace to={`/workspace/${encodeURIComponent(selectedProjectId)}?${query.toString()}`} />;
};

const FailuresRoute: React.FC = () => {
  const { failureId } = useParams();
  const { search } = useLocation();
  const { selectedProjectId } = useProjectScope();
  const query = new URLSearchParams(search);
  query.set('view', 'results');
  query.set('stage', 'failure');
  if (failureId) query.set('failureId', failureId);
  return <Navigate replace to={`${selectedProjectId ? `/workspace/${encodeURIComponent(selectedProjectId)}` : '/workspace'}?${query.toString()}`} />;
};

const RunWorkspaceRoute: React.FC = () => {
  const { runId = '' } = useParams();
  const [projectId, setProjectId] = useState('');
  const [missing, setMissing] = useState(false);
  useEffect(() => {
    let active = true;
    setProjectId('');
    setMissing(false);
    void api.getTestRun(runId).then((run) => {
      if (active) setProjectId(run.project_id);
    }).catch(() => { if (active) setMissing(true); });
    return () => { active = false; };
  }, [runId]);
  if (projectId) return <Navigate replace to={buildWorkspaceHref({ projectId, runId, stage: 'result', view: 'results' })} />;
  if (missing) return <Navigate replace to="/runs" />;
  return <div className="page-loading" aria-busy="true">Loading run…</div>;
};

const FlakyRoute: React.FC = () => {
  const nav = useAppNavigation();
  const { projects, selectedProjectId } = useProjectScope();

  return (
    <FlakyPage
      projects={projects}
      selectedProjectId={selectedProjectId}
      onNavigateToRuns={nav.toRun}
    />
  );
};

const QualityRoute: React.FC = () => {
  const nav = useAppNavigation();
  const { projects, selectedProjectId } = useProjectScope();

  return (
    <QualityPage
      projects={projects}
      selectedProjectId={selectedProjectId}
      onNavigateToRuns={nav.toRun}
    />
  );
};

const NotFoundRoute: React.FC = () => {
  const nav = useAppNavigation();
  const { t } = useTranslation('errors');
  return (
    <EmptyState
      message={t('notFound')}
      actionLabel={t('backToDashboard')}
      onAction={() => nav.toTab('dashboard')}
    />
  );
};

interface AppRoutesProps {
  onSignOut: () => void;
}

/** Canonical route table. Legacy tab aliases redirect so old in-app links keep working. */
export const AppRoutes: React.FC<AppRoutesProps> = ({ onSignOut }) => (
  <Routes>
    <Route element={<AppLayout onSignOut={onSignOut} />}>
      <Route path="/" element={<DashboardRoute />} />
      <Route path="/workspace" element={<WorkspacePage />} />
      <Route path="/workspace/:projectId" element={<WorkspacePage />} />
      <Route path="/workflow" element={<WorkflowRoute />} />
      <Route path="/library" element={<LibraryPage />} />
      <Route path="/projects" element={<ProjectsRoute />} />
      <Route path="/projects/:projectId" element={<ProjectOverviewPage />} />
      <Route
        path="/projects/:projectId/requirements"
        element={<RequirementsRoute />}
      />
      <Route
        path="/projects/:projectId/requirements/:requirementId"
        element={<RequirementsRoute />}
      />
      <Route
        path="/projects/:projectId/test-cases"
        element={<TestCasesRoute />}
      />
      <Route
        path="/projects/:projectId/test-cases/:testCaseId"
        element={<TestCasesRoute />}
      />
      <Route path="/projects/:projectId/studio" element={<StudioRoute />} />
      <Route
        path="/projects/:projectId/studio/file/*"
        element={<StudioRoute />}
      />
      <Route path="/requirements" element={<RequirementsRoute />} />
      <Route
        path="/requirements/:requirementId"
        element={<RequirementsRoute />}
      />
      <Route path="/test-cases" element={<TestCasesRoute />} />
      <Route path="/test-cases/:testCaseId" element={<TestCasesRoute />} />
      <Route path="/runs" element={<RunsRoute />} />
      <Route path="/runs/tasks" element={<WorkflowRoute />} />
      <Route path="/runs/:runId" element={<RunWorkspaceRoute />} />
      <Route path="/tasks" element={<LegacyTasksRoute />} />
      <Route path="/recorder" element={<RecorderRoute />} />
      <Route path="/failures" element={<FailuresRoute />} />
      <Route path="/failures/:failureId" element={<FailuresRoute />} />
      <Route path="/flaky" element={<FlakyRoute />} />
      <Route path="/quality" element={<QualityRoute />} />
      <Route path="/workers" element={<WorkersPage />} />
      <Route path="/security" element={<SecurityPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="/dashboard" element={<Navigate to="/" replace />} />
      <Route path="/automation" element={<Navigate to="/library" replace />} />
      <Route path="*" element={<NotFoundRoute />} />
    </Route>
  </Routes>
);
