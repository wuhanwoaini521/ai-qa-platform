export function canStartRecorderSessionWork(sessionId: string | null, closingSessionId: string | null): sessionId is string {
  return canSendRecorderSessionCommand(sessionId, closingSessionId);
}

export function canSendRecorderSessionCommand(sessionId: string | null, closingSessionId: string | null): sessionId is string {
  return sessionId !== null && sessionId !== closingSessionId;
}

const RECORDER_SESSION_SNAPSHOT_TYPES = new Set(['frame', 'navigating', 'error']);

export function shouldReconcileRecorderCommands(socketReady: boolean, messageType: string): boolean {
  return !socketReady && RECORDER_SESSION_SNAPSHOT_TYPES.has(messageType);
}

export function shouldApplyRecorderSessionCloseCleanup(activeSessionId: string | null, closingSessionId: string): boolean {
  return activeSessionId === closingSessionId;
}

export function canStartRecorderClose(sessionId: string | null, inFlightSessionId: string | null): sessionId is string {
  return sessionId !== null && inFlightSessionId === null;
}

export function shouldConnectRecorderSessionSocket(
  sessionId: string,
  active: boolean,
  closingSessionId: string | null,
  closedSessionId: string | null,
): boolean {
  return active && sessionId !== closingSessionId && sessionId !== closedSessionId;
}

export function isRecorderSessionAlreadyClosed(error: unknown): boolean {
  return error !== null
    && typeof error === 'object'
    && 'status' in error
    && (error as { status?: unknown }).status === 404;
}

const NON_BLOCKING_RECORDER_COMMANDS = new Set(['clear_hover', 'move', 'wheel']);
const RECORDER_NAVIGATION_COMMANDS = new Set(['back', 'click', 'double_click', 'forward', 'navigate', 'press', 'reload']);
const RECORDER_STEP_COMMANDS = new Set(['add_step', 'delete_step', 'edit_step', 'replace_steps', 'reorder']);

export function recorderBrowserCommandBlocksClose(action: string): boolean {
  return !NON_BLOCKING_RECORDER_COMMANDS.has(action);
}

export function recorderBrowserCommandMayNavigate(action: string): boolean {
  return RECORDER_NAVIGATION_COMMANDS.has(action);
}

export function recorderNavigationPendingAfterCommand(pendingCount: number, action: string): number {
  return Math.max(0, pendingCount) + (recorderBrowserCommandMayNavigate(action) ? 1 : 0);
}

const QUEUEABLE_RECORDER_NAVIGATION_COMMANDS = new Set(['back', 'forward', 'navigate', 'reload']);

export type PendingRecorderNavigationCommand = {
  command_id: string;
  action: string;
  payload: Record<string, unknown>;
};

export const PENDING_RECORDER_NAVIGATION_COMMANDS_STORAGE_VERSION = 1;

const recorderNavigationOutboxKey = (sessionId: string): string =>
  `ai-qa.recorder.pending-navigation-commands.v${PENDING_RECORDER_NAVIGATION_COMMANDS_STORAGE_VERSION}.${sessionId}`;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);

export function createPendingRecorderNavigationCommand(
  commandId: string,
  action: string,
  payload: Record<string, unknown>,
): PendingRecorderNavigationCommand | null {
  if (commandId.length === 0 || commandId.length > 128 || !isQueueableRecorderNavigationCommand(action)) return null;
  if (action === 'navigate' && (typeof payload.url !== 'string' || payload.url.length === 0)) return null;
  return { command_id: commandId, action, payload };
}

export function serializePendingRecorderNavigationCommands(pending: PendingRecorderNavigationCommand[]): string | null {
  if (pending.length === 0) return null;
  return JSON.stringify({ version: PENDING_RECORDER_NAVIGATION_COMMANDS_STORAGE_VERSION, commands: pending });
}

export function restorePendingRecorderNavigationCommands(serialized: string | null): PendingRecorderNavigationCommand[] {
  if (!serialized) return [];
  let value: unknown;
  try {
    value = JSON.parse(serialized);
  } catch {
    return [];
  }
  if (!isRecord(value) || value.version !== PENDING_RECORDER_NAVIGATION_COMMANDS_STORAGE_VERSION || !Array.isArray(value.commands)) {
    return [];
  }
  const restored: PendingRecorderNavigationCommand[] = [];
  const seenCommandIds = new Set<string>();
  for (const item of value.commands) {
    if (!isRecord(item) || typeof item.command_id !== 'string' || typeof item.action !== 'string' || !isRecord(item.payload)) continue;
    const command = createPendingRecorderNavigationCommand(item.command_id, item.action, item.payload);
    if (!command || seenCommandIds.has(command.command_id)) continue;
    restored.push(command);
    seenCommandIds.add(command.command_id);
  }
  return restored;
}

