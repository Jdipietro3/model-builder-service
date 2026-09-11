---
name: Metis
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
  accent-wash: "#2e2110"
  accent-line: "#634018"
  accent-dim: "#85541a"
  accent-edge: "#ab6e1f"
  accent: "#d08f2c"
  accent-bright: "#edb55c"
  accent-ink: "#09090b"
  alarm: "#e0706e"
  alarm-wash: "#3a1618"
  info: "#22c0d6"
  info-wash: "#0a262b"
  bracket: "#8b7ff0"
  bracket-wash: "#211c3d"
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
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
    typography: "{typography.body}"
    rounded: "{rounded.panel}"
    padding: "10px 20px"
  button-primary-hover:
    backgroundColor: "{colors.accent-bright}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-secondary}"
    typography: "{typography.label}"
    rounded: "{rounded.panel}"
    padding: "6px 12px"
  button-ghost-hover:
    backgroundColor: "{colors.ink-panel}"
    textColor: "{colors.accent}"
  input-text:
    backgroundColor: "{colors.ink-panel}"
    textColor: "{colors.ink-primary}"
    typography: "{typography.body}"
    rounded: "{rounded.panel}"
    padding: "10px 16px"
  section-band:
    backgroundColor: "transparent"
    borderBottom: "1px solid {colors.hairline}"
    textColor: "{colors.ink-secondary}"
    padding: "0 0 8px 0"
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

# Design System: Metis

## 1. Overview

**Creative North Star: "The Instrument Panel"**

This is the console of a serious machine. A user comes here to read state, form judgment, and act: which model won, whether the evaluation is honest, what is serving traffic right now. The interface is the glass over the dials. It is not the subject. Every pixel that draws attention to itself is a pixel stolen from a readout the user needed.

The system is near-black, near-monochrome, and dense. One amber carries every affirmative signal; three further hues carry status and nothing else. Depth is built from tonal layers of the same neutral rather than from shadow, and — since the 2026 redesign — from *typography and hairlines rather than from boxes*. Type is small and tight by design, because practitioners read tables and metrics here, not prose.

This system explicitly rejects the **black-box AutoML dashboard** (a score handed down with no visible mechanism), the **no-code business SaaS** (bright, rounded, illustrated, addressed to everyone), the **generic AI-chat wrapper** (a bubble stream with a sparkle and a gradient), and the **overloaded enterprise admin** (every control crammed in at equal weight with no hierarchy). The last of these is the live risk: this codebase drifts toward it every time a feature adds its own controls without ranking them.

**Key Characteristics:**
- Near-black neutral ground (`#09090b`) with two tonal layers above it
- Exactly one accent hue — amber; status hues are semantic, never decorative
- Flat surfaces, hairline borders, no ambient shadow, and **few enclosing boxes**
- Dense by intent: 12px and 14px carry the working UI
- Monospace reserved strictly for machine-produced values

## 2. Colors

A machined graphite ground with a single instrument amber, plus a three-hue status vocabulary that never appears for decoration.

Contrast figures below are measured against the three surface layers this system uses: ground `#09090b`, panel `#18181b`, raised `#27272a`. A token that passes only on the ground will fail the moment it lands on a hover row, so all three are stated.

### Primary

**The accent ramp.** Amber replaced emerald when the product became Metis: the approved data palettes are warm, and a cool action language on the same screen put two signals in competition for the eye.

| token | hex | ground | panel | raised | use |
|---|---|---|---|---|---|
| `accent-wash` | `#2e2110` | 1.27 | — | — | background tint only, never text |
| `accent-line` | `#634018` | 2.16 | — | — | hairline on an accent surface |
| `accent-dim` | `#85541a` | 3.11 | — | — | non-text fills: bars, dots, tracks |
| `accent-edge` | `#ab6e1f` | 4.72 | 4.20 | **3.53** | borders and large text **only** |
| `accent` | `#d08f2c` | **7.25** | 6.45 | 5.42 | the accent; safe as text everywhere |
| `accent-bright` | `#edb55c` | 10.77 | 9.59 | 8.06 | the figure the user came to read |

`accent-ink` (`#09090b`) is the text color **on** an accent fill. Near-black, not white: white measures 2.75 on `accent` and fails AA outright, while near-black measures 7.25.

