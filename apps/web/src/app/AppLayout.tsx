import React, { Suspense } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Navigation } from '../components/Navigation';
import { Header } from '../components/Header';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { LoadingState } from '../components/AsyncState';
import { useProjectScope } from './ProjectScope';
import { withProjectId } from './navigation';

const PAGE_TITLES: { match: (path: string) => boolean; title: string }[] = [
  { match: (p) => p === '/', title: 'Platform Overview' },
  { match: (p) => p.includes('/studio'), title: 'Automation Studio' },
  { match: (p) => p.startsWith('/projects') || p.startsWith('/requirements'), title: 'Requirements & Design' },
  { match: (p) => p.startsWith('/test-cases'), title: 'Test Cases' },
  { match: (p) => p.startsWith('/runs'), title: 'Execution Runs & Runners' },
  { match: (p) => p.startsWith('/flaky'), title: 'Flaky Intelligence & Stability' },
  { match: (p) => p.startsWith('/failures'), title: 'Failure Intelligence & Healing' },
  { match: (p) => p.startsWith('/quality'), title: 'Quality Intelligence & Release Gate' },
  { match: (p) => p.startsWith('/security'), title: 'Enterprise Security & RBAC' },
  { match: (p) => p.startsWith('/workers'), title: 'Distributed Workers & Cluster' },
];

export const AppLayout: React.FC<{ onSignOut: () => void }> = ({ onSignOut }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { projects, selectedProjectId, selectProject } = useProjectScope();

  const fullBleed = location.pathname.includes('/studio');
  const title = PAGE_TITLES.find((entry) => entry.match(location.pathname))?.title ?? 'AI QA Platform';

  const handleSelectProject = (projectId: string) => {
    selectProject(projectId);
    // Keep a project-scoped route pointing at the project the user just picked.
    navigate(withProjectId(location.pathname, projectId));
  };

  return (
    <div className="app-container">
      <Navigation />

      <div className="app-main">
        {!fullBleed && (
          <Header
            title={title}
            projects={projects}
            selectedProjectId={selectedProjectId}
            onSelectProject={handleSelectProject}
            actions={
              <button type="button" className="btn btn-secondary" onClick={onSignOut}>
                Sign out
              </button>
            }
          />
        )}

        <div className={`content-viewport ${fullBleed ? 'full-bleed' : ''}`}>
          <ErrorBoundary resetKey={location.pathname}>
            <Suspense fallback={<LoadingState />}>
              <Outlet />
            </Suspense>
          </ErrorBoundary>
        </div>
      </div>
    </div>
  );
};
