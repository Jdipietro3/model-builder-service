"use client";

/**
 * The assistant, pinned to the right of every project tab.
 *
 * Same treatment the old workspace mode used: compact cards (reference chips
 * rather than full cards, since the tab beside it renders the real thing) and
 * no upload button — CSVs go through the Data tab, which is where dataset
 * versions live.
 */

import { useEffect, useRef } from "react";
import { MessageView, StreamingMessage } from "@/components/Chat";
import Composer from "@/components/Composer";
import { useProject } from "@/lib/project-context";

export default function ChatRail() {
  const {
    messages,
    streamText,
    streamCards,
    datasets,
    methodologies,
    runStates,
    approveRun,
    approveTournament,
    busy,
    input,
    setInput,
    send,
  } = useProject();

  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamText, streamCards]);

  const ctx = {
    datasets,
    methodologies,
    runStates,
    onApprove: approveRun,
    onApproveTournament: approveTournament,
    compact: true,
  };

  function doSend() {
    if (input.trim() && !busy) {
      send(input.trim());
      setInput("");
    }
  }

  return (
    <aside className="flex w-95 shrink-0 flex-col border-l border-zinc-800 bg-zinc-950">
      <div className="border-b border-zinc-800 px-4 py-2.5 text-label font-medium uppercase tracking-wide text-zinc-400">
        Assistant
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {messages.map((m) => (
          <MessageView key={m.id} message={m} {...ctx} />
        ))}
        {streamText !== null && (
          <StreamingMessage text={streamText} cards={streamCards} {...ctx} />
        )}
        <div ref={bottomRef} />
      </div>
      <div className="border-t border-zinc-800 p-3">
        <Composer
          input={input}
          setInput={setInput}
          busy={busy}
          onSend={doSend}
          onUpload={() => {}}
          showUpload={false}
        />
      </div>
    </aside>
  );
}
