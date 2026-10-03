import { useRef, useState } from 'react';
import type { KeyboardEvent, PointerEvent } from 'react';

/** Shared viewport mechanics for KnowledgeGraph and Runtime DAG. */
export function useGraphViewport(initialScale = 0.75) {
  const [scale, setScale] = useState(initialScale);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const viewport = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(
    null,
  );
  const fit = (width: number, height: number) => {
    const element = viewport.current;
    setScale(
      Math.max(
        0.15,
        Math.min(
          1,
          ((element?.clientWidth ?? 800) - 30) / width,
          ((element?.clientHeight ?? 420) - 30) / height,
        ),
      ),
    );
    setOffset({ x: 8, y: 8 });
  };
  const center = (
    position: { x: number; y: number },
    width = 220,
    height = 126,
    nextScale = scale,
  ) => {
    const element = viewport.current;
    setOffset({
      x:
        (element?.clientWidth ?? 800) / 2 -
        (position.x + width / 2) * nextScale,
      y:
        (element?.clientHeight ?? 420) / 2 -
        (position.y + height / 2) * nextScale,
    });
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const delta: Record<string, { x: number; y: number }> = {
      ArrowLeft: { x: 40, y: 0 },
      ArrowRight: { x: -40, y: 0 },
      ArrowUp: { x: 0, y: 40 },
      ArrowDown: { x: 0, y: -40 },
    };
    if (event.target === event.currentTarget && delta[event.key]) {
      event.preventDefault();
      setOffset((value) => ({
        x: value.x + delta[event.key].x,
        y: value.y + delta[event.key].y,
      }));
    }
  };
  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if ((event.target as HTMLElement).closest('button,a,input')) return;
    drag.current = {
      x: event.clientX,
      y: event.clientY,
      ox: offset.x,
      oy: offset.y,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (drag.current)
      setOffset({
        x: drag.current.ox + event.clientX - drag.current.x,
        y: drag.current.oy + event.clientY - drag.current.y,
      });
  };
  const end = () => {
    drag.current = null;
  };
  return {
    scale,
    setScale,
    offset,
    setOffset,
    viewport,
    fit,
    center,
    handlers: {
      onKeyDown,
      onPointerDown,
      onPointerMove,
      onPointerUp: end,
      onPointerCancel: end,
    },
  };
}
