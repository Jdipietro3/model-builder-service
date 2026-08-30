/**
 * A one-shot handoff for the first message of a brand-new project.
 *
 * `/` creates the project and navigates before the chat stream can run, because
 * streaming needs ProjectProvider's state machinery (cards mutate runs,
 * datasets and deployments as they arrive). Re-implementing that on the landing
 * page would be a second copy of the hardest code in the app.
 *
 * So the text is parked here, and ProjectProvider claims it on mount. Module
 * scope, not sessionStorage, deliberately: it survives client-side navigation
 * but NOT a reload, which is what we want — a refresh should never silently
 * re-send a message the user already sent.
 */

let pending: { projectId: string; message: string } | null = null;

export function setPendingMessage(projectId: string, message: string): void {
  pending = { projectId, message };
}

/** Returns the pending message for this project and clears it, so a remount
 *  (React strict mode double-invokes effects in dev) cannot send it twice. */
export function takePendingMessage(projectId: string): string | null {
  if (pending?.projectId !== projectId) return null;
  const { message } = pending;
  pending = null;
  return message;
}

/** Name a new project from whatever the user gave us first, so the rail never
 *  fills up with "Untitled". Kept client-side: the backend has no rename route,
 *  so the name has to be right at creation time. */
export function deriveProjectName(source: string, kind: "message" | "filename"): string {
  if (kind === "filename") {
    const base = source.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();
    return base ? base.slice(0, 60) : "New project";
  }
  const flat = source.replace(/\s+/g, " ").trim();
  if (!flat) return "New project";
  if (flat.length <= 40) return flat;
  // Trim at the last word boundary inside the cap rather than mid-word.
  const cut = flat.slice(0, 40);
  const lastSpace = cut.lastIndexOf(" ");
  return (lastSpace > 20 ? cut.slice(0, lastSpace) : cut) + "…";
}
