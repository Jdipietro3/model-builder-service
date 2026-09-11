"use client";

/**
 * The assistant, pinned to the right of every project tab.
 *
 * Same treatment the old workspace mode used: compact cards (reference chips
 * rather than full cards, since the tab beside it renders the real thing) and
 * no upload button — CSVs go through the Data tab, which is where dataset
 * versions live.
 *
 * Width (and full screen) are owned by ResizableSplit, which renders this
 * component as its right pane — that's why the root here is `h-full w-full`
 * rather than a fixed width. Full screen toggles ResizableSplit's own state
 * via useSplitFullScreen rather than any local state, so streaming chat
 * (held in ProjectProvider, above this component) is never affected by it.
 */

import { useEffect, useRef } from "react";
import { MessageView, StreamingMessage } from "@/components/Chat";
import Composer from "@/components/Composer";
import { useProject } from "@/lib/project-context";
import { useSplitFullScreen } from "@/components/ResizableSplit";

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

  const { isFullScreen, toggleFullScreen } = useSplitFullScreen();

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
    <aside className="flex h-full w-full flex-col border-l border-zinc-800 bg-zinc-950">
      <div className="flex shrink-0 items-center justify-between border-b border-zinc-800 px-4 py-2.5">
        <span className="text-label font-medium uppercase tracking-wide text-zinc-400">
          Assistant
        </span>
        <button
          type="button"
          onClick={toggleFullScreen}
          aria-pressed={isFullScreen}
          aria-label={isFullScreen ? "Exit full screen" : "Expand assistant to full screen"}
          className="focus-ring-panel rounded p-1 text-zinc-400 transition-colors hover:bg-zinc-900 hover:text-accent"
        >
          {isFullScreen ? (
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
              <path
                d="M5.5 1.5v2a2 2 0 0 1-2 2h-2M8.5 1.5v2a2 2 0 0 0 2 2h2M5.5 12.5v-2a2 2 0 0 0-2-2h-2M8.5 12.5v-2a2 2 0 0 1 2-2h2"
                stroke="currentColor"
                strokeWidth="1.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
              <path
                d="M1.5 5.5v-2a2 2 0 0 1 2-2h2M12.5 5.5v-2a2 2 0 0 0-2-2h-2M1.5 8.5v2a2 2 0 0 0 2 2h2M12.5 8.5v2a2 2 0 0 1-2 2h-2"
                stroke="currentColor"
                strokeWidth="1.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          )}
        </button>
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