export function tryRestorePendingRecorderNavigationCommandsForSession(
  storage: Pick<Storage, 'getItem'>,
  sessionId: string,
): { commands: PendingRecorderNavigationCommand[]; available: boolean } {
  try {
    return { commands: restorePendingRecorderNavigationCommands(storage.getItem(recorderNavigationOutboxKey(sessionId))), available: true };
  } catch {
    return { commands: [], available: false };
  }
}

export function tryPersistPendingRecorderNavigationCommandsForSession(
  storage: Pick<Storage, 'setItem' | 'removeItem'>,
  sessionId: string,
  pending: PendingRecorderNavigationCommand[],
): boolean {
  try {
    const key = recorderNavigationOutboxKey(sessionId);
    const serialized = serializePendingRecorderNavigationCommands(pending);
    if (serialized) storage.setItem(key, serialized);
    else storage.removeItem(key);
    return true;
  } catch {
    return false;
  }
}

export function isQueueableRecorderNavigationCommand(action: string): boolean {
  return QUEUEABLE_RECORDER_NAVIGATION_COMMANDS.has(action);
}

export function prepareNextPendingRecorderNavigationCommand(
  pending: PendingRecorderNavigationCommand[],
  commandInFlight: boolean,
): { pending: PendingRecorderNavigationCommand[]; command: PendingRecorderNavigationCommand | null } {
  return { pending, command: commandInFlight ? null : pending[0] ?? null };
}

export function acknowledgeRecorderNavigationCommand(
  pending: PendingRecorderNavigationCommand[],
  commandId?: string,
): PendingRecorderNavigationCommand[] {
  if (!commandId) return pending.slice(1);
  return pending.filter((command) => command.command_id !== commandId);
}

export function reconcilePendingRecorderNavigationCommands(
  pending: PendingRecorderNavigationCommand[],
  processedCommandIds: string[],
): PendingRecorderNavigationCommand[] {
  const processed = new Set(processedCommandIds);
  return pending.filter((command) => !processed.has(command.command_id));
}

export function recorderNavigationPendingAfterReconnect(queuedNavigationCount: number, snapshotType: string): number {
  const queued = Number.isFinite(queuedNavigationCount) ? Math.max(0, Math.floor(queuedNavigationCount)) : 0;
  return queued + (snapshotType === 'navigating' ? 1 : 0);
}

export function recorderNavigationPendingAfterSnapshot(
  pendingCount: number,
  snapshotType: string,
  settledNavigationCount = 0,
): number {
  const pending = Math.max(0, pendingCount);
  if (snapshotType === 'navigating') return pending;
  if (snapshotType !== 'frame' && snapshotType !== 'error') return pending;
  const settled = Number.isFinite(settledNavigationCount) ? Math.max(0, Math.floor(settledNavigationCount)) : 0;
  return Math.max(0, pending - Math.min(pending, settled));
}

export function recorderNavigationPendingAfterError(pendingCount: number, action: string): number {
  const pending = Math.max(0, pendingCount);
  return recorderBrowserCommandMayNavigate(action) ? Math.max(1, pending) : pending;
}

export function recorderStepSnapshotPendingAfterCommandError(pendingCount: number, action: string): number {
  const pending = Math.max(0, pendingCount);
  return pending + (RECORDER_STEP_COMMANDS.has(action) ? 1 : 0);
}

export function recorderStepSnapshotPendingAfterSnapshot(pendingCount: number, hasCanonicalSteps: boolean): number {
  const pending = Math.max(0, pendingCount);
  return hasCanonicalSteps ? Math.max(0, pending - 1) : pending;
}

export type RecorderErrorRecovery = 'close';

export function isRecorderCloseRetryBlocked(
  sessionId: string | null,
  recovery: RecorderErrorRecovery | null,
  closeAllowed: boolean,
): boolean {
  return sessionId !== null && recovery === 'close' && !closeAllowed;
}

export function canCloseRecorderSession(activity: {
  closePending: boolean;
  pageBusy: boolean;
  taskStarting: boolean;
  taskRunning: boolean;
  agentGoalPending: boolean;
  locatorAnalysisBusy: boolean;
}): boolean {
  return !activity.closePending
    && !activity.pageBusy
    && !activity.taskStarting
    && !activity.taskRunning
    && !activity.agentGoalPending
    && !activity.locatorAnalysisBusy;
}

export function recorderErrorRecoveryFor(
  message: string,
  requestedRecovery?: RecorderErrorRecovery,
  currentRecovery?: RecorderErrorRecovery | null,
  preserveCloseRecovery = false,
): RecorderErrorRecovery | null {
  if (!message) return null;
  if (requestedRecovery) return requestedRecovery;
  return preserveCloseRecovery && currentRecovery === 'close' ? currentRecovery : null;
}
