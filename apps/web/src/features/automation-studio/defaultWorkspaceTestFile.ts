export function defaultWorkspaceTestFile(paths: string[]): string | null {
  return paths
    .map((path) => path.replace(/\\/g, '/'))
    .filter((path) => /(^|\/)tests\/test_[^/]+\.py$/.test(path))
    .sort()[0] ?? null;
}
