"use client";

import { memo } from "react";
import ReactMarkdown, { Components } from "react-markdown";
import remarkGfm from "remark-gfm";

// Assistant messages are markdown; render them themed to the dark zinc/emerald
// palette. Raw HTML in the source is ignored by react-markdown (no rehype-raw),
// so no sanitizer is needed.
const components: Components = {
  p: (props) => <p className="mb-3 leading-relaxed last:mb-0" {...props} />,
  ul: (props) => <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0" {...props} />,
  ol: (props) => <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0" {...props} />,
  h1: (props) => <h1 className="mb-2 mt-4 text-base font-semibold text-zinc-100 first:mt-0" {...props} />,
  h2: (props) => <h2 className="mb-2 mt-4 text-base font-semibold text-zinc-100 first:mt-0" {...props} />,
  h3: (props) => <h3 className="mb-2 mt-3 text-sm font-semibold text-zinc-100 first:mt-0" {...props} />,
  h4: (props) => <h4 className="mb-1 mt-3 text-sm font-semibold text-zinc-200 first:mt-0" {...props} />,
  a: (props) => (
    <a
      className="text-emerald-400 underline decoration-emerald-700 underline-offset-2 hover:text-emerald-300"
      target="_blank"
      rel="noreferrer"
      {...props}
    />
  ),
  code: (props) => (
    <code
      className="rounded bg-zinc-800 px-1 py-0.5 font-mono text-[0.85em] text-emerald-300"
      {...props}
    />
  ),
  pre: (props) => (
    <pre
      className="mb-3 overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-950 p-3 text-xs last:mb-0 [&>code]:bg-transparent [&>code]:p-0 [&>code]:text-zinc-200"
      {...props}
    />
  ),
  table: (props) => (
    <div className="mb-3 overflow-x-auto last:mb-0">
      <table className="w-full border-collapse text-xs" {...props} />
    </div>
  ),
  th: (props) => (
    <th className="border-b border-zinc-700 px-2 py-1 text-left font-semibold text-zinc-300" {...props} />
  ),
  td: (props) => <td className="border-b border-zinc-800 px-2 py-1 text-left" {...props} />,
  blockquote: (props) => (
    <blockquote className="mb-3 border-l-2 border-zinc-700 pl-3 italic text-zinc-400 last:mb-0" {...props} />
  ),
  strong: (props) => <strong className="font-semibold text-zinc-100" {...props} />,
  hr: (props) => <hr className="my-3 border-zinc-800" {...props} />,
};

export default memo(function Markdown({ text }: { text: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {text}
    </ReactMarkdown>
  );
});
