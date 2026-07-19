"use client";

import { useState } from "react";
import { Profile } from "@/lib/api";

export default function ProfileCard({
  filename,
  profile,
}: {
  filename: string;
  profile: Profile | null;
}) {
  const [expanded, setExpanded] = useState(false);
  if (!profile) return null;

  const shown = expanded ? profile.columns : profile.columns.slice(0, 8);

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/60">
      <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="rounded bg-sky-950 px-2 py-0.5 text-xs font-medium text-sky-300">
            DATASET
          </span>
          <span className="font-mono text-sm text-zinc-300">{filename}</span>
        </div>
        <span className="text-xs text-zinc-500">
          {profile.n_rows.toLocaleString()} rows × {profile.n_cols} columns
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-zinc-800 text-zinc-500">
              <th className="px-4 py-2 font-medium">Column</th>
              <th className="px-2 py-2 font-medium">Kind</th>
              <th className="px-2 py-2 font-medium">Unique</th>
              <th className="px-2 py-2 font-medium">Missing</th>
              <th className="px-4 py-2 font-medium">Sample values</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((c) => (
              <tr key={c.name} className="border-b border-zinc-800/50 last:border-0">
                <td className="px-4 py-1.5 font-mono text-zinc-200">
                  {c.name}
                  {profile.target_candidates.includes(c.name) && (
                    <span
                      className="ml-1.5 rounded bg-emerald-950 px-1 py-0.5 text-[10px] text-emerald-400"
                      title="Candidate target column"
                    >
                      target?
                    </span>
                  )}
                </td>
                <td className="px-2 py-1.5 text-zinc-400">{c.kind}</td>
                <td className="px-2 py-1.5 text-zinc-400">{c.n_unique.toLocaleString()}</td>
                <td className="px-2 py-1.5 text-zinc-400">
                  {c.pct_missing > 0 ? `${c.pct_missing}%` : "—"}
                </td>
                <td className="max-w-64 truncate px-4 py-1.5 font-mono text-zinc-500">
                  {c.top_values?.length
                    ? c.top_values.map((t) => `${t.value} (${t.pct}%)`).join(", ")
                    : c.sample_values.join(", ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {profile.columns.length > 8 && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full py-2 text-xs text-zinc-500 transition-colors hover:text-zinc-300"
        >
          {expanded ? "Show less" : `Show all ${profile.columns.length} columns`}
        </button>
      )}

      {profile.warnings.length > 0 && (
        <div className="border-t border-zinc-800 px-4 py-2.5">
          {profile.warnings.map((w, i) => (
            <p key={i} className="text-xs text-amber-400/90">
              ⚠ {w}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
