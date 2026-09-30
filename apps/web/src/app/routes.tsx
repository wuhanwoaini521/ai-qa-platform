import React, { lazy } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, Route, Routes, useNavigate, useParams } from 'react-router-dom';
import { DashboardPage } from '../pages/DashboardPage';
import { ProjectsPage } from '../pages/ProjectsPage';
import { AppLayout } from './AppLayout';
import { useProjectScope, useRouteProjectScope } from './ProjectScope';
import { useAppNavigation } from './navigation';
import { EmptyState } from '../components/AsyncState';

const RequirementsPage = lazy(() =>
  import('../pages/RequirementsPage').then((m) => ({ default: m.RequirementsPage }))
);
const TestCasesPage = lazy(() => import('../pages/TestCasesPage').then((m) => ({ default: m.TestCasesPage })));
const AutomationStudioPage = lazy(() =>
  import('../pages/AutomationStudioPage').then((m) => ({ default: m.AutomationStudioPage }))
);
const RunsPage = lazy(() => import('../pages/RunsPage').then((m) => ({ default: m.RunsPage })));
const TasksPage = lazy(() => import('../pages/TasksPage').then((m) => ({ default: m.TasksPage })));
const FailuresPage = lazy(() => import('../pages/FailuresPage').then((m) => ({ default: m.FailuresPage })));
const FlakyPage = lazy(() => import('../pages/FlakyPage').then((m) => ({ default: m.FlakyPage })));
const QualityPage = lazy(() => import('../pages/QualityPage').then((m) => ({ default: m.QualityPage })));
const SecurityPage = lazy(() => import('../pages/SecurityPage').then((m) => ({ default: m.SecurityPage })));
const WorkersPage = lazy(() => import('../pages/WorkersPage').then((m) => ({ default: m.WorkersPage })));
const SettingsPage = lazy(() => import('../pages/SettingsPage').then((m) => ({ default: m.SettingsPage })));
const RecorderPage = lazy(() => import('../pages/RecorderPage').then((m) => ({ default: m.RecorderPage })));

const DashboardRoute: React.FC = () => {
  const nav = useAppNavigation();
  const navigate = useNavigate();
  return <DashboardPage onNavigate={nav.toTab} onOpenTask={(id) => navigate(`/tasks?taskId=${encodeURIComponent(id)}`)} onOpenCreateProject={() => nav.toTab('projects')} />;
};

const ProjectsRoute: React.FC = () => {
  const { projectId } = useParams();
  const nav = useAppNavigation();
  const { projects, loading, refresh, createProject, selectProject } = useProjectScope();
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

const RequirementsRoute: React.FC = () => {
  const { projectId, requirementId } = useParams();
  const { projects, selectedProjectId } = useProjectScope();
  useRouteProjectScope(projectId);

  return (
    <RequirementsPage
      projects={projects}
      selectedProjectId={projectId ?? selectedProjectId}
      initialRequirementId={requirementId ?? null}
    />
  );
};

const TestCasesRoute: React.FC = () => {
  const { testCaseId } = useParams();
  const nav = useAppNavigation();
  const { projects, selectedProjectId } = useProjectScope();

  return (
    <TestCasesPage
      projects={projects}
      selectedProjectId={selectedProjectId}
      initialTestCaseId={testCaseId ?? null}
      onNavigateToStudio={nav.toStudio}
      onNavigateToRuns={nav.toRun}
    />
  );
};

const StudioRoute: React.FC = () => {
  const params = useParams();
  const navigate = useNavigate();
  const nav = useAppNavigation();
  const { projects, selectedProjectId, selectProject } = useProjectScope();
  const projectId = params.projectId;
  useRouteProjectScope(projectId);

  const splat = params['*'];
  return (
    <AutomationStudioPage
      projects={projects}
      selectedProjectId={projectId ?? selectedProjectId}
      onSelectProject={(nextProjectId) => {
        selectProject(nextProjectId);
        navigate(`/projects/${nextProjectId}/studio`);
      }}
      onNavigateToRuns={nav.toRun}
      initialOpenFilePath={splat ?? null}
    />
  );
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

const RecorderRoute: React.FC = () => {
  const { projects, selectedProjectId } = useProjectScope();
  return <RecorderPage projects={projects} selectedProjectId={selectedProjectId} />;
};

const TasksRoute: React.FC = () => {
  const { projects, selectedProjectId } = useProjectScope();
  return <TasksPage projects={projects} selectedProjectId={selectedProjectId} />;
};

const FailuresRoute: React.FC = () => {
  const { failureId } = useParams();
  const navigate = useNavigate();
  const nav = useAppNavigation();
  const { projects, selectedProjectId } = useProjectScope();

  return (
    <FailuresPage
      projects={projects}
      selectedProjectId={selectedProjectId}
      initialFailureId={failureId ?? null}
      onSelectFailure={(id) => navigate(`/failures/${id}`)}
      onOpenInStudio={nav.toStudio}
      onNavigateToRuns={nav.toRun}
    />
  );
};

const FlakyRoute: React.FC = () => {
  const nav = useAppNavigation();
  const { projects, selectedProjectId } = useProjectScope();

  return <FlakyPage projects={projects} selectedProjectId={selectedProjectId} onNavigateToRuns={nav.toRun} />;
};

const QualityRoute: React.FC = () => {
  const nav = useAppNavigation();
  const { projects, selectedProjectId } = useProjectScope();

  return <QualityPage projects={projects} selectedProjectId={selectedProjectId} onNavigateToRuns={nav.toRun} />;
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
      <Route path="/projects" element={<ProjectsRoute />} />
      <Route path="/projects/:projectId" element={<ProjectsRoute />} />
      <Route path="/projects/:projectId/requirements" element={<RequirementsRoute />} />
      <Route path="/projects/:projectId/studio" element={<StudioRoute />} />
      <Route path="/projects/:projectId/studio/file/*" element={<StudioRoute />} />
      <Route path="/requirements" element={<RequirementsRoute />} />
      <Route path="/requirements/:requirementId" element={<RequirementsRoute />} />
      <Route path="/test-cases" element={<TestCasesRoute />} />
      <Route path="/test-cases/:testCaseId" element={<TestCasesRoute />} />
      <Route path="/runs" element={<RunsRoute />} />
      <Route path="/runs/:runId" element={<RunsRoute />} />
      <Route path="/tasks" element={<TasksRoute />} />
      <Route path="/recorder" element={<RecorderRoute />} />
      <Route path="/failures" element={<FailuresRoute />} />
      <Route path="/failures/:failureId" element={<FailuresRoute />} />
      <Route path="/flaky" element={<FlakyRoute />} />
      <Route path="/quality" element={<QualityRoute />} />
      <Route path="/workers" element={<WorkersPage />} />
      <Route path="/security" element={<SecurityPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="/dashboard" element={<Navigate to="/" replace />} />
      <Route path="/automation" element={<Navigate to="/projects" replace />} />
      <Route path="*" element={<NotFoundRoute />} />
    </Route>
  </Routes>
);
