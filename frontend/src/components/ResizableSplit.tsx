"use client";

/**
 * A draggable vertical split between the tab content and the assistant rail.
 *
 * The right pane's width is user-resizable (pointer drag on the handle, or
 * arrow/Home/End keys when it has focus) and persisted to localStorage so it
 * survives navigation and reload. The left pane is rendered untouched — it
 * keeps its own `min-w-0 flex-1` sizing from the caller — so this component
 * only ever styles the handle and the right-pane wrapper.
 *
 * Full screen is an overlay, not a conditional render: the right pane's
 * wrapper goes `absolute inset-0` and paints over the left pane instead of
 * the left pane being hidden or removed. Nothing about the left pane's tree
 * changes, so ChatRail and the tab content (both of which hold state across
 * an SSE stream) never unmount when the assistant expands or collapses.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

type SplitFullScreenContextValue = {
  isFullScreen: boolean;
  toggleFullScreen: () => void;
  exitFullScreen: () => void;
};

const SplitFullScreenContext = createContext<SplitFullScreenContextValue | null>(null);

/** Lets content rendered as `right` (ChatRail's header button) drive the
 * split's full-screen state without ResizableSplit knowing anything about
 * what it's rendering. Must be called from inside the `right` subtree. */
export function useSplitFullScreen(): SplitFullScreenContextValue {
  const ctx = useContext(SplitFullScreenContext);
  if (!ctx) {
    throw new Error("useSplitFullScreen must be called from within ResizableSplit's right pane");
  }
  return ctx;
}

const STORAGE_PREFIX = "metis:split-width:";
const KEYBOARD_STEP_PX = 24;
// Larger than any real container could produce; used to mean "as wide as the
// clamp allows" when nudging to the End key extreme.
const LARGE_WIDTH_PX = 1_000_000;

function readStoredWidth(storageKey: string, fallback: number): number {
  try {
    const raw = window.localStorage.getItem(STORAGE_PREFIX + storageKey);
    if (raw === null) return fallback;
    const parsed = Number(raw);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
  } catch {
    return fallback;
  }
}

function writeStoredWidth(storageKey: string, widthPx: number) {
  try {
    window.localStorage.setItem(STORAGE_PREFIX + storageKey, String(Math.round(widthPx)));
  } catch {
    // Persistence is a decorative preference — storage throwing (private
    // browsing, quota, disabled storage) must never break the split.
  }
}

