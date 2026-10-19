import type { FailureAnalysisRun } from '../../types';

/** Events the analysis runner persists for a terminal run; the persisted status stays the authority. */
export const ANALYSIS_TERMINAL_EVENT_TYPES = ['run.failed', 'run.timeout', 'run.cancelled', 'run.interrupted'];

/**
 * Explains a persisted analysis when no live stream is attached. A completed or still running analysis has
 * nothing to report; a terminal one explains itself through its last terminal event.
 */
export function terminalAnalysisMessage(
  analysis: FailureAnalysisRun,
  failedFallback: string,
  incompleteFallback: string,
): string {
  if (analysis.status === 'COMPLETED' || analysis.status === 'RUNNING') return '';
  const terminal = [...analysis.events].reverse().find((event) => ANALYSIS_TERMINAL_EVENT_TYPES.includes(event.type));
  if (terminal?.message) return terminal.message;
  return analysis.status === 'FAILED' ? failedFallback : incompleteFallback;
}

export type AnalysisStageStatus = 'RUNNING' | 'CANCELLED' | 'FAILED' | 'SUCCEEDED' | 'NOT_STARTED';

/** Chip status for the diagnosis step: the persisted analysis decides, never a local guess. */
export function analysisStageStatus(state: {
  running: boolean;
  cancelled: boolean;
  error: string;
  succeeded: boolean;
}): AnalysisStageStatus {
  if (state.running) return 'RUNNING';
  if (state.cancelled) return 'CANCELLED';
  if (state.error) return 'FAILED';
  return state.succeeded ? 'SUCCEEDED' : 'NOT_STARTED';
}
