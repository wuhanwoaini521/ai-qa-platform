import type { TestCase } from '../../types';

type CoverageCase = Pick<TestCase, 'requirement_id' | 'binding'>;

export interface AutomationCoverageCount {
  total: number;
  automated: number;
  percentage: number;
}

export const hasActiveAutomationBinding = (testCase: CoverageCase): boolean =>
  testCase.binding?.status === 'ACTIVE' &&
  typeof testCase.binding.nodeid === 'string' &&
  testCase.binding.nodeid.trim().length > 0;

const summarizeCases = (cases: CoverageCase[]): AutomationCoverageCount => {
  const automated = cases.filter(hasActiveAutomationBinding).length;
  return {
    total: cases.length,
    automated,
    percentage: cases.length ? Math.round((automated / cases.length) * 1000) / 10 : 0,
  };
};

export const summarizeAutomationCoverage = (cases: CoverageCase[]) => {
  const byRequirement = new Map<string, CoverageCase[]>();
  for (const testCase of cases) {
    if (!testCase.requirement_id) continue;
    const group = byRequirement.get(testCase.requirement_id) ?? [];
    group.push(testCase);
    byRequirement.set(testCase.requirement_id, group);
  }

  return {
    ...summarizeCases(cases),
    byRequirement: new Map(
      [...byRequirement].map(([id, requirementCases]) => [id, summarizeCases(requirementCases)]),
    ),
  };
};
