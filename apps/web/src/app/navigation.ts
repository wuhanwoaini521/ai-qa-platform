import { useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { NavTab } from '../components/Navigation';
import { useProjectScope } from './ProjectScope';

export function pathForTab(tab: NavTab, projectId: string | null): string {
  switch (tab) {
    case 'dashboard':
      return '/';
    case 'projects':
      return '/projects';
    case 'requirements':
      return projectId ? `/projects/${projectId}/requirements` : '/requirements';
    case 'test_cases':
      return '/test-cases';
    case 'automation':
      return projectId ? `/projects/${projectId}/studio` : '/projects';
    case 'runs':
      return '/runs';
    case 'tasks':
      return '/tasks';
    case 'recorder':
      return '/recorder';
    case 'flaky':
      return '/flaky';
    case 'failures':
      return '/failures';
    case 'quality':
      return '/quality';
    case 'security':
      return '/security';
    case 'workers':
      return '/workers';
    case 'settings':
      return '/settings';
  }
}

/** Rewrites the `:projectId` segment of a project-scoped path, keeping the rest of the route. */
export function withProjectId(pathname: string, projectId: string | null): string {
  if (!projectId) {
    return pathname;
  }
  const match = /^\/projects\/[^/]+(?<rest>\/.*)?$/.exec(pathname);
  if (match) {
    return `/projects/${projectId}${match.groups?.rest ?? ''}`;
  }
  return pathname;
}

interface AppNavigation {
  /** `projectId` overrides the current selection, so a row action targets the row's project. */
  toTab: (tab: NavTab, projectId?: string | null) => void;
  toStudio: (filePath?: string, lineNumber?: number, debugNodeId?: string) => void;
  toRun: (runId?: string) => void;
  toFailures: (failureId?: string) => void;
}

/**
 * Route-aware replacement for the old `NavTab` state machine: every cross-page jump
 * becomes a real URL so it survives refresh, sharing and back/forward.
 */
export function useAppNavigation(): AppNavigation {
  const navigate = useNavigate();
  const { selectedProjectId } = useProjectScope();

  const toTab = useCallback(
    (tab: NavTab, projectId?: string | null) => {
      navigate(pathForTab(tab, projectId ?? selectedProjectId));
    },
    [navigate, selectedProjectId]
  );

  const toStudio = useCallback(
    (filePath?: string, lineNumber?: number, debugNodeId?: string) => {
      if (!selectedProjectId) {
        navigate('/projects');
        return;
      }
      const base = `/projects/${selectedProjectId}/studio`;
      // Encode once here: react-router decodes route params before the page reads them.
      const params = new URLSearchParams();
      if (lineNumber && lineNumber > 0) params.set('line', String(Math.floor(lineNumber)));
      if (debugNodeId) params.set('nodeid', debugNodeId);
      const query = params.size ? '?' + params.toString() : '';
      navigate(filePath ? base + '/file/' + encodeURIComponent(filePath) + query : base + query);
    },
    [navigate, selectedProjectId]
  );

  const toRun = useCallback(
    (runId?: string) => {
      navigate(runId ? `/runs/${runId}` : '/runs');
    },
    [navigate]
  );

  const toFailures = useCallback(
    (failureId?: string) => {
      navigate(failureId ? `/failures/${failureId}` : '/failures');
    },
    [navigate]
  );

  return useMemo(() => ({ toTab, toStudio, toRun, toFailures }), [toTab, toStudio, toRun, toFailures]);
}
