import { useCallback, useEffect, useRef, useState } from 'react';
import { api, getDebugSocketUrl } from '../../../api/client';
import { Breakpoint, DebugSessionBootstrap } from '../../../types';

export type DebugState = 'idle' | 'starting' | 'running' | 'paused' | 'finished' | 'error';

export interface DebugStackFrame {
  id: number;
  name: string;
  line: number;
  column?: number;
  source?: { name?: string; path?: string };
}

export interface DebugVariable {
  name: string;
  value: string;
  type?: string;
}

export interface DebugBreakpointBinding {
  id: string;
  path: string;
  requestedLine: number;
  line: number;
  adapterId?: number;
  verified: boolean | null;
  message?: string;
  hit: boolean;
}

interface DapMessage {
  seq?: number;
  type?: string;
  event?: string;
  command?: string;
  request_seq?: number;
  success?: boolean;
  message?: string;
  arguments?: Record<string, unknown>;
  body?: Record<string, unknown>;
}

interface PendingRequest {
  resolve: (message: DapMessage) => void;
  reject: (error: Error) => void;
  timeout: number;
}

interface UseDebugSessionOptions {
  projectId: string | null;
  breakpoints: Breakpoint[];
  onOpenFile: (path: string) => void | Promise<void>;
  onExecutionLine: (location: { path: string; line: number } | null) => void;
  onBreakpoints?: (breakpoints: Breakpoint[]) => void;
}

const isWorkspacePath = (value: string): boolean => !value.startsWith('/') && !/^[a-zA-Z]:[\\/]/.test(value);

