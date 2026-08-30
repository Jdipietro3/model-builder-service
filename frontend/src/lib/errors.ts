/**
 * Pull a readable message out of a thrown fetch error.
 *
 * `json()` in api.ts throws with the raw response body appended, so a FastAPI
 * error arrives as a string with a JSON blob somewhere inside it. Surfacing
 * `detail` is the difference between "Error: 400 {"detail":"Only CSV files are
 * supported in v1"}" and a sentence the user can act on.
 *
 * Lived as an identical private copy in both the project page and Workspace
 * before the tab split; one shared copy so the two cannot drift.
 */
export function extractErrorDetail(e: unknown): string {
  const msg = String(e instanceof Error ? e.message : e);
  const jsonStart = msg.indexOf("{");
  if (jsonStart >= 0) {
    try {
      const parsed = JSON.parse(msg.slice(jsonStart));
      if (parsed.detail) return String(parsed.detail);
    } catch {
      // fall through to raw message
    }
  }
  return msg;
}
