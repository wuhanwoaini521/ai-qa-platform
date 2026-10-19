import type {
  FailureRecord,
  FailureRepairAction,
  FailureRepairState,
  LocatorRepairProposal,
} from '../../types';

export type DiagnosisState = FailureRepairState;

export type PrimaryAction =
  | 'RUN_DIAGNOSIS'
  | 'RETRY'
  | 'CREATE_ISSUE_DRAFT'
  | 'REVIEW_REPAIR'
  | 'VERIFY_FIX'
  | 'ANALYZING'
  | 'VERIFYING'
  | 'VERIFIED'
  | 'BLOCKED';

export type EvidenceTab =
  | 'SUMMARY'
  | 'SOURCE'
  | 'STACK'
  | 'BROWSER'
  | 'CONSOLE'
  | 'NETWORK'
  | 'ARTIFACTS';

function hasEvidence(value: unknown): boolean {
  if (value === null || value === undefined || value === '') return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === 'object') return Object.keys(value).length > 0;
  return true;
}

export function normalizeFailureClassification(value?: string | null): string {
  const normalized = (value ?? 'UNKNOWN').trim().toUpperCase();
  if (normalized === 'LOCATOR_ERROR') return 'LOCATOR_CHANGED';
  if (normalized === 'ENVIRONMENT_ERROR') return 'ENVIRONMENT';
  if (normalized === 'TIMING_ISSUE') return 'TIMING';
  if (normalized === 'NETWORK_ERROR') return 'NETWORK';
  if (normalized === 'TEST_DATA_ISSUE') return 'TEST_DATA';
  return normalized || 'UNKNOWN';
}

