import { useSyncExternalStore } from 'react';
import { api, EventStreamError } from '../../api/client';
import { createRunStore, emptyRunState } from './runStore';

const stores = new Map<string, ReturnType<typeof createRunStore>>();
const idle = emptyRunState();
const empty = {
  getSnapshot: () => idle,
  subscribe: () => () => {},
  refresh: async () => {},
};
function getStore(runId: string | null) {
  if (!runId) return empty;
  let store = stores.get(runId);
  if (!store) {
    // Keep at most 32 inactive run snapshots; never evict a subscribed instance.
    for (const [id, cached] of stores) {
      if (stores.size < 32) break;
      if (!cached.isActive()) stores.delete(id);
    }
    store = createRunStore(runId, {
      getRun: api.getTestRun,
      stream: api.streamRunEvents,
      permanentError: (reason) =>
        reason instanceof EventStreamError && !reason.retryable,
    });
    const shared = store;
    const subscribe = shared.subscribe;
    shared.subscribe = (listener) => {
      const unsubscribe = subscribe(listener);
      return () => {
        unsubscribe();
        queueMicrotask(() => {
          if (!shared.isActive() && stores.get(runId) === shared)
            stores.delete(runId);
        });
      };
    };
    stores.set(runId, store);
  }
  return store;
}

/** The sole TestRun live state layer, shared across Runtime, Runs and Studio. */
export function useRunStore(runId: string | null) {
  const store = getStore(runId);
  const state = useSyncExternalStore(
    store.subscribe,
    store.getSnapshot,
    store.getSnapshot,
  );
  return { ...state, refresh: store.refresh };
}
