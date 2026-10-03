import { useLayoutEffect, useRef, useState } from 'react';
import { FLOW_NODE_HEIGHT, FLOW_NODE_WIDTH } from './dagLayout';

const clampScale = (value: number) => Math.max(0.15, Math.min(2, value));

/** Native scrolling keeps long flows readable and works with mouse, touch and keyboard. */
export function useFlowViewport(
  width: number,
  height: number,
  enabled: boolean,
) {
  const viewport = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const pending = useRef<{
    x: number;
    y: number;
    ax: number;
    ay: number;
  } | null>(null);
  const inset = Math.max(0, (size.width - width * scale) / 2);

  useLayoutEffect(() => {
    const element = viewport.current;
    if (!element) return;
    const measure = () =>
      setSize({ width: element.clientWidth, height: element.clientHeight });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [enabled]);

  useLayoutEffect(() => {
    const element = viewport.current;
    const target = pending.current;
    if (!element || !target) return;
    element.scrollLeft = inset + target.x * scale - target.ax;
    element.scrollTop = target.y * scale - target.ay;
    pending.current = null;
  }, [scale, inset, width, height, size]);

  const zoom = (value: number, anchor?: { x: number; y: number }) => {
    const element = viewport.current;
    if (!element) return;
    const next = clampScale(value);
    if (next === scale) return;
    const ax = anchor?.x ?? element.clientWidth / 2;
    const ay = anchor?.y ?? element.clientHeight / 2;
    const x = (element.scrollLeft + ax - inset) / scale;
    const y = (element.scrollTop + ay) / scale;
    // Keep the same graph point under the cursor (or viewport centre).
    element.scrollLeft =
      Math.max(0, (element.clientWidth - width * next) / 2) + x * next - ax;
    element.scrollTop = y * next - ay;
    pending.current = { x, y, ax, ay };
    setScale(next);
  };

  const center = (position: { x: number; y: number }, readable = false) => {
    const element = viewport.current;
    if (!element) return;
    const next = readable ? Math.max(0.85, scale) : scale;
    const target = {
      x: position.x + FLOW_NODE_WIDTH / 2,
      y: position.y + FLOW_NODE_HEIGHT / 2,
      ax: element.clientWidth / 2,
      ay: element.clientHeight / 2,
    };
    element.scrollLeft =
      Math.max(0, (element.clientWidth - width * next) / 2) +
      target.x * next -
      target.ax;
    element.scrollTop = target.y * next - target.ay;
    if (next !== scale) {
      pending.current = target;
      setScale(next);
    }
  };

  const fit = () => {
    const element = viewport.current;
    if (!element) return;
    const next = Math.max(0.01,
      Math.min(
        1,
        (element.clientWidth - 24) / width,
        (element.clientHeight - 24) / height,
      ),
    );
    pending.current =
      next === scale
        ? null
        : {
            x: width / 2,
            y: height / 2,
            ax: element.clientWidth / 2,
            ay: element.clientHeight / 2,
          };
    setScale(next);
    element.scrollTo(0, 0);
  };

  return { viewport, scale, size, inset, zoom, center, fit };
}
