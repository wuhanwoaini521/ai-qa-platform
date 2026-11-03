import type { Requirement } from '../../types';
import type { RequirementDocument } from './types';

export function criteriaTextFor(requirement: Requirement): string {
  const criteria = requirement.qa_model?.criteria ?? [];
  const values = criteria.length
    ? criteria.map((item) => item.description)
    : requirement.acceptance_criteria.split(/\r?\n/);
  return values.map((item) => item.trim()).filter(Boolean).join('\n');
}

export function requirementDocumentWithCriteria(
  requirement: Requirement,
  descriptions: string[],
): RequirementDocument {
  const document: RequirementDocument = requirement.qa_model ?? {
    display_id: '',
    criteria: [],
    rules: [],
    constraints: [],
    dependencies: [],
    history: [],
  };
  const usedIds = new Set<string>();
  const matchedIds = new Set<string>();
  const exactMatches = descriptions.map((description) => {
    const existing = document.criteria.find(
      (item) => item.description === description && !matchedIds.has(item.id),
    );
    if (existing) matchedIds.add(existing.id);
    return existing;
  });
  exactMatches.forEach((item) => {
    if (item) usedIds.add(item.id);
  });

  const allIds = new Set(document.criteria.map((item) => item.id));
  let nextId = 1;
  return {
    ...document,
    criteria: descriptions.map((description, index) => {
      let existing = exactMatches[index];
      if (!existing) {
        const positional = document.criteria[index];
        existing = positional && !usedIds.has(positional.id)
          ? positional
          : document.criteria.find((item) => !usedIds.has(item.id));
      }

      let id = existing?.id;
      if (!id) {
        while (allIds.has(`AC-${String(nextId).padStart(3, '0')}`) || usedIds.has(`AC-${String(nextId).padStart(3, '0')}`)) {
          nextId += 1;
        }
        id = `AC-${String(nextId).padStart(3, '0')}`;
        nextId += 1;
      }
      usedIds.add(id);
      return { id, description, negative_required: existing?.negative_required ?? false };
    }),
  };
}
