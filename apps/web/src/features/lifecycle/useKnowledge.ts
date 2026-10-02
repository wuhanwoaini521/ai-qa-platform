import { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { ProjectKnowledge } from './types';

export function useKnowledge(projectId: string | null, requirementId?: string, focus?: string) {
  const [graph, setGraph] = useState<ProjectKnowledge | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => setRevision(v => v + 1), []);
  useEffect(() => {
    let disposed = false;
    setGraph(null); setError('');
    if (!projectId) return;
    setLoading(true);
    api.getProjectKnowledge(projectId, {requirement_id: requirementId, focus}).then(value => {
      if (!disposed) setGraph(value);
    }).catch(reason => { if (!disposed) setError(String(reason)); })
      .finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; };
  }, [projectId, requirementId, focus, revision]);
  return {graph, error, loading, reload};
}
