export type WorkspaceStage =
  | 'requirement'
  | 'cases'
  | 'automation'
  | 'result'
  | 'failure';

export type WorkspaceView = 'requirement' | 'cases' | 'code' | 'browser' | 'debug' | 'results';

/**
 * Shared cross-surface context. Entity IDs in the URL remain the source of truth;
 * this object is only a typed projection for links and page composition.
 */
export interface WorkspaceContext {
  projectId?: string;
  requirementId?: string;
  testDesignId?: string;
  testCaseId?: string;
  automationBindingId?: string;
  taskId?: string;
  runId?: string;
  parentRunId?: string;
  failureId?: string;
  browserSessionId?: string;
  file?: string;
  lineNumber?: number;
  nodeId?: string;
  stepId?: string;
  stage?: WorkspaceStage;
  view?: WorkspaceView;
  returnTo?: 'workspace';
}

const PARAMS: ReadonlyArray<[keyof WorkspaceContext, string]> = [
  ['requirementId', 'requirementId'],
  ['testDesignId', 'testDesignId'],
  ['testCaseId', 'caseId'],
  ['automationBindingId', 'bindingId'],
  ['taskId', 'taskId'],
  ['runId', 'runId'],
  ['parentRunId', 'parentRunId'],
  ['failureId', 'failureId'],
  ['browserSessionId', 'browserSessionId'],
  ['nodeId', 'nodeid'],
  ['stepId', 'step'],
  ['stage', 'stage'],
  ['view', 'view'],
  ['returnTo', 'returnTo'],
];

const CONTEXT_KEYS = new Set([
  ...PARAMS.map(([, key]) => key),
  'testCaseId',
  'file',
  'line',
  'projectId',
  'parentRunId',
]);

function paramsFrom(search: string | URLSearchParams): URLSearchParams {
  if (search instanceof URLSearchParams) return new URLSearchParams(search);
  return new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
}

function nonEmpty(params: URLSearchParams, key: string): string | undefined {
  const value = params.get(key)?.trim();
  return value || undefined;
}

export function readWorkspaceContext(
  search: string | URLSearchParams,
  fallbackProjectId?: string | null,
): WorkspaceContext {
  const params = paramsFrom(search);
  const context: WorkspaceContext = {
    projectId: nonEmpty(params, 'projectId') ?? fallbackProjectId ?? undefined,
    requirementId: nonEmpty(params, 'requirementId'),
    testDesignId: nonEmpty(params, 'testDesignId'),
    testCaseId: nonEmpty(params, 'caseId') ?? nonEmpty(params, 'testCaseId'),
    automationBindingId: nonEmpty(params, 'bindingId'),
    taskId: nonEmpty(params, 'taskId'),
    runId: nonEmpty(params, 'runId') ?? nonEmpty(params, 'parentRunId'),
    parentRunId: nonEmpty(params, 'parentRunId'),
    failureId: nonEmpty(params, 'failureId'),
    browserSessionId: nonEmpty(params, 'browserSessionId'),
    file: nonEmpty(params, 'file'),
    nodeId: nonEmpty(params, 'nodeid') ?? nonEmpty(params, 'nodeId'),
    stepId: nonEmpty(params, 'step'),
    returnTo: params.get('returnTo') === 'workspace' ? 'workspace' : undefined,
  };

  const stage = params.get('stage');
  if (
    stage === 'requirement' ||
    stage === 'cases' ||
    stage === 'automation' ||
    stage === 'result' ||
    stage === 'failure'
  ) {
    context.stage = stage;
  }

  const view = params.get('view');
  if (
    view === 'requirement' ||
    view === 'cases' ||
    view === 'code' ||
    view === 'browser' ||
    view === 'debug' ||
    view === 'results'
  ) {
    context.view = view;
  } else if (context.stage) {
    context.view = context.stage === 'automation'
      ? 'code'
      : context.stage === 'result' || context.stage === 'failure'
        ? 'results'
        : context.stage;
  }

  const rawLine = Number(params.get('line'));
  if (Number.isSafeInteger(rawLine) && rawLine > 0) context.lineNumber = rawLine;

  return context;
}

export function writeWorkspaceContext(
  search: string | URLSearchParams,
  context: WorkspaceContext,
): URLSearchParams {
  const params = paramsFrom(search);
  for (const key of CONTEXT_KEYS) params.delete(key);

  if (context.projectId) params.set('projectId', context.projectId);
  for (const [field, key] of PARAMS) {
    const value = context[field];
    if (typeof value === 'string' && value.trim()) params.set(key, value.trim());
  }
  if (context.file?.trim()) params.set('file', context.file.trim());
  if (context.lineNumber && Number.isSafeInteger(context.lineNumber) && context.lineNumber > 0) {
    params.set('line', String(context.lineNumber));
  }
  return params;
}

function queryFor(context: WorkspaceContext): string {
  const params = writeWorkspaceContext('', context);
  const query = params.toString();
  return query ? `?${query}` : '';
}

export function buildWorkspaceHref(context: WorkspaceContext): string {
  const path = context.projectId
    ? `/workspace/${encodeURIComponent(context.projectId)}`
    : '/workspace';
  return `${path}${queryFor(context)}`;
}

export function buildWorkflowHref(context: WorkspaceContext): string {
  if (!context.taskId && !context.runId) return `/runs/tasks${queryFor(context)}`;

  const workspace = buildWorkspaceHref({
    ...context,
    stage: context.stage ?? (context.failureId ? 'failure' : 'result'),
    view: context.view ?? 'results',
  });
  return `${workspace}${workspace.includes('?') ? '&' : '?'}panel=runtime`;
}

export function buildStudioHref(context: WorkspaceContext): string {
  return buildWorkspaceHref({
    ...context,
    stage: 'automation',
    view: context.failureId ? 'debug' : 'code',
  });
}
