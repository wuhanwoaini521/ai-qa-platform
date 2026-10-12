import type { TestCase, TestExecution } from '../../types';

export interface ExecutionCaseIdentity {
  caseId: string | null;
  displayId: string | null;
  title: string;
  mapping: 'matched' | 'unmatched' | 'ambiguous';
  mappedCaseLabels: string[];
}

export interface ExecutionFailureReference {
  id: string;
  execution_id: string;
  test_run_id: string;
  title: string;
  message: string;
}

export interface TestExecutionResultRow {
  execution: TestExecution;
  identity: ExecutionCaseIdentity;
  failure: ExecutionFailureReference | null;
}

function caseDisplayId(testCase: TestCase): string {
  return testCase.test_model?.display_id
    || testCase.external_case_id
    || testCase.id.slice(-6).toUpperCase();
}

function nodeName(nodeid: string): string {
  return nodeid.split('::').at(-1) || nodeid;
}

function caseLabel(testCase: TestCase): string {
  return `${caseDisplayId(testCase)} · ${testCase.title}`;
}

export function resolveExecutionCase(nodeid: string, testCases: TestCase[]): ExecutionCaseIdentity {
  const matches = testCases.filter((testCase) => testCase.binding?.nodeid === nodeid);
  if (matches.length === 1) {
    const matched = matches[0];
    return {
      caseId: matched.id,
      displayId: caseDisplayId(matched),
      title: matched.title,
      mapping: 'matched',
      mappedCaseLabels: [],
    };
  }

  if (matches.length > 1) {
    return {
      caseId: null,
      displayId: null,
      title: nodeName(nodeid),
      mapping: 'ambiguous',
      mappedCaseLabels: matches.map(caseLabel),
    };
  }

  return {
    caseId: null,
    displayId: null,
    title: nodeName(nodeid),
    mapping: 'unmatched',
    mappedCaseLabels: [],
  };
}

export function buildTestExecutionRows(
  executions: TestExecution[],
  testCases: TestCase[],
  failures: ExecutionFailureReference[],
): TestExecutionResultRow[] {
  return executions.map((execution) => ({
    execution,
    identity: resolveExecutionCase(execution.nodeid, testCases),
    failure: failures.find((item) =>
      item.execution_id === execution.id && item.test_run_id === execution.run_id,
    ) ?? null,
  }));
}
