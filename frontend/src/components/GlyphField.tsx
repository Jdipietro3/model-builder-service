"use client";

/**
 * GlyphField — the decorative background behind the pre-auth cards.
 *
 * A blurred field of mathematical glyphs, drawn on a single <canvas> and
 * driven by requestAnimationFrame. Each column has a bright "head" that
 * advances downward with a fading trail behind it (the drift), and every
 * visible glyph independently has a small per-tick chance of swapping to a
 * different glyph (the mutation). Both behaviours matter: drift alone reads
 * as Matrix rain, mutation alone reads as static noise — together it reads
 * as a field of computation happening behind the glass.
 *
 * Why one <canvas> instead of DOM nodes: this sits behind a sign-in form on
 * a route that gets rendered constantly (every 401 lands here). Hundreds of
 * animated DOM nodes would jank; one canvas redrawn on a throttled loop does
 * not. Do not "componentize" this into per-glyph elements.
 *
 * Why prefers-reduced-motion is load-bearing, not decorative: a full-bleed
 * animated background sitting directly behind a form a user is trying to
 * read is a textbook vestibular trigger. When the media query matches we
 * draw exactly one static frame and never start the rAF loop — and we keep
 * listening for the query to change mid-session (OS-level settings changes
 * can fire while the tab is open), not just its value at mount.
 *
 * Why we pause on visibilitychange: this canvas has no viewer when the tab
 * is backgrounded. Letting rAF keep ticking would burn a core for a canvas
 * nobody can see, on a page (auth) users commonly leave open in a background
 * tab. We cancel the frame on hide and restart the loop on show.
 *
 * Why we throttle glyph state to ~15-18Hz while still using rAF: the visual
 * effect is *better* slower — mathematical mutation reads as considered, not
 * frantic — and it cuts the cost of the (larger, blur-heavy) redraw to a
 * fraction of running it every frame. rAF is kept for smooth scheduling and
 * because it auto-throttles/suspends per platform conventions; we just skip
 * the actual draw+advance until enough wall time has passed.
 *
 * Why cleanup is exhaustive: this component unmounts on every successful
 * sign-in (the router navigates away from /login or /signup). A leaked rAF
 * handle or a leaked listener here is not a hypothetical — it fires on the
 * app's single most common navigation event.
 */

import { useEffect, useRef } from "react";

const GLYPHS =
  "0123456789+−×÷=≠≤≥±∓√∑∏∫∂∇∞∈∉⊂∪∩∀∃¬∧∨→⇒≈≡⌈⌉⌊⌋πθλμσφψΔΩΓβαερτχ".split("");

// Amber only, head to tail. No other hue may appear here — see DESIGN.md's
// One Signal Rule.
const HEAD_COLOR = "#edb55c"; // --accent-bright
const MID_COLOR = "#d08f2c"; // --accent
const DIM_COLOR = "#85541a"; // --accent-dim

// A literal font stack, NOT `var(--font-mono, …)`.
//
// Canvas parses `ctx.font` as a CSS font shorthand but does not resolve CSS
// custom properties in it. An unparseable value is silently IGNORED — no
// throw, no warning — leaving the context on its default `10px sans-serif`.
// That is what happened here: glyphs rendered at 10px sans into an 18px grid
// and, once blurred, read as horizontal smears rather than characters.
// Verified in-page: assigning the var() form left ctx.font as "10px
// sans-serif", while this literal stack takes effect.
const CANVAS_FONT_STACK = `ui-monospace, "Cascadia Mono", "Segoe UI Mono", "DejaVu Sans Mono", "Liberation Mono", monospace`;

const FONT_PX = 15;
const COLUMN_PX = 18;
const TRAIL_LENGTH = 14;
const ADVANCE_INTERVAL_MS = 1000 / 16; // ~16 updates/sec, per spec (15-18Hz)
const MUTATE_CHANCE = 0.04; // per glyph, per advance tick
const MAX_DPR = 2;

