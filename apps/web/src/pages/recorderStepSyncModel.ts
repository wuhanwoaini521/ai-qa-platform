import type { RecorderStep } from '../types';

export type PendingRecorderStepCommand =
  | { command_id: string; action: 'add_step' | 'edit_step'; step: RecorderStep }
  | { command_id: string; action: 'replace_steps'; steps: RecorderStep[]; base_steps_revision?: number }
  | { command_id: string; action: 'delete_step'; id: string }
  | { command_id: string; action: 'reorder'; ids: string[] };

export type RecorderStepSnapshot = {
  type: string;
  steps?: RecorderStep[];
  steps_revision?: number;
  applied_step_command_ids?: string[];
};

export type RecorderStepSnapshotReconciliation = {
  pending: PendingRecorderStepCommand[];
  steps?: RecorderStep[];
  commandsToSend: PendingRecorderStepCommand[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function isStep(value: unknown): value is RecorderStep {
  return isRecord(value) && typeof value.id === 'string';
}

export function createPendingRecorderStepCommand(
  commandId: string,
  action: string,
  payload: Record<string, unknown>,
): PendingRecorderStepCommand | null {
  if ((action === 'add_step' || action === 'edit_step') && isStep(payload.step)) {
    return { command_id: commandId, action, step: payload.step };
  }
  if (action === 'replace_steps' && Array.isArray(payload.steps) && payload.steps.every(isStep)) {
    return { command_id: commandId, action, steps: payload.steps, ...(typeof payload.base_steps_revision === 'number' ? { base_steps_revision: payload.base_steps_revision } : {}) };
  }
  if (action === 'delete_step' && typeof payload.id === 'string') {
    return { command_id: commandId, action, id: payload.id };
  }
  if (action === 'reorder' && Array.isArray(payload.ids) && payload.ids.every((id) => typeof id === 'string')) {
    return { command_id: commandId, action, ids: payload.ids };
  }
  return null;
}

export const PENDING_RECORDER_STEP_COMMANDS_STORAGE_VERSION = 1;

export function serializePendingRecorderStepCommands(pending: PendingRecorderStepCommand[]): string | null {
  if (pending.length === 0) return null;
  return JSON.stringify({ version: PENDING_RECORDER_STEP_COMMANDS_STORAGE_VERSION, commands: pending });
}

export function restorePendingRecorderStepCommands(serialized: string | null): PendingRecorderStepCommand[] {
  if (!serialized) return [];
  let value: unknown;
  try {
    value = JSON.parse(serialized);
  } catch {
    return [];
  }
  if (!isRecord(value) || value.version !== PENDING_RECORDER_STEP_COMMANDS_STORAGE_VERSION || !Array.isArray(value.commands)) {
    return [];
  }

  const restored: PendingRecorderStepCommand[] = [];
  const seenCommandIds = new Set<string>();
  for (const item of value.commands) {
    if (!isRecord(item) || typeof item.command_id !== 'string' || item.command_id.length === 0 || item.command_id.length > 128 || typeof item.action !== 'string') {
      continue;
    }
    if (seenCommandIds.has(item.command_id)) continue;
    const command = createPendingRecorderStepCommand(item.command_id, item.action, item);
    if (!command) continue;
    restored.push(command);
    seenCommandIds.add(command.command_id);
  }
  return restored;
}

export function tryRestorePendingRecorderStepCommands(
  storage: Pick<Storage, 'getItem'>,
  key: string,
): { commands: PendingRecorderStepCommand[]; available: boolean } {
  try {
    return { commands: restorePendingRecorderStepCommands(storage.getItem(key)), available: true };
  } catch {
    return { commands: [], available: false };
  }
}

export function tryPersistPendingRecorderStepCommands(
  storage: Pick<Storage, 'setItem' | 'removeItem'>,
  key: string,
  pending: PendingRecorderStepCommand[],
): boolean {
  try {
    const serialized = serializePendingRecorderStepCommands(pending);
    if (serialized) storage.setItem(key, serialized);
    else storage.removeItem(key);
    return true;
  } catch {
    return false;
  }
}

export function acknowledgeRecorderStepCommand(
  pending: PendingRecorderStepCommand[],
  commandId: string,
): PendingRecorderStepCommand[] {
  return pending.filter((command) => command.command_id !== commandId);
}

export function isRetryableRecorderStepCommandError(action: string | undefined, code: string | undefined): boolean {
  return action === 'replace_steps' && code === 'steps_revision_conflict';
}

export function pendingRecorderStepCommandsToSend(
  pending: PendingRecorderStepCommand[],
  sentCommandIds: ReadonlySet<string>,
): PendingRecorderStepCommand[] {
  return pending.filter((command) => !sentCommandIds.has(command.command_id));
}

export function prepareNextPendingRecorderStepCommand(
  pending: PendingRecorderStepCommand[],
  sentCommandIds: ReadonlySet<string>,
  stepsRevision: number | null,
): { pending: PendingRecorderStepCommand[]; command: PendingRecorderStepCommand | null } {
  if (sentCommandIds.size > 0) return { pending, command: null };
  const command = pendingRecorderStepCommandsToSend(pending, sentCommandIds)[0];
  if (!command) return { pending, command: null };
  if (command.action !== 'replace_steps') return { pending, command };
  if (stepsRevision === null) return { pending, command: null };

  const currentCommand = { ...command, base_steps_revision: stepsRevision };
  return {
    pending: pending.map((item) => item.command_id === command.command_id ? currentCommand : item),
    command: currentCommand,
  };
}

export function reconcilePendingRecorderStepSnapshot(
  snapshot: RecorderStepSnapshot,
  pending: PendingRecorderStepCommand[],
  sentCommandIds: ReadonlySet<string>,
): RecorderStepSnapshotReconciliation {
  let reconciledPending = pending;
  for (const commandId of snapshot.applied_step_command_ids ?? []) {
    reconciledPending = acknowledgeRecorderStepCommand(reconciledPending, commandId);
  }

  if (!Array.isArray(snapshot.steps)) {
    return { pending: reconciledPending, commandsToSend: [] };
  }

  if (typeof snapshot.steps_revision === 'number') {
    reconciledPending = reconciledPending.map((command) =>
      command.action === 'replace_steps' && command.base_steps_revision === undefined
        ? { ...command, base_steps_revision: snapshot.steps_revision }
        : command,
    );
  }

  return {
    pending: reconciledPending,
    steps: applyPendingRecorderStepCommands(snapshot.steps, reconciledPending),
    commandsToSend: pendingRecorderStepCommandsToSend(reconciledPending, sentCommandIds),
  };
}

export function applyPendingRecorderStepCommands(
  serverSteps: RecorderStep[],
  pending: PendingRecorderStepCommand[],
): RecorderStep[] {
  let steps = [...serverSteps];
  for (const command of pending) {
    switch (command.action) {
      case 'add_step':
        if (!steps.some((step) => step.id === command.step.id)) steps = [...steps, command.step];
        break;
      case 'edit_step':
        steps = steps.map((step) => step.id === command.step.id ? command.step : step);
        break;
      case 'replace_steps':
        steps = [...command.steps];
        break;
      case 'delete_step':
        steps = steps.filter((step) => step.id !== command.id);
        break;
      case 'reorder': {
        const orderedIds = new Set(command.ids);
        const byId = new Map(steps.map((step) => [step.id, step]));
        steps = [
          ...command.ids.flatMap((id) => {
            const step = byId.get(id);
            return step ? [step] : [];
          }),
          ...steps.filter((step) => !orderedIds.has(step.id)),
        ];
        break;
      }
    }
  }
  return steps;
}
