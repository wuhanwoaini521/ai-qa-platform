import { useEffect, useState } from 'react';
import { api } from '../../../api/client';
import { errorText } from '../errorText';
import { useRunStore } from '../../runs/useRunStore';
import type { RunnerType } from '../../../types';

interface UseRunExecutionOptions {
  projectId: string | null;
  /** Falls back to the active file when no explicit test nodeid is given. */
  activeTabPath: string | null;
  onNavigateToRuns?: (runId?: string) => void;
  retryContext?: { failureId: string; runId: string };
}

export const useRunExecution = ({
  projectId,
  activeTabPath,
  onNavigateToRuns,
  retryContext,
}: UseRunExecutionOptions) => {
  // Execution from Studio
  const [runningTest, setRunningTest] = useState<boolean>(false);
  const [lastRunResult, setLastRunResult] = useState<string | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const live = useRunStore(activeRunId);
  useEffect(() => {
    setActiveRunId(null);
    setRunningTest(false);
    setLastRunResult(null);
  }, [projectId]);
  useEffect(() => {
    if (live.run) setLastRunResult(`Run #${live.run.id.slice(0, 8)} · ${live.run.status} · ${live.run.passed}/${live.run.total} passed`);
  }, [live.run]);

  // Run a specific test nodeid or the active file
  const runExecution = async (targetNodeid?: string) => {
    if (
      !projectId ||
      runningTest ||
      (live.run && ['RUNNING', 'QUEUED'].includes(live.run.status))
    )
      return;
    try {
      setRunningTest(true);
      setLastRunResult('Dispatching execution run...');
      const target = targetNodeid
        ? [targetNodeid]
        : activeTabPath
          ? [activeTabPath]
          : undefined;

      const originalRun = retryContext ? await api.getTestRun(retryContext.runId) : null;
      const run = await api.createTestRun({
        project_id: projectId,
        workspace_id: projectId,
        nodeids: target ?? [],
        requested_by: 'Automation Studio',
        ...(retryContext && originalRun ? {
          parent_run_id: originalRun.id,
          origin_failure_id: retryContext.failureId,
          environment: originalRun.environment,
          browser: originalRun.browser,
          runner_type: originalRun.runner_type as RunnerType | undefined,
          runner_profile_id: originalRun.runner_profile_id,
        } : {}),
      });

      setLastRunResult(
        `Run #${run.id.slice(0, 8)} started with status: ${run.status}`,
      );
      setActiveRunId(run.id);
    } catch (err) {
      setLastRunResult(`Execution error: ${errorText(err)}`);
    } finally {
      setRunningTest(false);
    }
  };

  return {
    runningTest:
      runningTest ||
      !!(live.run && ['RUNNING', 'QUEUED'].includes(live.run.status)),
    lastRunResult,
    runExecution,
    activeRunId,
    onNavigateToRuns,
  };
};
