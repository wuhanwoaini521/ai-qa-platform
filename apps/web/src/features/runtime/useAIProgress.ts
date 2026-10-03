import { useEffect, useRef, useState } from 'react';
import type { AITraceEvent } from '../../types';
import { appendProgress } from './progressModel';
export function useAIProgress(scope: string | null) {
  const [events, setEvents] = useState<AITraceEvent[]>([]);
  const [error, setError] = useState('');
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    setEvents([]);
    setError('');
    return () => controller.current?.abort();
  }, [scope]);
  async function execute<T>(
    operation: (
      onEvent: (event: AITraceEvent) => void,
      signal: AbortSignal,
    ) => Promise<T>,
  ): Promise<T> {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    setEvents([]);
    setError('');
    try {
      const value = await operation((event) => {
        if (!current.signal.aborted)
          setEvents((events) => appendProgress(events, event));
      }, current.signal);
      if (current.signal.aborted)
        throw new DOMException('Aborted', 'AbortError');
      return value;
    } catch (reason) {
      if (!current.signal.aborted) setError(String(reason));
      throw reason;
    }
  }
  return { events, error, execute, cancel: () => controller.current?.abort() };
}
