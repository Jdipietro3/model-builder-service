"use client";

/**
 * A collapsible section. One implementation, used everywhere something long
 * needs to start compressed.
 *
 * Built on native <details>/<summary> rather than a div with useState. That is
 * not laziness: the native element already gives correct keyboard operation
 * (Enter/Space), the right screen-reader semantics (a disclosure with an
 * expanded/collapsed state), and find-in-page that can reach inside a closed
 * section in Chromium. A hand-rolled version has to reimplement all of that and
 * usually reimplements none of it.
 *
 * Both controlled and uncontrolled use are supported. Uncontrolled (`defaultOpen`)
 * covers the common case; controlled (`open` + `onOpenChange`) exists because
 * the Deploy tab has to force its API-keys section open at the moment a key is
 * created — that key is the only copy of a secret the backend will ever return,
 * and it must not be created into a collapsed section the user cannot see.
 *
 * `meta` renders on the summary row and stays visible while closed. Use it so a
 * shut section still answers the obvious question — how many keys, how many
 * columns — without needing to be opened.
 */

import { ReactNode, useId, useState } from "react";

export default function Disclosure({
  summary,
  meta,
  children,
  defaultOpen = false,
  open,
  onOpenChange,
  className = "",
  summaryClassName = "",
  tone = "title",
}: {
  summary: ReactNode;
  /** Stays visible while collapsed — a count, a status, a short hint. */
  meta?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  /** Controlled mode: pass both `open` and `onOpenChange`. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
  summaryClassName?: string;
  /** `title` for a section heading, `label` for a smaller subsection. */
  tone?: "title" | "label";
}) {
  const id = useId();
  const controlled = open !== undefined;
  const [internalOpen, setInternalOpen] = useState(defaultOpen);
  const isOpen = controlled ? open : internalOpen;

  const summaryTone =
    tone === "title"
      ? "text-title font-medium text-zinc-100"
      : "text-label font-medium uppercase tracking-wide text-zinc-400";

  return (
    <details
      className={`group ${className}`}
      open={isOpen}
      // <details> toggles itself on click and on Enter/Space, then fires
      // onToggle. Mirroring that back into state keeps React's `open` in step
      // with what the element already did, so the native interaction keeps
      // working rather than being fought.
      onToggle={(e) => {
        const next = (e.currentTarget as HTMLDetailsElement).open;
        if (!controlled) setInternalOpen(next);
        onOpenChange?.(next);
      }}
    >
      <summary
        aria-controls={id}
        className={`focus-ring-panel flex cursor-pointer list-none items-center gap-2 rounded py-1 [&::-webkit-details-marker]:hidden ${summaryTone} ${summaryClassName}`}
      >
        <span
          aria-hidden="true"
          className="text-zinc-400 transition-transform duration-150 group-open:rotate-90"
        >
          ▸
        </span>
        <span className="min-w-0 flex-1">{summary}</span>
        {meta != null && (
          <span className="shrink-0 text-label font-normal normal-case text-zinc-400">{meta}</span>
        )}
      </summary>
      <div id={id} className="pt-3">
        {children}
      </div>
    </details>
  );
}
