import { useState } from 'react';
import { FileNode, GitDiffResult } from '../../../types';
import { api } from '../../../api/client';

/** Flatten file paths for quick open. */
const extractPaths = (nodes: FileNode[]): string[] => {
  let result: string[] = [];
  for (const node of nodes) {
    if (node.type === 'file') {
      result.push(node.path);
    }
    if (node.children) {
      result = result.concat(extractPaths(node.children));
    }
  }
  return result;
};

interface UseWorkspaceFilesOptions {
  /** Working-tree diff produced by `fetchFiles`; persisted by the owner of `diffResult` (useWorkspaceGit). */
  onDiffLoaded?: (diff: GitDiffResult) => void;
}

export const useWorkspaceFiles = (projectId: string | null, options: UseWorkspaceFilesOptions = {}) => {
  const { onDiffLoaded } = options;

  const [files, setFiles] = useState<FileNode[]>([]);
  const [allFilePaths, setAllFilePaths] = useState<string[]>([]);
  const [loadingFile, setLoadingFile] = useState<boolean>(false);

  // Expanded folders in explorer
  const [expandedFolders, setExpandedFolders] = useState<Record<string, boolean>>({
    tests: true,
    pages: true,
    flows: true,
    knowledge: true,
  });

  const fetchFiles = async () => {
    if (!projectId) return;
    try {
      const tree = await api.getWorkspaceFiles(projectId);
      setFiles(tree);
      setAllFilePaths(extractPaths(tree));
      const diff = await api.getWorkspaceDiff(projectId);
      onDiffLoaded?.(diff);
    } catch (err) {
      console.error('Failed to load workspace files', err);
    }
  };

  /** Bootstrap + tree refresh; rejects so the caller can report the failure. */
  const bootstrapWorkspace = async () => {
    if (!projectId) return;
    await api.bootstrapWorkspace(projectId);
    await fetchFiles();
  };

  const createWorkspaceFile = async (path: string) => {
    if (!projectId) return;
    await api.createWorkspaceFile(projectId, path, '# New File\n');
  };

  const createWorkspaceDirectory = async (path: string) => {
    if (!projectId) return;
    await api.createWorkspaceDirectory(projectId, path);
  };

  const renameWorkspaceEntry = async (targetPath: string, newPath: string) => {
    if (!projectId) return;
    await api.renameWorkspaceFile(projectId, targetPath, newPath);
  };

  const deleteWorkspaceEntry = async (targetPath: string) => {
    if (!projectId) return;
    await api.deleteWorkspaceFile(projectId, targetPath);
  };

  const toggleFolder = (path: string) => {
    setExpandedFolders((prev) => ({
      ...prev,
      [path]: !prev[path],
    }));
  };

  return {
    files,
    allFilePaths,
    expandedFolders,
    loadingFile,
    setLoadingFile,
    fetchFiles,
    bootstrapWorkspace,
    createWorkspaceFile,
    createWorkspaceDirectory,
    renameWorkspaceEntry,
    deleteWorkspaceEntry,
    toggleFolder,
  };
};
