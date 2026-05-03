import { useEffect, useLayoutEffect, useRef, useState } from "react";

const SWIPE_SNAP = 80;
const SWIPE_THRESHOLD = 40;

interface SwipeableRowProps {
  children: React.ReactNode;
  isOpen: boolean;
  onOpen: () => void;
  onClose: () => void;
  onDeleteClick: () => void;
  /** Optional left-side action revealed by right-swipe. */
  leftActionLabel?: string;
  leftActionColor?: string;
  isLeftOpen?: boolean;
  onLeftOpen?: () => void;
  onLeftClose?: () => void;
  onLeftActionClick?: () => void;
  borderBottom?: boolean;
  animationDelay?: number;
  /** Background of the sliding content (should match card background). */
  background?: string;
}

export function SwipeableRow({
  children,
  isOpen,
  onOpen,
  onClose,
  onDeleteClick,
  leftActionLabel,
  leftActionColor = "#22c55e",
  isLeftOpen = false,
  onLeftOpen,
  onLeftClose,
  onLeftActionClick,
  borderBottom = false,
  animationDelay,
  background = "var(--app-card-bg)",
}: SwipeableRowProps) {
  const rowRef = useRef<HTMLDivElement>(null);

  const isOpenRef = useRef(isOpen);
  const isLeftOpenRef = useRef(isLeftOpen);
  const onOpenRef = useRef(onOpen);
  const onCloseRef = useRef(onClose);
  const onLeftOpenRef = useRef(onLeftOpen);
  const onLeftCloseRef = useRef(onLeftClose);
  useLayoutEffect(() => { isOpenRef.current = isOpen; }, [isOpen]);
  useLayoutEffect(() => { isLeftOpenRef.current = isLeftOpen; }, [isLeftOpen]);
  useLayoutEffect(() => { onOpenRef.current = onOpen; }, [onOpen]);
  useLayoutEffect(() => { onCloseRef.current = onClose; }, [onClose]);
  useLayoutEffect(() => { onLeftOpenRef.current = onLeftOpen; }, [onLeftOpen]);
  useLayoutEffect(() => { onLeftCloseRef.current = onLeftClose; }, [onLeftClose]);

  const initialX = isLeftOpen ? SWIPE_SNAP : isOpen ? -SWIPE_SNAP : 0;
  const [translateX, setTranslateX] = useState(initialX);
  const [isDragging, setIsDragging] = useState(false);

  useLayoutEffect(() => {
    setTranslateX(isLeftOpen ? SWIPE_SNAP : isOpen ? -SWIPE_SNAP : 0);
  }, [isOpen, isLeftOpen]);

  const hasLeftAction = Boolean(leftActionLabel);

  useEffect(() => {
    const el = rowRef.current;
    if (!el) return;

    const gesture = { startX: 0, startY: 0, dragging: false, locked: false, currentX: 0 };

    function onTouchStart(e: TouchEvent) {
      const t = e.touches[0];
      gesture.startX = t.clientX;
      gesture.startY = t.clientY;
      gesture.dragging = false;
      gesture.locked = false;
      gesture.currentX = isLeftOpenRef.current ? SWIPE_SNAP : isOpenRef.current ? -SWIPE_SNAP : 0;
    }

    function onTouchMove(e: TouchEvent) {
      if (gesture.locked) return;
      const t = e.touches[0];
      const dx = t.clientX - gesture.startX;
      const dy = t.clientY - gesture.startY;

      if (!gesture.dragging) {
        if (Math.abs(dx) < 4 && Math.abs(dy) < 4) return;
        if (Math.abs(dy) > Math.abs(dx) * 1.5) { gesture.locked = true; return; }
        if (Math.abs(dx) >= 4) { gesture.dragging = true; setIsDragging(true); }
        else return;
      }

      e.preventDefault();
      const base = isLeftOpenRef.current ? SWIPE_SNAP : isOpenRef.current ? -SWIPE_SNAP : 0;
      const maxRight = hasLeftAction ? SWIPE_SNAP : 0;
      const newX = Math.max(-SWIPE_SNAP, Math.min(maxRight, base + dx));
      gesture.currentX = newX;
      setTranslateX(newX);
    }

    function onTouchEnd() {
      if (!gesture.dragging) return;
      gesture.dragging = false;
      setIsDragging(false);
      const base = isLeftOpenRef.current ? SWIPE_SNAP : isOpenRef.current ? -SWIPE_SNAP : 0;
      const delta = gesture.currentX - base;

      if (!isOpenRef.current && !isLeftOpenRef.current) {
        if (gesture.currentX < -SWIPE_THRESHOLD) {
          onOpenRef.current();
        } else if (hasLeftAction && gesture.currentX > SWIPE_THRESHOLD) {
          onLeftOpenRef.current?.();
        } else {
          setTranslateX(0);
        }
      } else if (isOpenRef.current) {
        if (delta > SWIPE_THRESHOLD) {
          onCloseRef.current();
        } else {
          setTranslateX(-SWIPE_SNAP);
        }
      } else if (isLeftOpenRef.current) {
        if (delta < -SWIPE_THRESHOLD) {
          onLeftCloseRef.current?.();
        } else {
          setTranslateX(SWIPE_SNAP);
        }
      }
    }

    el.addEventListener("touchstart", onTouchStart, { passive: true });
    el.addEventListener("touchmove", onTouchMove, { passive: false });
    el.addEventListener("touchend", onTouchEnd, { passive: true });
    return () => {
      el.removeEventListener("touchstart", onTouchStart);
      el.removeEventListener("touchmove", onTouchMove);
      el.removeEventListener("touchend", onTouchEnd);
    };
  }, [hasLeftAction]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div
      className="relative overflow-hidden"
      style={{ borderBottom: borderBottom ? "1px solid var(--app-border)" : undefined }}
    >
      {hasLeftAction && (
        <div
          className="absolute left-0 top-0 bottom-0 flex items-center justify-center"
          style={{ width: SWIPE_SNAP, background: leftActionColor }}
        >
          <button
            type="button"
            className="w-full h-full flex items-center justify-center text-white text-sm font-semibold"
            onClick={onLeftActionClick}
          >
            {leftActionLabel}
          </button>
        </div>
      )}

      <div
        className="absolute right-0 top-0 bottom-0 flex items-center justify-center"
        style={{ width: SWIPE_SNAP, background: "var(--app-danger)" }}
      >
        <button
          type="button"
          className="w-full h-full flex items-center justify-center text-white text-sm font-semibold"
          onClick={onDeleteClick}
        >
          Delete
        </button>
      </div>

      <div
        ref={rowRef}
        style={{
          transform: `translateX(${translateX}px)`,
          transition: isDragging ? "none" : "transform 0.22s ease",
          background,
          touchAction: "pan-y",
          animationDelay: animationDelay !== undefined ? `${animationDelay}ms` : undefined,
        }}
        onClick={() => {
          if (isOpenRef.current) onCloseRef.current();
          else if (isLeftOpenRef.current) onLeftCloseRef.current?.();
        }}
      >
        {children}
      </div>
    </div>
  );
}