export function failedLocatorFromFailure(
  failure: Pick<FailureRecord, 'failing_locator' | 'error_message' | 'stack_trace'>,
): string {
  const recorded = failure.failing_locator?.trim();
  if (recorded) return recorded;

  const combined = `${failure.error_message}\n${failure.stack_trace}`;
  // Playwright embeds quoted selectors inside locator("..."). Greedy matching is
  // needed so escaped quotes inside the selector don't look like the outer close.
  const match = combined.match(/locator\((["'])(.*)\1\)/i);
  if (!match) return '';
  try {
    return match[1] === '"' ? JSON.parse(`"${match[2]}"`) : match[2].replace(/\\'/g, "'");
  } catch {
    return match[2].replace(/\\"/g, '"').replace(/\\\\/g, '\\');
  }
}

export function displayedFailureClassification(
  failureClassification: string | null | undefined,
): string {
  return normalizeFailureClassification(failureClassification);
}

export function summarizeFailureError(error = '', failureClassification?: string | null): string {
  if (/BrowserType\.launch/i.test(error) && /spawn\s+EPERM/i.test(error)) {
    return 'browserLaunchEperm';
  }
  const classification = normalizeFailureClassification(failureClassification);
  const timedOut = /TimeoutError|timed out|timeout/i.test(error);
  if (classification === 'LOCATOR_CHANGED' && timedOut) {
    return 'locatorTimeout';
  }
  if (classification === 'ASSERTION_FAILURE' || /AssertionError|assertion failed/i.test(error)) {
    return 'assertion';
  }
  if (classification === 'TIMING' && timedOut) return 'timeout';
  if (/TimeoutError|timed out|timeout/i.test(error)) return 'timeout';
  const firstLine = error.split(/\r?\n/, 1)[0]?.trim();
  if (!firstLine) return 'unknownFailure';
  return firstLine.length > 118 ? `${firstLine.slice(0, 115)}…` : firstLine;
}

export function failureErrorPreview(error = ''): string {
  const detail = error.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).at(-1) ?? '';
  return detail.length > 180 ? `${detail.slice(0, 179)}…` : detail;
}

export function observedRoleLocatorMismatch(
  failure: Pick<FailureRecord, 'failing_locator' | 'error_message' | 'stack_trace' | 'evidence_bundle'>,
): { role: string; expectedName: string; observedNames: string[] } | null {
  const locatorEvidence = [
    failure.failing_locator?.trim(),
    failure.error_message,
    failure.stack_trace,
  ].filter(Boolean).join('\n');
  const roleName = locatorEvidence.match(
    /(?:get_by_role|getByRole)\(\s*['"]([^'"]+)['"]\s*,\s*(?:name\s*=\s*|\{\s*name\s*:\s*)['"]([^'"]+)['"]/i,
  );
  if (!roleName) return null;

  const controls = failure.evidence_bundle?.controls;
  if (!Array.isArray(controls)) return null;
  const role = roleName[1].trim().toLowerCase();
  const expectedName = roleName[2].trim();
  const observedNames = controls.flatMap((item) => {
    if (!item || typeof item !== 'object') return [];
    const control = item as Record<string, unknown>;
    if (String(control.role ?? '').trim().toLowerCase() !== role) return [];
    const name = typeof control.name === 'string' ? control.name.trim() : '';
    return name && name.toLocaleLowerCase() !== expectedName.toLocaleLowerCase() ? [name] : [];
  });
  const uniqueNames = [...new Set(observedNames)].slice(0, 3);
  return uniqueNames.length ? { role, expectedName, observedNames: uniqueNames } : null;
}

export function extractRelevantFrames(stackTrace = '', limit = 3): string[] {
  const frames: string[] = [];
  const seen = new Set<string>();
  for (const line of stackTrace.split(/\r?\n/)) {
    if (/site-packages|node_modules|\.venv[\\/]/i.test(line)) continue;
    const python = line.match(/File ["']([^"']+)["'], line (\d+)/i);
    const pythonCompact = line.match(/([\w./\\-]+\.py):(\d+)/i);
    const js = line.match(/(?:\(|at\s+)([^()\s]+\.[cm]?[jt]sx?):(\d+)(?::\d+)?/i);
    const matched = python ?? pythonCompact ?? js;
    if (!matched) continue;
    const file = matched[1].split(/[\\/]/).pop() ?? matched[1];
    const frame = `${file}:${matched[2]}`;
    if (!seen.has(frame)) {
      seen.add(frame);
      frames.push(frame);
    }
    if (frames.length >= limit) break;
  }
  return frames;
}

export function failureSourceLocation(
  failure: Pick<FailureRecord, 'test_nodeid' | 'stack_trace'> &
    Partial<Pick<FailureRecord, 'source_file' | 'source_line'>>,
): { filePath: string | null; lineNumber: number | null } {
  const recordedFile = failure.source_file?.trim() || null;
  const filePath = recordedFile ?? (failure.test_nodeid.split('::')[0]?.trim() || null);
  // The run finaliser records the failing frame, so the stored location wins over re-reading the stack.
  if (failure.source_line && failure.source_line > 0) {
    return { filePath, lineNumber: failure.source_line };
  }
  const fileName = filePath?.split(/[\\/]/).at(-1)?.toLowerCase();
  const frames = extractRelevantFrames(failure.stack_trace);
  const frame = frames.find((candidate) => {
    const colon = candidate.lastIndexOf(':');
    return colon > 0 && candidate.slice(0, colon).toLowerCase() === fileName;
  }) ?? frames[0];
  const line = frame?.match(/:(\d+)$/)?.[1];
  return { filePath, lineNumber: line ? Number(line) : null };
}

export function failureCodeFrames(
  failure: Pick<FailureRecord, 'test_nodeid' | 'stack_trace'> &
    Partial<Pick<FailureRecord, 'source_file' | 'source_line'>>,
  limit = 3,
): string[] {
  const recordedFile = failure.source_file?.trim();
  const recorded = recordedFile && failure.source_line ? `${recordedFile}:${failure.source_line}` : null;
  const frames = recorded
    ? [recorded, ...extractRelevantFrames(failure.stack_trace)]
    : extractRelevantFrames(failure.stack_trace);
  const seen = new Set<string>();
  return frames
    .filter((frame) => {
      const key = frame.split(/[\\/]/).at(-1)?.toLowerCase() ?? frame;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, limit);
}

export function failureFingerprint(failure: FailureRecord): string | null {
  const combined = `${failure.exception_type}\n${failure.error_message}\n${failure.stack_trace}`;
  if (/BrowserType\.launch/i.test(combined) && /spawn\s+EPERM/i.test(combined)) {
    return 'browser-launch:spawn-eperm';
  }
  const rootFrame = extractRelevantFrames(failure.stack_trace, 1)[0];
  if (rootFrame && /launch|browser|conftest/i.test(rootFrame)) {
    return `stack-root:${rootFrame.toLowerCase()}`;
  }
  return null;
}

export function relatedFailures(
  failures: FailureRecord[],
  selected: FailureRecord,
): FailureRecord[] {
  const fingerprint = failureFingerprint(selected);
  if (!fingerprint) return [];
  return failures.filter(
    (failure) => failureFingerprint(failure) === fingerprint,
  );
}

export function primaryActionForWorkflow(
  state: FailureRepairState,
  actions: FailureRepairAction[],
): PrimaryAction {
  if (actions.includes('START_ANALYSIS')) return 'RUN_DIAGNOSIS';
  if (actions.includes('APPLY')) return 'REVIEW_REPAIR';
  if (actions.includes('VERIFY')) return 'VERIFY_FIX';
  if (actions.includes('RETRY')) return 'RETRY';
  if (actions.includes('CREATE_ISSUE_DRAFT')) return 'CREATE_ISSUE_DRAFT';
  if (state === 'ANALYZING' || state === 'DECIDING' || state === 'VERIFYING_CANDIDATE') return 'ANALYZING';
  if (state === 'VERIFYING_FIX') return 'VERIFYING';
  if (state === 'VERIFIED') return 'VERIFIED';
  return 'BLOCKED';
}

export function availableEvidenceTabs(
  failure: FailureRecord,
  browserEvidence: Record<string, unknown> = {},
): EvidenceTab[] {
  const bundle = failure.evidence_bundle ?? {};
  const tabs: EvidenceTab[] = ['SUMMARY'];
  if (hasEvidence(bundle.source_context) || hasEvidence(bundle.context_paths) || hasEvidence(bundle.source)) {
    tabs.push('SOURCE');
  }
  if (failure.stack_trace?.trim()) tabs.push('STACK');
  if (
    failure.screenshot_path ||
    failure.dom_snapshot_path ||
    hasEvidence(bundle.page_url) ||
    hasEvidence(bundle.browser) ||
    hasEvidence(bundle.element_evidence) ||
    hasEvidence(browserEvidence)
  ) {
    tabs.push('BROWSER');
  }
  if (failure.console_logs?.length || hasEvidence(bundle.console) || hasEvidence(browserEvidence.console_logs)) tabs.push('CONSOLE');
  if (hasEvidence(bundle.network) || hasEvidence(browserEvidence.network_logs)) tabs.push('NETWORK');
  if (
    failure.screenshot_path ||
    failure.trace_path ||
    failure.dom_snapshot_path ||
    hasEvidence(bundle.artifacts) ||
    hasEvidence(browserEvidence.last_frame_artifact_id)
  ) {
    tabs.push('ARTIFACTS');
  }
  return tabs;
}

export function storedRepairProposal(
  value?: Partial<LocatorRepairProposal> | null,
): LocatorRepairProposal | null {
  const oldLocator = value?.old_locator?.trim();
  const proposedLocator = value?.proposed_locator?.trim();
  if (!oldLocator || !proposedLocator || oldLocator === proposedLocator || !value?.strategy) {
    return null;
  }
  return {
    old_locator: oldLocator,
    proposed_locator: proposedLocator,
    confidence: typeof value.confidence === 'number' ? value.confidence : null,
    strategy: value.strategy,
    reason: value.reason ?? '',
    candidate_id: value.candidate_id ?? null,
    provider: value.provider ?? 'local-strategy',
    model: value.model ?? null,
    latency_ms: value.latency_ms ?? null,
    ai_provider: value.ai_provider ?? null,
    ai_fallback_used: value.ai_fallback_used === true,
    verified: value.verified === true,
    verification_reason: value.verification_reason ?? null,
    resolved_classification: value.resolved_classification ?? null,
    decision_summary: value.decision_summary ?? {},
    code_diff: value.code_diff ?? '',
    file_path: value.file_path ?? null,
    applied: value.applied === true,
    execution_trace: value.execution_trace ?? [],
  };
}
