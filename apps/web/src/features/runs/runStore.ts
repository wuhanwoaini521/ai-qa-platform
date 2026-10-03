import type { TestBrowserSession, TestExecution, TestRun } from '../../types';

export const MAX_TRACE_EVENTS = 500;
export const MAX_LOG_ENTRIES = 200;
export const MAX_LOG_CHARACTERS = 20000;
export const MAX_NETWORK_EVENTS = 100;
export const MAX_CONSOLE_EVENTS = 100;
export const MAX_BROWSER_STEPS = 100;
export const MAX_BROWSER_SESSIONS = 32;
export type ConnectionState =
  'idle' | 'connecting' | 'connected' | 'reconnecting' | 'failed';
export type RunEvent = Record<string, unknown> & { type: string };
export interface RunState {
  run: TestRun | null;
  sessions: TestBrowserSession[];
  frames: Record<string, string>;
  events: RunEvent[];
  logs: string[];
  streamStatus: ConnectionState;
  error: string;
  seenIds: string[];
}
export const emptyRunState = (): RunState => ({
  run: null,
  sessions: [],
  frames: {},
  events: [],
  logs: [],
  streamStatus: 'idle',
  error: '',
  seenIds: [],
});
export const isTerminal = (status?: string) =>
  !!status && !['QUEUED', 'RUNNING'].includes(status);
const record = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
const number = (value: unknown, fallback: number) =>
  typeof value === 'number' && Number.isFinite(value) ? value : fallback;
const bounds = {
  network_logs: MAX_NETWORK_EVENTS,
  console_logs: MAX_CONSOLE_EVENTS,
  recent_steps: MAX_BROWSER_STEPS,
};

/** Align two bounded observations of the same append-only log without repeating their overlap. */
export function mergeObservedLog(persisted: string, observed: string): string {
  if (!observed || persisted.includes(observed))
    return persisted.slice(-MAX_LOG_CHARACTERS);
  if (!persisted || observed.includes(persisted))
    return observed.slice(-MAX_LOG_CHARACTERS);
  const prefix = Array<number>(observed.length).fill(0);
  for (let index = 1, matched = 0; index < observed.length; index++) {
    while (matched && observed[index] !== observed[matched])
      matched = prefix[matched - 1];
    if (observed[index] === observed[matched]) matched++;
    prefix[index] = matched;
  }
  let matched = 0;
  for (let index = 0; index < persisted.length; index++) {
    while (matched && persisted[index] !== observed[matched])
      matched = prefix[matched - 1];
    if (persisted[index] === observed[matched]) matched++;
    if (matched === observed.length && index < persisted.length - 1)
      matched = prefix[matched - 1];
  }
  return (persisted + observed.slice(matched)).slice(-MAX_LOG_CHARACTERS);
}
function boundedSession(session: TestBrowserSession): TestBrowserSession {
  const evidence = { ...session.page_evidence };
  for (const [key, limit] of Object.entries(bounds))
    if (Array.isArray(evidence[key]))
      evidence[key] = evidence[key].slice(-limit);
  return { ...session, page_evidence: evidence };
}
function keepFrames(
  frames: Record<string, string>,
  sessions: TestBrowserSession[],
) {
  const ids = new Set(sessions.map((session) => session.browser_session_id));
  return Object.fromEntries(
    Object.entries(frames).filter(([id]) => ids.has(id)),
  );
}

