/** The Studio toolbar runs the active file; explicit Test Explorer actions run one nodeid. */
export function resolveStudioRunTarget(
  activeTabPath: string | null,
  explicitNodeid?: string,
): string | undefined {
  return explicitNodeid ?? activeTabPath ?? undefined;
}