### Neutral
- **Ink Void** (`#09090b`): the application ground. The page itself, and the deepest layer of any nested surface.
- **Ink Panel** (`#18181b`): the working surface. Reserved now for genuinely discrete objects — chat cards, a deployment, inputs, the confirm dialog.
- **Ink Raised** (`#27272a`): the lifted layer. Hover states, chips, selected rows. Also serves as the default hairline.
- **Hairline Strong** (`#3f3f46`): borders that must survive against a raised surface, and separators inside dense tables.
- **Ink Primary** (`#f4f4f5`): headings, the value the user came to read, active labels.
- **Ink Secondary** (`#d4d4d8`): body copy and sustained reading.
- **Ink Muted** (`#a1a1aa`): the floor for anything a human must read. Labels, captions, metadata, placeholders, secondary units.
- **Ink Inert** (`#71717a`): non-text only. Icon strokes, dividers, disabled marks, decorative rules.

### Tertiary

The status vocabulary, drawn from the approved categorical palette so the UI and the charts speak one language. Each hue owns one meaning. Each wash sits at 1.23–1.26 against the ground, deliberately matched to `accent-wash`'s 1.27, so a red panel and an amber panel read as the same depth of tint and only the hue distinguishes them.

- **Alarm** (`#e0706e` on wash `#3a1618`): failure, error, destructive confirmation, and the trust layer's leakage findings. 6.36 on ground, 5.13 on its own wash. Never used for emphasis.
- **Info** (`#22c0d6` on wash `#0a262b`): neutral information, in-flight and streaming activity, comparison deltas. 9.08 / 7.23.
- **Bracket** (`#8b7ff0` on wash `#211c3d`): tournament and ensemble affordances only. 6.06 / 4.92. This hue is a namespace, not a mood.

**There is deliberately no caution hue.** Amber carried it before the rebrand and amber is now the accent; overloading it would make the accent meaningless. Warnings and caveats render as ordinary Ink Secondary text with a small Alarm dot marker — no wash, no chip. This product surfaces honest caveats constantly, and washing every one of them in red would turn a calm instrument into an alarming one.

### Data palettes

Two palettes exist for charts and are not UI colors.

**Sequential** — `#2e2110 · #463014 · #634018 · #85541a · #ab6e1f · #d08f2c · #edb55c`. Encodes *amount*: null rate, cardinality, drift magnitude, confusion-matrix density. Dark is low. Text over the top three steps takes `#09090b`; below that, `#f4f4f5`.

**Categorical** — `#22c0d6 · #8b7ff0 · #e0a03c · #4fb477 · #e0706e · #d68bc0 · #8e94a6`. Encodes *kind*: series identity, class labels, dtype chips. Every entry clears AA on ground and panel (5.39–9.08), so these are safe as text as well as as marks. Use in listed order; do not reorder for taste.

Green (`#4fb477`) exists **only inside charts**, as the improvement delta. It is not a UI accent and must never be used as one.

### Named Rules

**The One Signal Rule.** Amber is the only non-status hue in the system and must occupy under 10% of any screen. If two things on screen are amber, at most one of them is an action; the other is state. Three amber things means the screen has lost its hierarchy.

**The Inert Floor Rule.** `#71717a` (Ink Inert) is **prohibited for text of any size**. Computed from the token it measures 4.12:1 against the application ground; measured in the rendered page it is worse, **3.85:1**, because Tailwind v4's OKLCH pipeline resolves it nearer `rgb(109,109,109)`. `#a1a1aa` (Ink Muted) is the floor for every readable string, including placeholders, and measures 7.75:1.

**The Semantic Hue Rule.** Alarm, Info, and Bracket carry meaning only. A hue may never be chosen because a component needed visual variety. If a new feature wants a new color, it wants a new meaning, and it must justify that meaning before it gets a hue.

**The Dark-Ink-On-Amber Rule.** Any filled accent surface takes `accent-ink` text. White on amber fails AA at every step of the ramp.

## 3. Typography

**Display / Body Font:** Geist (with `system-ui`, `sans-serif`)
**Machine Font:** Geist Mono (with `ui-monospace`, `monospace`)

**Character:** One geometric grotesque doing all the work, which is correct for an instrument: consistent letterforms across labels, values, and prose mean the eye never re-calibrates. Contrast comes from weight and size, never from a second family. Geist Mono is the machine's voice; it appears wherever a value was computed rather than written.

### Hierarchy

A fixed rem ladder at roughly a 1.2 ratio, deliberately bottom-heavy: the two smallest steps carry the working interface, and the steps above exist to let regions outrank each other.

