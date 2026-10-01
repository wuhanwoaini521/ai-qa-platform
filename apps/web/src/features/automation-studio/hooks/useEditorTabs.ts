import { MouseEvent, useCallback, useRef, useState } from 'react';
import { api } from '../../../api/client';
import { EditorTab } from '../types';

interface UseEditorTabsOptions {
  projectId: string | null;
  /** `loadingFile` is owned by useWorkspaceFiles and rendered by the editor pane. */
  setLoadingFile: (loading: boolean) => void;
  /** Hides the Git diff view (owned by useWorkspaceGit) when a file becomes active. */
  hideDiffView: () => void;
  /** Post-save side effects (diff + validation + test refresh), run inside the save transaction. */
  onAfterSave?: (path: string) => Promise<void> | void;
  onAfterSaveAll?: () => Promise<void> | void;
}

export const useEditorTabs = ({
  projectId,
  setLoadingFile,
  hideDiffView,
  onAfterSave,
  onAfterSaveAll,
}: UseEditorTabsOptions) => {
  const [tabs, setTabs] = useState<EditorTab[]>([]);
  const [activeTabPath, setActiveTabPath] = useState<string | null>(null);
  const [saving, setSaving] = useState<boolean>(false);

  // Latest-ref so the save callbacks below keep their original dependency arrays.
  const afterSaveRef = useRef(onAfterSave);
  afterSaveRef.current = onAfterSave;
  const afterSaveAllRef = useRef(onAfterSaveAll);
  afterSaveAllRef.current = onAfterSaveAll;

  const activeTab = tabs.find((t) => t.path === activeTabPath);

  // Open file in tabs
  const openFile = async (path: string) => {
    if (!projectId) return;
    const existingIndex = tabs.findIndex((t) => t.path === path);
    if (existingIndex !== -1) {
      setActiveTabPath(path);
      hideDiffView();
      return;
    }

    try {
      setLoadingFile(true);
      const res = await api.readWorkspaceFile(projectId, path);
      const filename = path.split('/').pop() || path;
      const newTab: EditorTab = {
        path,
        name: filename,
        content: res.content,
        initialContent: res.content,
        isDirty: false,
      };
      setTabs((prev) => (prev.some((t) => t.path === path) ? prev : [...prev, newTab]));
      setActiveTabPath(path);
      hideDiffView();
    } catch (err) {
      console.error(`Failed to read file ${path}`, err);
    } finally {
      setLoadingFile(false);
    }
  };

  const selectTab = (path: string) => {
    setActiveTabPath(path);
    hideDiffView();
  };

  const closeTab = (path: string, e?: MouseEvent) => {
    if (e) e.stopPropagation();
    const tabToClose = tabs.find((t) => t.path === path);
    if (tabToClose?.isDirty) {
      const confirmClose = window.confirm(
        `File '${tabToClose.name}' has unsaved changes. Do you want to close it?`
      );
      if (!confirmClose) return;
    }

    const nextTabs = tabs.filter((t) => t.path !== path);
    setTabs(nextTabs);
    if (activeTabPath === path) {
      if (nextTabs.length > 0) {
        setActiveTabPath(nextTabs[nextTabs.length - 1].path);
      } else {
        setActiveTabPath(null);
      }
    }
  };

  const updateContent = (value: string | undefined) => {
    const newContent = value ?? '';
    if (!activeTabPath) return;
    setTabs((prev) =>
      prev.map((t) => {
        if (t.path === activeTabPath) {
          return {
            ...t,
            content: newContent,
            isDirty: newContent !== t.initialContent,
          };
        }
        return t;
      })
    );
  };

  /** Renames an open tab in place after a workspace rename. */
  const renameTab = (path: string, newPath: string) => {
    setTabs((prev) =>
      prev.map((t) =>
        t.path === path
          ? { ...t, path: newPath, name: newPath.split('/').pop() || newPath }
          : t
      )
    );
    if (activeTabPath === path) {
      setActiveTabPath(newPath);
    }
  };

  const saveActiveTab = useCallback(async () => {
    if (!projectId || !activeTab || saving) return false;
    try {
      setSaving(true);
      await api.writeWorkspaceFile(projectId, activeTab.path, activeTab.content);
      setTabs((prev) =>
        prev.map((t) =>
          t.path === activeTab.path
            ? { ...t, initialContent: t.content, isDirty: false }
            : t
        )
      );
      await afterSaveRef.current?.(activeTab.path);
      return true;
    } catch (err) {
      console.error(`Failed to save file ${activeTab.path}`, err);
      return false;
    } finally {
      setSaving(false);
    }
  }, [projectId, activeTab, saving]);

  const saveAll = useCallback(async () => {
    if (!projectId) return;
    const dirtyTabs = tabs.filter((t) => t.isDirty);
    if (dirtyTabs.length === 0) return;
    try {
      setSaving(true);
      for (const t of dirtyTabs) {
        await api.writeWorkspaceFile(projectId, t.path, t.content);
      }
      setTabs((prev) =>
        prev.map((t) => ({ ...t, initialContent: t.content, isDirty: false }))
      );
      await afterSaveAllRef.current?.();
    } catch (err) {
      console.error('Failed to save all files', err);
    } finally {
      setSaving(false);
    }
  }, [projectId, tabs]);

  return {
    tabs,
    activeTab,
    activeTabPath,
    saving,
    openFile,
    selectTab,
    closeTab,
    updateContent,
    renameTab,
    saveActiveTab,
    saveAll,
  };
};
