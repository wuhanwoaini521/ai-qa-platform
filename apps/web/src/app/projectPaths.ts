/**
 * Keeps a project-scoped query string in step with a project switch, so `/runs?projectId=A`
 * does not silently drop back to whatever project the shell defaults to.
 */
export function rewriteProjectScope(search: string, projectId: string | null): string {
  const params = new URLSearchParams(search);
  if (!params.has('projectId')) return search;
  if (projectId) params.set('projectId', projectId);
  else params.delete('projectId');
  const next = params.toString();
  return next ? `?${next}` : '';
}

/** Rewrites the project scope while keeping the current project page when it remains valid. */
export function withProjectId(
  pathname: string,
  projectId: string | null,
): string {
  if (!projectId) {
    if (pathname === '/workspace' || pathname.startsWith('/workspace/')) return '/projects';
    if (/^\/projects\/[^/]+(?:\/.*)?$/.test(pathname)) return '/projects';
    return pathname;
  }
  if (pathname === '/workspace' || pathname.startsWith('/workspace/')) {
    return `/workspace/${encodeURIComponent(projectId)}`;
  }
  const match = /^\/projects\/[^/]+(?<rest>\/.*)?$/.exec(pathname);
  if (match) {
    return `/projects/${encodeURIComponent(projectId)}${match.groups?.rest ?? ''}`;
  }
  return pathname;
}
