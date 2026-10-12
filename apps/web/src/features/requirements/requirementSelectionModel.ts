import type { Requirement } from '../../types';

export interface RequirementSelectionOption {
  id: string;
  label: string;
}

export interface RequirementSelectionModel {
  kind: 'single' | 'multiple';
  displayId: string;
  title: string;
  selectedId: string;
  options: RequirementSelectionOption[];
}

function displayId(requirement: Requirement): string {
  return requirement.qa_model?.display_id || requirement.id.slice(-6).toUpperCase();
}

export function buildRequirementSelectionModel(
  requirements: Requirement[],
  selected: Requirement | null,
): RequirementSelectionModel | null {
  if (!selected) return null;

  return {
    kind: requirements.length > 1 ? 'multiple' : 'single',
    displayId: displayId(selected),
    title: selected.title,
    selectedId: selected.id,
    options: requirements.map((requirement) => ({
      id: requirement.id,
      label: `${displayId(requirement)} · ${requirement.title}`,
    })),
  };
}
