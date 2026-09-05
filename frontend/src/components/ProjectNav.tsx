"use client";

/**
 * The rail's project view: title, model tree, tab list.
 *
 * Rendered by projects/[id]/layout.tsx from inside ProjectProvider, then handed
 * to <Sidebar nav={...} />. ModelTree writes the shared selectedRunId, which
 * every tab reads — that ambient selection is what lets Score and Metrics
 * exist as their own tabs without each growing a second run picker.
 *
 * Collapsed rendering lives here rather than in Sidebar because the tab list
 * (slug, label, icon) must stay defined in exactly one place — duplicating it
 * into Sidebar for the collapsed case would drift the moment a tab is added or
 * renamed. Sidebar only tells this component whether to collapse, via
 * useRailCollapsed(); the title and ModelTree simply have no collapsed form
 * (a tree can't usefully shrink to one glyph) and are omitted rather than
 * crammed into 40px.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useProject } from "@/lib/project-context";
import { useRailCollapsed } from "@/components/rail-context";
import ModelTree from "@/components/ModelTree";
import {
  ModelIcon,
  DataIcon,
  MetricsIcon,
  ScoreIcon,
  DeployIcon,
  LayersIcon,
} from "@/components/RailIcons";

const TABS = [
  { slug: "model", label: "Model", Icon: ModelIcon },
  { slug: "data", label: "Data", Icon: DataIcon },
  { slug: "metrics", label: "Metrics", Icon: MetricsIcon },
  { slug: "score", label: "Score", Icon: ScoreIcon },
  { slug: "deploy", label: "Deploy", Icon: DeployIcon },
] as const;

export default function ProjectNav() {
  const { projectId, project } = useProject();
  const pathname = usePathname();
  const { collapsed, setCollapsed } = useRailCollapsed();

  if (collapsed) {
    return (
      <div className="flex flex-col items-center gap-1">
        <button
          onClick={() => setCollapsed(false)}
          aria-label="Show models"
          title="Show models"
          className="focus-ring-panel flex h-10 w-10 items-center justify-center rounded text-zinc-400 transition-colors hover:bg-zinc-900 hover:text-zinc-100"
        >
          <LayersIcon size={18} />
        </button>

        {TABS.map(({ slug, label, Icon }) => {
          const href = `/projects/${projectId}/${slug}`;
          const active = pathname === href;
          return (
            <Link
              key={slug}
              href={href}
              aria-current={active ? "page" : undefined}
              aria-label={label}
              title={label}
              className={`focus-ring-panel flex h-10 w-10 items-center justify-center rounded transition-colors ${
                active
                  ? "bg-zinc-900 font-medium text-accent"
                  : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100"
              }`}
            >
              <Icon size={18} />
            </Link>
          );
        })}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-3">
      <h1 className="px-1 text-title font-semibold text-zinc-100" title={project?.name}>
        {project?.name ?? "…"}
      </h1>

      <ModelTree />

      <ul className="space-y-0.5">
        {TABS.map(({ slug, label }) => {
          const href = `/projects/${projectId}/${slug}`;
          const active = pathname === href;
          return (
            <li key={slug}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={`focus-ring-panel block rounded px-2 py-1.5 text-body transition-colors ${
                  active
                    ? "bg-zinc-900 font-medium text-accent"
                    : "text-zinc-300 hover:bg-zinc-900 hover:text-zinc-100"
                }`}
              >
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