function randomGlyph(): string {
  return GLYPHS[(Math.random() * GLYPHS.length) | 0];
}

interface Column {
  headRow: number;
  speed: number; // rows per advance tick
  progress: number; // fractional row progress toward next advance
  glyphs: string[]; // one glyph per row slot in this column, reused as a ring
  rows: number;
}

export default function GlyphField() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reducedMotionQuery = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    );

    let columns: Column[] = [];
    let rafId: number | null = null;
    let lastAdvance = 0;
    let running = false;
    // Cached CSS-pixel size, refreshed only by sizeCanvas(). The draw loop
    // reads this instead of calling getBoundingClientRect() per frame, which
    // forces a synchronous layout to re-read a value that changes only on
    // resize.
    let cssSize = { width: 1, height: 1 };

    function buildColumns(width: number, height: number) {
      const rows = Math.ceil(height / COLUMN_PX) + TRAIL_LENGTH;
      const count = Math.ceil(width / COLUMN_PX);
      columns = Array.from({ length: count }, () => ({
        // Seeded across the visible range, not above it. Seeding negative (as
        // this first did) means draw() skips every row until the head climbs
        // past zero — at 16Hz that is up to 3.4s of a completely blank field
        // on first load. Columns re-enter from above on wrap; only the very
        // first frame needs to arrive already populated.
        headRow: Math.floor(Math.random() * rows),
        speed: 1,
        progress: 0,
        glyphs: Array.from({ length: rows }, randomGlyph),
        rows,
      }));
    }

    // Measure the PARENT, and never write canvas.style.width/height.
    //
    // The canvas gets its display size from CSS (`absolute inset-0 h-full
    // w-full`). Writing an inline width/height back onto it from its own
    // measured rect is circular: an inline style outranks the utility classes,
    // so whatever the canvas measures once, it pins itself to permanently. On
    // the first effect run — before layout had resolved `h-full` against the
    // flex parent — that measured 48x118 inside a 1280x720 <main>, and the
    // field could never grow back out of it, so nothing was visible.
    //
    // Measuring the parent breaks the cycle: the parent's size is decided by
    // layout, never by anything written here. Only the backing store (the
    // width/height attributes) is set, which is what those attributes are for.
    function sizeCanvas() {
      const rect = (canvas!.parentElement ?? canvas!).getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
      const width = Math.max(1, Math.floor(rect.width));
      const height = Math.max(1, Math.floor(rect.height));
      canvas!.width = Math.floor(width * dpr);
      canvas!.height = Math.floor(height * dpr);
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      cssSize = { width, height };
      buildColumns(width, height);
      return cssSize;
    }

    function drawStaticFrame() {
      const { width, height } = sizeCanvas();
      ctx!.clearRect(0, 0, width, height);
      ctx!.font = `${FONT_PX}px ${CANVAS_FONT_STACK}`;
      ctx!.textBaseline = "top";
      for (const col of columns) {
        const x = columns.indexOf(col) * COLUMN_PX;
        for (let r = 0; r < col.rows; r++) {
          const y = r * COLUMN_PX;
          if (y < -COLUMN_PX || y > height + COLUMN_PX) continue;
          ctx!.fillStyle = DIM_COLOR;
          ctx!.fillText(col.glyphs[r], x, y);
        }
      }
    }

    function advance() {
      for (const col of columns) {
        col.headRow += 1;
        if (col.headRow - TRAIL_LENGTH > col.rows) {
          col.headRow = -Math.floor(Math.random() * 20);
        }
        // Mutation: independent of drift, each glyph has a small chance to
        // become a different character on this tick.
        for (let r = 0; r < col.glyphs.length; r++) {
          if (Math.random() < MUTATE_CHANCE) {
            col.glyphs[r] = randomGlyph();
          }
        }
      }
    }

    function draw(width: number, height: number) {
      ctx!.clearRect(0, 0, width, height);
      ctx!.font = `${FONT_PX}px ${CANVAS_FONT_STACK}`;
      ctx!.textBaseline = "top";
      columns.forEach((col, i) => {
        const x = i * COLUMN_PX;
        for (let offset = 0; offset <= TRAIL_LENGTH; offset++) {
          const r = col.headRow - offset;
          if (r < 0 || r >= col.rows) continue;
          const y = r * COLUMN_PX;
          if (y < -COLUMN_PX || y > height + COLUMN_PX) continue;
          if (offset === 0) {
            ctx!.fillStyle = HEAD_COLOR;
          } else if (offset < TRAIL_LENGTH * 0.4) {
            ctx!.fillStyle = MID_COLOR;
          } else {
            ctx!.fillStyle = DIM_COLOR;
          }
          ctx!.globalAlpha = 1 - offset / TRAIL_LENGTH;
          ctx!.fillText(col.glyphs[r], x, y);
        }
      });
      ctx!.globalAlpha = 1;
    }

    function loop(timestamp: number) {
      if (!running) return;
      if (timestamp - lastAdvance >= ADVANCE_INTERVAL_MS) {
        lastAdvance = timestamp;
        advance();
        draw(cssSize.width, cssSize.height);
      }
      rafId = requestAnimationFrame(loop);
    }

    function start() {
      if (running) return;
      running = true;
      lastAdvance = 0;
      rafId = requestAnimationFrame(loop);
    }

    function stop() {
      running = false;
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
        rafId = null;
      }
    }

    function handleVisibility() {
      if (document.hidden) {
        stop();
      } else if (!reducedMotionQuery.matches) {
        start();
      }
    }

    // Resize immediately, with NO debounce.
    //
    // ResizeObserver already coalesces to at most one callback per frame, so a
    // timer buys nothing — it only opens a window in which the canvas keeps a
    // stale size. That window was a real bug: the first measurement can land
    // before layout has resolved (48x118 inside a 1280x720 <main> here), and
    // because the backing store is set from that while CSS still stretches the
    // element to full size, the browser scaled a 48px-wide bitmap across
    // 1280px — glyphs came out roughly 26x too large and unreadably smeared.
    function handleResize() {
      if (reducedMotionQuery.matches) {
        drawStaticFrame();
        return;
      }
      sizeCanvas();
      // Repaint at the new size straight away. Resizing a canvas clears it,
      // and rAF does not run while the tab is hidden, so without this the
      // field would sit blank until the tab was next shown.
      draw(cssSize.width, cssSize.height);
    }

    function handleReducedMotionChange() {
      if (reducedMotionQuery.matches) {
        stop();
        drawStaticFrame();
      } else if (!document.hidden) {
        start();
      }
    }

    // Initial setup.
    if (reducedMotionQuery.matches) {
      drawStaticFrame();
    } else {
      sizeCanvas();
      // Paint one frame synchronously before handing over to rAF. A page that
      // loads in a background tab receives no rAF callbacks at all, so without
      // this the field is still blank at the moment the tab is first revealed
      // and only fills in on the frame after that.
      draw(cssSize.width, cssSize.height);
      start();
    }

    // A ResizeObserver on the parent, not a window resize listener. Besides
    // covering window resizes (the parent resizes with it), it fires once
    // layout first resolves — which is what makes the initial measurement
    // trustworthy. A window listener alone can never correct a first
    // measurement taken before the flex parent had its height, which is
    // exactly how this started life 48px wide.
    const parent = canvas.parentElement;
    const observer = new ResizeObserver(handleResize);
    if (parent) observer.observe(parent);

    document.addEventListener("visibilitychange", handleVisibility);
    reducedMotionQuery.addEventListener("change", handleReducedMotionChange);

    return () => {
      stop();
      observer.disconnect();
      document.removeEventListener("visibilitychange", handleVisibility);
      reducedMotionQuery.removeEventListener(
        "change",
        handleReducedMotionChange,
      );
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 h-full w-full opacity-40 blur-[3px]"
    />
  );
}