export default function ResizableSplit({
  left,
  right,
  storageKey,
  leftMinPx = 320,
  rightMinPx = 320,
  defaultRightPx = 380,
  ariaLabel = "Resize panel",
}: {
  left: React.ReactNode;
  right: React.ReactNode;
  /** Distinguishes this split's stored width from any other on the page. */
  storageKey: string;
  leftMinPx?: number;
  rightMinPx?: number;
  defaultRightPx?: number;
  ariaLabel?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);

  // Seeded with the default so the server-rendered markup and the first
  // client render agree; the stored value (if any) is only applied from an
  // effect, after hydration, never read during render.
  const [rightWidth, setRightWidth] = useState(defaultRightPx);
  const [isDragging, setIsDragging] = useState(false);
  const [isFullScreen, setIsFullScreen] = useState(false);
  const [containerWidth, setContainerWidth] = useState<number | null>(null);

  const clamp = useCallback(
    (widthPx: number) => {
      const measured = containerRef.current?.getBoundingClientRect().width;
      const totalWidth = measured ?? widthPx + leftMinPx;
      const maxRight = Math.max(rightMinPx, totalWidth - leftMinPx);
      return Math.min(Math.max(widthPx, rightMinPx), maxRight);
    },
    [leftMinPx, rightMinPx],
  );

  const commitWidth = useCallback(
    (widthPx: number) => {
      setRightWidth((current) => {
        const next = clamp(widthPx);
        if (next !== current) writeStoredWidth(storageKey, next);
        return next;
      });
    },
    [clamp, storageKey],
  );

  // Applies the stored width once, after hydration — reading localStorage
  // during render would make the client's first paint diverge from the
  // server-rendered markup (which has no access to it) and trip a mismatch.
  useEffect(() => {
    commitWidth(readStoredWidth(storageKey, defaultRightPx));
    // Only on mount / storageKey change — including commitWidth here is
    // unnecessary (it's stable across the inputs that matter) and would risk
    // re-running this on every drag.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  // Keeps aria-valuemax honest across window resizes; the actual drag clamp
  // above measures the container directly and does not depend on this.
  useEffect(() => {
    function measure() {
      setContainerWidth(containerRef.current?.getBoundingClientRect().width ?? null);
    }
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  useEffect(() => {
    if (containerWidth == null) return;
    commitWidth(rightWidth);
    // Re-clamp only when the container itself changes size, not on every
    // width commit (which would re-run this and fight the drag).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [containerWidth]);

  useEffect(() => {
    if (!isFullScreen) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setIsFullScreen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isFullScreen]);

  // Belt-and-suspenders: if this unmounts mid-drag, don't leave the page
  // with text selection disabled.
  useEffect(() => {
    return () => {
      if (draggingRef.current) {
        draggingRef.current = false;
        try {
          document.body.style.userSelect = "";
        } catch {
          // best effort
        }
      }
    };
  }, []);

  function handlePointerDown(e: React.PointerEvent<HTMLDivElement>) {
    if (isFullScreen) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    draggingRef.current = true;
    setIsDragging(true);
    try {
      document.body.style.userSelect = "none";
    } catch {
      // best effort
    }
  }

  function handlePointerMove(e: React.PointerEvent<HTMLDivElement>) {
    if (!draggingRef.current) return;
    const container = containerRef.current;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    commitWidth(rect.right - e.clientX);
  }

  function endDrag(e: React.PointerEvent<HTMLDivElement>) {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    setIsDragging(false);
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      // capture may already be gone
    }
    try {
      document.body.style.userSelect = "";
    } catch {
      // best effort
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (isFullScreen) return;
    switch (e.key) {
      case "ArrowLeft":
        e.preventDefault();
        commitWidth(rightWidth - KEYBOARD_STEP_PX);
        break;
      case "ArrowRight":
        e.preventDefault();
        commitWidth(rightWidth + KEYBOARD_STEP_PX);
        break;
      case "Home":
        e.preventDefault();
        commitWidth(0);
        break;
      case "End":
        e.preventDefault();
        commitWidth(LARGE_WIDTH_PX);
        break;
      default:
        break;
    }
  }

  const maxRightPx =
    containerWidth != null ? Math.max(rightMinPx, containerWidth - leftMinPx) : rightWidth;

  const fullScreenCtx: SplitFullScreenContextValue = {
    isFullScreen,
    toggleFullScreen: () => setIsFullScreen((v) => !v),
    exitFullScreen: () => setIsFullScreen(false),
  };

  return (
    <div ref={containerRef} className="relative flex h-full min-w-0 flex-1 overflow-hidden">
      {left}

      <div
        role="separator"
        aria-orientation="vertical"
        aria-label={ariaLabel}
        aria-valuenow={Math.round(rightWidth)}
        aria-valuemin={rightMinPx}
        aria-valuemax={Math.round(maxRightPx)}
        tabIndex={0}
        hidden={isFullScreen}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onKeyDown={handleKeyDown}
        className="focus-ring group relative z-10 w-2 shrink-0 cursor-col-resize touch-none select-none"
      >
        <div
          className={`pointer-events-none absolute inset-y-0 left-1/2 w-px -translate-x-1/2 transition-colors motion-reduce:transition-none ${
            isDragging ? "bg-accent-edge" : "bg-zinc-800 group-hover:bg-accent-edge"
          }`}
        />
      </div>

      <div
        className={
          isFullScreen
            ? "absolute inset-0 z-20 flex h-full min-w-0 flex-col"
            : "flex h-full min-w-0 shrink-0 flex-col"
        }
        style={isFullScreen ? undefined : { width: rightWidth }}
      >
        <SplitFullScreenContext.Provider value={fullScreenCtx}>
          {right}
        </SplitFullScreenContext.Provider>
      </div>
    </div>
  );
}
