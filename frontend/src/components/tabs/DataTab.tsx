"use client";

/**
 * Data tab: the training data and its version chain.
 *
 * Lifted from Workspace's DatasetSection/DatasetUpdateControl essentially
 * verbatim — only the prop plumbing changed, since state now comes from
 * ProjectProvider rather than from a parent component.
 *
 * Scoped to data the model trains ON. Data you predict on lives in the Score
 * tab; they read as the same noun but they are different jobs.
 */

import { useRef, useState } from "react";
import { Dataset } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { extractErrorDetail } from "@/lib/errors";
import { isChainTip } from "@/lib/dataset-chain";
import ProfileCard from "@/components/cards/ProfileCard";
import EmptyTab from "@/components/tabs/EmptyTab";

/** Inline "Update" control for a dataset chain tip: file picker, then a
 * Replace/Append/Cancel choice once a file is staged. */
function DatasetUpdateControl({
  dataset,
  onUploadDatasetUpdate,
}: {
  dataset: Dataset;
  onUploadDatasetUpdate: (
    datasetId: string,
    file: File,
    mode: "replace" | "append",
  ) => Promise<void>;
}) {
  const [pending, setPending] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function submit(mode: "replace" | "append") {
    if (!pending) return;
    setBusy(true);
    setError(null);
    try {
      await onUploadDatasetUpdate(dataset.id, pending, mode);
      setPending(null);
    } catch (e) {
      // Also surfaced by the caller as a chat message; additionally shown here,
      // inline next to the control the user was actually operating.
      setError(extractErrorDetail(e));
    } finally {
      setBusy(false);
    }
  }

  if (pending) {
    return (
      <div className="flex shrink-0 flex-col items-end gap-1" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-1.5 text-label">
          <span className="max-w-28 truncate font-mono text-zinc-400" title={pending.name}>
            {pending.name}
          </span>
          <button
            type="button"
            onClick={() => submit("replace")}
            disabled={busy}
            className="focus-ring-panel rounded border border-zinc-700 px-2 py-0.5 text-zinc-300 transition-colors hover:border-emerald-600 hover:text-emerald-400 disabled:opacity-40"
          >
            Replace
          </button>
          <button
            type="button"
            onClick={() => submit("append")}
            disabled={busy}
            className="focus-ring-panel rounded border border-zinc-700 px-2 py-0.5 text-zinc-300 transition-colors hover:border-emerald-600 hover:text-emerald-400 disabled:opacity-40"
          >
            Append
          </button>
          <button
            type="button"
            onClick={() => {
              setPending(null);
              setError(null);
            }}
            disabled={busy}
            aria-label="Cancel dataset update"
            title="Cancel"
            className="focus-ring-panel px-1 text-zinc-400 transition-colors hover:text-zinc-300 disabled:opacity-40"
          >
            ×
          </button>
        </div>
        {error && <span className="max-w-48 text-right text-label text-red-300">{error}</span>}
      </div>
    );
  }

  return (
    <div className="shrink-0" onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        className="focus-ring-panel cursor-pointer text-label text-zinc-400 transition-colors hover:text-emerald-400"
      >
        Update
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".csv"
        className="sr-only"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) setPending(f);
          e.target.value = "";
        }}
      />
    </div>
  );
}

export default function DataTab() {
  const { datasets, handleUpload, handleUpdateDataset } = useProject();
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const addInputRef = useRef<HTMLInputElement>(null);

  // Only chain tips are shown — an updated dataset supersedes its parent in the list.
  const tips = datasets.filter((d) => isChainTip(d, datasets));

  return (
    <section>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-headline font-semibold text-zinc-100">Data</h2>
        <button
          type="button"
          onClick={() => addInputRef.current?.click()}
          className="focus-ring cursor-pointer text-label text-zinc-400 transition-colors hover:text-emerald-400"
        >
          + Add dataset
        </button>
        <input
          ref={addInputRef}
          type="file"
          accept=".csv"
          className="sr-only"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleUpload(f);
            e.target.value = "";
          }}
        />
      </div>

      {datasets.length === 0 ? (
        <EmptyTab
          title="No data yet"
          body="Upload a CSV with + Add dataset above, then tell the assistant what you want to predict."
        />
      ) : (
        <div className="space-y-2">
          {tips.map((d) => (
            <div key={d.id}>
              <div className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/60 px-4 py-2.5 transition-colors hover:border-zinc-700">
                <button
                  onClick={() => setOpen((prev) => ({ ...prev, [d.id]: !prev[d.id] }))}
                  className="focus-ring-panel flex min-w-0 flex-1 items-center justify-between text-left"
                >
                  <span className="flex items-center gap-1.5 truncate font-mono text-xs text-zinc-300">
                    {d.filename}
                    {(d.version ?? 1) > 1 && (
                      <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-sans text-label font-medium text-zinc-400">
                        v{d.version}
                      </span>
                    )}
                  </span>
                  <span className="shrink-0 pl-2 text-label text-zinc-400">
                    {d.profile
                      ? `${d.profile.n_rows.toLocaleString()} rows × ${d.profile.n_cols} cols`
                      : ""}{" "}
                    {open[d.id] ? "▾" : "▸"}
                  </span>
                </button>
                <DatasetUpdateControl dataset={d} onUploadDatasetUpdate={handleUpdateDataset} />
              </div>
              {open[d.id] && (
                <div className="mt-2">
                  <ProfileCard filename={d.filename} profile={d.profile} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
