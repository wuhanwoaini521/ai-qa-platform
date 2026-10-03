import { useMemo, useState } from 'react';
import { AIExecutionTimeline } from '../../components/AIExecutionTimeline';
import type { RuntimeSnapshot } from '../../types/runtime';
import { runtimeActive } from './runtimeModel';
import {
  TRACE_FILTERS,
  filterTrace,
  traceAdapter,
  type TraceFilter,
} from './traceModel';
export function RuntimeTrace({
  snapshot,
  selectedStepId,
  onSelect,
}: {
  snapshot: RuntimeSnapshot;
  selectedStepId: string | null;
  onSelect: (id: string) => void;
}) {
  const [filter, setFilter] = useState<TraceFilter>('All');
  const [errors, setErrors] = useState(false);
  const events = useMemo(
    () =>
      filterTrace(snapshot.events, filter, errors, selectedStepId).map(
        traceAdapter,
      ),
    [snapshot.events, filter, errors, selectedStepId],
  );
  return (
    <div className="rt-trace">
      <div className="rt-toolbar" role="group" aria-label="Trace 筛选">
        {TRACE_FILTERS.map((key) => (
          <button
            key={key}
            aria-pressed={filter === key}
            onClick={() => setFilter(key)}
          >
            {key}
          </button>
        ))}
        <label>
          <input
            type="checkbox"
            checked={errors}
            onChange={(event) => setErrors(event.target.checked)}
          />
          仅错误
        </label>
      </div>
      {!events.length ? (
        <p className="rt-empty">当前筛选下没有已记录的事件</p>
      ) : (
        <AIExecutionTimeline
          events={events}
          running={runtimeActive(snapshot.status)}
          runtime
          selectedStepId={selectedStepId}
          onSelectStep={onSelect}
        />
      )}
    </div>
  );
}
