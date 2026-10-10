export interface QualityMapGapReference {
  item_id: string;
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
