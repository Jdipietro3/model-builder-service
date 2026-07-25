---
target: frontend/src/components/Workspace.tsx
total_score: 21
p0_count: 1
p1_count: 2
timestamp: 2026-07-22T17-24-49Z
slug: frontend-src-components-workspace-tsx
---
Method: dual-agent (A: design review · B: detector + browser evidence), both Sonnet, isolated and parallel. Neither assessor was told the previous run's findings, score, or what changed.

## Design Health Score

| # | Heuristic | Score | Δ | Key Issue |
|---|-----------|-------|---|-----------|
| 1 | Visibility of System Status | 3 | = | LIVE badge and reconciliation banner fixed the deployed-state blindness; a silently swallowed dataset-update catch remains. |
| 2 | Match System / Real World | 3 | +1 | Metric glossary and humanized task types landed; acronyms still assume fluency with the glossary closed. |
| 3 | User Control and Freedom | 2 | = | No cancel on in-flight training; promote is instant and irreversible. |
| 4 | Consistency and Standards | 2 | +1 | Promote is now one action with one clear alternative; one chart palette. Still 3 emerald primaries in some states. |
| 5 | Error Prevention | 1 | -1 | Switching what serves production traffic is a single unconfirmed click, now the standout weakness. |
| 6 | Recognition Rather Than Recall | 3 | +1 | Live/Recommended/Tournament are legible and their disagreement is stated in-place. |
| 7 | Flexibility and Efficiency | 1 | = | Uploads are keyboard-operable now, but no shortcuts, no bulk actions, no side-by-side compare. |
| 8 | Aesthetic and Minimalist Design | 2 | +1 | Disclosures cut the flat scroll; top-level headings still all render at one size. |
| 9 | Error Recovery | 2 | = | Dataset-update errors surface in the chat rail, away from the control that caused them. |
| 10 | Help and Documentation | 2 | = | Glossary exists but is collapsed by default for the persona who needs it most. |
| **Total** | | **21/40** | **+3** | **Acceptable — was 18/40 (Poor)** |

## Anti-Patterns Verdict

**LLM assessment.** Still not classic AI slop, and the component vocabulary now reads as genuinely disciplined. It fails the product-register test in one specific, self-inflicted way: the type ladder is not being used as a ladder. The project title and all three section headers render at the same 20px/600 Headline step, and the 30px Display step that DESIGN.md reserves for page identity is never invoked on this route. The hierarchy fix was half-applied — Headline was introduced, but by flattening Display down into it rather than ranking above it.

**Deterministic scan.** `detect.mjs`: **3 findings, down from 23**. All three are the same false positive — the detector pairs Tailwind classes across opposite branches of a ternary, so `text-zinc-400` (which always pairs with `bg-zinc-800`) is misread as sitting on `bg-emerald-950` / `bg-sky-950` / `bg-emerald-500`. Verified by reading all three sites. **Effective real CLI findings: 0.**

**Live overlay** surfaced classes of problem the static scan cannot see:
- `nested-cards` (7) — card inside card, which DESIGN.md calls always wrong. Partly introduced by this pass: the new `<details>` disclosures carry their own `rounded-lg border` inside already-bordered cards.
- `line-length` (~10) — paragraphs running 87–139 characters per line against a documented 65–75ch cap. Pre-existing and never addressed.
- `cramped-padding` (1) — persists from the previous run.
- `ai-color-palette` (5) and `overused-font` (2) — both false positives here: the flagged hues are the documented Readout Sky role, and one type family is explicitly correct for the product register.

**Measured accessibility — the area that actually moved:**

| Metric | Before | After |
|---|---|---|
| Contrast failures (live DOM, `<option>` excluded) | 3 pairs incl. 2.46:1 and 3.64:1 | **0** across 331 text elements |
| Focus coverage | essentially none compiled | **19/21**, both CSS rules verified present in the stylesheet |
| Uncovered interactive elements | 14 app elements | **2, both Next.js devtools overlay** — zero app-authored |
| Unnamed controls | 2 symbol-only | **0 app-authored** |
| Heading structure | `h2` → `h4` skip | **clean, no skips** |
| `prefers-reduced-motion` | absent | **present** |
| Sub-12px arbitrary font sizes | 19 | **0** |
| Undocumented palette hexes | 3 across 4 files | **0** |

