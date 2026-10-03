import { useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { RuntimeSnapshot } from '../../types/runtime';
import { useRunStore } from '../runs/useRunStore';
import { runtimeActive } from './runtimeModel';
import { reconcileSnapshot } from './reconcileSnapshot';

export function useRuntimeSnapshot(
  kind: 'task' | 'run',
  id: string,
  revision?: string,
) {
  const [snapshot, setSnapshot] = useState<RuntimeSnapshot | null>(null);
  const [error, setError] = useState('');
  const [connection, setConnection] = useState('connecting');
  const refresh = useRef<() => void>(() => {});
  const live = useRunStore(kind === 'run' ? id : null);
  useEffect(() => {
    let disposed = false,
      fetching = false,
      dirty = false;
    let close = () => {};
    let terminal = false;
    const sync = async () => {
      if (disposed) return;
      if (fetching) {
        dirty = true;
        return;
      }
      fetching = true;
      try {
        const value = await api.getRuntime(kind, id);
        if (disposed) return;
        setSnapshot((previous) => reconcileSnapshot(previous, value));
        setError('');
        terminal = !runtimeActive(value.status);
        if (terminal) {
          close();
          setConnection('idle');
        }
      } catch (reason) {
        if (!disposed) setError(String(reason));
      } finally {
        fetching = false;
        if (dirty && !disposed) {
          dirty = false;
          void sync();
        }
      }
    };
    refresh.current = () => {
      void sync();
    };
    if (kind === 'task')
      close = api.streamTaskEvents(
        id,
        () => {
          if (!disposed) {
            setConnection('connected');
            void sync();
          }
        },
        (reason) => {
          if (!disposed) {
            setConnection('reconnecting');
            setError(String(reason));
          }
        },
      );
    void sync();
    const timer = window.setInterval(() => {
      if (!terminal) void sync();
    }, 1500);
    return () => {
      disposed = true;
      close();
      window.clearInterval(timer);
      refresh.current = () => {};
    };
  }, [kind, id, revision]);
  useEffect(() => {
    refresh.current();
  }, [live.run]);
  return {
    snapshot: snapshot?.id === id && snapshot.kind === kind ? snapshot : null,
    error,
    connection: kind === 'run' ? live.streamStatus : connection,
    refresh: () => refresh.current(),
    live,
  };
}
