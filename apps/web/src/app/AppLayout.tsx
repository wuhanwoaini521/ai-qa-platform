import React, { Suspense, useEffect, useRef } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Navigation } from '../components/Navigation';
import { Header } from '../components/Header';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { LoadingState } from '../components/AsyncState';
import { useTranslation } from 'react-i18next';
import { useProjectScope } from './ProjectScope';
import { usePreferences } from './Preferences';
import { withProjectId } from './navigation';
import { ReadinessNotice } from '../components/ReadinessNotice';

/** Title keys per route, resolved through i18n (`titles` namespace). */
const PAGE_TITLES: { match: (path: string) => boolean; titleKey: string }[] = [
  { match: (p) => p === '/', titleKey: 'dashboard' },
  { match: (p) => p.includes('/studio'), titleKey: 'automation' },
  { match: (p) => /^\/projects(\/[^/]+)?$/.test(p), titleKey: 'projects' },
  { match: (p) => p.startsWith('/requirements') || p.includes('/requirements'), titleKey: 'requirements' },
  { match: (p) => p.startsWith('/test-cases'), titleKey: 'testCases' },
  { match: (p) => p.startsWith('/runs'), titleKey: 'runs' },
  { match: (p) => p.startsWith('/tasks'), titleKey: 'tasks' },
  { match: (p) => p.startsWith('/recorder'), titleKey: 'recorder' },
  { match: (p) => p.startsWith('/flaky'), titleKey: 'flaky' },
  { match: (p) => p.startsWith('/failures'), titleKey: 'failures' },
  { match: (p) => p.startsWith('/quality'), titleKey: 'quality' },
  { match: (p) => p.startsWith('/security'), titleKey: 'security' },
  { match: (p) => p.startsWith('/workers'), titleKey: 'workers' },
  { match: (p) => p.startsWith('/settings'), titleKey: 'settings' },
];

export const AppLayout: React.FC<{ onSignOut: () => void }> = ({ onSignOut }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { t } = useTranslation('titles');
  const { startPage } = usePreferences();
  const { projects, selectedProjectId, selectProject } = useProjectScope();

  // Land on the configured start page once, right after a fresh sign-in.
  const landedRef = useRef<boolean>(false);
  useEffect(() => {
    if (!landedRef.current && location.pathname === '/' && startPage !== '/') {
      landedRef.current = true;
      navigate(startPage, { replace: true });
    }
  }, [location.pathname, startPage, navigate]);

  const fullBleed = location.pathname.includes('/studio');
  const titleKey = PAGE_TITLES.find((entry) => entry.match(location.pathname))?.titleKey;
  const title = titleKey ? t(titleKey) : t('common:appName');

  const handleSelectProject = (projectId: string) => {
    selectProject(projectId);
    // Keep a project-scoped route pointing at the project the user just picked.
    navigate(withProjectId(location.pathname, projectId));
  };

  return (
    <div className="app-container">
      <Navigation />

      <div className="app-main">
        <ReadinessNotice />
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
