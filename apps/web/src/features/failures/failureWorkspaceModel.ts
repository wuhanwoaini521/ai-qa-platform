import type {
  AIFailureDiagnosisResponse,
  FailureAnalysisRun,
  FailureRecord,
  LocatorRepairProposal,
} from '../../types';

export type DiagnosisState =
  | 'NOT_ANALYZED'
  | 'ANALYZING'
  | 'DIAGNOSED'
  | 'REPAIR_PROPOSED'
  | 'REPAIR_APPLIED'
  | 'VERIFYING'
  | 'VERIFIED'
  | 'BLOCKED';

export type PrimaryAction =
  | 'RUN_DIAGNOSIS'
  | 'GENERATE_LOCATOR_REPAIR'
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

export function failedLocatorFromFailure(failure: FailureRecord): string {
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
  diagnosis: AIFailureDiagnosisResponse | null,
): string {
  if (
    diagnosis?.classification?.trim() &&
    diagnosis.provider !== 'fake' &&
    !diagnosis.fallback_used
  ) {
    return normalizeFailureClassification(diagnosis.classification);
  }
  return normalizeFailureClassification(failureClassification);
}

export function summarizeFailureError(error = ''): string {
  if (/BrowserType\.launch/i.test(error) && /spawn\s+EPERM/i.test(error)) {
    return 'browserLaunchEperm';
  }
  if (/TimeoutError|timed out|timeout/i.test(error)) return 'timeout';
  if (/AssertionError|assertion failed/i.test(error)) return 'assertion';
  const firstLine = error.split(/\r?\n/, 1)[0]?.trim();
  if (!firstLine) return 'unknownFailure';
  return firstLine.length > 118 ? `${firstLine.slice(0, 115)}…` : firstLine;
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

export function deriveDiagnosisState(input: {
  diagnosing: boolean;
  diagnosis: AIFailureDiagnosisResponse | null;
  repairProposed: boolean;
  repairApplied: boolean;
  verificationStatus?: string | null;
  verified?: boolean;
  analysis?: FailureAnalysisRun;
  error?: string;
}): DiagnosisState {
  const verification = (input.verificationStatus ?? '').toUpperCase();
  if (verification === 'QUEUED' || verification === 'RUNNING') return 'VERIFYING';
  if (input.verified || verification === 'PASSED') return 'VERIFIED';
  if (input.repairApplied) return 'REPAIR_APPLIED';
  if (input.repairProposed) return 'REPAIR_PROPOSED';
  if (input.diagnosing || input.analysis?.status === 'RUNNING') return 'ANALYZING';
  if (input.diagnosis || input.analysis?.status === 'COMPLETED') return 'DIAGNOSED';
  if (
    input.error ||
    ['FAILED', 'CANCELLED', 'INTERRUPTED'].includes(input.analysis?.status ?? '')
  ) {
    return 'BLOCKED';
  }
  return 'NOT_ANALYZED';
}

export function primaryActionFor(input: {
  state: DiagnosisState;
  classification: string;
  diagnosedClassification?: string;
  hasFailedLocator: boolean;
}): PrimaryAction {
  if (input.state === 'ANALYZING') return 'ANALYZING';
  if (input.state === 'VERIFYING') return 'VERIFYING';
  if (input.state === 'VERIFIED') return 'VERIFIED';
  if (input.state === 'REPAIR_APPLIED') return 'VERIFY_FIX';
  if (input.state === 'REPAIR_PROPOSED') return 'REVIEW_REPAIR';
  if (input.state === 'BLOCKED' || input.state === 'NOT_ANALYZED') {
    return 'RUN_DIAGNOSIS';
  }

  const category = normalizeFailureClassification(
    input.diagnosedClassification ?? input.classification,
  );
  if (category === 'LOCATOR_CHANGED') {
    return input.hasFailedLocator ? 'GENERATE_LOCATOR_REPAIR' : 'BLOCKED';
  }
  if (category === 'PRODUCT_DEFECT') return 'CREATE_ISSUE_DRAFT';
  if (['ENVIRONMENT', 'NETWORK', 'TIMING', 'TEST_DATA'].includes(category)) {
    return 'RETRY';
  }
  return 'BLOCKED';
}

export function availableEvidenceTabs(
  failure: FailureRecord,
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
    hasEvidence(bundle.browser)
  ) {
    tabs.push('BROWSER');
  }
  if (failure.console_logs?.length || hasEvidence(bundle.console)) tabs.push('CONSOLE');
  if (hasEvidence(bundle.network)) tabs.push('NETWORK');
  if (
    failure.screenshot_path ||
    failure.trace_path ||
    failure.dom_snapshot_path ||
    hasEvidence(bundle.artifacts)
  ) {
    tabs.push('ARTIFACTS');
  }
  return tabs;
}

export function repairEligibility(input: {
  diagnosis: AIFailureDiagnosisResponse | null;
  failure: FailureRecord;
  trustedAnalysis?: boolean;
}): { eligible: boolean; reason: string } {
  const classification = normalizeFailureClassification(
    input.diagnosis?.classification ??
      input.failure.failure_kind ??
      input.failure.classification,
  );
  if (classification !== 'LOCATOR_CHANGED') {
    return { eligible: false, reason: 'classification' };
  }
  if (!failedLocatorFromFailure(input.failure)) {
    return { eligible: false, reason: 'missing-locator' };
  }
  if (!input.failure.error_message.trim() && !input.failure.stack_trace.trim()) {
    return { eligible: false, reason: 'missing-evidence' };
  }
  if (!input.diagnosis && !input.trustedAnalysis) {
    return { eligible: false, reason: 'not-diagnosed' };
  }
  if (
    input.diagnosis &&
    (input.diagnosis.provider === 'fake' || input.diagnosis.fallback_used)
  ) {
    return { eligible: false, reason: 'untrusted-diagnosis' };
  }
  return { eligible: true, reason: 'eligible' };
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
    code_diff: value.code_diff ?? '',
    file_path: value.file_path ?? null,
    applied: value.applied === true,
    execution_trace: value.execution_trace ?? [],
  };
}
