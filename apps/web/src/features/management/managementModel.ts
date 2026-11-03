import type { Requirement, TestCase } from '../../types';

export type ManagementTab = 'requirements' | 'cases' | 'traceability';
export type RequirementSort = 'updated' | 'title' | 'status';
export type CaseSort = 'updated' | 'title' | 'priority';

export const INDEPENDENT_CASES_FILTER = 'independent';
export const REQUIREMENT_STATUSES = ['DRAFT', 'READY', 'ARCHIVED'] as const;
export const AUTOMATION_STATUSES = ['MANUAL', 'DRAFT', 'AUTOMATED'] as const;
export const PRIORITIES = ['P0', 'P1', 'P2', 'P3'] as const;

type RequirementStatus = typeof REQUIREMENT_STATUSES[number];
type AutomationStatus = typeof AUTOMATION_STATUSES[number];
type Priority = typeof PRIORITIES[number];

export function normalizeRequirementStatus(value: string): RequirementStatus | '' {
  return REQUIREMENT_STATUSES.includes(value as RequirementStatus) ? value as RequirementStatus : '';
}

export function normalizeAutomationStatus(value: string): AutomationStatus | '' {
  return AUTOMATION_STATUSES.includes(value as AutomationStatus) ? value as AutomationStatus : '';
}

export function normalizePriority(value: string): Priority | '' {
  return PRIORITIES.includes(value as Priority) ? value as Priority : '';
}

export interface RequirementFilters {
  query: string;
  status: string;
  sort: RequirementSort;
  onlyUnlinked?: boolean;
  onlyLinked?: boolean;
}

export interface TestCaseFilters {
  query: string;
  automationStatus: string;
  priority: string;
  requirementId?: string;
  sort: CaseSort;
}

function compareText(left: string | null | undefined, right: string | null | undefined): number {
  return (left ?? '').localeCompare(right ?? '', undefined, { sensitivity: 'base' });
}

function compareUpdated(left: { updated_at: string; id: string }, right: { updated_at: string; id: string }): number {
  return right.updated_at.localeCompare(left.updated_at) || left.id.localeCompare(right.id);
}

export function getProjectScopedCount(count: number, loadedProjectId: string | null, projectId: string): number | null {
  return loadedProjectId === projectId ? count : null;
}

export function canChangeCaseRequirement(item: Pick<TestCase, 'test_design_id'>): boolean {
  return !item.test_design_id;
}

export function getRequirementDisplayId(item: Requirement): string {
  return item.qa_model?.display_id || item.id.slice(-6).toUpperCase();
}

export function getCaseDisplayId(item: TestCase): string {
  return item.test_model?.display_id || item.id.slice(-6).toUpperCase();
}

export function countCasesForRequirement(requirementId: string, items: TestCase[]): number {
  return items.reduce((count, item) => count + Number(item.requirement_id === requirementId), 0);
}

export function countIndependentCases(items: TestCase[]): number {
  return items.reduce((count, item) => count + Number(!item.requirement_id), 0);
}

export function filterRequirements(items: Requirement[], filters: RequirementFilters, unlinkedRequirementIds?: Set<string>): Requirement[] {
  const query = filters.query.trim().toLocaleLowerCase();
  const status = normalizeRequirementStatus(filters.status);
  return items.filter((item) => {
    if (status && item.status !== status) return false;
    if (filters.onlyUnlinked && !unlinkedRequirementIds?.has(item.id)) return false;
    if (filters.onlyLinked && unlinkedRequirementIds?.has(item.id)) return false;
    if (!query) return true;
    return [item.title, item.description, item.acceptance_criteria, item.external_id, item.qa_model?.display_id]
      .some((value) => value?.toLocaleLowerCase().includes(query));
  }).sort((left, right) => {
    if (filters.sort === 'title') return compareText(left.title, right.title) || left.id.localeCompare(right.id);
    if (filters.sort === 'status') return compareText(left.status, right.status) || compareText(left.title, right.title) || left.id.localeCompare(right.id);
    return compareUpdated(left, right);
  });
}

const PRIORITY_RANK: Record<string, number> = { P0: 0, P1: 1, P2: 2, P3: 3 };

export function filterTestCases(items: TestCase[], filters: TestCaseFilters): TestCase[] {
  const query = filters.query.trim().toLocaleLowerCase();
  const automationStatus = normalizeAutomationStatus(filters.automationStatus);
  const priority = normalizePriority(filters.priority);
  return items.filter((item) => {
    if (filters.requirementId === INDEPENDENT_CASES_FILTER && item.requirement_id) return false;
    if (filters.requirementId && filters.requirementId !== INDEPENDENT_CASES_FILTER && item.requirement_id !== filters.requirementId) return false;
    if (automationStatus && item.automation_status !== automationStatus) return false;
    if (priority && item.priority !== priority) return false;
    if (!query) return true;
    return [getCaseDisplayId(item), item.title, item.preconditions, item.expected_result, ...item.steps, ...item.tags]
      .some((value) => value?.toLocaleLowerCase().includes(query));
  }).sort((left, right) => {
    if (filters.sort === 'title') return compareText(left.title, right.title) || left.id.localeCompare(right.id);
    if (filters.sort === 'priority') return (PRIORITY_RANK[left.priority] ?? 99) - (PRIORITY_RANK[right.priority] ?? 99)
      || compareText(left.title, right.title) || left.id.localeCompare(right.id);
    return compareUpdated(left, right);
  });
}
