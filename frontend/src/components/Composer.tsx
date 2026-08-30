"use client";

import { useRef } from "react";

/**
 * The message box: optional CSV upload button, textarea, send.
 *
 * Lifted out of the project page so the new-project screen at `/` and the chat
 * rail inside a project share one control rather than growing two that drift.
 */
export default function Composer({
  input,
  setInput,
  busy,
  onSend,
  onUpload,
  showUpload,
  placeholder,
}: {
  input: string;
  setInput: (v: string) => void;
  busy: boolean;
  onSend: () => void;
  onUpload: (f: File) => void;
  showUpload: boolean;
  placeholder?: string;
}) {
  // A <label> wrapping a display:none input is unreachable by keyboard — the
  // input leaves the tab order entirely and the label isn't focusable. Drive a
  // visually-hidden (but focusable-by-proxy) input from a real button instead.
  const uploadRef = useRef<HTMLInputElement>(null);

  return (
    <div className="flex items-end gap-2">
      {showUpload && (
        <>
          <input
            ref={uploadRef}
            type="file"
            accept=".csv"
            className="sr-only"
            tabIndex={-1}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onUpload(f);
              e.target.value = "";
            }}
          />
          <button
            type="button"
            onClick={() => uploadRef.current?.click()}
            disabled={busy}
            aria-label="Upload CSV"
            title="Upload CSV"
            className="focus-ring flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center rounded-lg border border-zinc-700 text-zinc-400 transition-colors hover:border-emerald-600 hover:text-emerald-500 disabled:pointer-events-none disabled:opacity-40"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              aria-hidden="true"
            >
              <path d="M12 16V4m0 0l-4 4m4-4l4 4" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3" strokeLinecap="round" />
            </svg>
          </button>
        </>
      )}
      <textarea
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            onSend();
          }
        }}
        rows={1}
        placeholder={busy ? "Working…" : (placeholder ?? "Ask about your data or model…")}
        className="focus-ring max-h-40 min-h-10 flex-1 resize-y rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2.5 text-body outline-none placeholder:text-zinc-400 focus:border-emerald-600"
      />
      <button
        onClick={onSend}
        disabled={busy || !input.trim()}
        className="focus-ring h-10 rounded-lg bg-emerald-600 px-4 text-body font-medium text-white transition-colors hover:bg-emerald-500 disabled:opacity-40"
      >
        Send
      </button>
    </div>
  );
}