export const useDebugSession = ({ projectId, breakpoints, onOpenFile, onExecutionLine, onBreakpoints }: UseDebugSessionOptions) => {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [targetNodeid, setTargetNodeid] = useState<string | null>(null);
  const [state, setState] = useState<DebugState>('idle');
  const [error, setError] = useState('');
  const [frames, setFrames] = useState<DebugStackFrame[]>([]);
  const [locals, setLocals] = useState<DebugVariable[]>([]);
  const [output, setOutput] = useState('');
  const [breakpointBindings, setBreakpointBindings] = useState<DebugBreakpointBinding[]>([]);
  const [hasHitBreakpoint, setHasHitBreakpoint] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const bootstrapRef = useRef<DebugSessionBootstrap | null>(null);
  const sequenceRef = useRef(0);
  const threadIdRef = useRef<number | null>(null);
  const pendingRef = useRef(new Map<number, PendingRequest>());
  const breakpointsRef = useRef(breakpoints);
  breakpointsRef.current = breakpoints;
  const projectIdRef = useRef(projectId);
  projectIdRef.current = projectId;
  const configuredRef = useRef(false);
  const breakpointPathsRef = useRef(new Set<string>());
  const breakpointQueueRef = useRef<Promise<void>>(Promise.resolve());

  const sendRequest = useCallback((command: string, args: Record<string, unknown> = {}, wait = true) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return Promise.reject(new Error('Debug Adapter WebSocket is not connected.'));
    }
    sequenceRef.current += 1;
    const seq = sequenceRef.current;
    socket.send(JSON.stringify({ seq, type: 'request', command, arguments: args }));
    if (!wait) return Promise.resolve(null as unknown as DapMessage);
    return new Promise<DapMessage>((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        pendingRef.current.delete(seq);
        reject(new Error(`DAP request timed out: ${command}`));
      }, 15000);
      pendingRef.current.set(seq, { resolve, reject, timeout });
    });
  }, []);

  const selectFrame = useCallback(async (frame: DebugStackFrame) => {
    const socket = socketRef.current;
    if (frame.source?.path && isWorkspacePath(frame.source.path)) {
      const path = frame.source.path.replace(/\\/g, '/');
      await onOpenFile(path);
      if (socketRef.current !== socket) return;
      onExecutionLine({ path, line: frame.line });
    }
    try {
      const scopeResponse = await sendRequest('scopes', { frameId: frame.id });
      if (socketRef.current !== socket) return;
      const scopes = (scopeResponse.body?.scopes as Array<{ name: string; variablesReference: number }> | undefined) ?? [];
      const localScope = scopes.find((scope) => scope.name === 'Locals');
      if (!localScope?.variablesReference) {
        setLocals([]);
        return;
      }
      const variableResponse = await sendRequest('variables', { variablesReference: localScope.variablesReference });
      if (socketRef.current !== socket) return;
      setLocals((variableResponse.body?.variables as DebugVariable[] | undefined) ?? []);
    } catch (requestError) {
      if (socketRef.current !== socket) return;
      setError(requestError instanceof Error ? requestError.message : String(requestError));
      setLocals([]);
    }
  }, [onExecutionLine, onOpenFile, sendRequest]);

  const loadStack = useCallback(async (threadId: number, reason?: string) => {
    const socket = socketRef.current;
    try {
      const response = await sendRequest('stackTrace', { threadId });
      if (socketRef.current !== socket) return;
      const nextFrames = (response.body?.stackFrames as DebugStackFrame[] | undefined) ?? [];
      setFrames(nextFrames);
      const frame = nextFrames[0];
      if (reason === 'breakpoint' && frame) {
        const path = frame.source?.path?.replace(/\\/g, '/');
        setBreakpointBindings((items) => items.map((item) => (
          item.path === path && item.line === frame.line ? { ...item, hit: true } : item
        )));
      }
      if (nextFrames[0]) await selectFrame(nextFrames[0]);
    } catch (requestError) {
      if (socketRef.current !== socket) return;
      setError(requestError instanceof Error ? requestError.message : String(requestError));
    }
  }, [selectFrame, sendRequest]);

  const synchronizeBreakpoints = useCallback((items: Breakpoint[]) => {
    const socket = socketRef.current;
    if (!configuredRef.current || !socket || socket.readyState !== WebSocket.OPEN
      || bootstrapRef.current?.workspace_id !== projectIdRef.current) return Promise.resolve();
    // Serialize full-file replacements, including empty lists when the last breakpoint is removed.
    // A slow response from an earlier edit must never overwrite a newer edit.
    const queued = breakpointQueueRef.current.catch(() => undefined).then(async () => {
      if (socketRef.current !== socket || !configuredRef.current
        || bootstrapRef.current?.workspace_id !== projectIdRef.current) return;
      const activeBreakpoints = items.filter((item) => item.enabled);
      const grouped = new Map<string, Breakpoint[]>();
      for (const breakpoint of activeBreakpoints) {
        const path = breakpoint.file_path.replace(/\\/g, '/').replace(/^\/+/, '');
        grouped.set(path, [...(grouped.get(path) ?? []), breakpoint]);
      }
      const paths = new Set([...breakpointPathsRef.current, ...grouped.keys()]);
      for (const path of paths) {
        if (bootstrapRef.current?.workspace_id !== projectIdRef.current) return;
        const fileItems = grouped.get(path) ?? [];
        // Keep track of partially applied configurations so a retry can clear them too.
        breakpointPathsRef.current.add(path);
        setBreakpointBindings((current) => [
          ...current.filter((item) => item.path !== path),
          ...fileItems.map((item) => ({
            id: item.id, path, requestedLine: item.line_number, line: item.line_number,
            verified: null, hit: current.find((binding) => binding.id === item.id)?.hit ?? false,
          })),
        ]);
        const response = await sendRequest('setBreakpoints', {
          source: { name: path.split('/').pop() ?? path, path },
          breakpoints: fileItems.map((item) => ({ line: item.line_number })),
          sourceModified: false,
        });
        if (socketRef.current !== socket) return;
        const accepted = (response.body?.breakpoints as Array<{ id?: number; line?: number; verified?: boolean; message?: string }> | undefined) ?? [];
        setBreakpointBindings((current) => current.map((binding) => {
          const index = fileItems.findIndex((item) => item.id === binding.id);
          if (binding.path !== path || index < 0) return binding;
          const result = accepted[index];
          return { ...binding, adapterId: result?.id, line: result?.line ?? binding.requestedLine,
            verified: result?.verified === true, message: result?.message };
        }));
      }
      breakpointPathsRef.current = new Set(grouped.keys());
    });
    breakpointQueueRef.current = queued;
    void queued.catch((requestError) => {
      if (socketRef.current !== socket) return;
      const message = requestError instanceof Error ? requestError.message : String(requestError);
      setError(message);
      setBreakpointBindings((current) => current.map((binding) => (
        binding.verified === null ? { ...binding, verified: false, message } : binding
      )));
    });
    return queued;
  }, [sendRequest]);

  useEffect(() => {
    void synchronizeBreakpoints(breakpoints).catch(() => undefined);
  }, [breakpoints, synchronizeBreakpoints]);

  const configureBreakpoints = useCallback(async () => {
    const socket = socketRef.current;
    try {
      configuredRef.current = true;
      await synchronizeBreakpoints(breakpointsRef.current);
      if (socketRef.current !== socket) return;
      await sendRequest('setExceptionBreakpoints', { filters: [] });
      if (socketRef.current !== socket) return;
      await breakpointQueueRef.current;
      if (socketRef.current !== socket) return;
      await sendRequest('configurationDone');
    } catch (requestError) {
      if (socketRef.current !== socket) return;
      setState('error');
      setError(requestError instanceof Error ? requestError.message : String(requestError));
    }
  }, [sendRequest, synchronizeBreakpoints]);

  const start = useCallback(async (nodeid: string, failureId?: string | null) => {
    if (!projectId || state === 'starting' || state === 'running' || state === 'paused') return;
    setState('starting');
    setError('');
    setFrames([]);
    setLocals([]);
    setOutput('');
    setBreakpointBindings([]);
    setHasHitBreakpoint(false);
    configuredRef.current = false;
    breakpointPathsRef.current = new Set();
    breakpointQueueRef.current = Promise.resolve();
    onExecutionLine(null);
    const previousSocket = socketRef.current;
    socketRef.current = null;
    previousSocket?.close();
    const previousId = sessionIdRef.current;
    sessionIdRef.current = null;
    bootstrapRef.current = null;
    threadIdRef.current = null;
    for (const pending of pendingRef.current.values()) {
      window.clearTimeout(pending.timeout);
      pending.reject(new Error('A new debug session started.'));
    }
    pendingRef.current.clear();
    try {
      if (previousId) await api.closeDebugSession(previousId).catch(() => undefined);
      const bootstrap = await api.createDebugSession(projectId, nodeid, failureId);
      setTargetNodeid(bootstrap.nodeid);
      bootstrapRef.current = bootstrap;
      breakpointsRef.current = bootstrap.breakpoints;
      onBreakpoints?.(bootstrap.breakpoints);
      sessionIdRef.current = bootstrap.id;
      setSessionId(bootstrap.id);
      const socketUrl = await getDebugSocketUrl(bootstrap.id);
      const streamTicket = await api.createStreamTicket('debug', bootstrap.id);
      const socket = new WebSocket(socketUrl);
      socketRef.current = socket;
      socket.onopen = async () => {
        if (socketRef.current !== socket) return;
        try {
          socket.send(JSON.stringify({ type: 'auth', stream_ticket: streamTicket }));
          const initialized = await sendRequest('initialize', {
            clientID: 'ai-qa-platform',
            adapterID: 'python',
            pathFormat: 'path',
            linesStartAt1: true,
            columnsStartAt1: true,
            supportsRunInTerminalRequest: false,
            supportsVariableType: true,
            supportsVariablePaging: false,
          });
          if (initialized.success !== true) throw new Error(initialized.message || 'debugpy initialization failed');
          void sendRequest('launch').then(() => {
            if (socketRef.current === socket) setState((current) => current === 'starting' ? 'running' : current);
          }).catch((requestError) => {
            if (socketRef.current !== socket) return;
            setState('error');
            setError(requestError instanceof Error ? requestError.message : String(requestError));
          });
        } catch (requestError) {
          if (socketRef.current !== socket) return;
          setState('error');
          setError(requestError instanceof Error ? requestError.message : String(requestError));
        }
      };
      socket.onmessage = (event) => {
        if (socketRef.current !== socket) return;
        let message: DapMessage;
        try { message = JSON.parse(String(event.data)) as DapMessage; } catch { return; }
        if (message.type === 'response' && typeof message.request_seq === 'number') {
          const pending = pendingRef.current.get(message.request_seq);
          if (pending) {
            window.clearTimeout(pending.timeout);
            pendingRef.current.delete(message.request_seq);
            if (message.success === false) pending.reject(new Error(message.message || `${message.command ?? 'DAP'} failed`));
            else pending.resolve(message);
          }
        } else if (message.type === 'event') {
          if (message.event === 'initialized') void configureBreakpoints();
          else if (message.event === 'stopped') {
            const threadId = message.body?.threadId;
            if (typeof threadId === 'number') {
              threadIdRef.current = threadId;
              setState('paused');
              const reason = String(message.body?.reason ?? '');
              if (reason === 'breakpoint') setHasHitBreakpoint(true);
              void loadStack(threadId, reason);
            }
          } else if (message.event === 'breakpoint') {
            const binding = message.body?.breakpoint as { id?: number; verified?: boolean; line?: number; message?: string } | undefined;
            if (binding && typeof binding.id === 'number') setBreakpointBindings((items) => items.map((item) => (
              item.adapterId === binding.id ? { ...item, verified: binding.verified === true,
                line: binding.line ?? item.line, message: binding.message } : item
            )));
          } else if (message.event === 'continued') setState('running');
          else if (message.event === 'output') {
            const text = String(message.body?.output ?? '');
            if (text) setOutput((current) => `${current}${text}`.slice(-12000));
          } else if (message.event === 'terminated') {
            configuredRef.current = false;
            setState('finished');
            threadIdRef.current = null;
            const currentId = sessionIdRef.current;
            if (currentId) window.setTimeout(() => { void api.closeDebugSession(currentId).catch(() => undefined); }, 250);
          }
        }
      };
      socket.onerror = () => {
        if (socketRef.current !== socket) return;
        setState('error');
        setError('Debug Adapter WebSocket connection failed.');
      };
      socket.onclose = () => {
        if (socketRef.current === socket && sessionIdRef.current === bootstrap.id) {
          configuredRef.current = false;
          setState((current) => current === 'error' ? current : 'finished');
        }
      };
    } catch (requestError) {
      const failedSessionId = sessionIdRef.current;
      if (failedSessionId) {
        await api.closeDebugSession(failedSessionId).catch(() => undefined);
        sessionIdRef.current = null;
        bootstrapRef.current = null;
      }
      setState('error');
      setError(requestError instanceof Error ? requestError.message : String(requestError));
    }
  }, [configureBreakpoints, loadStack, onBreakpoints, onExecutionLine, projectId, sendRequest, state]);

  const control = useCallback(async (command: 'continue' | 'next' | 'stepIn' | 'stepOut' | 'pause') => {
    const socket = socketRef.current;
    try {
      await breakpointQueueRef.current;
      if (socketRef.current !== socket) return;
      let threadId = threadIdRef.current;
      if (command === 'pause' && threadId === null) {
        const response = await sendRequest('threads');
        if (socketRef.current !== socket) return;
        const threads = (response.body?.threads as Array<{ id: number }> | undefined) ?? [];
        threadId = threads[0]?.id ?? null;
        threadIdRef.current = threadId;
      }
      if (threadId === null) return;
      if (command !== 'pause') {
        setState('running');
        setFrames([]);
        setLocals([]);
        onExecutionLine(null);
      }
      await sendRequest(command, { threadId });
    } catch (requestError) {
      if (socketRef.current !== socket) return;
      setState('error');
      setError(requestError instanceof Error ? requestError.message : String(requestError));
    }
  }, [onExecutionLine, sendRequest]);

  const stop = useCallback(async () => {
    const currentId = sessionIdRef.current;
    if (!currentId) return;
    setState('finished');
    configuredRef.current = false;
    void sendRequest('disconnect', { restart: false, terminateDebuggee: true }, false).catch(() => undefined);
    const socket = socketRef.current;
    socketRef.current = null;
    sessionIdRef.current = null;
    bootstrapRef.current = null;
    threadIdRef.current = null;
    socket?.close();
    for (const pending of pendingRef.current.values()) {
      window.clearTimeout(pending.timeout);
      pending.reject(new Error('Debug session stopped.'));
    }
    pendingRef.current.clear();
    await api.closeDebugSession(currentId).catch(() => undefined);
  }, [sendRequest]);

  useEffect(() => () => {
    const currentId = sessionIdRef.current;
    if (currentId) void api.closeDebugSession(currentId).catch(() => undefined);
    socketRef.current?.close();
    for (const pending of pendingRef.current.values()) {
      window.clearTimeout(pending.timeout);
      pending.reject(new Error('Debug view closed.'));
    }
    pendingRef.current.clear();
  }, []);

  return { sessionId, targetNodeid, state, error, frames, locals, output, breakpointBindings, hasHitBreakpoint, start, control, stop, selectFrame };
};
