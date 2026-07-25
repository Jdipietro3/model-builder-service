---
name: Model Builder
description: Chat-driven ML model training for engineers, rendered as a calm instrument panel.
colors:
  ink-void: "#09090b"
  ink-panel: "#18181b"
  ink-raised: "#27272a"
  hairline: "#27272a"
  hairline-strong: "#3f3f46"
  ink-primary: "#f4f4f5"
  ink-secondary: "#d4d4d8"
  ink-muted: "#a1a1aa"
  ink-inert: "#71717a"
  signal-green: "#10b981"
  signal-green-deep: "#059669"
  signal-green-light: "#34d399"
  signal-green-wash: "#022c22"
  alarm-red: "#f87171"
  alarm-red-wash: "#450a0a"
  caution-amber: "#fcd34d"
  caution-amber-wash: "#451a03"
  readout-sky: "#7dd3fc"
  readout-sky-wash: "#082f49"
  bracket-violet: "#c4b5fd"
  bracket-violet-wash: "#2e1065"
typography:
  display:
    fontFamily: "Geist, system-ui, sans-serif"
    fontSize: "1.875rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Geist, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Geist, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "normal"
  body:
    fontFamily: "Geist, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "normal"
  label:
    fontFamily: "Geist, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 1.45
    letterSpacing: "normal"
  data:
    fontFamily: "Geist Mono, ui-monospace, monospace"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: "normal"
rounded:
  chip: "4px"
  panel: "8px"
  shell: "12px"
  pill: "9999px"
spacing:
  hair: "4px"
  tight: "8px"
  snug: "12px"
  base: "16px"
  loose: "24px"
  section: "40px"
components:
  button-primary:
    backgroundColor: "{colors.signal-green-deep}"
    textColor: "#ffffff"
    typography: "{typography.body}"
    rounded: "{rounded.panel}"
    padding: "10px 20px"
  button-primary-hover:
    backgroundColor: "{colors.signal-green}"
  button-ghost:
    backgroundColor: "{colors.ink-panel}"
    textColor: "{colors.ink-secondary}"
    typography: "{typography.label}"
    rounded: "{rounded.panel}"
    padding: "6px 12px"
  button-ghost-hover:
    backgroundColor: "{colors.ink-raised}"
    textColor: "{colors.ink-primary}"
  input-text:
    backgroundColor: "{colors.ink-panel}"
    textColor: "{colors.ink-primary}"
    typography: "{typography.body}"
    rounded: "{rounded.panel}"
    padding: "10px 16px"
  panel-surface:
    backgroundColor: "{colors.ink-panel}"
    textColor: "{colors.ink-secondary}"
    rounded: "{rounded.panel}"
    padding: "16px"
  chip-status:
    backgroundColor: "{colors.ink-raised}"
    textColor: "{colors.ink-muted}"
    typography: "{typography.label}"
    rounded: "{rounded.chip}"
    padding: "2px 8px"
---

# Design System: Model Builder

## 1. Overview

**Creative North Star: "The Instrument Panel"**

This is the console of a serious machine. A user comes here to read state, form judgment, and act: which model won, whether the evaluation is honest, what is serving traffic right now. The interface is the glass over the dials. It is not the subject. Every pixel that draws attention to itself is a pixel stolen from a readout the user needed.

The system is near-black, near-monochrome, and dense. One green carries every affirmative signal; four further hues carry status and nothing else. Depth is built from tonal layers of the same neutral rather than from shadow, so the surface reads as one continuous machined panel with elements cut into it, not as paper stacked on paper. Type is small and tight by design, because practitioners read tables and metrics here, not prose.

This system explicitly rejects the **black-box AutoML dashboard** (a score handed down with no visible mechanism), the **no-code business SaaS** (bright, rounded, illustrated, addressed to everyone), the **generic AI-chat wrapper** (a bubble stream with a sparkle and a gradient), and the **overloaded enterprise admin** (every control crammed in at equal weight with no hierarchy). The last of these is the live risk: this codebase drifts toward it every time a feature adds its own controls without ranking them.