function mergeBrowserEntries(persisted: unknown[], live: unknown[]) {
  if (
    ![...persisted, ...live].every(
      (entry) => typeof record(entry).timestamp === 'string',
    )
  )
    return live.length > persisted.length ? live : persisted;
  const entries = new Map(
    [...persisted, ...live].map((entry) => [JSON.stringify(entry), entry]),
  );
  return [...entries.values()].sort(
    (a, b) =>
      Date.parse(String(record(a).timestamp)) -
      Date.parse(String(record(b).timestamp)),
  );
}
/** Reconcile durable evidence without erasing transient telemetry during reconnect. */
export function reconcileRun(state: RunState, snapshot: TestRun, preserveLiveLog = false): RunState {
  const run =
    isTerminal(state.run?.status) && !isTerminal(snapshot.status)
      ? ({ ...snapshot, ...state.run } as TestRun)
      : snapshot;
  const byId = new Map(
    state.sessions.map((session) => [session.browser_session_id, session]),
  );
  for (const session of snapshot.browser_sessions ?? []) {
    const previous = byId.get(session.browser_session_id);
    const evidence = { ...previous?.page_evidence, ...session.page_evidence };
    for (const key of Object.keys(bounds)) {
      const persisted = record(session.page_evidence)[key];
      const live = record(previous?.page_evidence)[key];
      if (Array.isArray(live))
        evidence[key] = Array.isArray(persisted)
          ? mergeBrowserEntries(persisted, live)
          : live;
    }
    byId.set(
      session.browser_session_id,
      boundedSession({
        ...previous,
        ...session,
        ...(previous?.finished_at && !session.finished_at
          ? { status: previous.status, finished_at: previous.finished_at }
          : {}),
        page_evidence: evidence,
      }),
    );
  }
  const sessions = [...byId.values()].slice(-MAX_BROWSER_SESSIONS);
  return {
    ...state,
    run: {
      ...run,
      log_output:
        preserveLiveLog || (isTerminal(state.run?.status) && !isTerminal(snapshot.status))
          ? mergeObservedLog(
              snapshot.log_output ?? '',
              state.run?.log_output ?? state.logs.join(''),
            )
          : (snapshot.log_output ?? state.run?.log_output ?? state.logs.join('')).slice(-MAX_LOG_CHARACTERS),
    },
    sessions,
    frames: keepFrames(state.frames, sessions),
    streamStatus: isTerminal(run.status) ? 'idle' : state.streamStatus,
  };
}

