"use client";

import { ReactNode, useEffect, useRef } from "react";

/**
 * Confirmation gate for irreversible actions.
 *
 * DESIGN.md's product bans say "modal as first thought is usually laziness —
 * exhaust inline / progressive alternatives first." This is the deliberate
 * exception: promoting a deployment swaps the model answering real prediction
 * traffic, cannot be undone, and affects callers who are not in the room. That
 * is the narrow case a modal is for. Do not reach for this component for
 * anything reversible.
 *
 * Built on native <dialog> + showModal(), which gives us the top layer (no
 * z-index needed), a focus trap, Esc-to-dismiss, and inert background content
 * for free — all things a hand-rolled overlay gets wrong.
 */
export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  cancelLabel = "Cancel",
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  body: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  // Esc and backdrop-dismiss both fire `cancel`/`close` natively; route them
  // back through onCancel so parent state can't drift out of sync with the
  // element's own open state.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const handleCancel = (e: Event) => {
      e.preventDefault();
      if (!busy) onCancel();
    };
    el.addEventListener("cancel", handleCancel);
    return () => el.removeEventListener("cancel", handleCancel);
  }, [onCancel, busy]);

  return (
    <dialog
      ref={ref}
      aria-labelledby="confirm-dialog-title"
      className="m-auto w-[min(32rem,calc(100vw-2rem))] rounded-lg border border-zinc-700 bg-zinc-900 p-0 text-zinc-200 backdrop:bg-zinc-950/70"
      onClick={(e) => {
        // Clicking the backdrop (the dialog element itself, outside the inner
        // panel) dismisses. Clicks inside the panel stop at the panel.
        if (e.target === ref.current && !busy) onCancel();
      }}
    >
      <div className="p-5">
        <h2 id="confirm-dialog-title" className="text-title font-medium text-zinc-100">
          {title}
        </h2>
        <div className="measure mt-2 text-body text-zinc-300">{body}</div>
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="focus-ring-panel rounded-lg px-4 py-2 text-body font-medium text-zinc-300 transition-colors hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-40"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="focus-ring-panel rounded-lg bg-accent px-4 py-2 text-body font-medium text-accent-ink transition-colors hover:bg-accent-bright disabled:opacity-40"
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </dialog>
  );
}
