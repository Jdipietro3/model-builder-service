import { redirect } from "next/navigation";

// /projects/[id] has no content of its own — Model is the default tab.
export default async function ProjectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  redirect(`/projects/${id}/model`);
}
