export interface QualityMapGapReference {
  item_id: string;
}

export function sourceRequirementId(ids: string[], requirements: Array<Record<string, unknown>>, draft?: string): string | undefined {
  for (const id of ids) {
    const source = requirements.find((item) => item.id === id)?.source_id;
    if (typeof source === 'string' && source && source !== 'PASTED') return source;
  }
  return draft;
}

export function gapsForCoverageRow<T extends QualityMapGapReference>(
  row: Record<string, unknown>,
  gaps: T[],
  featureRequirementIds: string[] = [],
): T[] {
  const featureId = typeof row.feature_id === 'string' ? row.feature_id : '';
  const rowRequirementIds = Array.isArray(row.requirement_ids)
    ? row.requirement_ids.filter((id): id is string => typeof id === 'string')
    : [];
  const requirementIds = new Set([...rowRequirementIds, ...featureRequirementIds]);

  return gaps.filter((gap) =>
    Boolean(featureId && gap.item_id === featureId)
    || [...requirementIds].some((id) => gap.item_id === id || gap.item_id.startsWith(`${id}:`)),
  );
}
