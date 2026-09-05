/**
 * One empty state, used by every tab.
 *
 * Splitting the old single scroll into five routes means a user can now land on
 * a tab before its content exists. Each one says what is missing and what to do
 * next, in the same shape, rather than rendering nothing and reading as broken.
 */
export default function EmptyTab({ title, body }: { title: string; body: string }) {
  return (
    <div className="px-1 py-10 text-center">
      <p className="font-medium text-zinc-300">{title}</p>
      <p className="measure mx-auto mt-1.5 text-body text-zinc-400">{body}</p>
    </div>
  );
}
