/**
 * Live Quality Discovery state: pure folding of the discovery event stream into what the
 * workbench shows. No React here so the behaviour is testable without a DOM.
 *
 * The stream mirrors one run's real events (`snapshot`, `page.*`, `element.inventory`,
 * `action.*`, `ai.*`, `finding`, `browser.frame`, `run.finished`). Nothing is invented: an
 * event the backend did not send is simply absent from the state.
 */

export const DEFAULT_VIEWPORT = { width: 1280, height: 720 };

/** Persisted run events (from `GET /discovery/runs/{id}`) and streamed events share this shape. */
export interface DiscoveryLiveEvent {
  id?: string;
  type: string;
  seq?: number;
  message?: string;
  metadata?: Record<string, any>;
  at?: string;
}

export interface DiscoveryElement {
  index?: number | null;
  tag?: string;
  role?: string;
  name?: string;
  actionable?: boolean;
  in_viewport?: boolean;
  visible_ratio?: number;
  bounding_box?: { x: number; y: number; width: number; height: number } | null;
  locator?: unknown;
}

export type DiscoveryStreamStatus = 'idle' | 'connecting' | 'live' | 'reconnecting' | 'ended';

export interface DiscoveryLiveState {
  status: string;
  streamStatus: DiscoveryStreamStatus;
  /** Data URL of the newest viewport frame, or null before the first frame. */
  frame: string | null;
  url: string;
  viewport: { width: number; height: number };
  elements: DiscoveryElement[];
  /** True when the page moved on after the element inventory was captured. */
  elementsStale: boolean;
  aiUnavailable: { stage: string; code?: string | null } | null;
  decision: DiscoveryLiveEvent | null;
  currentAction: DiscoveryLiveEvent | null;
  timeline: DiscoveryLiveEvent[];
  /** Keys of the events already folded, so a replayed stream cannot double-count anything. */
  seen: string[];
  counts: { frames: number; elements: number; actions: number; findings: number };
}

export const TERMINAL_RUN_STATUSES = ['COMPLETED', 'BLOCKED', 'FAILED', 'STOPPED', 'BUDGET_EXHAUSTED'];

export function isTerminalRunStatus(status: string): boolean {
  return TERMINAL_RUN_STATUSES.includes(status);
}

export function initialLiveState(): DiscoveryLiveState {
  return {
    status: 'PENDING',
    streamStatus: 'connecting',
    frame: null,
    url: '',
    viewport: { ...DEFAULT_VIEWPORT },
    elements: [],
    elementsStale: false,
    aiUnavailable: null,
    decision: null,
    currentAction: null,
    timeline: [],
    seen: [],
    counts: { frames: 0, elements: 0, actions: 0, findings: 0 },
  };
}

/** Normalise a persisted event row (created_at/id) into the streamed event shape. */
export function normalizeEvent(raw: any): DiscoveryLiveEvent | null {
  if (!raw || typeof raw !== 'object' || typeof raw.type !== 'string' || !raw.type.trim()) return null;
  return {
    id: typeof raw.id === 'string' ? raw.id : undefined,
    type: raw.type,
    seq: typeof raw.seq === 'number' ? raw.seq : undefined,
    message: typeof raw.message === 'string' ? raw.message : '',
    metadata: raw.metadata && typeof raw.metadata === 'object' ? raw.metadata : {},
    at: typeof raw.at === 'string' ? raw.at : typeof raw.created_at === 'string' ? raw.created_at : undefined,
  };
}

function eventKey(event: DiscoveryLiveEvent): string {
  return event.id ?? `${event.type}:${event.seq ?? ''}:${event.at ?? ''}`;
}

export function frameDataUrl(metadata: Record<string, any> | undefined): string | null {
  const frame = metadata?.frame;
  if (typeof frame !== 'string' || !frame) return null;
  const mime = metadata?.mime_type === 'image/png' ? 'image/png' : 'image/jpeg';
  return `data:${mime};base64,${frame}`;
}

function viewportFrom(metadata: Record<string, any> | undefined): { width: number; height: number } {
  const width = Number(metadata?.viewport?.width);
  const height = Number(metadata?.viewport?.height);
  if (Number.isFinite(width) && width > 0 && Number.isFinite(height) && height > 0)
    return { width, height };
  return { ...DEFAULT_VIEWPORT };
}

const SEEN_LIMIT = 500;

function pushTimeline(events: DiscoveryLiveEvent[], limit: number): DiscoveryLiveEvent[] {
  const seen = new Set<string>();
  const merged: DiscoveryLiveEvent[] = [];
  for (const event of events) {
    const key = eventKey(event);
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(event);
    if (merged.length >= limit) break;
  }
  return merged;
}