- **Display** (600, 1.875rem/30px): page-level identity only. One per route. Never inside a panel.
- **Headline** (600, 1.25rem/20px): the name of a major region the user navigates between.
- **Title** (500, 1rem/16px): section headings inside a region.
- **Body** (400, 0.875rem/14px): prose, chat messages, explanations. Cap sustained prose at 65–75ch.
- **Label** (500, 0.75rem/12px): the workhorse. Metadata, table cells, chips, captions, form labels, status text.
- **Data** (400 mono, 0.75rem/12px): metric values, IDs, endpoints, code, JSON.

### Named Rules

**The Two-Workhorse Rule.** Label (12px) and Body (14px) carry the working interface and should remain the overwhelming majority of rendered text. Density is a feature for this audience.

**The Machine Voice Rule.** Geist Mono is reserved for values the system produced: metrics, run IDs, endpoints, payloads, column names, code. Never set a human-authored label, button, or heading in mono.

**The Weight-Before-Size Rule.** When two elements must be distinguished inside one panel, change weight or ink color first. Reach for a larger type step only when the elements belong to different regions.

**The Type-Carries-Hierarchy Rule.** *(New with the borderless redesign.)* Card borders used to do the work of separating regions. With most of them gone, that job belongs to the ladder: every tab opens with one Headline, and each section within it takes a Title over a hairline. A borderless scroll with no Headline is not minimal, it is flat — and flat is the failure mode this rule exists to prevent.

**The Figure Rule.** In any readout, the number the user came for is set in `accent-bright` Geist Mono; its label is Ink Muted; surrounding prose is Ink Secondary. This is the primary way color enters text, and it is what "highlight what matters" means concretely.

## 4. Elevation

This system is flat. There is no ambient shadow vocabulary and none should be introduced. Depth is expressed through tonal layering of the neutral ramp (`#09090b` → `#18181b` → `#27272a`) plus 1px hairline borders. A card is not a sheet of paper floating above the page; it is a region cut into the panel.

The single exception is **state**. Shadow and glow are permitted only as a response to interaction, never at rest.

### Shadow Vocabulary

- **Focus ring** (`0 0 0 2px #09090b, 0 0 0 4px #ab6e1f`): the standard keyboard focus treatment. Two rings so the indicator survives on any of the three surface layers. Required on every interactive element. It uses `accent-edge` rather than `accent` because at 4px it is a border, not text, and the darker step reads as less shouty against a dense screen.
- **Active lift** (`0 0 0 1px #ab6e1f`): optional emphasis for the currently-selected item in a list where a background change alone is too subtle.

### Named Rules

**The Flat-At-Rest Rule.** No element carries a shadow in its default state. Prohibited: ambient card shadows, drop shadows on panels, soft glows behind accents, and any `box-shadow` used to imply hierarchy.

**The Border-Is-The-Edge Rule.** Every surface boundary is a 1px hairline (`#27272a`, or `#3f3f46` on a raised layer). Borders are never thicker than 1px and never colored as an accent stripe.

## 5. Components

### The Section Band — the default container

A Title (or Headline) row with a 1px hairline beneath it, content sitting directly on the ground. **This is now the standard way to group content.** It replaced the bordered `rounded-lg border bg-zinc-900` panel as the default, because 26 such boxes on a dense screen turn hierarchy into rubble; a band separates regions using one hairline instead of four.

Reach for the bordered panel only when the thing inside it is a genuinely discrete *object* the user can act on as a unit — a chat card, one deployment, an input, the confirm dialog. If the box is only there to say "these things go together," it should be a band.

### Buttons

Three tiers, and no more.

- **Primary:** `accent` fill, `accent-ink` text, 10px/20px, 8px radius, Body at weight 500. Hover lifts to `accent-bright`. **One primary action per view.**
- **Ghost:** *no border at rest.* Transparent background, Ink Secondary text, Label type, 6px/12px. Hover moves to Ink Panel with `accent` text. This is the correct default for every action that is not the single primary one, and dropping the resting border from it is most of what makes the redesign read as sleek.
- **Destructive:** ghost geometry with Alarm text and an Alarm wash on hover. Never a solid red fill.

Disabled drops to 40% opacity with no hue change.

### Chips
- **Style:** Ink Raised background, Ink Muted text, Label type, 2px/8px, 4px radius. Status chips take their hue from the semantic vocabulary at wash-background plus light-foreground.
- **State:** a selected chip takes a 1px `accent-edge` border and Ink Primary text. Unselected chips never carry accent color.

