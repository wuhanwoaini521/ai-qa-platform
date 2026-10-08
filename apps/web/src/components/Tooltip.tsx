import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

interface TooltipProps {
  label: string;
  children: React.ReactNode;
}

interface TooltipPosition {
  left: number;
  top: number;
}

/** Small shared tooltip that escapes scroll containers through a body portal. */
export const Tooltip: React.FC<TooltipProps> = ({ label, children }) => {
  const triggerRef = useRef<HTMLSpanElement>(null);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [position, setPosition] = useState<TooltipPosition | null>(null);
  const visible = hovered || focused;

  const updatePosition = useCallback(() => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setPosition({
      left: rect.right + 8,
      top: Math.max(32, Math.min(window.innerHeight - 32, rect.top + rect.height / 2)),
    });
  }, []);

  const showOnHover = useCallback(() => {
    if (!window.matchMedia('(max-width: 1150px)').matches) return;
    updatePosition();
    setHovered(true);
  }, [updatePosition]);

  const showOnFocus = useCallback(() => {
    if (!window.matchMedia('(max-width: 1150px)').matches) return;
    updatePosition();
    setFocused(true);
  }, [updatePosition]);

  useEffect(() => {
    if (!visible) return undefined;
    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);
    return () => {
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [updatePosition, visible]);

  return (
    <span
      ref={triggerRef}
      className="tooltip-trigger"
      onMouseEnter={showOnHover}
      onMouseLeave={() => setHovered(false)}
      onFocusCapture={showOnFocus}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          setFocused(false);
        }
      }}
    >
      {children}
      {visible && position && typeof document !== 'undefined'
        ? createPortal(
            <div
              className="tooltip-popover tooltip-popover--sidebar"
              role="tooltip"
              aria-hidden="true"
              style={position}
            >
              {label}
            </div>,
            document.body,
          )
        : null}
    </span>
  );
};
