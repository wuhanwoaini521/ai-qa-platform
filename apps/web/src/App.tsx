import React, { useEffect, useState } from 'react';
import { Project, ProjectCreate } from './types';
import { api } from './api/client';
import { Navigation, NavTab } from './components/Navigation';
import { Header } from './components/Header';
import { DashboardPage } from './pages/DashboardPage';
import { ProjectsPage } from './pages/ProjectsPage';
import { RequirementsPage } from './pages/RequirementsPage';
import { TestCasesPage } from './pages/TestCasesPage';
import { AutomationStudioPage } from './pages/AutomationStudioPage';
import { RunsPage } from './pages/RunsPage';
import { FailuresPage } from './pages/FailuresPage';
import { FlakyPage } from './pages/FlakyPage';
import { QualityPage } from './pages/QualityPage';
import { SecurityPage } from './pages/SecurityPage';

export const App: React.FC = () => {
  const [currentTab, setCurrentTab] = useState<NavTab>('dashboard');
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [loadingProjects, setLoadingProjects] = useState<boolean>(true);

  // Cross-page navigation state
  const [studioTargetFile, setStudioTargetFile] = useState<string | null>(null);
  const [runsTargetId, setRunsTargetId] = useState<string | null>(null);

  const fetchProjects = async () => {
    try {
      setLoadingProjects(true);
      const data = await api.getProjects();
      setProjects(data);
      if (data.length > 0 && !selectedProjectId) {
        setSelectedProjectId(data[0].id);
      }
    } catch (err) {
      console.error('Failed to load projects', err);
    } finally {
      setLoadingProjects(false);
    }
  };

  useEffect(() => {
    fetchProjects();
  }, []);

  const handleCreateProject = async (data: ProjectCreate) => {
    const created = await api.createProject(data);
    setProjects([created, ...projects]);
    setSelectedProjectId(created.id);
  };

  const handleNavigateToStudio = (filePath: string) => {
    setStudioTargetFile(filePath);
    setCurrentTab('automation');
  };

  const handleNavigateToRuns = (runId?: string) => {
    if (runId) setRunsTargetId(runId);
    setCurrentTab('runs');
  };

  const handleNavigateToFailures = () => {
    setCurrentTab('failures');
  };

  const pageTitles: Record<NavTab, string> = {
    dashboard: 'Platform Overview',
    projects: 'QA Projects',
    requirements: 'Requirements & Design',
    test_cases: 'Test Cases',
    automation: 'Automation Studio',
    runs: 'Execution Runs & Runners',
    flaky: 'Flaky Intelligence & Stability',
    failures: 'Failure Intelligence & Healing',
    quality: 'Quality Intelligence & Release Gate',
    security: 'Enterprise Security & RBAC',
  };

  return (
    <div className="app-container">
      {/* Sidebar Navigation */}
      <Navigation currentTab={currentTab} onSelectTab={setCurrentTab} />

      {/* Main Content Area */}
      <div className="app-main">
        {currentTab !== 'automation' && (
          <Header
            title={pageTitles[currentTab]}
            projects={projects}
            selectedProjectId={selectedProjectId}
            onSelectProject={setSelectedProjectId}
          />
        )}

        <div className={`content-viewport ${currentTab === 'automation' ? 'full-bleed' : ''}`}>
          {currentTab === 'dashboard' && (
            <DashboardPage
              onNavigate={setCurrentTab}
              onOpenCreateProject={() => setCurrentTab('projects')}
            />
          )}

          {currentTab === 'projects' && (
            <ProjectsPage
              projects={projects}
              loading={loadingProjects}
              onRefresh={fetchProjects}
              onCreateProject={handleCreateProject}
              onSelectProject={setSelectedProjectId}
              onNavigate={setCurrentTab}
            />
          )}

          {currentTab === 'requirements' && (
            <RequirementsPage
              projects={projects}
              selectedProjectId={selectedProjectId}
            />
          )}

          {currentTab === 'test_cases' && (
            <TestCasesPage
              projects={projects}
              selectedProjectId={selectedProjectId}
              onNavigateToStudio={handleNavigateToStudio}
              onNavigateToRuns={handleNavigateToRuns}
            />
          )}

          {currentTab === 'automation' && (
            <AutomationStudioPage
              projects={projects}
              selectedProjectId={selectedProjectId}
              onSelectProject={setSelectedProjectId}
              onNavigateToRuns={handleNavigateToRuns}
              initialOpenFilePath={studioTargetFile}
            />
          )}

          {currentTab === 'runs' && (
            <RunsPage
              projects={projects}
              selectedProjectId={selectedProjectId}
              initialRunId={runsTargetId}
              onNavigateToFailures={handleNavigateToFailures}
            />
          )}

          {currentTab === 'flaky' && (
            <FlakyPage
              projects={projects}
              selectedProjectId={selectedProjectId}
              onNavigateToRuns={handleNavigateToRuns}
            />
          )}

          {currentTab === 'failures' && (
            <FailuresPage
              projects={projects}
              selectedProjectId={selectedProjectId}
              onNavigateToRuns={handleNavigateToRuns}
            />
          )}

          {currentTab === 'quality' && (
            <QualityPage
              projects={projects}
              selectedProjectId={selectedProjectId}
              onNavigateToRuns={handleNavigateToRuns}
            />
          )}

          {currentTab === 'security' && <SecurityPage />}
        </div>
      </div>
    </div>
  );
};
