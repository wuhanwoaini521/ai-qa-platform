import React, { Suspense, useEffect, useRef } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Navigation } from '../components/Navigation';
import { Header } from '../components/Header';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { LoadingState } from '../components/AsyncState';
import { useTranslation } from 'react-i18next';
import { useProjectScope } from './ProjectScope';
import { usePreferences } from './Preferences';
import { ReadinessNotice } from '../components/ReadinessNotice';

/** Title keys per route, resolved through i18n (`titles` namespace). */
const PAGE_TITLES: { match: (path: string) => boolean; titleKey: string }[] = [
  { match: (p) => p === '/', titleKey: 'dashboard' },
  { match: (p) => p.includes('/studio'), titleKey: 'automation' },
  { match: (p) => p === '/workspace' || p.startsWith('/workspace/'), titleKey: 'workspace' },
  { match: (p) => p === '/workflow' || p === '/runs/tasks', titleKey: 'workflow' },
  { match: (p) => p === '/library', titleKey: 'library' },
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
  const { selectedProjectId } = useProjectScope();

  // Land on the configured start page once, right after a fresh sign-in.
  const landedRef = useRef<boolean>(false);
  useEffect(() => {
    if (!landedRef.current && location.pathname === '/' && startPage !== '/') {
      landedRef.current = true;
      navigate(startPage, { replace: true });
    }
  }, [location.pathname, startPage, navigate]);

  const fullBleed = location.pathname.includes('/studio');
  const workspaceRoute = location.pathname === '/workspace' || location.pathname.startsWith('/workspace/');
  const workspaceParams = new URLSearchParams(location.search);
  const workspaceStage = workspaceParams.get('stage');
  const workspaceView = workspaceParams.get('view');
  const workspaceResultsRoute = workspaceRoute && (
    workspaceStage === 'result' || (!workspaceStage && workspaceView === 'results')
  );
  const titleKey = PAGE_TITLES.find((entry) => entry.match(location.pathname))?.titleKey;
  const title = titleKey ? t(titleKey) : t('common:appName');

  return (
    <div className="app-container">
      <div className="app-frame">
        <a className="skip-to-content" href="#main-content">{t('common:skipToContent')}</a>
        <Header
          title={title}
          selectedProjectId={selectedProjectId}
          onSignOut={onSignOut}
        />

        <div className="app-body">
          <Navigation />
          <div className="app-main">
            <main id="main-content" className={`content-viewport ${fullBleed ? 'full-bleed' : ''} ${workspaceRoute ? 'is-workspace' : ''} ${workspaceResultsRoute ? 'is-workspace-result' : ''}`} tabIndex={-1}>
              <ReadinessNotice />
              <ErrorBoundary resetKey={location.pathname}>
                <Suspense fallback={<LoadingState />}>
                  <Outlet />
                </Suspense>
              </ErrorBoundary>
            </main>
          </div>
        </div>
      </div>
    </div>
  );
};
