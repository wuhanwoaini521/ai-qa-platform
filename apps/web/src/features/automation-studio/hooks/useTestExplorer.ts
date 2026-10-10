import { useEffect, useRef, useState } from 'react';
import { CollectedTest } from '../../../types';
import { api } from '../../../api/client';

export const useTestExplorer = (projectId: string | null) => {
  const [stateProjectId, setStateProjectId] = useState(projectId);
  const [collectedTests, setCollectedTests] = useState<CollectedTest[]>([]);
  const [loadingTests, setLoadingTests] = useState<boolean>(false);
  const [hasCollectedTests, setHasCollectedTests] = useState<boolean>(false);
  const [collectionFailed, setCollectionFailed] = useState<boolean>(false);
  const requestIdRef = useRef(0);

  useEffect(() => {
    requestIdRef.current += 1;
    setStateProjectId(projectId);
    setCollectedTests([]);
    setLoadingTests(false);
    setHasCollectedTests(false);
    setCollectionFailed(false);
    return () => { requestIdRef.current += 1; };
  }, [projectId]);

  const fetchCollectedTests = async () => {
    if (!projectId) return;
    const requestId = ++requestIdRef.current;
    setCollectionFailed(false);
    try {
      setLoadingTests(true);
      const tests = await api.collectWorkspaceTests(projectId);
      if (requestId !== requestIdRef.current) return;
      setCollectedTests(tests);
      setHasCollectedTests(true);
    } catch {
      if (requestId === requestIdRef.current) setCollectionFailed(true);
    } finally {
      if (requestId === requestIdRef.current) setLoadingTests(false);
    }
  };

  /** Refresh after a user-initiated save without replacing the Studio with a blocking spinner. */
  const refreshTestsInBackground = () => {
    if (!projectId) return;
    const requestId = ++requestIdRef.current;
    setCollectionFailed(false);
    setLoadingTests(true);
    api.collectWorkspaceTests(projectId).then((tests) => {
      if (requestId !== requestIdRef.current) return;
      setCollectedTests(tests);
      setHasCollectedTests(true);
    }).catch(() => {
      if (requestId === requestIdRef.current) setCollectionFailed(true);
    }).finally(() => {
      if (requestId === requestIdRef.current) setLoadingTests(false);
    });
  };

  const isCurrentProject = stateProjectId === projectId;

  return {
    collectedTests: isCurrentProject ? collectedTests : [],
    loadingTests: isCurrentProject && loadingTests,
    hasCollectedTests: isCurrentProject && hasCollectedTests,
    collectionFailed: isCurrentProject && collectionFailed,
    fetchCollectedTests,
    refreshTestsInBackground,
  };
};