**Key Characteristics:**
- Near-black neutral ground (`#09090b`) with two tonal layers above it
- Exactly one accent hue; status hues are semantic, never decorative
- Flat surfaces, hairline borders, no ambient shadow
- Dense by intent: 12px and 14px carry the working UI
- Monospace reserved strictly for machine-produced values

## 2. Colors

A machined graphite ground with a single instrument green, plus a four-hue status vocabulary that never appears for decoration.

### Primary
- **Signal Green** (`#10b981`, deep `#059669`, light `#34d399`, wash `#022c22`): the only accent in the system. Reserved for primary actions, the current selection, affirmative state (a run completed, a model is live, a recommendation stands), and focus. Its scarcity is what makes it readable as a signal.

### Neutral
- **Ink Void** (`#09090b`): the application ground. The page itself, and the deepest layer of any nested surface.
- **Ink Panel** (`#18181b`): the working surface. Cards, side panels, inputs, message backgrounds. The layer the user reads content off.
- **Ink Raised** (`#27272a`): the lifted layer. Hover states, chips, toolbars, selected rows. Also serves as the default hairline.
- **Hairline Strong** (`#3f3f46`): borders that must survive against a raised surface, and separators inside dense tables.
- **Ink Primary** (`#f4f4f5`): headings, the value the user came to read, active labels.
- **Ink Secondary** (`#d4d4d8`): body copy and sustained reading.
- **Ink Muted** (`#a1a1aa`): the floor for anything a human must read. Labels, captions, metadata, placeholders, secondary units.
- **Ink Inert** (`#71717a`): non-text only. Icon strokes, dividers, disabled marks, decorative rules.

### Tertiary
The status vocabulary. Each hue owns one meaning and is used at a wash background with a light foreground.

- **Alarm Red** (`#f87171` on wash `#450a0a`): failure, error, destructive confirmation, and the trust layer's leakage findings. Never used for emphasis.
- **Caution Amber** (`#fcd34d` on wash `#451a03`): warnings, caveats, degraded-but-working states, honest-evaluation caveats.
- **Readout Sky** (`#7dd3fc` on wash `#082f49`): neutral information, in-flight and streaming activity, comparison deltas.
- **Bracket Violet** (`#c4b5fd` on wash `#2e1065`): tournament and ensemble affordances only. This hue is a namespace, not a mood.

### Named Rules

**The One Signal Rule.** Signal Green is the only non-status hue in the system and must occupy under 10% of any screen. If two things on screen are green, at most one of them is an action; the other is state. Three green things means the screen has lost its hierarchy.

**The Inert Floor Rule.** `#71717a` (Ink Inert) is **prohibited for text of any size**. Computed from the token it measures 4.12:1 against the application ground; measured in the rendered page it is worse, **3.85:1**, because Tailwind v4's OKLCH pipeline resolves it nearer `rgb(109,109,109)`. Either way it fails WCAG AA. `#a1a1aa` (Ink Muted) is the floor for every readable string, including placeholders, and measures 7.75:1. This rule applies to the 98 existing call sites; they are debt, not precedent.

**The Semantic Hue Rule.** Red, amber, sky, and violet carry meaning only. A hue may never be chosen because a component needed visual variety. If a new feature wants a new color, it wants a new meaning, and it must justify that meaning before it gets a hue.

## 3. Typography

**Display Font:** Geist (with `system-ui`, `sans-serif`)
**Body Font:** Geist (same family, differentiated by weight and size)
**Label/Mono Font:** Geist Mono (with `ui-monospace`, `monospace`)

**Character:** One geometric grotesque doing all the work, which is correct for an instrument: consistent letterforms across labels, values, and prose mean the eye never re-calibrates. Contrast comes from weight and size, never from a second family. Geist Mono is the machine's voice; it appears wherever a value was computed rather than written.

### Hierarchy

A fixed rem ladder at roughly a 1.2 ratio. It is deliberately bottom-heavy: the two smallest steps carry the working interface, and the steps above exist to let regions outrank each other.

