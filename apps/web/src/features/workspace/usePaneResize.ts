import { useCallback, useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent } from 'react';

/**
 * Pure pane-size model plus a thin React wrapper. The model stays free of React so the
 * clamping, keyboard and persistence behaviour can be unit-tested without a DOM.
 */

export const PANE_RESIZE_STEP = 16;

export interface PaneSizeBounds {
  min: number;
  max: number;
}

export interface PaneSizeStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

/** Clamp a size into `[min, max]`; a non-finite size collapses to the minimum. */
export function clampPaneSize(size: number, min: number, max: number): number {
  if (!Number.isFinite(size)) return min;
  return Math.min(max, Math.max(min, size));
}

/**
 * Keyboard resize for a pane whose handle sits on its top edge: ArrowUp grows the pane,
 * ArrowDown shrinks it, Home/End jump to the minimum/maximum. Returns null for other keys.
 */
export function resizeFromKey(key: string, current: number, bounds: PaneSizeBounds, step = PANE_RESIZE_STEP): number | null {
  switch (key) {
    case 'ArrowUp': return clampPaneSize(current + step, bounds.min, bounds.max);
    case 'ArrowDown': return clampPaneSize(current - step, bounds.min, bounds.max);
    case 'Home': return bounds.min;
    case 'End': return bounds.max;
    default: return null;
  }
}

function defaultStore(): PaneSizeStore | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch {
    return null;
  }
}

/** Read a persisted size, clamping it to the current bounds and falling back when absent/invalid. */
export function readPaneSize(storageKey: string, bounds: PaneSizeBounds, fallback: number, store: PaneSizeStore | null = defaultStore()): number {
  const clampedFallback = clampPaneSize(fallback, bounds.min, bounds.max);
  if (!store) return clampedFallback;
  try {
    const raw = store.getItem(storageKey);
    if (raw === null) return clampedFallback;
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? clampPaneSize(parsed, bounds.min, bounds.max) : clampedFallback;
  } catch {
    return clampedFallback;
  }
}

/** Persist a size. Storage failures are non-fatal: the pane keeps working from in-memory state. */
export function writePaneSize(storageKey: string, size: number, store: PaneSizeStore | null = defaultStore()): void {
  if (!store) return;
  try {
    store.setItem(storageKey, String(size));
  } catch {
    // storage unavailable or full; the size stays in memory for this session
  }
}

export interface UsePaneResizeOptions {
  storageKey: string;
  min: number;
  max: number;
  /** Size used when nothing valid is stored yet. */
  initial: number;
}

export interface PaneResizeHandleProps {
  role: 'separator';
  tabIndex: 0;
  'aria-orientation': 'horizontal';
  'aria-valuemin': number;
  'aria-valuemax': number;
  'aria-valuenow': number;
  onPointerDown: (event: ReactPointerEvent<HTMLElement>) => void;
  onPointerMove: (event: ReactPointerEvent<HTMLElement>) => void;
  onPointerUp: (event: ReactPointerEvent<HTMLElement>) => void;
  onPointerCancel: (event: ReactPointerEvent<HTMLElement>) => void;
  onKeyDown: (event: ReactKeyboardEvent<HTMLElement>) => void;
}

/**
 * Resize a pane with pointer-capture dragging or the keyboard, persisting the chosen size.
 * Spread `handleProps` onto a `role="separator"` element rendered on the pane's resizing edge.
 */
export function usePaneResize({ storageKey, min, max, initial }: UsePaneResizeOptions) {
  const bounds = useRef<PaneSizeBounds>({ min, max });
  bounds.current = { min, max };
  const [size, setSize] = useState(() => readPaneSize(storageKey, { min, max }, initial));
  const sizeRef = useRef(size);
  sizeRef.current = size;
  const drag = useRef<{ pointerId: number; startY: number; startSize: number } | null>(null);

  const applySize = useCallback((next: number) => {
    setSize(clampPaneSize(next, bounds.current.min, bounds.current.max));
  }, []);

  useEffect(() => {
    writePaneSize(storageKey, size);
  }, [storageKey, size]);

  // A drag that unmounts mid-gesture must not leave a stale gesture behind.
  useEffect(() => () => { drag.current = null; }, []);

  const onPointerDown = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { pointerId: event.pointerId, startY: event.clientY, startSize: sizeRef.current };
  }, []);

  const onPointerMove = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    const gesture = drag.current;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    applySize(gesture.startSize + (gesture.startY - event.clientY));
  }, [applySize]);

  const endDrag = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    if (drag.current?.pointerId === event.pointerId) drag.current = null;
  }, []);

  const onKeyDown = useCallback((event: ReactKeyboardEvent<HTMLElement>) => {
    const next = resizeFromKey(event.key, sizeRef.current, bounds.current);
    if (next === null) return;
    event.preventDefault();
    applySize(next);
  }, [applySize]);

  const handleProps = {
    role: 'separator' as const,
    tabIndex: 0 as const,
    'aria-orientation': 'horizontal' as const,
    'aria-valuemin': min,
    'aria-valuemax': max,
    'aria-valuenow': size,
    onPointerDown,
    onPointerMove,
    onPointerUp: endDrag,
    onPointerCancel: endDrag,
    onKeyDown,
  } satisfies PaneResizeHandleProps;

  return { size, setSize: applySize, handleProps };
}
