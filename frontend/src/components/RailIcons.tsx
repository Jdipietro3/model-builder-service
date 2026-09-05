/**
 * The rail's icon set.
 *
 * These exist because the left rail collapses to a ~56px strip where the tab
 * labels are gone and the glyph is the only thing identifying a destination.
 * At that point the icons are not decoration — they are the navigation — so
 * they are drawn to one specification rather than sourced ad hoc:
 *
 *   - 24x24 viewBox, always. A mixed-viewBox set silently renders at mixed
 *     optical weights even when every `size` prop matches.
 *   - Stroked, never filled. `stroke="currentColor"` + `fill="none"` means a
 *     caller colors them with an ordinary text utility (`text-accent` when
 *     active, `text-zinc-400` at rest), the same way MetisMark works.
 *   - strokeWidth 1.6 with round caps and joins, uniformly. Weight is what the
 *     eye reads as "same family"; a 2.0 in among 1.6s looks like a bug.
 *   - Geometry inset to roughly 3.5..20.5, so no glyph optically outweighs
 *     another by running closer to its own edges.
 *
 * No icon library. Adding one for eleven glyphs would put a dependency (and its
 * tree-shaking behaviour) into the bundle to save less code than this file.
 *
 * Every icon here is `aria-hidden`. That is deliberate and not an oversight:
 * each is rendered inside a control that already carries an accessible name
 * (the visible label when the rail is open, an `aria-label` when it is
 * collapsed). Labelling the glyph too would announce the destination twice.
 */

type IconProps = { size?: number; className?: string };

function Icon({ size = 18, className, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

/** Model — three connected nodes. The trained thing itself. */
export function ModelIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="5" r="2.2" />
      <circle cx="5.5" cy="18" r="2.2" />
      <circle cx="18.5" cy="18" r="2.2" />
      <path d="M10.6 6.9 6.9 16.1M13.4 6.9l3.7 9.2M7.7 18h8.6" />
    </Icon>
  );
}

/** Data — a table: header row above two body rows, split by one column rule. */
export function DataIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
      <path d="M3.5 9.5h17M3.5 14.5h17M12 9.5v10" />
    </Icon>
  );
}

/** Metrics — bars on a baseline. Magnitude, which is what the tab reports. */
export function MetricsIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 20h16" />
      <path d="M7.5 20v-5.5M12 20V8M16.5 20v-8.5" />
    </Icon>
  );
}

/** Score — a crosshair. Aiming the model at rows it has not seen. */
export function ScoreIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="7.5" />
      <circle cx="12" cy="12" r="2.6" />
      <path d="M12 1.8v2.7M12 19.5v2.7M1.8 12h2.7M19.5 12h2.7" />
    </Icon>
  );
}

/** Deploy — lifting out of a tray. Shipping it somewhere it can be called. */
export function DeployIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 15.5V3.8" />
      <path d="M8 7.8 12 3.8l4 4" />
      <path d="M4.5 14.5v3.7a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-3.7" />
    </Icon>
  );
}

/** Models tree — a stack of rounds. Used where the tree itself needs a glyph. */
export function LayersIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="m12 3.5 8.5 4.5-8.5 4.5L3.5 8z" />
      <path d="m3.5 12.4 8.5 4.5 8.5-4.5" />
      <path d="m3.5 16.4 8.5 4.5 8.5-4.5" />
    </Icon>
  );
}

/** Projects — the list of them. */
export function ListIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M9 6.5h11.5M9 12h11.5M9 17.5h11.5" />
      <path d="M4.2 6.5h.01M4.2 12h.01M4.2 17.5h.01" />
    </Icon>
  );
}

/** New project. */
export function PlusIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 4.5v15M4.5 12h15" />
    </Icon>
  );
}

/** Account. */
export function UserIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="8.2" r="3.7" />
      <path d="M4.8 20.2a7.2 7.2 0 0 1 14.4 0" />
    </Icon>
  );
}

/** Sign out — leaving through the doorway. */
export function SignOutIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M14.5 4.5h3.7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2h-3.7" />
      <path d="M9.5 8 5.5 12l4 4" />
      <path d="M5.5 12h9" />
    </Icon>
  );
}

/**
 * The collapse/expand control.
 *
 * One glyph, not two: a panel outline with the divider drawn in, plus a
 * chevron that flips direction. Swapping between two different glyphs on
 * toggle makes the control read as two different buttons; flipping one part of
 * a stable glyph reads as one button changing state, which is what it is.
 */
export function PanelToggleIcon({ collapsed, ...props }: IconProps & { collapsed: boolean }) {
  return (
    <Icon {...props}>
      <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
      <path d="M9.5 4.5v15" />
      <path d={collapsed ? "m13.6 9.8 2.4 2.2-2.4 2.2" : "m16.4 9.8-2.4 2.2 2.4 2.2"} />
    </Icon>
  );
}
