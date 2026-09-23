import { useState } from 'react';
import { CollectedTest } from '../../../types';
import { api } from '../../../api/client';

export const useTestExplorer = (projectId: string | null) => {
  const [collectedTests, setCollectedTests] = useState<CollectedTest[]>([]);
  const [loadingTests, setLoadingTests] = useState<boolean>(false);

  const fetchCollectedTests = async () => {
    if (!projectId) return;
    try {
      setLoadingTests(true);
      const tests = await api.collectWorkspaceTests(projectId);
      setCollectedTests(tests);
    } catch (err) {
      console.error('Failed to collect workspace tests', err);
    } finally {
      setLoadingTests(false);
    }
  };

  /** Post-save refresh: no spinner, no error handling — matches the original fire-and-forget call. */
  const refreshTestsInBackground = () => {
    if (!projectId) return;
    api.collectWorkspaceTests(projectId).then((tests) => setCollectedTests(tests));
  };

  return { collectedTests, loadingTests, fetchCollectedTests, refreshTestsInBackground };
};
