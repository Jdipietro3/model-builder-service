"use client";

/**
 * Threads the rail's collapsed state down to ProjectNav.
 *
 * ProjectNav is instantiated by projects/[id]/layout.tsx — a server component —
 * and handed to Sidebar as the `nav` prop, so Sidebar cannot pass `collapsed`
 * to it as an ordinary prop; it can only wrap it as a child. Context closes
 * that gap without turning the layout into a client component or moving
 * ProjectNav's construction into Sidebar itself.
 */

import { createContext, useContext } from "react";

type RailCollapsedContextValue = {
  collapsed: boolean;
  setCollapsed: (collapsed: boolean) => void;
};

const RailCollapsedContext = createContext<RailCollapsedContextValue | null>(null);

export function RailCollapsedProvider({
  value,
  children,
}: {
  value: RailCollapsedContextValue;
  children: React.ReactNode;
}) {
  return <RailCollapsedContext.Provider value={value}>{children}</RailCollapsedContext.Provider>;
}

/** ProjectNav is only ever rendered as Sidebar's `nav` child, so a missing
 * provider means a caller wired something up wrong — surface that immediately
 * rather than silently falling back to an always-expanded rail. */
export function useRailCollapsed(): RailCollapsedContextValue {
  const ctx = useContext(RailCollapsedContext);
  if (!ctx) {
    throw new Error("useRailCollapsed must be called from within Sidebar's rendered tree");
  }
  return ctx;
}
