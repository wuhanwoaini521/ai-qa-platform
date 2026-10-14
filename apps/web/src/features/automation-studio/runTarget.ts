/** Explicit Test Explorer selections win; the Studio toolbar otherwise runs the active file. */
export function resolveStudioRunTarget(
  activeTabPath: string | null,
  explicitNodeid?: string,
  caseNodeid?: string,
): string | undefined {
  return explicitNodeid ?? activeTabPath ?? caseNodeid ?? undefined;
}