export function foldLiveEvent(
  state: DiscoveryLiveState,
  raw: DiscoveryLiveEvent,
  options: { timelineLimit?: number } = {},
): DiscoveryLiveState {
  const event = normalizeEvent(raw);
  if (!event) return state;
  const limit = options.timelineLimit ?? 200;
  const key = eventKey(event);
  // SSE reconnects replay history; folding the same event twice would double-count it.
  if (state.seen.includes(key)) return state;

  if (event.type === 'snapshot') {
    const seeded = Array.isArray((raw as any).events)
      ? ((raw as any).events as any[]).map(normalizeEvent).filter((item): item is DiscoveryLiveEvent => item !== null)
      : [];
    return {
      ...state,
      status: typeof (raw as any).status === 'string' ? (raw as any).status : state.status,
      // The snapshot replays history oldest-first, while the timeline is newest-first.
      timeline: pushTimeline([...state.timeline, ...seeded.slice().reverse()], limit),
      seen: [key, ...seeded.map(eventKey), ...state.seen].slice(0, SEEN_LIMIT),
    };
  }

  let next: DiscoveryLiveState = {
    ...state,
    timeline: pushTimeline([event, ...state.timeline], limit),
    seen: [key, ...state.seen].slice(0, SEEN_LIMIT),
  };

  switch (event.type) {
    case 'run.status':
    case 'run.finished': {
      next = {
        ...next,
        status: String(event.metadata?.status ?? next.status),
      };
      if (event.type === 'run.finished' || isTerminalRunStatus(next.status))
        next = { ...next, streamStatus: 'ended' };
      return next;
    }
    case 'browser.frame': {
      const frame = frameDataUrl(event.metadata);
      return {
        ...next,
        frame: frame ?? next.frame,
        url: String(event.metadata?.url || next.url),
        viewport: viewportFrom(event.metadata),
        counts: { ...next.counts, frames: next.counts.frames + (frame ? 1 : 0) },
      };
    }
    case 'element.inventory': {
      const elements = Array.isArray(event.metadata?.elements) ? (event.metadata.elements as DiscoveryElement[]) : [];
      return {
        ...next,
        elements,
        elementsStale: false,
        counts: { ...next.counts, elements: elements.length },
      };
    }
    case 'page.opened':
    case 'page.state': {
      const url = String(event.metadata?.url || '');
      const moved = Boolean(url) && url !== next.url;
      return {
        ...next,
        url: url || next.url,
        // Element boxes belong to the page they were measured on; a new page invalidates them.
        elementsStale: moved ? true : next.elementsStale,
      };
    }
    case 'ai.decision':
      return { ...next, decision: event };
    case 'ai.unavailable':
      return {
        ...next,
        aiUnavailable: { stage: String(event.metadata?.stage ?? ''), code: event.metadata?.code ?? null },
      };
    case 'action.planned':
    case 'action.executed':
    case 'action.failed':
      return {
        ...next,
        currentAction: event,
        counts: {
          ...next.counts,
          actions: event.type === 'action.planned' ? next.counts.actions : next.counts.actions + 1,
        },
      };
    case 'finding':
      return { ...next, counts: { ...next.counts, findings: next.counts.findings + 1 } };
    default:
      return next;
  }
}

export type OverlayTone = 'interactive' | 'form' | 'uncertain';

export interface OverlayBox {
  key: string;
  index: number | null;
  label: string;
  tone: OverlayTone;
  left: number;
  top: number;
  width: number;
  height: number;
}

/** Colour by what the element is, never by what we hope it is: only the DOM tells us. */
export function toneFor(element: DiscoveryElement): OverlayTone {
  const tag = String(element.tag ?? '').toLowerCase();
  const role = String(element.role ?? '').toLowerCase();
  if (['input', 'select', 'textarea'].includes(tag) || ['textbox', 'combobox', 'searchbox', 'spinbutton'].includes(role))
    return 'form';
  if (['button', 'link', 'tab', 'menuitem', 'checkbox', 'switch', 'radio'].includes(role)) return 'interactive';
  if (['a', 'button'].includes(tag)) return 'interactive';
  return 'uncertain';
}

/**
 * Turn measured element boxes into overlay geometry in percent of the viewport, clipped to it.
 * Elements measured on a page that has since changed are dropped by the caller (see `elementsStale`).
 */
export function overlayBoxes(
  elements: DiscoveryElement[],
  viewport: { width: number; height: number },
  options: { maxBoxes?: number; minSize?: number } = {},
): OverlayBox[] {
  const maxBoxes = options.maxBoxes ?? 40;
  const minSize = options.minSize ?? 4;
  const boxes: OverlayBox[] = [];
  for (const element of elements) {
    const box = element.bounding_box;
    if (!box) continue;
    const x = Number(box.x);
    const y = Number(box.y);
    const width = Number(box.width);
    const height = Number(box.height);
    if (![x, y, width, height].every(Number.isFinite)) continue;
    if (x >= viewport.width || y >= viewport.height) continue;
    const left = Math.max(0, x);
    const top = Math.max(0, y);
    const right = Math.min(viewport.width, x + width);
    const bottom = Math.min(viewport.height, y + height);
    const clippedWidth = right - left;
    const clippedHeight = bottom - top;
    if (clippedWidth < minSize || clippedHeight < minSize) continue;
    boxes.push({
      key: `${element.index ?? boxes.length}-${left}-${top}`,
      index: element.index ?? null,
      label: String(element.name || element.role || element.tag || ''),
      tone: toneFor(element),
      left: (left / viewport.width) * 100,
      top: (top / viewport.height) * 100,
      width: (clippedWidth / viewport.width) * 100,
      height: (clippedHeight / viewport.height) * 100,
    });
    if (boxes.length >= maxBoxes) break;
  }
  return boxes;
}
