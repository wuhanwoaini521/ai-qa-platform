import type { AgentTask, TestCase } from '../types';
import { buildWorkspaceHref } from '../app/workspaceContext.ts';

export function dashboardExecutionHref(
  run: { id: string; project_id?: string | null },
  execution: { nodeid: string },
  selectedProjectId?: string | null,
): string | null {
  const projectId = run.project_id ?? selectedProjectId ?? undefined;
  if (!projectId) return null;
  return buildWorkspaceHref({
    projectId,
    runId: run.id,
    nodeId: execution.nodeid,
    file: execution.nodeid.split('::')[0],
    stage: 'result',
    view: 'results',
  });
}

const TERMINAL_TASK_STATUSES = new Set<AgentTask['status']>([
  'COMPLETED', 'FAILED', 'BLOCKED', 'CANCELLED',
]);

export function isExecutableTestCase(testCase: Pick<TestCase, 'binding'>): boolean {
  return testCase.binding?.status === 'ACTIVE' && Boolean(testCase.binding.nodeid);
}

export function isUnfinishedTask(task: Pick<AgentTask, 'status'>): boolean {
  return !TERMINAL_TASK_STATUSES.has(task.status);
}
