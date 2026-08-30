"use client";

/**
 * The rail's project view: title, model tree, tab list.
 *
 * Rendered by projects/[id]/layout.tsx from inside ProjectProvider, then handed
 * to <Sidebar nav={...} />. ModelTree writes the shared selectedRunId, which
 * every tab reads — that ambient selection is what lets Score and Metrics
 * exist as their own tabs without each growing a second run picker.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useProject } from "@/lib/project-context";
import ModelTree from "@/components/ModelTree";

const TABS = [
  { slug: "model", label: "Model" },
  { slug: "data", label: "Data" },
  { slug: "metrics", label: "Metrics" },
  { slug: "score", label: "Score" },
  { slug: "deploy", label: "Deploy" },
] as const;

export default function ProjectNav() {
  const { projectId, project } = useProject();
  const pathname = usePathname();

  return (
    <div className="flex flex-col gap-4 p-3">
      <h1 className="px-1 text-title font-semibold text-zinc-100" title={project?.name}>
        {project?.name ?? "…"}
      </h1>

      <ModelTree />

      <ul className="space-y-0.5">
        {TABS.map((t) => {
          const href = `/projects/${projectId}/${t.slug}`;
          const active = pathname === href;
          return (
            <li key={t.slug}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={`focus-ring-panel block rounded px-2 py-1.5 text-body transition-colors ${
                  active
                    ? "bg-zinc-900 font-medium text-emerald-400"
                    : "text-zinc-300 hover:bg-zinc-900 hover:text-zinc-100"
                }`}
              >
                {t.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
