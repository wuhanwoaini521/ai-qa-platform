import type { TestRun } from '../../types';
import type { WorkspaceRunConfig } from './WorkspaceRunDock';

const TERMINAL_RUN_STATUSES = new Set<TestRun['status']>(['PASSED', 'FAILED', 'ERROR', 'CANCELLED']);
const TERMINAL_TASK_STATUSES = new Set(['COMPLETED', 'FAILED', 'BLOCKED', 'CANCELLED', 'ERROR']);

export type WorkspaceRunDockStatus =
  | 'idle'
  | 'preparing'
  | 'running'
  | 'failed'
  | 'passed'
  | 'cancelled'
  | 'task-completed'
  | 'task-failed'
  | 'task-blocked'
  | 'task-cancelled';

export interface WorkspaceRunDockState {
  status: WorkspaceRunDockStatus;
  active: boolean;
  failed: boolean;
  passed: boolean;
  taskTerminal: boolean;
}

export function workspaceRunCaseLabel(
  displayId?: string | null,
  caseId?: string | null,
  failureLabel?: string | null,
): string {
  return displayId?.trim() || caseId?.slice(-6).toUpperCase() || failureLabel?.trim() || '';
}

export function workspaceRunDockState(
  runStatus: TestRun['status'] | null,
  taskStatus?: string | null,
): WorkspaceRunDockState {
  let status: WorkspaceRunDockStatus = 'idle';
  if (runStatus === 'QUEUED') status = 'preparing';
  else if (runStatus === 'RUNNING') status = 'running';
  else if (runStatus === 'FAILED' || runStatus === 'ERROR') status = 'failed';
  else if (runStatus === 'PASSED') status = 'passed';
  else if (runStatus === 'CANCELLED') status = 'cancelled';
  else if (taskStatus === 'COMPLETED') status = 'task-completed';
  else if (taskStatus === 'FAILED' || taskStatus === 'ERROR') status = 'task-failed';
  else if (taskStatus === 'BLOCKED') status = 'task-blocked';
  else if (taskStatus === 'CANCELLED') status = 'task-cancelled';
  else if (taskStatus) status = ['PENDING', 'PLANNING', 'QUEUED'].includes(taskStatus) ? 'preparing' : 'running';

  return {
    status,
    active: status === 'preparing' || status === 'running',
    failed: status === 'failed' || status === 'task-failed' || status === 'task-blocked',
    passed: status === 'passed',
    taskTerminal: !runStatus && TERMINAL_TASK_STATUSES.has(taskStatus ?? ''),
  };
}

export function terminalRunStatus(status: TestRun['status']): TestRun['status'] | null {
  return TERMINAL_RUN_STATUSES.has(status) ? status : null;
}

export function repairNoticeForRun(
  status: TestRun['status'],
  hasFailure: boolean,
  hasAiInvocation: boolean,
): 'BLOCKED' | 'NOT_NEEDED' | null {
  if (hasFailure || hasAiInvocation) return null;
  if (status === 'PASSED') return 'NOT_NEEDED';
  if (status === 'FAILED' || status === 'ERROR') return 'BLOCKED';
  return null;
}

export function bindingForSelectedCase<T>(
  record: { caseId: string; binding: T } | null,
  selectedCaseId: string | undefined,
): T | null {
  return record && record.caseId === selectedCaseId ? record.binding : null;
}

export type WorkspaceGoalTarget = 'failure' | 'requirement' | 'case' | 'project';

export function workspaceGoalTarget(
  goal: string,
  context: { failureId?: string | null; requirementId?: string | null; testCaseId?: string | null },
): WorkspaceGoalTarget {
  if (context.failureId) return 'failure';
  if (context.requirementId && /需求|requirement/i.test(goal)) return 'requirement';
  if (context.testCaseId && /用例|\bcase\b/i.test(goal)) return 'case';
  if (/项目|\bproject\b/i.test(goal)) return 'project';
  if (context.requirementId) return 'requirement';
  if (context.testCaseId) return 'case';
  return 'project';
}

export function defaultWorkspaceGoal(context: {
  failureId?: string | null;
  requirementId?: string | null;
  testCaseId?: string | null;
  stage?: string;
  hasAutomation: boolean;
}): string {
  if (context.failureId) return '分析并修复这个失败';
  if (context.requirementId && context.stage === 'requirement') {
    return '帮我把这个需求测试完整。可以自动完成低风险步骤；需要修改代码时让我确认。';
  }
  if (context.testCaseId && ['cases', 'automation'].includes(context.stage ?? '')) {
    return context.hasAutomation
      ? '运行当前用例并分析结果'
      : '为当前用例生成自动化并运行，修改代码前让我确认。';
  }
  if (context.requirementId) {
    return '帮我把这个需求测试完整。可以自动完成低风险步骤；需要修改代码时让我确认。';
  }
  if (context.testCaseId) {
    return context.hasAutomation
      ? '运行当前用例并分析结果'
      : '为当前用例生成自动化并运行，修改代码前让我确认。';
  }
  return '检查这个项目目前还有什么明显测试问题';
}

export function configForRerun(run: TestRun, fallback: WorkspaceRunConfig): WorkspaceRunConfig {
  return {
    environment: run.environment.QA_ENVIRONMENT || fallback.environment,
    region: run.environment.QA_REGION || fallback.region,
    browser: run.browser || fallback.browser,
    workers: run.parallel_workers ?? fallback.workers,
  };
}
