import type { TestRunCreate } from '../types';

export interface RecorderRunConfig {
  environment: string;
  region: string;
  browser: string;
  workers: number;
}

type RecorderRunStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
type RecorderRunIntent = Omit<TestRunCreate, 'idempotency_key'>;

const STORAGE_PREFIX = 'ai-qa:recorder-run:';
const volatileRunKeys = new Map<string, { signature: string; key: string }>();

export function recorderRunConfigFields(config?: RecorderRunConfig): Pick<TestRunCreate, 'browser' | 'environment' | 'parallel_workers'> {
  if (!config) return {};
  return {
    browser: config.browser,
    environment: {
      QA_ENVIRONMENT: config.environment,
      QA_REGION: config.region,
    },
    parallel_workers: config.workers,
  };
}

function createRunKey(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') return globalThis.crypto.randomUUID();
  return `recorder-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function getSessionStorage(): RecorderRunStorage | undefined {
  try {
    return globalThis.sessionStorage;
  } catch {
    return undefined;
  }
}

function storageKey(scope: string): string {
  return `${STORAGE_PREFIX}${encodeURIComponent(scope)}`;
}

export function recorderRunIdempotencyKey(
  scope: string,
  intent: RecorderRunIntent,
  storage?: RecorderRunStorage,
  createKey: () => string = createRunKey,
): string {
  const activeStorage = storage ?? getSessionStorage();
  const signature = JSON.stringify(intent);
  const memoryKey = storageKey(scope);
  const createOrReuseInMemory = (): string => {
    const previous = volatileRunKeys.get(memoryKey);
    if (previous?.signature === signature) return previous.key;
    const nextKey = createKey();
    volatileRunKeys.set(memoryKey, { signature, key: nextKey });
    return nextKey;
  };
  if (!activeStorage) return createOrReuseInMemory();

  const key = storageKey(scope);
  try {
    const stored = JSON.parse(activeStorage.getItem(key) ?? 'null') as { signature?: string; key?: string } | null;
    if (stored?.signature === signature && stored.key) {
      volatileRunKeys.set(memoryKey, { signature, key: stored.key });
      return stored.key;
    }

    const nextKey = createKey();
    volatileRunKeys.set(memoryKey, { signature, key: nextKey });
    activeStorage.setItem(key, JSON.stringify({ signature, key: nextKey }));
    return nextKey;
  } catch {
    return createOrReuseInMemory();
  }
}

export function clearRecorderRunIdempotencyKey(scope: string, storage?: RecorderRunStorage): void {
  volatileRunKeys.delete(storageKey(scope));
  try {
    (storage ?? getSessionStorage())?.removeItem(storageKey(scope));
  } catch {
    // Storage can be disabled by browser policy; the Run request itself remains valid.
  }
}
