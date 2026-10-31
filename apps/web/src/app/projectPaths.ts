const PROJECT_BOUND_QUERY_KEYS = [
  'requirementId',
  'testDesignId',
  'caseId',
  'testCaseId',
  'bindingId',
  'taskId',
  'runId',
  'parentRunId',
  'failureId',
  'browserSessionId',
  'file',
  'line',
  'nodeid',
  'nodeId',
  'node',
  'step',
  'target',
  'panel',
] as const;

export function clearProjectBoundContext(search: string | URLSearchParams): URLSearchParams {
  const params = new URLSearchParams(search);
  for (const key of PROJECT_BOUND_QUERY_KEYS) params.delete(key);
  return params;
}

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
    let rest = match.groups?.rest ?? '';
    if (/^\/requirements\/[^/]+\/?$/.test(rest)) rest = '/requirements';
    else if (/^\/test-cases\/[^/]+\/?$/.test(rest)) rest = '/test-cases';
    else if (/^\/studio\/file(?:\/|$)/.test(rest)) rest = '/studio';
    return `/projects/${encodeURIComponent(projectId)}${rest}`;
  }
  return pathname;
}
