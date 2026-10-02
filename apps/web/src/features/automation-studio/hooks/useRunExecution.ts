import { useEffect, useState } from 'react';
import { api } from '../../../api/client';
import { errorText } from '../errorText';

interface UseRunExecutionOptions {
  projectId: string | null;
  /** Falls back to the active file when no explicit test nodeid is given. */
  activeTabPath: string | null;
  onNavigateToRuns?: (runId?: string) => void;
}

export const useRunExecution = ({ projectId, activeTabPath, onNavigateToRuns }: UseRunExecutionOptions) => {
  // Execution from Studio
  const [runningTest, setRunningTest] = useState<boolean>(false);
  const [lastRunResult, setLastRunResult] = useState<string | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  useEffect(()=>{setActiveRunId(null);setRunningTest(false);setLastRunResult(null);},[projectId]);
  useEffect(()=>{
    if(!activeRunId)return;let disposed=false;
    const sync=async()=>{try{const value=await api.getTestRun(activeRunId);if(!disposed){setRunningTest(['RUNNING','QUEUED'].includes(value.status));if(!['RUNNING','QUEUED'].includes(value.status))window.clearInterval(timer);}}catch{if(!disposed)setRunningTest(false);}};
    const timer=window.setInterval(()=>{void sync();},1500);void sync();return()=>{disposed=true;window.clearInterval(timer);};
  },[activeRunId]);

  // Run a specific test nodeid or the active file
  const runExecution = async (targetNodeid?: string) => {
    if (!projectId || runningTest) return;
    try {
      setRunningTest(true);
      setLastRunResult('Dispatching execution run...');
      const target = targetNodeid
        ? [targetNodeid]
        : activeTabPath
        ? [activeTabPath]
        : undefined;

      const run = await api.createTestRun({
        project_id: projectId,
        workspace_id: projectId,
        nodeids: target ?? [],
        requested_by: 'Automation Studio',
      });

      setLastRunResult(`Run #${run.id.slice(0, 8)} started with status: ${run.status}`);
      setActiveRunId(run.id);
    } catch (err) {
      setLastRunResult(`Execution error: ${errorText(err)}`);
    } finally {
      setRunningTest(false);
    }
  };

  return { runningTest, lastRunResult, runExecution, activeRunId, onNavigateToRuns };
};