### Tables
Header row in Ink Muted Label type over a hairline; rows separated by hairlines at 50% opacity; **no enclosing box and no panel fill.** Tables run full-bleed in their content column. Values are Data (mono); names and categories are Label.

### Inputs / Fields
- **Style:** Ink Panel background, 1px Ink Raised border, 8px radius, 10px/16px, Body type.
- **Focus:** border shifts to `accent-edge` and the standard focus ring applies.
- **Placeholder:** Ink Muted. Never Ink Inert.
- **Error:** Alarm border with a Label-sized Alarm message beneath.

### Navigation
- **Style:** Label type, transparent at rest, hover to Ink Panel, and the active item takes Ink Primary text with an `accent` indicator.
- **Density:** navigation items carry at most two signals: their name and one state. A third signal means the item is doing the job of a table row and should become one.

### Confirmation Dialog
The one sanctioned modal, for actions that are irreversible **and** affect people who are not present — promoting a deployment swaps the model answering live traffic. Built on native `<dialog>` + `showModal()` for the top layer, focus trap, Esc-dismiss, and background inerting. Ink Panel surface, 1px hairline, `zinc-950/70` backdrop, no shadow. One primary and one ghost; cancel is always reachable by Esc and by backdrop click.

### The Status Dot
The system's signature primitive. A `9999px` dot, 6–8px, expressing run and deployment state in the smallest possible footprint:

| state | color |
|---|---|
| live / serving | `accent` |
| running | `info`, pulsing |
| failed | `alarm` |
| completed | Ink Muted |
| idle | Ink Inert |

**Completed is deliberately quiet.** Most runs complete; if the resting state were amber it would consume the entire accent budget and the dot would stop signalling anything. The dot always sits left of the label it describes and never carries a border. This and chart marks are the only correct uses of Ink Inert, because they are not text.

### The Mark
An asterisk (the moment of counsel) above an open eye (the foresight it produces). `app/icon.svg` is the tab icon and paints its own near-black ground so it survives on light browser chrome; `<MetisMark>` is the in-app twin, drawn in `currentColor` on transparency. Until a real wordmark exists, the lockup is the mark beside "Metis" set in Geist.

## 6. Do's and Don'ts

### Do:
- **Do** use a section band as the default container, and reserve the bordered panel for discrete objects.
- **Do** open every tab with one Headline. With borders gone, type is the only thing holding hierarchy.
- **Do** set the figure the user came for in `accent-bright` mono, its label in Ink Muted.
- **Do** use `#a1a1aa` (Ink Muted) as the floor for every readable string, including placeholders.
- **Do** build depth from the tonal ramp: `#09090b` ground, `#18181b` panel, `#27272a` raised.
- **Do** give every interactive element the standard two-ring focus treatment.
- **Do** reserve Geist Mono for machine-produced values.
- **Do** keep exactly one primary action per view; everything else is a ghost button.
- **Do** pair every animation with a `prefers-reduced-motion: reduce` alternative, and keep state transitions in the 150–250ms band.
- **Do** make empty states teach the interface: what this panel will show, and what the user does to fill it.

### Don't:
- **Don't** put a border and a panel fill around content that is merely grouped. That is a band.
- **Don't** give a ghost button a resting border.
- **Don't** use white text on an amber fill. It fails AA at every step of the ramp; use `accent-ink`.
- **Don't** use `accent-edge` (`#ab6e1f`) as body text — it measures 3.53 on a raised surface and fails.
- **Don't** use `#71717a` (Ink Inert) for text at any size.
- **Don't** add a `box-shadow` to any element at rest.
- **Don't** use `border-left` or `border-right` above 1px as a colored accent stripe.
- **Don't** introduce a new hue because a component needed visual variety.
- **Don't** use green as a UI color. It lives in charts, as the improvement delta, and nowhere else.
- **Don't** let a navigation item carry more than two signals.
- **Don't** build a **black-box AutoML dashboard**: never show a metric without a path to the reasoning behind it.
- **Don't** drift toward **no-code business SaaS**: no illustration spots, no oversized rounded cards, no encouraging color washes on neutral information.
- **Don't** render the product as a **generic AI-chat wrapper**: no sparkle iconography, no gradient text, no `background-clip: text`, no glassmorphism.
- **Don't** become an **overloaded enterprise admin**: if a panel presents six controls at identical weight, it has no hierarchy and the design is not finished.
- **Don't** use `clamp()` fluid type. The rem ladder is fixed on purpose.
- **Don't** animate anything that does not communicate state.
