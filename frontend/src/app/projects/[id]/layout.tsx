/**
 * Owns ProjectProvider for the whole /projects/[id] subtree, so the SSE
 * training streams and chat state survive navigation between tabs (each tab
 * is a sibling route segment that mounts/unmounts on its own — see
 * project-context.tsx for why that matters).
 *
 * ProjectNav is rendered here, inside the provider, then handed down to
 * Sidebar as the `nav` prop — Sidebar itself renders outside any project
 * context so it can also serve the project-less `/` route.
 */

import { ProjectProvider } from "@/lib/project-context";
import Sidebar from "@/components/Sidebar";
import ProjectNav from "@/components/ProjectNav";
import ChatRail from "@/components/ChatRail";
import ProjectGate from "@/components/ProjectGate";
import ResizableSplit from "@/components/ResizableSplit";

export default async function ProjectLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <ProjectProvider projectId={id}>
      <div className="flex h-full">
        <Sidebar nav={<ProjectNav />} />
        <ResizableSplit
          storageKey="chat-rail"
          leftMinPx={360}
          rightMinPx={320}
          defaultRightPx={380}
          ariaLabel="Resize assistant panel"
          left={
            <main className="min-w-0 flex-1 overflow-y-auto px-6 py-6">
              <ProjectGate>{children}</ProjectGate>
            </main>
          }
          right={<ChatRail />}
        />
      </div>
    </ProjectProvider>
  );
}