## Overall Impression

The mechanical layer is genuinely fixed and the state-legibility problem is solved — the reconciliation banner is the strongest thing added, and it does exactly what PRODUCT.md's principles demand. But the score moved only 3 points, and that is the honest result: most of the work landed on measurable debt (contrast, focus, palette, font floor), while the two issues that most shape how the interface *feels* were left standing. The biggest one was never in scope: the single highest-stakes action in the product still has no confirmation.

## What's Working

1. **The reconciliation banner.** When live and recommended disagree, the interface now says so in plain language with a resolution path, rather than leaving the user to notice. This is the glass-box promise made concrete.
2. **Diagnostics as progressive disclosure.** Collapsed `<details>` whose summaries preview the finding before opening ("2 features may be leaking the answer") — native, keyboard-accessible, teaches trust-checking without forcing density on everyone.
3. **The run pill vocabulary.** One dot per lifecycle state, one badge, capped at the documented two-signal ceiling. The place complexity is managed best.

## Priority Issues

**[P0] "Promote to live deployment" fires on one click with no confirmation.**
It changes what serves real production traffic, has no undo, no diff of what changes, and identical visual weight to "Retrain" beside it. PRODUCT.md names this exact moment as needing reassurance; it is currently the least ceremonious interaction on the page. Fix with an inline confirm that expands to show the old-vs-new metric delta and requires a second click — not a modal.
*Command:* `/impeccable harden`

**[P1] The type ladder is collapsed at the top.**
Project title and "Data" / "Model" / "Predict on new data" all render at 20px/600. Display (30px) is unused on this route, so nothing outranks anything above card level. Promote the project `<h1>` to `text-display` and leave sections at `text-headline`.
*Command:* `/impeccable typeset`

**[P1] Three solid-emerald primaries still co-visible.**
When Promote is available, "Promote to live deployment", "Upload CSV to score", and chat "Send" are all solid emerald at once. The previous pass demoted "Run prediction" but stopped there, reasoning one primary *per region*; DESIGN.md actually says one primary *per view*. Demote "Upload CSV to score" to ghost.
*Command:* `/impeccable clarify`

**[P2] Nested cards, partly introduced by the last pass.**
Seven card-in-card instances, including the new disclosures carrying `rounded-lg border` inside already-bordered cards. Give disclosures a borderless, background-only treatment.
*Command:* `/impeccable layout`

**[P2] Prose runs 87–139 characters per line** against a 65–75ch cap, in reasoning blocks and caveat lists — the longest-form text in the product, where it matters most.
*Command:* `/impeccable typeset`

**[P2] Dataset-update errors surface in the wrong region.** `DatasetUpdateControl.submit()` swallows its catch and the message appears as a chat bubble in the right rail, away from the control the user was operating. `PredictSection` already does this correctly inline.
*Command:* `/impeccable clarify`

## Persona Red Flags

**Alex (power user):** No keyboard shortcuts for run switching or deploy actions. Comparing two runs means clicking each pill and re-reading the whole stack; no side-by-side outside the auto tournament table. No bulk actions.

**Jordan (the primary persona — codes, no deep ML):** Five unexplained acronyms render at once with the glossary collapsed by default. For the user PRODUCT.md puts first, the glossary should default open on a first completed run.

**Sam (accessibility-dependent):** Materially better — zero contrast failures, focus rings verified compiled, clean heading order. Remaining: the `×` cancel in `DatasetUpdateControl` announces as "× button", and importance-bar numerics live only in hover `title`.

**Priya (project-specific: promoted engineer now owning a live model):** Opens the project to check her deployed model and finds Promote sitting visually equal to Retrain and Upload, three emerald buttons with no cue which is momentous. A misclick on Promote has no confirmation and no undo.

## Questions to Consider

- The reconciliation banner proves this team can resolve ambiguous state in the interface. Why doesn't the promote action itself get the same care, when it's the one moment PRODUCT.md names explicitly?
- Display exists in the system specifically to rank the project title above everything else. Was skipping it an oversight, or a belief that workspace mode should stay flatter than the design system prescribes?
- Would a section-level region label do more for the flat-scroll problem than a font-size change alone?
