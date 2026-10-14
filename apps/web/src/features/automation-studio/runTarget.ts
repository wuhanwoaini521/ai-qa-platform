/** Prefer an explicit test, then the selected case binding, then the active file. */
export function resolveStudioRunTarget(
  activeTabPath: string | null,
  explicitNodeid?: string,
  caseNodeid?: string,
): string | undefined {
  return explicitNodeid ?? caseNodeid ?? activeTabPath ?? undefined;
}