/** One pure transition function for the actual TestRun event vocabulary. */
export function runEventReducer(state: RunState, raw: unknown): RunState {
  const event = record(raw);
  if (typeof event.type !== 'string') return state;
  if (
    state.run &&
    typeof event.run_id === 'string' &&
    event.run_id !== state.run.id
  )
    return state;
  const id = event.id === undefined ? null : String(event.id);
  if (id && state.seenIds.includes(id)) return state;
  const terminal = isTerminal(state.run?.status);
  if (
    terminal &&
    ['CONNECTED', 'RUN_STARTED', 'TEST_FINISHED', 'LOG_STREAM'].includes(
      event.type,
    )
  )
    return state;
  if (
    terminal &&
    ['RUN_FINISHED', 'RUN_ERROR', 'RUN_CANCELLED'].includes(event.type)
  )
    return state;
  let next = state;
  const run = state.run;
  switch (event.type) {
    case 'CONNECTED':
      next = { ...state, streamStatus: 'connected', error: '' };
      break;
    case 'RUN_STARTED':
      next = {
        ...state,
        run: run
          ? {
              ...run,
              status: event.status === 'QUEUED' ? 'QUEUED' : 'RUNNING',
              total: number(event.total, run.total),
            }
          : run,
      };
      break;
    case 'TEST_FINISHED': {
      if (
        !run ||
        typeof event.nodeid !== 'string' ||
        !['PASSED', 'FAILED', 'SKIPPED', 'ERROR'].includes(String(event.status))
      )
        return state;
      const previous = run.executions.find(
        (item) => item.nodeid === event.nodeid,
      );
      const execution = {
        ...previous,
        id: previous?.id ?? `live:${event.nodeid}`,
        run_id: run.id,
        nodeid: event.nodeid,
        status: event.status,
        duration_ms: number(event.duration_ms, previous?.duration_ms ?? 0),
        artifact_paths: previous?.artifact_paths ?? [],
        started_at: previous?.started_at ?? null,
        finished_at: previous?.finished_at ?? null,
      } as TestExecution;
      const executions = previous
        ? run.executions.map((item) =>
            item.nodeid === event.nodeid ? execution : item,
          )
        : [...run.executions, execution];
      next = { ...state, run: { ...run, executions } };
      break;
    }
    case 'LOG_STREAM': {
      if (typeof event.log !== 'string') return state;
      next = {
        ...state,
        logs: [...state.logs, event.log.slice(-MAX_LOG_CHARACTERS)].slice(
          -MAX_LOG_ENTRIES,
        ),
        run: run
          ? {
              ...run,
              log_output: (event.replace === true ? event.log : (run.log_output ?? '') + event.log).slice(
                -MAX_LOG_CHARACTERS,
              ),
            }
          : run,
      };
      break;
    }
    case 'RUN_FINISHED':
    case 'RUN_ERROR':
    case 'RUN_CANCELLED': {
      const status =
        event.type === 'RUN_ERROR'
          ? 'ERROR'
          : event.type === 'RUN_CANCELLED'
            ? 'CANCELLED'
            : event.status;
      if (!['PASSED', 'FAILED', 'ERROR', 'CANCELLED'].includes(String(status)))
        return state;
      next = {
        ...state,
        streamStatus: 'idle',
        error: typeof event.error === 'string' ? event.error : state.error,
        run: run
          ? {
              ...run,
              status: status as TestRun['status'],
              passed: number(event.passed, run.passed),
              failed: number(event.failed, run.failed),
              duration_ms: number(event.duration_ms, run.duration_ms),
            }
          : run,
      };
      break;
    }
    case 'BROWSER_SESSION': {
      const value = record(event.session);
      if (typeof value.browser_session_id !== 'string') return state;
      const existing = state.sessions.find(
        (item) => item.browser_session_id === value.browser_session_id,
      );
      const session = boundedSession({
        ...existing,
        ...value,
      } as TestBrowserSession);
      const sessions = (
        existing
          ? state.sessions.map((item) =>
              item.browser_session_id === session.browser_session_id
                ? session
                : item,
            )
          : [...state.sessions, session]
      ).slice(-MAX_BROWSER_SESSIONS);
      next = { ...state, sessions, frames: keepFrames(state.frames, sessions) };
      break;
    }
    case 'BROWSER_TELEMETRY': {
      const key = (
        {
          network: 'network_logs',
          console: 'console_logs',
          step: 'recent_steps',
        } as const
      )[String(event.channel) as 'network' | 'console' | 'step'];
      if (!key || !event.entry) return state;
      next = {
        ...state,
        sessions: state.sessions.map((session) => {
          if (session.browser_session_id !== event.session_id) return session;
          const entries = session.page_evidence?.[key];
          return {
            ...session,
            page_evidence: {
              ...session.page_evidence,
              [key]: [
                ...(Array.isArray(entries) ? entries : []),
                event.entry,
              ].slice(-bounds[key]),
            },
          };
        }),
      };
      break;
    }
    case 'BROWSER_FRAME': {
      if (
        typeof event.session_id !== 'string' ||
        typeof event.frame !== 'string' ||
        event.frame.length > 2 * 1024 * 1024
      )
        return state;
      // A frame is evidence, never a synthetic browser session or trace entry.
      const frames = {
        ...state.frames,
        [event.session_id]: `data:${event.mime_type === 'image/png' ? 'image/png' : 'image/jpeg'};base64,${event.frame}`,
      };
      return {
        ...state,
        frames: Object.fromEntries(
          Object.entries(frames).slice(-MAX_BROWSER_SESSIONS),
        ),
      };
    }
    default:
      return state;
  }
  // Do not retain prompt, content, credentials or frame payloads in the ordinary trace buffer.
  const trace = Object.fromEntries(
    [
      'id',
      'type',
      'run_id',
      'timestamp',
      'nodeid',
      'status',
      'duration_ms',
      'channel',
      'session_id',
    ]
      .filter((key) => event[key] !== undefined)
      .map((key) => [key, event[key]]),
  ) as RunEvent;
  return {
    ...next,
    events: [...state.events, trace].slice(-MAX_TRACE_EVENTS),
    seenIds: id
      ? [...state.seenIds, id].slice(-MAX_TRACE_EVENTS)
      : state.seenIds,
  };
}

