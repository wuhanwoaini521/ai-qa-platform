import { useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { NavTab } from '../components/Navigation';
import { useProjectScope } from './ProjectScope';
import { buildScopedHref } from './workspaceContext';

export function pathForTab(tab: NavTab, projectId: string | null): string {
  switch (tab) {
    case 'dashboard':
      return '/';
    case 'projects':
      return '/projects';
    case 'workspace':
      return projectId ? `/workspace/${projectId}` : '/workspace';
    case 'discovery':
      return `${projectId ? `/workspace/${projectId}` : '/workspace'}?stage=discover&view=discover`;
    case 'workflow':
      return '/workflow';
    case 'library':
      return '/library';
    case 'requirements':
      return projectId
        ? `/projects/${projectId}/requirements`
        : '/requirements';
    case 'test_cases':
      return '/test-cases';
    case 'automation':
      return projectId ? `/workspace/${projectId}?view=code` : '/projects';
    case 'runs':
      return buildScopedHref('/runs', { projectId: projectId ?? undefined });
    case 'tasks':
      return buildScopedHref('/runs/tasks', { projectId: projectId ?? undefined });
    case 'recorder':
      return projectId
        ? `/workspace/${projectId}?view=browser`
        : '/projects';
    case 'flaky':
      return '/flaky';
    case 'failures':
      return '/failures';
    case 'quality':
      return buildScopedHref('/quality', { projectId: projectId ?? undefined });
    case 'security':
      return '/security';
    case 'workers':
      return '/workers';
    case 'settings':
      return '/settings';
  }
}

interface AppNavigation {
  /** `projectId` overrides the current selection, so a row action targets the row's project. */
  toTab: (tab: NavTab, projectId?: string | null) => void;
  toStudio: (
    filePath?: string,
    lineNumber?: number,
    debugNodeId?: string,
    failureContext?: { failureId: string; runId: string },
  ) => void;
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
    [navigate, selectedProjectId],
  );

  const toStudio = useCallback(
    (filePath?: string, lineNumber?: number, debugNodeId?: string, failureContext?: { failureId: string; runId: string }) => {
      if (!selectedProjectId) {
        navigate('/projects');
        return;
      }
      const params = new URLSearchParams({
        view: failureContext || debugNodeId ? 'debug' : 'code',
      });
      if (filePath) params.set('file', filePath);
      if (lineNumber && lineNumber > 0)
        params.set('line', String(Math.floor(lineNumber)));
      if (debugNodeId) params.set('nodeid', debugNodeId);
      if (failureContext) {
        params.set('failureId', failureContext.failureId);
        params.set('parentRunId', failureContext.runId);
      }
      navigate(`/workspace/${selectedProjectId}?${params.toString()}`);
    },
    [navigate, selectedProjectId],
  );

  const toRun = useCallback(
    (runId?: string) => {
      navigate(runId ? `/runs/${runId}` : '/runs');
    },
    [navigate],
  );

  const toFailures = useCallback(
    (failureId?: string) => {
      navigate(failureId ? `/failures/${failureId}` : '/failures');
    },
    [navigate],
  );

  return useMemo(
    () => ({ toTab, toStudio, toRun, toFailures }),
    [toTab, toStudio, toRun, toFailures],
  );
}