- **Display** (600, 1.875rem/30px, 1.2, `-0.02em`): page-level identity only. One per route, typically the project or app title. Never inside a panel.
- **Headline** (600, 1.25rem/20px, 1.3, `-0.01em`): the name of a major region the user navigates between. This step is currently missing from the codebase and is the primary tool for fixing flat, undifferentiated scrolls.
- **Title** (500, 1rem/16px, 1.4): card and section headings inside a region.
- **Body** (400, 0.875rem/14px, 1.55): prose, chat messages, explanations, reasoning. Cap sustained prose at 65–75ch.
- **Label** (500, 0.75rem/12px, 1.45): the workhorse. Metadata, table cells, chips, captions, form labels, status text.
- **Data** (400 mono, 0.75rem/12px, 1.45): metric values, IDs, endpoints, code, JSON, anything the machine produced.

### Named Rules

**The Two-Workhorse Rule.** Label (12px) and Body (14px) carry the working interface and should remain the overwhelming majority of rendered text. Density is a feature for this audience. The ladder above them exists to rank regions, not to inflate the UI: adding a Headline is how you create hierarchy, enlarging body copy is not.

**The Machine Voice Rule.** Geist Mono is reserved for values the system produced: metrics, run IDs, endpoints, payloads, column names, code. Never set a human-authored label, button, or heading in mono. If you cannot tell whether a string came from the machine or the writer, it is not mono.

**The Weight-Before-Size Rule.** When two elements must be distinguished inside one panel, change weight or ink color first. Reach for a larger type step only when the elements belong to different regions.

## 4. Elevation

This system is flat. There is no ambient shadow vocabulary and none should be introduced. Depth is expressed entirely through tonal layering of the neutral ramp (`#09090b` ground → `#18181b` panel → `#27272a` raised) combined with 1px hairline borders. A card is not a sheet of paper floating above the page; it is a region cut into the panel. This is what keeps a dense screen from turning into visual rubble.

The single exception is **state**. Shadow and glow are permitted only as a response to interaction, never at rest.

### Shadow Vocabulary

- **Focus ring** (`box-shadow: 0 0 0 2px #09090b, 0 0 0 4px #059669`): the standard keyboard focus treatment. Two rings so the indicator survives on any of the three surface layers. Required on every interactive element.
- **Active lift** (`box-shadow: 0 0 0 1px #059669`): optional emphasis for the currently-selected item in a list where a background change alone is too subtle.

### Named Rules

**The Flat-At-Rest Rule.** No element carries a shadow in its default state. Prohibited: ambient card shadows, drop shadows on panels, soft glows behind accents, and any `box-shadow` used to imply hierarchy. If a surface needs to feel higher, move it up the tonal ramp instead.

**The Border-Is-The-Edge Rule.** Every surface boundary is a 1px hairline (`#27272a`, or `#3f3f46` when sitting on a raised layer). Borders are never thicker than 1px, and never colored as an accent stripe.

## 5. Components

### Buttons
- **Shape:** softly cut corners (8px, `rounded-lg`). Consistent across every button in the system.
- **Primary:** Signal Green Deep (`#059669`) with white text, 10px/20px padding, Body type at weight 500. One primary action per view.
- **Hover / Focus:** hover lifts to Signal Green (`#10b981`) over a 150ms color transition. Focus applies the standard focus ring. Disabled drops to 40% opacity with no hue change.
- **Ghost / Secondary:** Ink Panel background, Ink Secondary text, Label type, 6px/12px padding, 1px hairline border. Hover moves to Ink Raised and lifts text to Ink Primary. This is the correct default for every action that is not the single primary one.
- **Destructive:** ghost geometry with Alarm Red text and an Alarm Red wash on hover. Never a solid red fill.

### Chips
- **Style:** Ink Raised background, Ink Muted text, Label type, 2px/8px padding, 4px radius (`rounded`). Status chips take their hue from the semantic vocabulary at wash-background plus light-foreground.
- **State:** a selected chip takes a 1px Signal Green border and Ink Primary text. Unselected chips never carry accent color.

### Cards / Containers
- **Corner Style:** 8px (`rounded-lg`) for panels; 12px reserved for the outermost shell of a region.
- **Background:** Ink Panel on the application ground. Nested content sits on Ink Raised.
- **Shadow Strategy:** none. See Elevation.
- **Border:** 1px Ink Raised hairline on every card.
- **Internal Padding:** 16px standard, 12px in dense list contexts. Never below 8px.