export interface RunTransport {
  getRun: (id: string) => Promise<TestRun>;
  stream: (
    id: string,
    onEvent: (event: unknown) => void,
    onError: (reason: unknown) => void,
  ) => () => void;
  permanentError: (reason: unknown) => boolean;
}
/** Reference-counted transport: all consumers of this instance share one SSE and poller. */
export function createRunStore(runId: string, transport: RunTransport) {
  let state = emptyRunState();
  const listeners = new Set<() => void>();
  let close = () => {};
  let timer: ReturnType<typeof setInterval> | undefined;
  let generation = 0;
  let revision = 0;
  let inFlightEvents: unknown[] = [];
  let terminalSyncNeeded = false;
  let pending: Promise<void> | null = null;
  const update = (value: RunState) => {
    if (value === state) return;
    state = value;
    listeners.forEach((listener) => listener());
  };
  const stop = () => {
    generation++;
    close();
    close = () => {};
    clearInterval(timer);
    timer = undefined;
    pending = null;
  };
  const refresh = async () => {
    if (pending) return pending;
    const current = generation;
    const version = revision;
    inFlightEvents = [];
    const request = (async () => {
      try {
        const snapshot = await transport.getRun(runId);
        if (current !== generation || !listeners.size) return;
        // A slow snapshot must never overwrite a newer lifecycle/log event.
        let reconciled = reconcileRun(state, snapshot, inFlightEvents.some((event) => record(event).type === 'LOG_STREAM'));
        if (version !== revision) {
          for (const event of inFlightEvents)
            if (
              !['LOG_STREAM', 'BROWSER_SESSION', 'BROWSER_TELEMETRY'].includes(
                String(record(event).type),
              )
            )
              reconciled = runEventReducer(
                { ...reconciled, seenIds: [] },
                event,
              );
          reconciled = {
            ...reconciled,
            events: state.events,
            logs: state.logs,
            seenIds: state.seenIds,
          };
        }
        update(reconciled);
        if (isTerminal(state.run?.status)) stop();
      } catch (reason) {
        if (current === generation) update({ ...state, error: String(reason) });
      }
    })();
    pending = request;
    await request;
    if (pending === request) pending = null;
    if (terminalSyncNeeded && listeners.size) {
      terminalSyncNeeded = false;
      await refresh();
    }
  };
  const start = () => {
    const current = ++generation;
    update({ ...state, streamStatus: 'connecting' });
    close = transport.stream(
      runId,
      (raw) => {
        if (current !== generation) return;
        const event = record(raw);
        revision++;
        if (pending && event.type !== 'BROWSER_FRAME')
          inFlightEvents = [...inFlightEvents, raw].slice(-MAX_TRACE_EVENTS);
        update(runEventReducer(state, raw));
        if (
          ['RUN_FINISHED', 'RUN_ERROR', 'RUN_CANCELLED'].includes(
            String(event.type),
          )
        ) {
          close();
          clearInterval(timer);
          timer = undefined;
          if (pending) terminalSyncNeeded = true;
          else void refresh();
        } else if (
          [
            'CONNECTED',
            'RUN_STARTED',
            'TEST_FINISHED',
            'BROWSER_SESSION',
          ].includes(String(event.type))
        )
          void refresh();
      },
      (reason) => {
        if (current !== generation || isTerminal(state.run?.status)) return;
        const permanent = transport.permanentError(reason);
        update({
          ...state,
          streamStatus: permanent ? 'failed' : 'reconnecting',
          error: String(reason),
        });
        if (permanent) close();
        void refresh();
      },
    );
    timer = setInterval(() => void refresh(), 1500);
    void refresh();
  };
  return {
    getSnapshot: () => state,
    isActive: () => listeners.size > 0,
    refresh,
    subscribe(listener: () => void) {
      listeners.add(listener);
      if (listeners.size === 1) start();
      return () => {
        listeners.delete(listener);
        if (!listeners.size) stop();
      };
    },
  };
}
