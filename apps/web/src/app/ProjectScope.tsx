import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Project, ProjectCreate } from '../types';
import { api } from '../api/client';
import { usePreferences } from './Preferences';

const SELECTED_PROJECT_KEY = 'ai-qa.selected-project';

interface ProjectScopeValue {
  projects: Project[];
  loading: boolean;
  error: string | null;
  selectedProjectId: string | null;
  /** Select the active project. `null` clears the selection. */
  selectProject: (projectId: string | null) => void;
  refresh: () => Promise<void>;
  createProject: (data: ProjectCreate) => Promise<Project>;
}

const ProjectScopeContext = createContext<ProjectScopeValue | null>(null);

export const ProjectScopeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { defaultProjectId } = usePreferences();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(() => {
    try {
      return window.localStorage.getItem(SELECTED_PROJECT_KEY);
    } catch {
      return null;
    }
  });

  const selectProject = useCallback((projectId: string | null) => {
    setSelectedProjectId(projectId);
    try {
      if (projectId) {
        window.localStorage.setItem(SELECTED_PROJECT_KEY, projectId);
      } else {
        window.localStorage.removeItem(SELECTED_PROJECT_KEY);
      }
    } catch {
      /* storage unavailable (private mode): the selection just does not persist */
    }
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getProjects();
      setProjects(data);
      setError(null);
      setSelectedProjectId((current) => {
        // A project pinned in Settings wins over the last used one.
        if (defaultProjectId && data.some((project) => project.id === defaultProjectId)) {
          return defaultProjectId;
        }
        if (current && data.some((project) => project.id === current)) {
          return current;
        }
        const next = data.length > 0 ? data[0].id : null;
        try {
          if (next) {
            window.localStorage.setItem(SELECTED_PROJECT_KEY, next);
          } else {
            window.localStorage.removeItem(SELECTED_PROJECT_KEY);
          }
        } catch {
          /* ignore */
        }
        return next;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load projects');
    } finally {
      setLoading(false);
    }
  }, [defaultProjectId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const createProject = useCallback(
    async (data: ProjectCreate) => {
      const created = await api.createProject(data);
      setProjects((prev) => [created, ...prev]);
      selectProject(created.id);
      return created;
    },
    [selectProject]
  );

  const value = useMemo<ProjectScopeValue>(
    () => ({ projects, loading, error, selectedProjectId, selectProject, refresh, createProject }),
    [projects, loading, error, selectedProjectId, selectProject, refresh, createProject]
  );

  return <ProjectScopeContext.Provider value={value}>{children}</ProjectScopeContext.Provider>;
};

export function useProjectScope(): ProjectScopeValue {
  const value = useContext(ProjectScopeContext);
  if (!value) {
    throw new Error('useProjectScope must be used inside <ProjectScopeProvider>');
  }
  return value;
}

/**
 * Keeps the project context aligned with a `:projectId` route param, so a deep link
 * such as `/projects/proj_123/studio` also updates the header project selector.
 */
export function useRouteProjectScope(routeProjectId: string | undefined): void {
  const { selectProject, selectedProjectId } = useProjectScope();
  useEffect(() => {
    if (routeProjectId && routeProjectId !== selectedProjectId) {
      selectProject(routeProjectId);
    }
  }, [routeProjectId, selectedProjectId, selectProject]);
}