### Inputs / Fields
- **Style:** Ink Panel background, 1px Ink Raised border, 8px radius, 10px/16px padding, Body type.
- **Focus:** border shifts to Signal Green Deep and the standard focus ring applies. Never remove the outline without replacing it.
- **Placeholder:** Ink Muted (`#a1a1aa`). Never Ink Inert.
- **Error / Disabled:** error takes an Alarm Red border with a Label-sized Alarm Red message beneath. Disabled drops to 40% opacity.

### Navigation
- **Style:** the run list is the primary navigation of this product. Items are Label type on Ink Panel, hover to Ink Raised, and the active item takes Ink Primary text with a Signal Green indicator.
- **Density:** navigation items carry at most two signals: their name and one state. A third signal means the item is doing the job of a table row and should become one.

### Confirmation Dialog
The one sanctioned modal. Product register treats a modal as a first-thought failure, and that stands: anything reversible resolves inline or through progressive disclosure. The exception is an action that is irreversible **and** affects people who are not present — promoting a deployment swaps the model answering live prediction traffic. Built on native `<dialog>` + `showModal()` for the top layer, focus trap, Esc-dismiss, and background inerting. Zinc-900 panel, 1px zinc-700 hairline, `zinc-950/70` backdrop, no shadow. One primary (emerald) and one ghost (cancel); cancel is always reachable by Esc and by backdrop click.

### The Status Dot
The system's signature primitive. A `9999px` dot, 6–8px, expressing run and deployment state in the smallest possible footprint: Signal Green for completed or live, Readout Sky with a pulse for in-flight, Alarm Red for failed, Ink Inert for idle. It is the one place Ink Inert is correct, because it is not text. The dot always sits left of the label it describes and never carries a border.

## 6. Do's and Don'ts

### Do:
- **Do** use `#a1a1aa` (Ink Muted) as the floor for every readable string, including placeholders. It measures 7.75:1 against the ground.
- **Do** build depth from the tonal ramp: `#09090b` ground, `#18181b` panel, `#27272a` raised.
- **Do** give every interactive element the standard two-ring focus treatment. The audience includes keyboard-driven practitioners.
- **Do** reserve Geist Mono for machine-produced values: metrics, IDs, endpoints, payloads, code.
- **Do** introduce a Headline (20px) step when a region needs to outrank its neighbors. This is the sanctioned fix for a flat scroll.
- **Do** keep exactly one primary action per view; everything else is a ghost button.
- **Do** pair every animation with a `prefers-reduced-motion: reduce` alternative, and keep state transitions in the 150–250ms band.
- **Do** make empty states teach the interface: what this panel will show, and what the user does to fill it.

### Don't:
- **Don't** use `#71717a` (Ink Inert) for text at any size. It fails AA at 4.12:1. The 98 existing usages are debt to be repaid, not a pattern to copy.
- **Don't** add a `box-shadow` to any element at rest. Flat is the system, not an oversight.
- **Don't** use `border-left` or `border-right` above 1px as a colored accent stripe on cards, callouts, or list items.
- **Don't** introduce a new hue because a component needed visual variety. A new color requires a new meaning first.
- **Don't** let a navigation item carry more than two signals. A run pill stacking a status dot, name, target, version, tournament stripe, and a recommendation badge has become a table row wearing a chip's clothes.
- **Don't** build a **black-box AutoML dashboard**: never show a metric without a path to the reasoning behind it.
- **Don't** drift toward **no-code business SaaS**: no illustration spots, no oversized rounded cards, no encouraging color washes on neutral information.
- **Don't** render the product as a **generic AI-chat wrapper**: no sparkle iconography, no gradient text, no `background-clip: text`, no glassmorphism.
- **Don't** become an **overloaded enterprise admin**: if a panel presents six controls at identical weight, it has no hierarchy and the design is not finished.
- **Don't** use `clamp()` fluid type. This is product UI at consistent DPI; the rem ladder is fixed on purpose.
- **Don't** animate anything that does not communicate state. No entrance choreography on a surface the user opened to read.
