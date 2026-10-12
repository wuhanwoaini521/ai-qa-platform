import type { TestCase } from '../../types';

export interface TestCaseSelectionOption {
  id: string;
  label: string;
}

export interface TestCaseSelectionModel {
  kind: 'static' | 'select';
  selectedId: string;
  displayId: string;
  title: string;
  options: TestCaseSelectionOption[];
}

function displayId(testCase: TestCase): string {
  return testCase.test_model?.display_id
    || testCase.external_case_id
    || testCase.id.slice(-6).toUpperCase();
}

export function buildTestCaseSelectionModel(
  testCases: TestCase[],
  selected: TestCase | null,
): TestCaseSelectionModel | null {
  if (testCases.length === 0) return null;

  return {
    kind: selected && testCases.length === 1 ? 'static' : 'select',
    selectedId: selected?.id ?? '',
    displayId: selected ? displayId(selected) : '',
    title: selected?.title ?? '',
    options: testCases.map((testCase) => ({
      id: testCase.id,
      label: `${displayId(testCase)} · ${testCase.title}`,
    })),
  };
}
