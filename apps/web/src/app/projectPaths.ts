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
