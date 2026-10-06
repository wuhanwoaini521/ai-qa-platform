import type { TestRun } from '../../types';
import type { WorkspaceRunConfig } from './WorkspaceRunDock';

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
